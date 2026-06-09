<?php

declare(strict_types=1);

namespace App\Services;

use PDO;
use Exception;

/**
 * Class EditService
 *
 * Encapsulates the core Field Note & Media Modification logic, isolating
 * structural dependencies for unit testing mocks.
 */
class EditService
{
    use MailerTrait;

    private PDO $db;
    private ?MediaService $mediaService;
    private ProfileService $profileService;

    /**
     * Constructor.
     *
     * @param PDO $db The PDO connection.
     * @param MediaService|null $mediaService The media service handler.
     * @param ProfileService|null $profileService The profile service helper.
     */
    public function __construct(PDO $db, ?MediaService $mediaService = null, ?ProfileService $profileService = null)
    {
        $this->db = $db;
        $this->mediaService = $mediaService;
        $this->profileService = $profileService ?? new ProfileService($this->db);
    }

    /**
     * Updates an existing visit record with new notes and conditionally managed photos.
     *
     * @param int $userId The authenticated user ID.
     * @param string $dashpointId The target dashpoint ID.
     * @param string $notes The new text narrative.
     * @param string $keptPhotosRaw JSON string array/objects of image URLs/captions to keep.
     * @param array|null $newFiles The new `$_FILES` structurally mapped image uploads.
     * @param bool $sendEmail Whether to dispatch list updates.
     * @param array $newCaptions Array of captions for newly uploaded images.
     * @return array Status array ready for JSON response encoding.
     */
    public function processEdit(int $userId, string $dashpointId, string $notes, string $keptPhotosRaw, ?array $newFiles = null, bool $sendEmail = true, array $newCaptions = []): array
    {
        $keptPhotos = json_decode($keptPhotosRaw, true);
        if (!is_array($keptPhotos)) {
            $keptPhotos = [];
        }

        // 1. Security Check: Verify visit existence and edit permissions
        $stmt = $this->db->prepare("
            SELECT v.id, v.photos, v.is_attempt, v.score_awarded, v.distance_meters, v.reported_time, ST_Latitude(v.reported_location) as dp_lat, ST_Longitude(v.reported_location) as dp_lon, g.is_active, g.id as game_id, u.username
            FROM visits v
            JOIN dashpoints d ON v.dashpoint_id = d.id
            JOIN games g ON d.game_id = g.id
            JOIN users u ON v.user_id = u.id
            WHERE v.user_id = :uid AND v.dashpoint_id = :dpid 
            LIMIT 1
        ");
        $stmt->execute([':uid' => $userId, ':dpid' => $dashpointId]);
        $visit = $stmt->fetch(PDO::FETCH_ASSOC);

        if (!$visit) {
            return ["status" => "error", "message" => "Modification rejected. You can only edit dashpoints you have visited.", "code" => 403];
        }

        if (!$visit['is_active']) {
            return ["status" => "error", "message" => "Modification rejected. Historical game logs cannot be edited.", "code" => 403];
        }

        $visitId = $visit['id'];
        $dbPhotos = json_decode($visit['photos'] ?? '[]', true);
        if (!is_array($dbPhotos)) {
            $dbPhotos = [];
        }

        // 2. GCP Media Synchronization (Diffing the DB against User Intent)
        $urlsToDelete = [];
        $finalPhotoObjects = [];

        foreach ($dbPhotos as $dbPhotoObj) {
            $urlStr = is_array($dbPhotoObj) ? ($dbPhotoObj['url'] ?? '') : $dbPhotoObj;

            $keptItem = null;
            foreach ($keptPhotos as $kPhoto) {
                $kUrl = is_array($kPhoto) ? ($kPhoto['url'] ?? '') : $kPhoto;
                if ($kUrl === $urlStr) {
                    $keptItem = $kPhoto;
                    break;
                }
            }

            if ($keptItem === null) {
                $urlsToDelete[] = $urlStr;
            } else {
                $caption = is_array($keptItem) ? ($keptItem['caption'] ?? null) : null;
                if (is_array($dbPhotoObj)) {
                    $updatedObj = $dbPhotoObj;
                    $updatedObj['caption'] = $caption !== null && trim($caption) !== '' ? trim($caption) : null;
                    $finalPhotoObjects[] = $updatedObj;
                } else {
                    $finalPhotoObjects[] = [
                        'url' => $urlStr,
                        'thumb_url' => $urlStr,
                        'lat' => null,
                        'lon' => null,
                        'caption' => $caption !== null && trim($caption) !== '' ? trim($caption) : null
                    ];
                }
            }
        }

        $hasNewUploads = (!empty($newFiles) && (is_array($newFiles['error']) ? $newFiles['error'][0] : $newFiles['error']) !== UPLOAD_ERR_NO_FILE);

        if ((count($urlsToDelete) > 0 || $hasNewUploads) && $this->mediaService === null) {
            return ["status" => "error", "message" => "Server configuration error blocking media processing.", "code" => 500];
        }

        // 3a. Delete GCP objects that were removed
        if (count($urlsToDelete) > 0 && $this->mediaService !== null) {
            try {
                $this->mediaService->deletePhotos($urlsToDelete);
            } catch (Exception $e) {
                error_log("GCP Physical Deletion Failure: " . $e->getMessage());
            }
        }

        // 3b. Upload new GCS objects
        if ($hasNewUploads && $this->mediaService !== null) {
            try {
                $newUploadObjects = $this->mediaService->uploadPhotos($newFiles, $dashpointId, $userId, $newCaptions);
                foreach ($newUploadObjects as $newObj) {
                    $finalPhotoObjects[] = $newObj;
                }
            } catch (Exception $e) {
                return ["status" => "error", "message" => "Image transfer failed: " . $e->getMessage(), "code" => 400];
            }
        }

        // 4. Structural constraint: 10 image maximum.
        if (count($finalPhotoObjects) > 10) {
            return ["status" => "error", "message" => "Modification rejected: Maximum of 10 media files allowed per visit.", "code" => 400];
        }

        $finalPhotosJson = count($finalPhotoObjects) > 0 ? json_encode($finalPhotoObjects) : null;

        // 5. Commit the structural modifications triggering the newly validated DATETIME `edited_at`
        $updateStmt = $this->db->prepare("
            UPDATE visits 
            SET notes = :notes, 
                photos = :photos, 
                edited_at = NOW() 
            WHERE id = :id
        ");

        $updateStmt->execute([
            ':notes' => $notes,
            ':photos' => $finalPhotosJson,
            ':id' => $visitId
        ]);

        if ($sendEmail) {
            $stats = $this->profileService->getPlayerMailStats($userId, (int)$visit['game_id'], $visit['reported_time']);
            $totalPointsAllGames = $stats['total_points_all_games'];
            $totalPointsGame = $stats['total_points_game'];
            $previousHuntsAllGames = $stats['previous_hunts_all_games'];
            $previousHuntsGame = $stats['previous_hunts_game'];

            $configPath = __DIR__ . '/../config.ini';
            $config = file_exists($configPath) ? parse_ini_file($configPath) : [];
            $apiKey = $config['GOOGLE_MAPS_API_KEY'] ?? '';
            $apiBaseUrl = $config['GOOGLE_MAPS_API_BASE_URL']
                ?? ((getenv('APP_ENV') === 'testing') ? 'http://127.0.0.1:8081/api/mock_maps.php?' : 'https://maps.googleapis.com');

            $geoContextService = new GeoContextService($this->db, $apiKey, $apiBaseUrl);
            $geoContext = $geoContextService->getDashpointContext((float)$visit['dp_lat'], (float)$visit['dp_lon'], $dashpointId);

            $this->sendVisitReportEmail($visit['username'], $dashpointId, (int)$visit['distance_meters'], (int)$visit['score_awarded'], $totalPointsAllGames, $totalPointsGame, (bool)$visit['is_attempt'], $notes, $finalPhotosJson, $previousHuntsAllGames, $previousHuntsGame, $geoContext, true);
        }

        return [
            "status" => "success",
            "message" => "Field notes successfully updated.",
            "data" => ["photos" => $finalPhotoObjects]
        ];
    }
}
