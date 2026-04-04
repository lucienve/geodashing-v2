<?php
use PHPUnit\Framework\TestCase;

require_once __DIR__ . '/../api/auth.php';

use PHPUnit\Framework\Attributes\Test;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\Attributes\AllowMockObjectsWithoutExpectations;

/**
 * AuthServiceTest
 *
 * Verifies core registration boundaries and login payload hashing validity constraints natively against mocked states.
 */
#[CoversClass(AuthService::class)]
#[AllowMockObjectsWithoutExpectations]
class AuthServiceTest extends TestCase
{
    private $pdoMock;
    private $authService;

    protected function setUp(): void
    {
        $this->pdoMock = $this->createMock(PDO::class);
        
        // Instantiate a partial mock exclusively locking out the physical mail router
        $this->authService = $this->getMockBuilder(AuthService::class)
            ->setConstructorArgs([$this->pdoMock])
            ->onlyMethods(['executeMail'])
            ->getMock();
            
        // Globally nullify side-effects by forcing true return silently
        $this->authService->method('executeMail')->willReturn(true);
    }

    #[Test]
    public function signupRejectsEmptyFields()
    {
        $result = $this->authService->signup('', 'test@test.com', 'pass');
        $this->assertEquals('error', $result['status']);
        $this->assertEquals('All fields are required', $result['message']);
    }

    #[Test]
    public function signupHandlesDuplicateUsersSafely()
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

    #[Test]
    public function loginRejectsInvalidPasswords()
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

    #[Test]
    public function loginAcceptsCorrectCredentials()
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

    #[Test]
    public function resendVerificationRejectsAlreadyVerifiedUsers()
    {
        $stmtMock = $this->createMock(PDOStatement::class);
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

    #[Test]
    public function resendVerificationSucceedsForUnverifiedUsers()
    {
        $selectMock = $this->createMock(PDOStatement::class);
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
}
