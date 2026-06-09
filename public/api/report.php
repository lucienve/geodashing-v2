<?php

/**
 * Reporting API Endpoint
 *
 * Processes spatial dashpoint claims by evaluating the user's submitted physical
 * coordinates against the Dashpoint's master coordinates.
 *
 * @package Geodashing\API
 */

declare(strict_types=1);

// If we are executing this file directly (not importing it for testing)
use App\Services\MediaService;
use App\Services\ReportService;

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
    // Validating against the frontend `name="lat"` and `name="lon"` constraints.
    $lat = filter_var($_POST['lat'] ?? '', FILTER_VALIDATE_FLOAT);
    $lon = filter_var($_POST['lon'] ?? '', FILTER_VALIDATE_FLOAT);
    $notes = trim($_POST['notes'] ?? '');

    // Phase 5 Validation: Strict Field Log Text Constraints
    if (empty($notes) || strlen($notes) > 10000) {
        http_response_code(400);
        echo json_encode(["status" => "error", "message" => "Field observations are mandatory and must not exceed 10,000 characters."]);
        exit;
    }
    $photosJson = null;

    // 2.5 Optional Media Processing Pipeline
    if (!empty($_FILES['photos']) && (is_array($_FILES['photos']['error']) ? $_FILES['photos']['error'][0] : $_FILES['photos']['error']) !== UPLOAD_ERR_NO_FILE) {
        $configPath = __DIR__ . '/../../backend/config.ini';
        $config = file_exists($configPath) ? parse_ini_file($configPath) : [];
        $keyPath = $config['GOOGLE_APPLICATION_CREDENTIALS'] ?? getenv('GOOGLE_APPLICATION_CREDENTIALS');
        $isTesting = getenv('APP_ENV') === 'testing';

        if (!$isTesting && (!$keyPath || !file_exists($keyPath))) {
            http_response_code(500);
            echo json_encode(["status" => "error", "message" => "Server configuration error blocking media uploads."]);
            exit;
        }

        try {
            // Instantiate securely with user's explicitly provided Geodashing GCP identifiers
            $mediaService = new MediaService('geodashing-v2', 'geodashing-v2-blobs', $isTesting ? null : $keyPath);
            $captions = $_POST['captions'] ?? [];
            if (!is_array($captions)) {
                $captions = [];
            }
            $urls = $mediaService->uploadPhotos($_FILES['photos'], $dashpoint_id, $_SESSION['user_id'], $captions);
            if (!empty($urls)) {
                $photosJson = json_encode($urls);
            }
        } catch (Exception $e) {
            error_log("GCP Upload Error: " . $e->getMessage());
            http_response_code(400);
            echo json_encode(["status" => "error", "message" => "Image upload failed: " . $e->getMessage()]);
            exit;
        }
    }

    if (empty($dashpoint_id) || $lat === false || $lon === false) {
        http_response_code(400);
        echo json_encode(["status" => "error", "message" => "Invalid or missing required location data."]);
        exit;
    }

    try {
        $db = \App\Database::getConnection();
        $service = new ReportService($db);
        $is_attempt = filter_var($_POST['is_attempt'] ?? false, FILTER_VALIDATE_BOOLEAN);
        $suppress_email = filter_var($_POST['suppress_email'] ?? false, FILTER_VALIDATE_BOOLEAN);
        $result = $service->processVisit($_SESSION['user_id'], $dashpoint_id, $lat, $lon, $is_attempt, $notes, $photosJson, $suppress_email);

        if ($result['status'] === 'error') {
            http_response_code(400);
        }
        echo json_encode($result);
    } catch (Exception $e) {
        error_log("Report API Error: " . $e->getMessage());
        http_response_code(500);
        echo json_encode(["status" => "error", "message" => "Failed to log visit due to internal server error."]);
    }
}
