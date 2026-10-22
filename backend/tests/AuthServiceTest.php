<?php

declare(strict_types=1);

namespace App\Tests;

use PDO;
use PDOException;
use PDOStatement;
use App\Services\AuthService;
use PHPUnit\Framework\TestCase;
use PHPUnit\Framework\Attributes\Test;
use PHPUnit\Framework\Attributes\CoversClass;

/**
 * AuthServiceTest
 *
 * Verifies core registration boundaries and login payload hashing validity constraints against mocked states.
 */
#[CoversClass(AuthService::class)]
class AuthServiceTest extends TestCase
{
    /**
     * @var PDO
     */
    private PDO $pdoMock;

    /**
     * @var AuthService
     */
    private AuthService $authService;

    /**
     * Sets up the test fixtures.
     */
    #[\Override]
    protected function setUp(): void
    {
        $this->pdoMock = $this->createStub(PDO::class);
        $this->authService = $this->createAuthServiceWithPdo($this->pdoMock);
    }

    /**
     * Creates an AuthService partial stub that bypasses executeMail.
     *
     * @param PDO $pdo The PDO stub or mock.
     * @return AuthService
     */
    private function createAuthServiceWithPdo(PDO $pdo): AuthService
    {
        $authService = $this->getStubBuilder(AuthService::class)
            ->setConstructorArgs([$pdo])
            ->onlyMethods(['executeMail'])
            ->getStub();
        $authService->method('executeMail')->willReturn(true);
        return $authService;
    }

    /**
     * Verifies signup rejects empty fields.
     */
    #[Test]
    public function signupRejectsEmptyFields(): void
    {
        $result = $this->authService->signup('', 'test@test.com', 'pass');
        $this->assertEquals('error', $result['status']);
        $this->assertEquals('All fields are required', $result['message']);
    }

    /**
     * Verifies signup handles duplicate users gracefully.
     */
    #[Test]
    public function signupHandlesDuplicateUsersSafely(): void
    {
        $stmtMock = $this->createStub(PDOStatement::class);
        // Feed the constraint violation error artificially
        $stmtMock->method('execute')->willThrowException(new PDOException("Duplicate entry", 23000));

        $this->pdoMock->method('prepare')->willReturn($stmtMock);

        $result = $this->authService->signup('Lucien', 'lucien@example.com', 'secure123');

        // Assert native response correctly shields HTTP code 500
        $this->assertEquals('error', $result['status']);
        $this->assertEquals('That username or email already exists', $result['message']);
    }

    /**
     * Verifies login rejects invalid passwords.
     */
    #[Test]
    public function loginRejectsInvalidPasswords(): void
    {
        $stmtMock = $this->createStub(PDOStatement::class);
        // Feed the mock an active user record attached to a standard bcrypt hash to test password_verify
        $hash = password_hash('correct_password', PASSWORD_DEFAULT);

        $stmtMock->method('fetch')->willReturn([
            'id' => 1,
            'username' => 'Lucien',
            'password_hash' => $hash,
            'is_verified' => 1
        ]);

        $this->pdoMock->method('prepare')->willReturn($stmtMock);

        $result = $this->authService->login('Lucien', 'wrong_password');

        $this->assertEquals('error', $result['status']);
        $this->assertEquals('Invalid credentials', $result['message']);
    }

    /**
     * Verifies login accepts valid credentials.
     */
    #[Test]
    public function loginAcceptsCorrectCredentials(): void
    {
        $stmtMock = $this->createStub(PDOStatement::class);

        $hash = password_hash('correct_password', PASSWORD_DEFAULT);
        $stmtMock->method('fetch')->willReturn([
            'id' => 1,
            'username' => 'Lucien',
            'password_hash' => $hash,
            'is_verified' => 0
        ]);

        $this->pdoMock->method('prepare')->willReturn($stmtMock);

        $result = $this->authService->login('Lucien', 'correct_password');

        // Assert explicit success returning the exact database identity context
        $this->assertEquals('success', $result['status']);
        $this->assertEquals(1, $result['user_id']);
        $this->assertEquals(0, $result['is_verified']);
    }

    /**
     * Verifies resendVerification rejects already verified users.
     */
    #[Test]
    public function resendVerificationRejectsAlreadyVerifiedUsers(): void
    {
        $stmtMock = $this->createStub(PDOStatement::class);
        $stmtMock->method('fetch')->willReturn([
            'email' => 'test@example.com',
            'is_verified' => 1,
            'verification_token' => null
        ]);

        $this->pdoMock->method('prepare')->willReturn($stmtMock);

        $result = $this->authService->resendVerification(1);

        $this->assertEquals('error', $result['status']);
        $this->assertEquals('Account is already verified.', $result['message']);
    }

    /**
     * Verifies resendVerification succeeds for unverified users.
     */
    #[Test]
    public function resendVerificationSucceedsForUnverifiedUsers(): void
    {
        $this->pdoMock = $this->createMock(PDO::class);
        $this->authService = $this->createAuthServiceWithPdo($this->pdoMock);

        $selectMock = $this->createStub(PDOStatement::class);
        $selectMock->method('fetch')->willReturn([
            'email' => 'test@example.com',
            'is_verified' => 0,
            'verification_token' => 'old_token'
        ]);

        $updateMock = $this->createMock(PDOStatement::class);
        $updateMock->expects($this->once())->method('execute')->willReturn(true);

        $this->pdoMock->expects($this->exactly(2))
            ->method('prepare')
            ->willReturnOnConsecutiveCalls($selectMock, $updateMock);

        $result = $this->authService->resendVerification(1);

        $this->assertEquals('success', $result['status']);
        $this->assertEquals('Verification email resent successfully.', $result['message']);
    }

    /**
     * Verifies signup saves the subscribe_group preference.
     */
    #[Test]
    public function signupSavesSubscribeGroupPreference(): void
    {
        $stmtMock = $this->createMock(PDOStatement::class);
        $stmtMock->expects($this->once())
            ->method('execute')
            ->with($this->callback(function (array $params): bool {
                return $params[':subscribe_group'] === 1;
            }))
            ->willReturn(true);

        $this->pdoMock->method('prepare')->willReturn($stmtMock);

        $result = $this->authService->signup('LucienSubscribe', 'lucien.sub@example.com', 'secure123', true);
        $this->assertEquals('success', $result['status']);
    }

    /**
     * Verifies verifyEmail returns the subscribe_group preference.
     */
    #[Test]
    public function verifyEmailReturnsSubscribeGroupPreference(): void
    {
        $this->pdoMock = $this->createMock(PDO::class);
        $this->authService = $this->createAuthServiceWithPdo($this->pdoMock);

        $selectMock = $this->createStub(PDOStatement::class);
        $selectMock->method('fetch')->willReturn([
            'id' => 42,
            'username' => 'Lucien',
            'email' => 'lucien@example.com',
            'subscribe_group' => 1
        ]);

        $updateMock = $this->createStub(PDOStatement::class);
        $updateMock->method('execute')->willReturn(true);

        $this->pdoMock->expects($this->exactly(2))
            ->method('prepare')
            ->willReturnOnConsecutiveCalls($selectMock, $updateMock);

        $result = $this->authService->verifyEmail('some_token');

        $this->assertEquals('success', $result['status']);
        $this->assertEquals(42, $result['user_id']);
        $this->assertEquals('Lucien', $result['username']);
        $this->assertEquals('lucien@example.com', $result['email']);
        $this->assertTrue($result['subscribe_group']);
    }
}
