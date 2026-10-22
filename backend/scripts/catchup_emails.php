<?php

/**
 * catchup_emails.php
 *
 * One-off script to manually dispatch HTML emails for Dashpoint visits
 * that were logged prior to the email notification feature.
 */

declare(strict_types=1);

require_once __DIR__ . '/../../vendor/autoload.php';
require_once __DIR__ . '/../Database.php';

use App\Database;
use App\Services\ProfileService;
use App\Services\ReportService;

try {
    $db = Database::getConnection();

    // IMPORTANT: Edit the WHERE clause below to isolate only the visits you want to send emails for.
    // For example: WHERE v.id IN (10, 11, 12) or WHERE v.reported_time > '2026-04-18 00:00:00'
    $stmt = $db->query("
        SELECT v.*, u.username, d.game_id
        FROM visits v
        JOIN users u ON v.user_id = u.id
        JOIN dashpoints d ON v.dashpoint_id = d.id
        -- WHERE v.id IN (...)
    ");

    $visits = $stmt->fetchAll();

    if (!$visits) {
        echo "No visits found matching your criteria.\n";
        exit;
    }

    echo "Found " . count($visits) . " visits. Preparing to send...\n";

    // Instantiate ReportService and ProfileService
    $profileService = new ProfileService($db);
    $reportService = new ReportService($db, null, $profileService);
    $reflection = new \ReflectionClass(ReportService::class);
    $method = $reflection->getMethod('sendVisitReportEmail');

    foreach ($visits as $visit) {
        $userId = (int) $visit['user_id'];

        $stats = $profileService->getPlayerMailStats(
            $userId,
            (int) $visit['game_id'],
            (string) $visit['reported_time']
        );
        $totalPointsAllGames = $stats['total_points_all_games'];
        $totalPointsGame = $stats['total_points_game'];
        $previousHuntsAllGames = $stats['previous_hunts_all_games'];
        $previousHuntsGame = $stats['previous_hunts_game'];

        echo "-> Sending email for dashpoint {$visit['dashpoint_id']} logged by {$visit['username']}...\n";

        // Invoke the private method securely
        $method->invoke(
            $reportService,
            $visit['username'],
            $visit['dashpoint_id'],
            (int) $visit['distance_meters'],
            (int) $visit['score_awarded'],
            $totalPointsAllGames,
            $totalPointsGame,
            (bool) $visit['is_attempt'], // 7th param: isAttempt
            $visit['notes'],             // 8th param: notes
            $visit['photos'],            // 9th param: photosJson
            $previousHuntsAllGames,      // 10th param: previousHuntsAllGames
            $previousHuntsGame           // 11th param: previousHuntsGame
        );
    }

    echo "Done catching up.\n";
} catch (Exception $e) {
    echo "Error: " . $e->getMessage() . "\n";
}
