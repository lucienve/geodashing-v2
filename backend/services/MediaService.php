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
            // Silently skip if no file was uploaded
            if ($file['error'] === UPLOAD_ERR_NO_FILE || empty($file['tmp_name'])) {
                continue; 
            }
            
            // Explosively intercept physical block drops cleanly routing the failure to the UI
            if ($file['error'] !== UPLOAD_ERR_OK) {
                $errMap = [
                    UPLOAD_ERR_INI_SIZE => "Payload exceeds PHP 'upload_max_filesize' limits (Current default is likely 2MB).",
                    UPLOAD_ERR_FORM_SIZE => "File exceeds MAX_FILE_SIZE form limit.",
                    UPLOAD_ERR_PARTIAL => "File was only partially uploaded over the network.",
                    UPLOAD_ERR_NO_TMP_DIR => "Disk error: Missing temporary tracking directory.",
                    UPLOAD_ERR_CANT_WRITE => "Disk error: PHP failed to write chunk to disk.",
                ];
                $msg = $errMap[$file['error']] ?? "Raw PHP System Error Code: {$file['error']}";
                throw new Exception($msg);
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
            // Explicitly disabling resumable uploads forces a direct multipart stream natively preventing 
            // the PHP Apache lifecycle from abandoning the background chunk process mid-upload!
            $bucket->upload(
                fopen($file['tmp_name'], 'r'),
                [
                    'name' => $objectName,
                    'resumable' => false             // Bypass chunked background uploads natively
                ]
            );

            // Extract standard EXIF GPS coordinates strictly BEFORE we physically trash the local tmp_name!
            $exifData = $this->parseExifGPS($file['tmp_name']);

            // Construct standard GS public URL path resolving identically via HTTP
            $urls[] = [
                'url' => "https://storage.googleapis.com/{$this->bucketName}/{$objectName}",
                'lat' => $exifData ? $exifData['lat'] : null,
                'lon' => $exifData ? $exifData['lon'] : null
            ];
        }

        return $urls;
    }

    /**
     * Extracts and calculates EXIF GPS data from an image file natively.
     * 
     * @param string $path Local absolute path to the uploaded image binary.
     * @return array|null Null if no EXIF exists or if coordinates are missing.
     */
    private function parseExifGPS(string $path): ?array
    {
        // Suppress warnings specifically because standard WebP/PNG uploads often strictly lack EXIF headers!
        $exif = @exif_read_data($path);
        if (!$exif || !isset($exif['GPSLatitude'], $exif['GPSLongitude'], $exif['GPSLatitudeRef'], $exif['GPSLongitudeRef'])) {
            return null;
        }

        $lat = $this->convertGpsToDecimal($exif['GPSLatitude'], $exif['GPSLatitudeRef']);
        $lon = $this->convertGpsToDecimal($exif['GPSLongitude'], $exif['GPSLongitudeRef']);

        if ($lat === null || $lon === null) {
            return null;
        }

        return ['lat' => $lat, 'lon' => $lon];
    }

    /**
     * Converts raw EXIF DMS fraction arrays into a strict Decimal Degree natively.
     */
    private function convertGpsToDecimal(array $exifCoord, string $hemi): ?float
    {
        $degrees = count($exifCoord) > 0 ? $this->evalExifFraction($exifCoord[0]) : 0;
        $minutes = count($exifCoord) > 1 ? $this->evalExifFraction($exifCoord[1]) : 0;
        $seconds = count($exifCoord) > 2 ? $this->evalExifFraction($exifCoord[2]) : 0;

        $decimal = $degrees + ($minutes / 60) + ($seconds / 3600);
        
        $hemi = strtoupper(trim($hemi));
        if ($hemi === 'S' || $hemi === 'W') {
            $decimal *= -1;
        }

        return round($decimal, 6);
    }

    /**
     * Evaluates PHP's physical EXIF integer fractions (e.g. "42/1") cleanly.
     */
    private function evalExifFraction($fraction): float 
    {
        $parts = explode('/', (string)$fraction);
        if (count($parts) <= 0) return 0.0;
        if (count($parts) == 1) return (float)$parts[0];
        if ($parts[1] == 0) return 0.0; 
        return (float)$parts[0] / (float)$parts[1];
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
