<?php

declare(strict_types=1);

namespace App\Tests;

use PHPUnit\Framework\TestCase;
use PHPUnit\Framework\Attributes\Test;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\Attributes\AllowMockObjectsWithoutExpectations;
use App\Services\GameService;
use PDO;
use PDOStatement;

#[CoversClass(GameService::class)]
#[AllowMockObjectsWithoutExpectations]
class GameServiceTest extends TestCase
{
    private $pdoMock;
    private $gameService;

    protected function setUp(): void
    {
        $this->pdoMock = $this->createMock(PDO::class);
        $this->gameService = new GameService($this->pdoMock);
    }

    #[Test]
    public function getActiveGameReturnsActiveGameSuccessfully()
    {
        $stmtMock = $this->createMock(PDOStatement::class);
        $gameData = [
            'id' => 1,
            'title' => 'April Dash 2026',
            'start_time' => '2026-04-01 00:00:00',
            'end_time' => '2026-04-30 23:59:59'
        ];

        $stmtMock->expects($this->once())
            ->method('execute')
            ->willReturn(true);

        $stmtMock->expects($this->once())
            ->method('fetch')
            ->willReturn($gameData);

        $this->pdoMock->expects($this->once())
            ->method('prepare')
            ->with($this->stringContains('is_active = TRUE'))
            ->willReturn($stmtMock);

        $result = $this->gameService->getActiveGame();

        $this->assertNotNull($result);
        $this->assertEquals(1, $result['game_id']);
        $this->assertEquals('April Dash 2026', $result['title']);
    }

    #[Test]
    public function getActiveGameReturnsNullWhenNoActiveGame()
    {
        $stmtMock = $this->createMock(PDOStatement::class);

        $stmtMock->expects($this->once())
            ->method('execute')
            ->willReturn(true);

        $stmtMock->expects($this->once())
            ->method('fetch')
            ->willReturn(false);

        $this->pdoMock->expects($this->once())
            ->method('prepare')
            ->willReturn($stmtMock);

        $result = $this->gameService->getActiveGame();

        $this->assertNull($result);
    }

    #[Test]
    public function getAllGamesReturnsListOfGames()
    {
        $stmtMock = $this->createMock(PDOStatement::class);
        $gamesData = [
            [
                'id' => 2,
                'title' => 'April Dash 2026',
                'start_time' => '2026-04-01 00:00:00',
                'end_time' => '2026-04-30 23:59:59',
                'is_active' => 1
            ],
            [
                'id' => 1,
                'title' => 'March Dash 2026',
                'start_time' => '2026-03-01 00:00:00',
                'end_time' => '2026-03-31 23:59:59',
                'is_active' => 0
            ]
        ];

        $stmtMock->expects($this->once())
            ->method('fetchAll')
            ->willReturn($gamesData);

        $this->pdoMock->expects($this->once())
            ->method('query')
            ->with($this->stringContains('ORDER BY id DESC'))
            ->willReturn($stmtMock);

        $result = $this->gameService->getAllGames();

        $this->assertIsArray($result);
        $this->assertCount(2, $result);
        $this->assertEquals(2, $result[0]['id']);
        $this->assertEquals(1, $result[1]['id']);
    }
}
