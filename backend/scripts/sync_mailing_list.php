<?php

/**
 * Catch-up Mailing List Sync Utility
 *
 * Synchronizes verified players in the Geodashing database with the
 * dashers@geodashing.org Google Group mailing list.
 *
 * Usage:
 *   php backend/scripts/sync_mailing_list.php [options]
 *
 * Options:
 *   --dry-run        Preview synchronization plan without making changes (default)
 *   --execute        Execute synchronization: add members to group and update database
 *   --all-verified   Target all verified users (regardless of prior subscribe_group value)
 *   -h, --help       Display this help message
 *
 * @package Geodashing\Scripts
 */

declare(strict_types=1);

require_once __DIR__ . '/../../vendor/autoload.php';
require_once __DIR__ . '/../Database.php';

use App\Database;
use App\Services\GoogleGroupService;

// Ensure this script is only run via the command line interface
if (php_sapi_name() !== 'cli') {
    http_response_code(403);
    echo "This script can only be executed via the command line.\n";
    exit(1);
}

$shortOpts = "h";
$longOpts = [
    "help",
    "dry-run",
    "execute",
    "all-verified"
];

$options = getopt($shortOpts, $longOpts);

if (isset($options['h']) || isset($options['help'])) {
    echo <<<HELP
Geodashing Mailing List Catch-Up Synchronization Script

Usage:
  php backend/scripts/sync_mailing_list.php [options]

Options:
  --dry-run        Preview synchronization plan without making changes (default).
  --execute        Execute synchronization against Google Workspace Directory API and MySQL.
  --all-verified   Target all verified players (is_verified = 1). If omitted, targets
                   only verified players with subscribe_group = 1.
  -h, --help       Show this help message.

Examples:
  # Preview what would be synchronized for all verified users
  php backend/scripts/sync_mailing_list.php --dry-run --all-verified

  # Execute synchronization for all verified users
  php backend/scripts/sync_mailing_list.php --execute --all-verified

HELP;
    exit(0);
}

$isExecute = isset($options['execute']);
$isDryRun = isset($options['dry-run']) || !$isExecute;
$allVerified = isset($options['all-verified']);

$modeLabel = $isDryRun ? "DRY-RUN (Preview Mode)" : "EXECUTE (Live Mutation Mode)";

echo "====================================================================\n";
echo "Geodashing Mailing List Synchronization\n";
echo "Mode: {$modeLabel}\n";
echo "Scope: " . ($allVerified ? "All Verified Players (is_verified = 1)" : "Opted-in Verified Players (subscribe_group = 1)") . "\n";
echo "====================================================================\n\n";

try {
    // 1. Establish Database Connection
    echo "[1/4] Connecting to database...\n";
    $db = Database::getConnection();

    // 2. Fetch Group Members from Google Workspace
    echo "[2/4] Fetching current Google Group membership...\n";
    $groupService = new GoogleGroupService();
    $groupKey = $groupService->getGroupKey();
    $adminUser = $groupService->getAdminUser();

    echo "      Target Group: {$groupKey}\n";
    echo "      Admin User:   {$adminUser}\n";

    $rawMembers = $groupService->listMembers();
    $groupMemberMap = [];
    foreach ($rawMembers as $m) {
        $email = strtolower(trim((string) $m['email']));
        if ($email !== '') {
            $groupMemberMap[$email] = $m;
        }
    }
    echo "      Current Group Members: " . count($groupMemberMap) . "\n\n";

    // 3. Query Target Users from Database
    echo "[3/4] Querying verified players from database...\n";
    $sql = "SELECT id, username, email, is_verified, subscribe_group FROM users WHERE is_verified = 1";
    if (!$allVerified) {
        $sql .= " AND subscribe_group = 1";
    }
    $sql .= " ORDER BY email ASC";

    $stmt = $db->query($sql);
    $users = $stmt->fetchAll();
    echo "      Matching Verified Players in Database: " . count($users) . "\n\n";

    // 4. Analyze Discrepancies
    $alreadySubscribed = [];
    $toEnroll = [];
    $matchedEmails = [];

    foreach ($users as $user) {
        $userEmail = strtolower(trim((string) $user['email']));
        if (isset($groupMemberMap[$userEmail])) {
            $alreadySubscribed[] = $user;
            $matchedEmails[$userEmail] = true;
        } else {
            $toEnroll[] = $user;
        }
    }

    $externalMembers = [];
    foreach ($groupMemberMap as $email => $member) {
        if (!isset($matchedEmails[$email])) {
            $externalMembers[] = $member;
        }
    }

    // Display Comparison Summary
    echo "--------------------------------------------------------------------\n";
    echo "Synchronization Plan Summary:\n";
    echo "--------------------------------------------------------------------\n";
    echo "  Already in Google Group: " . count($alreadySubscribed) . "\n";
    echo "  Pending Enrollment:      " . count($toEnroll) . "\n";
    echo "  External / Other Group Members: " . count($externalMembers) . "\n\n";

    if (!empty($alreadySubscribed)) {
        echo "--- Already Subscribed Players (" . count($alreadySubscribed) . ") ---\n";
        foreach ($alreadySubscribed as $u) {
            echo "  [OK] {$u['email']} (User: {$u['username']})\n";
        }
        echo "\n";
    }

    if (!empty($toEnroll)) {
        echo "--- Pending Enrollment Players (" . count($toEnroll) . ") ---\n";
        foreach ($toEnroll as $u) {
            $optedStatus = !empty($u['subscribe_group']) ? "opted-in" : "not opted-in";
            echo "  [+]  {$u['email']} (User: {$u['username']}, DB status: {$optedStatus})\n";
        }
        echo "\n";
    }

    if (!empty($externalMembers)) {
        echo "--- External Group Members (not in matched player list) (" . count($externalMembers) . ") ---\n";
        foreach ($externalMembers as $m) {
            echo "  [*]  {$m['email']} (Role: {$m['role']}, Type: {$m['type']})\n";
        }
        echo "\n";
    }

    // 5. Execution or Dry-Run Exit
    if ($isDryRun) {
        echo "--------------------------------------------------------------------\n";
        echo "[DRY-RUN COMPLETE] No mutations were performed.\n";
        echo "To execute these changes, run with the --execute flag:\n";
        $executeCommand = "php backend/scripts/sync_mailing_list.php --execute";
        if ($allVerified) {
            $executeCommand .= " --all-verified";
        }
        echo "  {$executeCommand}\n";
        echo "--------------------------------------------------------------------\n";
        exit(0);
    }

    // Execute Enrollment Mutations
    echo "--------------------------------------------------------------------\n";
    echo "[EXECUTING MUTATIONS] Enrolling " . count($toEnroll) . " player(s)...\n";
    echo "--------------------------------------------------------------------\n";

    $successCount = 0;
    $failureCount = 0;

    $updateStmt = $db->prepare("UPDATE users SET subscribe_group = 1 WHERE id = :id");

    foreach ($toEnroll as $user) {
        $email = $user['email'];
        $username = $user['username'];
        $userId = (int) $user['id'];

        echo "  -> Enrolling {$email} ({$username})... ";

        try {
            $apiSuccess = $groupService->addMember($email);
            if ($apiSuccess) {
                // Update database subscribe_group flag
                $updateStmt->execute([':id' => $userId]);
                echo "SUCCESS\n";
                $successCount++;
            } else {
                echo "FAILED (API returned false)\n";
                $failureCount++;
            }
        } catch (Throwable $e) {
            echo "FAILED: " . $e->getMessage() . "\n";
            $failureCount++;
        }

        // Throttle requests slightly (100ms) to respect Google Workspace Directory API quotas
        usleep(100000);
    }

    echo "\n--------------------------------------------------------------------\n";
    echo "[EXECUTION COMPLETE]\n";
    echo "  Successfully enrolled: {$successCount}\n";
    echo "  Failures:              {$failureCount}\n";
    echo "--------------------------------------------------------------------\n";
} catch (Throwable $e) {
    echo "\n[ERROR] An unexpected error occurred: " . $e->getMessage() . "\n";
    exit(1);
}
