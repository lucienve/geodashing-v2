<?php
/**
 * Vector Search API Endpoint
 *
 * Exposes a generic JSON array mapper for frontend map rendering blocks,
 * parsing bounding box filters natively preventing rendering overload on mobile.
 */

header('Content-Type: application/json');

// If HTTP executes directly (no require)
if (basename(__FILE__) === basename($_SERVER['PHP_SELF'] ?? '')) {
    require_once __DIR__ . '/../Database.php';
    require_once __DIR__ . '/../services/SearchService.php';

    // Extract boundaries dynamically mapped from the frontend Map viewport bounds
    // Examples: n = 43.12, s = 42.10, e = -70.30, w = -71.50
    $n = filter_var($_GET['n'] ?? '', FILTER_VALIDATE_FLOAT);
    $s = filter_var($_GET['s'] ?? '', FILTER_VALIDATE_FLOAT);
    $e = filter_var($_GET['e'] ?? '', FILTER_VALIDATE_FLOAT);
    $w = filter_var($_GET['w'] ?? '', FILTER_VALIDATE_FLOAT);
    $gameId = filter_var($_GET['game_id'] ?? null, FILTER_VALIDATE_INT);

    // Fail out safely preventing undefined spatial mapping indexes
    if ($n === false || $s === false || $e === false || $w === false) {
        http_response_code(400);
        echo json_encode(['status' => 'error', 'message' => 'Missing strictly formatted spatial bounds (n, s, e, w).']);
        exit;
    }

    try {
        $db = Database::getConnection();
        $service = new SearchService($db);
        
        // Ping MySQL for the cached bounding box mapping securely
        $points = $service->searchRegion($n, $s, $e, $w, $gameId ? $gameId : null);

        // JSON block out mapped back to browser for Leaflet/Google Maps parsing natively
        echo json_encode([
            "status" => "success", 
            "count" => count($points), 
            "data" => $points
        ]);
        
    } catch (Exception $e) {
        error_log("Search API Crash: " . $e->getMessage());
        http_response_code(500);
        echo json_encode(["status" => "error", "message" => "SQL Mapping error retrieving vectors."]);
    }
}
