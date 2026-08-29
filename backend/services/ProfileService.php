<?php

declare(strict_types=1);

namespace App\Services;

use PDO;
use Exception;

/**
 * Class ProfileService
 *
 * Encapsulates the core business logic required to retrieve historical metrics for a specific user.
 */
class ProfileService
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
     * Get profile metrics for a specific user.
     *
     * @param string $username The username of the user.
     * @return array|null Returns array of user data and games history or null if user not found.
     */
    public function getProfileSettings(string $username): ?array
    {
        // 1. Get User Core Details
        $stmtUser = $this->db->prepare("SELECT id, username, created_at FROM users WHERE username = :username");
        $stmtUser->execute([':username' => $username]);
        $user = $stmtUser->fetch(PDO::FETCH_ASSOC);

        if (!$user) {
            return null;
        }

        // 2. Fetch Historical Logs and Scores joining Games and Dashpoints
        $query = "
            SELECT 
                v.id AS visit_id,
                v.score_awarded,
                v.is_attempt,
                v.reported_time,
                v.distance_meters,
                d.id AS dashpoint_id,
                g.id AS game_id,
                g.title AS game_title,
                g.is_active AS game_is_active
            FROM visits v
            JOIN dashpoints d ON v.dashpoint_id = d.id
            JOIN games g ON d.game_id = g.id
            WHERE v.user_id = :user_id AND v.status = 'approved'
            ORDER BY g.id DESC, v.reported_time DESC
        ";

        $stmtLogs = $this->db->prepare($query);
        $stmtLogs->execute([':user_id' => $user['id']]);
        $logs = $stmtLogs->fetchAll(PDO::FETCH_ASSOC);

        // 3. Aggregate data mapping by Game ID
        $totalScore = 0;
        $gamesHistory = [];

        foreach ($logs as $log) {
            $totalScore += (int) $log['score_awarded'];
            $gId = $log['game_id'];

            if (!isset($gamesHistory[$gId])) {
                $gamesHistory[$gId] = [
                    'game_id' => $gId,
                    'title' => $log['game_title'],
                    'is_active' => (bool) $log['game_is_active'],
                    'game_total_score' => 0,
                    'visits' => []
                ];
            }

            $gamesHistory[$gId]['game_total_score'] += (int) $log['score_awarded'];
            $gamesHistory[$gId]['visits'][] = [
                'visit_id' => $log['visit_id'],
                'dashpoint_id' => $log['dashpoint_id'],
                'score_awarded' => (int) $log['score_awarded'],
                'is_attempt' => (bool) $log['is_attempt'],
                'distance_meters' => (int) $log['distance_meters'],
                'reported_time' => $log['reported_time']
            ];
        }

        return [
            "user" => [
                "id" => $user['id'],
                "username" => $user['username'],
                "created_at" => $user['created_at'],
                "lifetime_score" => $totalScore
            ],
            "games" => array_values($gamesHistory)
        ];
    }

    /**
     * Retrieves aggregated player statistics for email notifications.
     *
     * @param int $userId The ID of the user.
     * @param int $gameId The ID of the active game.
     * @param string|null $beforeTime Optional ISO timestamp to only count hunts prior to a specific time.
     * @return array Array containing 'total_points_all_games', 'total_points_game', 'previous_hunts_all_games', and 'previous_hunts_game'.
     */
    public function getPlayerMailStats(int $userId, int $gameId, ?string $beforeTime = null): array
    {
        $scoreQuery = "SELECT SUM(score_awarded) AS total FROM visits WHERE user_id = :uid AND status = 'approved'";
        $stmtScore = $this->db->prepare($scoreQuery);
        $stmtScore->execute([':uid' => $userId]);
        $rowScore = $stmtScore->fetch(PDO::FETCH_ASSOC);
        $totalPointsAllGames = $rowScore ? (int) $rowScore['total'] : 0;

        $scoreGameQuery = "
            SELECT SUM(v.score_awarded) AS total 
            FROM visits v 
            JOIN dashpoints d ON v.dashpoint_id = d.id 
            WHERE v.user_id = :uid AND d.game_id = :game_id AND v.status = 'approved'
        ";
        $stmtScoreGame = $this->db->prepare($scoreGameQuery);
        $stmtScoreGame->execute([':uid' => $userId, ':game_id' => $gameId]);
        $rowScoreGame = $stmtScoreGame->fetch(PDO::FETCH_ASSOC);
        $totalPointsGame = $rowScoreGame ? (int) $rowScoreGame['total'] : 0;

        $huntsParams = [':uid' => $userId];
        $huntsQuery = "SELECT COUNT(id) AS previous_hunts FROM visits WHERE user_id = :uid AND status = 'approved'";
        if ($beforeTime !== null) {
            $huntsQuery .= " AND reported_time < :before_time";
            $huntsParams[':before_time'] = $beforeTime;
        }
        $stmtHunts = $this->db->prepare($huntsQuery);
        $stmtHunts->execute($huntsParams);
        $rowHunts = $stmtHunts->fetch(PDO::FETCH_ASSOC);
        $previousHuntsAllGames = $rowHunts ? (int) $rowHunts['previous_hunts'] : 0;

        $huntsGameParams = [':uid' => $userId, ':game_id' => $gameId];
        $huntsGameQuery = "
            SELECT COUNT(v.id) AS previous_hunts 
            FROM visits v 
            JOIN dashpoints d ON v.dashpoint_id = d.id 
            WHERE v.user_id = :uid AND d.game_id = :game_id AND v.status = 'approved'
        ";
        if ($beforeTime !== null) {
            $huntsGameQuery .= " AND v.reported_time < :before_time";
            $huntsGameParams[':before_time'] = $beforeTime;
        }
        $stmtHuntsGame = $this->db->prepare($huntsGameQuery);
        $stmtHuntsGame->execute($huntsGameParams);
        $rowHuntsGame = $stmtHuntsGame->fetch(PDO::FETCH_ASSOC);
        $previousHuntsGame = $rowHuntsGame ? (int) $rowHuntsGame['previous_hunts'] : 0;

        return [
            'total_points_all_games' => $totalPointsAllGames,
            'total_points_game' => $totalPointsGame,
            'previous_hunts_all_games' => $previousHuntsAllGames,
            'previous_hunts_game' => $previousHuntsGame,
        ];
    }
}
