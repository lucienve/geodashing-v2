<?php

declare(strict_types=1);

namespace App\Tests;

use PHPUnit\Framework\TestCase;
use PHPUnit\Framework\Attributes\Test;
use PHPUnit\Framework\Attributes\CoversClass;
use App\Services\RerollService;
use App\Services\GeoContextService;
use PDO;
use PDOStatement;
use Exception;

#[CoversClass(RerollService::class)]
class RerollServiceTest extends TestCase
{
    private $pdoMock;
    private array $testConfig = [
        'reroll' => [
            'REROLL_ENABLED' => true,
            'REROLL_MAX_RADIUS_KM' => 10.0,
            'REROLL_MAX_PER_PLAYER' => 3,
            'REROLL_NOTIFICATION_EMAIL' => 'test@example.com',
        ],
    ];

    protected function setUp(): void
    {
        putenv('APP_ENV=testing');
        $_ENV['APP_ENV'] = 'testing';
        $this->pdoMock = $this->createMock(PDO::class);
    }

    #[Test]
    public function rerollFailsWhenFeatureDisabled(): void
    {
        $disabledConfig = [
            'reroll' => [
                'REROLL_ENABLED' => false,
            ],
        ];
        $service = new RerollService($this->pdoMock, null, $disabledConfig);

        $this->expectException(Exception::class);
        $this->expectExceptionMessage('Dashpoint rerolling is currently disabled.');

        $service->rerollDashpoint(1, 'GD002-AAAA', 'Inaccessible location');
    }

    #[Test]
    public function rerollFailsWhenUserHasZeroFinds(): void
    {
        $userStmt = $this->createMock(PDOStatement::class);
        $userStmt->method('fetch')->willReturn(['username' => 'TestUser']);

        $findsStmt = $this->createMock(PDOStatement::class);
        $findsStmt->method('fetch')->willReturn(['find_count' => 0]);

        $this->pdoMock->method('prepare')->willReturnCallback(function ($sql) use ($userStmt, $findsStmt) {
            if (str_contains($sql, 'FROM users')) {
                return $userStmt;
            }
            if (str_contains($sql, 'FROM visits')) {
                return $findsStmt;
            }
            return $this->createMock(PDOStatement::class);
        });

        $service = new RerollService($this->pdoMock, null, $this->testConfig);

        $this->expectException(Exception::class);
        $this->expectExceptionMessage('You must have logged at least 1 verified find');

        $service->rerollDashpoint(1, 'GD002-AAAA', 'Inaccessible location');
    }

    #[Test]
    public function rerollFailsWhenGameIsActive(): void
    {
        $userStmt = $this->createMock(PDOStatement::class);
        $userStmt->method('fetch')->willReturn(['username' => 'TestUser']);

        $findsStmt = $this->createMock(PDOStatement::class);
        $findsStmt->method('fetch')->willReturn(['find_count' => 5]);

        $dpStmt = $this->createMock(PDOStatement::class);
        $dpStmt->method('fetch')->willReturn([
            'id' => 'GD001-AAAA',
            'game_id' => 2,
            'lat' => 40.7128,
            'lon' => -74.0060,
            'start_time' => date('Y-m-d H:i:s', strtotime('-1 day')),
            'end_time' => date('Y-m-d H:i:s', strtotime('+30 days')),
            'is_active' => 1
        ]);

        $this->pdoMock->method('prepare')->willReturnCallback(function ($sql) use ($userStmt, $findsStmt, $dpStmt) {
            if (str_contains($sql, 'FROM users')) {
                return $userStmt;
            }
            if (str_contains($sql, 'FROM visits')) {
                return $findsStmt;
            }
            if (str_contains($sql, 'FROM dashpoints')) {
                return $dpStmt;
            }
            return $this->createMock(PDOStatement::class);
        });

        $service = new RerollService($this->pdoMock, null, $this->testConfig);

        $this->expectException(Exception::class);
        $this->expectExceptionMessage('Dashpoints can only be rerolled while the game is in preview.');

        $service->rerollDashpoint(1, 'GD001-AAAA', 'Inaccessible location');
    }

    #[Test]
    public function rerollFailsWhenDashpointAlreadyRerolled(): void
    {
        $userStmt = $this->createMock(PDOStatement::class);
        $userStmt->method('fetch')->willReturn(['username' => 'TestUser']);

        $findsStmt = $this->createMock(PDOStatement::class);
        $findsStmt->method('fetch')->willReturn(['find_count' => 5]);

        $dpStmt = $this->createMock(PDOStatement::class);
        $dpStmt->method('fetch')->willReturn([
            'id' => 'GD002-AAAA',
            'game_id' => 3,
            'lat' => 48.8566,
            'lon' => 2.3522,
            'start_time' => date('Y-m-d H:i:s', strtotime('+30 days')),
            'end_time' => date('Y-m-d H:i:s', strtotime('+60 days')),
            'is_active' => 0
        ]);

        $dpRerollsStmt = $this->createMock(PDOStatement::class);
        $dpRerollsStmt->method('fetch')->willReturn(['reroll_count' => 1]);

        $this->pdoMock->method('prepare')->willReturnCallback(
            function ($sql) use ($userStmt, $findsStmt, $dpStmt, $dpRerollsStmt) {
                if (str_contains($sql, 'FROM users')) {
                    return $userStmt;
                }
                if (str_contains($sql, 'FROM visits')) {
                    return $findsStmt;
                }
                if (str_contains($sql, 'FROM dashpoints d')) {
                    return $dpStmt;
                }
                if (str_contains($sql, 'WHERE dashpoint_id = :dashpoint_id')) {
                    return $dpRerollsStmt;
                }
                return $this->createMock(PDOStatement::class);
            }
        );

        $service = new RerollService($this->pdoMock, null, $this->testConfig);

        $this->expectException(Exception::class);
        $this->expectExceptionMessage('This dashpoint has already been rerolled during preview.');

        $service->rerollDashpoint(1, 'GD002-AAAA', 'Inaccessible location');
    }

    #[Test]
    public function rerollSuccess(): void
    {
        $userStmt = $this->createMock(PDOStatement::class);
        $userStmt->method('fetch')->willReturn(['username' => 'TestUser']);

        $findsStmt = $this->createMock(PDOStatement::class);
        $findsStmt->method('fetch')->willReturn(['find_count' => 3]);

        $dpStmt = $this->createMock(PDOStatement::class);
        $dpStmt->method('fetch')->willReturn([
            'id' => 'GD002-AAAA',
            'game_id' => 3,
            'lat' => 48.8566,
            'lon' => 2.3522,
            'start_time' => date('Y-m-d H:i:s', strtotime('+30 days')),
            'end_time' => date('Y-m-d H:i:s', strtotime('+60 days')),
            'is_active' => 0
        ]);

        $dpRerollsStmt = $this->createMock(PDOStatement::class);
        $dpRerollsStmt->method('fetch')->willReturn(['reroll_count' => 0]);

        $userRerollsStmt = $this->createMock(PDOStatement::class);
        $userRerollsStmt->method('fetch')->willReturn(['user_reroll_count' => 1]);

        $execStmt = $this->createMock(PDOStatement::class);
        $execStmt->method('execute')->willReturn(true);

        $this->pdoMock->method('prepare')->willReturnCallback(
            function ($sql) use ($userStmt, $findsStmt, $dpStmt, $dpRerollsStmt, $userRerollsStmt, $execStmt) {
                if (str_contains($sql, 'FROM users')) {
                    return $userStmt;
                }
                if (str_contains($sql, 'FROM visits')) {
                    return $findsStmt;
                }
                if (str_contains($sql, 'FROM dashpoints d')) {
                    return $dpStmt;
                }
                if (str_contains($sql, 'WHERE dashpoint_id = :dashpoint_id')) {
                    return $dpRerollsStmt;
                }
                if (str_contains($sql, 'WHERE user_id = :user_id AND game_id = :game_id')) {
                    return $userRerollsStmt;
                }
                return $execStmt;
            }
        );

        $geoMock = $this->createMock(GeoContextService::class);
        $geoMock->method('getDashpointContext')->willReturn('Mocked GeoContext');

        $service = new class ($this->pdoMock, $geoMock, $this->testConfig) extends RerollService {
            protected function executePythonRerollScript(float $origLat, float $origLon, float $maxRadiusKm): array
            {
                return [
                    'status' => 'success',
                    'lat' => 48.8600,
                    'lon' => 2.3600
                ];
            }
        };

        $result = $service->rerollDashpoint(1, 'GD002-AAAA', 'Inaccessible location');

        $this->assertEquals('success', $result['status']);
        $this->assertEquals('GD002-AAAA', $result['dashpoint_id']);
        $this->assertEquals(48.8600, $result['new_lat']);
        $this->assertEquals(2.3600, $result['new_lon']);
        $this->assertEquals(1, $result['rerolls_left']);
        $this->assertEquals(3, $result['max_rerolls']);
    }

    #[Test]
    public function rerollFailsWhenReasonIsEmpty(): void
    {
        $service = new RerollService($this->pdoMock, null, $this->testConfig);

        $this->expectException(Exception::class);
        $this->expectExceptionMessage('Reroll reason is required.');

        $service->rerollDashpoint(1, 'GD002-AAAA', '   ');
    }

    #[Test]
    public function rerollFailsWhenReasonTooLong(): void
    {
        $service = new RerollService($this->pdoMock, null, $this->testConfig);

        $this->expectException(Exception::class);
        $this->expectExceptionMessage('Reroll reason must be less than 100 characters.');
        $longReason = str_repeat('a', 100);
        $service->rerollDashpoint(1, 'GD002-AAAA', $longReason);
    }

    #[Test]
    public function resolveUvBinaryFromConfigSection(): void
    {
        $configWithUv = [
            'config' => [
                'UV_BIN' => '/custom/path/to/uv',
            ],
        ];
        $service = new RerollService($this->pdoMock, null, $configWithUv);
        $this->assertEquals('/custom/path/to/uv', $service->resolveUvBinary());
    }

    #[Test]
    public function buildRerollCommandUsesUvAndOutputFile(): void
    {
        $configWithUv = [
            'config' => [
                'UV_BIN' => '/custom/uv',
            ],
        ];
        $service = new RerollService($this->pdoMock, null, $configWithUv);
        $cmd = $service->buildRerollCommand(51.5074, -0.1278, 10.0, '/tmp/test_out.json');

        $this->assertStringContainsString('/custom/uv', $cmd);
        $this->assertStringContainsString('run --project', $cmd);
        $this->assertStringContainsString('UV_CACHE_DIR=/tmp/uv-cache', $cmd);
        $this->assertStringContainsString('--output-file', $cmd);
        $this->assertStringContainsString('/tmp/test_out.json', $cmd);
    }
}
