<?php

declare(strict_types=1);

namespace App\Services;

use PDO;
use Exception;

/**
 * Service handling preview game dashpoint relocation (rerolling).
 */
class RerollService
{
    use MailerTrait;

    private PDO $db;
    private GeoContextService $geoService;
    private array $config;

    public function __construct(PDO $db, ?GeoContextService $geoService = null, ?array $config = null)
    {
        $this->db = $db;
        if ($config === null) {
            $configPath = __DIR__ . '/../config.ini';
            $this->config = file_exists($configPath) ? (parse_ini_file($configPath, true) ?: []) : [];
        } else {
            $this->config = $config;
        }

        if ($geoService === null) {
            $apiKey = $this->config['google']['GOOGLE_MAPS_API_KEY']
                ?? ($this->config['GOOGLE_MAPS_API_KEY'] ?? '');
            $apiBaseUrl = $this->config['google']['GOOGLE_MAPS_API_BASE_URL']
                ?? ($this->config['GOOGLE_MAPS_API_BASE_URL']
                ?? ((getenv('APP_ENV') === 'testing') ? 'http://127.0.0.1:8081/api/mock_maps.php?' : 'https://maps.googleapis.com'));
            $this->geoService = new GeoContextService($this->db, $apiKey, $apiBaseUrl);
        } else {
            $this->geoService = $geoService;
        }
    }

    /**
     * Rerolls a preview dashpoint within land constraints and configurable radius.
     *
     * @param int $userId
     * @param string $dashpointId
     * @param string|null $reason
     * @return array
     * @throws Exception
     */
    public function rerollDashpoint(int $userId, string $dashpointId, ?string $reason = null): array
    {
        $reason = $reason !== null ? trim($reason) : '';
        if ($reason === '') {
            throw new Exception("Reroll reason is required.");
        }
        if (mb_strlen($reason) >= 100) {
            throw new Exception("Reroll reason must be less than 100 characters.");
        }

        $rerollSection = $this->config['reroll'] ?? $this->config;

        $rerollEnabled = filter_var($rerollSection['REROLL_ENABLED'] ?? true, FILTER_VALIDATE_BOOLEAN);
        $maxRadiusKm = (float) ($rerollSection['REROLL_MAX_RADIUS_KM'] ?? 10.0);
        $maxRerolls = (int) ($rerollSection['REROLL_MAX_PER_PLAYER'] ?? 3);

        if (!$rerollEnabled) {
            throw new Exception("Dashpoint rerolling is currently disabled.");
        }

        // 1. Fetch User details and verify finds count
        $stmtUser = $this->db->prepare(
            "SELECT username FROM users WHERE id = :user_id"
        );
        $stmtUser->execute(['user_id' => $userId]);
        $userRow = $stmtUser->fetch();
        if (!$userRow) {
            throw new Exception("User not found.");
        }
        $username = $userRow['username'];

        $stmtFinds = $this->db->prepare(
            "SELECT COUNT(*) AS find_count FROM visits WHERE user_id = :user_id AND is_attempt = FALSE AND status = 'approved'"
        );
        $stmtFinds->execute(['user_id' => $userId]);
        $findsCount = (int) ($stmtFinds->fetch()['find_count'] ?? 0);

        if ($findsCount < 1) {
            throw new Exception("You must have logged at least 1 verified find to reroll a dashpoint.");
        }

        // 2. Fetch Dashpoint info and game preview status
        $stmtDp = $this->db->prepare(
            "SELECT d.id, d.game_id, ST_Latitude(d.location) AS lat, ST_Longitude(d.location) AS lon,
                    g.start_time, g.end_time, g.is_active
             FROM dashpoints d
             JOIN games g ON d.game_id = g.id
             WHERE d.id = :dashpoint_id"
        );
        $stmtDp->execute(['dashpoint_id' => $dashpointId]);
        $dp = $stmtDp->fetch();

        if (!$dp) {
            throw new Exception("Dashpoint not found.");
        }

        $gameId = (int) $dp['game_id'];
        $origLat = (float) $dp['lat'];
        $origLon = (float) $dp['lon'];
        $isActive = (bool) $dp['is_active'];
        $startTime = strtotime($dp['start_time']);

        if ($isActive || $startTime <= time()) {
            throw new Exception("Dashpoints can only be rerolled while the game is in preview.");
        }

        // 3. Verify point has not already been rerolled
        $stmtDpRerolls = $this->db->prepare(
            "SELECT COUNT(*) AS reroll_count FROM dashpoint_rerolls WHERE dashpoint_id = :dashpoint_id"
        );
        $stmtDpRerolls->execute(['dashpoint_id' => $dashpointId]);
        $dpRerollCount = (int) ($stmtDpRerolls->fetch()['reroll_count'] ?? 0);

        if ($dpRerollCount > 0) {
            throw new Exception("This dashpoint has already been rerolled during preview.");
        }

        // 4. Verify user quota
        $stmtUserRerolls = $this->db->prepare(
            "SELECT COUNT(*) AS user_reroll_count FROM dashpoint_rerolls WHERE user_id = :user_id AND game_id = :game_id"
        );
        $stmtUserRerolls->execute(['user_id' => $userId, 'game_id' => $gameId]);
        $userRerollCount = (int) ($stmtUserRerolls->fetch()['user_reroll_count'] ?? 0);

        if ($userRerollCount >= $maxRerolls) {
            throw new Exception("You have reached your maximum reroll limit of {$maxRerolls} for this game.");
        }

        // 5. Execute Python spatial helper script
        $newCoords = $this->executePythonRerollScript($origLat, $origLon, $maxRadiusKm);
        $newLat = (float) $newCoords['lat'];
        $newLon = (float) $newCoords['lon'];

        // 6. Transactional Database Update
        $this->db->beginTransaction();
        try {
            $wktNew = "POINT({$newLat} {$newLon})";
            $stmtUpdate = $this->db->prepare(
                "UPDATE dashpoints 
                 SET location = ST_GeomFromText(:wkt, 4326), country_code = NULL, state_province = NULL 
                 WHERE id = :dashpoint_id"
            );
            $stmtUpdate->execute(['wkt' => $wktNew, 'dashpoint_id' => $dashpointId]);

            $wktOld = "POINT({$origLat} {$origLon})";
            $stmtInsertLog = $this->db->prepare(
                "INSERT INTO dashpoint_rerolls (dashpoint_id, game_id, user_id, old_location, new_location, reason)
                 VALUES (:dashpoint_id, :game_id, :user_id, ST_GeomFromText(:old_wkt, 4326), ST_GeomFromText(:new_wkt, 4326), :reason)"
            );
            $stmtInsertLog->execute([
                'dashpoint_id' => $dashpointId,
                'game_id' => $gameId,
                'user_id' => $userId,
                'old_wkt' => $wktOld,
                'new_wkt' => $wktNew,
                'reason' => $reason
            ]);

            $this->db->commit();
        } catch (Exception $e) {
            $this->db->rollBack();
            throw new Exception("Database update failed during reroll: " . $e->getMessage());
        }

        $rerollsLeft = $maxRerolls - ($userRerollCount + 1);

        $oldGeoContext = $this->geoService->getDashpointContext($origLat, $origLon, $dashpointId);

        // 7. Dispatch Email Notification
        $this->sendRerollNotificationEmail(
            $username,
            $dashpointId,
            $origLat,
            $origLon,
            $newLat,
            $newLon,
            $rerollsLeft,
            $maxRerolls,
            $reason,
            $oldGeoContext
        );

        return [
            "status" => "success",
            "message" => "Dashpoint successfully rerolled.",
            "dashpoint_id" => $dashpointId,
            "old_lat" => $origLat,
            "old_lon" => $origLon,
            "new_lat" => $newLat,
            "new_lon" => $newLon,
            "rerolls_left" => $rerollsLeft,
            "max_rerolls" => $maxRerolls
        ];
    }

    /**
     * Executes the Python reroll CLI script. Protected for unit test overriding.
     *
     * @param float $origLat
     * @param float $origLon
     * @param float $maxRadiusKm
     * @return array
     * @throws Exception
     */
    protected function executePythonRerollScript(float $origLat, float $origLon, float $maxRadiusKm): array
    {
        if (getenv('APP_ENV') === 'testing') {
            return [
                'status' => 'success',
                'lat' => $origLat + 0.005,
                'lon' => $origLon + 0.005
            ];
        }

        $pythonBin = __DIR__ . '/../../.venv/bin/python';
        if (!file_exists($pythonBin)) {
            $pythonBin = 'python3';
        }
        $projectRoot = dirname(__DIR__, 2);
        $scriptPath = __DIR__ . '/../scripts/reroll_dashpoint.py';
        $landZipPath = $projectRoot . '/data/ne_10m_land.zip';
        $lakesZipPath = $projectRoot . '/data/ne_10m_lakes.zip';
        $cmd = sprintf(
            'PYTHONPATH=%s %s %s --lat %f --lon %f --max-radius-km %f --land-zip %s --lakes-zip %s 2>&1',
            escapeshellarg($projectRoot),
            escapeshellarg($pythonBin),
            escapeshellarg($scriptPath),
            $origLat,
            $origLon,
            $maxRadiusKm,
            escapeshellarg($landZipPath),
            escapeshellarg($lakesZipPath)
        );

        $output = [];
        $returnCode = 0;
        exec($cmd, $output, $returnCode);

        $jsonStr = implode("\n", $output);
        $result = json_decode($jsonStr, true);

        if ($returnCode !== 0 || !is_array($result) || ($result['status'] ?? '') !== 'success') {
            $errMsg = $result['message'] ?? ($jsonStr ?: 'Unknown Python script failure');
            throw new Exception("Failed to relocate dashpoint on land: " . $errMsg);
        }

        return $result;
    }
}
