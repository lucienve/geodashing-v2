<?php

/**
 * User Tags API Endpoint
 *
 * RESTful endpoint providing player-specific private dashpoint tagging.
 *
 * @package Geodashing\API
 */

declare(strict_types=1);

use App\Services\TagService;

if (basename(__FILE__) === basename($_SERVER['PHP_SELF'] ?? '')) {
    require_once __DIR__ . '/../../vendor/autoload.php';
    require_once __DIR__ . '/../../backend/session.php';
    header('Content-Type: application/json');
    require_once __DIR__ . '/../../backend/Database.php';

    if (!isset($_SESSION['user_id'])) {
        http_response_code(401);
        echo json_encode(["status" => "error", "message" => "Unauthorized access. Please log in."]);
        exit;
    }

    try {
        $db = \App\Database::getConnection();
        $tagService = new TagService($db);

        $currentUsername = $_SESSION['username'] ?? null;
        if (!$tagService->isFeatureEnabledForUser($currentUsername)) {
            http_response_code(403);
            echo json_encode(["status" => "error", "message" => "Tagging feature is currently disabled."]);
            exit;
        }

        $method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
        $userId = (int) $_SESSION['user_id'];

        if ($method === 'GET') {
            session_write_close();

            $gameId = filter_var($_GET['game_id'] ?? null, FILTER_VALIDATE_INT);
            if ($gameId === false || $gameId === null) {
                http_response_code(400);
                echo json_encode(["status" => "error", "message" => "Valid game_id is required."]);
                exit;
            }

            $tags = $tagService->getTagsForUserAndGame($userId, $gameId);
            $etag = TagService::generateETag($tags);

            header('Cache-Control: private, no-cache');
            header('Vary: Cookie');
            header('ETag: ' . $etag);

            $ifNoneMatch = trim($_SERVER['HTTP_IF_NONE_MATCH'] ?? '');
            $clientHash = trim((string) preg_replace('/^W\//', '', $ifNoneMatch), '"');
            $serverHash = trim($etag, '"');

            if ($clientHash !== '' && $clientHash === $serverHash) {
                http_response_code(304);
                exit;
            }

            echo json_encode([
                "status" => "success",
                "tags" => $tags
            ]);
            exit;
        }

        if ($method === 'POST') {
            $body = file_get_contents('php://input');
            $data = json_decode($body, true);
            if (!is_array($data)) {
                $data = $_POST;
            }

            $dashpointId = trim((string) ($data['dashpoint_id'] ?? ''));
            $color = trim((string) ($data['color'] ?? ''));
            $shape = trim((string) ($data['shape'] ?? ''));

            if (empty($dashpointId) || empty($color) || empty($shape)) {
                http_response_code(400);
                echo json_encode(["status" => "error", "message" => "dashpoint_id, color, and shape are required."]);
                exit;
            }

            $result = $tagService->setTag($userId, $dashpointId, $color, $shape);
            echo json_encode([
                "status" => "success",
                "data" => $result
            ]);
            exit;
        }

        if ($method === 'DELETE') {
            $body = file_get_contents('php://input');
            $data = json_decode($body, true) ?: [];
            $dashpointId = trim((string) ($data['dashpoint_id'] ?? ($_GET['dashpoint_id'] ?? '')));

            if (empty($dashpointId)) {
                http_response_code(400);
                echo json_encode(["status" => "error", "message" => "dashpoint_id is required."]);
                exit;
            }

            $tagService->deleteTag($userId, $dashpointId);
            echo json_encode([
                "status" => "success",
                "message" => "Tag removed successfully."
            ]);
            exit;
        }

        http_response_code(405);
        echo json_encode(["status" => "error", "message" => "Method not allowed."]);
    } catch (InvalidArgumentException $e) {
        http_response_code(400);
        echo json_encode(["status" => "error", "message" => $e->getMessage()]);
    } catch (Exception $e) {
        error_log("User Tags API Error: " . $e->getMessage());
        http_response_code(500);
        echo json_encode(["status" => "error", "message" => "Internal server error."]);
    }
}
