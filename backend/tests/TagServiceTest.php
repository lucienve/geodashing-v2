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

#[CoversClass(TagService::class)]
class TagServiceTest extends TestCase
{
    private $pdoMock;

    protected function setUp(): void
    {
        putenv('APP_ENV=testing');
        $_ENV['APP_ENV'] = 'testing';
        $this->pdoMock = $this->createMock(PDO::class);
    }

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
        $stmtMock = $this->createMock(PDOStatement::class);
        $stmtMock->expects($this->once())
            ->method('execute')
            ->with(['user_id' => 1, 'game_id' => 2]);
        $stmtMock->expects($this->once())
            ->method('fetchAll')
            ->with(PDO::FETCH_ASSOC)
            ->willReturn([
                ['dashpoint_id' => 'GD001-AAAA', 'color_code' => '#1a73e8', 'shape' => 'star'],
                ['dashpoint_id' => 'GD001-AAAB', 'color_code' => '#e64a19', 'shape' => 'triangle']
            ]);

        $this->pdoMock->expects($this->once())
            ->method('prepare')
            ->willReturn($stmtMock);

        $service = new TagService($this->pdoMock, ['tags' => ['TAGS_ENABLED' => true]]);
        $tags = $service->getTagsForUserAndGame(1, 2);

        $this->assertCount(2, $tags);
        $this->assertEquals(['color' => '#1a73e8', 'shape' => 'star'], $tags['GD001-AAAA']);
        $this->assertEquals(['color' => '#e64a19', 'shape' => 'triangle'], $tags['GD001-AAAB']);
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
        $checkStmt = $this->createMock(PDOStatement::class);
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
        $checkStmt = $this->createMock(PDOStatement::class);
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
        $checkStmt = $this->createMock(PDOStatement::class);
        $checkStmt->method('fetch')->willReturn([
            'id' => 'GD001-AAAA',
            'is_active' => true,
            'start_time' => date('Y-m-d H:i:s', strtotime('-2 days'))
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
    }

    #[Test]
    public function setTagSucceedsInPreviewGame(): void
    {
        $checkStmt = $this->createMock(PDOStatement::class);
        $checkStmt->method('fetch')->willReturn([
            'id' => 'GD002-AAAA',
            'is_active' => false,
            'start_time' => date('Y-m-d H:i:s', strtotime('+15 days'))
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
    }

    #[Test]
    public function deleteTagRejectsCompletedPastGame(): void
    {
        $checkStmt = $this->createMock(PDOStatement::class);
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

        $service->deleteTag(1, 'GD000-AAAA');
    }

    #[Test]
    public function deleteTagSucceedsInActiveGame(): void
    {
        $checkStmt = $this->createMock(PDOStatement::class);
        $checkStmt->method('fetch')->willReturn([
            'id' => 'GD001-AAAA',
            'is_active' => true,
            'start_time' => date('Y-m-d H:i:s', strtotime('-2 days'))
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
