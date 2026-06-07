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
    $config = file_exists($configPath) ? parse_ini_file($configPath) : [];
    $keyPath = $config['GOOGLE_APPLICATION_CREDENTIALS'] ?? getenv('GOOGLE_APPLICATION_CREDENTIALS');

    if (!$keyPath || !file_exists($keyPath)) {
        throw new Exception("Server configuration error: GOOGLE_APPLICATION_CREDENTIALS not found.");
    }

    $db = Database::getConnection();

    // Instantiate MediaService using production project and bucket names (defaulting to standard ones if not in config)
    $projectId = $config['GEMINI_PROJECT_ID'] ?? 'geodashing-v2';
    $bucketName = 'geodashing-v2-blobs'; // Standard bucket name from API handlers
    $mediaService = new MediaService($projectId, $bucketName, $keyPath);

    // Reflect MediaService to access private methods and properties
    $reflection = new \ReflectionClass(MediaService::class);

    $generateThumbnailMethod = $reflection->getMethod('generateThumbnail');
    $generateThumbnailMethod->setAccessible(true);

    $storageProp = $reflection->getProperty('storage');
    $storageProp->setAccessible(true);
    $storageClient = $storageProp->getValue($mediaService);

    $bucketNameProp = $reflection->getProperty('bucketName');
    $bucketNameProp->setAccessible(true);
    $realBucketName = $bucketNameProp->getValue($mediaService);

    $bucket = $storageClient->bucket($realBucketName);

    // Fetch visits containing photos
    $stmt = $db->query("SELECT id, photos FROM visits WHERE photos IS NOT NULL AND photos != '' AND photos != '[]'");
    $visits = $stmt->fetchAll();

    if (!$visits) {
        echo "No visits with photos found in the database.\n";
        exit;
    }

    echo "Found " . count($visits) . " visits to process.\n";

    $publicDomain = "https://storage.googleapis.com";
    $prefix = "{$publicDomain}/{$realBucketName}/";
    $count = 0;

    foreach ($visits as $visit) {
        $photos = json_decode($visit['photos'], true);
        if (!is_array($photos)) {
            continue;
        }

        foreach ($photos as $photo) {
            if (empty($photo['url']) || empty($photo['thumb_url'])) {
                continue;
            }

            $url = $photo['url'];
            $thumbUrl = $photo['thumb_url'];

            // Strip the prefix to isolate GCS object names
            if (strpos($url, $prefix) !== 0 || strpos($thumbUrl, $prefix) !== 0) {
                continue;
            }

            $fullSizeObjectName = substr($url, strlen($prefix));
            $thumbObjectName = substr($thumbUrl, strlen($prefix));

            echo "Checking: {$fullSizeObjectName}...\n";

            $object = $bucket->object($fullSizeObjectName);
            if (!$object->exists()) {
                echo "  -> Full-size image object does not exist on GCS. Skipping.\n";
                continue;
            }

            // Download full-size image to temp file
            $tempFile = tempnam(sys_get_temp_dir(), 'gd_full_');
            try {
                $object->downloadToFile($tempFile);
            } catch (Exception $e) {
                echo "  -> Failed to download file: " . $e->getMessage() . "\n";
                @unlink($tempFile);
                continue;
            }

            // Check if the image has EXIF Orientation metadata
            $exif = @exif_read_data($tempFile);
            if (!$exif || empty($exif['Orientation']) || (int)$exif['Orientation'] <= 1) {
                // Already correct orientation or no EXIF tag, skip
                @unlink($tempFile);
                continue;
            }

            $orientation = (int)$exif['Orientation'];
            echo "  -> Found EXIF Orientation: {$orientation}. Recreating thumbnail...\n";

            // Determine mime type
            $finfo = new finfo(FILEINFO_MIME_TYPE);
            $mime = $finfo->file($tempFile);

            // Generate corrected thumbnail
            $newThumbPath = $generateThumbnailMethod->invoke($mediaService, $tempFile, $mime);
            if (!$newThumbPath) {
                echo "  -> Failed to generate thumbnail. Skipping.\n";
                @unlink($tempFile);
                continue;
            }

            // Upload the new thumbnail overwriting the old one
            try {
                $bucket->upload(
                    fopen($newThumbPath, 'r'),
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
                @unlink($tempFile);
                @unlink($newThumbPath);
            }
        }
    }

    echo "Completed! Recreated {$count} thumbnails.\n";
} catch (Exception $e) {
    echo "Fatal Error: " . $e->getMessage() . "\n";
}
