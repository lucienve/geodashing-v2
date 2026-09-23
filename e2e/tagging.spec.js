const { test, expect } = require('@playwright/test');

test.describe('Private Point Tagging Feature', () => {
    test.describe.configure({ mode: 'serial' });
    test.setTimeout(60000);

    let activeDpId = 'GD001-AAAA';
    let previewDpId = 'GD002-AAAA';

    test.beforeEach(async ({ page }, testInfo) => {
        if (testInfo.project.name === 'iPhone 12') {
            activeDpId = 'GD001-AAAB';
            previewDpId = 'GD002-AAAB';
        } else if (testInfo.project.name === 'Pixel 7') {
            activeDpId = 'GD001-AAAC';
            previewDpId = 'GD002-AAAC';
        } else {
            activeDpId = 'GD001-AAAA';
            previewDpId = 'GD002-AAAA';
        }

        // Grant consent and hide banner to prevent intercepting clicks
        await page.goto('/');
        await page.evaluate(() => {
            window.localStorage.setItem('ga_consent', 'granted');
            const style = document.createElement('style');
            style.innerHTML = '#cookie-consent-banner { display: none !important; }';
            document.head.appendChild(style);
        });
    });

    test('Tag UI is hidden for unauthenticated guest users', async ({ page }) => {
        await page.goto(`/#dashpoint?id=${activeDpId}`);
        await page.waitForSelector('#dp-id-label');

        const tagContainer = page.locator('#dp-tag-container');
        await expect(tagContainer).toBeHidden();
    });

    test('Tag UI is hidden for users not in allowlist when TAGS_ENABLED=false', async ({ page }) => {
        // Log in as NewUser (who is not in TAGS_ALLOWLIST)
        await page.goto('/#login');
        await page.fill('#login-username', 'NewUser');
        await page.fill('#login-password', 'testpass');
        await Promise.all([
            page.waitForResponse(resp => resp.url().includes('action=login') && resp.status() === 200),
            page.click('#btn-submit-login')
        ]);
        await page.waitForURL('**/#home');

        await page.goto(`/#dashpoint?id=${activeDpId}`);
        await page.waitForSelector('#dp-id-label');

        const tagContainer = page.locator('#dp-tag-container');
        await expect(tagContainer).toBeHidden();
    });

    test('Allowed user can tag an active game dashpoint and see the marker badge', async ({ page }) => {
        // Log in as TestUser (present in TAGS_ALLOWLIST)
        await page.goto('/#login');
        await page.fill('#login-username', 'TestUser');
        await page.fill('#login-password', 'testpass');
        await Promise.all([
            page.waitForResponse(resp => resp.url().includes('action=login') && resp.status() === 200),
            page.click('#btn-submit-login')
        ]);
        await page.waitForURL('**/#home');

        // Navigate to active game dashpoint
        await page.goto(`/#dashpoint?id=${activeDpId}`);
        await page.waitForSelector('#dp-id-label');

        const tagContainer = page.locator('#dp-tag-container');
        await expect(tagContainer).toBeVisible();

        // Select the Google Blue swatch
        const blueSwatch = tagContainer.locator('.swatch-google-blue');
        await expect(blueSwatch).toBeVisible();
        await blueSwatch.click();

        // Verify swatch is selected and has correct accessibility state
        await expect(blueSwatch).toHaveClass(/selected/);
        await expect(blueSwatch).toHaveAttribute('aria-pressed', 'true');

        const tagToast = page.locator('#dp-tag-toast');
        await expect(tagToast).toHaveText('Saved');

        // Clear the tag
        const clearBtn = page.locator('#btn-clear-tag');
        await clearBtn.click();

        await expect(blueSwatch).not.toHaveClass(/selected/);
        await expect(blueSwatch).toHaveAttribute('aria-pressed', 'false');
        await expect(tagToast).toHaveText('Cleared');
    });

    test('Tag UI is read-only for historical past games', async ({ page }) => {
        // Log in as TestUser
        await page.goto('/#login');
        await page.fill('#login-username', 'TestUser');
        await page.fill('#login-password', 'testpass');
        await Promise.all([
            page.waitForResponse(resp => resp.url().includes('action=login') && resp.status() === 200),
            page.click('#btn-submit-login')
        ]);
        await page.waitForURL('**/#home');

        // Navigate to historical game dashpoint (Game 1)
        await page.goto('/#dashpoint?id=GD000-AAAA');
        await page.waitForSelector('#dp-id-label');

        const tagContainer = page.locator('#dp-tag-container');
        await expect(tagContainer).toBeVisible();

        // Read-only badge must be displayed
        const readonlyBadge = page.locator('#dp-tag-readonly-badge');
        await expect(readonlyBadge).toBeVisible();

        // Swatches and clear button must be disabled
        const swatches = tagContainer.locator('.dash-tag-swatch');
        const count = await swatches.count();
        expect(count).toBe(4);
        for (let i = 0; i < count; i++) {
            await expect(swatches.nth(i)).toBeDisabled();
        }

        const clearBtn = page.locator('#btn-clear-tag');
        await expect(clearBtn).toBeDisabled();
    });

    test('Allowed user can tag preview game dashpoint', async ({ page }) => {
        // Log in as TestUser
        await page.goto('/#login');
        await page.fill('#login-username', 'TestUser');
        await page.fill('#login-password', 'testpass');
        await Promise.all([
            page.waitForResponse(resp => resp.url().includes('action=login') && resp.status() === 200),
            page.click('#btn-submit-login')
        ]);
        await page.waitForURL('**/#home');

        // Navigate to preview game dashpoint (Game 3)
        await page.goto(`/#dashpoint?id=${previewDpId}`);
        await page.waitForSelector('#dp-id-label');

        const tagContainer = page.locator('#dp-tag-container');
        await expect(tagContainer).toBeVisible();

        // Read-only badge should NOT be visible on preview
        const readonlyBadge = page.locator('#dp-tag-readonly-badge');
        await expect(readonlyBadge).toBeHidden();

        // Select the Google Purple swatch
        const purpleSwatch = tagContainer.locator('.swatch-google-purple');
        await purpleSwatch.click();
        await expect(purpleSwatch).toHaveClass(/selected/);
    });

    test('Cross-tab synchronization updates marker badges and swatch selection in real-time', async ({ context, page }) => {
        // Log in as TestUser in page 1
        await page.goto('/#login');
        await page.fill('#login-username', 'TestUser');
        await page.fill('#login-password', 'testpass');
        await Promise.all([
            page.waitForResponse(resp => resp.url().includes('action=login') && resp.status() === 200),
            page.click('#btn-submit-login')
        ]);
        await page.waitForURL('**/#home');

        // Open page 2 in the same browser context (shares cookies / session)
        const page2 = await context.newPage();
        await page2.goto(`/#dashpoint?id=${activeDpId}`);
        await page2.waitForSelector('#dp-id-label');

        const page2TagContainer = page2.locator('#dp-tag-container');
        await expect(page2TagContainer).toBeVisible();
        const page2OrangeSwatch = page2TagContainer.locator('.swatch-google-orange');
        await expect(page2OrangeSwatch).not.toHaveClass(/selected/);

        // In page 1, navigate to the active dashpoint and select Google Deep Orange
        await page.goto(`/#dashpoint?id=${activeDpId}`);
        await page.waitForSelector('#dp-id-label');
        const page1OrangeSwatch = page.locator('#dp-tag-container .swatch-google-orange');
        await page1OrangeSwatch.click();
        await expect(page1OrangeSwatch).toHaveClass(/selected/);

        // Assert that page 2 automatically reflects the selected tag via BroadcastChannel
        await expect(page2OrangeSwatch).toHaveClass(/selected/);

        // In page 2, clear the tag
        const page2ClearBtn = page2.locator('#btn-clear-tag');
        await page2ClearBtn.click();
        await expect(page2OrangeSwatch).not.toHaveClass(/selected/);

        // Assert that page 1 automatically reflects the cleared tag
        await expect(page1OrangeSwatch).not.toHaveClass(/selected/);

        await page2.close();
    });
});
