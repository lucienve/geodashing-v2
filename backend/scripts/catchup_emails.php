<?php

/**
 * catchup_emails.php
 *
 * One-off script to manually dispatch HTML emails for Dashpoint visits
 * that were logged prior to the email notification feature.
 */

require_once __DIR__ . '/../../vendor/autoload.php';
require_once __DIR__ . '/../Database.php';

use App\Database;
use App\Services\ReportService;

try {
    $db = Database::getConnection();

    // IMPORTANT: Edit the WHERE clause below to isolate only the visits you want to send emails for.
    // For example: WHERE v.id IN (10, 11, 12) or WHERE v.reported_time > '2026-04-18 00:00:00'
    $stmt = $db->query("
        SELECT v.*, u.username 
        FROM visits v 
        JOIN users u ON v.user_id = u.id
        -- WHERE v.id IN (...)
    ");

    $visits = $stmt->fetchAll();

    if (!$visits) {
        echo "No visits found matching your criteria.\n";
        exit;
    }

    echo "Found " . count($visits) . " visits. Preparing to send...\n";

    // Instantiate ReportService and use Reflection to unlock the private email method
    $reportService = new ReportService($db);
    $reflection = new \ReflectionClass(ReportService::class);
    $method = $reflection->getMethod('sendVisitReportEmail');
    $method->setAccessible(true);

    foreach ($visits as $visit) {
        $userId = $visit['user_id'];

        // Calculate the user's current total score
        $totalScoreStmt = $db->prepare("SELECT SUM(score_awarded) AS total FROM visits WHERE user_id = :uid");
        $totalScoreStmt->execute([':uid' => $userId]);
        $totalScoreRow = $totalScoreStmt->fetch();
        $totalPoints = $totalScoreRow ? (int) $totalScoreRow['total'] : (int)$visit['score_awarded'];

        echo "-> Sending email for dashpoint {$visit['dashpoint_id']} logged by {$visit['username']}...\n";

        // Invoke the private method securely
        $method->invoke(
            $reportService,
            $visit['username'],
            $visit['dashpoint_id'],
            (int)$visit['distance_meters'],
            (int)$visit['score_awarded'],
            $totalPoints,
            (bool)$visit['is_attempt'], // 6th param: isAttempt
            $visit['notes'],            // 7th param: notes
            $visit['photos']            // 8th param: photosJson
        );
    }

    echo "Done catching up!\n";
} catch (Exception $e) {
    echo "Error: " . $e->getMessage() . "\n";
}
