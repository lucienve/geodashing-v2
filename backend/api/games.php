<?php
/**
 * Games API Endpoint
 *
 * Retrieves the full list of historical and active games.
 */

header('Content-Type: application/json');

require_once __DIR__ . '/../Database.php';

try {
    $db = Database::getConnection();
    
    $stmt = $db->query("SELECT id, title, start_time, end_time, is_active FROM games ORDER BY id DESC");
    $games = $stmt->fetchAll(PDO::FETCH_ASSOC);

    echo json_encode([
        "status" => "success",
        "data" => $games
    ]);

} catch (Exception $e) {
    error_log("Games API Error: " . $e->getMessage());
    http_response_code(500);
    echo json_encode(["status" => "error", "message" => "Database connection failed."]);
}
