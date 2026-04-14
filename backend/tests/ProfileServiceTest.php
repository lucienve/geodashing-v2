<?php

namespace App\Tests;

use PHPUnit\Framework\TestCase;
use PHPUnit\Framework\Attributes\Test;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\Attributes\AllowMockObjectsWithoutExpectations;
use App\Services\ProfileService;
use PDO;
use PDOStatement;

require_once __DIR__ . '/../api/profile.php';

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

        $result = $this->profileService->getProfileSettings(999);
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

        $result = $this->profileService->getProfileSettings(1);
        
        $this->assertNotNull($result);
        $this->assertEquals(1, $result['user']['id']);
        $this->assertEquals('testuser', $result['user']['username']);
        $this->assertEquals(5, $result['user']['lifetime_score']);
        
        $this->assertCount(1, $result['games']);
        $this->assertEquals(1, $result['games'][0]['game_id']);
        $this->assertEquals(5, $result['games'][0]['game_total_score']);
        $this->assertCount(2, $result['games'][0]['visits']);
    }
}
