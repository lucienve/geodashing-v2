<?php
/**
 * MediaService
 *
 * Handles file validation and Google Cloud Storage SDK integration natively
 * pushing image binary arrays directly into the distributed geodashing-v2-blobs bucket.
 */

// Load Composer autoload specifically for Google Cloud Storage Library mapping
require_once __DIR__ . '/../../vendor/autoload.php';

use Google\Cloud\Storage\StorageClient;

class MediaService
{
    private StorageClient $storage;
    private string $bucketName;

    /**
     * @param string $projectId  The GCP Architecture Project ID.
     * @param string $bucketName The dedicated GS blob storage pool name.
     * @param string $keyFilePath Absolute disk path referencing the IAM Service Account JSON key.
     * @param StorageClient|null $storage Optional dependency injection override strictly for PHPUnit Mocking protocols!
     */
    public function __construct(string $projectId, string $bucketName, string $keyFilePath, ?StorageClient $storage = null)
    {
        $this->bucketName = $bucketName;
        
        if ($storage !== null) {
            $this->storage = $storage;
        } else {
            // Natively bridge the production GCP sockets safely wrapping the IAM config map
            $this->storage = new StorageClient([
                'projectId' => $projectId,
                'keyFilePath' => $keyFilePath
            ]);
        }
    }

    /**
     * Normalizes and uploads an array of raw PHP files natively to Google Cloud Storage.
     *
     * @param array $files The raw $_FILES['photos'] multidimensional array dump.
     * @param string $dashpointId The target dashpoint enforcing hierarchical naming.
     * @param int|string $userId The uploader identity bounding scope.
     * @return array Array of public GCS URLs mapping directly to the successfully stored images.
     * @throws Exception If an upload logically fails or hits invalid mime blocks.
     */
    public function uploadPhotos(array $files, string $dashpointId, $userId): array
    {
        $urls = [];
        $bucket = $this->storage->bucket($this->bucketName);

        // Normalize the heavily disjointed $_FILES multi-upload array architecture into an iterable linear map
        $normalizedFiles = $this->normalizeFilesArray($files);
        
        if (count($normalizedFiles) > 10) {
            throw new Exception("Maximum of 10 photos allowed per visit block.");
        }

        foreach ($normalizedFiles as $index => $file) {
            // Drop technically null/omitted form inputs cleanly
            if ($file['error'] !== UPLOAD_ERR_OK || empty($file['tmp_name'])) {
                continue; 
            }
            
            // Server-side strict MIME validation preventing remote exploits
            $finfo = new finfo(FILEINFO_MIME_TYPE);
            $mime = $finfo->file($file['tmp_name']);
            if (!in_array($mime, ['image/jpeg', 'image/png', 'image/webp'])) {
                throw new Exception("Invalid file type explicitly blocked. Only JPEG, PNG, and WebP assets are strictly allowed.");
            }

            // Generate a secure unique mathematical path map locking the object structure securely in the bucket
            $extension = pathinfo($file['name'], PATHINFO_EXTENSION) ?: 'jpg';
            $objectName = sprintf("visits/%s/%d_%s_%d.%s", 
                $dashpointId, 
                $userId, 
                date('YmdHis'), 
                $index, 
                strtolower($extension)
            );

            // Execute the RESTful socket stream uploading binary payload natively into Google Cloud
            $bucket->upload(
                fopen($file['tmp_name'], 'r'),
                [
                    'name' => $objectName,
                    'predefinedAcl' => 'publicRead' // Force Public-Read scope natively enabling frontend image tag renders without pre-signed URL architectures
                ]
            );

            // Construct standard GS public URL path resolving identically via HTTP
            $urls[] = "https://storage.googleapis.com/{$this->bucketName}/{$objectName}";
        }

        return $urls;
    }

    /**
     * Cleans the legacy `$_FILES` structure into a standard iterative matrix natively mapping
     * fields uniformly across multiple HTTP-uploaded binary payload arrays.
     */
    private function normalizeFilesArray(array $files): array
    {
        $normalized = [];
        // Determine whether HTML explicitly passed a single file or a multi-part array map 
        if (!is_array($files['name'])) {
            return [$files];
        }

        foreach ($files['name'] as $i => $name) {
            if ($files['error'][$i] === UPLOAD_ERR_NO_FILE) {
                continue;
            }
            $normalized[] = [
                'name'     => $files['name'][$i],
                'type'     => $files['type'][$i],
                'tmp_name' => $files['tmp_name'][$i],
                'error'    => $files['error'][$i],
                'size'     => $files['size'][$i],
            ];
        }
        return $normalized;
    }
}
