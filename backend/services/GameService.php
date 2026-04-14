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

    public function __construct(PDO $db)
    {
        $this->db = $db;
    }

    /**
     * Gets the currently active game.
     *
     * @return array|null The active game array or null if none
     */
    public function getActiveGame(): ?array
    {
        $stmt = $this->db->prepare("SELECT id, title, start_time, end_time FROM games WHERE is_active = TRUE ORDER BY id DESC LIMIT 1");
        $stmt->execute();
        $game = $stmt->fetch(PDO::FETCH_ASSOC);

        if ($game) {
            return [
                "game_id" => (int)$game['id'],
                "title" => $game['title'],
                "start_time" => $game['start_time'],
                "end_time" => $game['end_time']
            ];
        }

        return null;
    }

    /**
     * Retrieves all games sorted by descending ID.
     *
     * @return array Array of game records
     */
    public function getAllGames(): array
    {
        $stmt = $this->db->query("SELECT id, title, start_time, end_time, is_active FROM games ORDER BY id DESC");
        $games = $stmt->fetchAll(PDO::FETCH_ASSOC);

        return $games ?: [];
    }
}
