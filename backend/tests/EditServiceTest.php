<?php
use PHPUnit\Framework\TestCase;

require_once __DIR__ . '/../api/edit.php';
require_once __DIR__ . '/../services/MediaService.php';

use PHPUnit\Framework\Attributes\Test;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\Attributes\AllowMockObjectsWithoutExpectations;

/**
 * EditServiceTest
 *
 * Physically verifies the backend Diff logic ensuring edits strictly validate 
 * Session ownership, safely orchestrate GCP Deletions, and rigidly enforce Image Counts.
 */
#[CoversClass(EditService::class)]
#[AllowMockObjectsWithoutExpectations]
class EditServiceTest extends TestCase
{
    private $pdoMock;
    private $mediaMock;
    private $editService;

    protected function setUp(): void
    {
        $this->pdoMock = $this->createMock(PDO::class);
        $this->mediaMock = $this->createMock(MediaService::class);
        $this->editService = new EditService($this->pdoMock, $this->mediaMock);
    }

    /**
     * Asserts that editing fundamentally aborts securely if the user physically 
     * tries to modify a Dashpoint log they do not natively own.
     */
    #[Test]
    public function processEditRejectsForeignOwnership()
    {
        $stmtMock = $this->createMock(PDOStatement::class);
        $stmtMock->method('fetch')->willReturn(false); // Simulates standard DB fail natively
        $this->pdoMock->method('prepare')->willReturn($stmtMock);

        $result = $this->editService->processEdit(1, 'GD01-999', 'Hacking attempt', '[]');

        $this->assertEquals("error", $result['status']);
        $this->assertEquals(403, $result['code']);
    }

    /**
     * Asserts that legacy photos mapped in the Database that are mathematically excluded 
     * from the incoming `kept_photos` JSON payload are structurally dumped to GCP Deletion.
     */
    #[Test]
    public function processEditTriggersMediaDeletionForAbandonedUrls()
    {
        $stmtMock = $this->createMock(PDOStatement::class);
        $stmtMock->method('fetch')->willReturn([
            'id' => 10,
            'photos' => json_encode([
                ['url' => 'https://storage.googleapis.com/b/historic_1.jpg', 'lat' => null, 'lon' => null],
                ['url' => 'https://storage.googleapis.com/b/historic_2.jpg', 'lat' => null, 'lon' => null]
            ])
        ]);
        
        $updateStmtMock = $this->createMock(PDOStatement::class);
        $updateStmtMock->expects($this->once())->method('execute'); // Ensure the DB updates securely

        $this->pdoMock->method('prepare')->willReturnCallback(function($sql) use ($stmtMock, $updateStmtMock) {
            if (strpos($sql, 'SELECT id') !== false) return $stmtMock;
            if (strpos($sql, 'UPDATE visits') !== false) return $updateStmtMock;
            return $this->createMock(PDOStatement::class);
        });

        // We explicitly tell the Server we ONLY want to keep `historic_2.jpg`.
        $keptRaw = json_encode(['https://storage.googleapis.com/b/historic_2.jpg']);

        // Assert that the MediaService dynamically intercepts `historic_1.jpg` for explicit Destruction!
        $this->mediaMock->expects($this->once())
             ->method('deletePhotos')
             ->with(['https://storage.googleapis.com/b/historic_1.jpg']);

        $result = $this->editService->processEdit(1, 'GD01-001', 'Changed notes.', $keptRaw, null);

        $this->assertEquals("success", $result['status']);
        // Assert the returned mutated array natively ONLY has `historic_2`!
        $this->assertCount(1, $result['data']['photos']);
        $this->assertEquals('https://storage.googleapis.com/b/historic_2.jpg', $result['data']['photos'][0]['url']);
    }

    /**
     * Proves the architectural 10-Media limitation is strictly enforced post-merge natively
     */
    #[Test]
    public function processEditRestrictsMaximumImageMerges()
    {
        // Simulate a database row with 8 physical binaries 
        $existingPhotos = [];
        $keptStrings = [];
        for ($i = 0; $i < 8; $i++) {
            $url = "https://storage.../historic_{$i}.jpg";
            $existingPhotos[] = ['url' => $url];
            $keptStrings[] = $url;
        }

        $stmtMock = $this->createMock(PDOStatement::class);
        $stmtMock->method('fetch')->willReturn([
            'id' => 10,
            'photos' => json_encode($existingPhotos)
        ]);
        $this->pdoMock->method('prepare')->willReturn($stmtMock);

        // Simulate 3 New Binaries incoming natively making 11 total!
        $newFilesMock = [
            'name' => ['new1.jpg', 'new2.jpg', 'new3.jpg'],
            'tmp_name' => ['/tmp/1', '/tmp/2', '/tmp/3'],
            'size' => [1000, 1000, 1000],
            'error' => [UPLOAD_ERR_OK, UPLOAD_ERR_OK, UPLOAD_ERR_OK]
        ];

        // Ensure MediaService physically uploads the 3 new ones securely 
        $this->mediaMock->expects($this->once())
             ->method('uploadPhotos')
             ->willReturn([
                 ['url' => 'https://../new1.jpg'],
                 ['url' => 'https://../new2.jpg'],
                 ['url' => 'https://../new3.jpg']
             ]);

        // Submit the mathematical mutation!
        $result = $this->editService->processEdit(1, 'GD01-001', 'Updating photos.', json_encode($keptStrings), $newFilesMock);

        // It should rigidly abort completely mapping a 400!
        $this->assertEquals("error", $result['status']);
        $this->assertEquals(400, $result['code']);
    }
}
