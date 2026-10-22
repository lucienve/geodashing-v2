<?php

declare(strict_types=1);

namespace App\Tests;

use App\Services\GeoContextService;
use PDO;
use PDOStatement;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\Attributes\Test;
use PHPUnit\Framework\MockObject\Stub;
use PHPUnit\Framework\TestCase;

/**
 * GeoContextServiceTest
 *
 * Verifies reverse geocoding context formatting, bearing math, timezone offsets,
 * and geographic extreme annotations.
 */
#[CoversClass(GeoContextService::class)]
class GeoContextServiceTest extends TestCase
{
    /**
     * @var GeoContextService&Stub
     */
    private GeoContextService $service;

    /**
     * Sets up the test fixtures.
     */
    #[\Override]
    protected function setUp(): void
    {
        $pdoMock = $this->createStub(PDO::class);

        // We use a partial stub to bypass the actual HTTP/CURL calls and DB spatial queries
        // so we can test the string formatting and bearing math in isolation.
        $this->service = $this->getStubBuilder(GeoContextService::class)
            ->setConstructorArgs([$pdoMock, 'fake_api_key'])
            ->onlyMethods(['getProvinceAndCountry', 'getLargestNearbyCity'])
            ->getStub();
    }

    /**
     * Verifies context string when both region and nearby city are present.
     */
    #[Test]
    public function testGetDashpointContextWithBothRegionAndCity(): void
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

    /**
     * Verifies context string when only region is present.
     */
    #[Test]
    public function testGetDashpointContextWithOnlyRegion(): void
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

    /**
     * Verifies context string when only nearby city is present.
     */
    #[Test]
    public function testGetDashpointContextWithOnlyCity(): void
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

    /**
     * Verifies fallback context string when neither region nor city is found.
     */
    #[Test]
    public function testGetDashpointContextWithNothing(): void
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
     * Uses reflection to test the protected calculateBearing method directly.
     */
    #[Test]
    public function testCalculateBearing(): void
    {
        $pdoMock = $this->createStub(PDO::class);
        $service = new GeoContextService($pdoMock, 'fake_api_key');

        $reflection = new \ReflectionClass($service);
        $method = $reflection->getMethod('calculateBearing');

        // From Null Island (0,0) to North (1,0)
        $this->assertEquals("North", $method->invoke($service, 0.0, 0.0, 1.0, 0.0));

        // From Null Island (0,0) to South (-1,0)
        $this->assertEquals("South", $method->invoke($service, 0.0, 0.0, -1.0, 0.0));

        // From Null Island (0,0) to East (0,1)
        $this->assertEquals("East", $method->invoke($service, 0.0, 0.0, 0.0, 1.0));

        // From Null Island (0,0) to West (0,-1)
        $this->assertEquals("West", $method->invoke($service, 0.0, 0.0, 0.0, -1.0));

        // From Null Island to NE (1,1)
        $this->assertEquals("Northeast", $method->invoke($service, 0.0, 0.0, 1.0, 1.0));
    }

    /**
     * Verifies getTimezoneOffset returns 0 when the API key is empty.
     */
    #[Test]
    public function testGetTimezoneOffsetEmptyApiKey(): void
    {
        $pdoMock = $this->createStub(PDO::class);
        $service = new GeoContextService($pdoMock, ''); // Empty API key

        // Should return 0 immediately without making curl requests
        $offset = $service->getTimezoneOffset(40.0, -70.0);
        $this->assertEquals(0, $offset);
    }

    /**
     * Verifies evaluateAndGetExtremeAnnotations returns expected annotations when no records exist.
     */
    #[Test]
    public function testEvaluateAndGetExtremeAnnotations(): void
    {
        $pdoMock = $this->createStub(PDO::class);
        $stmtMock = $this->createStub(PDOStatement::class);

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
