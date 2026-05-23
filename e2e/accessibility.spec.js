const { test, expect } = require('@playwright/test');

test.describe('E2E Accessibility & Visual Contrast Suite', () => {
    test.setTimeout(120000); // 2 minutes to allow thorough testing of all 9 routes/states

    test.beforeEach(async ({ page }) => {
        // Dismiss Cookie Consent globally by injecting styles or clicking
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
        } catch (_e) {
            // Ignore if already dismissed or not present
        }
    });

    // Helper: Verify standard accessibility rules of the currently active view
    async function verifyBaseAccessibility(page, viewName) {
        console.log(`Verifying base accessibility constraints for: ${viewName}`);

        // 1. Heading structure check (semantic view headers)
        const headingsCount = await page.locator('h1.logo, #app-content h2, #app-content h3, #app-content h4, .modal-content h2, .modal-content h3, .modal-content h4').count();
        expect(headingsCount).toBeGreaterThan(0);

        // 2. Buttons must have descriptive content or aria-label
        const buttons = page.locator('#top-nav button, #mobile-nav-drawer button, #app-content button, .modal-content button');
        const btnCount = await buttons.count();
        for (let i = 0; i < btnCount; i++) {
            const btn = buttons.nth(i);
            if (await btn.isVisible()) {
                const text = (await btn.innerText()).trim();
                const ariaLabel = await btn.getAttribute('aria-label');
                const ariaLabelledBy = await btn.getAttribute('aria-labelledby');
                
                // Ensure at least one of these is non-empty
                expect(text || ariaLabel || ariaLabelledBy).toBeTruthy();
            }
        }

        // 3. Images must have alternative text
        const images = page.locator('#top-nav img, #mobile-nav-drawer img, #app-content img, .modal-content img');
        const imgCount = await images.count();
        for (let i = 0; i < imgCount; i++) {
            const img = images.nth(i);
            if (await img.isVisible()) {
                const alt = await img.getAttribute('alt');
                expect(alt).not.toBeNull();
            }
        }

        // 4. Input elements must have associated accessible names/labels
        const inputs = page.locator('#top-nav input, #top-nav textarea, #top-nav select, #mobile-nav-drawer input, #mobile-nav-drawer textarea, #mobile-nav-drawer select, #app-content input, #app-content textarea, #app-content select, .modal-content input, .modal-content textarea, .modal-content select');
        const inputCount = await inputs.count();
        for (let i = 0; i < inputCount; i++) {
            const input = inputs.nth(i);
            if (await input.isVisible() && (await input.getAttribute('type')) !== 'hidden') {
                const isLabeled = await input.evaluate((el) => {
                    // 1. Direct descriptive attributes
                    if (el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') || el.getAttribute('placeholder') || el.getAttribute('title')) {
                        return true;
                    }
                    // 2. Ancestor/Parent wrapped association
                    if (el.closest('label')) {
                        return true;
                    }
                    // 3. Explicit for-id relationship
                    if (el.id) {
                        const label = document.querySelector(`label[for="${el.id}"]`);
                        if (label) return true;
                    }
                    // 4. Sibling labeling context in form controls
                    const container = el.closest('.form-group, .dash-block, td, tr, div');
                    if (container) {
                        const label = container.querySelector('label');
                        if (label) return true;
                    }
                    return false;
                });
                expect(isLabeled).toBe(true);
            }
        }
    }

    // Helper: Authenticate TestUser
    async function loginAsTestUser(page) {
        await page.goto('/#login');
        await expect(page.locator('#view-login')).toBeVisible();

        await page.fill('#login-username', 'TestUser');
        await page.fill('#login-password', 'testpass');
        
        await Promise.all([
            page.waitForResponse(resp => resp.url().includes('action=login') && resp.status() === 200),
            page.click('#btn-submit-login')
        ]);
        await page.waitForURL('**/#home');
    }

    test('Stylesheets contain high-contrast visited anchor rules', async ({ page }) => {
        await page.goto('/');
        await page.waitForLoadState('networkidle');

        const stylesChecked = await page.evaluate(() => {
            let visitedStyled = false;
            let globalVisitedStyled = false;
            for (const sheet of document.styleSheets) {
                try {
                    for (const rule of sheet.cssRules) {
                        if (rule.selectorText) {
                            const sel = rule.selectorText.toLowerCase();
                            if (sel.includes('.summary-rich-content a:visited') && rule.style.color) {
                                visitedStyled = true;
                            }
                            if (sel === 'a:visited' && rule.style.color) {
                                globalVisitedStyled = true;
                            }
                        }
                    }
                } catch (_e) {
                    // Ignore cross-origin stylesheet access errors
                }
            }
            return { visitedStyled, globalVisitedStyled };
        });

        expect(stylesChecked.visitedStyled).toBe(true);
        expect(stylesChecked.globalVisitedStyled).toBe(true);
    });

    test('Home Page (Map Context) Accessibility & Text Colors', async ({ page }) => {
        await page.goto('/');
        await page.waitForLoadState('networkidle');

        // Check header links and text
        const logo = page.locator('.logo');
        await expect(logo).toBeVisible();
        const logoColor = await logo.evaluate(el => window.getComputedStyle(el).color);
        expect(logoColor).toBe('rgb(248, 250, 252)'); // var(--text-main) #f8fafc

        await verifyBaseAccessibility(page, 'Home');
    });

    test('Static Help Pages (#about, #how-to, #contact) Accessibility & Link Contrast', async ({ page }) => {
        const routes = ['#about', '#how-to', '#contact'];

        for (const route of routes) {
            await page.goto('/' + route);
            await page.waitForLoadState('networkidle');
            
            const viewSelector = `#view-${route.substring(1)}`;
            const view = page.locator(viewSelector);
            await expect(view).toBeVisible();

            await verifyBaseAccessibility(page, route);

            // Assert anchor elements in these help pages use high-contrast theme accents (amber or green)
            const links = view.locator('a:not(.close-btn)');
            const linkCount = await links.count();
            for (let i = 0; i < linkCount; i++) {
                const link = links.nth(i);
                if (await link.isVisible()) {
                    const color = await link.evaluate(el => window.getComputedStyle(el).color);
                    expect(['rgb(245, 158, 11)', 'rgb(16, 185, 129)']).toContain(color);
                }
            }
        }
    });

    test('Login Screen (#login) Input Fields & Interactive Tabs Accessibility', async ({ page }) => {
        await page.goto('/#login');
        await page.waitForLoadState('networkidle');

        const loginView = page.locator('#view-login');
        await expect(loginView).toBeVisible();

        // 1. Accessibility Checks
        await verifyBaseAccessibility(page, 'Login');

        // 2. Interactive tab toggle to Signup
        const toggleSignup = page.locator('#toggle-signup');
        await toggleSignup.scrollIntoViewIfNeeded();
        await expect(toggleSignup).toBeVisible();
        await toggleSignup.click();
        
        const signupPane = page.locator('#signup-pane');
        await expect(signupPane).toBeVisible();
        await verifyBaseAccessibility(page, 'Signup Pane');

        // Go back to login pane first to reveal Forgot toggle
        const toggleLogin = page.locator('#toggle-login');
        await toggleLogin.scrollIntoViewIfNeeded();
        await toggleLogin.click();

        // 3. Interactive tab toggle to Recovery/Forgot
        const toggleForgot = page.locator('#toggle-forgot');
        await toggleForgot.scrollIntoViewIfNeeded();
        await expect(toggleForgot).toBeVisible();
        await toggleForgot.click();

        const forgotPane = page.locator('#forgot-pane');
        await expect(forgotPane).toBeVisible();
        await verifyBaseAccessibility(page, 'Forgot Pane');
    });

    test('Global Leaderboard (#leaderboard) & Game Summary Modal Accessibility & Link Contrast', async ({ page }) => {
        await page.goto('/#leaderboard');
        await page.waitForLoadState('networkidle');

        const leaderboardView = page.locator('#view-leaderboard');
        await expect(leaderboardView).toBeVisible();

        // 1. Choose Completed Game 1 from Selector to show summary trigger
        await expect(page.locator('#game-selector')).toBeVisible();
        await page.selectOption('#game-selector', '1');
        
        // 2. Read Game Summary trigger visibility
        const summaryContainer = page.locator('#leaderboard-summary-container');
        await expect(summaryContainer).toBeVisible();

        const btnSummary = page.locator('#btn-view-summary');
        await expect(btnSummary).toBeVisible();
        
        // Click the trigger to mount and open the Glassmorphic Modal overlay
        await btnSummary.click();

        const modalOverlay = page.locator('#summary-modal-overlay');
        await expect(modalOverlay).toBeVisible();

        const modalContent = modalOverlay.locator('.modal-content');
        await expect(modalContent).toBeVisible();

        // 3. Base modal accessibility check
        const modalClose = modalContent.locator('.modal-close');
        await expect(modalClose).toBeVisible();
        
        const heading = modalContent.locator('h2');
        await expect(heading).toBeVisible();

        // 4. Verify rich text links inside modal content are high-contrast amber
        const summaryRichContent = modalContent.locator('.summary-rich-content');
        await expect(summaryRichContent).toBeVisible();

        const links = summaryRichContent.locator('a');
        const linkCount = await links.count();
        expect(linkCount).toBeGreaterThan(0);

        for (let i = 0; i < linkCount; i++) {
            const link = links.nth(i);
            const color = await link.evaluate(el => window.getComputedStyle(el).color);
            expect(color).toBe('rgb(245, 158, 11)'); // Must match HSL high-contrast amber accent
        }

        // Close modal
        await modalClose.click();
        await expect(modalOverlay).not.toBeVisible();
    });

    test('User Profile (#profile?username=TestUser) Accessibility', async ({ page }) => {
        await page.goto('/#profile?username=TestUser');
        await page.waitForLoadState('networkidle');

        const profileContainer = page.locator('#profile-container');
        await expect(profileContainer).toBeVisible();

        // Wait for profile service data to render
        const usernameHeader = profileContainer.locator('h3');
        await expect(usernameHeader).toBeVisible({ timeout: 5000 });

        await verifyBaseAccessibility(page, 'User Profile');
    });

    test('Export Coordinator overlay (#search) (Authenticated) Accessibility', async ({ page }) => {
        // Authenticate first
        await loginAsTestUser(page);

        // Navigate to search
        await page.goto('/#search');
        await page.waitForLoadState('networkidle');

        const searchView = page.locator('#view-search');
        await expect(searchView).toBeVisible();

        await verifyBaseAccessibility(page, 'Export Coordinates overlay');
    });

    test('Log Visit Overlay (#report?id=GD001-AAAA) (Authenticated) Accessibility', async ({ page }) => {
        // Authenticate first
        await loginAsTestUser(page);

        // Navigate to log visit report
        await page.goto('/#report?id=GD001-AAAA');
        await page.waitForLoadState('networkidle');

        const reportView = page.locator('#view-report');
        await expect(reportView).toBeVisible();

        await verifyBaseAccessibility(page, 'Log Visit Overlay');
    });

    test('Edit Visit Overlay (#edit?id=GD000-AAAA) (Authenticated) Accessibility', async ({ page }) => {
        // Authenticate first
        await loginAsTestUser(page);

        // Navigate to edit visit
        await page.goto('/#edit?id=GD000-AAAA');
        await page.waitForLoadState('networkidle');

        const editView = page.locator('#view-edit');
        await expect(editView).toBeVisible();

        await verifyBaseAccessibility(page, 'Edit Visit Overlay');
    });
});
