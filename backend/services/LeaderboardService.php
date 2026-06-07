<?php

declare(strict_types=1);

namespace App\Services;

use PDO;

/**
 * LeaderboardService
 *
 * Aggregates and ranks active player scores utilizing SQL GROUP BY projections.
 */

class LeaderboardService
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
     * Calculates the Solo Player Leaderboard rankings for a specific game.
     * Evaluates `SUM(score_awarded)`, `COUNT(status=approved)`, and utilizes
     * the MAX(`reported_time`) to enforce FCFS tie-breaking protocols.
     *
     * @param int $gameId The Monthly game ID.
     * @param int $limit Limits the SQL loop for structural safety (Default: 100 players).
     * @return array Ranked struct mapping [`rank`, `username`, `total_score`, `total_finds`, `last_find_time`]
     */
    public function getSoloRankings(int $gameId, int $limit = 100): array
    {
        // Execute structural aggregation calculating standard sums, filtering explicitly for the dashpoint game array.
        $sql = "
            SELECT 
                u.id AS user_id,
                u.username,
                SUM(v.score_awarded) AS total_score,
                COUNT(v.id) AS total_finds,
                MAX(v.reported_time) AS last_find_time
            FROM visits v
            JOIN users u ON v.user_id = u.id
            JOIN dashpoints d ON v.dashpoint_id = d.id
            WHERE d.game_id = :game_id AND v.status = 'approved'
            GROUP BY u.id, u.username
            ORDER BY total_score DESC, u.username ASC
            LIMIT :limit
        ";

        $stmt = $this->db->prepare($sql);

        // Map parameter bindings using PDO constants.
        $stmt->bindValue(':game_id', $gameId, PDO::PARAM_INT);
        $stmt->bindValue(':limit', $limit, PDO::PARAM_INT);
        $stmt->execute();

        $rawRankings = $stmt->fetchAll(PDO::FETCH_ASSOC);
        if ($rawRankings === false) {
            return [];
        }

        // Calculate ordinal ranking accounting for exact ties.
        $mappedRankings = [];
        $currentRank = 1;
        $idx = 1;
        $prevScore = null;

        foreach ($rawRankings as $row) {
            $rowScore = (int) $row['total_score'];

            // Enforce standard competition tie-breaking (Rank 1, 1, 3, 4) if points are identical.
            if ($prevScore !== null && $rowScore === $prevScore) {
                // Exact identical score. Holds the current rank mapping.
            } else {
                $currentRank = $idx;
            }

            $mappedRankings[] = [
                'rank' => $currentRank,
                'user_id' => (int) $row['user_id'],
                'username' => $row['username'],
                'total_score' => $rowScore,
                'total_finds' => (int) $row['total_finds'],
                'last_find_time' => $row['last_find_time']
            ];

            $prevScore = $rowScore;
            $idx++;
        }

        return $mappedRankings;
    }
}
