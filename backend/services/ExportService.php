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

                $idSafe = htmlspecialchars($pt['id']);

                $name = $dom->createElement('name', $idSafe);
                $wpt->appendChild($name);

                $desc = $dom->createElement('desc', 'Dashpoint ' . $idSafe);
                $wpt->appendChild($desc);

                $link = $dom->createElement('link');
                $link->setAttribute('href', 'https://www.geodashing.org/#dashpoint?id=' . $idSafe);
                $linkText = $dom->createElement('text', 'View on Geodashing');
                $link->appendChild($linkText);
                $wpt->appendChild($link);

                $sym = $dom->createElement('sym', 'Waypoint');
                $wpt->appendChild($sym);

                $type = $dom->createElement('type', 'Dashpoint');
                $wpt->appendChild($type);

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
                $idSafe = htmlspecialchars($pt['id']);

                $name = $dom->createElement('name', $idSafe);
                $name->setAttribute('id', $idSafe);
                $waypoint->appendChild($name);

                $coord = $dom->createElement('coord');
                $coord->setAttribute('lat', (string)$pt['lat']);
                $coord->setAttribute('lon', (string)$pt['lon']);
                $waypoint->appendChild($coord);

                $type = $dom->createElement('type', 'Dashpoint');
                $waypoint->appendChild($type);

                $link = $dom->createElement('link', 'https://www.geodashing.org/#dashpoint?id=' . $idSafe);
                $link->setAttribute('text', 'View on Geodashing');
                $waypoint->appendChild($link);

                $loc->appendChild($waypoint);
            }
        } elseif ($format === 'kml') {
            // Keyhole Markup Language (KML) 2.2 standard format
            $kml = $dom->createElement('kml');
            $kml->setAttribute('xmlns', 'http://www.opengis.net/kml/2.2');
            $dom->appendChild($kml);

            $document = $dom->createElement('Document');
            $kml->appendChild($document);

            $docName = $dom->createElement('name', 'Geodashing V2 Dashpoints');
            $document->appendChild($docName);

            $docDesc = $dom->createElement('desc', 'Exported Dashpoints from Geodashing V2');
            $document->appendChild($docDesc);

            foreach ($points as $pt) {
                $placemark = $dom->createElement('Placemark');
                $idSafe = htmlspecialchars($pt['id']);

                $name = $dom->createElement('name', $idSafe);
                $placemark->appendChild($name);

                // Build CDATA description
                $descContent = "Dashpoint: {$idSafe}<br><a href=\"https://www.geodashing.org/#dashpoint?id={$idSafe}\">View on Geodashing</a>";
                $cdata = $dom->createCDATASection($descContent);
                $desc = $dom->createElement('description');
                $desc->appendChild($cdata);
                $placemark->appendChild($desc);

                $point = $dom->createElement('Point');

                // Set altitudeMode to clampToGround to ensure pins clamp to terrain surface
                $altMode = $dom->createElement('altitudeMode', 'clampToGround');
                $point->appendChild($altMode);

                // KML coordinates format: longitude,latitude,altitude (no spaces)
                $coordsText = (string)$pt['lon'] . ',' . (string)$pt['lat'] . ',0';
                $coordinates = $dom->createElement('coordinates', $coordsText);
                $point->appendChild($coordinates);

                $placemark->appendChild($point);
                $document->appendChild($placemark);
            }
        } else {
            throw new InvalidArgumentException("Error: Unsupported document format structure securely rejected.");
        }

        return $dom->saveXML();
    }
}
