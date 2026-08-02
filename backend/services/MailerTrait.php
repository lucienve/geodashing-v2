<?php

declare(strict_types=1);

namespace App\Services;

use Google_Client;
use Google_Service_Gmail;
use Google_Service_Gmail_Message;
use Symfony\Component\Mime\Email;
use Exception;

/**
 * Trait MailerTrait
 *
 * Provides a unified mail execution wrapper using the official Gmail REST API.
 */
trait MailerTrait
{
    /**
     * Executes email delivery via the Gmail API. Protected specifically to allow PHPUnit mocking.
     *
     * @param string $to
     * @param string $subject
     * @param string $htmlMessage
     * @param string|null $textMessage
     * @return bool
     */
    protected function executeMail(string $to, string $subject, string $htmlMessage, ?string $textMessage = null): bool
    {
        // Bypass actual API interaction during E2E testing
        if ((getenv('APP_ENV') ?: ($_ENV['APP_ENV'] ?? '')) === 'testing') {
            error_log("APP_ENV=testing: Suppressed physical email transmission to $to");
            return true;
        }

        try {
            $configPath = __DIR__ . '/../config.ini';
            $config = file_exists($configPath) ? parse_ini_file($configPath) : [];
            $credentialsPath = $config['GOOGLE_APPLICATION_CREDENTIALS'] ?? getenv('GOOGLE_APPLICATION_CREDENTIALS');

            if (!$credentialsPath || !file_exists($credentialsPath)) {
                error_log("Mailer Error: GOOGLE_APPLICATION_CREDENTIALS not configured or file missing.");
                return false;
            }

            $sender = 'tracker@geodashing.org';

            $client = new Google_Client();
            $client->setAuthConfig($credentialsPath);
            $client->addScope(Google_Service_Gmail::GMAIL_SEND);
            $client->setSubject($sender); // Domain-wide delegation impersonation

            $service = new Google_Service_Gmail($client);

            $email = (new Email())
                ->from($sender)
                ->to($to)
                ->subject($subject)
                ->html($htmlMessage);

            if ($textMessage) {
                $email->text($textMessage);
            } else {
                // Generate a simple plain-text fallback by stripping tags
                $email->text(strip_tags(str_replace(['<br>', '<br/>', '<br />', '</p>'], "\n", $htmlMessage)));
            }

            // Build the raw MIME message string
            $rawMessageString = $email->toString();

            // Base64url encode the raw message
            $rawMessage = rtrim(strtr(base64_encode($rawMessageString), '+/', '-_'), '=');

            $msg = new Google_Service_Gmail_Message();
            $msg->setRaw($rawMessage);

            $service->users_messages->send('me', $msg);

            return true;
        } catch (Exception $e) {
            error_log("Gmail API Error: " . $e->getMessage());
            return false;
        }
    }

    /**
     * Constructs and dispatches an HTML email to the mailing list detailing the new Dashpoint visit or edit.
     */
    protected function sendVisitReportEmail(string $username, string $dashpointId, int $distance, int $points, int $totalPointsAllGames, int $totalPointsGame, bool $isAttempt, ?string $notes, ?string $photosJson, int $previousHuntsAllGames = 0, int $previousHuntsGame = 0, ?string $geoContext = null, bool $isEdit = false): void
    {
        $configPath = __DIR__ . '/../config.ini';
        $config = file_exists($configPath) ? parse_ini_file($configPath) : [];
        $toList = getenv('MAILING_LIST_ADDRESS') ?: (($_ENV['MAILING_LIST_ADDRESS'] ?? null) ?: ($config['MAILING_LIST_ADDRESS'] ?? ''));

        if (empty($toList)) {
            return;
        }

        if ($isEdit) {
            $subject = "Dashpoint Edit: {$username} updated log for {$dashpointId}";
            $message = "<html><body>";
            $message .= "<h2>Dashpoint Log Edited</h2>";
        } elseif ($isAttempt) {
            $subject = "Dashpoint Attempt: {$username} logged an attempt for {$dashpointId}";
            $message = "<html><body>";
            $message .= "<h2>Dashpoint Attempt Logged</h2>";
        } else {
            $subject = "New Dashpoint Log: {$username} claimed {$dashpointId}";
            $message = "<html><body>";
            $message .= "<h2>New Dashpoint Log</h2>";
        }
        $profileUrl = "https://www.geodashing.org/#profile?username=" . urlencode($username);
        $message .= "<p><strong>User:</strong> <a href='" . htmlspecialchars($profileUrl, ENT_QUOTES, 'UTF-8') . "'>" . htmlspecialchars($username) . "</a></p>";
        $dashpointUrl = "https://www.geodashing.org/#dashpoint?id=" . urlencode($dashpointId);
        $message .= "<p><strong>Dashpoint:</strong> <a href='" . htmlspecialchars($dashpointUrl, ENT_QUOTES, 'UTF-8') . "'>" . htmlspecialchars($dashpointId) . "</a></p>";
        if ($previousHuntsAllGames === 0) {
            $message .= "<p><strong>First dashpoint found by user - welcome to geodashing!</strong></p>";
        } else {
            $message .= "<p><strong>Total lifetime hunts by " . htmlspecialchars($username) . ":</strong> {$previousHuntsAllGames}</p>";
        }

        if ($previousHuntsGame === 0) {
            $message .= "<p><strong>First dashpoint this game!</strong></p>";
        } else {
            $message .= "<p><strong>Previous hunts in this game by " . htmlspecialchars($username) . ":</strong> {$previousHuntsGame}</p>";
        }

        if (!empty($geoContext)) {
            $message .= "<p><strong>Location:</strong> " . htmlspecialchars($geoContext, ENT_QUOTES, 'UTF-8') . "</p>";
        }

        $message .= "<p><strong>Distance:</strong> {$distance} meters</p>";
        $message .= "<p><strong>Points Gained:</strong> {$points}</p>";
        $message .= "<p><strong>Points in this game:</strong> {$totalPointsGame}</p>";
        $message .= "<p><strong>Lifetime points:</strong> {$totalPointsAllGames}</p>";

        if (!empty($notes)) {
            $message .= "<h3>Field Notes</h3>";
            $message .= "<p>" . nl2br(htmlspecialchars($notes)) . "</p>";
        }

        if (!empty($photosJson)) {
            $photos = json_decode($photosJson, true);
            if (is_array($photos) && count($photos) > 0) {
                $message .= "<h3>Photos</h3>";
                foreach ($photos as $photoObj) {
                    if (is_array($photoObj) && !empty($photoObj['thumb_url']) && !empty($photoObj['url'])) {
                        $thumbUrl = $photoObj['thumb_url'];
                        $fullUrl = $photoObj['url'];
                        $message .= "<div style='margin-bottom: 10px;'>";
                        $message .= "<a href='" . htmlspecialchars($fullUrl, ENT_QUOTES, 'UTF-8') . "' target='_blank'>";
                        $message .= "<img src='" . htmlspecialchars($thumbUrl, ENT_QUOTES, 'UTF-8') . "' alt='Dashpoint Photo' style='max-width: 100%; height: auto;' />";
                        $message .= "</a>";
                        if (!empty($photoObj['caption'])) {
                            $message .= "<div style='font-style: italic; color: #555; font-size: 0.9em; margin-top: 5px;'>" . htmlspecialchars($photoObj['caption']) . "</div>";
                        }
                        $message .= "</div>";
                    }
                }
            }
        }

        $message .= "</body></html>";

        $this->executeMail($toList, $subject, $message);
    }

    /**
     * Constructs and dispatches an HTML email detailing a preview dashpoint reroll.
     *
     * @param string $username
     * @param string $dashpointId
     * @param float $oldLat
     * @param float $oldLon
     * @param float $newLat
     * @param float $newLon
     * @param int $rerollsLeft
     * @param int $maxRerolls
     * @param string|null $reason
     * @return void
     */
    protected function sendRerollNotificationEmail(
        string $username,
        string $dashpointId,
        float $oldLat,
        float $oldLon,
        float $newLat,
        float $newLon,
        int $rerollsLeft,
        int $maxRerolls,
        ?string $reason = null,
        ?string $oldGeoContext = null
    ): void {
        $configPath = __DIR__ . '/../config.ini';
        $config = file_exists($configPath) ? parse_ini_file($configPath) : [];
        $toList = getenv('REROLL_NOTIFICATION_EMAIL')
            ?: (($_ENV['REROLL_NOTIFICATION_EMAIL'] ?? null)
            ?: ($config['REROLL_NOTIFICATION_EMAIL'] ?? ($config['MAILING_LIST_ADDRESS'] ?? '')));

        if (empty($toList)) {
            return;
        }

        $subject = "[Geodashing Preview] Dashpoint {$dashpointId} Rerolled by {$username}";
        $profileUrl = "https://www.geodashing.org/#profile?username=" . urlencode($username);
        $dashpointUrl = "https://www.geodashing.org/#dashpoint?id=" . urlencode($dashpointId);
        $oldMapUrl = "https://www.google.com/maps?q={$oldLat},{$oldLon}";
        $newMapUrl = "https://www.geodashing.org/#dashpoint?id=" . urlencode($dashpointId);
        $newGoogleMapUrl = "https://www.google.com/maps?q={$newLat},{$newLon}";

        $message = "<html><body>";
        $message .= "<h2>Dashpoint Rerolled During Preview</h2>";
        $message .= "<p><strong>User:</strong> <a href='" . htmlspecialchars($profileUrl, ENT_QUOTES, 'UTF-8') . "'>" . htmlspecialchars($username) . "</a></p>";
        $message .= "<p><strong>Dashpoint:</strong> <a href='" . htmlspecialchars($dashpointUrl, ENT_QUOTES, 'UTF-8') . "'>" . htmlspecialchars($dashpointId) . "</a></p>";
        $message .= "<p><strong>Original Location:</strong> <a href='" . htmlspecialchars($oldMapUrl, ENT_QUOTES, 'UTF-8') . "' target='_blank'>{$oldLat}, {$oldLon}</a></p>";
        if (!empty($oldGeoContext)) {
            $message .= "<p style='margin-left: 20px; font-style: italic; color: #555;'>" . htmlspecialchars($oldGeoContext, ENT_QUOTES, 'UTF-8') . "</p>";
        }
        $message .= "<p><strong>New Location:</strong> <a href='" . htmlspecialchars($newMapUrl, ENT_QUOTES, 'UTF-8') . "'>{$newLat}, {$newLon} (Geodashing Map)</a> [<a href='" . htmlspecialchars($newGoogleMapUrl, ENT_QUOTES, 'UTF-8') . "' target='_blank'>Google Maps</a>]</p>";
        $message .= "<p><strong>Rerolls Remaining for Player:</strong> {$rerollsLeft} / {$maxRerolls}</p>";


        if (!empty($reason)) {
            $message .= "<h3>Reason for Reroll</h3>";
            $message .= "<p>" . nl2br(htmlspecialchars($reason)) . "</p>";
        }

        $message .= "</body></html>";

        $this->executeMail($toList, $subject, $message);
    }
}
