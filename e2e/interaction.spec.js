const { test, expect } = require('@playwright/test');

test.describe('Component & Interactive Layout Constraints', () => {
    // These tests do a lot of physical page routing across devices and need time to breathe over the PHP stack
    test.setTimeout(90000);

    test.beforeEach(async ({ page }) => {
        await page.goto('/');

        // Let the SPA router and dynamic Map layer settle
        await page.waitForLoadState('networkidle');

        // 1. Dismiss Cookie Consent Banner if present
        const cookieBanner = page.locator('.cookie-banner');
        if (await cookieBanner.isVisible()) {
            const acceptBtn = page.locator('.btn-accept');
            if (await acceptBtn.isVisible()) {
                await acceptBtn.click();
                await expect(cookieBanner).not.toBeVisible();
            }
        }
    });

    test('Map controls render safely above OS bounds', async ({ page }) => {
        // Find the custom "My Location" SVG button
        const recenterBtn = page.locator('button[title="Recenter Map on Current Location"]');
        
        // Wait for google maps to inject the UI overlays
        await expect(recenterBtn).toBeVisible({ timeout: 10000 });
        
        // Validate clickability directly (Playwright throws if covered/hidden)
        // Ensure to pass true to trial so it just verifes clickability without actually triggering geolocation API
        await recenterBtn.click({ trial: true });

        // The Google Map Type Toggle (Satellite vs Terrain toggle)
        const mapTypeToggle = page.locator('button[title="Show street map"], button[title="Show satellite imagery"]').first();
        if (await mapTypeToggle.isVisible()) {
             // Perform a click to pop open the secondary overlay context
             await mapTypeToggle.click({ force: true }); // Google Maps layers can be tricky, force the dispatch
             
             // Wait for the Google Maps submenu to render 'Terrain' or 'Labels'
             const subMenuText = page.locator('text=/Terrain|Labels/i').first();
             // Verify the sub-checkboxes pop out without getting blocked.
             await expect(subMenuText).toBeVisible({ timeout: 15000 });
        }
    });

    test('Menu template overlays invoke successfully and confine without clipping', async ({ page, isMobile }) => {
        // Define all textual menu links that trigger a Template View overlay
        const routes = [
            { id: '#leaderboard', type: 'link' },
            { id: '#about', type: 'dropdown' },
            { id: '#how-to', type: 'dropdown' },
            { id: '#contact', type: 'dropdown' },
            { id: '#search', type: 'dropdown' }
        ];

        for (const route of routes) {
            // Re-center application safely before each interaction
            await page.goto('/');
            await page.waitForLoadState('networkidle'); // Allow DOM reset

            if (isMobile) {
                // Open Hamburger
                const menuBtn = page.locator('#mobile-menu-btn');
                await menuBtn.click();
                await page.waitForTimeout(350); // slide transition

                // Click link securely
                const link = page.locator(`#mobile-nav-drawer a.nav-link[href="${route.id}"]`);
                await expect(link).toBeVisible();
                await link.click();
            } else {
                if (route.type === 'dropdown') {
                    // Hover glass dropdown to reveal
                    await page.locator('text="HELP ▾"').first().hover();
                    await page.waitForTimeout(200); // Allow rapid CSS state change
                }
                const link = page.locator(`#desktop-links a.nav-link[href="${route.id}"]`);
                await expect(link).toBeVisible();
                await link.click();
            }

            // We must wait for the template-view to be fetched and sliding animation to finish
            const templateView = page.locator('.template-view').first();
            await expect(templateView).toBeVisible();

            // Verify a Close button exists and is correctly structured
            const closeBtn = templateView.locator('.close-btn').first();
            await expect(closeBtn).toBeVisible();

            // Verify a core text element exists and is mathematically bounded inside the phone
            const h2 = templateView.locator('h2, h3, p').first();
            if (await h2.count() > 0) {
                await expect(h2).toBeVisible();
                
                const box = await h2.boundingBox();
                expect(box).not.toBeNull();
                
                // Assert no single row of text bleeds brutally off the viewport constraints
                const viewport = page.viewportSize();
                expect(box.x + box.width).toBeLessThanOrEqual(viewport.width);
                expect(box.x).toBeGreaterThanOrEqual(0);
            }
            
            // Verify bounding overlay doesn't clip horizontally off phones
            const viewbox = await templateView.boundingBox();
            expect(viewbox).not.toBeNull();
            
            const viewport = page.viewportSize();
            expect(viewbox.width).toBeLessThanOrEqual(viewport.width);
        }
    });

    test('Login screen invokes and explicitly bounds text securely', async ({ page, isMobile }) => {
        await page.goto('/');
        await page.waitForLoadState('networkidle');

        if (isMobile) {
            const menuBtn = page.locator('#mobile-menu-btn');
            await menuBtn.click();
            await page.waitForTimeout(350);
            await page.locator('#mobile-nav-auth-btn').click();
        } else {
            await page.locator('#nav-auth-btn').click();
        }

        const templateView = page.locator('.template-view').first();
        await expect(templateView).toBeVisible({ timeout: 10000 });

        const closeBtn = templateView.locator('.close-btn').first();
        await expect(closeBtn).toBeVisible();

        const formNode = templateView.locator('form, h2').first();
        await expect(formNode).toBeVisible();
        
        const box = await formNode.boundingBox();
        expect(box).not.toBeNull();
        
        const viewport = page.viewportSize();
        // Check horizontal bounds specifically to prevent clipping
        expect(box.x + box.width).toBeLessThanOrEqual(viewport.width);
    });

    test('Latitude and Longitude inputs allow negative signs on iOS', async ({ page }) => {
        // Navigate and open the report view
        await page.goto('/');
        await page.waitForLoadState('networkidle');

        // We can just go directly to the hash route for the report form
        await page.goto('/#report?id=GD001-XXXX');
        
        // Wait for the form to appear
        const reportView = page.locator('#view-report');
        await expect(reportView).toBeVisible({ timeout: 10000 });

        const latInput = page.locator('#input-lat');
        const lonInput = page.locator('#input-lon');

        await expect(latInput).toBeVisible();
        await expect(lonInput).toBeVisible();

        const latInputMode = await latInput.getAttribute('inputmode');
        const lonInputMode = await lonInput.getAttribute('inputmode');

        // Evaluate user agent directly inside Playwright to map our JS check
        const ua = await page.evaluate(() => navigator.userAgent);
        const isIOS = /iPad|iPhone|iPod/.test(ua);

        if (isIOS) {
            expect(latInputMode).not.toBe('decimal');
            expect(lonInputMode).not.toBe('decimal');
        } else {
            expect(latInputMode).toBe('decimal');
            expect(lonInputMode).toBe('decimal');
        }
    });

    test('Mobile overlays can be closed by tapping outside', async ({ page, isMobile }) => {
        // This behavior is only active and expected on mobile viewports
        if (!isMobile) {
            test.skip();
            return;
        }

        // --- 1. Test Navigation Drawer Backdrop Tap-Close ---
        await page.goto('/');
        await page.waitForLoadState('networkidle');

        // Confirm mobile navigation drawer is initially closed
        const mobileNavDrawer = page.locator('#mobile-nav-drawer');
        const mobileNavBackdrop = page.locator('#mobile-nav-backdrop');
        await expect(mobileNavDrawer).not.toHaveClass(/open/);
        await expect(mobileNavBackdrop).not.toHaveClass(/open/);

        // Click hamburger menu button
        const menuBtn = page.locator('#mobile-menu-btn');
        await menuBtn.click();
        await page.waitForTimeout(350); // wait for slide-in animation

        // Confirm drawer and backdrop are open
        await expect(mobileNavDrawer).toHaveClass(/open/);
        await expect(mobileNavBackdrop).toHaveClass(/open/);

        // Click outside (on the left portion of the backdrop, not covered by the drawer)
        await mobileNavBackdrop.click({ position: { x: 10, y: 10 }, force: true });
        await page.waitForTimeout(350); // wait for slide-out animation

        // Confirm both closed
        await expect(mobileNavDrawer).not.toHaveClass(/open/);
        await expect(mobileNavBackdrop).not.toHaveClass(/open/);

        // --- 2. Test Template View (Bottom Sheet) Backdrop Tap-Close ---
        // Open a template view (e.g. About page)
        await page.goto('/#about');
        await page.waitForLoadState('networkidle');

        const templateView = page.locator('.template-view').first();
        await expect(templateView).toBeVisible();

        // Verify URL has the #about hash
        expect(page.url()).toContain('#about');

        // Click outside the template view, which on mobile is `#app-content`
        const appContent = page.locator('#app-content');
        await expect(appContent).toHaveClass(/overlay-active/);
        
        // Tap on the top part of #app-content (e.g. at x: 10, y: 10 relative to the element, representing empty space above bottom sheet)
        await appContent.click({ position: { x: 10, y: 10 }, force: true });
        
        // Wait for route reload to settle
        await page.waitForTimeout(350);

        // Confirm the hash changed back to #home or empty
        const currentUrl = page.url();
        expect(currentUrl.endsWith('#home') || currentUrl.endsWith('/')).toBe(true);
        await expect(templateView).not.toBeVisible();
    });

    test('VisibilityManager pauses and resumes geolocation watchPosition stream', async ({ page }) => {
        // Mock geolocation watchPosition and clearWatch to count calls
        await page.addInitScript(() => {
            const mockGeo = {
                watchPosition: (success, _error, _options) => {
                    window.__watchCalls = (window.__watchCalls || 0) + 1;
                    setTimeout(() => {
                        success({ coords: { latitude: 43.0606, longitude: -88.1065, accuracy: 10 } });
                    }, 0);
                    return 12345;
                },
                clearWatch: (watchId) => {
                    if (watchId === 12345) {
                        window.__clearCalls = (window.__clearCalls || 0) + 1;
                    }
                },
                getCurrentPosition: (success, _error, _options) => {
                    success({ coords: { latitude: 43.0606, longitude: -88.1065, accuracy: 10 } });
                }
            };
            Object.defineProperty(navigator, 'geolocation', {
                value: mockGeo,
                configurable: true
            });
        });

        await page.goto('/');
        await page.waitForLoadState('networkidle');

        // Verify watchPosition is initially called once
        await page.waitForFunction(() => window.__watchCalls !== undefined, { timeout: 10000 });
        let watchCalls = await page.evaluate(() => window.__watchCalls);
        expect(watchCalls).toBe(1);

        // Hide page and verify clearWatch is called
        await page.evaluate(() => {
            Object.defineProperty(document, 'visibilityState', {
                value: 'hidden',
                writable: true,
                configurable: true
            });
            document.dispatchEvent(new Event('visibilitychange'));
        });
        await page.waitForFunction(() => window.__clearCalls !== undefined, { timeout: 10000 });
        let clearCalls = await page.evaluate(() => window.__clearCalls);
        expect(clearCalls).toBe(1);

        // Make page visible again and verify watchPosition is restarted
        await page.evaluate(() => {
            Object.defineProperty(document, 'visibilityState', {
                value: 'visible',
                writable: true,
                configurable: true
            });
            document.dispatchEvent(new Event('visibilitychange'));
        });
        await page.waitForFunction(() => window.__watchCalls === 2, { timeout: 10000 });
        watchCalls = await page.evaluate(() => window.__watchCalls);
        expect(watchCalls).toBe(2);
    });

});

