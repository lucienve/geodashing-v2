<?php

declare(strict_types=1);

namespace App\Services;

use InvalidArgumentException;
use PDO;

/**
 * TagService
 *
 * Manages private player-specific dashpoint tags, feature flags,
 * and game state validation (active/preview allowed, past games read-only).
 */
class TagService
{
    /**
     * Allowed preset color and shape pairs (Palette Option 1: Google Maps Categories).
     */
    public const ALLOWED_TAGS = [
        ['color' => '#1a73e8', 'shape' => 'star'],
        ['color' => '#8e24aa', 'shape' => 'diamond'],
        ['color' => '#e64a19', 'shape' => 'triangle'],
        ['color' => '#d81b60', 'shape' => 'square']
    ];

    private PDO $db;
    private array $config;

    /**
     * Constructor.
     *
     * @param PDO $db Database connection.
     * @param array|null $config Optional injected configuration array.
     */
    public function __construct(PDO $db, ?array $config = null)
    {
        $this->db = $db;
        if ($config === null) {
            $configPath = __DIR__ . '/../config.ini';
            $this->config = file_exists($configPath) ? (parse_ini_file($configPath, true) ?: []) : [];
        } else {
            $this->config = $config;
        }
    }

    /**
     * Checks if the private tagging feature is enabled for the specified username.
     *
     * @param string|null $username The player username to check.
     * @return bool True if globally enabled or if the user is present in the allowlist.
     */
    public function isFeatureEnabledForUser(?string $username): bool
    {
        $tagsConfig = $this->config['tags'] ?? [];
        $globallyEnabled = filter_var($tagsConfig['TAGS_ENABLED'] ?? false, FILTER_VALIDATE_BOOLEAN);

        if ($globallyEnabled) {
            return true;
        }

        if (empty($username)) {
            return false;
        }

        $allowlistRaw = (string) ($tagsConfig['TAGS_ALLOWLIST'] ?? '');
        if (trim($allowlistRaw) === '') {
            return false;
        }

        $allowedUsers = array_map(
            static fn(string $u): string => strtolower(trim($u)),
            explode(',', $allowlistRaw)
        );

        return in_array(strtolower(trim($username)), $allowedUsers, true);
    }

    /**
     * Retrieves all private tags for a specific user and game as an associative dictionary.
     *
     * @param int $userId The ID of the authenticated user.
     * @param int $gameId The ID of the target game.
     * @return array<string, array{color: string, shape: string}> Map of dashpoint_id => [color, shape].
     */
    public function getTagsForUserAndGame(int $userId, int $gameId): array
    {
        $stmt = $this->db->prepare(
            "SELECT udt.dashpoint_id, udt.color_code, udt.shape
             FROM user_dashpoint_tags udt
             JOIN dashpoints d ON udt.dashpoint_id = d.id
             WHERE udt.user_id = :user_id AND d.game_id = :game_id"
        );
        $stmt->execute([
            'user_id' => $userId,
            'game_id' => $gameId
        ]);

        $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);
        $tags = [];

        foreach ($rows as $row) {
            $tags[$row['dashpoint_id']] = [
                'color' => $row['color_code'],
                'shape' => $row['shape']
            ];
        }

        return $tags;
    }

    /**
     * Sets or updates a private tag on a dashpoint for a user.
     *
     * @param int $userId The user ID.
     * @param string $dashpointId The dashpoint identifier.
     * @param string $colorCode The hex color code.
     * @param string $shape The shape identifier.
     * @return array{status: string, dashpoint_id: string, color: string, shape: string} Result details.
     * @throws InvalidArgumentException When inputs are invalid or game is completed.
     */
    public function setTag(int $userId, string $dashpointId, string $colorCode, string $shape): array
    {
        $colorCode = strtolower(trim($colorCode));
        $shape = strtolower(trim($shape));

        if (!$this->isValidTag($colorCode, $shape)) {
            throw new InvalidArgumentException("Invalid color code or shape specified.");
        }

        $this->assertDashpointModifiable($dashpointId);

        $stmt = $this->db->prepare(
            "INSERT INTO user_dashpoint_tags (user_id, dashpoint_id, color_code, shape)
             VALUES (:user_id, :dashpoint_id, :color_code, :shape)
             ON DUPLICATE KEY UPDATE 
                color_code = VALUES(color_code), 
                shape = VALUES(shape),
                updated_at = CURRENT_TIMESTAMP"
        );
        $stmt->execute([
            'user_id' => $userId,
            'dashpoint_id' => $dashpointId,
            'color_code' => $colorCode,
            'shape' => $shape
        ]);

        return [
            'status' => 'success',
            'dashpoint_id' => $dashpointId,
            'color' => $colorCode,
            'shape' => $shape
        ];
    }

    /**
     * Removes a private tag from a dashpoint for a user.
     *
     * @param int $userId The user ID.
     * @param string $dashpointId The dashpoint identifier.
     * @return bool True if deleted successfully.
     * @throws InvalidArgumentException When game is completed or dashpoint not found.
     */
    public function deleteTag(int $userId, string $dashpointId): bool
    {
        $this->assertDashpointModifiable($dashpointId);

        $stmt = $this->db->prepare(
            "DELETE FROM user_dashpoint_tags 
             WHERE user_id = :user_id AND dashpoint_id = :dashpoint_id"
        );
        $stmt->execute([
            'user_id' => $userId,
            'dashpoint_id' => $dashpointId
        ]);

        return true;
    }

    /**
     * Purges all user tags for a given dashpoint (used during preview rerolls).
     *
     * @param string $dashpointId The dashpoint identifier.
     * @return int Number of deleted rows.
     */
    public function purgeTagsForDashpoint(string $dashpointId): int
    {
        $stmt = $this->db->prepare(
            "DELETE FROM user_dashpoint_tags WHERE dashpoint_id = :dashpoint_id"
        );
        $stmt->execute(['dashpoint_id' => $dashpointId]);

        return $stmt->rowCount();
    }

    /**
     * Verifies that the tag color and shape match one of the allowed presets.
     *
     * @param string $color The hex color.
     * @param string $shape The shape name.
     * @return bool True if valid.
     */
    private function isValidTag(string $color, string $shape): bool
    {
        foreach (self::ALLOWED_TAGS as $allowed) {
            if ($allowed['color'] === $color && $allowed['shape'] === $shape) {
                return true;
            }
        }
        return false;
    }

    /**
     * Asserts that a dashpoint exists and belongs to an active or preview game.
     * Rejects modifications for completed past games.
     *
     * @param string $dashpointId The dashpoint identifier.
     * @throws InvalidArgumentException If dashpoint is not found or belongs to a past game.
     */
    private function assertDashpointModifiable(string $dashpointId): void
    {
        $stmt = $this->db->prepare(
            "SELECT d.id, g.is_active, g.start_time
             FROM dashpoints d
             JOIN games g ON d.game_id = g.id
             WHERE d.id = :dashpoint_id"
        );
        $stmt->execute(['dashpoint_id' => $dashpointId]);
        $row = $stmt->fetch(PDO::FETCH_ASSOC);

        if (!$row) {
            throw new InvalidArgumentException("Dashpoint not found.");
        }

        $isActive = (bool) ($row['is_active'] ?? false);
        $startTime = isset($row['start_time']) ? strtotime((string) $row['start_time']) : 0;
        $isPast = (!$isActive && $startTime <= time());

        if ($isPast) {
            throw new InvalidArgumentException("Tags cannot be modified for completed games.");
        }
    }
}
