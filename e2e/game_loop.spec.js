const { test, expect } = require('@playwright/test');

test.describe('Core Functional Game Loop', () => {
    test.beforeEach(async ({ page }) => {
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
        // Grant permissions and spoof location to London
        await page.context().grantPermissions(['geolocation']);
        await page.context().setGeolocation({ latitude: 51.5074, longitude: -0.1278 });

        // Authenticate
        await page.goto('/#login');
        // Dismiss cookie banner
        const cookieBtn = page.locator('#btn-accept-cookies');
        if (await cookieBtn.isVisible()) {
            await cookieBtn.click();
        }
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
        await expect(page.locator('#input-lat')).not.toBeEmpty({ timeout: 10000 });
        await expect(page.locator('#input-lon')).not.toBeEmpty({ timeout: 10000 });

        await page.fill('#log-textarea', 'Attempting a spoof log from London!');
        await page.click('#btn-submit-report');
        
        const feedback = page.locator('#report-feedback');
        await expect(feedback).toContainText('Too far away', { timeout: 10000 });
    });

    test('Successful Dashpoint Log and Ledger Verification', async ({ page }) => {
        // Mock proper GPS location matching test dashpoint GD001-AAAA exactly
        await page.context().grantPermissions(['geolocation']);
        await page.context().setGeolocation({ latitude: 40.7128, longitude: -74.0060 });

        // Authenticate
        await page.goto('/#login');
        // Dismiss cookie banner
        const cookieBtn = page.locator('#btn-accept-cookies');
        if (await cookieBtn.isVisible()) {
            await cookieBtn.click();
        }
        await page.fill('#login-username', 'TestUser');
        await page.fill('#login-password', 'testpass');
        await page.click('#btn-submit-login');
        await page.waitForURL('**/#home');

        // Go to specific dashpoint report
        await page.goto('/#report?id=GD001-AAAA');
        await expect(page.locator('#dashpoint_id')).toHaveValue('GD001-AAAA');
        
        // Sync GPS
        await page.click('#btn-geolocation');
        await expect(page.locator('#input-lat')).not.toBeEmpty();
        
        await page.fill('#log-textarea', 'Found it! Great dashpoint.');
        await page.click('#btn-submit-report');
        
        // Validate success response
        const feedback = page.locator('#report-feedback');
        await expect(feedback).toContainText('Success!');

        // Navigate to dashpoint ledger explicitly to ensure it shows up in general visits. Wait for successful post first.
        await page.goto('/#dashpoint?id=GD001-AAAA');
        
        const visitsContainer = page.locator('#dp-visits-container');
        await expect(visitsContainer).toContainText('TestUser');
        await expect(visitsContainer).toContainText('PT'); 

        // Navigate to profile to verify scoring linkage
        await page.goto('/#profile?id=1');
        
        const profileContainer = page.locator('#profile-container');
        await expect(profileContainer).toContainText('GD001-AAAA');
    });
});
