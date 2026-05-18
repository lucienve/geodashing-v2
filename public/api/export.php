<?php

/**
 * XML Waypoints Export Utility
 *
 * Exposes a structured DOMDocument renderer formatting bounding box subsets
 * purely into GPS-compatible schema wrappers (.gpx, .loc). Natively pushes HTTP
 * headers simulating file downloads on web browsers.
 */

declare(strict_types=1);

use App\Services\SearchService;
use App\Services\ExportService;

// If HTTP executes directly
if (basename(__FILE__) === basename($_SERVER['PHP_SELF'] ?? '')) {
    require_once __DIR__ . '/../../vendor/autoload.php';
    require_once __DIR__ . '/../../backend/session.php';
    require_once __DIR__ . '/../../backend/Database.php';

    // Securely demand a populated active session dynamically
    if (!isset($_SESSION['user_id'])) {
        http_response_code(401);
        exit('Error: Unauthorized. You must be logged in to export dashpoint data.');
    }

    // Parse the spatial layout natively
    $n = filter_var($_GET['n'] ?? '', FILTER_VALIDATE_FLOAT);
    $s = filter_var($_GET['s'] ?? '', FILTER_VALIDATE_FLOAT);
    $e = filter_var($_GET['e'] ?? '', FILTER_VALIDATE_FLOAT);
    $w = filter_var($_GET['w'] ?? '', FILTER_VALIDATE_FLOAT);

    // Parse the game_id constraint dynamically
    $gameId = filter_var($_GET['game_id'] ?? null, FILTER_VALIDATE_INT, FILTER_NULL_ON_FAILURE);

    // Default the payload syntax to GPX architectures dynamically
    $format = $_GET['format'] ?? 'gpx';

    if ($n === false || $s === false || $e === false || $w === false) {
        http_response_code(400);
        exit('Error: Invalid spatial boundaries completely disrupting parsing.');
    }

    try {
        $db = \App\Database::getConnection();
        $searchService = new SearchService($db);
        $points = $searchService->searchRegion($n, $s, $e, $w, $gameId);

        $exportService = new ExportService();
        $xmlOutput = $exportService->generateXml($points, $format);

        $filenameSuffix = $gameId !== null ? "_game_{$gameId}" : "";

        if ($format === 'gpx') {
            // Force strict caching overrides tricking browser into saving files natively
            header('Content-Type: application/gpx+xml');
            header("Content-Disposition: attachment; filename=\"geodashing_v2{$filenameSuffix}_export.gpx\"");
        } elseif ($format === 'loc') {
            // Geocaching legacy LOC formats
            header('Content-Type: application/xml');
            header("Content-Disposition: attachment; filename=\"geodashing_v2{$filenameSuffix}_export.loc\"");
        }

        // Output raw buffer bytes mapping HTTP stream correctly
        echo $xmlOutput;
    } catch (InvalidArgumentException $e) {
        http_response_code(400);
        exit($e->getMessage());
    } catch (Exception $e) {
        error_log("XML Export API Error: " . $e->getMessage());
        http_response_code(500);
        exit("Failed rendering XML layout globally.");
    }
}
