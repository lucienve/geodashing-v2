<?php
require_once __DIR__ . '/../../vendor/autoload.php';
require_once __DIR__ . '/../Database.php';

use App\Database;
use App\Services\ReportService;

try {
    $db = Database::getConnection();
    
    // Fetch all visits
    $stmt = $db->query("
        SELECT v.*, u.username 
        FROM visits v 
        JOIN users u ON v.user_id = u.id
    ");
    $visits = $stmt->fetchAll();

    if (!$visits) {
        echo "No visits found.\n";
        exit;
    }

    $reportService = new ReportService($db);
    $reflection = new \ReflectionClass(ReportService::class);
    $method = $reflection->getMethod('sendVisitReportEmail');
    $method->setAccessible(true);

    foreach ($visits as $visit) {
        $userId = $visit['user_id'];
        
        // Fetch total points for the user up to this point, or just their current total
        // Since it's a catchup, their total points right now is fine, or we could calculate it exactly
        $totalScoreStmt = $db->prepare("SELECT SUM(score_awarded) AS total FROM visits WHERE user_id = :uid");
        $totalScoreStmt->execute([':uid' => $userId]);
        $totalScoreRow = $totalScoreStmt->fetch();
        $totalPoints = $totalScoreRow ? (int) $totalScoreRow['total'] : (int)$visit['score_awarded'];

        echo "Sending email for dashpoint {$visit['dashpoint_id']} logged by {$visit['username']}...\n";
        
        $method->invoke(
            $reportService, 
            $visit['username'], 
            $visit['dashpoint_id'], 
            (int)$visit['distance_meters'], 
            (int)$visit['score_awarded'], 
            $totalPoints, 
            $visit['notes'], 
            $visit['photos']
        );
    }
    
    echo "Done catching up!\n";

} catch (Exception $e) {
    echo "Error: " . $e->getMessage() . "\n";
}
