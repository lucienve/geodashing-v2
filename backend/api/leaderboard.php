<?php
/**
 * Leaderboards API Endpoint
 *
 * Provides high-speed JSON dumps containing the pre-aggregated Player Ranks
 * organized by total points and temporal tie-breakers.
 */

header('Content-Type: application/json');

if (basename(__FILE__) === basename($_SERVER['PHP_SELF'] ?? '')) {
    require_once __DIR__ . '/../Database.php';
    require_once __DIR__ . '/../services/LeaderboardService.php';

    try {
        $db = Database::getConnection();

        // 1. Identify the logical Game Loop constraints
        $gameId = filter_var($_GET['game_id'] ?? null, FILTER_VALIDATE_INT);

        if (!$gameId) {
            // Natively default to the currently "Active" game mapping dynamically
            $stmt = $db->query("SELECT id FROM games WHERE is_active = TRUE LIMIT 1");
            $game = $stmt->fetch(PDO::FETCH_ASSOC);
            if (!$game) {
                http_response_code(404);
                echo json_encode(["status" => "error", "message" => "Critical Error: Engine failed to identify an active Game State!"]);
                exit;
            }
            $gameId = (int)$game['id'];
        }

        // 2. Instantiate the Mathematical Aggregator Engine natively
        $leaderboardService = new LeaderboardService($db);
        
        // 3. Extract the clean arrays strictly isolating Solo logic bounds
        $ranks = $leaderboardService->getSoloRankings($gameId, 100);

        echo json_encode([
            "status" => "success",
            "game_id" => $gameId,
            "data" => $ranks
        ]);

    } catch (Exception $e) {
        error_log("Leaderboard Engine Panic: " . $e->getMessage());
        http_response_code(500);
        echo json_encode(["status" => "error", "message" => "SQL Aggregate failure."]);
    }
}
