<?php

declare(strict_types=1);

namespace App\Tests;

use PHPUnit\Framework\TestCase;
use PHPUnit\Framework\Attributes\Test;
use PHPUnit\Framework\Attributes\CoversClass;
use App\Services\ExportService;
use InvalidArgumentException;

/**
 * ExportServiceTest
 *
 * Verifies that the XML DOM rendering securely correctly formats GPX and LOC
 * string outputs based on input arrays, ensuring syntax remains well-formed.
 */
#[CoversClass(ExportService::class)]
class ExportServiceTest extends TestCase
{
    private ExportService $exportService;

    protected function setUp(): void
    {
        $this->exportService = new ExportService();
    }

    /**
     * Verifies that the service correctly generates a GPX XML structure
     * for a valid array of dashpoints.
     */
    #[Test]
    public function processesGpxFormatCorrectlyWithDashpoints()
    {
        $points = [
            ['id' => 'GD001-AAAA', 'lat' => 45.0, 'lon' => -70.0],
            ['id' => 'GD001-BBBB', 'lat' => 46.0, 'lon' => -71.0],
        ];

        $xml = $this->exportService->generateXml($points, 'gpx');

        $this->assertStringContainsString('<?xml version="1.0" encoding="UTF-8"?>', $xml);
        $this->assertStringContainsString('<gpx', $xml);
        $this->assertStringContainsString('version="1.1"', $xml);
        $this->assertStringContainsString('creator="Geodashing V2 API Engine"', $xml);
        $this->assertStringContainsString('xmlns="http://www.topografix.com/GPX/1/1"', $xml);

        // Assert first point
        $this->assertStringContainsString('<wpt lat="45" lon="-70">', $xml);
        $this->assertStringContainsString('<name>GD001-AAAA</name>', $xml);
        $this->assertStringContainsString('<desc>Dashpoint GD001-AAAA</desc>', $xml);
        $this->assertStringContainsString('<sym>Waypoint</sym>', $xml);
        $this->assertStringContainsString('<type>Dashpoint</type>', $xml);
        $this->assertStringContainsString('<link href="https://www.geodashing.org/#dashpoint?id=GD001-AAAA">', $xml);
        $this->assertStringContainsString('<text>View on Geodashing</text>', $xml);

        // Assert second point
        $this->assertStringContainsString('<wpt lat="46" lon="-71">', $xml);
        $this->assertStringContainsString('<name>GD001-BBBB</name>', $xml);
        $this->assertStringContainsString('<desc>Dashpoint GD001-BBBB</desc>', $xml);
        $this->assertStringContainsString('<sym>Waypoint</sym>', $xml);
        $this->assertStringContainsString('<type>Dashpoint</type>', $xml);
        $this->assertStringContainsString('<link href="https://www.geodashing.org/#dashpoint?id=GD001-BBBB">', $xml);
        $this->assertStringContainsString('<text>View on Geodashing</text>', $xml);

        $this->assertStringContainsString('</gpx>', $xml);
    }

    /**
     * Verifies that the service correctly generates an empty GPX XML structure
     * when no dashpoints are provided.
     */
    #[Test]
    public function processesGpxFormatCorrectlyWithNoDashpoints()
    {
        $points = [];

        $xml = $this->exportService->generateXml($points, 'gpx');

        $this->assertStringContainsString('<?xml version="1.0" encoding="UTF-8"?>', $xml);
        $this->assertStringContainsString('<gpx', $xml);
        $this->assertStringContainsString('version="1.1"', $xml);
        $this->assertStringContainsString('creator="Geodashing V2 API Engine"', $xml);
        $this->assertStringContainsString('xmlns="http://www.topografix.com/GPX/1/1"', $xml);
        $this->assertStringContainsString('/>', $xml);
        $this->assertStringNotContainsString('<wpt', $xml);
    }

    /**
     * Verifies that the service correctly generates a LOC XML structure
     * for a valid array of dashpoints.
     */
    #[Test]
    public function processesLocFormatCorrectlyWithDashpoints()
    {
        $points = [
            ['id' => 'GD001-AAAA', 'lat' => 45.0, 'lon' => -70.0]
        ];

        $xml = $this->exportService->generateXml($points, 'loc');

        $this->assertStringContainsString('<?xml version="1.0" encoding="UTF-8"?>', $xml);
        $this->assertStringContainsString('<loc version="1.0" src="Geodashing V2 System">', $xml);

        // Assert point
        $this->assertStringContainsString('<waypoint>', $xml);
        $this->assertStringContainsString('<name id="GD001-AAAA">GD001-AAAA</name>', $xml);
        $this->assertStringContainsString('<coord lat="45" lon="-70"/>', $xml);
        $this->assertStringContainsString('<type>Dashpoint</type>', $xml);
        $this->assertStringContainsString('<link text="View on Geodashing">https://www.geodashing.org/#dashpoint?id=GD001-AAAA</link>', $xml);

        $this->assertStringContainsString('</loc>', $xml);
    }

    /**
     * Verifies that the service correctly generates an empty LOC XML structure
     * when no dashpoints are provided.
     */
    #[Test]
    public function processesLocFormatCorrectlyWithNoDashpoints()
    {
        $points = [];

        $xml = $this->exportService->generateXml($points, 'loc');

        $this->assertStringContainsString('<?xml version="1.0" encoding="UTF-8"?>', $xml);
        $this->assertStringContainsString('<loc version="1.0" src="Geodashing V2 System"/>', $xml);
        $this->assertStringNotContainsString('<waypoint>', $xml);
    }

    /**
     * Verifies that the service correctly generates a KML XML structure
     * for a valid array of dashpoints.
     */
    #[Test]
    public function processesKmlFormatCorrectlyWithDashpoints()
    {
        $points = [
            ['id' => 'GD001-AAAA', 'lat' => 45.0, 'lon' => -70.0],
            ['id' => 'GD001-BBBB', 'lat' => 46.0, 'lon' => -71.0],
        ];

        $xml = $this->exportService->generateXml($points, 'kml');

        $this->assertStringContainsString('<?xml version="1.0" encoding="UTF-8"?>', $xml);
        $this->assertStringContainsString('<kml xmlns="http://www.opengis.net/kml/2.2">', $xml);
        $this->assertStringContainsString('<Document>', $xml);

        // Assert first point
        $this->assertStringContainsString('<Placemark>', $xml);
        $this->assertStringContainsString('<name>GD001-AAAA</name>', $xml);
        $this->assertStringContainsString('<description><![CDATA[Dashpoint: GD001-AAAA<br><a href="https://www.geodashing.org/#dashpoint?id=GD001-AAAA">View on Geodashing</a>]]></description>', $xml);
        $this->assertStringContainsString('<Point>', $xml);
        $this->assertStringContainsString('<altitudeMode>clampToGround</altitudeMode>', $xml);
        $this->assertStringContainsString('<coordinates>-70,45,0</coordinates>', $xml);

        // Assert second point
        $this->assertStringContainsString('<name>GD001-BBBB</name>', $xml);
        $this->assertStringContainsString('<description><![CDATA[Dashpoint: GD001-BBBB<br><a href="https://www.geodashing.org/#dashpoint?id=GD001-BBBB">View on Geodashing</a>]]></description>', $xml);
        $this->assertStringContainsString('<coordinates>-71,46,0</coordinates>', $xml);

        $this->assertStringContainsString('</Document>', $xml);
        $this->assertStringContainsString('</kml>', $xml);
    }

    /**
     * Verifies that the service correctly generates an empty KML XML structure
     * when no dashpoints are provided.
     */
    #[Test]
    public function processesKmlFormatCorrectlyWithNoDashpoints()
    {
        $points = [];

        $xml = $this->exportService->generateXml($points, 'kml');

        $this->assertStringContainsString('<?xml version="1.0" encoding="UTF-8"?>', $xml);
        $this->assertStringContainsString('<kml xmlns="http://www.opengis.net/kml/2.2">', $xml);
        $this->assertStringContainsString('<Document>', $xml);
        $this->assertStringNotContainsString('<Placemark>', $xml);
    }

    /**
     * Verifies that injecting an invalid format securely throws an exception.
     */
    #[Test]
    public function blocksUnsupportedFormatStrictly()
    {
        $this->expectException(InvalidArgumentException::class);
        $this->expectExceptionMessage('Error: Unsupported document format structure securely rejected.');

        $this->exportService->generateXml([], 'geojson');
    }
}
