<?php

/**
 * Sitemap Service
 *
 * Generates dynamic XML sitemaps exposing explicitly logged Dashpoints
 * to Search Engine bots using the SEO-friendly Query Parameter fallback schema.
 */

declare(strict_types=1);

namespace App\Services;

use PDO;
use Exception;

class SitemapService
{
    private PDO $pdo;
    private string $baseUrl;

    public function __construct(PDO $pdo, string $baseUrl = "https://www.geodashing.org")
    {
        $this->pdo = $pdo;
        $this->baseUrl = $baseUrl;
    }

    /**
     * Generates a fully formatted XML Sitemap string.
     * Includes static core pages and dynamic Dashpoint pages that have been logged.
     *
     * @return string Raw XML Sitemap
     */
    public function generateSitemapXml(): string
    {
        $xml = new \XMLWriter();
        $xml->openMemory();
        $xml->setIndent(true);
        $xml->startDocument('1.0', 'UTF-8');
        $xml->startElement('urlset');
        $xml->writeAttribute('xmlns', 'http://www.sitemaps.org/schemas/sitemap/0.9');

        // Add core static application views
        $this->addStaticUrls($xml);

        // Fetch and add logged Dashpoints dynamically
        $dashpoints = $this->getLoggedDashpointIds();
        foreach ($dashpoints as $dpId) {
            $this->addUrl($xml, $this->baseUrl . "/?dashpoint=" . urlencode($dpId), 'weekly', '0.6');
        }

        $xml->endElement(); // urlset
        $xml->endDocument();

        return $xml->outputMemory();
    }

    /**
     * Internal helper to register the primary Single Page App views.
     */
    private function addStaticUrls(\XMLWriter $xml): void
    {
        // Core roots
        $this->addUrl($xml, $this->baseUrl . "/", 'daily', '1.0');

        // Deep link equivalents for indexing the SPA states if Googlebot follows them
        // Note: To Googlebot these are query params, but we route them via hash natively.
        // We only explicitly output the query param fallback links to guarantee indexing.
        $this->addUrl($xml, $this->baseUrl . "/?page=about", 'monthly', '0.8');
        $this->addUrl($xml, $this->baseUrl . "/?page=how-to", 'monthly', '0.8');
        $this->addUrl($xml, $this->baseUrl . "/?page=contact", 'monthly', '0.5');
    }

    /**
     * Injects a standard <url> block into the XML tree.
     */
    private function addUrl(\XMLWriter $xml, string $loc, string $changefreq, string $priority): void
    {
        $xml->startElement('url');
        $xml->writeElement('loc', htmlspecialchars($loc, ENT_XML1, 'UTF-8'));
        $xml->writeElement('changefreq', $changefreq);
        $xml->writeElement('priority', $priority);
        $xml->endElement();
    }

    /**
     * Retrieves all Dashpoint IDs that have at least one approved visit log.
     */
    public function getLoggedDashpointIds(): array
    {
        $stmt = $this->pdo->prepare("
            SELECT DISTINCT d.id 
            FROM dashpoints d
            INNER JOIN visits v ON d.id = v.dashpoint_id
            WHERE v.status = 'approved'
            ORDER BY d.id DESC
        ");
        $stmt->execute();

        return $stmt->fetchAll(PDO::FETCH_COLUMN);
    }
}
