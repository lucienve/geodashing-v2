const { test, expect } = require('@playwright/test');

// Helper function to update geolocation 3 times and flush the rolling average buffer of size 3
async function setGeolocationAndFlush(context, page, latitude, longitude) {
    for (let i = 0; i < 3; i++) {
        await context.setGeolocation({ latitude, longitude });
        await page.waitForTimeout(150);
    }
}

test.describe('Proximity Radar HUD Integration Tests', () => {

    test.beforeEach(async ({ page, context }) => {
        // Log browser console output for E2E debugging
        page.on('console', msg => console.log(`[BROWSER CONSOLE ${msg.type()}] ${msg.text()}`));

        // 1. Grant geolocation permissions
        await context.grantPermissions(['geolocation']);
        
        // 2. Set default initial position far away from NYC point GD001-AAAA (40.7128, -74.0060)
        await context.setGeolocation({ latitude: 40.8000, longitude: -74.0060 }); // ~10km away

        // 3. Inject global spies to track navigator.geolocation watch position calls
        await page.addInitScript(() => {
            window.__activeWatches = [];
            window.__clearedWatchIds = [];

            const originalWatch = navigator.geolocation.watchPosition;
            const originalClear = navigator.geolocation.clearWatch;

            navigator.geolocation.watchPosition = function(success, error, options) {
                const id = originalWatch.apply(this, arguments);
                window.__activeWatches.push({ id, options });
                return id;
            };

            navigator.geolocation.clearWatch = function(id) {
                window.__clearedWatchIds.push(id);
                window.__activeWatches = window.__activeWatches.filter(w => w.id !== id);
                originalClear.apply(this, arguments);
            };
        });

        // 4. Dismiss Cookie Consent Banner globally if present
        await page.goto('/');
        await page.waitForLoadState('networkidle');

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
    });

    test('HUD remains hidden when user is far away (> 500m)', async ({ page, context }) => {
        // Target GD001-AAAA is at 40.7128, -74.0060. Geolocation is at 40.8000 (~10km away)
        await setGeolocationAndFlush(context, page, 40.8000, -74.0060);
        const hud = page.locator('#radar-hud');
        await expect(hud).toBeHidden();
    });

    test('HUD is displayed in Out-of-Range mode when approaching (<= 500m)', async ({ page, context }) => {
        // Move to 240m away: 40.7150, -74.0060
        await setGeolocationAndFlush(context, page, 40.7150, -74.0060);
        
        // Wait for HUD to become visible
        const hud = page.locator('#radar-hud');
        await expect(hud).toBeVisible({ timeout: 10000 });
        await expect(hud).toHaveClass(/out-of-range/);

        const targetLabel = page.locator('#radar-target-id');
        await expect(targetLabel).toHaveText('GD001-AAAA');

        const distanceText = page.locator('#radar-distance-text');
        await expect(distanceText).toContainText('244'); // ~244 meters

        // Verify the Log Visit button is hidden
        const logBtn = page.locator('#radar-btn-log');
        await expect(logBtn).toBeHidden();
    });

    test('HUD turns green and displays Log Visit button when in range (<= 100m)', async ({ page, context }) => {
        // Move to 22m away: 40.7130, -74.0060
        await setGeolocationAndFlush(context, page, 40.7130, -74.0060);

        const hud = page.locator('#radar-hud');
        await expect(hud).toBeVisible({ timeout: 10000 });
        await expect(hud).toHaveClass(/in-range/);

        const logBtn = page.locator('#radar-btn-log');
        await expect(logBtn).toBeVisible();
        await expect(logBtn).toBeEnabled();
    });

    test('Hysteresis buffer prevents HUD flickering near boundary splits', async ({ page, context }) => {
        const hud = page.locator('#radar-hud');

        // 1. Move inside the 100m range to trigger lock and in-range state
        await setGeolocationAndFlush(context, page, 40.7130, -74.0060); // ~22m away
        await expect(hud).toHaveClass(/in-range/, { timeout: 10000 });

        // 2. Move just past 100m (e.g. 104m away: 40.71374, -74.0060)
        await setGeolocationAndFlush(context, page, 40.71374, -74.0060);
        
        // Verify it maintains the "in-range" state due to hysteresis (110m limit)
        await expect(hud).toHaveClass(/in-range/);

        // 3. Move beyond the hysteresis exit boundary (> 110m, e.g. 122m: 40.7139, -74.0060)
        await setGeolocationAndFlush(context, page, 40.7139, -74.0060);
        await expect(hud).toHaveClass(/out-of-range/, { timeout: 10000 });
    });

    test('HUD panel collapses and expands correctly when toggle is clicked', async ({ page, context }) => {
        // Make HUD visible first
        await setGeolocationAndFlush(context, page, 40.7130, -74.0060);
        const hud = page.locator('#radar-hud');
        await expect(hud).toBeVisible({ timeout: 10000 });

        const toggleBtn = page.locator('#radar-hud-toggle');
        
        // Collapse panel
        await toggleBtn.click();
        await expect(hud).toHaveClass(/collapsed/);
        await expect(toggleBtn).toHaveText('▼');

        // Expand panel back
        await toggleBtn.click();
        await expect(hud).not.toHaveClass(/collapsed/);
        await expect(toggleBtn).toHaveText('▲');
    });

    test('Clicking Log Visit navigates directly to the reporting route with target ID', async ({ page, context }) => {
        await setGeolocationAndFlush(context, page, 40.7130, -74.0060);
        const logBtn = page.locator('#radar-btn-log');
        await expect(logBtn).toBeVisible({ timeout: 10000 });

        await logBtn.click();
        
        // Wait for page redirect to log report page
        await page.waitForURL(/#report\?id=GD001-AAAA/);
        const reportView = page.locator('#view-report');
        await expect(reportView).toBeVisible();

        const badge = page.locator('#dashpoint_id');
        await expect(badge).toHaveValue('GD001-AAAA');
    });

    test('Battery sleep on visibility change clears and re-registers watches', async ({ page, context }) => {
        // Move within 500m to activate watch
        await setGeolocationAndFlush(context, page, 40.7150, -74.0060);
        await expect(page.locator('#radar-hud')).toBeVisible({ timeout: 10000 });

        // Verify there is an active watch position ID
        await expect.poll(async () => {
            return await page.evaluate(() => window.__activeWatches.length);
        }).toBe(1);

        // Mock document visibilityState to 'hidden'
        await page.evaluate(() => {
            Object.defineProperty(document, 'visibilityState', { value: 'hidden', writable: true });
            document.dispatchEvent(new Event('visibilitychange'));
        });

        // Verify watch is cleared immediately to save battery
        await expect.poll(async () => {
            return await page.evaluate(() => window.__activeWatches.length);
        }).toBe(0);

        // Restore visibilityState to 'visible'
        await page.evaluate(() => {
            Object.defineProperty(document, 'visibilityState', { value: 'visible', writable: true });
            document.dispatchEvent(new Event('visibilitychange'));
        });

        // Verify watch is re-established
        await expect.poll(async () => {
            return await page.evaluate(() => window.__activeWatches.length);
        }).toBe(1);
    });

    test('Battery sleep on routing clears watch and restores it on home return', async ({ page, context }) => {
        // Move within 500m to activate watch
        await setGeolocationAndFlush(context, page, 40.7150, -74.0060);
        await expect(page.locator('#radar-hud')).toBeVisible({ timeout: 10000 });

        await expect.poll(async () => {
            return await page.evaluate(() => window.__activeWatches.length);
        }).toBe(1);

        // Navigate away to Leaderboard page
        await page.goto('/#leaderboard');
        await page.waitForLoadState('networkidle');

        // Verify watch is cleared on route change
        await expect.poll(async () => {
            return await page.evaluate(() => window.__activeWatches.length);
        }).toBe(0);

        // Navigate back home to map
        await page.goto('/');
        await page.waitForLoadState('networkidle');

        // Re-simulate position within range
        await setGeolocationAndFlush(context, page, 40.7150, -74.0060);
        await expect(page.locator('#radar-hud')).toBeVisible({ timeout: 10000 });

        // Verify watch is re-established
        await expect.poll(async () => {
            return await page.evaluate(() => window.__activeWatches.length);
        }).toBe(1);
    });

    test('Dynamic GPS Accuracy Gating switches accuracy modes based on proximity', async ({ page, context }) => {
        // Start far away (> 500m)
        await setGeolocationAndFlush(context, page, 40.8000, -74.0060);
        await page.waitForTimeout(2000);

        // Verify tracker is running in low-accuracy mode
        let currentOptions = await page.evaluate(() => {
            return window.__activeWatches[0] ? window.__activeWatches[0].options : null;
        });
        expect(currentOptions).not.toBeNull();
        expect(currentOptions.enableHighAccuracy).toBe(false);

        // Move inside 500m zone
        await setGeolocationAndFlush(context, page, 40.7150, -74.0060);
        
        // Wait for the accuracy upgrade trigger
        await page.waitForTimeout(1000);

        // Verify tracker has been upgraded to high-accuracy mode
        currentOptions = await page.evaluate(() => {
            return window.__activeWatches[0] ? window.__activeWatches[0].options : null;
        });
        expect(currentOptions).not.toBeNull();
        expect(currentOptions.enableHighAccuracy).toBe(true);
    });

});
