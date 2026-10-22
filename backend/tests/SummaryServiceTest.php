<?php

declare(strict_types=1);

namespace App\Tests;

use App\Services\SummaryService;
use PDO;
use PDOStatement;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\Attributes\Test;
use PHPUnit\Framework\MockObject\MockObject;
use PHPUnit\Framework\TestCase;

/**
 * SummaryServiceTest
 *
 * Verifies SummaryService game summary HTML retrieval.
 */
#[CoversClass(SummaryService::class)]
class SummaryServiceTest extends TestCase
{
    /**
     * @var PDO&MockObject
     */
    private PDO $pdoMock;

    /**
     * @var SummaryService
     */
    private SummaryService $summaryService;

    /**
     * Sets up the test fixtures.
     */
    #[\Override]
    protected function setUp(): void
    {
        $this->pdoMock = $this->createMock(PDO::class);
        $this->summaryService = new SummaryService($this->pdoMock);
    }

    #[Test]
    public function getSummaryReturnsHtmlStringWhenExists(): void
    {
        $stmtMock = $this->createMock(PDOStatement::class);
        $stmtMock->expects($this->once())
            ->method('execute')
            ->with([15])
            ->willReturn(true);
        $stmtMock->expects($this->once())
            ->method('fetchColumn')
            ->willReturn("<p>Summary text</p>");

        $this->pdoMock->expects($this->once())
            ->method('prepare')
            ->with($this->stringContains("SELECT summary FROM games WHERE id = ?"))
            ->willReturn($stmtMock);

        $result = $this->summaryService->getSummary(15);
        $this->assertEquals("<p>Summary text</p>", $result);
    }

    #[Test]
    public function getSummaryReturnsNullWhenNotExists(): void
    {
        $stmtMock = $this->createMock(PDOStatement::class);
        $stmtMock->expects($this->once())
            ->method('execute')
            ->with([999])
            ->willReturn(true);
        $stmtMock->expects($this->once())
            ->method('fetchColumn')
            ->willReturn(false);

        $this->pdoMock->expects($this->once())
            ->method('prepare')
            ->with($this->stringContains("SELECT summary FROM games WHERE id = ?"))
            ->willReturn($stmtMock);

        $result = $this->summaryService->getSummary(999);
        $this->assertNull($result);
    }
}
