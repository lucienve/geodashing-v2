<?php

declare(strict_types=1);

namespace App\Tests;

use App\Services\TagService;
use InvalidArgumentException;
use PDO;
use PDOStatement;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\Attributes\Test;
use PHPUnit\Framework\TestCase;

/**
 * TagServiceTest
 *
 * Verifies TagService feature flags, ETag determinism, and dashpoint tag CRUD.
 */
#[CoversClass(TagService::class)]
class TagServiceTest extends TestCase
{
    /**
     * @var PDO
     */
    private PDO $pdoMock;

    /**
     * Sets up the test fixtures.
     */
    #[\Override]
    protected function setUp(): void
    {
        putenv('APP_ENV=testing');
        $_ENV['APP_ENV'] = 'testing';
        $this->pdoMock = $this->createStub(PDO::class);
    }

    /**
     * Cleans up environment overrides after each test.
     */
    #[\Override]
    protected function tearDown(): void
    {
        putenv('TAGS_ENABLED');
        putenv('TAGS_ALLOWLIST');
        unset($_ENV['TAGS_ENABLED'], $_ENV['TAGS_ALLOWLIST']);
    }

    #[Test]
    public function featureFlagReturnsTrueWhenGloballyEnabled(): void
    {
        $config = [
            'tags' => [
                'TAGS_ENABLED' => true,
                'TAGS_ALLOWLIST' => ''
            ]
        ];
        $service = new TagService($this->pdoMock, $config);

        $this->assertTrue($service->isFeatureEnabledForUser(null));
        $this->assertTrue($service->isFeatureEnabledForUser('anyone'));
    }

    #[Test]
    public function featureFlagAllowsUserInAllowlistWhenGloballyDisabled(): void
    {
        $config = [
            'tags' => [
                'TAGS_ENABLED' => false,
                'TAGS_ALLOWLIST' => 'Alice, Bob, Charlie'
            ]
        ];
        $service = new TagService($this->pdoMock, $config);

        $this->assertTrue($service->isFeatureEnabledForUser('alice'));
        $this->assertTrue($service->isFeatureEnabledForUser('BOB'));
        $this->assertTrue($service->isFeatureEnabledForUser('charlie'));
        $this->assertFalse($service->isFeatureEnabledForUser('Dave'));
        $this->assertFalse($service->isFeatureEnabledForUser(null));
        $this->assertFalse($service->isFeatureEnabledForUser(''));
    }

    #[Test]
    public function featureFlagDisallowsAllWhenGloballyDisabledAndAllowlistEmpty(): void
    {
        $config = [
            'tags' => [
                'TAGS_ENABLED' => false,
                'TAGS_ALLOWLIST' => ''
            ]
        ];
        $service = new TagService($this->pdoMock, $config);

        $this->assertFalse($service->isFeatureEnabledForUser('alice'));
        $this->assertFalse($service->isFeatureEnabledForUser(null));
    }

    #[Test]
    public function getTagsForUserAndGameFormatsAssociativeDictionary(): void
    {
        $this->pdoMock = $this->createMock(PDO::class);
        $stmtMock = $this->createMock(PDOStatement::class);
        $stmtMock->expects($this->once())
            ->method('execute')
            ->with(['user_id' => 1, 'game_id' => 2]);
        $stmtMock->expects($this->once())
            ->method('fetchAll')
            ->with(PDO::FETCH_ASSOC)
            ->willReturn([
                [
                    'dashpoint_id' => 'GD001-AAAA',
                    'color_code' => '#1a73e8',
                    'shape' => 'star',
                    'lat' => '43.0851',
                    'lon' => '-88.0412'
                ],
                [
                    'dashpoint_id' => 'GD001-AAAB',
                    'color_code' => '#e64a19',
                    'shape' => 'triangle',
                    'lat' => '43.1420',
                    'lon' => '-87.9810'
                ]
            ]);

        $this->pdoMock->expects($this->once())
            ->method('prepare')
            ->willReturn($stmtMock);

        $service = new TagService($this->pdoMock, ['tags' => ['TAGS_ENABLED' => true]]);
        $tags = $service->getTagsForUserAndGame(1, 2);

        $this->assertCount(2, $tags);
        $this->assertEquals(
            ['color' => '#1a73e8', 'shape' => 'star', 'lat' => 43.0851, 'lon' => -88.0412],
            $tags['GD001-AAAA']
        );
        $this->assertEquals(
            ['color' => '#e64a19', 'shape' => 'triangle', 'lat' => 43.1420, 'lon' => -87.9810],
            $tags['GD001-AAAB']
        );
        $this->assertSame(43.0851, $tags['GD001-AAAA']['lat']);
        $this->assertSame(-88.0412, $tags['GD001-AAAA']['lon']);
    }

    #[Test]
    public function setTagRejectsInvalidColor(): void
    {
        $service = new TagService($this->pdoMock, ['tags' => ['TAGS_ENABLED' => true]]);

        $this->expectException(InvalidArgumentException::class);
        $this->expectExceptionMessage('Invalid color code or shape specified.');

        $service->setTag(1, 'GD001-AAAA', '#000000', 'star');
    }

    #[Test]
    public function setTagRejectsInvalidShape(): void
    {
        $service = new TagService($this->pdoMock, ['tags' => ['TAGS_ENABLED' => true]]);

        $this->expectException(InvalidArgumentException::class);
        $this->expectExceptionMessage('Invalid color code or shape specified.');

        $service->setTag(1, 'GD001-AAAA', '#1a73e8', 'circle');
    }

    #[Test]
    public function setTagRejectsNonExistentDashpoint(): void
    {
        $this->pdoMock = $this->createMock(PDO::class);
        $checkStmt = $this->createStub(PDOStatement::class);
        $checkStmt->method('fetch')->willReturn(false);

        $this->pdoMock->expects($this->once())
            ->method('prepare')
            ->willReturn($checkStmt);

        $service = new TagService($this->pdoMock, ['tags' => ['TAGS_ENABLED' => true]]);

        $this->expectException(InvalidArgumentException::class);
        $this->expectExceptionMessage('Dashpoint not found.');

        $service->setTag(1, 'GD999-XXXX', '#1a73e8', 'star');
    }

    #[Test]
    public function setTagRejectsCompletedPastGame(): void
    {
        $this->pdoMock = $this->createMock(PDO::class);
        $checkStmt = $this->createStub(PDOStatement::class);
        $checkStmt->method('fetch')->willReturn([
            'id' => 'GD000-AAAA',
            'is_active' => false,
            'start_time' => date('Y-m-d H:i:s', strtotime('-40 days'))
        ]);

        $this->pdoMock->expects($this->once())
            ->method('prepare')
            ->willReturn($checkStmt);

        $service = new TagService($this->pdoMock, ['tags' => ['TAGS_ENABLED' => true]]);

        $this->expectException(InvalidArgumentException::class);
        $this->expectExceptionMessage('Tags cannot be modified for completed games.');

        $service->setTag(1, 'GD000-AAAA', '#1a73e8', 'star');
    }

    #[Test]
    public function setTagSucceedsInActiveGame(): void
    {
        $this->pdoMock = $this->createMock(PDO::class);
        $checkStmt = $this->createStub(PDOStatement::class);
        $checkStmt->method('fetch')->willReturn([
            'id' => 'GD001-AAAA',
            'is_active' => true,
            'start_time' => date('Y-m-d H:i:s', strtotime('-2 days')),
            'lat' => 43.1234,
            'lon' => -88.5678
        ]);

        $insertStmt = $this->createMock(PDOStatement::class);
        $insertStmt->expects($this->once())->method('execute');

        $this->pdoMock->expects($this->exactly(2))
            ->method('prepare')
            ->willReturnOnConsecutiveCalls($checkStmt, $insertStmt);

        $service = new TagService($this->pdoMock, ['tags' => ['TAGS_ENABLED' => true]]);
        $result = $service->setTag(1, 'GD001-AAAA', '#1a73e8', 'star');

        $this->assertEquals('success', $result['status']);
        $this->assertEquals('GD001-AAAA', $result['dashpoint_id']);
        $this->assertEquals('#1a73e8', $result['color']);
        $this->assertEquals('star', $result['shape']);
        $this->assertSame(43.1234, $result['lat']);
        $this->assertSame(-88.5678, $result['lon']);
    }

    #[Test]
    public function setTagSucceedsInPreviewGame(): void
    {
        $this->pdoMock = $this->createMock(PDO::class);
        $checkStmt = $this->createStub(PDOStatement::class);
        $checkStmt->method('fetch')->willReturn([
            'id' => 'GD002-AAAA',
            'is_active' => false,
            'start_time' => date('Y-m-d H:i:s', strtotime('+15 days')),
            'lat' => 43.9876,
            'lon' => -88.1234
        ]);

        $insertStmt = $this->createMock(PDOStatement::class);
        $insertStmt->expects($this->once())->method('execute');

        $this->pdoMock->expects($this->exactly(2))
            ->method('prepare')
            ->willReturnOnConsecutiveCalls($checkStmt, $insertStmt);

        $service = new TagService($this->pdoMock, ['tags' => ['TAGS_ENABLED' => true]]);
        $result = $service->setTag(1, 'GD002-AAAA', '#8e24aa', 'diamond');

        $this->assertEquals('success', $result['status']);
        $this->assertEquals('GD002-AAAA', $result['dashpoint_id']);
        $this->assertEquals('#8e24aa', $result['color']);
        $this->assertEquals('diamond', $result['shape']);
        $this->assertSame(43.9876, $result['lat']);
        $this->assertSame(-88.1234, $result['lon']);
    }

    #[Test]
    public function deleteTagRejectsCompletedPastGame(): void
    {
        $this->pdoMock = $this->createMock(PDO::class);
        $checkStmt = $this->createStub(PDOStatement::class);
        $checkStmt->method('fetch')->willReturn([
            'id' => 'GD000-AAAA',
            'is_active' => false,
            'start_time' => date('Y-m-d H:i:s', strtotime('-40 days')),
            'lat' => 43.0,
            'lon' => -88.0
        ]);

        $this->pdoMock->expects($this->once())
            ->method('prepare')
            ->willReturn($checkStmt);

        $service = new TagService($this->pdoMock, ['tags' => ['TAGS_ENABLED' => true]]);

        $this->expectException(InvalidArgumentException::class);
        $this->expectExceptionMessage('Tags cannot be modified for completed games.');

        $service->deleteTag(1, 'GD000-AAAA');
    }

    #[Test]
    public function deleteTagSucceedsInActiveGame(): void
    {
        $this->pdoMock = $this->createMock(PDO::class);
        $checkStmt = $this->createStub(PDOStatement::class);
        $checkStmt->method('fetch')->willReturn([
            'id' => 'GD001-AAAA',
            'is_active' => true,
            'start_time' => date('Y-m-d H:i:s', strtotime('-2 days')),
            'lat' => 43.1234,
            'lon' => -88.5678
        ]);

        $deleteStmt = $this->createMock(PDOStatement::class);
        $deleteStmt->expects($this->once())
            ->method('execute')
            ->with(['user_id' => 1, 'dashpoint_id' => 'GD001-AAAA']);

        $this->pdoMock->expects($this->exactly(2))
            ->method('prepare')
            ->willReturnOnConsecutiveCalls($checkStmt, $deleteStmt);

        $service = new TagService($this->pdoMock, ['tags' => ['TAGS_ENABLED' => true]]);
        $res = $service->deleteTag(1, 'GD001-AAAA');

        $this->assertTrue($res);
    }

    #[Test]
    public function purgeTagsForDashpointReturnsRowCount(): void
    {
        $this->pdoMock = $this->createMock(PDO::class);
        $stmtMock = $this->createMock(PDOStatement::class);
        $stmtMock->expects($this->once())
            ->method('execute')
            ->with(['dashpoint_id' => 'GD002-AAAA']);
        $stmtMock->expects($this->once())
            ->method('rowCount')
            ->willReturn(3);

        $this->pdoMock->expects($this->once())
            ->method('prepare')
            ->willReturn($stmtMock);

        $service = new TagService($this->pdoMock, ['tags' => ['TAGS_ENABLED' => true]]);
        $count = $service->purgeTagsForDashpoint('GD002-AAAA');

        $this->assertEquals(3, $count);
    }

    #[Test]
    public function generateETagIsDeterministicRegardlessOfKeyOrder(): void
    {
        $tagsA = [
            'GD001-AAAB' => ['color' => '#8e24aa', 'shape' => 'diamond'],
            'GD001-AAAA' => ['color' => '#1a73e8', 'shape' => 'star'],
        ];

        $tagsB = [
            'GD001-AAAA' => ['color' => '#1a73e8', 'shape' => 'star'],
            'GD001-AAAB' => ['color' => '#8e24aa', 'shape' => 'diamond'],
        ];

        $etagA = TagService::generateETag($tagsA);
        $etagB = TagService::generateETag($tagsB);

        $this->assertNotEmpty($etagA);
        $this->assertStringStartsWith('"', $etagA);
        $this->assertStringEndsWith('"', $etagA);
        $this->assertEquals($etagA, $etagB);
    }

    #[Test]
    public function generateETagDiffersWhenTagSetDiffers(): void
    {
        $tagsA = [
            'GD001-AAAA' => ['color' => '#1a73e8', 'shape' => 'star'],
        ];

        $tagsB = [
            'GD001-AAAA' => ['color' => '#8e24aa', 'shape' => 'diamond'],
        ];

        $tagsC = [];

        $etagA = TagService::generateETag($tagsA);
        $etagB = TagService::generateETag($tagsB);
        $etagC = TagService::generateETag($tagsC);

        $this->assertNotEquals($etagA, $etagB);
        $this->assertNotEquals($etagA, $etagC);
        $this->assertNotEquals($etagB, $etagC);
    }

    #[Test]
    public function constructorAppliesEnvironmentVariableOverridesWhenConfigIsNull(): void
    {
        putenv('TAGS_ENABLED=false');
        putenv('TAGS_ALLOWLIST=CustomTester,EnvUser');

        $service = new TagService($this->pdoMock);

        $this->assertTrue($service->isFeatureEnabledForUser('CustomTester'));
        $this->assertTrue($service->isFeatureEnabledForUser('envuser'));
        $this->assertFalse($service->isFeatureEnabledForUser('Stranger'));
    }
}
