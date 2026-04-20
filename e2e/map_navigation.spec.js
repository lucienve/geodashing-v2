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

});
