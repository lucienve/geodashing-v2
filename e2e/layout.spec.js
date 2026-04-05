const { test, expect } = require('@playwright/test');

test.describe('Navigation Layout Constraints', () => {
    
    test.beforeEach(async ({ page }) => {
        // 1. Dismiss Cookie Consent Banner globally if present so it doesn't obscure layout bounds checks
        const cookieBanner = page.locator('.cookie-banner');
        try {
            if (await cookieBanner.isVisible({ timeout: 500 })) {
                const acceptBtn = page.locator('.btn-accept');
                if (await acceptBtn.isVisible({ timeout: 500 })) {
                    await acceptBtn.click();
                    await expect(cookieBanner).not.toBeVisible();
                }
            }
        } catch (e) {
            // gracefully ignore if it's not mounted yet
        }
    });

    test('Ensures the desktop and mobile menus do not exceed screen width', async ({ page, isMobile }) => {
        // Load the local server index
        await page.goto('/');

        // Let the router and dynamically injected JS run
        await page.waitForTimeout(500);

        // Get the accurate viewport size Playwright is emulating
        const viewport = page.viewportSize();
        
        if (isMobile) {
            const menuBtn = page.locator('#mobile-menu-btn');
            
            // Wait for the button to be visibly rendered
            await expect(menuBtn).toBeVisible();
            await menuBtn.click();

            const mobileDrawer = page.locator('#mobile-nav-drawer');
            await expect(mobileDrawer).toBeVisible();
            
            // Wait for the CSS transition (0.3s) to slide the drawer fully into view
            await page.waitForTimeout(350);

            const box = await mobileDrawer.boundingBox();
            expect(box).not.toBeNull();
            
            // Critical Assertion: The drawer must not bleed off the right or left edge of the phone!
            expect(box.x).toBeGreaterThanOrEqual(0);
            expect(box.x + box.width).toBeLessThanOrEqual(viewport.width);
        } else {
            // Desktop checking
            const desktopLinks = page.locator('#desktop-links');
            await expect(desktopLinks).toBeVisible();

            const box = await desktopLinks.boundingBox();
            expect(box).not.toBeNull();
            
            // Ensure the container itself isn't pushed off screen
            expect(box.x).toBeGreaterThanOrEqual(0);
            expect(box.x + box.width).toBeLessThanOrEqual(viewport.width);
        }
    });

    test('Help dropdown constraint check on Desktop', async ({ page, isMobile }) => {
        if (isMobile) {
            // Dropdowns are flattened on mobile in this app architecture, so we skip this test there.
            return;
        }

        await page.goto('/');
        await page.waitForTimeout(500);
        
        const dropdown = page.locator('.dropdown-content');
        const helpLink = page.locator('.dropdown');
        
        // Emulate mouse hover to activate the CSS dropdown
        await helpLink.hover();
        
        // Ensure it became visible
        await expect(dropdown).toBeVisible();

        const box = await dropdown.boundingBox();
        expect(box).not.toBeNull();
        
        const viewport = page.viewportSize();
        // The dropdown content frame must not bleed off the window edge
        expect(box.x + box.width).toBeLessThanOrEqual(viewport.width);
    });
});
