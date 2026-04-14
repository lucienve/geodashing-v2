<?php

/**
 * Authentication API Endpoint
 *
 * Processes JSON user signups, logins, and logouts.
 *
 * @package Geodashing\API
 */

declare(strict_types=1);

use App\Services\AuthService;

// Bypass procedural logic during PHPUnit inclusion
if (basename(__FILE__) === basename($_SERVER['PHP_SELF'] ?? '')) {
    require_once __DIR__ . '/../../vendor/autoload.php';
    require_once __DIR__ . '/../session.php';
    header('Content-Type: application/json');
    require_once __DIR__ . '/../Database.php';

    $action = $_GET['action'] ?? '';

    // Enforce POST
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
        http_response_code(405);
        echo json_encode(["status" => "error", "message" => "Method not allowed"]);
        exit;
    }

    try {
        $db = \App\Database::getConnection();
        $authService = new AuthService($db);

        if ($action === 'signup') {
            $username = trim($_POST['username'] ?? '');
            $email = trim($_POST['email'] ?? '');
            $password = $_POST['password'] ?? '';

            $result = $authService->signup($username, $email, $password);

            // Auto sign-in
            if ($result['status'] === 'success') {
                session_regenerate_id(true);
                $_SESSION['user_id'] = $result['user_id'];
                $_SESSION['username'] = $result['username'];
                $_SESSION['is_verified'] = $result['is_verified'];
                // Clean the raw database keys out of the JSON response payload
                unset($result['user_id'], $result['username'], $result['is_verified']);
            } else {
                http_response_code(400);
            }
            echo json_encode($result);
        } elseif ($action === 'login') {
            $username = trim($_POST['username'] ?? '');
            $password = $_POST['password'] ?? '';

            $result = $authService->login($username, $password);

            if ($result['status'] === 'success') {
                session_regenerate_id(true);
                $_SESSION['user_id'] = $result['user_id'];
                $_SESSION['username'] = $result['username'];
                $_SESSION['is_verified'] = $result['is_verified'];
                unset($result['user_id'], $result['username'], $result['is_verified']);
            } else {
                http_response_code(401);
            }
            echo json_encode($result);
        } elseif ($action === 'logout') {
            session_unset();
            session_destroy();
            echo json_encode(["status" => "success", "message" => "Logged out successfully"]);
        } elseif ($action === 'resend_verification') {
            // Securely demand a populated active session dynamically preventing spam hooks
            if (!isset($_SESSION['user_id'])) {
                http_response_code(401);
                echo json_encode(["status" => "error", "message" => "Unauthorized access."]);
                exit;
            }

            // Check if they are already formally verified preventing mail relays
            if (isset($_SESSION['is_verified']) && $_SESSION['is_verified']) {
                echo json_encode(["status" => "error", "message" => "Account is already verified."]);
                exit;
            }

            // Ping the AuthService to fire the relay
            $result = $authService->resendVerification((int) $_SESSION['user_id']);
            if ($result['status'] !== 'success') {
                http_response_code(500);
            }
            echo json_encode($result);
        } elseif ($action === 'forgot_password') {
            $username = trim($_POST['username'] ?? '');
            if (empty($username)) {
                http_response_code(400);
                echo json_encode(["status" => "error", "message" => "Username is required"]);
                exit;
            }
            $result = $authService->forgotPassword($username);
            if ($result['status'] !== 'success') {
                http_response_code(400);
            }
            echo json_encode($result);
        } elseif ($action === 'reset_password') {
            $token = trim($_POST['token'] ?? '');
            $password = $_POST['password'] ?? '';
            if (empty($token) || empty($password)) {
                http_response_code(400);
                echo json_encode(["status" => "error", "message" => "Token and new password required"]);
                exit;
            }
            $result = $authService->resetPassword($token, $password);
            if ($result['status'] !== 'success') {
                http_response_code(400);
            }
            echo json_encode($result);
        } elseif ($action === 'session') {
            // Native session state retrieval explicitly mapping memory back to the SPA
            if (isset($_SESSION['user_id']) && isset($_SESSION['username'])) {
                echo json_encode([
                    "status" => "success",
                    "user_id" => $_SESSION['user_id'],
                    "username" => $_SESSION['username'],
                    "is_verified" => $_SESSION['is_verified'] ?? 0
                ]);
            } else {
                http_response_code(401);
                echo json_encode(["status" => "error", "message" => "No active session"]);
            }
        } else {
            http_response_code(400);
            echo json_encode(["status" => "error", "message" => "Invalid action specified."]);
        }
    } catch (Exception $e) {
        error_log("Auth API Error: " . $e->getMessage());
        http_response_code(500);
        echo json_encode(["status" => "error", "message" => "Internal server error"]);
    }
}
