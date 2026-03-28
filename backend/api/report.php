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
    session_start();
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
    $lat = filter_var($_POST['latitude'] ?? '', FILTER_VALIDATE_FLOAT);
    $lon = filter_var($_POST['longitude'] ?? '', FILTER_VALIDATE_FLOAT);
    $notes = $_POST['notes'] ?? null;
    $visit_time = !empty($_POST['visit_time']) ? date('Y-m-d H:i:s', strtotime($_POST['visit_time'])) : date('Y-m-d H:i:s');

    if (empty($dashpoint_id) || $lat === false || $lon === false) {
        http_response_code(400);
        echo json_encode(["status" => "error", "message" => "Invalid or missing required spatial fields"]);
        exit;
    }

    try {
        $db = Database::getConnection();
        $service = new ReportService($db);
        $result = $service->processVisit($_SESSION['user_id'], $dashpoint_id, $lat, $lon, $visit_time, $notes);
        
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
     * @param string      $visitTime    The SQL-formatted DATETIME of the visit.
     * @param string|null $notes        Optional narrative submitted by the user.
     *
     * @return array Associative array containing the JSON-ready API response.
     * @throws PDOException If the database connection fails.
     */
    public function processVisit($userId, string $dashpointId, float $lat, float $lon, string $visitTime, ?string $notes = null): array
    {
        // 3. Proximity Calculation utilizing MySQL native ST_Distance_Sphere
        $wkt = "POINT($lat $lon)";
        
        $distStmt = $this->db->prepare("
            SELECT ST_Distance_Sphere(location, ST_GeomFromText(:wkt, 4326)) AS distance_meters
            FROM dashpoints 
            WHERE id = :id 
            LIMIT 1
        ");
        $distStmt->execute([':wkt' => $wkt, ':id' => $dashpointId]);
        $result = $distStmt->fetch(PDO::FETCH_ASSOC);
        
        if (!$result) {
            return ["status" => "error", "message" => "Invalid Dashpoint ID."];
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
        
        // 7. Insert the valid visit cleanly into MySQL Spatial tracking
        $insertStmt = $this->db->prepare("
            INSERT INTO visits (dashpoint_id, user_id, team_id, reported_location, distance_meters, visit_time, notes)
            VALUES (:dpid, :uid, :tid, ST_GeomFromText(:wkt, 4326), :dist, :vtime, :notes)
        ");
        
        $insertStmt->execute([
            ':dpid' => $dashpointId,
            ':uid' => $userId,
            ':tid' => $teamId,
            ':wkt' => $wkt,
            ':dist' => $distance,
            ':vtime' => $visitTime,
            ':notes' => $notes
        ]);
        
        return [
            "status" => "success", 
            "message" => "Dashpoint successfully claimed!",
            "distance" => $distance
        ];
    }
}
