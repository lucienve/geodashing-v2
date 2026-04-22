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
}
