<?php

declare(strict_types=1);

namespace Tests;

use PHPUnit\Framework\TestCase;
use PHPUnit\Framework\Attributes\AllowMockObjectsWithoutExpectations;
use App\Services\GeoContextService;
use PDO;
use PDOStatement;

#[AllowMockObjectsWithoutExpectations]
class GeoContextServiceTest extends TestCase
{
    /**
     * @var GeoContextService|\PHPUnit\Framework\MockObject\MockObject
     */
    private $service;

    protected function setUp(): void
    {
        $pdoMock = $this->createMock(PDO::class);

        // We use a partial mock to bypass the actual HTTP/CURL calls and DB spatial queries
        // so we can test the string formatting and bearing math in isolation.
        $this->service = $this->getMockBuilder(GeoContextService::class)
            ->setConstructorArgs([$pdoMock, 'fake_api_key'])
            ->onlyMethods(['getProvinceAndCountry', 'getLargestNearbyCity'])
            ->getMock();
    }

    public function testGetDashpointContextWithBothRegionAndCity()
    {
        $this->service->method('getProvinceAndCountry')
            ->willReturn(['province' => 'Maine', 'country' => 'United States']);

        $this->service->method('getLargestNearbyCity')
            ->willReturn([
                'name' => 'Portland',
                'admin_name' => 'Maine',
                'country_name' => 'United States',
                'lat' => 43.6591,
                'lon' => -70.2568,
                'distance_meters' => 80467 // ~50 miles
            ]);

        // Point is NW of Portland
        // Portland is at ~ 43.65, -70.25
        // A point NW would be at ~ 44.0, -71.0
        $context = $this->service->getDashpointContext(44.0, -71.0, 'GD01-ABCD');

        $this->assertEquals(
            'GD01-ABCD is in Maine, United States, and is 50 miles northwest of Portland, Maine, United States',
            $context
        );
    }

    public function testGetDashpointContextWithOnlyRegion()
    {
        $this->service->method('getProvinceAndCountry')
            ->willReturn(['province' => 'Quebec', 'country' => 'Canada']);

        $this->service->method('getLargestNearbyCity')
            ->willReturn(null);

        $context = $this->service->getDashpointContext(50.0, -70.0, 'GD01-XYZW');

        $this->assertEquals(
            'GD01-XYZW is in Quebec, Canada',
            $context
        );
    }

    public function testGetDashpointContextWithOnlyCity()
    {
        $this->service->method('getProvinceAndCountry')
            ->willReturn(null);

        $this->service->method('getLargestNearbyCity')
            ->willReturn([
                'name' => 'Alice Springs',
                'admin_name' => 'Northern Territory',
                'country_name' => 'Australia',
                'lat' => -23.6980,
                'lon' => 133.8807,
                'distance_meters' => 16093 // ~10 miles
            ]);

        // Dashpoint is exactly South of Alice Springs
        $context = $this->service->getDashpointContext(-23.8, 133.8807, 'GD01-1234');

        $this->assertEquals(
            'GD01-1234 is 10 miles south of Alice Springs, Northern Territory, Australia',
            $context
        );
    }

    public function testGetDashpointContextWithNothing()
    {
        $this->service->method('getProvinceAndCountry')
            ->willReturn(null);

        $this->service->method('getLargestNearbyCity')
            ->willReturn(null);

        $context = $this->service->getDashpointContext(0.0, 0.0, 'GD01-0000');

        $this->assertEquals(
            'GD01-0000 is at coordinates 0.000000, 0.000000',
            $context
        );
    }

    /**
     * Use Reflection to test the protected calculateBearing method directly
     */
    public function testCalculateBearing()
    {
        $pdoMock = $this->createMock(PDO::class);
        $service = new GeoContextService($pdoMock, 'fake_api_key');

        $reflection = new \ReflectionClass($service);
        $method = $reflection->getMethod('calculateBearing');
        $method->setAccessible(true);

        // From Null Island (0,0) to North (1,0)
        $this->assertEquals("North", $method->invoke($service, 0, 0, 1, 0));

        // From Null Island (0,0) to South (-1,0)
        $this->assertEquals("South", $method->invoke($service, 0, 0, -1, 0));

        // From Null Island (0,0) to East (0,1)
        $this->assertEquals("East", $method->invoke($service, 0, 0, 0, 1));

        // From Null Island (0,0) to West (0,-1)
        $this->assertEquals("West", $method->invoke($service, 0, 0, 0, -1));

        // From Null Island to NE (1,1)
        $this->assertEquals("Northeast", $method->invoke($service, 0, 0, 1, 1));
    }

    public function testGetTimezoneOffsetEmptyApiKey()
    {
        $pdoMock = $this->createMock(PDO::class);
        $service = new GeoContextService($pdoMock, ''); // Empty API key

        // Should return 0 immediately without making curl requests
        $offset = $service->getTimezoneOffset(40.0, -70.0);
        $this->assertEquals(0, $offset);
    }

    public function testEvaluateAndGetExtremeAnnotations()
    {
        $pdoMock = $this->createMock(PDO::class);
        $stmtMock = $this->createMock(PDOStatement::class);

        $pdoMock->method('prepare')->willReturn($stmtMock);

        // Simulating that no records exist yet (fetch returns false)
        $stmtMock->method('fetch')->willReturn(false);
        $stmtMock->method('execute')->willReturn(true);

        $service = new GeoContextService($pdoMock, 'fake_api_key');

        $annotations = $service->evaluateAndGetExtremeAnnotations(
            'GD-123',
            45.0,
            -70.0,
            100.5,
            'Maine',
            'US',
            2026
        );

        $this->assertStringContainsString('all-time northernmost', $annotations);
        $this->assertStringContainsString('all-time highest', $annotations);
        $this->assertStringContainsString('2026 westernmost', $annotations);
    }
}
