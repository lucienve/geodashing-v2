<?php

declare(strict_types=1);

namespace App\Services;

use PDO;

/**
 * Class DashpointService
 *
 * Encapsulates data fetching operations for Dashpoints and associated visits.
 */
class DashpointService
{
    private PDO $db;

    /**
     * Constructor.
     *
     * @param PDO|null $db The PDO database connection.
     */
    public function __construct(?PDO $db = null)
    {
        // Permits dependency injection for PHPUnit Testing isolating the Database
        $this->db = $db ?: \App\Database::getConnection();
    }

    /**
     * Resolves metadata for a Dashpoint alongside globally joined visit data.
     *
     * @param string $dashpointId The unique dashpoint ID.
     * @return array|null The dashpoint details and visit list, or null if not found.
     */
    public function getDashpointDetails(string $dashpointId): ?array
    {
        // 1. Fetch exact Dashpoint metadata utilizing SRID 4326 correctly mapping Lat/Lon
        $stmt = $this->db->prepare("
            SELECT d.id, ST_Latitude(d.location) AS lat, ST_Longitude(d.location) AS lon, d.game_id,
                   g.is_active, g.start_time,
                   (SELECT COUNT(*) FROM dashpoint_rerolls r WHERE r.dashpoint_id = d.id) AS reroll_count
            FROM dashpoints d
            JOIN games g ON d.game_id = g.id
            WHERE d.id = :id LIMIT 1
        ");
        $stmt->execute(['id' => $dashpointId]);
        $dashpoint = $stmt->fetch(PDO::FETCH_ASSOC);

        if (!$dashpoint) {
            return null;
        }

        // 2. Query precisely all approved Historical Visits mapped to this exact dashpoint
        $vStmt = $this->db->prepare("
            SELECT v.id AS visit_id, u.username, v.reported_time, v.edited_at, v.score_awarded, v.is_attempt, v.notes, v.photos,
                   ST_Latitude(v.reported_location) AS reported_lat, ST_Longitude(v.reported_location) AS reported_lon, v.distance_meters 
            FROM visits v 
            JOIN users u ON v.user_id = u.id 
            WHERE v.dashpoint_id = :id AND v.status = 'approved'
            ORDER BY v.reported_time ASC
        ");
        $vStmt->execute(['id' => $dashpointId]);
        $visits = $vStmt->fetchAll(PDO::FETCH_ASSOC);

        // 3. Decode the raw JSON photographic arrays safely for the UI Carousel parser statically
        foreach ($visits as &$v) {
            $v['photos'] = json_decode($v['photos'] ?? '[]', true) ?: [];
        }

        $startTime = isset($dashpoint['start_time']) ? strtotime((string) $dashpoint['start_time']) : 0;
        $isGameActive = (bool) ($dashpoint['is_active'] ?? false);
        $isGamePreview = (!$isGameActive && $startTime > time());
        $isRerolled = ((int) ($dashpoint['reroll_count'] ?? 0)) > 0;


        return [
            "id" => $dashpoint['id'],
            "lat" => (float) $dashpoint['lat'],
            "lon" => (float) $dashpoint['lon'],
            "game_id" => (int) $dashpoint['game_id'],
            "is_game_active" => $isGameActive,
            "is_game_preview" => $isGamePreview,
            "is_rerolled" => $isRerolled,
            "visits" => $visits
        ];
    }
}
