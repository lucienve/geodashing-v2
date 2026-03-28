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
    session_start();
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
                // Clean the raw database keys out of the JSON response payload
                unset($result['user_id'], $result['username']); 
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
                unset($result['user_id'], $result['username']);
            } else {
                http_response_code(401);
            }
            echo json_encode($result);
            
        } elseif ($action === 'logout') {
            session_unset();
            session_destroy();
            echo json_encode(["status" => "success", "message" => "Logged out successfully"]);
            
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

        // Utilizing robust underlying native algorithm (bcrypt currently via PASSWORD_DEFAULT)
        $hash = password_hash($password, PASSWORD_DEFAULT);

        try {
            $stmt = $this->db->prepare("INSERT INTO users (username, email, password_hash) VALUES (:username, :email, :hash)");
            $stmt->execute([
                ':username' => $username,
                ':email' => $email,
                ':hash' => $hash
            ]);
            
            return [
                "status" => "success",
                "message" => "Signup successful",
                "user_id" => (int)$this->db->lastInsertId(),
                "username" => $username
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
            $stmt = $this->db->prepare("SELECT id, username, password_hash FROM users WHERE username = :username LIMIT 1");
            $stmt->execute([':username' => $username]);
            $user = $stmt->fetch(PDO::FETCH_ASSOC);

            // Execute time-safe, dictionary-resistant string compare natively via pass_verify
            if ($user && password_verify($password, $user['password_hash'])) {
                return [
                    "status" => "success",
                    "message" => "Login successful",
                    "user_id" => (int)$user['id'],
                    "username" => $user['username']
                ];
            }
            
            return ["status" => "error", "message" => "Invalid credentials"];
            
        } catch (PDOException $e) {
            error_log("Login Logic Error: " . $e->getMessage());
            return ["status" => "error", "message" => "Login failed due to internal server error"];
        }
    }
}
