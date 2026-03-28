<?php
/**
 * SearchService
 *
 * Executes highly optimized spatial bounding box queries against the 
 * MySQL 8 engine natively, routing frontend coordinates reliably 
 * across boundaries like the International Date Line.
 */

require_once __DIR__ . '/../Database.php';

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
     * @return array Array of indexed geocoordinates and Dashpoint strings.
     * @throws PDOException
     */
    public function searchRegion(float $north, float $south, float $east, float $west): array
    {
        // 1. Base Query ensuring we only actively process points that belong to the LIVE Game State Month.
        $baseQuery = "
            SELECT d.id, ST_Y(d.location) AS lat, ST_X(d.location) AS lon 
            FROM dashpoints d
            JOIN games g ON d.game_id = g.id
            WHERE g.is_active = TRUE 
              AND ST_Y(d.location) BETWEEN :south AND :north
        ";
        
        // 2. International Date Line Router Algorithm
        // When looking at a map spanning Fiji, the "East" coordinate is technically smaller (-179) than the "West" (179).
        if ($east < $west) {
            // Box mathematically crossed the Anti-Meridian -> Break query into two global hemispheres safely
            $sql = $baseQuery . " AND (ST_X(d.location) BETWEEN :west AND 180.0 OR ST_X(d.location) BETWEEN -180.0 AND :east)";
        } else {
            // Standard Euclidean Bounding Box mapping
            $sql = $baseQuery . " AND ST_X(d.location) BETWEEN :west AND :east";
        }
        
        $stmt = $this->db->prepare($sql);
        
        $stmt->execute([
            ':south' => $south,
            ':north' => $north,
            ':west' => $west,
            ':east' => $east
        ]);
        
        $results = $stmt->fetchAll(PDO::FETCH_ASSOC);
        
        // Natively return an empty PHP array over 'false' for clean mapping APIs
        return $results !== false ? $results : [];
    }
}
