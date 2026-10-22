<?php

declare(strict_types=1);

namespace App\Services;

use Exception;
use finfo;
use Google\Cloud\Storage\StorageClient;

/**
 * MediaService
 *
 * Handles file validation and Google Cloud Storage SDK integration,
 * pushing image files into the Cloud Storage bucket.
 */
class MediaService
{
    /**
     * @var StorageClient Google Cloud Storage client instance.
     */
    private StorageClient $storage;

    /**
     * @var string Google Cloud Storage bucket name.
     */
    private string $bucketName;

    /**
     * Constructor.
     *
     * @param string             $projectId   The GCP Architecture Project ID.
     * @param string             $bucketName  The dedicated GS blob storage pool name.
     * @param string|null        $keyFilePath Absolute disk path referencing the IAM Service Account JSON key.
     * @param StorageClient|null $storage     Optional dependency injection override for PHPUnit mocks.
     */
    public function __construct(
        string $projectId,
        string $bucketName,
        ?string $keyFilePath = null,
        ?StorageClient $storage = null
    ) {
        $this->bucketName = $bucketName;

        if ($storage !== null) {
            $this->storage = $storage;
        } else {
            $config = [
                'projectId' => $projectId,
            ];

            if ($keyFilePath !== null) {
                $config['keyFilePath'] = $keyFilePath;
            }

            // When in E2E testing, re-route GCP storage requests to the local emulator mapping
            if (getenv('APP_ENV') === 'testing' && getenv('GCS_EMULATOR_HOST')) {
                $config['apiEndpoint'] = getenv('GCS_EMULATOR_HOST');
                // Neutralize auth by supplying a dummy credentials fetcher. This prevents
                // the SDK from eagerly loading developer Application Default Credentials and hitting OAuth.
                $config['credentialsFetcher'] = new class implements \Google\Auth\FetchAuthTokenInterface {
                    /**
                     * Returns a mock auth token for the local GCS emulator.
                     *
                     * @param callable|null $httpHandler Optional HTTP handler.
                     * @return array<string, mixed>
                     */
                    #[\Override]
                    public function fetchAuthToken(?callable $httpHandler = null): array
                    {
                        return ['access_token' => 'mock-token-for-emulator', 'expires_in' => 3600];
                    }

                    /**
                     * Returns a mock cache key for the local GCS emulator.
                     *
                     * @return string
                     */
                    #[\Override]
                    public function getCacheKey(): string
                    {
                        return 'mock-key';
                    }

                    /**
                     * Returns the last received mock token for the local GCS emulator.
                     *
                     * @return array<string, mixed>|null
                     */
                    #[\Override]
                    public function getLastReceivedToken(): ?array
                    {
                        return ['access_token' => 'mock-token-for-emulator', 'expires_in' => 3600];
                    }
                };
            }

            // Bridge the production GCP sockets safely wrapping the IAM config map
            $this->storage = new StorageClient($config);
        }
    }

    /**
     * Normalizes and uploads an array of raw PHP files to Google Cloud Storage.
     *
     * @param array<string, mixed>       $files       The raw $_FILES['photos'] multidimensional array dump.
     * @param string                     $dashpointId The target dashpoint enforcing hierarchical naming.
     * @param int|string                 $userId      The uploader identity bounding scope.
     * @param array<int|string, string>  $captions    Optional array of captions mapped to original photo indexes.
     * @return array<int, array<string, mixed>> Array of public GCS URLs and metadata for stored images.
     * @throws Exception If an upload logically fails or hits invalid mime blocks.
     */
    public function uploadPhotos(array $files, string $dashpointId, int|string $userId, array $captions = []): array
    {
        $urls = [];
        $bucket = $this->storage->bucket($this->bucketName);

        // Normalize the $_FILES multi-upload array architecture into an iterable linear map
        $normalizedFiles = $this->normalizeFilesArray($files);

        if (count($normalizedFiles) > 10) {
            throw new Exception("Maximum of 10 photos allowed per visit block.");
        }

        foreach ($normalizedFiles as $index => $file) {
            // Silently skip if no file was uploaded
            if ($file['error'] === UPLOAD_ERR_NO_FILE || empty($file['tmp_name'])) {
                continue;
            }

            // Intercept upload errors cleanly routing the failure to the UI
            if ($file['error'] !== UPLOAD_ERR_OK) {
                $errMap = [
                    UPLOAD_ERR_INI_SIZE =>
                        "Payload exceeds PHP 'upload_max_filesize' limits (Current default is likely 2MB).",
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
            if (!in_array($mime, ['image/jpeg', 'image/png', 'image/webp'], true)) {
                throw new Exception("Invalid file type. Only JPEG, PNG, and WebP assets are allowed.");
            }

            // Map MIME type to canonical file extension
            $mimeToExt = [
                'image/jpeg' => 'jpg',
                'image/png'  => 'png',
                'image/webp' => 'webp'
            ];
            $extension = $mimeToExt[$mime] ?? 'jpg';

            // Path traversal protection neutralizing directory escapes
            $safeDashpointId = preg_replace('/[^a-zA-Z0-9_-]/', '', $dashpointId);

            $objectName = sprintf(
                "visits/%s/%s_%s_%d.%s",
                $safeDashpointId,
                (string) $userId,
                date('YmdHis'),
                $index,
                $extension
            );

            // Extract standard EXIF GPS coordinates before modifying the local file.
            $exifData = $this->parseExifGPS($file['tmp_name']);

            // Embed IPTC caption metadata into the local JPEG temp file before upload if provided
            $origIndex = $file['index'] ?? $index;
            $caption = isset($captions[$origIndex]) ? trim((string)$captions[$origIndex]) : '';
            if ($caption !== '') {
                $this->embedIptcCaption($file['tmp_name'], $caption);
            }

            // Execute the RESTful socket stream uploading binary payload into Google Cloud
            // Explicitly disabling resumable uploads forces a direct multipart stream preventing
            // the PHP Apache lifecycle from abandoning the background chunk process mid-upload.
            $bucket->upload(
                fopen($file['tmp_name'], 'r'),
                [
                    'name' => $objectName,
                    'resumable' => false
                ]
            );

            $publicDomain = (getenv('APP_ENV') === 'testing' && getenv('GCS_EMULATOR_HOST'))
                ? getenv('GCS_EMULATOR_HOST')
                : "https://storage.googleapis.com";

            $thumbUrl = null;
            $thumbPath = $this->generateThumbnail($file['tmp_name'], $mime);
            if ($thumbPath) {
                $thumbObjectName = sprintf(
                    "visits/%s/%s_%s_%d_thumb.%s",
                    $safeDashpointId,
                    (string) $userId,
                    date('YmdHis'),
                    $index,
                    $extension
                );
                try {
                    $bucket->upload(
                        fopen($thumbPath, 'r'),
                        [
                            'name' => $thumbObjectName,
                            'resumable' => false
                        ]
                    );
                    $thumbUrl = "{$publicDomain}/{$this->bucketName}/{$thumbObjectName}";
                } finally {
                    if (file_exists($thumbPath)) {
                        unlink($thumbPath);
                    }
                }
            }

            // Construct standard GS public URL path resolving identically via HTTP
            $urls[] = [
                'url' => "{$publicDomain}/{$this->bucketName}/{$objectName}",
                'thumb_url' => $thumbUrl,
                'lat' => $exifData ? $exifData['lat'] : null,
                'lon' => $exifData ? $exifData['lon'] : null,
                'caption' => $caption !== '' ? $caption : null
            ];
        }

        return $urls;
    }

    /**
     * Parses public Google URLs routing them back into internal object paths
     * and deletes the object inside the bucket.
     *
     * @param string[] $urls An array of raw Google Cloud Storage URL strings.
     * @return void
     */
    public function deletePhotos(array $urls): void
    {
        $bucket = $this->storage->bucket($this->bucketName);
        $publicDomain = (getenv('APP_ENV') === 'testing' && getenv('GCS_EMULATOR_HOST'))
            ? getenv('GCS_EMULATOR_HOST')
            : "https://storage.googleapis.com";

        $prefix = "{$publicDomain}/{$this->bucketName}/";

        foreach ($urls as $url) {
            // Strip the public HTTP prefix to isolate the internal Object mapping (e.g. 'visits/GD01/1_pic.jpg')
            if (str_starts_with($url, $prefix)) {
                $objectName = substr($url, strlen($prefix));

                // Execute the explicit REST deletion hook synchronously
                $object = $bucket->object($objectName);
                if ($object->exists()) {
                    $object->delete();
                }

                // If this is a primary image (not already a _thumb), derive and delete companion thumbnail
                $ext = pathinfo($objectName, PATHINFO_EXTENSION);
                $filename = pathinfo($objectName, PATHINFO_FILENAME);
                $dirname = pathinfo($objectName, PATHINFO_DIRNAME);

                if (!str_ends_with($filename, '_thumb')) {
                    $thumbObjectName = ($dirname !== '.' && $dirname !== '')
                        ? "{$dirname}/{$filename}_thumb.{$ext}"
                        : "{$filename}_thumb.{$ext}";

                    $thumbObject = $bucket->object($thumbObjectName);
                    if ($thumbObject->exists()) {
                        $thumbObject->delete();
                    }
                }
            }
        }
    }

    /**
     * Executes a GD/EXIF/IPTC binary parsing callback while suppressing non-fatal PHP warnings
     * emitted on truncated or malformed image streams.
     *
     * @param callable $callback The binary image operation to execute.
     * @return mixed
     */
    private function runWithoutWarnings(callable $callback): mixed
    {
        set_error_handler(static fn(): bool => true);
        try {
            return $callback();
        } finally {
            restore_error_handler();
        }
    }

    /**
     * Generates a temporary thumbnail file proportional to an 800px max dimension.
     *
     * @param string $sourcePath The absolute path to the uploaded image.
     * @param string $mime The mime type to map the GD render function.
     * @return string|null The temporary absolute file path to the thumbnail, or null on failure.
     */
    private function generateThumbnail(string $sourcePath, string $mime): ?string
    {
        if (!extension_loaded('gd')) {
            return null; // Fallback safely if GD is missing during tests
        }

        switch ($mime) {
            case 'image/jpeg':
                $image = $this->runWithoutWarnings(static fn() => imagecreatefromjpeg($sourcePath));
                break;
            case 'image/png':
                $image = $this->runWithoutWarnings(static fn() => imagecreatefrompng($sourcePath));
                break;
            case 'image/webp':
                $image = $this->runWithoutWarnings(static fn() => imagecreatefromwebp($sourcePath));
                break;
            default:
                return null;
        }

        if (!$image) {
            return null;
        }

        // Correct orientation based on EXIF metadata if present
        $exif = $this->readExifData($sourcePath);
        if ($exif && !empty($exif['Orientation'])) {
            $orientation = (int)$exif['Orientation'];
            switch ($orientation) {
                case 2:
                    imageflip($image, IMG_FLIP_HORIZONTAL);
                    break;
                case 3:
                    $rotated = $this->runWithoutWarnings(static fn() => imagerotate($image, 180, 0));
                    if ($rotated !== false) {
                        $image = $rotated;
                    }
                    break;
                case 4:
                    imageflip($image, IMG_FLIP_VERTICAL);
                    break;
                case 5:
                    imageflip($image, IMG_FLIP_VERTICAL);
                    $rotated = $this->runWithoutWarnings(static fn() => imagerotate($image, 270, 0));
                    if ($rotated !== false) {
                        $image = $rotated;
                    }
                    break;
                case 6:
                    $rotated = $this->runWithoutWarnings(static fn() => imagerotate($image, 270, 0));
                    if ($rotated !== false) {
                        $image = $rotated;
                    }
                    break;
                case 7:
                    imageflip($image, IMG_FLIP_HORIZONTAL);
                    $rotated = $this->runWithoutWarnings(static fn() => imagerotate($image, 270, 0));
                    if ($rotated !== false) {
                        $image = $rotated;
                    }
                    break;
                case 8:
                    $rotated = $this->runWithoutWarnings(static fn() => imagerotate($image, 90, 0));
                    if ($rotated !== false) {
                        $image = $rotated;
                    }
                    break;
            }
        }

        $width = imagesx($image);
        $height = imagesy($image);

        $maxWidth = 800;
        $maxHeight = 800;

        if ($width <= $maxWidth && $height <= $maxHeight) {
            $newWidth = $width;
            $newHeight = $height;
        } else {
            $ratio = min($maxWidth / $width, $maxHeight / $height);
            $newWidth = (int)round($width * $ratio);
            $newHeight = (int)round($height * $ratio);
        }

        $thumbnail = imagecreatetruecolor($newWidth, $newHeight);

        // Preserve transparency for PNG and WebP
        if ($mime === 'image/png' || $mime === 'image/webp') {
            imagealphablending($thumbnail, false);
            imagesavealpha($thumbnail, true);
            $transparent = imagecolorallocatealpha($thumbnail, 255, 255, 255, 127);
            imagefilledrectangle($thumbnail, 0, 0, $newWidth, $newHeight, $transparent);
        }

        imagecopyresampled($thumbnail, $image, 0, 0, 0, 0, $newWidth, $newHeight, $width, $height);

        $tempFile = tempnam(sys_get_temp_dir(), 'gd_thumb_');
        if ($tempFile === false) {
            return null;
        }
        $success = false;

        switch ($mime) {
            case 'image/jpeg':
                $success = imagejpeg($thumbnail, $tempFile, 85);
                break;
            case 'image/png':
                $success = imagepng($thumbnail, $tempFile, 8);
                break;
            case 'image/webp':
                $success = imagewebp($thumbnail, $tempFile, 85);
                break;
        }

        if (!$success) {
            if (file_exists($tempFile)) {
                unlink($tempFile);
            }
            return null;
        }

        return $tempFile;
    }

    /**
     * Extracts and calculates EXIF GPS data from an image file.
     *
     * @param string $path Local absolute path to the uploaded image binary.
     * @return array{lat: float, lon: float}|null Null if no EXIF exists or if coordinates are missing.
     */
    private function parseExifGPS(string $path): ?array
    {
        $exif = $this->readExifData($path);
        $hasGps = $exif && isset(
            $exif['GPSLatitude'],
            $exif['GPSLongitude'],
            $exif['GPSLatitudeRef'],
            $exif['GPSLongitudeRef']
        );
        if (!$hasGps) {
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
     * Converts raw EXIF DMS fraction arrays into a Decimal Degree float.
     *
     * @param array<int, string|int|float> $exifCoord EXIF DMS coordinate array.
     * @param string                       $hemi      Hemisphere reference ('N', 'S', 'E', 'W').
     * @return float|null
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
     * Evaluates PHP's standard EXIF integer fractions (e.g. "42/1") cleanly.
     *
     * @param string|int|float $fraction Raw EXIF rational value.
     * @return float
     */
    private function evalExifFraction(string|int|float $fraction): float
    {
        $parts = explode('/', (string)$fraction);
        if (count($parts) <= 0) {
            return 0.0;
        }
        if (count($parts) === 1) {
            return (float)$parts[0];
        }
        $denominator = (float)$parts[1];
        if ($denominator === 0.0) {
            return 0.0;
        }
        return (float)$parts[0] / $denominator;
    }

    /**
     * Cleans the legacy `$_FILES` structure into a standard iterative matrix mapping
     * fields uniformly across multiple HTTP-uploaded binary payload arrays.
     *
     * @param array<string, mixed> $files Raw `$_FILES` entry.
     * @return array<int, array<string, mixed>>
     */
    private function normalizeFilesArray(array $files): array
    {
        $normalized = [];
        // Determine whether HTML explicitly passed a single file or a multi-part array map
        if (!is_array($files['name'])) {
            $single = $files;
            $single['index'] = 0;
            return [$single];
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
                'index'    => $i,
            ];
        }
        return $normalized;
    }

    /**
     * Reads EXIF data from an image file path.
     *
     * @param string $path Local absolute path to the image file.
     * @return array<string, mixed>|null
     */
    protected function readExifData(string $path): ?array
    {
        if (!function_exists('exif_read_data') || !file_exists($path)) {
            return null;
        }
        $data = $this->runWithoutWarnings(static fn() => exif_read_data($path));
        return is_array($data) ? $data : null;
    }

    /**
     * Embeds a caption into the local JPEG image using native IPTC headers.
     *
     * @param string $filePath The absolute path to the local file.
     * @param string $caption The caption string to embed.
     * @return void
     */
    private function embedIptcCaption(string $filePath, string $caption): void
    {
        if (!function_exists('iptcembed')) {
            return;
        }

        $caption = trim($caption);
        if ($caption === '') {
            return;
        }

        // Verify that the file is indeed a JPEG before attempting metadata injection
        $finfo = new finfo(FILEINFO_MIME_TYPE);
        $mime = $finfo->file($filePath);
        if ($mime !== 'image/jpeg') {
            return;
        }

        // Construct standard IPTC payload containing tag 2:120 (Caption/Abstract)
        // Set tag 1:90 to UTF-8 escape sequence to declare UTF-8 encoding standard
        $utf8Seq = "\x1b\x25\x47";
        $data = $this->iptcMakeTag(1, 90, $utf8Seq) . $this->iptcMakeTag(2, 120, $caption);

        // Inject standard IPTC markers into the JPEG stream
        $content = $this->runWithoutWarnings(static fn() => iptcembed($data, $filePath));
        if (is_string($content) && is_writable($filePath)) {
            $fp = fopen($filePath, 'wb');
            if ($fp !== false) {
                fwrite($fp, $content);
                fclose($fp);
            }
        }
    }

    /**
     * Helper to construct a single IPTC binary tag structure.
     *
     * @param int    $rec   IPTC record number.
     * @param int    $data  IPTC dataset tag number.
     * @param string $value Raw binary tag value.
     * @return string
     */
    private function iptcMakeTag(int $rec, int $data, string $value): string
    {
        $length = strlen($value);
        $retval = chr(0x1C) . chr($rec) . chr($data);

        if ($length < 0x8000) {
            $retval .= chr($length >> 8) . chr($length & 0xFF);
        } else {
            $retval .= chr(0x80) . chr(0x04) .
                       chr(($length >> 24) & 0xFF) .
                       chr(($length >> 16) & 0xFF) .
                       chr(($length >> 8) & 0xFF) .
                       chr($length & 0xFF);
        }
        return $retval . $value;
    }
}
