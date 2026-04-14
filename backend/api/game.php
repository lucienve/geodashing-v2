<?php

/**
 * Game State API Endpoint
 *
 * Lightweight public metric returning the current active monthly configuration
 * from the database, feeding the Javascript Dashboard Countdown Timer.
 */

header('Content-Type: application/json');

use App\Services\GameService;

if (basename(__FILE__) === basename($_SERVER['PHP_SELF'] ?? '')) {
    require_once __DIR__ . '/../../vendor/autoload.php';
    require_once __DIR__ . '/../Database.php';

    try {
        $db = \App\Database::getConnection();
        $gameService = new GameService($db);

        $game = $gameService->getActiveGame();

        if ($game) {
            echo json_encode([
                "status" => "success",
                "data" => $game
            ]);
        } else {
            http_response_code(404);
            echo json_encode(["status" => "error", "message" => "No active game found."]);
        }
    } catch (Exception $e) {
        error_log("Game API Error: " . $e->getMessage());
        http_response_code(500);
        echo json_encode(["status" => "error", "message" => "Database connection failed."]);
    }
}
