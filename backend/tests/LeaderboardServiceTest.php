<?php

declare(strict_types=1);

namespace App\Tests;

use PHPUnit\Framework\TestCase;
use PHPUnit\Framework\Attributes\Test;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\Attributes\AllowMockObjectsWithoutExpectations;
use App\Services\LeaderboardService;
use PDO;
use PDOStatement;

/**
 * LeaderboardServiceTest
 *
 * Verifies the mathematical aggregation, rank mapping, and explicit temporal
 * Tie-breaker algorithms parsing identical players.
 */
#[CoversClass(LeaderboardService::class)]
#[AllowMockObjectsWithoutExpectations]
class LeaderboardServiceTest extends TestCase
{
    private $pdoMock;
    private $leaderboardService;

    protected function setUp(): void
    {
        $this->pdoMock = $this->createMock(PDO::class);
        $this->leaderboardService = new LeaderboardService($this->pdoMock);
    }

    /**
     * Asserts that when two players tie with the exact same Score `(20)`, they get
     * the exact same rank under the points-only ranking rules.
     */
    #[Test]
    public function getSoloRankingsProperlyResolvesTieBreakers()
    {
        $stmtMock = $this->createMock(PDOStatement::class);

        // Simulating the MySQL Engine returning an Array sorted `ORDER BY total_score DESC, u.username ASC`
        $stmtMock->method('fetchAll')->willReturn([
            ['user_id' => 1, 'username' => 'Alpha', 'total_score' => 20, 'total_finds' => 10, 'last_find_time' => '2026-03-01 12:00:00'],
            ['user_id' => 2, 'username' => 'Bravo', 'total_score' => 20, 'total_finds' => 8,  'last_find_time' => '2026-03-01 13:00:00'],
            ['user_id' => 3, 'username' => 'Charlie', 'total_score' => 15, 'total_finds' => 5,  'last_find_time' => '2026-03-05 10:00:00']
        ]);

        $this->pdoMock->method('prepare')->willReturn($stmtMock);

        $rankings = $this->leaderboardService->getSoloRankings(1);

        $this->assertCount(3, $rankings);

        // Alpha and Bravo tied on 20 points, so both earn Rank #1.
        $this->assertEquals(1, $rankings[0]['rank']);
        $this->assertEquals('Alpha', $rankings[0]['username']);

        $this->assertEquals(1, $rankings[1]['rank']);
        $this->assertEquals('Bravo', $rankings[1]['username']);

        // Charlie gets rank 3 (skipping rank 2 due to standard competition ranking).
        $this->assertEquals(3, $rankings[2]['rank']);
        $this->assertEquals('Charlie', $rankings[2]['username']);
    }

    /**
     * Asserts that if two players log the exact same score at the exact same identical second,
     * the system awards them the identical rank.
     */
    #[Test]
    public function getSoloRankingsHandlesExactSimultaneousTiesProperly()
    {
        $stmtMock = $this->createMock(PDOStatement::class);

        $stmtMock->method('fetchAll')->willReturn([
            ['user_id' => 4, 'username' => 'Delta', 'total_score' => 50, 'total_finds' => 20, 'last_find_time' => '2026-03-10 12:00:00'],
            ['user_id' => 5, 'username' => 'Echo', 'total_score' => 50, 'total_finds' => 20, 'last_find_time' => '2026-03-10 12:00:00'],
            ['user_id' => 6, 'username' => 'Foxtrot', 'total_score' => 10, 'total_finds' => 4, 'last_find_time' => '2026-03-11 12:00:00']
        ]);

        $this->pdoMock->method('prepare')->willReturn($stmtMock);

        $rankings = $this->leaderboardService->getSoloRankings(1);

        $this->assertCount(3, $rankings);

        // Delta and Echo hold equal values. Both earn Rank #1.
        $this->assertEquals(1, $rankings[0]['rank']);
        $this->assertEquals(1, $rankings[1]['rank']);

        // Foxtrot follows, inheriting the ordinal index #3.
        $this->assertEquals(3, $rankings[2]['rank']);
    }

    /**
     * Asserts returning empty arrays gracefully handles edge bounds.
     */
    #[Test]
    public function getSoloRankingsHandlesEmptySetsSafely()
    {
        $stmtMock = $this->createMock(PDOStatement::class);
        $stmtMock->method('fetchAll')->willReturn([]); // Simulate ZERO results

        $this->pdoMock->method('prepare')->willReturn($stmtMock);

        $rankings = $this->leaderboardService->getSoloRankings(999);
        $this->assertIsArray($rankings);
        $this->assertCount(0, $rankings);
    }
}
