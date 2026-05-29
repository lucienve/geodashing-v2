<?php

declare(strict_types=1);

namespace App\Tests;

use PHPUnit\Framework\TestCase;
use PHPUnit\Framework\Attributes\Test;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\Attributes\AllowMockObjectsWithoutExpectations;
use App\Services\ReportService;
use PDO;
use PDOStatement;

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
    private $geoMock;
    private $reportService;

    protected function setUp(): void
    {
        // Force the testing environment variable to prevent physical email dispatches
        putenv('APP_ENV=testing');
        $_ENV['APP_ENV'] = 'testing';

        // Create a mock of the PDO object
        $this->pdoMock = $this->createMock(PDO::class);

        // Mock GeoContextService to prevent real Google Maps API calls during tests
        $this->geoMock = $this->createMock(\App\Services\GeoContextService::class);
        $this->geoMock->method('getTimezoneOffset')->willReturn(0);
        $this->geoMock->method('getDashpointContext')->willReturn('Mocked GeoContext');

        $this->reportService = new ReportService($this->pdoMock, $this->geoMock);
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
        $distMock->method('fetch')->willReturn(['distance_meters' => 101.5, 'is_active' => 1, 'dp_lat' => 40.0, 'dp_lon' => -75.0, 'game_id' => 1, 'elevation' => null]);

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
        $distMock->method('fetch')->willReturn(['distance_meters' => 45.0, 'is_active' => 1, 'dp_lat' => 40.0, 'dp_lon' => -75.0, 'game_id' => 1, 'elevation' => null]);

        // 2. Mock the Duplicate Check (Returns false, meaning no existing visit)
        $duplicateMock = $this->createMock(PDOStatement::class);
        $duplicateMock->method('fetch')->willReturn(false);

        // 3. Mock the Team ID fetch (Returns null, meaning user is flying solo)
        $teamMock = $this->createMock(PDOStatement::class);
        $teamMock->method('fetch')->willReturn(false);

        // 4. Mock the Native FCFS Scoring check (0 previous claims = 3 points)
        $scoreMock = $this->createMock(PDOStatement::class);
        $scoreMock->method('fetch')->willReturn(['previous_claims' => 0]);

        // 5. Mock the previous hunts check
        $huntsMock = $this->createMock(PDOStatement::class);
        $huntsMock->method('fetch')->willReturn(['previous_hunts' => 123]);

        $huntsGameMock = $this->createMock(PDOStatement::class);
        $huntsGameMock->method('fetch')->willReturn(['previous_hunts' => 2]);

        // 6. Mock the final Insert
        $insertMock = $this->createMock(PDOStatement::class);
        $insertMock->expects($this->once())->method('execute')->willReturn(true);

        // 7. Mock Username lookup
        $usernameMock = $this->createMock(PDOStatement::class);
        $usernameMock->method('fetch')->willReturn(['username' => 'TestUser']);

        // 8. Mock Total Score lookup
        $totalScoreMock = $this->createMock(PDOStatement::class);
        $totalScoreMock->method('fetch')->willReturn(['total' => 15]);

        $totalScoreGameMock = $this->createMock(PDOStatement::class);
        $totalScoreGameMock->method('fetch')->willReturn(['total' => 5]);

        // Chain the PDO prepares to return the distinct statements sequentially in order
        $this->pdoMock->expects($this->exactly(11))
            ->method('prepare')
            ->willReturnOnConsecutiveCalls($userMock, $distMock, $duplicateMock, $teamMock, $scoreMock, $huntsMock, $huntsGameMock, $insertMock, $usernameMock, $totalScoreMock, $totalScoreGameMock);

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
        $distMock->method('fetch')->willReturn(['distance_meters' => 45.0, 'is_active' => 0, 'dp_lat' => 40.0, 'dp_lon' => -75.0, 'game_id' => 1, 'elevation' => null]);

        $this->pdoMock->expects($this->exactly(2))
            ->method('prepare')
            ->willReturnOnConsecutiveCalls($userMock, $distMock);

        $result = $this->reportService->processVisit(1, 'GD001-AAAA', 40.0, -75.0);

        $this->assertEquals('error', $result['status']);
        $this->assertStringContainsString('Target dashpoint belongs to an inactive game', $result['message']);
    }

    /**
     * Verifies that the service accepts an attempt even if the distance is > 100 meters, awarding 0 points.
     */
    #[Test]
    public function processVisitAcceptsAttemptOver100Meters()
    {
        $userMock = $this->createMock(PDOStatement::class);
        $userMock->method('fetch')->willReturn(['is_verified' => 1]);

        $distMock = $this->createMock(PDOStatement::class);
        $distMock->method('fetch')->willReturn(['distance_meters' => 150.0, 'is_active' => 1, 'dp_lat' => 40.0, 'dp_lon' => -75.0, 'game_id' => 1, 'elevation' => null]);

        $duplicateMock = $this->createMock(PDOStatement::class);
        // Duplicate check query shouldn't fail attempt anyway because of !$isAttempt in logic
        $duplicateMock->method('fetch')->willReturn(false);

        $teamMock = $this->createMock(PDOStatement::class);
        $teamMock->method('fetch')->willReturn(false);

        $scoreMock = $this->createMock(PDOStatement::class);
        $scoreMock->method('fetch')->willReturn(['previous_claims' => 0]);

        $huntsMock = $this->createMock(PDOStatement::class);
        $huntsMock->method('fetch')->willReturn(['previous_hunts' => 123]);

        $huntsGameMock = $this->createMock(PDOStatement::class);
        $huntsGameMock->method('fetch')->willReturn(['previous_hunts' => 2]);

        $insertMock = $this->createMock(PDOStatement::class);
        $insertMock->expects($this->once())->method('execute')->willReturn(true);

        $usernameMock = $this->createMock(PDOStatement::class);
        $usernameMock->method('fetch')->willReturn(['username' => 'TestUser']);

        $totalScoreMock = $this->createMock(PDOStatement::class);
        $totalScoreMock->method('fetch')->willReturn(['total' => 15]);

        $totalScoreGameMock = $this->createMock(PDOStatement::class);
        $totalScoreGameMock->method('fetch')->willReturn(['total' => 5]);

        $this->pdoMock->expects($this->exactly(11))
            ->method('prepare')
            ->willReturnOnConsecutiveCalls($userMock, $distMock, $duplicateMock, $teamMock, $scoreMock, $huntsMock, $huntsGameMock, $insertMock, $usernameMock, $totalScoreMock, $totalScoreGameMock);

        $result = $this->reportService->processVisit(1, 'GD001-AAAA', 40.0, -75.0, true);

        $this->assertEquals('success', $result['status']);
        $this->assertEquals(150, $result['distance']);
        $this->assertEquals(0, $result['points']);
        $this->assertStringContainsString('Attempt logged.', $result['message']);
    }

    /**
     * Verifies that the service assigns 3 points to multiple users if the SQL determines they are on the same day.
     * (Mocking previous_claims = 0 simulates the DATE(...) < DATE(CURRENT_TIMESTAMP) SQL logic for same-day claims)
     */
    #[Test]
    public function processVisitAwardsSamePointsForSameDayClaims()
    {
        $userMock = $this->createMock(PDOStatement::class);
        $userMock->method('fetch')->willReturn(['is_verified' => 1]);

        $distMock = $this->createMock(PDOStatement::class);
        $distMock->method('fetch')->willReturn(['distance_meters' => 45.0, 'is_active' => 1, 'dp_lat' => 40.0, 'dp_lon' => -75.0, 'game_id' => 1, 'elevation' => null]);

        $duplicateMock = $this->createMock(PDOStatement::class);
        $duplicateMock->method('fetch')->willReturn(false);

        $teamMock = $this->createMock(PDOStatement::class);
        $teamMock->method('fetch')->willReturn(false);

        // Simulate that no claims existed on previous days (even if claims exist today)
        $scoreMock = $this->createMock(PDOStatement::class);
        $scoreMock->method('fetch')->willReturn(['previous_claims' => 0]);

        $huntsMock = $this->createMock(PDOStatement::class);
        $huntsMock->method('fetch')->willReturn(['previous_hunts' => 123]);

        $huntsGameMock = $this->createMock(PDOStatement::class);
        $huntsGameMock->method('fetch')->willReturn(['previous_hunts' => 2]);

        $insertMock = $this->createMock(PDOStatement::class);
        $insertMock->expects($this->once())->method('execute')->willReturn(true);

        $usernameMock = $this->createMock(PDOStatement::class);
        $usernameMock->method('fetch')->willReturn(['username' => 'TestUserDay1']);

        $totalScoreMock = $this->createMock(PDOStatement::class);
        $totalScoreMock->method('fetch')->willReturn(['total' => 15]);

        $totalScoreGameMock = $this->createMock(PDOStatement::class);
        $totalScoreGameMock->method('fetch')->willReturn(['total' => 5]);

        $this->pdoMock->expects($this->exactly(11))
            ->method('prepare')
            ->willReturnOnConsecutiveCalls($userMock, $distMock, $duplicateMock, $teamMock, $scoreMock, $huntsMock, $huntsGameMock, $insertMock, $usernameMock, $totalScoreMock, $totalScoreGameMock);

        $result = $this->reportService->processVisit(2, 'GD001-SAME', 40.0, -75.0);

        $this->assertEquals('success', $result['status']);
        $this->assertEquals(3, $result['points'], "Secondary claims on the same day should still award 3 points.");
    }

    /**
     * Verifies that the service assigns 2 points if exactly one prior claim exists on an earlier day.
     */
    #[Test]
    public function processVisitAwardsTwoPointsForSecondDayClaim()
    {
        $userMock = $this->createMock(PDOStatement::class);
        $userMock->method('fetch')->willReturn(['is_verified' => 1]);

        $distMock = $this->createMock(PDOStatement::class);
        $distMock->method('fetch')->willReturn(['distance_meters' => 45.0, 'is_active' => 1, 'dp_lat' => 40.0, 'dp_lon' => -75.0, 'game_id' => 1, 'elevation' => null]);

        $duplicateMock = $this->createMock(PDOStatement::class);
        $duplicateMock->method('fetch')->willReturn(false);

        $teamMock = $this->createMock(PDOStatement::class);
        $teamMock->method('fetch')->willReturn(false);

        // Simulate exactly one claim on a previous day
        $scoreMock = $this->createMock(PDOStatement::class);
        $scoreMock->method('fetch')->willReturn(['previous_claims' => 1]);

        $huntsMock = $this->createMock(PDOStatement::class);
        $huntsMock->method('fetch')->willReturn(['previous_hunts' => 123]);

        $huntsGameMock = $this->createMock(PDOStatement::class);
        $huntsGameMock->method('fetch')->willReturn(['previous_hunts' => 2]);

        $insertMock = $this->createMock(PDOStatement::class);
        $insertMock->expects($this->once())->method('execute')->willReturn(true);

        $usernameMock = $this->createMock(PDOStatement::class);
        $usernameMock->method('fetch')->willReturn(['username' => 'TestUserDay2']);

        $totalScoreMock = $this->createMock(PDOStatement::class);
        $totalScoreMock->method('fetch')->willReturn(['total' => 15]);

        $totalScoreGameMock = $this->createMock(PDOStatement::class);
        $totalScoreGameMock->method('fetch')->willReturn(['total' => 5]);

        $this->pdoMock->expects($this->exactly(11))
            ->method('prepare')
            ->willReturnOnConsecutiveCalls($userMock, $distMock, $duplicateMock, $teamMock, $scoreMock, $huntsMock, $huntsGameMock, $insertMock, $usernameMock, $totalScoreMock, $totalScoreGameMock);

        $result = $this->reportService->processVisit(3, 'GD001-NEXT', 40.0, -75.0);

        $this->assertEquals('success', $result['status']);
        $this->assertEquals(2, $result['points'], "Claims on a subsequent day with 1 prior-day claim should award 2 points.");
    }

    /**
     * Verifies that processVisit sends email by default (when $suppressEmail is false).
     */
    #[Test]
    public function processVisitSendsEmailByDefault()
    {
        $userMock = $this->createMock(PDOStatement::class);
        $userMock->method('fetch')->willReturn(['is_verified' => 1]);

        $distMock = $this->createMock(PDOStatement::class);
        $distMock->method('fetch')->willReturn(['distance_meters' => 45.0, 'is_active' => 1, 'dp_lat' => 40.0, 'dp_lon' => -75.0, 'game_id' => 1, 'elevation' => null]);

        $duplicateMock = $this->createMock(PDOStatement::class);
        $duplicateMock->method('fetch')->willReturn(false);

        $teamMock = $this->createMock(PDOStatement::class);
        $teamMock->method('fetch')->willReturn(false);

        $scoreMock = $this->createMock(PDOStatement::class);
        $scoreMock->method('fetch')->willReturn(['previous_claims' => 0]);

        $huntsMock = $this->createMock(PDOStatement::class);
        $huntsMock->method('fetch')->willReturn(['previous_hunts' => 123]);

        $huntsGameMock = $this->createMock(PDOStatement::class);
        $huntsGameMock->method('fetch')->willReturn(['previous_hunts' => 2]);

        $insertMock = $this->createMock(PDOStatement::class);
        $insertMock->method('execute')->willReturn(true);

        $usernameMock = $this->createMock(PDOStatement::class);
        $usernameMock->method('fetch')->willReturn(['username' => 'TestUser']);

        $totalScoreMock = $this->createMock(PDOStatement::class);
        $totalScoreMock->method('fetch')->willReturn(['total' => 15]);

        $totalScoreGameMock = $this->createMock(PDOStatement::class);
        $totalScoreGameMock->method('fetch')->willReturn(['total' => 5]);

        $this->pdoMock->expects($this->exactly(11))
            ->method('prepare')
            ->willReturnOnConsecutiveCalls($userMock, $distMock, $duplicateMock, $teamMock, $scoreMock, $huntsMock, $huntsGameMock, $insertMock, $usernameMock, $totalScoreMock, $totalScoreGameMock);

        $testableService = new class ($this->pdoMock, $this->geoMock) extends ReportService {
            public bool $emailSent = false;

            protected function sendVisitReportEmail(string $username, string $dashpointId, int $distance, int $points, int $totalPointsAllGames, int $totalPointsGame, bool $isAttempt, ?string $notes, ?string $photosJson, int $previousHuntsAllGames = 0, int $previousHuntsGame = 0, ?string $geoContext = null, bool $isEdit = false): void
            {
                $this->emailSent = true;
            }
        };

        $result = $testableService->processVisit(1, 'GD001-AAAA', 40.0, -75.0);

        $this->assertEquals('success', $result['status']);
        $this->assertTrue($testableService->emailSent);
    }

    /**
     * Verifies that processVisit suppresses email notification when $suppressEmail is true.
     */
    #[Test]
    public function processVisitSuppressesEmailWhenFlagged()
    {
        $userMock = $this->createMock(PDOStatement::class);
        $userMock->method('fetch')->willReturn(['is_verified' => 1]);

        $distMock = $this->createMock(PDOStatement::class);
        $distMock->method('fetch')->willReturn(['distance_meters' => 45.0, 'is_active' => 1, 'dp_lat' => 40.0, 'dp_lon' => -75.0, 'game_id' => 1, 'elevation' => null]);

        $duplicateMock = $this->createMock(PDOStatement::class);
        $duplicateMock->method('fetch')->willReturn(false);

        $teamMock = $this->createMock(PDOStatement::class);
        $teamMock->method('fetch')->willReturn(false);

        $scoreMock = $this->createMock(PDOStatement::class);
        $scoreMock->method('fetch')->willReturn(['previous_claims' => 0]);

        $huntsMock = $this->createMock(PDOStatement::class);
        $huntsMock->method('fetch')->willReturn(['previous_hunts' => 123]);

        $huntsGameMock = $this->createMock(PDOStatement::class);
        $huntsGameMock->method('fetch')->willReturn(['previous_hunts' => 2]);

        $insertMock = $this->createMock(PDOStatement::class);
        $insertMock->method('execute')->willReturn(true);

        $usernameMock = $this->createMock(PDOStatement::class);
        $usernameMock->method('fetch')->willReturn(['username' => 'TestUser']);

        $totalScoreMock = $this->createMock(PDOStatement::class);
        $totalScoreMock->method('fetch')->willReturn(['total' => 15]);

        $totalScoreGameMock = $this->createMock(PDOStatement::class);
        $totalScoreGameMock->method('fetch')->willReturn(['total' => 5]);

        $this->pdoMock->expects($this->exactly(11))
            ->method('prepare')
            ->willReturnOnConsecutiveCalls($userMock, $distMock, $duplicateMock, $teamMock, $scoreMock, $huntsMock, $huntsGameMock, $insertMock, $usernameMock, $totalScoreMock, $totalScoreGameMock);

        $testableService = new class ($this->pdoMock, $this->geoMock) extends ReportService {
            public bool $emailSent = false;

            protected function sendVisitReportEmail(string $username, string $dashpointId, int $distance, int $points, int $totalPointsAllGames, int $totalPointsGame, bool $isAttempt, ?string $notes, ?string $photosJson, int $previousHuntsAllGames = 0, int $previousHuntsGame = 0, ?string $geoContext = null, bool $isEdit = false): void
            {
                $this->emailSent = true;
            }
        };

        $result = $testableService->processVisit(1, 'GD001-AAAA', 40.0, -75.0, false, null, null, true);

        $this->assertEquals('success', $result['status']);
        $this->assertFalse($testableService->emailSent);
    }
}
