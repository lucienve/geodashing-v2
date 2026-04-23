<?php

declare(strict_types=1);

namespace App\Services;

/**
 * Trait MailerTrait
 *
 * Provides a unified mail header generation and safe execution wrapper
 * for classes needing to dispatch emails.
 */
trait MailerTrait
{
    /**
     * Builds standardized mail headers.
     *
     * @param string $fromEmail The email address representing the sender.
     * @param string $fromName  Optional name for the sender.
     * @param bool   $isHtml    If true, injects MIME headers for HTML email rendering.
     * @return string Complete headers string separated by \r\n
     */
    protected function buildMailHeaders(string $fromEmail, string $fromName = '', bool $isHtml = false): string
    {
        $fromStr = $fromName ? "{$fromName} <{$fromEmail}>" : $fromEmail;
        $headers = "From: {$fromStr}\r\n";
        $headers .= "Reply-To: {$fromStr}\r\n";

        if ($isHtml) {
            $headers .= "MIME-Version: 1.0\r\n";
            $headers .= "Content-Type: text/html; charset=UTF-8\r\n";
        }

        $headers .= "X-Mailer: PHP/" . phpversion();

        return $headers;
    }

    /**
     * Executes email delivery. Protected specifically to allow PHPUnit mocking.
     *
     * @param string $to
     * @param string $subject
     * @param string $message
     * @param string $headers
     * @param string $additional_params
     * @return bool
     */
    protected function executeMail(string $to, string $subject, string $message, string $headers, string $additional_params): bool
    {
        // Bypass physical SMTP interaction during E2E testing
        if ((getenv('APP_ENV') ?: ($_ENV['APP_ENV'] ?? '')) === 'testing') {
            error_log("APP_ENV=testing: Suppressed physical email transmission to $to");
            return true;
        }

        return @mail($to, $subject, $message, $headers, $additional_params);
    }

    /**
     * Constructs and dispatches an HTML email to the mailing list detailing the new Dashpoint visit or edit.
     */
    protected function sendVisitReportEmail(string $username, string $dashpointId, int $distance, int $points, int $totalPoints, bool $isAttempt, ?string $notes, ?string $photosJson, ?string $geoContext = null, bool $isEdit = false): void
    {
        $configPath = __DIR__ . '/../config.ini';
        $config = file_exists($configPath) ? parse_ini_file($configPath) : [];
        $toList = $config['MAILING_LIST_ADDRESS'] ?? '';

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
        $profileUrl = "https://www.geodashing.org/?profile=" . urlencode($username);
        $message .= "<p><strong>User:</strong> <a href='" . htmlspecialchars($profileUrl, ENT_QUOTES, 'UTF-8') . "'>" . htmlspecialchars($username) . "</a></p>";
        $dashpointUrl = "https://www.geodashing.org/?dashpoint=" . urlencode($dashpointId);
        $message .= "<p><strong>Dashpoint:</strong> <a href='" . htmlspecialchars($dashpointUrl, ENT_QUOTES, 'UTF-8') . "'>" . htmlspecialchars($dashpointId) . "</a></p>";
        
        if (!empty($geoContext)) {
            $message .= "<p><strong>Location:</strong> " . htmlspecialchars($geoContext, ENT_QUOTES, 'UTF-8') . "</p>";
        }

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
