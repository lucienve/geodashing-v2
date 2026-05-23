<?php

declare(strict_types=1);

namespace App\Services;

use PDO;

/**
 * SummaryService
 *
 * Handles logic for retrieving HTML summaries of completed games.
 */
class SummaryService
{
    private PDO $db;

    /**
     * Constructor.
     *
     * @param PDO $db The PDO connection.
     */
    public function __construct(PDO $db)
    {
        $this->db = $db;
    }

    /**
     * Retrieves the HTML summary for a specific game ID.
     *
     * @param int $gameId The ID of the game
     * @return string|null The HTML summary, or null if not found
     */
    public function getSummary(int $gameId): ?string
    {
        $stmt = $this->db->prepare("SELECT summary FROM games WHERE id = ?");
        $stmt->execute([$gameId]);
        $summary = $stmt->fetchColumn();

        return $summary !== false && $summary !== null ? (string)$summary : null;
    }
}
