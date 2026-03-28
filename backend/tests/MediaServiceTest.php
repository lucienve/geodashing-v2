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
}
