<?php
/**
 * Dashpoint Historical Details Endpoint
 *
 * Retrieves the explicit coordinates for a single Dashpoint and mathematically joins 
 * all historically recorded Finders out of the `visits` and `users` table.
 */

header('Content-Type: application/json');

require_once __DIR__ . '/../services/DashpointService.php';

$id = $_GET['id'] ?? null;

if (!$id) {
    http_response_code(400);
    echo json_encode(["status" => "error", "message" => "Dashpoint ID completely missing."]);
    exit;
}

try {
    $service = new DashpointService();
    $data = $service->getDashpointDetails($id);

    if (!$data) {
        http_response_code(404);
        echo json_encode(["status" => "error", "message" => "Dashpoint matrix unmapped or deleted."]);
        exit;
    }

    echo json_encode([
        "status" => "success",
        "data" => $data
    ]);

} catch (Exception $e) {
    error_log("Dashpoint Fetch RUPTURE: " . $e->getMessage());
    http_response_code(500);
    echo json_encode(["status" => "error", "message" => "Database link severed completely."]);
}
