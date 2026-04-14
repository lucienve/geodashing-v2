<?php

declare(strict_types=1);

/**
 * Dashpoint Historical Details Endpoint
 *
 * Retrieves the explicit coordinates for a single Dashpoint and mathematically joins
 * all historically recorded Finders out of the `visits` and `users` table.
 */

use App\Services\DashpointService;

if (basename(__FILE__) === basename($_SERVER['PHP_SELF'] ?? '')) {
    require_once __DIR__ . '/../../vendor/autoload.php';
    header('Content-Type: application/json');

    $id = $_GET['id'] ?? null;

    if (!$id) {
        http_response_code(400);
        echo json_encode(["status" => "error", "message" => "Dashpoint ID is missing."]);
        exit;
    }

    try {
        $service = new DashpointService();
        $data = $service->getDashpointDetails($id);

        if (!$data) {
            http_response_code(404);
            echo json_encode(["status" => "error", "message" => "Dashpoint not found."]);
            exit;
        }

        echo json_encode([
        "status" => "success",
        "data" => $data
        ]);
    } catch (Exception $e) {
        error_log("Dashpoint API Error: " . $e->getMessage());
        http_response_code(500);
        echo json_encode(["status" => "error", "message" => "Database connection failed."]);
    }
}
