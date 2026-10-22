<?php

declare(strict_types=1);

namespace App\Tests;

use App\Services\ProfileService;
use PDO;
use PDOStatement;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\Attributes\Test;
use PHPUnit\Framework\MockObject\MockObject;
use PHPUnit\Framework\TestCase;

/**
 * ProfileServiceTest
 *
 * Verifies user profile aggregation, privacy filtering, and player mail stats.
 */
#[CoversClass(ProfileService::class)]
class ProfileServiceTest extends TestCase
{
    /**
     * @var PDO&MockObject
     */
    private PDO $pdoMock;

    /**
     * @var ProfileService
     */
    private ProfileService $profileService;

    /**
     * Sets up the test fixtures.
     */
    #[\Override]
    protected function setUp(): void
    {
        $this->pdoMock = $this->createMock(PDO::class);
        $this->profileService = new ProfileService($this->pdoMock);
    }

    /**
     * Cleans up session state after each test.
     */
    #[\Override]
    protected function tearDown(): void
    {
        $_SESSION = [];
    }

    /**
     * Verifies getProfileSettings returns null when user is not found.
     */
    #[Test]
    public function getProfileSettingsReturnsNullIfUserNotFound(): void
    {
        $stmtMock = $this->createStub(PDOStatement::class);
        $stmtMock->method('fetch')->willReturn(false);
        $this->pdoMock->expects($this->once())->method('prepare')->willReturn($stmtMock);

        $result = $this->profileService->getProfileSettings('nonexistentuser');
        $this->assertNull($result);
    }

    /**
     * Verifies getProfileSettings returns formatted profile and game data.
     */
    #[Test]
    public function getProfileSettingsReturnsFormattedData(): void
    {
        $stmtUserMock = $this->createStub(PDOStatement::class);
        $stmtUserMock->method('fetch')->willReturn([
            'id' => 1,
            'username' => 'testuser',
            'created_at' => '2023-01-01 10:00:00',
            'subscribe_group' => 1
        ]);

        $stmtLogsMock = $this->createStub(PDOStatement::class);
        $stmtLogsMock->method('fetchAll')->willReturn([
            [
                'visit_id' => 10,
                'score_awarded' => 3,
                'is_attempt' => 0,
                'reported_time' => '2023-02-01 10:00:00',
                'distance_meters' => 45,
                'dashpoint_id' => 'GD001-XXXX',
                'game_id' => 1,
                'game_title' => 'Game 1',
                'game_is_active' => 1
            ],
            [
                'visit_id' => 11,
                'score_awarded' => 2,
                'is_attempt' => 0,
                'reported_time' => '2023-02-02 10:00:00',
                'distance_meters' => 15,
                'dashpoint_id' => 'GD001-YYYY',
                'game_id' => 1,
                'game_title' => 'Game 1',
                'game_is_active' => 1
            ]
        ]);

        $this->pdoMock->expects($this->exactly(2))
            ->method('prepare')
            ->willReturnOnConsecutiveCalls($stmtUserMock, $stmtLogsMock);

        $result = $this->profileService->getProfileSettings('testuser');

        $this->assertNotNull($result);
        $this->assertEquals(1, $result['user']['id']);
        $this->assertEquals('testuser', $result['user']['username']);
        $this->assertEquals(5, $result['user']['lifetime_score']);
        $this->assertArrayNotHasKey('subscribe_group', $result['user']);

        $this->assertCount(1, $result['games']);
        $this->assertEquals(1, $result['games'][0]['game_id']);
        $this->assertEquals(5, $result['games'][0]['game_total_score']);
        $this->assertCount(2, $result['games'][0]['visits']);
    }

    /**
     * Verifies getProfileSettings includes subscribe_group when viewing own profile.
     */
    #[Test]
    public function getProfileSettingsIncludesSubscribeGroupForSelf(): void
    {
        $_SESSION['username'] = 'testuser';

        $stmtUserMock = $this->createStub(PDOStatement::class);
        $stmtUserMock->method('fetch')->willReturn([
            'id' => 1,
            'username' => 'testuser',
            'created_at' => '2023-01-01 10:00:00',
            'subscribe_group' => 1
        ]);

        $stmtLogsMock = $this->createStub(PDOStatement::class);
        $stmtLogsMock->method('fetchAll')->willReturn([]);

        $this->pdoMock->expects($this->exactly(2))
            ->method('prepare')
            ->willReturnOnConsecutiveCalls($stmtUserMock, $stmtLogsMock);

        $result = $this->profileService->getProfileSettings('testuser');

        $this->assertNotNull($result);
        $this->assertArrayHasKey('subscribe_group', $result['user']);
        $this->assertTrue($result['user']['subscribe_group']);

        unset($_SESSION['username']);
    }

    /**
     * Verifies getPlayerMailStats returns aggregated player statistics.
     */
    #[Test]
    public function getPlayerMailStatsReturnsAggregatedStats(): void
    {
        $stmtScoreMock = $this->createStub(PDOStatement::class);
        $stmtScoreMock->method('fetch')->willReturn(['total' => 15]);

        $stmtScoreGameMock = $this->createStub(PDOStatement::class);
        $stmtScoreGameMock->method('fetch')->willReturn(['total' => 5]);

        $stmtHuntsMock = $this->createStub(PDOStatement::class);
        $stmtHuntsMock->method('fetch')->willReturn(['previous_hunts' => 12]);

        $stmtHuntsGameMock = $this->createStub(PDOStatement::class);
        $stmtHuntsGameMock->method('fetch')->willReturn(['previous_hunts' => 3]);

        $this->pdoMock->expects($this->exactly(4))
            ->method('prepare')
            ->willReturnOnConsecutiveCalls($stmtScoreMock, $stmtScoreGameMock, $stmtHuntsMock, $stmtHuntsGameMock);

        $result = $this->profileService->getPlayerMailStats(1, 2, '2026-06-07 00:00:00');

        $this->assertEquals(15, $result['total_points_all_games']);
        $this->assertEquals(5, $result['total_points_game']);
        $this->assertEquals(12, $result['previous_hunts_all_games']);
        $this->assertEquals(3, $result['previous_hunts_game']);
    }
}
