<?php
/**
 * Game State API Endpoint
 *
 * Lightweight public metric returning the current active monthly configuration 
 * from the database, feeding the Javascript Dashboard Countdown Timer.
 */

header('Content-Type: application/json');

require_once __DIR__ . '/../Database.php';

try {
    $db = Database::getConnection();
    
    // We strictly pull the singular active game month
    $stmt = $db->prepare("SELECT id, start_time, end_time FROM games WHERE is_active = TRUE ORDER BY id DESC LIMIT 1");
    $stmt->execute();
    $game = $stmt->fetch(PDO::FETCH_ASSOC);

    if ($game) {
        echo json_encode([
            "status" => "success",
            "data" => [
                "game_id" => (int)$game['id'],
                "start_time" => $game['start_time'],
                "end_time" => $game['end_time']
            ]
        ]);
    } else {
        http_response_code(404);
        echo json_encode(["status" => "error", "message" => "No active game matrix found locally."]);
    }

} catch (Exception $e) {
    error_log("Game API RUPTURE: " . $e->getMessage());
    http_response_code(500);
    echo json_encode(["status" => "error", "message" => "Database link severed completely."]);
}
