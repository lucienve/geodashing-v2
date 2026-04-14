<?php

declare(strict_types=1);

namespace App\Services;

use PDO;
use PDOException;

/**
 * Class ReportService
 *
 * Encapsulates the core business logic required to validate proximity
 * and persist Dashpoint visits, architected this way to allow for PHPUnit testing.
 */
class ReportService
{
    /**
     * @var PDO The configured database connection.
     */
    private PDO $db;

    /**
     * Constructor.
     *
     * @param PDO $db The PDO connection instance.
     */
    public function __construct(PDO $db)
    {
        $this->db = $db;
    }

    /**
     * Processes a user's location claim against a specific Dashpoint.
     *
     * @param int|string  $userId       The ID of the user submitting the visit.
     * @param string      $dashpointId  The unique ID target Dashpoint.
     * @param float       $lat          The user's reported latitude.
     * @param float       $lon          The user's reported longitude.
     * @param string|null $notes        Optional narrative submitted by the user.
     * @param string|null $photosJson   Optional pre-compiled JSON string array of valid GCS image paths.
     *
     * @return array Associative array containing the JSON-ready API response.
     * @throws PDOException If the database connection fails.
     */
    public function processVisit($userId, string $dashpointId, float $lat, float $lon, ?string $notes = null, ?string $photosJson = null): array
    {
        $userStmt = $this->db->prepare("SELECT is_verified FROM users WHERE id = :user_id LIMIT 1");
        $userStmt->execute([':user_id' => $userId]);
        $userCheck = $userStmt->fetch(PDO::FETCH_ASSOC);

        if (!$userCheck || $userCheck['is_verified'] == 0) {
            return ["status" => "error", "message" => "Account not verified. Please check your email to activate your account before logging Dashpoints."];
        }

        // 3. Proximity Calculation utilizing MySQL native ST_Distance_Sphere
        $wkt = "POINT($lat $lon)";

        $distStmt = $this->db->prepare("
            SELECT ST_Distance_Sphere(d.location, ST_GeomFromText(:wkt, 4326)) AS distance_meters, g.is_active
            FROM dashpoints d
            JOIN games g ON d.game_id = g.id
            WHERE d.id = :id 
            LIMIT 1
        ");
        $distStmt->execute([':wkt' => $wkt, ':id' => $dashpointId]);
        $result = $distStmt->fetch(PDO::FETCH_ASSOC);

        if (!$result) {
            return ["status" => "error", "message" => "Invalid Dashpoint ID."];
        }

        if (!$result['is_active']) {
            return ["status" => "error", "message" => "Target dashpoint belongs to an inactive game."];
        }

        $distance = (int) round($result['distance_meters']);

        // 4. Enforce the classic 100-meter proximity rule
        if ($distance > 100) {
            return [
                "status" => "error",
                "message" => "Visit rejected. You must be within 100 meters to claim this point. Calculated distance: {$distance}m."
            ];
        }

        // 5. Verify Anti-Cheat: User hasn't already claimed this dashpoint
        $checkStmt = $this->db->prepare("SELECT id FROM visits WHERE user_id = :uid AND dashpoint_id = :dpid LIMIT 1");
        $checkStmt->execute([':uid' => $userId, ':dpid' => $dashpointId]);
        if ($checkStmt->fetch()) {
            return ["status" => "error", "message" => "You have already logged a visit for this dashpoint."];
        }

        // 6. Historic Team Snapshot Mechanics
        $teamStmt = $this->db->prepare("SELECT team_id FROM team_members WHERE user_id = :uid LIMIT 1");
        $teamStmt->execute([':uid' => $userId]);
        $teamRow = $teamStmt->fetch(PDO::FETCH_ASSOC);
        $teamId = $teamRow ? $teamRow['team_id'] : null;

        // 7. Real-Time Scoring Assessment
        $scoreCheckStmt = $this->db->prepare("SELECT COUNT(id) AS previous_claims FROM visits WHERE dashpoint_id = :dpid");
        $scoreCheckStmt->execute([':dpid' => $dashpointId]);
        $previousClaims = (int) $scoreCheckStmt->fetch(PDO::FETCH_ASSOC)['previous_claims'];

        $scoreAwarded = 1; // Default minimum score for latecomers
        if ($previousClaims === 0) {
            $scoreAwarded = 3; // First to physically network the claim
        } elseif ($previousClaims === 1) {
            $scoreAwarded = 2; // Second to claim
        }

        // 8. Log the Visit and Secure the Calculated Score Automatically alongside bounded JSON image paths
        $insertStmt = $this->db->prepare("
            INSERT INTO visits (dashpoint_id, user_id, team_id, reported_location, distance_meters, score_awarded, notes, photos)
            VALUES (:dpid, :uid, :tid, ST_GeomFromText(:wkt, 4326), :dist, :score, :notes, :photos)
        ");

        $insertStmt->execute([
            ':dpid' => $dashpointId,
            ':uid' => $userId,
            ':tid' => $teamId,
            ':wkt' => $wkt,
            ':dist' => $distance,
            ':score' => $scoreAwarded,
            ':notes' => $notes,
            ':photos' => $photosJson
        ]);

        return [
            "status" => "success",
            "message" => "Dashpoint successfully claimed. You earned {$scoreAwarded} points.",
            "distance" => $distance,
            "points" => $scoreAwarded
        ];
    }
}
