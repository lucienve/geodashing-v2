<?php

/**
 * Playwright E2E Testing Router
 * 
 * This router is ONLY used by the local PHP development server (`php -S`) during E2E testing.
 * It intercepts static file requests, injects the security headers that are normally 
 * set by Apache in `public/.htaccess`, and serves the file contents.
 * 
 * This ensures that Lighthouse audits run via Playwright see the correct production-parity 
 * security headers and pass successfully.
 */

$path = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
if ($path === '/') {
    $path = '/index.html';
}

$absolutePath = __DIR__ . '/../public' . $path;

if (file_exists($absolutePath) && !is_dir($absolutePath)) {
    // Determine the correct MIME type
    $ext = pathinfo($absolutePath, PATHINFO_EXTENSION);
    
    // If it's a PHP file, let the built-in server handle it
    if (strtolower($ext) === 'php') {
        return false;
    }

    $mimes = [
        'html' => 'text/html',
        'css'  => 'text/css',
        'js'   => 'application/javascript',
        'png'  => 'image/png',
        'ico'  => 'image/x-icon',
        'json' => 'application/json',
        'webmanifest' => 'application/manifest+json',
        'svg'  => 'image/svg+xml'
    ];
    $mime = $mimes[$ext] ?? mime_content_type($absolutePath);
    if ($mime) {
        header("Content-Type: $mime");
    }
    
    // Inject Production-Parity Security Headers
    header('X-Content-Type-Options: nosniff');
    header('X-Frame-Options: SAMEORIGIN');
    header('Strict-Transport-Security: max-age=2592000');
    header('Cross-Origin-Opener-Policy: same-origin-allow-popups');
    header("Content-Security-Policy: frame-ancestors 'self';");
    
    // Output the static file
    readfile($absolutePath);
    return true; // Tells PHP built-in server we handled it
}

// Return false so PHP built-in server handles API scripts
return false;
