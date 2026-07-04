const { test, expect } = require('@playwright/test');

test.describe('Actual Log Locations Map Markers', () => {

    test.beforeEach(async ({ page, context }) => {
        // Log browser console output for E2E debugging
        page.on('console', msg => console.log(`[BROWSER CONSOLE ${msg.type()}] ${msg.text()}`));

        // Grant geolocation permissions and set location in London (Game 1 dashpoint location)
        await context.grantPermissions(['geolocation']);
        await context.setGeolocation({ latitude: 51.5074, longitude: -0.1278 });

        // Navigate to homepage and wait for map to load
        await page.goto('/');
        await page.waitForLoadState('networkidle');

        // Dismiss Cookie Consent Banner if present
        const cookieBanner = page.locator('.cookie-banner');
        try {
            if (await cookieBanner.isVisible({ timeout: 500 })) {
                const acceptBtn = page.locator('.btn-accept');
                if (await acceptBtn.isVisible({ timeout: 500 })) {
                    await acceptBtn.click();
                    await expect(cookieBanner).not.toBeVisible();
                }
            }
        } catch (err) {
            console.warn("Cookie banner acceptance skipped or failed:", err);
        }

        // Wait for the Google Map instance to be initialized
        await page.waitForFunction(() => window.__geodashingMap !== undefined, { timeout: 10000 });

        // Wait for the game context to be loaded
        await page.evaluate(async () => {
            await window.gameContextLoaded;
        });

        // Switch to Game 1 context!
        await page.selectOption('#game-selector', '1');

        // Wait for user position watcher to start
        await page.waitForFunction(() => window.currentUserPosition !== undefined, { timeout: 10000 });

        // Wait an additional moment for initial setCenter/setZoom to settle
        await page.waitForTimeout(1000);
    });

    test('Visit markers are hidden at lower zoom and visible at higher zoom levels', async ({ page }) => {
        // 1. Zoom to 14 (not zoomed in sufficiently, visits should not render)
        await page.evaluate(() => {
            window.__geodashingMap.setCenter({ lat: 51.5074, lng: -0.1278 });
            window.__geodashingMap.setZoom(14);
        });

        // Wait to clear any potential transitions
        await page.waitForTimeout(1000);

        const markers = page.locator('.visit-marker-container');
        await expect(markers).toHaveCount(0);

        // 2. Zoom to 16 (sufficiently zoomed in)
        await page.evaluate(() => {
            window.__geodashingMap.setZoom(16);
        });

        // Wait for API and rendering
        await page.waitForFunction(() => document.querySelectorAll('.visit-marker-container').length === 2, { timeout: 10000 });

        const successMarker = page.locator('.visit-marker-container:not(.attempt)');
        const attemptMarker = page.locator('.visit-marker-container.attempt');

        await expect(successMarker).toBeVisible();
        await expect(attemptMarker).toBeVisible();

        await expect(successMarker.locator('.visit-marker-label')).toHaveText('TestUser');
        await expect(attemptMarker.locator('.visit-marker-label')).toHaveText('TestUser');

        // 3. Zoom back out to 14
        await page.evaluate(() => {
            window.__geodashingMap.setZoom(14);
        });

        // Markers should disappear immediately on zoom change
        await expect(markers).toHaveCount(0);
    });

    test('Clicking a visit marker navigates to the dashpoint details view', async ({ page }) => {
        // Zoom to 16 to reveal markers
        await page.evaluate(() => {
            window.__geodashingMap.setCenter({ lat: 51.5074, lng: -0.1278 });
            window.__geodashingMap.setZoom(16);
        });

        await page.waitForFunction(() => document.querySelectorAll('.visit-marker-container').length === 2, { timeout: 10000 });

        const successMarker = page.locator('.visit-marker-container:not(.attempt) .visit-marker-label');
        await successMarker.click();

        // Should update hash route and load the dashpoint page details
        await page.waitForURL(/#dashpoint\?id=GD000-AAAA/);
        const dashpointView = page.locator('#view-dashpoint');
        await expect(dashpointView).toBeVisible();
    });

});
