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
}
