<?php

/**
 * Global Session and Security Bootstrapper
 */

declare(strict_types=1);

// 1. Enforce strict session cookie parameters
session_set_cookie_params([
    'lifetime' => 86400 * 30, // 30 days
    'path' => '/',
    'secure' => isset($_SERVER['HTTPS']) && $_SERVER['HTTPS'] === 'on', // Require HTTPS if available
    'httponly' => true,
    'samesite' => 'Strict'
]);

// 2. HTTP Defense-in-Depth Headers
header('X-Content-Type-Options: nosniff');
header('X-Frame-Options: DENY');
// Note: We omit CSP because Google Maps dynamically injects complex inline styles and cross-domain iframes that break easily under strict rules.

// 3. Boot session
session_start();

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
