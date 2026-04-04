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
     * Verifies that the service immediately returns an error if the user is unverified.
     */
    #[Test]
    public function processVisitRejectsUnverifiedUsers()
    {
        $userMock = $this->createMock(PDOStatement::class);
        $userMock->method('fetch')->willReturn(['is_verified' => 0]);
        $this->pdoMock->method('prepare')->willReturn($userMock);

        $result = $this->reportService->processVisit(1, 'GD001-XXXX', 40.0, -75.0);

        $this->assertEquals('error', $result['status']);
        $this->assertEquals('Account not verified. Please check your email to activate your account before logging Dashpoints.', $result['message']);
    }

    /**
     * Verifies that the service immediately returns an error if the dashpoint is completely invalid/missing.
     */
    #[Test]
    public function processVisitRejectsInvalidDashpoint()
    {
        $userMock = $this->createMock(PDOStatement::class);
        $userMock->method('fetch')->willReturn(['is_verified' => 1]);

        $distMock = $this->createMock(PDOStatement::class);
        $distMock->method('fetch')->willReturn(false); // Simulates 0 rows found

        $this->pdoMock->expects($this->exactly(2))
            ->method('prepare')
            ->willReturnOnConsecutiveCalls($userMock, $distMock);

        $result = $this->reportService->processVisit(1, 'GD001-XXXX', 40.0, -75.0);

        $this->assertEquals('error', $result['status']);
        $this->assertEquals('Invalid Dashpoint ID.', $result['message']);
    }

    /**
     * Verifies that the service rejects a coordinate claim mathematically resolved by MySQL to be >100 meters away.
     */
    #[Test]
    public function processVisitRejectsDistanceOver100Meters()
    {
        $userMock = $this->createMock(PDOStatement::class);
        $userMock->method('fetch')->willReturn(['is_verified' => 1]);

        $distMock = $this->createMock(PDOStatement::class);
        // Simulates MySQL ST_Distance_Sphere returning exactly 101 meters
        $distMock->method('fetch')->willReturn(['distance_meters' => 101.5, 'is_active' => 1]); 
        
        $this->pdoMock->expects($this->exactly(2))
            ->method('prepare')
            ->willReturnOnConsecutiveCalls($userMock, $distMock);

        $result = $this->reportService->processVisit(1, 'GD001-AAAA', 40.0, -75.0);

        $this->assertEquals('error', $result['status']);
        $this->assertStringContainsString('Visit rejected', $result['message']);
    }

    /**
     * Verifies that the system safely processes and successfully logs a visit if the user is 99 meters away.
     */
    #[Test]
    public function processVisitAcceptsDistanceUnder100Meters()
    {
        // 0. Mock the user verification check
        $userMock = $this->createMock(PDOStatement::class);
        $userMock->method('fetch')->willReturn(['is_verified' => 1]);

        // 1. Mock the Distance Calculation (Returns 45 meters)
        $distMock = $this->createMock(PDOStatement::class);
        $distMock->method('fetch')->willReturn(['distance_meters' => 45.0, 'is_active' => 1]);
        
        // 2. Mock the Duplicate Check (Returns false, meaning no existing visit)
        $duplicateMock = $this->createMock(PDOStatement::class);
        $duplicateMock->method('fetch')->willReturn(false);

        // 3. Mock the Team ID fetch (Returns null, meaning user is flying solo)
        $teamMock = $this->createMock(PDOStatement::class);
        $teamMock->method('fetch')->willReturn(false);
        
        // 4. Mock the Native FCFS Scoring check (0 previous claims = 3 points)
        $scoreMock = $this->createMock(PDOStatement::class);
        $scoreMock->method('fetch')->willReturn(['previous_claims' => 0]);
        
        // 5. Mock the final Insert
        $insertMock = $this->createMock(PDOStatement::class);
        $insertMock->expects($this->once())->method('execute')->willReturn(true);

        // Chain the PDO prepares to return the distinct statements sequentially in order
        $this->pdoMock->expects($this->exactly(6))
            ->method('prepare')
            ->willReturnOnConsecutiveCalls($userMock, $distMock, $duplicateMock, $teamMock, $scoreMock, $insertMock);

        $result = $this->reportService->processVisit(1, 'GD001-AAAA', 40.0, -75.0);

        $this->assertEquals('success', $result['status']);
        $this->assertEquals(45, $result['distance']);
        $this->assertEquals(3, $result['points']);
    }

    /**
     * Verifies that the service rejects logging to an inactive game dashpoint.
     */
    #[Test]
    public function processVisitRejectsInactiveGame()
    {
        $userMock = $this->createMock(PDOStatement::class);
        $userMock->method('fetch')->willReturn(['is_verified' => 1]);

        $distMock = $this->createMock(PDOStatement::class);
        // Simulates returning 45 meters but belongs to inactive game
        $distMock->method('fetch')->willReturn(['distance_meters' => 45.0, 'is_active' => 0]); 
        
        $this->pdoMock->expects($this->exactly(2))
            ->method('prepare')
            ->willReturnOnConsecutiveCalls($userMock, $distMock);

        $result = $this->reportService->processVisit(1, 'GD001-AAAA', 40.0, -75.0);

        $this->assertEquals('error', $result['status']);
        $this->assertStringContainsString('Target dashpoint belongs to an inactive game', $result['message']);
    }
}
