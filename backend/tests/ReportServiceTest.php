<?php
use PHPUnit\Framework\TestCase;

require_once __DIR__ . '/../api/report.php';

use PHPUnit\Framework\Attributes\Test;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\Attributes\AllowMockObjectsWithoutExpectations;

/**
 * ReportServiceTest
 *
 * Tests the core spatial distance and validation logic for processing dashpoint claims.
 */
#[CoversClass(ReportService::class)]
#[AllowMockObjectsWithoutExpectations]
class ReportServiceTest extends TestCase
{
    private $pdoMock;
    private $reportService;

    protected function setUp(): void
    {
        // Create a mock of the PDO object
        $this->pdoMock = $this->createMock(PDO::class);
        $this->reportService = new ReportService($this->pdoMock);
    }

    /**
     * Verifies that the service immediately returns an error if the dashpoint is completely invalid/missing.
     */
    #[Test]
    public function processVisitRejectsInvalidDashpoint()
    {
        $stmtMock = $this->createMock(PDOStatement::class);
        $stmtMock->method('fetch')->willReturn(false); // Simulates 0 rows found
        $this->pdoMock->method('prepare')->willReturn($stmtMock);

        $result = $this->reportService->processVisit(1, 'GD01-99999', 40.0, -75.0, '2026-04-01 12:00:00');

        $this->assertEquals('error', $result['status']);
        $this->assertEquals('Invalid Dashpoint ID.', $result['message']);
    }

    /**
     * Verifies that the service rejects a coordinate claim mathematically resolved by MySQL to be >100 meters away.
     */
    #[Test]
    public function processVisitRejectsDistanceOver100Meters()
    {
        $stmtMock = $this->createMock(PDOStatement::class);
        // Simulates MySQL ST_Distance_Sphere returning exactly 101 meters
        $stmtMock->method('fetch')->willReturn(['distance_meters' => 101.5]); 
        $this->pdoMock->method('prepare')->willReturn($stmtMock);

        $result = $this->reportService->processVisit(1, 'GD01-00001', 40.0, -75.0, '2026-04-01 12:00:00');

        $this->assertEquals('error', $result['status']);
        $this->assertStringContainsString('Visit rejected', $result['message']);
    }

    /**
     * Verifies that the system safely processes and successfully logs a visit if the user is 99 meters away.
     */
    #[Test]
    public function processVisitAcceptsDistanceUnder100Meters()
    {
        // 1. Mock the Distance Calculation (Returns 45 meters)
        $distMock = $this->createMock(PDOStatement::class);
        $distMock->method('fetch')->willReturn(['distance_meters' => 45.0]);
        
        // 2. Mock the Duplicate Check (Returns false, meaning no existing visit)
        $duplicateMock = $this->createMock(PDOStatement::class);
        $duplicateMock->method('fetch')->willReturn(false);

        // 3. Mock the Team ID fetch (Returns null, meaning user is flying solo)
        $teamMock = $this->createMock(PDOStatement::class);
        $teamMock->method('fetch')->willReturn(false);
        
        // 4. Mock the final Insert
        $insertMock = $this->createMock(PDOStatement::class);
        $insertMock->expects($this->once())->method('execute')->willReturn(true);

        // Chain the PDO prepares to return the distinct statements sequentially in order
        $this->pdoMock->expects($this->exactly(4))
            ->method('prepare')
            ->willReturnOnConsecutiveCalls($distMock, $duplicateMock, $teamMock, $insertMock);

        $result = $this->reportService->processVisit(1, 'GD01-00001', 40.0, -75.0, '2026-04-01 12:00:00');

        $this->assertEquals('success', $result['status']);
        $this->assertEquals(45, $result['distance']);
    }
}
