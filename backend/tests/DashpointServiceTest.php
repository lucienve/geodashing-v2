<?php

declare(strict_types=1);

namespace App\Tests;

use PHPUnit\Framework\TestCase;
use PHPUnit\Framework\Attributes\Test;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\Attributes\AllowMockObjectsWithoutExpectations;
use App\Services\DashpointService;
use PDO;
use PDOStatement;

#[CoversClass(DashpointService::class)]
#[AllowMockObjectsWithoutExpectations]
class DashpointServiceTest extends TestCase
{
    private $pdoMock;
    private $dashpointService;

    protected function setUp(): void
    {
        // Synthesize the PDO connection so we don't accidentally touch the actual active Geodashing database
        $this->pdoMock = $this->createMock(PDO::class);
        $this->dashpointService = new DashpointService($this->pdoMock);
    }

    public function testGetDashpointDetailsSuccess()
    {
        $dashpointId = 'GD001-AAAA';

        // 1. Mock the first query pulling target metadata (Location)
        $stmtMock1 = $this->createMock(PDOStatement::class);
        $stmtMock1->expects($this->once())
            ->method('execute')
            ->with(['id' => $dashpointId])
            ->willReturn(true);
        $stmtMock1->expects($this->once())
            ->method('fetch')
            ->willReturn([
                'id' => $dashpointId,
                'lat' => 39.8283,
                'lon' => -98.5795,
                'game_id' => 1
            ]);

        // 2. Mock the second query pulling the Historical Ledgers (Visits JOIN Users)
        $stmtMock2 = $this->createMock(PDOStatement::class);
        $stmtMock2->expects($this->once())
            ->method('execute')
            ->with(['id' => $dashpointId])
            ->willReturn(true);
        $stmtMock2->expects($this->once())
            ->method('fetchAll')
            ->willReturn([
                [
                    'visit_id' => 50,
                    'username' => 'LucienDashes',
                    'reported_time' => '2026-03-28 12:00:00',
                    'score_awarded' => 3,
                    'notes' => 'Tough hike.',
                    'photos' => '["/uploads/pic1.jpg"]' // Physically rendering MySQL JSON structures
                ]
            ]);

        // Sequence the PDO prepare statements securely matching the Service logic exactly
        $this->pdoMock->expects($this->exactly(2))
            ->method('prepare')
            ->willReturnOnConsecutiveCalls($stmtMock1, $stmtMock2);

        $result = $this->dashpointService->getDashpointDetails($dashpointId);

        // Core assertions confirming the Payload array builds natively
        $this->assertNotNull($result);
        $this->assertEquals($dashpointId, $result['id']);
        $this->assertEquals(39.8283, $result['lat']);
        $this->assertCount(1, $result['visits']);
        $this->assertEquals('LucienDashes', $result['visits'][0]['username']);

        // Ensure the JSON parser successfully mapped the raw string back into a PHP Array natively
        $this->assertIsArray($result['visits'][0]['photos']);
        $this->assertEquals('/uploads/pic1.jpg', $result['visits'][0]['photos'][0]);
    }

    public function testGetDashpointDetailsNotFound()
    {
        $dashpointId = 'GD001-GHOS';

        $stmtMock1 = $this->createMock(PDOStatement::class);
        $stmtMock1->expects($this->once())
            ->method('execute')
            ->willReturn(true);

        // Simulating the PDO engine returning `false` natively when a Dashpoint lacks physical mapping
        $stmtMock1->expects($this->once())
            ->method('fetch')
            ->willReturn(false);

        $this->pdoMock->expects($this->once())
            ->method('prepare')
            ->willReturn($stmtMock1);

        $result = $this->dashpointService->getDashpointDetails($dashpointId);

        $this->assertNull($result);
    }
}
