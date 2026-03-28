<?php
session_start();
header('Content-Type: application/json');

// Pull in our previously made generic Database class
require_once __DIR__ . '/../Database.php';

$action = $_GET['action'] ?? '';

// Ensure we only process POST requests to this API for security
if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(["status" => "error", "message" => "Method not allowed"]);
    exit;
}

try {
    $db = Database::getConnection();
} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(["status" => "error", "message" => "Database connection failed"]);
    exit;
}

if ($action === 'signup') {
    $username = trim($_POST['username'] ?? '');
    $email = trim($_POST['email'] ?? '');
    $password = $_POST['password'] ?? '';

    if (empty($username) || empty($email) || empty($password)) {
        echo json_encode(["status" => "error", "message" => "All fields are required"]);
        exit;
    }

    // Securely hash the plain-text password utilizing bcrypt/Argon2i (Default PHP strategy)
    $hash = password_hash($password, PASSWORD_DEFAULT);

    try {
        // Strict use of prepared statements to explicitly prevent SQL injection
        $stmt = $db->prepare("INSERT INTO users (username, email, password_hash) VALUES (:username, :email, :hash)");
        $stmt->bindParam(':username', $username);
        $stmt->bindParam(':email', $email);
        $stmt->bindParam(':hash', $hash);
        $stmt->execute();
        
        // Auto-login the user immediately establishing a session state
        $_SESSION['user_id'] = $db->lastInsertId();
        $_SESSION['username'] = $username;
        
        echo json_encode(["status" => "success", "message" => "Signup successful"]);
        
    } catch (PDOException $e) {
        if ($e->getCode() == 23000) { // 23000 catches MySQL's Integrity constraint violations (UNIQUE keywords)
            echo json_encode(["status" => "error", "message" => "That username or email already exists"]);
        } else {
            error_log("Signup API Error: " . $e->getMessage());
            echo json_encode(["status" => "error", "message" => "Signup failed due to internal server error"]);
        }
    }
    
} elseif ($action === 'login') {
    $username = trim($_POST['username'] ?? '');
    $password = $_POST['password'] ?? '';

    try {
        // Query utilizing prepared parameters
        $stmt = $db->prepare("SELECT id, username, password_hash FROM users WHERE username = :username LIMIT 1");
        $stmt->bindParam(':username', $username);
        $stmt->execute();
        $user = $stmt->fetch();

        // Validate retrieved hash against raw input
        if ($user && password_verify($password, $user['password_hash'])) {
            $_SESSION['user_id'] = $user['id'];
            $_SESSION['username'] = $user['username'];
            echo json_encode(["status" => "success", "message" => "Login successful"]);
        } else {
            echo json_encode(["status" => "error", "message" => "Invalid credentials"]);
        }
        
    } catch (PDOException $e) {
        error_log("Login API Error: " . $e->getMessage());
        echo json_encode(["status" => "error", "message" => "Login failed due to internal server error"]);
    }
    
} elseif ($action === 'logout') {
    session_unset();
    session_destroy();
    echo json_encode(["status" => "success", "message" => "Logged out successfully"]);
    
} else {
    http_response_code(400);
    echo json_encode(["status" => "error", "message" => "Invalid action specified."]);
}
