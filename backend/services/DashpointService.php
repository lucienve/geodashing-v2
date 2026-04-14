<?php

namespace App\Services;

use PDO;

require_once __DIR__ . '/../Database.php';

class DashpointService
{
    private PDO $db;

    public function __construct(?PDO $db = null)
    {
        // Permits dependency injection for PHPUnit Testing natively isolating the Database
        $this->db = $db ?: \App\Database::getConnection();
    }

    /**
     * Resolves metadata for a Dashpoint alongside universally joined Historic Visit Ledgers
     */
    public function getDashpointDetails(string $dashpointId): ?array
    {
        // 1. Fetch exact Dashpoint metadata utilizing SRID 4326 correctly mapping Lat/Lon
        $stmt = $this->db->prepare("SELECT id, ST_X(location) AS lat, ST_Y(location) AS lon, game_id FROM dashpoints WHERE id = :id LIMIT 1");
        $stmt->execute(['id' => $dashpointId]);
        $dashpoint = $stmt->fetch(PDO::FETCH_ASSOC);

        if (!$dashpoint) {
            return null;
        }

        // 2. Query precisely all approved Historical Visits mapped to this exact dashpoint
        $vStmt = $this->db->prepare("
            SELECT v.id AS visit_id, u.username, v.reported_time, v.edited_at, v.score_awarded, v.notes, v.photos 
            FROM visits v 
            JOIN users u ON v.user_id = u.id 
            WHERE v.dashpoint_id = :id AND v.status = 'approved'
            ORDER BY v.reported_time ASC
        ");
        $vStmt->execute(['id' => $dashpointId]);
        $visits = $vStmt->fetchAll(PDO::FETCH_ASSOC);

        // 3. Decode the raw JSON photographic arrays safely for the UI Carousel parser statically
        foreach ($visits as &$v) {
            $v['photos'] = json_decode($v['photos'], true) ?: [];
        }

        return [
            "id" => $dashpoint['id'],
            "lat" => (float)$dashpoint['lat'],
            "lon" => (float)$dashpoint['lon'],
            "game_id" => (int)$dashpoint['game_id'],
            "visits" => $visits
        ];
    }
}
