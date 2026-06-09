<?php

/**
 * Post-Log Editing API Endpoint
 *
 * Allows authenticated users to safely modify their Field Notes or append/delete
 * physical tracking photos without triggering or modifying the 100m Geolocation
 * bounds locked during the initial claim.
 *
 * @package Geodashing\API
 */

declare(strict_types=1);

use App\Services\EditService;
use App\Services\MediaService;

// Native Execution Gateway
if (basename(__FILE__) === basename($_SERVER['PHP_SELF'] ?? '')) {
    require_once __DIR__ . '/../../vendor/autoload.php';
    require_once __DIR__ . '/../../backend/session.php';
    header('Content-Type: application/json');
    require_once __DIR__ . '/../../backend/Database.php';

    // 1. Strict Authentication Boundary
    if (!isset($_SESSION['user_id'])) {
        http_response_code(401);
        echo json_encode(["status" => "error", "message" => "Unauthorized. Please log in first."]);
        exit;
    }

    if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
        http_response_code(405);
        echo json_encode(["status" => "error", "message" => "Method not allowed"]);
        exit;
    }

    // 2. Input Sanitization
    $dashpoint_id = $_POST['dashpoint_id'] ?? '';
    $notes = trim($_POST['notes'] ?? '');

    // `kept_photos` arrives as a strict JSON string array of public URLs the user explicitly chose NOT to click [X] on
    $keptPhotosRaw = $_POST['kept_photos'] ?? '[]';
    $keptPhotos = json_decode($keptPhotosRaw, true);
    if (!is_array($keptPhotos)) {
        $keptPhotos = [];
    }

    $sendEmail = isset($_POST['send_email']) && $_POST['send_email'] === '1';

    // Validate Log Narrative Boundaries
    if (empty($notes) || strlen($notes) > 10000) {
        http_response_code(400);
        echo json_encode(["status" => "error", "message" => "Field observations are mandatory and must not exceed 10,000 characters."]);
        exit;
    }

    if (empty($dashpoint_id)) {
        http_response_code(400);
        echo json_encode(["status" => "error", "message" => "Invalid target tracking configuration."]);
        exit;
    }

    try {
        $db = \App\Database::getConnection();
        $configPath = __DIR__ . '/../../backend/config.ini';
        $config = file_exists($configPath) ? parse_ini_file($configPath) : [];
        $keyPath = $config['GOOGLE_APPLICATION_CREDENTIALS'] ?? getenv('GOOGLE_APPLICATION_CREDENTIALS');

        $mediaService = null;
        if ($keyPath && file_exists($keyPath)) {
            $mediaService = new MediaService('geodashing-v2', 'geodashing-v2-blobs', $keyPath);
        }

        $newCaptions = $_POST['new_captions'] ?? [];
        if (!is_array($newCaptions)) {
            $newCaptions = [];
        }

        $editService = new EditService($db, $mediaService);
        $result = $editService->processEdit($_SESSION['user_id'], $dashpoint_id, $notes, $keptPhotosRaw, $_FILES['photos'] ?? null, $sendEmail, $newCaptions);

        if ($result['status'] === 'success') {
            echo json_encode($result);
        } else {
            http_response_code(isset($result['code']) ? $result['code'] : 400);
            echo json_encode($result);
        }
    } catch (Exception $e) {
        error_log("Edit API Error: " . $e->getMessage());
        http_response_code(500);
        echo json_encode(["status" => "error", "message" => "Failed to update dashpoint log."]);
    }
}
