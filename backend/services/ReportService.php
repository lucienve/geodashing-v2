<?php

declare(strict_types=1);

namespace App\Services;

use PDO;
use PDOException;

/**
 * Class ReportService
 *
 * Encapsulates the core business logic required to validate proximity
 * and persist Dashpoint visits, designed to allow for PHPUnit testing.
 */
class ReportService
{
    use MailerTrait;

    /**
     * @var PDO The configured database connection.
     */
    private PDO $db;

    /**
     * @var GeoContextService
     */
    private GeoContextService $geoService;

    /**
     * Constructor.
     *
     * @param PDO $db The PDO connection instance.
     * @param GeoContextService|null $geoService Optional injected GeoContextService for testing.
     */
    public function __construct(PDO $db, ?GeoContextService $geoService = null)
    {
        $this->db = $db;
        if ($geoService === null) {
            $configPath = __DIR__ . '/../config.ini';
            $config = file_exists($configPath) ? parse_ini_file($configPath) : [];
            $apiKey = $config['GOOGLE_MAPS_API_KEY'] ?? '';
            $this->geoService = new GeoContextService($this->db, $apiKey);
        } else {
            $this->geoService = $geoService;
        }
    }

    /**
     * Processes a user's location claim against a specific Dashpoint.
     *
     * @param int|string  $userId       The ID of the user submitting the visit.
     * @param string      $dashpointId  The unique ID target Dashpoint.
     * @param float       $lat          The user's reported latitude.
     * @param float       $lon          The user's reported longitude.
     * @param bool        $isAttempt    Whether this is logged as a 0-point attempt.
     * @param string|null $notes        Optional narrative submitted by the user.
     * @param string|null $photosJson   Optional pre-compiled JSON string array of valid GCS image paths.
     *
     * @return array Associative array containing the JSON-ready API response.
     * @throws PDOException If the database connection fails.
     */
    public function processVisit($userId, string $dashpointId, float $lat, float $lon, bool $isAttempt = false, ?string $notes = null, ?string $photosJson = null): array
    {
        $userStmt = $this->db->prepare("SELECT is_verified FROM users WHERE id = :user_id LIMIT 1");
        $userStmt->execute([':user_id' => $userId]);
        $userCheck = $userStmt->fetch(PDO::FETCH_ASSOC);

        if (!$userCheck || $userCheck['is_verified'] == 0) {
            return ["status" => "error", "message" => "Account not verified. Please check your email to activate your account before logging Dashpoints."];
        }

        // 3. Proximity Calculation utilizing MySQL native ST_Distance_Sphere
        $wkt = "POINT($lat $lon)";

        $distStmt = $this->db->prepare("
            SELECT 
                ST_Distance_Sphere(d.location, ST_GeomFromText(:wkt, 4326)) AS distance_meters, 
                g.is_active,
                g.id AS game_id,
                ST_X(d.location) as dp_lat,
                ST_Y(d.location) as dp_lon,
                d.country_code,
                d.state_province,
                d.elevation
            FROM dashpoints d
            JOIN games g ON d.game_id = g.id
            WHERE d.id = :id 
            LIMIT 1
        ");
        $distStmt->execute([':wkt' => $wkt, ':id' => $dashpointId]);
        $result = $distStmt->fetch(PDO::FETCH_ASSOC);

        if (!$result) {
            return ["status" => "error", "message" => "Invalid Dashpoint ID."];
        }

        if (!$result['is_active']) {
            return ["status" => "error", "message" => "Target dashpoint belongs to an inactive game."];
        }

        $distance = (int) round($result['distance_meters']);
        $dpLat = (float) $result['dp_lat'];
        $dpLon = (float) $result['dp_lon'];
        $dpCountry = $result['country_code'] ?? '';
        $dpState = $result['state_province'] ?? '';
        $dpElevation = isset($result['elevation']) ? (float) $result['elevation'] : null;

        // Fetch and cache elevation if missing
        if ($dpElevation === null) {
            $fetchedElevation = $this->geoService->getElevation($dpLat, $dpLon);
            if ($fetchedElevation !== null) {
                $dpElevation = $fetchedElevation;
                $elevStmt = $this->db->prepare("UPDATE dashpoints SET elevation = :elev WHERE id = :id");
                $elevStmt->execute([':elev' => $dpElevation, ':id' => $dashpointId]);
            }
        }

        // 4. Enforce the classic 100-meter proximity rule (bypass if it's an attempt)
        if (!$isAttempt && $distance > 100) {
            return [
                "status" => "error",
                "message" => "Visit rejected. You must be within 100 meters to claim this point. Calculated distance: {$distance}m."
            ];
        }

        // 5. Verify Anti-Cheat: User hasn't already claimed a successful visit for this dashpoint
        $checkStmt = $this->db->prepare("SELECT id FROM visits WHERE user_id = :uid AND dashpoint_id = :dpid AND is_attempt = FALSE LIMIT 1");
        $checkStmt->execute([':uid' => $userId, ':dpid' => $dashpointId]);
        if (!$isAttempt && $checkStmt->fetch()) {
            return ["status" => "error", "message" => "You have already claimed this dashpoint."];
        }

        // 6. Historic Team Snapshot Mechanics
        $teamStmt = $this->db->prepare("SELECT team_id FROM team_members WHERE user_id = :uid LIMIT 1");
        $teamStmt->execute([':uid' => $userId]);
        $teamRow = $teamStmt->fetch(PDO::FETCH_ASSOC);
        $teamId = $teamRow ? $teamRow['team_id'] : null;

        // 7. Real-Time Scoring Assessment
        // Calculate the timezone offset based on the dashpoint's coordinates.
        $tzOffsetSeconds = $this->geoService->getTimezoneOffset($dpLat, $dpLon);

        // Do not count attempts when determining the sequence of claims.
        // We shift the database UTC timestamps by the local offset to determine the true "day" boundary.
        // We only count claims that occurred strictly before the current local day.
        $scoreCheckStmt = $this->db->prepare("
            SELECT COUNT(id) AS previous_claims 
            FROM visits 
            WHERE dashpoint_id = :dpid 
              AND is_attempt = FALSE 
              AND DATE(DATE_ADD(reported_time, INTERVAL {$tzOffsetSeconds} SECOND)) < DATE(DATE_ADD(CURRENT_TIMESTAMP, INTERVAL {$tzOffsetSeconds} SECOND))
        ");
        $scoreCheckStmt->execute([
            ':dpid' => $dashpointId
        ]);
        $previousClaims = (int) $scoreCheckStmt->fetch(PDO::FETCH_ASSOC)['previous_claims'];

        $scoreAwarded = 1; // Default minimum score for latecomers
        if ($isAttempt) {
            $scoreAwarded = 0;
        } elseif ($previousClaims === 0) {
            $scoreAwarded = 3; // First to secure the claim
        } elseif ($previousClaims === 1) {
            $scoreAwarded = 2; // Second to claim
        }

        $gameId = $result['game_id'] ?? null;

        // 8. Calculate total previous hunts for this user before the new insert
        $huntsStmt = $this->db->prepare("SELECT COUNT(id) AS previous_hunts FROM visits WHERE user_id = :uid");
        $huntsStmt->execute([':uid' => $userId]);
        $previousHuntsRow = $huntsStmt->fetch(PDO::FETCH_ASSOC);
        $previousHuntsAllGames = $previousHuntsRow ? (int) $previousHuntsRow['previous_hunts'] : 0;

        $huntsGameStmt = $this->db->prepare("
            SELECT COUNT(v.id) AS previous_hunts 
            FROM visits v 
            JOIN dashpoints d ON v.dashpoint_id = d.id 
            WHERE v.user_id = :uid AND d.game_id = :game_id
        ");
        $huntsGameStmt->execute([':uid' => $userId, ':game_id' => $gameId]);
        $previousHuntsGameRow = $huntsGameStmt->fetch(PDO::FETCH_ASSOC);
        $previousHuntsGame = $previousHuntsGameRow ? (int) $previousHuntsGameRow['previous_hunts'] : 0;

        // 9. Log the Visit and Secure the Calculated Score Automatically alongside bounded JSON image paths
        $insertStmt = $this->db->prepare("
            INSERT INTO visits (dashpoint_id, user_id, team_id, reported_location, distance_meters, score_awarded, is_attempt, notes, photos)
            VALUES (:dpid, :uid, :tid, ST_GeomFromText(:wkt, 4326), :dist, :score, :is_attempt, :notes, :photos)
        ");

        $insertStmt->execute([
            ':dpid' => $dashpointId,
            ':uid' => $userId,
            ':tid' => $teamId,
            ':wkt' => $wkt,
            ':dist' => $distance,
            ':score' => $scoreAwarded,
            ':is_attempt' => $isAttempt ? 1 : 0,
            ':notes' => $notes,
            ':photos' => $photosJson
        ]);

        $userStmt = $this->db->prepare("SELECT username FROM users WHERE id = :uid LIMIT 1");
        $userStmt->execute([':uid' => $userId]);
        $userRow = $userStmt->fetch(PDO::FETCH_ASSOC);
        $username = $userRow ? $userRow['username'] : 'Unknown User';

        $totalScoreStmt = $this->db->prepare("SELECT SUM(score_awarded) AS total FROM visits WHERE user_id = :uid");
        $totalScoreStmt->execute([':uid' => $userId]);
        $totalScoreRow = $totalScoreStmt->fetch(PDO::FETCH_ASSOC);
        $totalPointsAllGames = $totalScoreRow ? (int) $totalScoreRow['total'] : $scoreAwarded;

        $totalScoreGameStmt = $this->db->prepare("
            SELECT SUM(v.score_awarded) AS total 
            FROM visits v 
            JOIN dashpoints d ON v.dashpoint_id = d.id 
            WHERE v.user_id = :uid AND d.game_id = :game_id
        ");
        $totalScoreGameStmt->execute([':uid' => $userId, ':game_id' => $gameId]);
        $totalScoreGameRow = $totalScoreGameStmt->fetch(PDO::FETCH_ASSOC);
        $totalPointsGame = $totalScoreGameRow ? (int) $totalScoreGameRow['total'] : $scoreAwarded;

        $geoContext = $this->geoService->getDashpointContext($dpLat, $dpLon, $dashpointId);

        // Calculate extremes if valid province is set AND it was a successful claim (not an attempt)
        if (!$isAttempt && !empty($dpState) && !empty($dpCountry)) {
            $visitYear = (int) date('Y');
            $extremeAnnotations = $this->geoService->evaluateAndGetExtremeAnnotations($dashpointId, $dpLat, $dpLon, $dpElevation, $dpState, $dpCountry, $visitYear);
            if (!empty($extremeAnnotations)) {
                $geoContext .= $extremeAnnotations;
            }
        }

        $this->sendVisitReportEmail($username, $dashpointId, $distance, $scoreAwarded, $totalPointsAllGames, $totalPointsGame, $isAttempt, $notes, $photosJson, $previousHuntsAllGames, $previousHuntsGame, $geoContext);

        $action = $isAttempt ? "Attempt logged" : "Dashpoint successfully claimed";
        $pointsMessage = $isAttempt ? "This attempt earned 0 points." : "You earned {$scoreAwarded} points.";

        return [
            "status" => "success",
            "message" => "{$action}. {$pointsMessage}",
            "distance" => $distance,
            "points" => $scoreAwarded
        ];
    }
}
