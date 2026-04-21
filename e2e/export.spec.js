const { test, expect } = require('@playwright/test');
const fs = require('fs');

test.describe('Export Functionality', () => {

    test.beforeEach(async ({ page }) => {
        // Authenticate as TestUser to access export endpoint
        await page.goto('/#login');
        await page.fill('#login-username', 'TestUser');
        await page.fill('#login-password', 'testpass');

        // Hide cookie banner unconditionally to prevent interception
        await page.evaluate(() => {
            const style = document.createElement('style');
            style.innerHTML = '#cookie-consent-banner { display: none !important; }';
            document.head.appendChild(style);
        });

        // Trigger login and ensure the API call completes
        await Promise.all([
            page.waitForResponse(resp => resp.url().includes('action=login') && resp.status() === 200),
            page.click('#btn-submit-login')
        ]);
        
        // Ensure successful login navigates away
        await page.waitForURL('**/#home');

        // Navigate to the scanner/search interface
        await page.goto('/#search');
        await expect(page.locator('#btn-export-gpx')).toBeVisible();
    });

    test('Successful GPX Export with Dashpoints', async ({ page }) => {
        // Enter bounds containing NYC mock dashpoint (GD001-AAAA)
        await page.fill('#search-n', '45.0');
        await page.fill('#search-s', '35.0');
        await page.fill('#search-e', '-70.0');
        await page.fill('#search-w', '-80.0');

        // Setup download listener
        const downloadPromise = page.waitForEvent('download');
        
        // Trigger export
        await page.click('#btn-export-gpx', { force: true });
        
        // Wait for download to trigger and complete
        const download = await downloadPromise;
        expect(download.suggestedFilename()).toBe('geodashing_v2_export.gpx');

        // Read the downloaded file stream in memory
        const path = await download.path();
        const fileContent = fs.readFileSync(path, 'utf8');

        // Assert valid GPX syntax and the presence of the mock point
        expect(fileContent).toContain('<?xml version="1.0" encoding="UTF-8"?>');
        expect(fileContent).toContain('version="1.1"');
        expect(fileContent).toContain('<name>GD001-AAAA</name>');
        expect(fileContent).toContain('</gpx>');
    });

    test('Successful LOC Export with Dashpoints', async ({ page }) => {
        // Enter bounds containing NYC mock dashpoint (GD001-AAAA)
        await page.fill('#search-n', '45.0');
        await page.fill('#search-s', '35.0');
        await page.fill('#search-e', '-70.0');
        await page.fill('#search-w', '-80.0');

        // Setup download listener
        const downloadPromise = page.waitForEvent('download');
        
        // Trigger export
        await page.click('#btn-export-loc', { force: true });
        
        // Wait for download to trigger and complete
        const download = await downloadPromise;
        expect(download.suggestedFilename()).toBe('geodashing_v2_export.loc');

        // Read the downloaded file stream in memory
        const path = await download.path();
        const fileContent = fs.readFileSync(path, 'utf8');

        // Assert valid LOC syntax and the presence of the mock point
        expect(fileContent).toContain('<?xml version="1.0" encoding="UTF-8"?>');
        expect(fileContent).toContain('<loc version="1.0"');
        expect(fileContent).toContain('<name id="GD001-AAAA">GD001-AAAA</name>');
        expect(fileContent).toContain('</loc>');
    });

    test('Empty GPX Export when No Dashpoints in Region', async ({ page }) => {
        // Enter bounds safely far away from NYC (Lat 0-10, Lon 0-10)
        await page.fill('#search-n', '10.0');
        await page.fill('#search-s', '0.0');
        await page.fill('#search-e', '10.0');
        await page.fill('#search-w', '0.0');

        // Setup download listener
        const downloadPromise = page.waitForEvent('download');
        
        // Trigger export
        await page.click('#btn-export-gpx', { force: true });
        
        // Wait for download to trigger and complete
        const download = await downloadPromise;
        expect(download.suggestedFilename()).toBe('geodashing_v2_export.gpx');

        // Read the downloaded file stream in memory
        const path = await download.path();
        const fileContent = fs.readFileSync(path, 'utf8');

        // Assert valid GPX syntax but explicitly lacking wpt nodes
        expect(fileContent).toContain('<?xml version="1.0" encoding="UTF-8"?>');
        expect(fileContent).toContain('version="1.1"');
        expect(fileContent).not.toContain('<wpt');
    });

    test('Validation Error on Missing Coordinates', async ({ page }) => {
        // Intentionally missing the West coordinate
        await page.fill('#search-n', '45.0');
        await page.fill('#search-s', '35.0');
        await page.fill('#search-e', '-70.0');
        await page.fill('#search-w', '');

        await page.click('#btn-export-gpx', { force: true });

        // Verify the native DOM feedback triggers securely without navigating
        const feedback = page.locator('#search-feedback');
        await expect(feedback).toBeVisible();
        await expect(feedback).toContainText('Error: Missing coordinates.');
    });
});
