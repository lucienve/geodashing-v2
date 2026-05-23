<?php

/**
 * Game Summary Retrieval Endpoint
 *
 * Retrieves the HTML summary for a specific game ID.
 */

declare(strict_types=1);

use App\Services\SummaryService;

if (basename(__FILE__) === basename($_SERVER['PHP_SELF'] ?? '')) {
    require_once __DIR__ . '/../../vendor/autoload.php';
    require_once __DIR__ . '/../../backend/Database.php';
    header('Content-Type: application/json');

    $gameIdRaw = $_GET['game_id'] ?? null;
    $gameId = $gameIdRaw !== null ? (int) $gameIdRaw : null;

    if ($gameId === null || $gameId <= 0) {
        http_response_code(400);
        echo json_encode(["status" => "error", "message" => "Game ID is missing or invalid."]);
        exit;
    }

    try {
        $db = \App\Database::getConnection();
        $service = new SummaryService($db);
        $summary = $service->getSummary($gameId);

        if ($summary === null) {
            http_response_code(404);
            echo json_encode(["status" => "error", "message" => "Summary not found for the specified game."]);
            exit;
        }

        echo json_encode([
            "status" => "success",
            "summary" => $summary
        ]);
    } catch (Exception $e) {
        error_log("Summary API Error: " . $e->getMessage());
        http_response_code(500);
        echo json_encode(["status" => "error", "message" => "Database connection failed."]);
    }
}
