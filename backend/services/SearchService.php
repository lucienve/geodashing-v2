<?php

namespace App\Services;

use PDO;
use PDOException;

/**
 * SearchService
 *
 * Executes highly optimized spatial bounding box queries against the
 * MySQL 8 engine natively, routing frontend coordinates reliably
 * across boundaries like the International Date Line.
 */

class SearchService
{
    private PDO $db;

    public function __construct(PDO $db)
    {
        $this->db = $db;
    }

    /**
     * Retrieves all active dashpoints within the specified geographic rectangle.
     * Natively supports anti-meridian wrapping seamlessly for Pacific maps.
     *
     * @param float $north Maximum Latitude
     * @param float $south Minimum Latitude
     * @param float $east  Maximum Longitude
     * @param float $west  Minimum Longitude
     * @param int|null $gameId Optional historical Game ID
     * @return array Array of indexed geocoordinates and Dashpoint strings.
     * @throws PDOException
     */
    public function searchRegion(float $north, float $south, float $east, float $west, ?int $gameId = null): array
    {
        // 1. Base Query ensuring we actively process points that belong to the specified or LIVE Game State Month.
        $baseQuery = "
            SELECT d.id, ST_X(d.location) AS lat, ST_Y(d.location) AS lon, COUNT(v.id) AS visit_count 
            FROM dashpoints d
            JOIN games g ON d.game_id = g.id
            LEFT JOIN visits v ON d.id = v.dashpoint_id AND v.status = 'approved'
            WHERE ST_X(d.location) BETWEEN :south AND :north
        ";

        if ($gameId !== null) {
            $baseQuery .= " AND g.id = :game_id";
        } else {
            $baseQuery .= " AND g.is_active = TRUE";
        }

        // 2. International Date Line Router Algorithm
        if ($east < $west) {
            // Box mathematically crossed the Anti-Meridian -> Break query into two global hemispheres safely
            $sql = $baseQuery . " AND (ST_Y(d.location) BETWEEN :west AND 180.0 OR ST_Y(d.location) BETWEEN -180.0 AND :east) GROUP BY d.id";
        } else {
            // Standard Euclidean Bounding Box mapping
            $sql = $baseQuery . " AND ST_Y(d.location) BETWEEN :west AND :east GROUP BY d.id";
        }

        $stmt = $this->db->prepare($sql);

        $params = [
            ':south' => $south,
            ':north' => $north,
            ':west' => $west,
            ':east' => $east
        ];

        if ($gameId !== null) {
            $params[':game_id'] = $gameId;
        }

        $stmt->execute($params);

        $results = $stmt->fetchAll(PDO::FETCH_ASSOC);

        // Natively return an empty PHP array over 'false' for clean mapping APIs
        return $results !== false ? $results : [];
    }
}
