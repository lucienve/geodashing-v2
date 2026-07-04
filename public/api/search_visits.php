<?php

/**
 * Vector Visits Search API Endpoint
 *
 * Exposes a JSON array of visits/attempts for map rendering at high zoom levels.
 */

declare(strict_types=1);

header('Content-Type: application/json');

use App\Services\SearchService;

if (basename(__FILE__) === basename($_SERVER['PHP_SELF'] ?? '')) {
    require_once __DIR__ . '/../../vendor/autoload.php';
    require_once __DIR__ . '/../../backend/Database.php';

    $n = filter_var($_GET['n'] ?? '', FILTER_VALIDATE_FLOAT);
    $s = filter_var($_GET['s'] ?? '', FILTER_VALIDATE_FLOAT);
    $e = filter_var($_GET['e'] ?? '', FILTER_VALIDATE_FLOAT);
    $w = filter_var($_GET['w'] ?? '', FILTER_VALIDATE_FLOAT);
    $gameId = filter_var($_GET['game_id'] ?? null, FILTER_VALIDATE_INT);

    if ($n === false || $s === false || $e === false || $w === false) {
        http_response_code(400);
        echo json_encode(['status' => 'error', 'message' => 'Missing spatial bounds (n, s, e, w).']);
        exit;
    }

    if ($gameId === null || $gameId === false) {
        http_response_code(400);
        echo json_encode(['status' => 'error', 'message' => 'Missing game_id parameter.']);
        exit;
    }

    try {
        $db = \App\Database::getConnection();
        $service = new SearchService($db);

        $visits = $service->searchVisitsRegion($n, $s, $e, $w, $gameId);

        echo json_encode([
            "status" => "success",
            "count" => count($visits),
            "data" => $visits
        ]);
    } catch (Exception $e) {
        error_log("Search Visits API Error: " . $e->getMessage());
        http_response_code(500);
        echo json_encode(["status" => "error", "message" => "Error retrieving visits."]);
    }
}
