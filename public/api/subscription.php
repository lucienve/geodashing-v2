<?php

/**
 * Subscription API Endpoint
 *
 * Allows authenticated, verified players to manage their subscription
 * to the dashers@geodashing.org Google Group mailing list.
 *
 * @package Geodashing\API
 */

declare(strict_types=1);

require_once __DIR__ . '/../../backend/session.php';
require_once __DIR__ . '/../../vendor/autoload.php';
require_once __DIR__ . '/../../backend/Database.php';

use App\Services\GoogleGroupService;

if (basename(__FILE__) === basename($_SERVER['PHP_SELF'] ?? '')) {
    header('Content-Type: application/json');

    if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
        http_response_code(405);
        echo json_encode([
            "status" => "error",
            "message" => "Method not allowed. POST required."
        ]);
        exit;
    }

    if (empty($_SESSION['user_id']) || empty($_SESSION['is_verified'])) {
        http_response_code(401);
        echo json_encode([
            "status" => "error",
            "message" => "Authentication required. You must be logged in with a verified account."
        ]);
        exit;
    }

    $rawInput = file_get_contents('php://input');
    $input = json_decode($rawInput, true);

    if (!is_array($input) || !array_key_exists('subscribe', $input)) {
        http_response_code(400);
        echo json_encode([
            "status" => "error",
            "message" => "Invalid request payload. The 'subscribe' boolean parameter is required."
        ]);
        exit;
    }

    $subscribe = (bool) $input['subscribe'];

    try {
        $db = \App\Database::getConnection();
        $stmt = $db->prepare("SELECT id, username, email, subscribe_group FROM users WHERE id = :id LIMIT 1");
        $stmt->execute([':id' => (int) $_SESSION['user_id']]);
        $user = $stmt->fetch(PDO::FETCH_ASSOC);

        if (!$user) {
            http_response_code(404);
            echo json_encode([
                "status" => "error",
                "message" => "User account not found."
            ]);
            exit;
        }

        $groupService = new GoogleGroupService();

        if ($subscribe) {
            $apiSuccess = $groupService->addMember($user['email']);
        } else {
            $apiSuccess = $groupService->removeMember($user['email']);
        }

        if (!$apiSuccess) {
            http_response_code(502);
            echo json_encode([
                "status" => "error",
                "message" => "Failed to update mailing list subscription via Google Groups. Please try again."
            ]);
            exit;
        }

        // Commit database preference update strictly after external Google API call succeeded
        $updateStmt = $db->prepare("UPDATE users SET subscribe_group = :sub WHERE id = :id");
        $updateStmt->execute([
            ':sub' => $subscribe ? 1 : 0,
            ':id' => $user['id']
        ]);

        echo json_encode([
            "status" => "success",
            "subscribe_group" => $subscribe ? 1 : 0,
            "message" => $subscribe
                ? "Subscribed to dashers@geodashing.org."
                : "Unsubscribed from dashers@geodashing.org."
        ]);
    } catch (Throwable $e) {
        error_log("Subscription API Error: " . $e->getMessage());
        http_response_code(500);
        echo json_encode([
            "status" => "error",
            "message" => "An internal server error occurred while updating your subscription preference."
        ]);
    }
}
