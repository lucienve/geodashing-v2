<?php

namespace App\Services;

use PDO;
use Exception;

/**
 * Encapsulates the core Field Note & Media Modification logic physically isolating
 * structural dependencies for unit testing mocks.
 */
class EditService
{
    private PDO $db;
    private ?MediaService $mediaService;

    public function __construct(PDO $db, ?MediaService $mediaService = null)
    {
        $this->db = $db;
        $this->mediaService = $mediaService;
    }

    public function processEdit(int $userId, string $dashpointId, string $notes, string $keptPhotosRaw, ?array $newFiles = null): array
    {
        $keptPhotos = json_decode($keptPhotosRaw, true);
        if (!is_array($keptPhotos)) {
            $keptPhotos = [];
        }

        // 1. Security Check: Assert Structural Database Ownership natively
        $stmt = $this->db->prepare("
            SELECT v.id, v.photos, g.is_active 
            FROM visits v
            JOIN dashpoints d ON v.dashpoint_id = d.id
            JOIN games g ON d.game_id = g.id
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
            if (!in_array($urlStr, $keptPhotos, true)) {
                $urlsToDelete[] = $urlStr;
            } else {
                $finalPhotoObjects[] = $dbPhotoObj; // Safely retain the structurally mapped metadata
            }
        }

        $hasNewUploads = (!empty($newFiles) && (is_array($newFiles['error']) ? $newFiles['error'][0] : $newFiles['error']) !== UPLOAD_ERR_NO_FILE);

        if ((count($urlsToDelete) > 0 || $hasNewUploads) && $this->mediaService === null) {
            return ["status" => "error", "message" => "Server configuration error blocking media processing.", "code" => 500];
        }

        // 3a. Execute Physical GCP Blob Destruction natively
        if (count($urlsToDelete) > 0 && $this->mediaService !== null) {
            try {
                $this->mediaService->deletePhotos($urlsToDelete);
            } catch (Exception $e) {
                error_log("GCP Physical Deletion Failure: " . $e->getMessage());
            }
        }

        // 3b. Execute New GCS Binary Pipeline processing
        if ($hasNewUploads && $this->mediaService !== null) {
            try {
                $newUploadObjects = $this->mediaService->uploadPhotos($newFiles, $dashpointId, $userId);
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

        return [
            "status" => "success",
            "message" => "Field notes successfully updated.",
            "data" => ["photos" => $finalPhotoObjects]
        ];
    }
}
