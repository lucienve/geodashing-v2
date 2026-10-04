<?php

declare(strict_types=1);

namespace App\Services;

use Google_Client;
use Google_Service_Directory;
use Google_Service_Directory_Member;
use Google_Service_Exception;
use Throwable;

/**
 * Class GoogleGroupService
 *
 * Encapsulates Google Workspace Directory API operations to manage Google Group memberships
 * using service account credentials with Domain-Wide Delegation.
 */
class GoogleGroupService
{
    private ?Google_Service_Directory $directory;
    private string $groupKey;
    private string $adminUser;
    private ?string $credentialsPath;

    /**
     * GoogleGroupService constructor.
     *
     * @param Google_Service_Directory|null $directory Optional injected directory service for unit testing.
     * @param array|null $config Optional injected configuration array.
     */
    public function __construct(?Google_Service_Directory $directory = null, ?array $config = null)
    {
        $this->directory = $directory;

        if ($config === null) {
            $configPath = __DIR__ . '/../config.ini';
            $parsed = file_exists($configPath) ? @parse_ini_file($configPath) : false;
            $config = $parsed !== false ? $parsed : [];
        }

        $this->groupKey = $config['GOOGLE_GROUP_KEY']
            ?? $config['MAILING_LIST_ADDRESS']
            ?? 'dashers@geodashing.org';

        $this->adminUser = $config['GOOGLE_GROUP_ADMIN_USER']
            ?? 'tracker@geodashing.org';

        $envCredentials = getenv('GOOGLE_APPLICATION_CREDENTIALS');
        $this->credentialsPath = $config['GOOGLE_APPLICATION_CREDENTIALS']
            ?? ($envCredentials !== false ? $envCredentials : null);
    }

    /**
     * Initializes the underlying Google Directory service client if not already injected.
     *
     * @return bool True if directory service is available, false otherwise.
     */
    private function ensureClientInitialized(): bool
    {
        if ($this->directory !== null) {
            return true;
        }

        if (!$this->credentialsPath || !file_exists($this->credentialsPath)) {
            error_log("GoogleGroupService: Credentials path not found or unreadable: " . ($this->credentialsPath ?? 'null'));
            return false;
        }

        try {
            $client = new Google_Client();
            $client->setAuthConfig($this->credentialsPath);
            $client->addScope(Google_Service_Directory::ADMIN_DIRECTORY_GROUP_MEMBER);
            $client->setSubject($this->adminUser);

            $this->directory = new Google_Service_Directory($client);
            return true;
        } catch (Throwable $e) {
            error_log("GoogleGroupService: Failed to initialize client: " . $e->getMessage());
            return false;
        }
    }

    /**
     * Subscribes a user email address to the Google Group.
     *
     * @param string $email The target user email address.
     * @param string $delivery Optional delivery preference (default: 'ALL_MAIL').
     * @return bool True on successful addition or if member already exists (idempotent), false on failure.
     */
    public function addMember(string $email, string $delivery = 'ALL_MAIL'): bool
    {
        $normalizedEmail = strtolower(trim($email));
        if (!filter_var($normalizedEmail, FILTER_VALIDATE_EMAIL)) {
            error_log("GoogleGroupService: Cannot add invalid email address: $email");
            return false;
        }

        // Bypass live external API during test runs when no mock service was injected
        if ($this->directory === null && (getenv('APP_ENV') ?: ($_ENV['APP_ENV'] ?? '')) === 'testing') {
            error_log("APP_ENV=testing: Suppressed adding $normalizedEmail to {$this->groupKey}");
            return true;
        }

        if (!$this->ensureClientInitialized()) {
            return false;
        }

        try {
            $member = new Google_Service_Directory_Member([
                'email' => $normalizedEmail,
                'role' => 'MEMBER',
                'delivery_settings' => $delivery,
            ]);

            $this->directory->members->insert($this->groupKey, $member);
            return true;
        } catch (Google_Service_Exception $e) {
            if ($e->getCode() === 409) {
                // Member is already enrolled in the group; treat as idempotent success
                error_log("GoogleGroupService: $normalizedEmail is already a member of {$this->groupKey}");
                return true;
            }
            error_log("GoogleGroupService: API error adding $normalizedEmail: " . $e->getMessage());
            return false;
        } catch (Throwable $e) {
            error_log("GoogleGroupService: Unexpected error adding $normalizedEmail: " . $e->getMessage());
            return false;
        }
    }

    /**
     * Unsubscribes a user email address from the Google Group.
     *
     * @param string $email The target user email address.
     * @return bool True on successful removal or if member is not present (idempotent), false on failure.
     */
    public function removeMember(string $email): bool
    {
        $normalizedEmail = strtolower(trim($email));
        if (!filter_var($normalizedEmail, FILTER_VALIDATE_EMAIL)) {
            error_log("GoogleGroupService: Cannot remove invalid email address: $email");
            return false;
        }

        // Bypass live external API during test runs when no mock service was injected
        if ($this->directory === null && (getenv('APP_ENV') ?: ($_ENV['APP_ENV'] ?? '')) === 'testing') {
            error_log("APP_ENV=testing: Suppressed removing $normalizedEmail from {$this->groupKey}");
            return true;
        }

        if (!$this->ensureClientInitialized()) {
            return false;
        }

        try {
            $this->directory->members->delete($this->groupKey, $normalizedEmail);
            return true;
        } catch (Google_Service_Exception $e) {
            if ($e->getCode() === 404) {
                // Member was not in the group; treat as idempotent success
                error_log("GoogleGroupService: $normalizedEmail is not in {$this->groupKey}");
                return true;
            }
            error_log("GoogleGroupService: API error removing $normalizedEmail: " . $e->getMessage());
            return false;
        } catch (Throwable $e) {
            error_log("GoogleGroupService: Unexpected error removing $normalizedEmail: " . $e->getMessage());
            return false;
        }
    }

    /**
     * Retrieves all current members of the Google Group, handling pagination automatically.
     *
     * @return array Array of associative arrays with 'email', 'role', and 'type'.
     */
    public function listMembers(): array
    {
        // Bypass live external API during test runs when no mock service was injected
        if ($this->directory === null && (getenv('APP_ENV') ?: ($_ENV['APP_ENV'] ?? '')) === 'testing') {
            return [];
        }

        if (!$this->ensureClientInitialized()) {
            return [];
        }

        $allMembers = [];
        $pageToken = null;

        try {
            do {
                $optParams = ['maxResults' => 200];
                if ($pageToken) {
                    $optParams['pageToken'] = $pageToken;
                }

                $response = $this->directory->members->listMembers($this->groupKey, $optParams);
                $members = $response->getMembers() ?? [];

                foreach ($members as $m) {
                    $allMembers[] = [
                        'email' => strtolower($m->getEmail() ?? ''),
                        'role' => $m->getRole(),
                        'type' => $m->getType(),
                    ];
                }

                $pageToken = $response->getNextPageToken();
            } while (!empty($pageToken));

            return $allMembers;
        } catch (Throwable $e) {
            error_log("GoogleGroupService: Failed to list members of {$this->groupKey}: " . $e->getMessage());
            return [];
        }
    }

    /**
     * Returns the target Google Group address.
     *
     * @return string
     */
    public function getGroupKey(): string
    {
        return $this->groupKey;
    }

    /**
     * Returns the impersonated admin user identity.
     *
     * @return string
     */
    public function getAdminUser(): string
    {
        return $this->adminUser;
    }
}
