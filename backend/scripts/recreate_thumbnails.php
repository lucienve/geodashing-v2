<?php

/**
 * recreate_thumbnails.php
 *
 * One-off script to recreate GCS thumbnails for visits that were uploaded
 * with EXIF Orientation tags prior to the rotation fix.
 */

declare(strict_types=1);

require_once __DIR__ . '/../../vendor/autoload.php';
require_once __DIR__ . '/../Database.php';
require_once __DIR__ . '/../services/MediaService.php';

use App\Database;
use App\Services\MediaService;

try {
    $configPath = __DIR__ . '/../config.ini';
    $config = (file_exists($configPath) && is_readable($configPath))
        ? (parse_ini_file($configPath) ?: [])
        : [];
    $keyPath = $config['GOOGLE_APPLICATION_CREDENTIALS'] ?? getenv('GOOGLE_APPLICATION_CREDENTIALS');

    if (!$keyPath || !file_exists((string) $keyPath)) {
        throw new Exception("Server configuration error: GOOGLE_APPLICATION_CREDENTIALS not found.");
    }

    $db = Database::getConnection();

    // Instantiate MediaService using production project and bucket names
    $projectId = $config['GEMINI_PROJECT_ID'] ?? 'geodashing-v2';
    $bucketName = 'geodashing-v2-blobs'; // Standard bucket name from API handlers
    $mediaService = new MediaService((string) $projectId, $bucketName, (string) $keyPath);

    // Reflect MediaService to access private methods and properties
    $reflection = new \ReflectionClass(MediaService::class);

    $generateThumbnailMethod = $reflection->getMethod('generateThumbnail');

    $storageProp = $reflection->getProperty('storage');
    $storageClient = $storageProp->getValue($mediaService);

    $bucketNameProp = $reflection->getProperty('bucketName');
    $realBucketName = (string) $bucketNameProp->getValue($mediaService);

    $bucket = $storageClient->bucket($realBucketName);

    // Fetch visits containing photos
    $stmt = $db->query(
        "SELECT id, photos FROM visits WHERE photos IS NOT NULL AND photos != '' AND photos != '[]'"
    );
    $visits = $stmt->fetchAll();

    if (!$visits) {
        echo "No visits with photos found in the database.\n";
        exit;
    }

    echo "Found " . count($visits) . " visits to process.\n";

    $publicDomain = (getenv('APP_ENV') === 'testing' && getenv('GCS_EMULATOR_HOST'))
        ? (string) getenv('GCS_EMULATOR_HOST')
        : "https://storage.googleapis.com";
    $prefix = "{$publicDomain}/{$realBucketName}/";
    $count = 0;

    foreach ($visits as $visit) {
        $photos = json_decode((string) $visit['photos'], true);
        if (!is_array($photos)) {
            continue;
        }

        foreach ($photos as $photo) {
            if (empty($photo['url']) || empty($photo['thumb_url'])) {
                continue;
            }

            $url = (string) $photo['url'];
            $thumbUrl = (string) $photo['thumb_url'];

            // Strip the prefix to isolate GCS object names
            if (!str_starts_with($url, $prefix) || !str_starts_with($thumbUrl, $prefix)) {
                continue;
            }

            $fullSizeObjectName = substr($url, strlen($prefix));
            $thumbObjectName = substr($thumbUrl, strlen($prefix));

            echo "Checking: {$fullSizeObjectName}...\n";

            // Download full-size image via standard HTTP GET request for GCS portability
            $tempFile = tempnam(sys_get_temp_dir(), 'gd_full_');
            if ($tempFile === false) {
                echo "  -> Failed to create temporary file. Skipping.\n";
                continue;
            }

            $httpCtx = stream_context_create(['http' => ['timeout' => 15]]);
            set_error_handler(static fn(): bool => true);
            try {
                $imageBytes = file_get_contents($url, false, $httpCtx);
            } finally {
                restore_error_handler();
            }

            if ($imageBytes === false || file_put_contents($tempFile, $imageBytes) === false) {
                echo "  -> Failed to download file via HTTP GET. Skipping.\n";
                if (file_exists($tempFile)) {
                    unlink($tempFile);
                }
                continue;
            }

            // Check if the image has EXIF Orientation metadata
            set_error_handler(static fn(): bool => true);
            try {
                $exif = exif_read_data($tempFile);
            } finally {
                restore_error_handler();
            }

            if (!$exif || empty($exif['Orientation']) || (int) $exif['Orientation'] <= 1) {
                // Already correct orientation or no EXIF tag, skip
                if (file_exists($tempFile)) {
                    unlink($tempFile);
                }
                continue;
            }

            $orientation = (int) $exif['Orientation'];
            echo "  -> Found EXIF Orientation: {$orientation}. Recreating thumbnail...\n";

            // Determine mime type
            $finfo = new finfo(FILEINFO_MIME_TYPE);
            $mime = $finfo->file($tempFile);

            // Generate corrected thumbnail
            $newThumbPath = $generateThumbnailMethod->invoke($mediaService, $tempFile, $mime);
            if (!is_string($newThumbPath) || $newThumbPath === '') {
                echo "  -> Failed to generate thumbnail. Skipping.\n";
                if (file_exists($tempFile)) {
                    unlink($tempFile);
                }
                continue;
            }

            // Upload the new thumbnail overwriting the old one
            try {
                $stream = fopen($newThumbPath, 'r');
                if ($stream === false) {
                    throw new Exception("Unable to open generated thumbnail stream.");
                }
                $bucket->upload(
                    $stream,
                    [
                        'name' => $thumbObjectName,
                        'resumable' => false
                    ]
                );
                echo "  -> Recreated and uploaded thumbnail successfully.\n";
                $count++;
            } catch (Exception $e) {
                echo "  -> Upload failed: " . $e->getMessage() . "\n";
            } finally {
                if (file_exists($tempFile)) {
                    unlink($tempFile);
                }
                if (file_exists($newThumbPath)) {
                    unlink($newThumbPath);
                }
            }
        }
    }

    echo "Completed. Recreated {$count} thumbnails.\n";
} catch (Exception $e) {
    echo "Fatal Error: " . $e->getMessage() . "\n";
}
