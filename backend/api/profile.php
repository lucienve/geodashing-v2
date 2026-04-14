<?php

/**
 * Profile API Endpoint
 *
 * Retrieves historical metrics for a specific user.
 */

declare(strict_types=1);

require_once __DIR__ . '/../../vendor/autoload.php';
require_once __DIR__ . '/../Database.php';

use App\Services\ProfileService;

if (basename(__FILE__) === basename($_SERVER['PHP_SELF'] ?? '')) {
    header('Content-Type: application/json');

    $userId = filter_var($_GET['id'] ?? null, FILTER_VALIDATE_INT);

    if (!$userId) {
        http_response_code(400);
        echo json_encode(["status" => "error", "message" => "Valid User ID required."]);
        exit;
    }

    try {
        $db = \App\Database::getConnection();
        $service = new ProfileService($db);
        $data = $service->getProfileSettings($userId);

        if (!$data) {
            http_response_code(404);
            echo json_encode(["status" => "error", "message" => "User not found."]);
            exit;
        }

        echo json_encode([
            "status" => "success",
            "data" => $data
        ]);
    } catch (Exception $e) {
        error_log("Profile API Error: " . $e->getMessage());
        http_response_code(500);
        echo json_encode(["status" => "error", "message" => "Database connection failed."]);
    }
}
