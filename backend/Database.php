<?php

declare(strict_types=1);

namespace App;

use PDO;
use Exception;

class Database
{
    private static $pdo = null;

    /**
     * Initializes and returns the PDO connection to MySQL.
     * Implements a singleton pattern to reuse the same connection.
     *
     * @return PDO
     * @throws Exception If connection fails or config is missing.
     */
    public static function getConnection()
    {
        if (self::$pdo === null) {
            $configPath = __DIR__ . '/config.ini';

            if (!file_exists($configPath)) {
                throw new Exception("Configuration file not found. Ensure backend/config.ini exists.");
            }

            $config = parse_ini_file($configPath);
            if ($config === false) {
                throw new Exception("Error parsing the configuration file.");
            }

            // Intercept credentials securely for the E2E testing framework
            if ((getenv('APP_ENV') ?: ($_ENV['APP_ENV'] ?? '')) === 'testing') {
                $host = getenv('DB_HOST') ?: '127.0.0.1';
                $port = getenv('DB_PORT') ?: ($config['DB_PORT'] ?? '3306');
                $db   = 'geodashing_test';
                $user = 'geodashing_test';
                $pass = 'geodashing_test_secure_pass';
            } else {
                $host = $config['DB_HOST'] ?? '127.0.0.1';
                $port = $config['DB_PORT'] ?? '3306';
                $db   = $config['DB_NAME'] ?? 'geodashing';
                $user = $config['DB_USER'] ?? 'geodashing';
                $pass = $config['DB_PASS'] ?? '';
            }
            $charset = 'utf8mb4';

            $dsn = "mysql:host=$host;port=$port;dbname=$db;charset=$charset";

            $options = [
                PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION, // Throw exceptions on SQL errors
                PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,       // Return associative arrays by default
                PDO::ATTR_EMULATE_PREPARES   => false,                  // Use native prepared statements for security
            ];

            try {
                self::$pdo = new PDO($dsn, $user, $pass, $options);
            } catch (\PDOException $e) {
                // Log strictly internally, throw a generic exception to avoid leaking credentials
                error_log("Database Connection Error: " . $e->getMessage());
                throw new \Exception("Database connection failed. Please check the server logs.");
            }
        }

        return self::$pdo;
    }
}
