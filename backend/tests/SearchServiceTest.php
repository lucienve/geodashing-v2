<?php

declare(strict_types=1);

namespace App\Tests;

use PHPUnit\Framework\TestCase;
use PHPUnit\Framework\Attributes\Test;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\Attributes\AllowMockObjectsWithoutExpectations;
use App\Services\SearchService;
use PDO;
use PDOStatement;

/**
 * SearchServiceTest
 *
 * Verifies the spatial bounding box mechanics and ensures Date Line (-180/180)
 * coordinate logic cleanly bifurcates vectors in MySQL.
 */
#[CoversClass(SearchService::class)]
#[AllowMockObjectsWithoutExpectations]
class SearchServiceTest extends TestCase
{
    private $pdoMock;
    private $searchService;

    protected function setUp(): void
    {
        // Mock the PDO object mimicking the MySQL environment
        $this->pdoMock = $this->createMock(PDO::class);
        $this->searchService = new SearchService($this->pdoMock);
    }

    /**
     * Verifies that the service properly parses a standard bounding box payload
     * directly into the default BETWEEN clauses.
     */
    #[Test]
    public function processesStandardBoundingBoxQuery()
    {
        $stmtMock = $this->createMock(PDOStatement::class);
        $stmtMock->method('fetchAll')->willReturn([
            ['id' => 'GD001-AAAA', 'lat' => 45.0, 'lon' => -70.0, 'visit_count' => 0]
        ]);

        $this->pdoMock->expects($this->once())
            ->method('prepare')
            ->with($this->logicalAnd(
                $this->stringContains('MBRContains(ST_GeomFromText(:poly, 4326), d.location)'),
                $this->stringContains('g.id = :game_id')
            ))
            ->willReturn($stmtMock);

        $result = $this->searchService->searchRegion(50.0, 40.0, -60.0, -80.0, 1);

        $this->assertCount(1, $result);
        $this->assertEquals('GD001-AAAA', $result[0]['id']);
        $this->assertEquals(0, $result[0]['visit_count']);
    }

    /**
     * Mathematically verifies that the system gracefully detects Pacific Date Line
     * crossings and splits the boundary checking bounds.
     */
    #[Test]
    public function processesAntiMeridianDateLineOverflow()
    {
        $stmtMock = $this->createMock(PDOStatement::class);
        $stmtMock->method('fetchAll')->willReturn([
            ['id' => 'GD001-FIJI', 'lat' => -18.0, 'lon' => 179.9, 'visit_count' => 1],
            ['id' => 'GD001-SAMO', 'lat' => -13.0, 'lon' => -171.0, 'visit_count' => 5]
        ]);

        $this->pdoMock->expects($this->once())
            ->method('prepare')
            ->with($this->logicalAnd(
                $this->stringContains('MBRContains(ST_GeomFromText(:poly_west, 4326), d.location) OR MBRContains(ST_GeomFromText(:poly_east, 4326), d.location)'),
                $this->stringContains('g.id = :game_id')
            ))
            ->willReturn($stmtMock);

        // Simulated Bounding box bridging the Date Line securely
        $result = $this->searchService->searchRegion(0.0, -30.0, -170.0, 175.0, 1);

        $this->assertCount(2, $result);
        $this->assertEquals('GD001-FIJI', $result[0]['id']);
        $this->assertEquals(1, $result[0]['visit_count']);

        $this->assertEquals('GD001-SAMO', $result[1]['id']);
        $this->assertEquals(5, $result[1]['visit_count']);
    }

    /**
     * Verifies that the service properly parses a standard bounding box payload
     * directly into MBRContains clauses for visits.
     */
    #[Test]
    public function searchVisitsProcessesStandardBoundingBoxQuery()
    {
        $stmtMock = $this->createMock(PDOStatement::class);
        $stmtMock->method('fetchAll')->willReturn([
            ['id' => 1, 'dashpoint_id' => 'GD001-AAAA', 'username' => 'testuser', 'lat' => 45.0, 'lon' => -70.0, 'is_attempt' => 0, 'score_awarded' => 3, 'reported_time' => '2026-07-01 12:00:00']
        ]);

        $this->pdoMock->expects($this->once())
            ->method('prepare')
            ->with($this->logicalAnd(
                $this->stringContains('MBRContains(ST_GeomFromText(:poly, 4326), v.reported_location)'),
                $this->stringContains('d.game_id = :game_id')
            ))
            ->willReturn($stmtMock);

        $result = $this->searchService->searchVisitsRegion(50.0, 40.0, -60.0, -80.0, 1);

        $this->assertCount(1, $result);
        $this->assertEquals('GD001-AAAA', $result[0]['dashpoint_id']);
        $this->assertEquals('testuser', $result[0]['username']);
        $this->assertFalse($result[0]['is_attempt']);
        $this->assertEquals(3, $result[0]['score_awarded']);
    }

    /**
     * Mathematically verifies that searchVisitsRegion gracefully detects Pacific Date Line
     * crossings and splits the boundary checking bounds.
     */
    #[Test]
    public function searchVisitsProcessesAntiMeridianDateLineOverflow()
    {
        $stmtMock = $this->createMock(PDOStatement::class);
        $stmtMock->method('fetchAll')->willReturn([
            ['id' => 1, 'dashpoint_id' => 'GD001-FIJI', 'username' => 'testuser1', 'lat' => -18.0, 'lon' => 179.9, 'is_attempt' => 0, 'score_awarded' => 3, 'reported_time' => '2026-07-01 12:00:00'],
            ['id' => 2, 'dashpoint_id' => 'GD001-SAMO', 'username' => 'testuser2', 'lat' => -13.0, 'lon' => -171.0, 'is_attempt' => 1, 'score_awarded' => 0, 'reported_time' => '2026-07-01 13:00:00']
        ]);

        $this->pdoMock->expects($this->once())
            ->method('prepare')
            ->with($this->logicalAnd(
                $this->stringContains('MBRContains(ST_GeomFromText(:poly_west, 4326), v.reported_location) OR MBRContains(ST_GeomFromText(:poly_east, 4326), v.reported_location)'),
                $this->stringContains('d.game_id = :game_id')
            ))
            ->willReturn($stmtMock);

        // Simulated Bounding box bridging the Date Line securely
        $result = $this->searchService->searchVisitsRegion(0.0, -30.0, -170.0, 175.0, 1);

        $this->assertCount(2, $result);
        $this->assertEquals('GD001-FIJI', $result[0]['dashpoint_id']);
        $this->assertFalse($result[0]['is_attempt']);
        $this->assertEquals('GD001-SAMO', $result[1]['dashpoint_id']);
        $this->assertTrue($result[1]['is_attempt']);
    }
}
