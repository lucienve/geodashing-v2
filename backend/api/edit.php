<?php
/**
 * Post-Log Editing API Endpoint
 *
 * Allows authenticated users to safely modify their Field Notes or append/delete 
 * physical tracking photos without triggering or modifying the 100m Geolocation 
 * bounds natively locked during the initial claim.
 *
 * @package Geodashing\API
 */

// Native Execution Gateway
if (basename(__FILE__) === basename($_SERVER['PHP_SELF'] ?? '')) {
    require_once __DIR__ . '/../session.php';
    header('Content-Type: application/json');
    require_once __DIR__ . '/../Database.php';

    // 1. Strict Authentication Boundary
    if (!isset($_SESSION['user_id'])) {
        http_response_code(401);
        echo json_encode(["status" => "error", "message" => "Unauthorized. Please log in first."]);
        exit;
    }

    if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
        http_response_code(405);
        echo json_encode(["status" => "error", "message" => "Method not allowed"]);
        exit;
    }

    // 2. Input Sanitization
    $dashpoint_id = $_POST['dashpoint_id'] ?? '';
    $notes = trim($_POST['notes'] ?? '');
    
    // `kept_photos` arrives as a strict JSON string array of public URLs the user explicitly chose NOT to click [X] on
    $keptPhotosRaw = $_POST['kept_photos'] ?? '[]';
    $keptPhotos = json_decode($keptPhotosRaw, true);
    if (!is_array($keptPhotos)) {
        $keptPhotos = [];
    }
    
    // Validate Log Narrative Boundaries
    if (empty($notes) || strlen($notes) > 10000) {
        http_response_code(400);
        echo json_encode(["status" => "error", "message" => "Field observations are mandatory and must not exceed 10,000 characters."]);
        exit;
    }

    if (empty($dashpoint_id)) {
        http_response_code(400);
        echo json_encode(["status" => "error", "message" => "Invalid target tracking configuration."]);
        exit;
    }

    try {
        $db = Database::getConnection();
        require_once __DIR__ . '/../services/MediaService.php';
        $keyPath = __DIR__ . '/../gcp-credentials.json';
        
        $mediaService = null;
        if (file_exists($keyPath)) {
            $mediaService = new MediaService('geodashing-v2', 'geodashing-v2-blobs', $keyPath);
        }

        $editService = new EditService($db, $mediaService);
        $result = $editService->processEdit($_SESSION['user_id'], $dashpoint_id, $notes, $keptPhotosRaw, $_FILES['photos'] ?? null);
        
        if ($result['status'] === 'success') {
            echo json_encode($result);
        } else {
            http_response_code(isset($result['code']) ? $result['code'] : 400);
            echo json_encode($result);
        }
    } catch (Exception $e) {
        error_log("Edit API Runtime Extinction: " . $e->getMessage());
        http_response_code(500);
        echo json_encode(["status" => "error", "message" => "Failed to restructure database schema internally."]);
    }
}

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
        if (!is_array($keptPhotos)) $keptPhotos = [];

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
            return ["status" => "error", "message" => "System fault: Modification rejected. You can exclusively edit Dashpoints you have physically captured!", "code" => 403];
        }

        if (!$visit['is_active']) {
            return ["status" => "error", "message" => "Modification rejected: Historical game logs are strictly immutable.", "code" => 403];
        }

        $visitId = $visit['id'];
        $dbPhotos = json_decode($visit['photos'] ?? '[]', true);
        if(!is_array($dbPhotos)) $dbPhotos = [];

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
            return ["status" => "error", "message" => "Server missing GCP Key mappings blocking Media processing.", "code" => 500];
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
                return ["status" => "error", "message" => "Physical Image Transfer Failed: " . $e->getMessage(), "code" => 400];
            }
        }

        // 4. Structural constraint: 10 image maximum.
        if (count($finalPhotoObjects) > 10) {
            return ["status" => "error", "message" => "Modification rejected: Maximum 10 physical media files permitted per spatial log.", "code" => 400];
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
            "message" => "Field Notes successfully modified physically syncing local arrays.",
            "data" => ["photos" => $finalPhotoObjects]
        ];
    }
}
