<?php
/**
 * Profile API Endpoint
 *
 * Retrieves historical metrics for a specific user.
 */

header('Content-Type: application/json');

require_once __DIR__ . '/../Database.php';

$userId = filter_var($_GET['id'] ?? null, FILTER_VALIDATE_INT);

if (!$userId) {
    http_response_code(400);
    echo json_encode(["status" => "error", "message" => "Valid User ID required."]);
    exit;
}

try {
    $db = Database::getConnection();

    // 1. Get User Core Details
    $stmtUser = $db->prepare("SELECT id, username, created_at FROM users WHERE id = :id");
    $stmtUser->execute([':id' => $userId]);
    $user = $stmtUser->fetch(PDO::FETCH_ASSOC);

    if (!$user) {
        http_response_code(404);
        echo json_encode(["status" => "error", "message" => "User not found."]);
        exit;
    }

    // 2. Fetch Historical Logs and Scores joining Games and Dashpoints
    $query = "
        SELECT 
            v.id AS visit_id,
            v.score_awarded,
            v.reported_time,
            v.distance_meters,
            d.id AS dashpoint_id,
            g.id AS game_id,
            g.title AS game_title,
            g.is_active AS game_is_active
        FROM visits v
        JOIN dashpoints d ON v.dashpoint_id = d.id
        JOIN games g ON d.game_id = g.id
        WHERE v.user_id = :user_id AND v.status = 'approved'
        ORDER BY g.id DESC, v.reported_time DESC
    ";
    
    $stmtLogs = $db->prepare($query);
    $stmtLogs->execute([':user_id' => $userId]);
    $logs = $stmtLogs->fetchAll(PDO::FETCH_ASSOC);

    // 3. Aggregate Data natively mapping by Game ID
    $totalScore = 0;
    $gamesHistory = [];

    foreach ($logs as $log) {
        $totalScore += (int)$log['score_awarded'];
        $gId = $log['game_id'];

        if (!isset($gamesHistory[$gId])) {
            $gamesHistory[$gId] = [
                'game_id' => $gId,
                'title' => $log['game_title'],
                'is_active' => (bool)$log['game_is_active'],
                'game_total_score' => 0,
                'visits' => []
            ];
        }

        $gamesHistory[$gId]['game_total_score'] += (int)$log['score_awarded'];
        $gamesHistory[$gId]['visits'][] = [
            'visit_id' => $log['visit_id'],
            'dashpoint_id' => $log['dashpoint_id'],
            'score_awarded' => (int)$log['score_awarded'],
            'distance_meters' => (int)$log['distance_meters'],
            'reported_time' => $log['reported_time']
        ];
    }

    echo json_encode([
        "status" => "success",
        "data" => [
            "user" => [
                "id" => $user['id'],
                "username" => $user['username'],
                "created_at" => $user['created_at'],
                "lifetime_score" => $totalScore
            ],
            "games" => array_values($gamesHistory) // Re-index array perfectly for JSON structures
        ]
    ]);

} catch (Exception $e) {
    error_log("Profile API Error: " . $e->getMessage());
    http_response_code(500);
    echo json_encode(["status" => "error", "message" => "Database connection failed."]);
}
