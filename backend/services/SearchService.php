<?php

declare(strict_types=1);

namespace App\Services;

use PDO;
use PDOException;

/**
 * SearchService
 *
 * Executes highly optimized spatial bounding box queries against the
 * MySQL 8 engine, routing frontend coordinates reliably
 * across boundaries like the International Date Line.
 */

class SearchService
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
     * Retrieves all active dashpoints within the specified geographic rectangle.
     * Supports anti-meridian wrapping seamlessly for Pacific maps.
     *
     * @param float $north Maximum Latitude
     * @param float $south Minimum Latitude
     * @param float $east  Maximum Longitude
     * @param float $west  Minimum Longitude
     * @param int $gameId  Game ID
     * @return array Array of indexed geocoordinates and Dashpoint strings.
     * @throws PDOException
     */
    public function searchRegion(float $north, float $south, float $east, float $west, int $gameId): array
    {
        // 1. Base Query ensuring we actively process points that belong to the specified or LIVE Game State Month.
        $baseQuery = "
            SELECT d.id, ST_Latitude(d.location) AS lat, ST_Longitude(d.location) AS lon, COUNT(v.id) AS visit_count 
            FROM dashpoints d
            JOIN games g ON d.game_id = g.id
            LEFT JOIN visits v ON d.id = v.dashpoint_id AND v.status = 'approved'
            WHERE g.id = :game_id
        ";

        // 2. International Date Line Router Algorithm
        if ($east < $west) {
            // Box mathematically crossed the Anti-Meridian -> Break query into two global polygons
            $polyWest = sprintf('POLYGON((%F %F, %F %F, %F 180.0, %F 180.0, %F %F))', $south, $west, $north, $west, $north, $south, $south, $west);
            $polyEast = sprintf('POLYGON((%F -180.0, %F -180.0, %F %F, %F %F, %F -180.0))', $south, $north, $north, $east, $south, $east, $south);

            $sql = $baseQuery . " AND (MBRContains(ST_GeomFromText(:poly_west, 4326), d.location) OR MBRContains(ST_GeomFromText(:poly_east, 4326), d.location)) GROUP BY d.id";
            $params = [
                ':poly_west' => $polyWest,
                ':poly_east' => $polyEast,
                ':game_id' => $gameId
            ];
        } else {
            // Standard Bounding Box mapping utilizing MySQL SPATIAL INDEX
            $poly = sprintf('POLYGON((%F %F, %F %F, %F %F, %F %F, %F %F))', $south, $west, $north, $west, $north, $east, $south, $east, $south, $west);
            $sql = $baseQuery . " AND MBRContains(ST_GeomFromText(:poly, 4326), d.location) GROUP BY d.id";
            $params = [
                ':poly' => $poly,
                ':game_id' => $gameId
            ];
        }

        $stmt = $this->db->prepare($sql);
        $stmt->execute($params);

        $results = $stmt->fetchAll(PDO::FETCH_ASSOC);

        // Return an empty PHP array over 'false' for clean mapping APIs
        return $results !== false ? $results : [];
    }

    /**
     * Retrieves all approved visits/attempts within the specified geographic rectangle.
     * Supports anti-meridian wrapping seamlessly for Pacific maps.
     *
     * @param float $north Maximum Latitude
     * @param float $south Minimum Latitude
     * @param float $east  Maximum Longitude
     * @param float $west  Minimum Longitude
     * @param int $gameId  Game ID
     * @return array Array of visits.
     * @throws PDOException
     */
    public function searchVisitsRegion(float $north, float $south, float $east, float $west, int $gameId): array
    {
        $baseQuery = "
            SELECT v.id, v.dashpoint_id, u.username, 
                   ST_Latitude(v.reported_location) AS lat, 
                   ST_Longitude(v.reported_location) AS lon, 
                   v.is_attempt, v.score_awarded, v.reported_time
            FROM visits v
            JOIN users u ON v.user_id = u.id
            JOIN dashpoints d ON v.dashpoint_id = d.id
            WHERE d.game_id = :game_id
              AND v.status = 'approved'
        ";

        if ($east < $west) {
            $polyWest = sprintf('POLYGON((%F %F, %F %F, %F 180.0, %F 180.0, %F %F))', $south, $west, $north, $west, $north, $south, $south, $west);
            $polyEast = sprintf('POLYGON((%F -180.0, %F -180.0, %F %F, %F %F, %F -180.0))', $south, $north, $north, $east, $south, $east, $south);

            $sql = $baseQuery . " AND (MBRContains(ST_GeomFromText(:poly_west, 4326), v.reported_location) OR MBRContains(ST_GeomFromText(:poly_east, 4326), v.reported_location))";
            $params = [
                ':poly_west' => $polyWest,
                ':poly_east' => $polyEast,
                ':game_id' => $gameId
            ];
        } else {
            $poly = sprintf('POLYGON((%F %F, %F %F, %F %F, %F %F, %F %F))', $south, $west, $north, $west, $north, $east, $south, $east, $south, $west);
            $sql = $baseQuery . " AND MBRContains(ST_GeomFromText(:poly, 4326), v.reported_location)";
            $params = [
                ':poly' => $poly,
                ':game_id' => $gameId
            ];
        }

        $stmt = $this->db->prepare($sql);
        $stmt->execute($params);

        $results = $stmt->fetchAll(PDO::FETCH_ASSOC);

        if ($results !== false) {
            foreach ($results as &$row) {
                $row['is_attempt'] = (bool)$row['is_attempt'];
                $row['score_awarded'] = (int)$row['score_awarded'];
                $row['lat'] = (float)$row['lat'];
                $row['lon'] = (float)$row['lon'];
            }
            return $results;
        }

        return [];
    }
}
