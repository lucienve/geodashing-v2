<?php

declare(strict_types=1);

namespace App\Services;

use PDO;
use PDOException;

/**
 * GameService
 *
 * Handles logic for retrieving game parameters, active state, and historical listings.
 */
class GameService
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
     * Retrieves all games sorted by descending ID.
     *
     * @return array Array of game records
     */
    public function getAllGames(): array
    {
        $stmt = $this->db->query("SELECT id, title, start_time, end_time, is_active, (summary IS NOT NULL AND summary != '') as has_summary FROM games ORDER BY id DESC");
        $games = $stmt->fetchAll(PDO::FETCH_ASSOC);

        return $games ?: [];
    }
}
