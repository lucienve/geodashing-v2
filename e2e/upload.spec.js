const { test, expect } = require('@playwright/test');
const path = require('path');

test.describe('Photo Upload Integration', () => {
    test.beforeEach(async ({ page }) => {
        await page.addInitScript(() => {
            window.localStorage.setItem('ga_consent', 'granted');
        });
        await page.goto('/');
    });

    test('Successful Photo Upload to Local GCS Emulator', async ({ page }, testInfo) => {
        // Guarantee parallel test isolation
        const dynamicUser = `Uploader_${Date.now()}_${testInfo.workerIndex}`;
        const dynamicPass = `SecurePass123!`;

        // Inject Default GPS
        const mockFn = () => {
            window.mockGeolocation = {
                getCurrentPosition: (success) => {
                    success({ coords: { latitude: 40.7128, longitude: -74.0060, accuracy: 10 } });
                }
            };
        };
        await page.addInitScript(mockFn);
        await page.evaluate(mockFn);

        // 1. Signup Flow
        await page.goto('/#login');
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
        expect(responseBody.status).toBe('success');

        // Force verify user natively
        const { execSync } = require('child_process');
        execSync(`mysql -h 127.0.0.1 -u geodashing_test -pgeodashing_test_secure_pass geodashing_test -e "UPDATE users SET is_verified = 1 WHERE username = '${dynamicUser}';"`);

        // Force navigate home to apply auth
        await page.goto('/#home');
        await page.waitForURL('**/#home', { timeout: 5000 });

        // Go to report modal for GD001-AAAA
        await page.goto('/#report?id=GD001-AAAA');
        await expect(page.locator('#dashpoint_id')).toHaveValue('GD001-AAAA');

        // Sync GPS
        await page.click('#btn-geolocation');
        await expect(page.locator('#input-lat')).not.toHaveValue('', { timeout: 10000 });
        await expect(page.locator('#input-lon')).not.toHaveValue('', { timeout: 10000 });
        
        await page.fill('#log-textarea', 'Logging a photo natively to the emulator!');

        // Upload our photo
        const imagePath = path.resolve(__dirname, '../images/android-chrome-192x192.png');
        await page.setInputFiles('#input-photos', imagePath);

        // Submit the report
        await page.click('#btn-submit-report');

        // Validate success response
        const feedback = page.locator('#report-feedback');
        await expect(feedback).toContainText('Success!', { timeout: 30000 }); // Uploads take slightly longer natively

        // Let's assert the visit ledger contains the image natively
        await page.goto('/#dashpoint?id=GD001-AAAA');
        const visitsContainer = page.locator('#dp-visits-container');
        const userVisit = visitsContainer.locator('> div').filter({ hasText: dynamicUser });
        await expect(userVisit).toBeVisible({ timeout: 10000 });

        // Expand the UI mapping to natively render the DOM tree visibility constraints
        await userVisit.locator('button', { hasText: 'VIEW DETAILS' }).click();

        // Ensure an img tag with the mapped public URL is visible logically
        // We know the mock emulator binds to http://127.0.0.1:4443
        const loadedImage = userVisit.locator('img');
        await expect(loadedImage.first()).toBeVisible({ timeout: 10000 });

        // Logically verify the image src is hitting our emulator
        const srcAttr = await loadedImage.first().getAttribute('src');
        expect(srcAttr).toContain('http://127.0.0.1:4443/');
    });
});
