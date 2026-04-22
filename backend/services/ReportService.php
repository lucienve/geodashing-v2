<?php

declare(strict_types=1);

namespace App\Services;

use PDO;
use PDOException;

/**
 * Class ReportService
 *
 * Encapsulates the core business logic required to validate proximity
 * Encapsulates the core business logic required to validate proximity
 * and persist Dashpoint visits, designed to allow for PHPUnit testing.
 */
class ReportService
{
    use MailerTrait;

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
     * @param bool        $isAttempt    Whether this is logged as a 0-point attempt.
     * @param string|null $notes        Optional narrative submitted by the user.
     * @param string|null $photosJson   Optional pre-compiled JSON string array of valid GCS image paths.
     *
     * @return array Associative array containing the JSON-ready API response.
     * @throws PDOException If the database connection fails.
     */
    public function processVisit($userId, string $dashpointId, float $lat, float $lon, bool $isAttempt = false, ?string $notes = null, ?string $photosJson = null): array
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

        // 4. Enforce the classic 100-meter proximity rule (bypass if it's an attempt)
        if (!$isAttempt && $distance > 100) {
            return [
                "status" => "error",
                "message" => "Visit rejected. You must be within 100 meters to claim this point. Calculated distance: {$distance}m."
            ];
        }

        // 5. Verify Anti-Cheat: User hasn't already claimed a successful visit for this dashpoint
        $checkStmt = $this->db->prepare("SELECT id FROM visits WHERE user_id = :uid AND dashpoint_id = :dpid AND is_attempt = FALSE LIMIT 1");
        $checkStmt->execute([':uid' => $userId, ':dpid' => $dashpointId]);
        if (!$isAttempt && $checkStmt->fetch()) {
            return ["status" => "error", "message" => "You have already claimed this dashpoint."];
        }

        // 6. Historic Team Snapshot Mechanics
        $teamStmt = $this->db->prepare("SELECT team_id FROM team_members WHERE user_id = :uid LIMIT 1");
        $teamStmt->execute([':uid' => $userId]);
        $teamRow = $teamStmt->fetch(PDO::FETCH_ASSOC);
        $teamId = $teamRow ? $teamRow['team_id'] : null;

        // 7. Real-Time Scoring Assessment
        // Do not count attempts when determining the sequence of claims
        $scoreCheckStmt = $this->db->prepare("SELECT COUNT(id) AS previous_claims FROM visits WHERE dashpoint_id = :dpid AND is_attempt = FALSE");
        $scoreCheckStmt->execute([':dpid' => $dashpointId]);
        $previousClaims = (int) $scoreCheckStmt->fetch(PDO::FETCH_ASSOC)['previous_claims'];

        $scoreAwarded = 1; // Default minimum score for latecomers
        if ($isAttempt) {
            $scoreAwarded = 0;
        } elseif ($previousClaims === 0) {
            $scoreAwarded = 3; // First to secure the claim
        } elseif ($previousClaims === 1) {
            $scoreAwarded = 2; // Second to claim
        }

        // 8. Log the Visit and Secure the Calculated Score Automatically alongside bounded JSON image paths
        $insertStmt = $this->db->prepare("
            INSERT INTO visits (dashpoint_id, user_id, team_id, reported_location, distance_meters, score_awarded, is_attempt, notes, photos)
            VALUES (:dpid, :uid, :tid, ST_GeomFromText(:wkt, 4326), :dist, :score, :is_attempt, :notes, :photos)
        ");

        $insertStmt->execute([
            ':dpid' => $dashpointId,
            ':uid' => $userId,
            ':tid' => $teamId,
            ':wkt' => $wkt,
            ':dist' => $distance,
            ':score' => $scoreAwarded,
            ':is_attempt' => $isAttempt ? 1 : 0,
            ':notes' => $notes,
            ':photos' => $photosJson
        ]);

        $userStmt = $this->db->prepare("SELECT username FROM users WHERE id = :uid LIMIT 1");
        $userStmt->execute([':uid' => $userId]);
        $userRow = $userStmt->fetch(PDO::FETCH_ASSOC);
        $username = $userRow ? $userRow['username'] : 'Unknown User';

        $totalScoreStmt = $this->db->prepare("SELECT SUM(score_awarded) AS total FROM visits WHERE user_id = :uid");
        $totalScoreStmt->execute([':uid' => $userId]);
        $totalScoreRow = $totalScoreStmt->fetch(PDO::FETCH_ASSOC);
        $totalPoints = $totalScoreRow ? (int) $totalScoreRow['total'] : $scoreAwarded;

        $this->sendVisitReportEmail($username, $dashpointId, $distance, $scoreAwarded, $totalPoints, $isAttempt, $notes, $photosJson);

        $action = $isAttempt ? "Attempt logged" : "Dashpoint successfully claimed";
        $pointsMessage = $isAttempt ? "This attempt earned 0 points." : "You earned {$scoreAwarded} points.";

        return [
            "status" => "success",
            "message" => "{$action}. {$pointsMessage}",
            "distance" => $distance,
            "points" => $scoreAwarded
        ];
    }

    /**
     * Constructs and dispatches an HTML email to the mailing list detailing the new Dashpoint visit.
     */
    private function sendVisitReportEmail(string $username, string $dashpointId, int $distance, int $points, int $totalPoints, bool $isAttempt, ?string $notes, ?string $photosJson): void
    {
        $configPath = __DIR__ . '/../config.ini';
        $config = file_exists($configPath) ? parse_ini_file($configPath) : [];
        $toList = $config['MAILING_LIST_ADDRESS'] ?? '';

        if (empty($toList)) {
            return;
        }

        if ($isAttempt) {
            $subject = "Dashpoint Attempt: {$username} logged an attempt for {$dashpointId}";
            $message = "<html><body>";
            $message .= "<h2>Dashpoint Attempt Logged</h2>";
        } else {
            $subject = "New Dashpoint Log: {$username} claimed {$dashpointId}";
            $message = "<html><body>";
            $message .= "<h2>New Dashpoint Log</h2>";
        }
        $profileUrl = "https://www.geodashing.org/?profile=" . urlencode($username);
        $message .= "<p><strong>User:</strong> <a href='" . htmlspecialchars($profileUrl, ENT_QUOTES, 'UTF-8') . "'>" . htmlspecialchars($username) . "</a></p>";
        $dashpointUrl = "https://www.geodashing.org/?dashpoint=" . urlencode($dashpointId);
        $message .= "<p><strong>Dashpoint:</strong> <a href='" . htmlspecialchars($dashpointUrl, ENT_QUOTES, 'UTF-8') . "'>" . htmlspecialchars($dashpointId) . "</a></p>";
        $message .= "<p><strong>Distance:</strong> {$distance} meters</p>";
        $message .= "<p><strong>Points Gained:</strong> {$points}</p>";
        $message .= "<p><strong>New Total Points:</strong> {$totalPoints}</p>";

        if (!empty($notes)) {
            $message .= "<h3>Field Notes</h3>";
            $message .= "<p>" . nl2br(htmlspecialchars($notes)) . "</p>";
        }

        if (!empty($photosJson)) {
            $photos = json_decode($photosJson, true);
            if (is_array($photos) && count($photos) > 0) {
                $message .= "<h3>Photos</h3>";
                foreach ($photos as $photoObj) {
                    if (is_array($photoObj) && isset($photoObj['url'])) {
                        $message .= "<div style='margin-bottom: 10px;'><img src='" . htmlspecialchars($photoObj['url'], ENT_QUOTES, 'UTF-8') . "' alt='Dashpoint Photo' style='max-width: 100%; height: auto;' /></div>";
                    } elseif (is_string($photoObj)) {
                        $message .= "<div style='margin-bottom: 10px;'><img src='" . htmlspecialchars($photoObj, ENT_QUOTES, 'UTF-8') . "' alt='Dashpoint Photo' style='max-width: 100%; height: auto;' /></div>";
                    }
                }
            }
        }

        $message .= "</body></html>";

        $headers = $this->buildMailHeaders("tracker@geodashing.org", "Geodashing Emails", true);

        $this->executeMail($toList, $subject, $message, $headers, "-ftracker@geodashing.org");
    }


}
