<?php

declare(strict_types=1);

namespace App\Services;

use DOMDocument;
use InvalidArgumentException;

/**
 * ExportService
 *
 * Exposes a structured DOMDocument renderer formatting bounding box subsets
 * purely into GPS-compatible schema wrappers (.gpx, .loc).
 */
class ExportService
{
    /**
     * Generates an XML string in the specified format for the given dashpoints.
     *
     * @param array $points The array of dashpoints to format.
     * @param string $format The export format ('gpx' or 'loc').
     * @return string The generated XML string.
     * @throws InvalidArgumentException If the format is not supported.
     */
    public function generateXml(array $points, string $format): string
    {
        // Bootstrap the rigorous XML layout builder blocking syntax exploits internally
        $dom = new DOMDocument('1.0', 'UTF-8');
        $dom->formatOutput = true; // Maps clean indentation

        if ($format === 'gpx') {
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
            throw new InvalidArgumentException("Error: Unsupported document format structure securely rejected.");
        }

        return $dom->saveXML();
    }
}
