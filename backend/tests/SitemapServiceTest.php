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
        $stmtMock = $this->createMock(PDOStatement::class);
        $stmtMock->expects($this->once())->method('execute')->willReturn(true);
        $stmtMock->method('fetchAll')->willReturn(['GD001-AAAA']);

        $this->pdoMock->expects($this->once())
            ->method('prepare')
            ->willReturn($stmtMock);

        $xml = $this->sitemapService->generateSitemapXml();

        // Validate raw structure
        $this->assertStringContainsString('<?xml version="1.0" encoding="UTF-8"?>', $xml);
        $this->assertStringContainsString('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">', $xml);
        
        // Validate core root
        $this->assertStringContainsString('<loc>http://test.local/</loc>', $xml);
        
        // Validate dynamic injection
        $this->assertStringContainsString('<loc>http://test.local/?dashpoint=GD001-AAAA</loc>', $xml);
        
        // Ensure valid XML parse
        $dom = new \DOMDocument();
        $this->assertTrue($dom->loadXML($xml));
    }
}
