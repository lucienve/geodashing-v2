<?php
use PHPUnit\Framework\TestCase;

require_once __DIR__ . '/../services/SearchService.php';

use PHPUnit\Framework\Attributes\Test;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\Attributes\AllowMockObjectsWithoutExpectations;

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
     * directly into the default BETWEEN clauses natively.
     */
    #[Test]
    public function processesStandardBoundingBoxQueryNatively()
    {
        $stmtMock = $this->createMock(PDOStatement::class);
        $stmtMock->method('fetchAll')->willReturn([
            ['id' => 'GD001-AAAA', 'lat' => 45.0, 'lon' => -70.0, 'visit_count' => 0]
        ]);
        
        // Assert the SQL string securely binds a strict monolithic coordinate matrix expecting Longitudes on ST_Y
        $this->pdoMock->expects($this->once())
            ->method('prepare')
            ->with($this->stringContains('ST_Y(d.location) BETWEEN :west AND :east'))
            ->willReturn($stmtMock);

        $result = $this->searchService->searchRegion(50.0, 40.0, -60.0, -80.0);

        $this->assertCount(1, $result);
        $this->assertEquals('GD001-AAAA', $result[0]['id']);
        $this->assertEquals(0, $result[0]['visit_count']);
    }

    /**
     * Mathematically verifies that the system gracefully detects Pacific Date Line
     * crossings and splits the boundary checking bounds.
     */
    #[Test]
    public function processesAntiMeridianDateLineOveflowNatively()
    {
        $stmtMock = $this->createMock(PDOStatement::class);
        $stmtMock->method('fetchAll')->willReturn([
            ['id' => 'GD001-FIJI', 'lat' => -18.0, 'lon' => 179.9, 'visit_count' => 1],
            ['id' => 'GD001-SAMO', 'lat' => -13.0, 'lon' => -171.0, 'visit_count' => 5]
        ]);
        
        // Assert the SQL definitively overrides the WHERE clause mapping dual hemispheres via ST_Y Longitudes natively
        $this->pdoMock->expects($this->once())
            ->method('prepare')
            ->with($this->stringContains('ST_Y(d.location) BETWEEN :west AND 180.0 OR ST_Y(d.location) BETWEEN -180.0 AND :east'))
            ->willReturn($stmtMock);

        // Simulated Bounding box bridging the Date Line securely
        $result = $this->searchService->searchRegion(0.0, -30.0, -170.0, 175.0);

        $this->assertCount(2, $result);
        $this->assertEquals('GD001-FIJI', $result[0]['id']);
        $this->assertEquals(1, $result[0]['visit_count']);
        
        $this->assertEquals('GD001-SAMO', $result[1]['id']);
        $this->assertEquals(5, $result[1]['visit_count']);
    }

    /**
     * Verifies that injecting an explicit Game ID natively overrides the is_active mapping
     * correctly binding historical boundaries directly to the target configuration.
     */
    #[Test]
    public function processesHistoricalGameIdFilterNatively()
    {
        $stmtMock = $this->createMock(PDOStatement::class);
        $stmtMock->method('fetchAll')->willReturn([
            ['id' => 'GD001-XXXX', 'lat' => 45.0, 'lon' => -70.0, 'visit_count' => 3]
        ]);
        
        $this->pdoMock->expects($this->once())
            ->method('prepare')
            ->with($this->logicalAnd(
                 $this->stringContains('g.id = :game_id'),
                 $this->logicalNot($this->stringContains('g.is_active = TRUE'))
             ))
            ->willReturn($stmtMock);

        $result = $this->searchService->searchRegion(50.0, 40.0, -60.0, -80.0, 999);

        $this->assertCount(1, $result);
        $this->assertEquals('GD001-XXXX', $result[0]['id']);
        $this->assertEquals(3, $result[0]['visit_count']);
    }
}
