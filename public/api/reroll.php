<?php

/**
 * Dashpoint Reroll API Endpoint
 *
 * Handles HTTP requests to relocate a dashpoint during the game preview phase.
 *
 * @package Geodashing\API
 */

declare(strict_types=1);

use App\Services\RerollService;

if (basename(__FILE__) === basename($_SERVER['PHP_SELF'] ?? '')) {
    require_once __DIR__ . '/../../vendor/autoload.php';
    require_once __DIR__ . '/../../backend/session.php';
    header('Content-Type: application/json');
    require_once __DIR__ . '/../../backend/Database.php';

    if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
        http_response_code(405);
        echo json_encode(["status" => "error", "message" => "Method not allowed"]);
        exit;
    }

    if (!isset($_SESSION['user_id'])) {
        http_response_code(401);
        echo json_encode(["status" => "error", "message" => "Unauthorized access. Please log in."]);
        exit;
    }

    $dashpointId = trim($_POST['dashpoint_id'] ?? '');
    $reason = trim($_POST['reason'] ?? '');
    $reason = $reason !== '' ? $reason : null;

    if (empty($dashpointId)) {
        http_response_code(400);
        echo json_encode(["status" => "error", "message" => "Dashpoint ID is required"]);
        exit;
    }

    try {
        $db = \App\Database::getConnection();
        $rerollService = new RerollService($db);
        $result = $rerollService->rerollDashpoint((int) $_SESSION['user_id'], $dashpointId, $reason);
        echo json_encode($result);
    } catch (Exception $e) {
        http_response_code(400);
        echo json_encode(["status" => "error", "message" => $e->getMessage()]);
    }
}
