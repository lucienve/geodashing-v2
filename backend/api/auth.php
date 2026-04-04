<?php
/**
 * Authentication API Endpoint
 *
 * Processes JSON user signups, logins, and logouts.
 *
 * @package Geodashing\API
 */

// Bypass procedural logic during PHPUnit inclusion
if (basename(__FILE__) === basename($_SERVER['PHP_SELF'] ?? '')) {
    require_once __DIR__ . '/../session.php';
    header('Content-Type: application/json');
    require_once __DIR__ . '/../Database.php';

    $action = $_GET['action'] ?? '';

    // Enforce POST
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
        http_response_code(405);
        echo json_encode(["status" => "error", "message" => "Method not allowed"]);
        exit;
    }

    try {
        $db = Database::getConnection();
        $authService = new AuthService($db);

        if ($action === 'signup') {
            $username = trim($_POST['username'] ?? '');
            $email = trim($_POST['email'] ?? '');
            $password = $_POST['password'] ?? '';

            $result = $authService->signup($username, $email, $password);

            // Auto sign-in
            if ($result['status'] === 'success') {
                $_SESSION['user_id'] = $result['user_id'];
                $_SESSION['username'] = $result['username'];
                $_SESSION['is_verified'] = $result['is_verified'];
                // Clean the raw database keys out of the JSON response payload
                unset($result['user_id'], $result['username'], $result['is_verified']);
            } else {
                http_response_code(400);
            }
            echo json_encode($result);

        } elseif ($action === 'login') {
            $username = trim($_POST['username'] ?? '');
            $password = $_POST['password'] ?? '';

            $result = $authService->login($username, $password);

            if ($result['status'] === 'success') {
                $_SESSION['user_id'] = $result['user_id'];
                $_SESSION['username'] = $result['username'];
                $_SESSION['is_verified'] = $result['is_verified'];
                unset($result['user_id'], $result['username'], $result['is_verified']);
            } else {
                http_response_code(401);
            }
            echo json_encode($result);

        } elseif ($action === 'logout') {
            session_unset();
            session_destroy();
            echo json_encode(["status" => "success", "message" => "Logged out successfully"]);

        } elseif ($action === 'resend_verification') {
            // Securely demand a populated active session dynamically preventing spam hooks
            if (!isset($_SESSION['user_id'])) {
                http_response_code(401);
                echo json_encode(["status" => "error", "message" => "Unauthorized access."]);
                exit;
            }

            // Check if they are already formally verified preventing mail relays
            if (isset($_SESSION['is_verified']) && $_SESSION['is_verified']) {
                echo json_encode(["status" => "error", "message" => "Account is already verified."]);
                exit;
            }

            // Ping the AuthService to fire the relay
            $result = $authService->resendVerification((int) $_SESSION['user_id']);
            if ($result['status'] !== 'success') {
                http_response_code(500);
            }
            echo json_encode($result);

        } elseif ($action === 'forgot_password') {
            $username = trim($_POST['username'] ?? '');
            if (empty($username)) {
                http_response_code(400);
                echo json_encode(["status" => "error", "message" => "Username is required"]);
                exit;
            }
            $result = $authService->forgotPassword($username);
            if ($result['status'] !== 'success')
                http_response_code(400);
            echo json_encode($result);

        } elseif ($action === 'reset_password') {
            $token = trim($_POST['token'] ?? '');
            $password = $_POST['password'] ?? '';
            if (empty($token) || empty($password)) {
                http_response_code(400);
                echo json_encode(["status" => "error", "message" => "Token and new password required"]);
                exit;
            }
            $result = $authService->resetPassword($token, $password);
            if ($result['status'] !== 'success')
                http_response_code(400);
            echo json_encode($result);

        } elseif ($action === 'session') {
            // Native session state retrieval explicitly mapping memory back to the SPA
            if (isset($_SESSION['user_id']) && isset($_SESSION['username'])) {
                echo json_encode([
                    "status" => "success",
                    "user_id" => $_SESSION['user_id'],
                    "username" => $_SESSION['username'],
                    "is_verified" => $_SESSION['is_verified'] ?? 0
                ]);
            } else {
                http_response_code(401);
                echo json_encode(["status" => "error", "message" => "No active session"]);
            }

        } else {
            http_response_code(400);
            echo json_encode(["status" => "error", "message" => "Invalid action specified."]);
        }

    } catch (Exception $e) {
        error_log("Auth API Error: " . $e->getMessage());
        http_response_code(500);
        echo json_encode(["status" => "error", "message" => "Internal server error"]);
    }
}

/**
 * Class AuthService
 *
 * Encapsulates the core business logic required for verifying credentials,
 * hashing passwords, and persisting new User signups securely via PDO.
 */
class AuthService
{
    /**
     * @var PDO The configured database connection.
     */
    private PDO $db;

    /**
     * Constructor.
     *
     * @param PDO $db The PDO connection instance.
     */
    public function __construct(PDO $db)
    {
        $this->db = $db;
    }

    /**
     * securely hashes and inserts a new player's profile into tracking.
     *
     * @param string $username The unique vanity handle.
     * @param string $email    A legitimate email address.
     * @param string $password The raw, un-hashed plaintext password.
     *
     * @return array Standardized JSON-ready map containing explicit error/success states.
     */
    public function signup(string $username, string $email, string $password): array
    {
        if (empty($username) || empty($email) || empty($password)) {
            return ["status" => "error", "message" => "All fields are required"];
        }

        if (!filter_var($email, FILTER_VALIDATE_EMAIL)) {
            return ["status" => "error", "message" => "Invalid email format. Please provide a structurally valid email address."];
        }

        // Utilizing robust underlying native algorithm (bcrypt currently via PASSWORD_DEFAULT)
        $hash = password_hash($password, PASSWORD_DEFAULT);

        $token = bin2hex(random_bytes(32));

        try {
            $stmt = $this->db->prepare("INSERT INTO users (username, email, password_hash, is_verified, verification_token) VALUES (:username, :email, :hash, 0, :token)");
            $stmt->execute([
                ':username' => $username,
                ':email' => $email,
                ':hash' => $hash,
                ':token' => $token
            ]);

            $this->sendVerificationEmail($email, $token);

            return [
                "status" => "success",
                "message" => "Signup successful. Verification email sent.",
                "user_id" => (int) $this->db->lastInsertId(),
                "username" => $username,
                "is_verified" => 0
            ];

        } catch (PDOException $e) {
            if ($e->getCode() == 23000) { // Catch MySQL unique constraint violations natively against user data
                return ["status" => "error", "message" => "That username or email already exists"];
            }
            // Bubble to raw error_log
            error_log("Signup Logic Error: " . $e->getMessage());
            return ["status" => "error", "message" => "Signup failed due to internal server error"];
        }
    }

    /**
     * Queries database by user identifier and securely verifies against their hashed payload.
     *
     * @param string $username Standard lookup key.
     * @param string $password The raw claimed identity password.
     *
     * @return array Standardized execution state graph payload.
     */
    public function login(string $username, string $password): array
    {
        if (empty($username) || empty($password)) {
            return ["status" => "error", "message" => "All fields are required"];
        }

        try {
            $stmt = $this->db->prepare("SELECT id, username, password_hash, is_verified FROM users WHERE username = :username LIMIT 1");
            $stmt->execute([':username' => $username]);
            $user = $stmt->fetch(PDO::FETCH_ASSOC);

            // Execute time-safe, dictionary-resistant string compare natively via pass_verify
            if ($user && password_verify($password, $user['password_hash'])) {
                return [
                    "status" => "success",
                    "message" => "Login successful",
                    "user_id" => (int) $user['id'],
                    "username" => $user['username'],
                    "is_verified" => (int) $user['is_verified']
                ];
            }

            return ["status" => "error", "message" => "Invalid credentials"];

        } catch (PDOException $e) {
            error_log("Login Logic Error: " . $e->getMessage());
            return ["status" => "error", "message" => "Login failed due to internal server error"];
        }
    }

    /**
     * Resends the verification email, optionally regenerating the token.
     *
     * @param int $userId The authenticated user's ID
     * @return array Status array
     */
    public function resendVerification(int $userId): array
    {
        try {
            // Check if user exists and get current status
            $stmt = $this->db->prepare("SELECT email, is_verified, verification_token FROM users WHERE id = :id LIMIT 1");
            $stmt->execute([':id' => $userId]);
            $user = $stmt->fetch(PDO::FETCH_ASSOC);

            if (!$user) {
                return ["status" => "error", "message" => "User not found."];
            }

            if ($user['is_verified']) {
                return ["status" => "error", "message" => "Account is already verified."];
            }

            // Optional: Regenerate token to prevent stale links
            $token = bin2hex(random_bytes(32));
            $updateStmt = $this->db->prepare("UPDATE users SET verification_token = :token WHERE id = :id");
            $updateStmt->execute([':token' => $token, ':id' => $userId]);

            $this->sendVerificationEmail($user['email'], $token);

            return ["status" => "success", "message" => "Verification email resent successfully."];

        } catch (PDOException $e) {
            error_log("Resend Verification Error: " . $e->getMessage());
            return ["status" => "error", "message" => "Failed to resend email."];
        }
    }

    /**
     * Helper routine to construct and explicitly dispatch the Geodashing.org Verification Email.
     * 
     * @param string $email
     * @param string $token
     */
    private function sendVerificationEmail(string $email, string $token): void
    {
        $verifyLink = "https://geodashing.org/backend/api/verify.php?token=" . $token;
        $subject = "Verify your account on Geodashing V2";
        $message = "Welcome to Geodashing V2!\n\nPlease finalize your account registration by clicking the link natively below:\n\n" . $verifyLink . "\n\nWelcome to the game!";

        $headers = "From: no-reply@geodashing.org\r\n";
        $headers .= "Reply-To: no-reply@geodashing.org\r\n";
        $headers .= "X-Mailer: PHP/" . phpversion();

        // The 5th parameter securely overrides the 'MAIL FROM' Envelope Sender dynamically bypassing Postfix default arrays!
        $this->executeMail($email, $subject, $message, $headers, "-fno-reply@geodashing.org");
    }

    /**
     * Issues a time-bound cryptographically secure Reset Token for the User.
     * 
     * @param string $username
     * @return array Status array
     */
    public function forgotPassword(string $username): array
    {
        try {
            $stmt = $this->db->prepare("SELECT id, email FROM users WHERE username = :username LIMIT 1");
            $stmt->execute([':username' => $username]);
            $user = $stmt->fetch(PDO::FETCH_ASSOC);

            // Obfuscate success natively preventing account enumeration algorithms
            if (!$user) {
                return ["status" => "success", "message" => "If that username matches our records, an email has been deployed."];
            }

            // Generate a secure 64-char token
            $resetToken = bin2hex(random_bytes(32));

            // Expire in one hour
            $updateStmt = $this->db->prepare("UPDATE users SET reset_token = :token, reset_token_expires = DATE_ADD(NOW(), INTERVAL 1 HOUR) WHERE id = :id");
            $updateStmt->execute([':token' => $resetToken, ':id' => $user['id']]);

            $this->sendPasswordResetEmail($user['email'], $resetToken, $username);

            return ["status" => "success", "message" => "If that username matches our records, an email has been deployed."];

        } catch (PDOException $e) {
            error_log("Forgot Password Error: " . $e->getMessage());
            return ["status" => "error", "message" => "Internal server array failure."];
        }
    }

    /**
     * Helper routine to explicitly dispatch the Password Reset Email.
     * 
     * @param string $email
     * @param string $token
     * @param string $username
     */
    private function sendPasswordResetEmail(string $email, string $token, string $username): void
    {
        // Route purely to the frontend parameter architecture where the `#login` controller dynamically intercepts the payload
        $resetLink = "https://geodashing.org/#login?reset_token=" . $token;

        $subject = "Password Reset Request for Geodashing V2";
        $message = "Hello " . $username . ",\n\nWe received a request to reset your password on Geodashing V2.\n\n";
        $message .= "If you did not make this request, please safely ignore this email.\n\n";
        $message .= "Otherwise, physically click the highly-secure link below to establish a new credential:\n\n";
        $message .= $resetLink . "\n\n";
        $message .= "This link algorithmically expires in exactly 1 hour for your protection.";

        $headers = "From: no-reply@geodashing.org\r\n";
        $headers .= "Reply-To: no-reply@geodashing.org\r\n";
        $headers .= "X-Mailer: PHP/" . phpversion();

        $this->executeMail($email, $subject, $message, $headers, "-fno-reply@geodashing.org");
    }

    /**
     * Executes the physical mail payload. Protected specifically to allow PHPUnit mocking.
     */
    protected function executeMail(string $to, string $subject, string $message, string $headers, string $additional_params): bool
    {
        return @mail($to, $subject, $message, $headers, $additional_params);
    }

    /**
     * Executes the mechanical password override tracking validation metrics strictly natively.
     * 
     * @param string $token
     * @param string $newPassword
     * @return array Status array
     */
    public function resetPassword(string $token, string $newPassword): array
    {
        if (strlen($newPassword) < 6) {
            return ["status" => "error", "message" => "Password must logically exceed 6 characters."];
        }

        try {
            // Guarantee exactly one match checking both structurally and temporally natively
            $stmt = $this->db->prepare("SELECT id FROM users WHERE reset_token = :token AND reset_token_expires > NOW() LIMIT 1");
            $stmt->execute([':token' => $token]);
            $user = $stmt->fetch(PDO::FETCH_ASSOC);

            if (!$user) {
                return ["status" => "error", "message" => "Reset token is invalid or mathematically expired."];
            }

            // Mathematically execute password rotation locking out previous hashes
            $newHash = password_hash($newPassword, PASSWORD_DEFAULT);
            $updateStmt = $this->db->prepare("UPDATE users SET password_hash = :hash, reset_token = NULL, reset_token_expires = NULL WHERE id = :id");
            $updateStmt->execute([':hash' => $newHash, ':id' => $user['id']]);

            return ["status" => "success", "message" => "Password physically updated! You may now login."];

        } catch (PDOException $e) {
            error_log("Reset Password Error: " . $e->getMessage());
            return ["status" => "error", "message" => "Server logic array crashed."];
        }
    }
}
