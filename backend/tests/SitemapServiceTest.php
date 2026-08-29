<?php

/**
 * Sitemap Service Unit Tests
 */

declare(strict_types=1);

namespace App\Tests;

use PHPUnit\Framework\TestCase;
use PHPUnit\Framework\Attributes\Test;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\Attributes\AllowMockObjectsWithoutExpectations;
use App\Services\SitemapService;
use PDO;
use PDOStatement;

#[CoversClass(SitemapService::class)]
#[AllowMockObjectsWithoutExpectations]
class SitemapServiceTest extends TestCase
{
    private $pdoMock;
    private $sitemapService;

    protected function setUp(): void
    {
        $this->pdoMock = $this->createMock(PDO::class);
        $this->sitemapService = new SitemapService($this->pdoMock, "http://test.local");
    }

    #[Test]
    public function testGetLoggedDashpointIdsReturnsOnlyApprovedVisits(): void
    {
        $stmtMock = $this->createMock(PDOStatement::class);
        $stmtMock->expects($this->once())->method('execute')->willReturn(true);
        $stmtMock->method('fetchAll')->willReturn(['GD001-AAAA']);

        $this->pdoMock->expects($this->once())
            ->method('prepare')
            ->willReturn($stmtMock);

        $dashpoints = $this->sitemapService->getLoggedDashpointIds();

        $this->assertCount(1, $dashpoints);
        $this->assertEquals('GD001-AAAA', $dashpoints[0]);
    }

    #[Test]
    public function testGenerateSitemapXmlOutputsValidXmlStructure(): void
    {
        $stmtMock1 = $this->createMock(PDOStatement::class);
        $stmtMock1->expects($this->once())->method('execute')->willReturn(true);
        $stmtMock1->method('fetchAll')->willReturn(['GD001-AAAA']);

        $stmtMock2 = $this->createMock(PDOStatement::class);
        $stmtMock2->expects($this->once())->method('execute')->willReturn(true);
        $stmtMock2->method('fetchAll')->willReturn([15]);

        $this->pdoMock->expects($this->exactly(2))
            ->method('prepare')
            ->willReturnOnConsecutiveCalls($stmtMock1, $stmtMock2);

        $xml = $this->sitemapService->generateSitemapXml();

        // Validate raw structure
        $this->assertStringContainsString('<?xml version="1.0" encoding="UTF-8"?>', $xml);
        $this->assertStringContainsString('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">', $xml);

        // Validate core root
        $this->assertStringContainsString('<loc>http://test.local/</loc>', $xml);

        // Validate static help pages
        $this->assertStringContainsString('<loc>http://test.local/?page=about</loc>', $xml);
        $this->assertStringContainsString('<loc>http://test.local/?page=how-to</loc>', $xml);
        $this->assertStringContainsString('<loc>http://test.local/?page=contact</loc>', $xml);

        // Validate dynamic injection
        $this->assertStringContainsString('<loc>http://test.local/?dashpoint=GD001-AAAA</loc>', $xml);
        $this->assertStringContainsString('<loc>http://test.local/?summary=15</loc>', $xml);

        // Ensure valid XML parse
        $dom = new \DOMDocument();
        $this->assertTrue($dom->loadXML($xml));
    }

    #[Test]
    public function testGetGamesWithSummariesReturnsIds(): void
    {
        $stmtMock = $this->createMock(PDOStatement::class);
        $stmtMock->expects($this->once())->method('execute')->willReturn(true);
        $stmtMock->method('fetchAll')->willReturn([15, 12]);

        $this->pdoMock->expects($this->once())
            ->method('prepare')
            ->with($this->stringContains("summary IS NOT NULL AND summary != ''"))
            ->willReturn($stmtMock);

        $result = $this->sitemapService->getGamesWithSummaries();

        $this->assertCount(2, $result);
        $this->assertEquals(15, $result[0]);
        $this->assertEquals(12, $result[1]);
    }

    #[Test]
    public function testGenerateSitemapXmlDoesNotDoubleEscapeUrls(): void
    {
        $stmtMock1 = $this->createMock(PDOStatement::class);
        $stmtMock1->method('fetchAll')->willReturn([]);

        $stmtMock2 = $this->createMock(PDOStatement::class);
        $stmtMock2->method('fetchAll')->willReturn([]);

        $this->pdoMock->method('prepare')
            ->willReturnOnConsecutiveCalls($stmtMock1, $stmtMock2);

        $customSitemapService = new SitemapService($this->pdoMock, "http://test.local?page=main&version=2");
        $xml = $customSitemapService->generateSitemapXml();

        // Valid XML encoding produces &amp; and must not produce &amp;amp;
        $this->assertStringContainsString('<loc>http://test.local?page=main&amp;version=2/</loc>', $xml);
        $this->assertStringNotContainsString('&amp;amp;', $xml);
    }
}
