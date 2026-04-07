<?php
/**
 * Reporting API Endpoint
 *
 * Processes spatial dashpoint claims by evaluating the user's submitted physical
 * coordinates against the Dashpoint's master coordinates.
 *
 * @package Geodashing\API
 */

// If we are executing this file directly (not importing it for testing)
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
    // Validating against the frontend `name="lat"` and `name="lon"` constraints.
    $lat = filter_var($_POST['lat'] ?? '', FILTER_VALIDATE_FLOAT);
    $lon = filter_var($_POST['lon'] ?? '', FILTER_VALIDATE_FLOAT);
    $notes = trim($_POST['notes'] ?? '');

    // Phase 5 Validation: Strict Field Log Text Constraints
    if (empty($notes) || strlen($notes) > 10000) {
        http_response_code(400);
        echo json_encode(["status" => "error", "message" => "Field observations are mandatory and must not exceed 10,000 characters."]);
        exit;
    }
    $photosJson = null;

    // 2.5 Optional Media Processing Pipeline
    if (!empty($_FILES['photos']) && (is_array($_FILES['photos']['error']) ? $_FILES['photos']['error'][0] : $_FILES['photos']['error']) !== UPLOAD_ERR_NO_FILE) {
        require_once __DIR__ . '/../services/MediaService.php';

        $keyPath = __DIR__ . '/../gcp-credentials.json';
        if (!file_exists($keyPath)) {
            http_response_code(500);
            echo json_encode(["status" => "error", "message" => "Server missing GCP Key mappings blocking photo payload uploads."]);
            exit;
        }

        try {
            // Instantiate securely with user's explicitly provided Geodashing GCP identifiers
            $mediaService = new MediaService('geodashing-v2', 'geodashing-v2-blobs', $keyPath);
            $urls = $mediaService->uploadPhotos($_FILES['photos'], $dashpoint_id, $_SESSION['user_id']);
            if (!empty($urls)) {
                $photosJson = json_encode($urls);
            }
        } catch (Exception $e) {
            error_log("GCP Upload Error: " . $e->getMessage());
            http_response_code(400);
            echo json_encode(["status" => "error", "message" => "Image Upload Framework Failed: " . $e->getMessage()]);
            exit;
        }
    }

    if (empty($dashpoint_id) || $lat === false || $lon === false) {
        http_response_code(400);
        echo json_encode(["status" => "error", "message" => "Invalid or missing required spatial fields"]);
        exit;
    }

    try {
        $db = Database::getConnection();
        $service = new ReportService($db);
        $result = $service->processVisit($_SESSION['user_id'], $dashpoint_id, $lat, $lon, $notes, $photosJson);

        if ($result['status'] === 'error') {
            http_response_code(400);
        }
        echo json_encode($result);

    } catch (Exception $e) {
        error_log("Report API Error: " . $e->getMessage());
        http_response_code(500);
        echo json_encode(["status" => "error", "message" => "Failed to log visit due to internal server error."]);
    }
}

/**
 * Class ReportService
 *
 * Encapsulates the core business logic required to validate proximity
 * and persist Dashpoint visits, architected this way to allow for PHPUnit testing.
 */
class ReportService
{
    /**
     * @var PDO The configured database connection.
     */
    private PDO $db;

    /**
     * Constructor.
     *
     * @param PDO $db The PDO connection instance.
     */
    public function __construct(PDO $db)
    {
        $this->db = $db;
    }

    /**
     * Processes a user's location claim against a specific Dashpoint.
     *
     * @param int|string  $userId       The ID of the user submitting the visit.
     * @param string      $dashpointId  The unique ID target Dashpoint.
     * @param float       $lat          The user's reported latitude.
     * @param float       $lon          The user's reported longitude.
     * @param string|null $notes        Optional narrative submitted by the user.
     * @param string|null $photosJson   Optional pre-compiled JSON string array of valid GCS image paths.
     *
     * @return array Associative array containing the JSON-ready API response.
     * @throws PDOException If the database connection fails.
     */
    public function processVisit($userId, string $dashpointId, float $lat, float $lon, ?string $notes = null, ?string $photosJson = null): array
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
            SELECT ST_Distance_Sphere(d.location, ST_GeomFromText(:wkt, 4326)) AS distance_meters, g.is_active
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
            return ["status" => "error", "message" => "Target dashpoint belongs to an inactive game. Legacy claims are prohibited!"];
        }

        $distance = (int) round($result['distance_meters']);

        // 4. Enforce the classic 100-meter proximity rule
        if ($distance > 100) {
            return [
                "status" => "error",
                "message" => "Visit rejected. You must be physically within 100 meters to claim this point. Calculated distance: {$distance}m."
            ];
        }

        // 5. Verify Anti-Cheat: User hasn't already claimed this dashpoint
        $checkStmt = $this->db->prepare("SELECT id FROM visits WHERE user_id = :uid AND dashpoint_id = :dpid LIMIT 1");
        $checkStmt->execute([':uid' => $userId, ':dpid' => $dashpointId]);
        if ($checkStmt->fetch()) {
            return ["status" => "error", "message" => "You have already logged a visit for this dashpoint."];
        }

        // 6. Historic Team Snapshot Mechanics
        $teamStmt = $this->db->prepare("SELECT team_id FROM team_members WHERE user_id = :uid LIMIT 1");
        $teamStmt->execute([':uid' => $userId]);
        $teamRow = $teamStmt->fetch(PDO::FETCH_ASSOC);
        $teamId = $teamRow ? $teamRow['team_id'] : null;

        // 7. Real-Time Scoring Assessment
        $scoreCheckStmt = $this->db->prepare("SELECT COUNT(id) AS previous_claims FROM visits WHERE dashpoint_id = :dpid");
        $scoreCheckStmt->execute([':dpid' => $dashpointId]);
        $previousClaims = (int) $scoreCheckStmt->fetch(PDO::FETCH_ASSOC)['previous_claims'];

        $scoreAwarded = 1; // Default minimum score for latecomers
        if ($previousClaims === 0) {
            $scoreAwarded = 3; // First to physically network the claim
        } elseif ($previousClaims === 1) {
            $scoreAwarded = 2; // Second to claim
        }

        // 8. Log the Visit and Secure the Calculated Score Automatically alongside bounded JSON image paths
        $insertStmt = $this->db->prepare("
            INSERT INTO visits (dashpoint_id, user_id, team_id, reported_location, distance_meters, score_awarded, notes, photos)
            VALUES (:dpid, :uid, :tid, ST_GeomFromText(:wkt, 4326), :dist, :score, :notes, :photos)
        ");

        $insertStmt->execute([
            ':dpid' => $dashpointId,
            ':uid' => $userId,
            ':tid' => $teamId,
            ':wkt' => $wkt,
            ':dist' => $distance,
            ':score' => $scoreAwarded,
            ':notes' => $notes,
            ':photos' => $photosJson
        ]);

        return [
            "status" => "success",
            "message" => "Dashpoint successfully claimed! You earned {$scoreAwarded} points.",
            "distance" => $distance,
            "points" => $scoreAwarded
        ];
    }
}
