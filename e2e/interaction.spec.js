const { test, expect } = require('@playwright/test');

test.describe('Component & Interactive Layout Constraints', () => {
    // These tests do a lot of physical page routing across devices and need time to breathe over the PHP stack
    test.setTimeout(90000);

    test.beforeEach(async ({ page }) => {
        await page.goto('/');

        // Let the SPA router and dynamic Map layer settle
        await page.waitForTimeout(800);

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
        
        // Wait for google maps to natively inject the UI overlays
        await expect(recenterBtn).toBeVisible({ timeout: 10000 });
        
        // Validate clickability directly (Playwright throws if covered/hidden natively)
        // Ensure to pass true to trial so it just verifes clickability without actually triggering geolocation API
        await recenterBtn.click({ trial: true });

        // The native Google Map Type Toggle (Satellite vs Terrain toggle)
        const mapTypeToggle = page.locator('button[title="Show street map"], button[title="Show satellite imagery"]').first();
        if (await mapTypeToggle.isVisible()) {
             // Perform a physical click to pop open the secondary overlay context
             await mapTypeToggle.click({ force: true }); // Google Maps layers can be tricky, force the dispatch
             
             // Wait for the native Google Maps submenu to render 'Terrain' or 'Labels'
             const subMenuText = page.locator('text=/Terrain|Labels/i').first();
             // Verify the sub-checkboxes pop out without getting blocked.
             await expect(subMenuText).toBeVisible({ timeout: 15000 });
        }
    });

    test('Menu template overlays invoke successfully and confine natively without clipping', async ({ page, isMobile }) => {
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
            await page.waitForTimeout(500); // Allow DOM reset

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
            await page.waitForTimeout(500); 

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
        await page.waitForTimeout(500);

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
        await page.waitForTimeout(500);

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

});
