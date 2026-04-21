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

// If HTTP executes directly
if (basename(__FILE__) === basename($_SERVER['PHP_SELF'] ?? '')) {
    require_once __DIR__ . '/../../vendor/autoload.php';
    require_once __DIR__ . '/../../backend/Database.php';

    // Parse the spatial layout natively
    $n = filter_var($_GET['n'] ?? '', FILTER_VALIDATE_FLOAT);
    $s = filter_var($_GET['s'] ?? '', FILTER_VALIDATE_FLOAT);
    $e = filter_var($_GET['e'] ?? '', FILTER_VALIDATE_FLOAT);
    $w = filter_var($_GET['w'] ?? '', FILTER_VALIDATE_FLOAT);

    // Default the payload syntax to GPX architectures dynamically
    $format = $_GET['format'] ?? 'gpx';

    if ($n === false || $s === false || $e === false || $w === false) {
        http_response_code(400);
        exit('Error: Invalid spatial boundaries completely disrupting parsing.');
    }

    try {
        $db = \App\Database::getConnection();
        $service = new SearchService($db);
        $points = $service->searchRegion($n, $s, $e, $w);

        // Bootstrap the rigorous XML layout builder blocking syntax exploits internally
        $dom = new DOMDocument('1.0', 'UTF-8');
        $dom->formatOutput = true; // Maps clean indentation

        if ($format === 'gpx') {
            // Force strict caching overrides tricking browser into saving files natively
            header('Content-Type: application/gpx+xml');
            header('Content-Disposition: attachment; filename="geodashing_v2_export.gpx"');

            $gpx = $dom->createElement('gpx');
            $gpx->setAttribute('version', '1.1');
            $gpx->setAttribute('creator', 'Geodashing V2 API Engine');
            $gpx->setAttribute('xmlns', 'http://www.topografix.com/GPX/1/1');
            $dom->appendChild($gpx);

            foreach ($points as $pt) {
                // Strict WP bounds
                $wpt = $dom->createElement('wpt');
                $wpt->setAttribute('lat', (string)$pt['lat']);
                $wpt->setAttribute('lon', (string)$pt['lon']);

                $name = $dom->createElement('name', htmlspecialchars($pt['id']));
                $wpt->appendChild($name);

                $gpx->appendChild($wpt);
            }
        } elseif ($format === 'loc') {
            // Geocaching legacy LOC formats
            header('Content-Type: application/xml');
            header('Content-Disposition: attachment; filename="geodashing_v2_export.loc"');

            $loc = $dom->createElement('loc');
            $loc->setAttribute('version', '1.0');
            $loc->setAttribute('src', 'Geodashing V2 System');
            $dom->appendChild($loc);

            foreach ($points as $pt) {
                $waypoint = $dom->createElement('waypoint');

                $name = $dom->createElement('name');
                $name->setAttribute('id', htmlspecialchars($pt['id']));
                $waypoint->appendChild($name);

                $coord = $dom->createElement('coord');
                $coord->setAttribute('lat', (string)$pt['lat']);
                $coord->setAttribute('lon', (string)$pt['lon']);
                $waypoint->appendChild($coord);

                $loc->appendChild($waypoint);
            }
        } else {
            http_response_code(400);
            exit("Error: Unsupported document format structure securely rejected.");
        }

        // Output raw buffer bytes mapping HTTP stream correctly
        echo $dom->saveXML();
    } catch (Exception $e) {
        error_log("XML Export API Error: " . $e->getMessage());
        http_response_code(500);
        exit("Failed rendering XML layout globally.");
    }
}
