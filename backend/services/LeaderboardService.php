<?php

declare(strict_types=1);

namespace App\Services;

use PDO;

/**
 * LeaderboardService
 *
 * Exclusively aggregates and formally ranks active Player scores and metrics
 * utilizing SQL GROUP BY projections.
 */

class LeaderboardService
{
    private PDO $db;

    public function __construct(PDO $db)
    {
        $this->db = $db;
    }

    /**
     * Executes the Solo Player Leaderboard aggregation for a specific game loop natively.
     * Evaluates `SUM(score_awarded)`, `COUNT(status=approved)`, and strictly utilizes
     * the MAX(`reported_time`) to enforce FCFS tie-breaking protocols.
     *
     * @param int $gameId The primary mathematical index representing the Monthly dashpoint matrix.
     * @param int $limit Limits the SQL loop for structural safety (Default: 100 players).
     * @return array Ranked struct mapping [`rank`, `username`, `total_score`, `total_finds`, `last_find_time`]
     */
    public function getSoloRankings(int $gameId, int $limit = 100): array
    {
        // Execute structural aggregation calculating standard sums natively, filtering explicitly for the dashpoint game array.
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
            ORDER BY total_score DESC, last_find_time ASC
            LIMIT :limit
        ";

        $stmt = $this->db->prepare($sql);

        // Map parameter bindings using PDO constants to prevent float cast errors on limits.
        $stmt->bindValue(':game_id', $gameId, PDO::PARAM_INT);
        $stmt->bindValue(':limit', $limit, PDO::PARAM_INT);
        $stmt->execute();

        $rawRankings = $stmt->fetchAll(PDO::FETCH_ASSOC);
        if ($rawRankings === false) {
            return [];
        }

        // Rigorously format and calculate ordinal ranking (`#1`, `#2`) logically to account for exact ties perfectly.
        $mappedRankings = [];
        $currentRank = 1;
        $idx = 1;
        $prevScore = null;
        $prevTime = null;

        foreach ($rawRankings as $row) {
            $rowScore = (int) $row['total_score'];
            $rowTime = $row['last_find_time'];

            // Enforce standard competition tie-breaking (Rank 1, 1, 3, 4) if parameters are identical.
            if ($prevScore !== null && $rowScore === $prevScore && $rowTime === $prevTime) {
                // Exact identical score AND exact identical finish time. Holds the current rank string mapping structurally.
            } else {
                $currentRank = $idx;
            }

            $mappedRankings[] = [
                'rank' => $currentRank,
                'user_id' => (int) $row['user_id'],
                'username' => $row['username'],
                'total_score' => $rowScore,
                'total_finds' => (int) $row['total_finds'],
                'last_find_time' => $rowTime
            ];

            $prevScore = $rowScore;
            $prevTime = $rowTime;
            $idx++;
        }

        return $mappedRankings;
    }
}
