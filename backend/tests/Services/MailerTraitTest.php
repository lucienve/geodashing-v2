<?php

declare(strict_types=1);

namespace App\Tests\Services;

use App\Services\MailerTrait;
use PHPUnit\Framework\TestCase;
use PHPUnit\Framework\Attributes\Test;

class MailerTraitTest extends TestCase
{
    protected function setUp(): void
    {
        // Force the testing environment variable just in case
        putenv('APP_ENV=testing');
        $_ENV['APP_ENV'] = 'testing';
    }

    #[Test]
    public function testExecuteMailBypassesApiInTestingEnv()
    {
        // Anonymous class to expose the trait
        $mailer = new class {
            use MailerTrait {
                executeMail as public publicExecuteMail;
            }
        };

        // This will trigger the APP_ENV=testing early return
        // No Google_Client will be instantiated and no exceptions will be thrown.
        $result = $mailer->publicExecuteMail("test@example.com", "Subject", "<h1>HTML</h1>", "Text");

        $this->assertTrue($result, "Expected executeMail to return true immediately when APP_ENV=testing");
    }

    #[Test]
    public function testSendVisitReportConstructsProperHtml()
    {
        // Anonymous class to intercept executeMail
        $mailer = new class {
            use MailerTrait;

            public $lastTo = null;
            public $lastSubject = null;
            public $lastHtmlMessage = null;
            public $lastTextMessage = null;

            protected function executeMail(string $to, string $subject, string $htmlMessage, ?string $textMessage = null): bool
            {
                $this->lastTo = $to;
                $this->lastSubject = $subject;
                $this->lastHtmlMessage = $htmlMessage;
                $this->lastTextMessage = $textMessage;
                return true;
            }

            public function publicSendVisitReportEmail(string $username, string $dashpointId, int $distance, int $points, int $totalPoints, bool $isAttempt, ?string $notes, ?string $photosJson, ?string $geoContext = null, bool $isEdit = false): void
            {
                $this->sendVisitReportEmail($username, $dashpointId, $distance, $points, $totalPoints, $isAttempt, $notes, $photosJson, $geoContext, $isEdit);
            }
        };

        // Create a fake config.ini structure for the test
        $configPath = __DIR__ . '/../../services/../config.ini';
        if (!file_exists(dirname($configPath))) {
            mkdir(dirname($configPath), 0777, true);
        }
        if (!file_exists($configPath)) {
            file_put_contents($configPath, "[mail]\nMAILING_LIST_ADDRESS = \"dashers@geodashing.org\"\n");
        }

        $mailer->publicSendVisitReportEmail(
            "Lucien",
            "DP123",
            5000,
            10,
            100,
            false,
            "Found it!",
            json_encode([["url" => "http://example.com/photo.jpg"]]),
            "Forest"
        );

        $this->assertEquals("dashers@geodashing.org", $mailer->lastTo);
        $this->assertEquals("New Dashpoint Log: Lucien claimed DP123", $mailer->lastSubject);

        // Validate HTML content
        $this->assertStringContainsString("<h2>New Dashpoint Log</h2>", $mailer->lastHtmlMessage);
        $this->assertStringContainsString("Lucien", $mailer->lastHtmlMessage);
        $this->assertStringContainsString("DP123", $mailer->lastHtmlMessage);
        $this->assertStringContainsString("5000 meters", $mailer->lastHtmlMessage);
        $this->assertStringContainsString("Found it!", $mailer->lastHtmlMessage);
        $this->assertStringContainsString("http://example.com/photo.jpg", $mailer->lastHtmlMessage);
    }
}
