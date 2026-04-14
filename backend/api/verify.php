<?php

/**
 * Email Verification Endpoint
 *
 * Intercepts the GET payload shipped via the PHP mail() engine.
 */

declare(strict_types=1);

use App\Services\AuthService;

require_once __DIR__ . '/../session.php';
require_once __DIR__ . '/../../vendor/autoload.php';
require_once __DIR__ . '/../Database.php';

$token = $_GET['token'] ?? '';

if (empty($token)) {
    // Graceful routing logic natively dumping bad actors
    header("Location: ../../index.html#home");
    exit;
}

try {
    $db = \App\Database::getConnection();
    $authService = new AuthService($db);

    $result = $authService->verifyEmail($token);

    if ($result['status'] === 'success') {
        // Mark the user as logged in.
        session_regenerate_id(true);
        $_SESSION['user_id'] = $result['user_id'];
        $_SESSION['is_verified'] = 1;

        // Redirect with success anchor
        header("Location: ../../index.html#login?verified=true");
        exit;
    } else {
        // Token invalid or already consumed
        header("Location: ../../index.html#login?error=invalid_token");
        exit;
    }
} catch (Exception $e) {
    error_log("Verification Endpoint Failure: " . $e->getMessage());
    header("Location: ../../index.html#home");
    exit;
}
