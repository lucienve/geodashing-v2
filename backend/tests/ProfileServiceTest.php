<?php

declare(strict_types=1);

namespace App\Tests;

use PHPUnit\Framework\TestCase;
use PHPUnit\Framework\Attributes\Test;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\Attributes\AllowMockObjectsWithoutExpectations;
use App\Services\ProfileService;
use PDO;
use PDOStatement;

/**
 * ProfileServiceTest
 */
#[CoversClass(ProfileService::class)]
#[AllowMockObjectsWithoutExpectations]
class ProfileServiceTest extends TestCase
{
    private $pdoMock;
    private $profileService;

    protected function setUp(): void
    {
        $this->pdoMock = $this->createMock(PDO::class);
        $this->profileService = new ProfileService($this->pdoMock);
    }

    #[Test]
    public function getProfileSettingsReturnsNullIfUserNotFound()
    {
        $stmtMock = $this->createMock(PDOStatement::class);
        $stmtMock->method('fetch')->willReturn(false);
        $this->pdoMock->method('prepare')->willReturn($stmtMock);

        $result = $this->profileService->getProfileSettings('nonexistentuser');
        $this->assertNull($result);
    }

    #[Test]
    public function getProfileSettingsReturnsFormattedData()
    {
        $stmtUserMock = $this->createMock(PDOStatement::class);
        $stmtUserMock->method('fetch')->willReturn([
            'id' => 1,
            'username' => 'testuser',
            'created_at' => '2023-01-01 10:00:00'
        ]);

        $stmtLogsMock = $this->createMock(PDOStatement::class);
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

        $this->assertCount(1, $result['games']);
        $this->assertEquals(1, $result['games'][0]['game_id']);
        $this->assertEquals(5, $result['games'][0]['game_total_score']);
        $this->assertCount(2, $result['games'][0]['visits']);
    }

    #[Test]
    public function getPlayerMailStatsReturnsAggregatedStats()
    {
        $stmtScoreMock = $this->createMock(PDOStatement::class);
        $stmtScoreMock->method('fetch')->willReturn(['total' => 15]);

        $stmtScoreGameMock = $this->createMock(PDOStatement::class);
        $stmtScoreGameMock->method('fetch')->willReturn(['total' => 5]);

        $stmtHuntsMock = $this->createMock(PDOStatement::class);
        $stmtHuntsMock->method('fetch')->willReturn(['previous_hunts' => 12]);

        $stmtHuntsGameMock = $this->createMock(PDOStatement::class);
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
