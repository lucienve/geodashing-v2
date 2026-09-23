const { test, expect } = require('@playwright/test');

test.describe('Map Navigation & Deep Linking Behavior', () => {
    
    test.beforeEach(async ({ context }) => {
        // Set a recognizable test location (e.g., London, UK)
        // This simulates the user's physical GPS coordinate
        await context.grantPermissions(['geolocation']);
        await context.setGeolocation({ latitude: 51.5074, longitude: -0.1278 });
    });

    test('Deep-linking to a dashpoint prevents native GPS auto-centering', async ({ page }) => {
        // We navigate to a dashpoint deep link without triggering the default home route
        await page.goto('/#dashpoint?id=GD001-AAAA');
        
        // Wait for the app and map to fully initialize
        await page.waitForLoadState('networkidle');
        
        // Wait for the dashpoint UI to be visibly mounted 
        // This ensures the application router has caught the deep link and rendered the template
        await expect(page.locator('#view-dashpoint')).toBeVisible({ timeout: 15000 });

        // Await the instantiation of the exposed global map object
        await page.waitForFunction(() => window.__geodashingMap !== undefined, { timeout: 10000 });

        // We must also wait for the geolocation API callback to potentially execute in map.js.
        // Giving it 2.5 seconds easily clears the asynchronous callback execution timeframe.
        await page.waitForTimeout(2500);

        // Retrieve the current map center naturally processed by Google Maps
        const mapCenter = await page.evaluate(() => {
            if (window.__geodashingMap) {
                return {
                    lat: window.__geodashingMap.getCenter().lat(),
                    lng: window.__geodashingMap.getCenter().lng()
                };
            }
            return null;
        });
        
        expect(mapCenter).not.toBeNull();
        
        // Assert the map center has NOT snapped to the user's mocked GPS location (London: 51.5074, -0.1278)
        // If the regression occurs, the map would blindly follow the geolocation tracker and snap to London
        // ignoring the fact the user is specifically deep-linked to a dashpoint.
        const latitudeDiff = Math.abs(mapCenter.lat - 51.5074);
        const longitudeDiff = Math.abs(mapCenter.lng - -0.1278);

        // The exact center should be noticeably disconnected from the GPS mock
        expect(latitudeDiff).toBeGreaterThan(0.5);
        expect(longitudeDiff).toBeGreaterThan(0.5);
    });

    test('Deep-linking to a dashpoint sets zoom level to 10', async ({ page }) => {
        await page.goto('/#dashpoint?id=GD001-AAAA');
        await page.waitForLoadState('networkidle');
        await expect(page.locator('#view-dashpoint')).toBeVisible({ timeout: 15000 });
        await page.waitForFunction(() => window.__geodashingMap !== undefined, { timeout: 10000 });
        await expect(page.locator('#dp-id-label')).toHaveText('GD001-AAAA', { timeout: 10000 });

        const zoom = await page.evaluate(() => window.__geodashingMap.getZoom());
        expect(zoom).toBe(10);
    });

    test('Clicking a dashpoint marker on the map preserves close zoom and gently pans', async ({ page, context }) => {
        // Set geolocation to NYC slightly south of the dashpoint to prevent the location blue dot from overlapping the marker
        await context.setGeolocation({ latitude: 40.7000, longitude: -74.0100 });

        await page.goto('/#home');
        await page.waitForLoadState('networkidle');

        // Dismiss cookie banner if present
        const cookieBanner = page.locator('.cookie-banner');
        try {
            if (await cookieBanner.isVisible({ timeout: 1000 })) {
                const acceptBtn = page.locator('.btn-accept');
                if (await acceptBtn.isVisible({ timeout: 500 })) {
                    await acceptBtn.click();
                }
            }
        } catch (_err) {
            // Ignore if cookie banner not present
        }

        // Wait for map and dashpoints to load
        await page.waitForFunction(() => window.__geodashingMap !== undefined, { timeout: 10000 });
        await page.waitForFunction(() => window.loadedDashpoints && window.loadedDashpoints.length > 0, { timeout: 10000 });

        // Zoom into NYC at level 16
        await page.evaluate(() => {
            window.__geodashingMap.setCenter({ lat: 40.7128, lng: -74.0060 });
            window.__geodashingMap.setZoom(16);
        });

        // Allow idle listener and marker rendering to settle
        await page.waitForTimeout(1000);

        // Find and click the visible marker pin
        const marker = page.locator('.custom-pin-container').first();
        await expect(marker).toBeVisible({ timeout: 10000 });
        await marker.click({ force: true });

        // Wait for dashpoint view and ensure ledger fetch completed
        await expect(page.locator('#view-dashpoint')).toBeVisible({ timeout: 15000 });
        await expect(page.locator('#dp-id-label')).not.toHaveText('[ LOADING ]', { timeout: 10000 });

        // Assert that zoom level is preserved at 16 (not reset to 10)
        const zoom = await page.evaluate(() => window.__geodashingMap.getZoom());
        expect(zoom).toBe(16);

        // Assert that map panned to near the target dashpoint
        const center = await page.evaluate(() => ({
            lat: window.__geodashingMap.getCenter().lat(),
            lng: window.__geodashingMap.getCenter().lng()
        }));
        expect(Math.abs(center.lat - 40.7128)).toBeLessThan(0.05);
        expect(Math.abs(center.lng - (-74.0060))).toBeLessThan(0.05);
    });

});
