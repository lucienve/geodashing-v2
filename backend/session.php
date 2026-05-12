<?php

/**
 * Global Session and Security Bootstrapper
 */

declare(strict_types=1);

// 1. Enforce strict session cookie parameters
ini_set('session.gc_maxlifetime', (string)(86400 * 30)); // 30 days garbage collection
session_set_cookie_params([
    'lifetime' => 86400 * 30, // 30 days
    'path' => '/',
    'secure' => isset($_SERVER['HTTPS']) && $_SERVER['HTTPS'] === 'on', // Require HTTPS if available
    'httponly' => true,
    'samesite' => 'Strict'
]);

// 2. HTTP Defense-in-Depth Headers
header('X-Content-Type-Options: nosniff');
header('X-Frame-Options: SAMEORIGIN');
header('Strict-Transport-Security: max-age=2592000');
header('Cross-Origin-Opener-Policy: same-origin-allow-popups');
header("Content-Security-Policy: frame-ancestors 'self';");
// Note: We omit full CSP because Google Maps dynamically injects complex inline styles and cross-domain iframes that break easily under strict rules.

// 3. Configure custom session storage (Bypass Ubuntu cron job)
if ((getenv('APP_ENV') ?: ($_ENV['APP_ENV'] ?? '')) !== 'testing') {
    session_save_path('/var/lib/geodashing_sessions');
    ini_set('session.gc_probability', '1');
    ini_set('session.gc_divisor', '100');
}

// 4. Boot session
session_start();

// Refresh the session cookie lifetime to implement a 30-day rolling window
setcookie(session_name(), session_id(), [
    'expires' => time() + 86400 * 30,
    'path' => '/',
    'secure' => isset($_SERVER['HTTPS']) && $_SERVER['HTTPS'] === 'on',
    'httponly' => true,
    'samesite' => 'Strict'
]);

// Force a session write to update the server-side session file's modification time
// This prevents read-only sessions from being garbage collected after 30 days
$_SESSION['last_activity'] = time();

// 4. CSRF Token Generation
if (empty($_SESSION['csrf_token'])) {
    $_SESSION['csrf_token'] = bin2hex(random_bytes(32));
}

// Write the CSRF Token down into an accessible Javascript cookie (HttpOnly = false)
setcookie('csrf_token', $_SESSION['csrf_token'], [
    'expires' => time() + 86400 * 30,
    'path' => '/',
    'secure' => isset($_SERVER['HTTPS']) && $_SERVER['HTTPS'] === 'on',
    'httponly' => false,
    'samesite' => 'Strict'
]);

// 5. CSRF Token Validation
// We only enforce CSRF checks if the user currently holds an active, authenticated Session Context.
// This allows initial unauthenticated POST operations (like login, signup) to establish state seamlessly.
if ($_SERVER['REQUEST_METHOD'] === 'POST' && !empty($_SESSION['user_id'])) {
    $providedToken = $_SERVER['HTTP_X_CSRF_TOKEN'] ?? '';

    if (empty($providedToken) || !hash_equals($_SESSION['csrf_token'], $providedToken)) {
        header('Content-Type: application/json');
        http_response_code(403);
        echo json_encode([
            "status" => "error",
            "message" => "Security Validation Failed. Invalid or missing CSRF token."
        ]);
        exit;
    }
}
