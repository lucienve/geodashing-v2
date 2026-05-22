const { test, expect } = require('@playwright/test');

test.describe('Core Functional Game Loop', () => {
    test.beforeEach(async ({ page }) => {
        await page.addInitScript(() => {
            window.localStorage.setItem('ga_consent', 'granted');
        });
        await page.goto('/');
    });

    test('Authenticate via Login UI', async ({ page }) => {
        await page.goto('/#login');

        // Wait for login view to be visible
        await expect(page.locator('#view-login')).toBeVisible();

        await page.fill('#login-username', 'TestUser');
        await page.fill('#login-password', 'testpass');
        await page.click('#btn-submit-login');

        // Expect auth state to update globally. The label becomes LOGOUT [TestUser].
        // Because of the 800ms redirect in app.js, we should wait for #home
        await page.waitForURL('**/#home');

        const desktopAuthBtn = page.locator('#nav-auth-btn');
        await expect(desktopAuthBtn).toContainText('LOGOUT [TestUser]');
    });

    test('Geolocation Bounds Validation - Too Far Rejection', async ({ page }) => {
        // Inject E2E Mock Geolocation via window.mockGeolocation
        const mockFn = () => {
            window.mockGeolocation = {
                getCurrentPosition: (success, _error, _options) => {
                    success({ coords: { latitude: 51.5074, longitude: -0.1278, accuracy: 10 } });
                }
            };
        };
        await page.addInitScript(mockFn);
        await page.evaluate(mockFn);

        // Authenticate
        await page.goto('/#login');
        await page.fill('#login-username', 'TestUser');
        await page.fill('#login-password', 'testpass');
        await page.click('#btn-submit-login');
        await page.waitForURL('**/#home');

        // Go to specific dashpoint report
        await page.goto('/#report?id=GD001-AAAA');
        await expect(page.locator('#dashpoint_id')).toHaveValue('GD001-AAAA', { timeout: 10000 });

        // Sync GPS
        await page.click('#btn-geolocation');

        // Wait for inputs to populate
        await expect(page.locator('#input-lat')).not.toHaveValue('', { timeout: 10000 });
        await expect(page.locator('#input-lon')).not.toHaveValue('', { timeout: 10000 });

        await page.fill('#log-textarea', 'Attempting a spoof log from London!');
        await page.click('#btn-submit-report');

        const feedback = page.locator('#report-feedback');
        await expect(feedback).toContainText('Too far away', { timeout: 10000 });
    });

    test('Geolocation Bounds Validation - Successful Attempt Logging', async ({ page }, testInfo) => {
        // Inject E2E Mock Geolocation via window.mockGeolocation
        const mockFn = () => {
            window.mockGeolocation = {
                getCurrentPosition: (success, _error, _options) => {
                    success({ coords: { latitude: 51.5074, longitude: -0.1278, accuracy: 10 } }); // Far from NYC
                }
            };
        };
        await page.addInitScript(mockFn);
        await page.evaluate(mockFn);

        const dynamicUser = `Attempter_${Date.now()}_${testInfo.workerIndex}`;
        const dynamicPass = `SecurePass123!`;
        
        await page.goto('/#login');
        await page.click('#toggle-signup');
        await page.fill('#signup-username', dynamicUser);
        await page.fill('#signup-email', `${dynamicUser}@example.com`);
        await page.fill('#signup-password', dynamicPass);
        await page.fill('#signup-password-verify', dynamicPass);
        
        await Promise.all([
            page.waitForResponse(res => res.url().includes('auth.php?action=signup')),
            page.click('#btn-submit-signup')
        ]);
        
        const { execSync } = require('child_process');
        execSync(`mysql -h 127.0.0.1 -u geodashing_test -pgeodashing_test_secure_pass geodashing_test -e "UPDATE users SET is_verified = 1 WHERE username = '${dynamicUser}';"`);

        await page.waitForURL('**/#login', { timeout: 5000 });
        await page.goto('/#home');
        await page.waitForURL('**/#home', { timeout: 5000 });

        // Go to specific dashpoint report
        await page.goto('/#report?id=GD001-AAAA');
        await expect(page.locator('#dashpoint_id')).toHaveValue('GD001-AAAA', { timeout: 10000 });

        // Sync GPS
        await page.click('#btn-geolocation');
        await expect(page.locator('#input-lat')).not.toHaveValue('', { timeout: 10000 });
        await expect(page.locator('#input-lon')).not.toHaveValue('', { timeout: 10000 });

        // Check Attempt
        await page.check('#input-is-attempt');

        await page.fill('#log-textarea', 'Logging an attempt from London!');
        await page.click('#btn-submit-report');

        const feedback = page.locator('#report-feedback');
        await expect(feedback).toContainText('Attempt logged.', { timeout: 10000 });
    });

    test('Successful Dashpoint Log and Ledger Verification', async ({ page }, testInfo) => {
        test.setTimeout(60000);

        // Guarantee parallel test isolation without global DELETE statements by creating a native account per-test.
        const dynamicUser = `Worker_${Date.now()}_${testInfo.workerIndex}`;
        const dynamicPass = `SecurePass123!`;

        // Inject E2E Mock Geolocation (NYC mapping to GD001-AAAA) via window.mockGeolocation directly
        const mockFn = () => {
            window.mockGeolocation = {
                getCurrentPosition: (success, _error, _options) => {
                    success({ coords: { latitude: 40.7128, longitude: -74.0060, accuracy: 10 } });
                }
            };
        };
        await page.addInitScript(mockFn);
        await page.evaluate(mockFn);

        // 1. Dynamically execute native Signup Flow. 
        await page.goto('/#login');

        // Toggle standard layout tabs.
        await page.click('#toggle-signup');
        await page.fill('#signup-username', dynamicUser);
        await page.fill('#signup-email', `${dynamicUser}@example.com`);
        await page.fill('#signup-password', dynamicPass);
        await page.fill('#signup-password-verify', dynamicPass);
        const [response] = await Promise.all([
            page.waitForResponse(res => res.url().includes('auth.php?action=signup')),
            page.click('#btn-submit-signup')
        ]);
        const responseBody = await response.json();

        await expect(responseBody.status).toBe('success');

        // Explicitly bypass Email Verification constraint with a fast DB hit to ensure our dynamic user is authorized to play.
        const { execSync } = require('child_process');
        execSync(`mysql -h 127.0.0.1 -u geodashing_test -pgeodashing_test_secure_pass geodashing_test -e "UPDATE users SET is_verified = 1 WHERE username = '${dynamicUser}';"`);

        // Wait dynamically for the frontend to naturally redirect to login (1.5s delay)
        // to clear the setTimeout race condition, then force navigate to home.
        await page.waitForURL('**/#login', { timeout: 5000 });
        await page.goto('/#home');
        await page.waitForURL('**/#home', { timeout: 5000 });

        // Go to specific dashpoint report
        await page.goto('/#report?id=GD001-AAAA');
        await expect(page.locator('#dashpoint_id')).toHaveValue('GD001-AAAA');

        // Sync GPS
        await page.click('#btn-geolocation');
        await expect(page.locator('#input-lat')).not.toHaveValue('', { timeout: 10000 });
        await expect(page.locator('#input-lon')).not.toHaveValue('', { timeout: 10000 });

        await page.fill('#log-textarea', 'Found it! Great dashpoint.');
        await page.click('#btn-submit-report');

        // Validate success response
        const feedback = page.locator('#report-feedback');
        await expect(feedback).toContainText('Success!', { timeout: 10000 });

        // Navigate to dashpoint ledger explicitly to ensure it shows up in general visits. Wait for successful post first.
        await page.goto('/#dashpoint?id=GD001-AAAA');

        const visitsContainer = page.locator('#dp-visits-container');
        await expect(visitsContainer).toContainText(dynamicUser, { timeout: 10000 });
        await expect(visitsContainer).toContainText('PT', { timeout: 10000 });

        // Navigate to profile to verify scoring linkage
        await page.goto(`/#profile?username=${encodeURIComponent(dynamicUser)}`);

        const profileContainer = page.locator('#profile-container');
        await expect(profileContainer).toContainText('GD001-AAAA', { timeout: 10000 });
    });
});
