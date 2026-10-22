<?php

/**
 * Public Sitemap Endpoint
 * Outputs dynamic XML Sitemap representing the Geodashing V2 site state.
 */

declare(strict_types=1);

use App\Services\SitemapService;

if (basename(__FILE__) === basename($_SERVER['PHP_SELF'] ?? '')) {
    require_once __DIR__ . '/../../vendor/autoload.php';
    require_once __DIR__ . '/../../backend/Database.php';

    // Set headers for valid XML search engine reading
    header('Content-Type: application/xml; charset=utf-8');

    try {
        $db = \App\Database::getConnection();

        $isHttps = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off')
            || (($_SERVER['SERVER_PORT'] ?? null) == 443);
        $protocol = $isHttps ? "https://" : "http://";
        $rawHost = (string) ($_SERVER['HTTP_HOST'] ?? 'www.geodashing.org');
        $host = preg_match('/^[a-zA-Z0-9.-]+(?::\d+)?$/', $rawHost) === 1
            ? $rawHost
            : 'www.geodashing.org';
        $baseUrl = $protocol . $host;

        $service = new SitemapService($db, $baseUrl);
        echo $service->generateSitemapXml();
    } catch (Exception $e) {
        error_log("Sitemap Generation Error: " . $e->getMessage());
        http_response_code(500);

        // Output a minimal, valid XML structure in case of failure
        echo '<?xml version="1.0" encoding="UTF-8"?>'
            . '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>';
    }
}
