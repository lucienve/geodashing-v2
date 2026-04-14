<?php

/**
 * Games API Endpoint
 *
 * Retrieves the full list of historical and active games.
 */

header('Content-Type: application/json');

use App\Services\GameService;

if (basename(__FILE__) === basename($_SERVER['PHP_SELF'] ?? '')) {
    require_once __DIR__ . '/../../vendor/autoload.php';
    require_once __DIR__ . '/../Database.php';

    try {
        $db = \App\Database::getConnection();
        $gameService = new GameService($db);

        $games = $gameService->getAllGames();

        echo json_encode([
            "status" => "success",
            "data" => $games
        ]);
    } catch (Exception $e) {
        error_log("Games API Error: " . $e->getMessage());
        http_response_code(500);
        echo json_encode(["status" => "error", "message" => "Database connection failed."]);
    }
}
