<?php
/**
 * Email Verification Endpoint
 * 
 * Intercepts the GET payload shipped via the PHP mail() engine.
 */
session_start();
require_once __DIR__ . '/../Database.php';

$token = $_GET['token'] ?? '';

if (empty($token)) {
    // Graceful routing logic natively dumping bad actors
    header("Location: ../../index.html#home");
    exit;
}

try {
    $db = Database::getConnection();

    // Evaluate the physical token strictly matching the Users table
    $stmt = $db->prepare("SELECT id FROM users WHERE verification_token = :token AND is_verified = 0 LIMIT 1");
    $stmt->execute([':token' => $token]);
    $user = $stmt->fetch(PDO::FETCH_ASSOC);

    if ($user) {
        // Formally verify the account and aggressively purge the token array
        $updateStmt = $db->prepare("UPDATE users SET is_verified = 1, verification_token = NULL WHERE id = :id");
        $updateStmt->execute([':id' => $user['id']]);

        // Mark the user as logged in.
        $_SESSION['user_id'] = $user['id'];
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
