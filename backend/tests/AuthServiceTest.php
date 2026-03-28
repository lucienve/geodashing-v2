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
        $this->pdoMock = $this->createStub(PDO::class);
        $this->authService = new AuthService($this->pdoMock);
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
            'password_hash' => $hash
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
            'password_hash' => $hash
        ]);
        
        $this->pdoMock->method('prepare')->willReturn($stmtMock);

        $result = $this->authService->login('Lucien', 'correct_password');
        
        // Assert explicit success returning the exact database identity context
        $this->assertEquals('success', $result['status']);
        $this->assertEquals(1, $result['user_id']);
    }
}
