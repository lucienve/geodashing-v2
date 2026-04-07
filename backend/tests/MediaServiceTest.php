<?php
use PHPUnit\Framework\TestCase;

require_once __DIR__ . '/../services/MediaService.php';

use PHPUnit\Framework\Attributes\Test;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\Attributes\AllowMockObjectsWithoutExpectations;
use Google\Cloud\Storage\StorageClient;
use Google\Cloud\Storage\Bucket;

/**
 * MediaServiceTest
 *
 * Enforces the logical boundaries and architectural constraints
 * of the Google Cloud Storage pipeline via Dependency Injection mock protocols.
 */
#[CoversClass(MediaService::class)]
#[AllowMockObjectsWithoutExpectations]
class MediaServiceTest extends TestCase
{
    private $storageMock;
    private $bucketMock;

    protected function setUp(): void
    {
        // Mock the native Google Cloud Bucket Object
        $this->bucketMock = $this->createMock(Bucket::class);
        
        // Mock the overarching StorageClient to prevent live backend credentials scanning
        $this->storageMock = $this->createMock(StorageClient::class);
        $this->storageMock->method('bucket')->willReturn($this->bucketMock);
    }

    /**
     * Verifies that the internal logic strictly throws an exception preventing
     * massive memory block arrays overriding the Google pipeline constraints.
     */
    #[Test]
    public function processUploadBlocksMoreThan10ImagesNatively()
    {
        // Inject the Google Mocks safely wrapping the logic
        $service = new MediaService('geodashing-unit', 'geodashing-test-blobs', 'dummy.json', $this->storageMock);
        
        // Fabricate a monolithic payload containing precisely 11 identical inputs
        $fakeFiles = [
            'name' => array_fill(0, 11, 'exploit_file.jpg'),
            'type' => array_fill(0, 11, 'image/jpeg'),
            'tmp_name' => array_fill(0, 11, '/tmp/phpExploit123'),
            'error' => array_fill(0, 11, UPLOAD_ERR_OK),
            'size' => array_fill(0, 11, 1000)
        ];

        // The exact Exception string hard-mapped to MediaService.php lines 45-50
        $this->expectException(Exception::class);
        $this->expectExceptionMessage("Maximum of 10 photos allowed per visit block.");

        // Pull the trigger mapped to User ID 1 and Dashpoint 'GD-TEST'
        $service->uploadPhotos($fakeFiles, 'GD-TEST', 1);
    }

    /**
     * Asserts that when PHP silently drops an oversized payload natively matching UPLOAD_ERR_INI_SIZE
     * the pipeline fails and routes the failure back to the UI.
     */
    #[Test]
    public function processUploadCatchesPhpIniSizeLimits()
    {
        $service = new MediaService('geodashing-unit', 'geodashing-test-blobs', 'dummy.json', $this->storageMock);
        
        $fakeFiles = [
            'name' => ['too_big.jpg'],
            'type' => ['image/jpeg'],
            'tmp_name' => ['/tmp/missing'],
            'error' => [UPLOAD_ERR_INI_SIZE],
            'size' => [10000000]
        ];

        $this->expectException(Exception::class);
        $this->expectExceptionMessage("Payload exceeds PHP 'upload_max_filesize' limits");

        // The sequence must abort prior to resolving GCP streams.
        $service->uploadPhotos($fakeFiles, 'GD-TEST', 1);
    }
    
    /**
     * Asserts that successfully validated uploads return an associative array.
     */
    #[Test]
    public function processUploadReturnsAssociatedObjectArrays()
    {
        $service = new MediaService('geodashing-unit', 'geodashing-test-blobs', 'dummy.json', $this->storageMock);
        
        // Construct a raw mock JPEG using magic hex bytes.
        // This ensures finfo(FILEINFO_MIME_TYPE) identifies it as 'image/jpeg' without requiring ext-gd rendering.
        $tempFile = tempnam(sys_get_temp_dir(), 'fktst');
        file_put_contents($tempFile, "\xFF\xD8\xFF\xE0\x00\x10\x4A\x46\x49\x46\x00\x01\x01\x01");
        
        $fakeFiles = [
            'name' => ['valid_pic.jpg'],
            'type' => ['image/jpeg'],
            'tmp_name' => [$tempFile],
            'error' => [UPLOAD_ERR_OK],
            'size' => [filesize($tempFile)]
        ];

        // Ensure the bucket mock physically accepts the RESTful stream payload structurally
        $this->bucketMock->expects($this->once())->method('upload');

        $result = $service->uploadPhotos($fakeFiles, 'GD-TEST', 1);
        
        // Assert exactly correct Object mapping parameters preventing frontend array collisions
        $this->assertIsArray($result);
        $this->assertCount(1, $result);
        $this->assertArrayHasKey('url', $result[0]);
        $this->assertArrayHasKey('lat', $result[0]);
        $this->assertArrayHasKey('lon', $result[0]);
        $this->assertStringContainsString("geodashing-test-blobs", $result[0]['url']);
        
        // Without an EXIF data package in our mock JPEG, coordinates must resolve to null.
        $this->assertNull($result[0]['lat']);
        $this->assertNull($result[0]['lon']);
        
        // Trash the local mock mapping safely
        unlink($tempFile);
    }

    /**
     * Asserts that passing public GCS URLs dynamically routes to the underlying raw bucket 
     * objects uniquely isolating the structural deletions correctly.
     */
    #[Test]
    public function processDeleteIsolatesGcsObjectPrefix()
    {
        $service = new MediaService('geodashing-unit', 'geodashing-test-blobs', 'dummy.json', $this->storageMock);
        
        $fakeObject = $this->createMock(\Google\Cloud\Storage\StorageObject::class);
        $fakeObject->expects($this->once())->method('exists')->willReturn(true);
        $fakeObject->expects($this->once())->method('delete');
        
        // Assert that exactly 'visits/GD001/my_pic.jpg' is passed natively to the Google Bucket Object request
        $this->bucketMock->expects($this->once())
             ->method('object')
             ->with('visits/GD001/my_pic.jpg')
             ->willReturn($fakeObject);

        $urlsToDelete = ['https://storage.googleapis.com/geodashing-test-blobs/visits/GD001/my_pic.jpg'];
        $service->deletePhotos($urlsToDelete);
    }
}
