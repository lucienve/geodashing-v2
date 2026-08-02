const { test, expect } = require('@playwright/test');

test.describe('Dashpoint Reroll Feature (#67)', () => {
    test.describe.configure({ mode: 'serial' });
    test.setTimeout(90000);

    let targetDpId = 'GD002-AAAA';

    test.beforeEach(async ({ page }, testInfo) => {
        if (testInfo.project.name === 'iPhone 12') {
            targetDpId = 'GD002-AAAB';
        } else if (testInfo.project.name === 'Pixel 7') {
            targetDpId = 'GD002-AAAC';
        } else {
            targetDpId = 'GD002-AAAA';
        }

        // Hide cookie banner unconditionally to prevent pointer interception in mobile viewports
        await page.goto('/');
        await page.evaluate(() => {
            const style = document.createElement('style');
            style.innerHTML = '#cookie-consent-banner { display: none !important; }';
            document.head.appendChild(style);
        });
    });

    test('Reroll UI hidden on active game dashpoint', async ({ page }) => {

        // Authenticate as TestUser
        await page.goto('/#login');
        await page.fill('#login-username', 'TestUser');
        await page.fill('#login-password', 'testpass');
        await Promise.all([
            page.waitForResponse(resp => resp.url().includes('action=login') && resp.status() === 200),
            page.click('#btn-submit-login')
        ]);
        await page.waitForURL('**/#home');

        // Navigate to active game dashpoint (Game 2)
        await page.goto('/#dashpoint?id=GD001-AAAA');
        await page.waitForSelector('#dp-id-label');

        // Reroll container should be hidden on active games
        const rerollContainer = page.locator('#dp-reroll-container');
        await expect(rerollContainer).toBeHidden();
    });

    test('Reroll UI displayed for qualified player on preview game dashpoint', async ({ page }) => {
        // Authenticate as TestUser (has 1 find)
        await page.goto('/#login');
        await page.fill('#login-username', 'TestUser');
        await page.fill('#login-password', 'testpass');
        await Promise.all([
            page.waitForResponse(resp => resp.url().includes('action=login') && resp.status() === 200),
            page.click('#btn-submit-login')
        ]);
        await page.waitForURL('**/#home');

        // Navigate to preview game dashpoint (Game 3)
        await page.goto(`/#dashpoint?id=${targetDpId}`);
        await page.waitForSelector('#dp-id-label');

        // Reroll container should be visible for qualified user on preview game
        const rerollContainer = page.locator('#dp-reroll-container');
        await expect(rerollContainer).toBeVisible();

        const rerollBtn = page.locator('#btn-reroll-dp');
        await expect(rerollBtn).toBeVisible();

        // The notice stating the dashpoint was rerolled should be hidden
        const rerollNotice = page.locator('#dp-reroll-notice');
        await expect(rerollNotice).toBeHidden();
    });

    test('Reroll UI hidden or restricted for user with 0 finds', async ({ page }) => {
        // Authenticate as NewUser (0 finds)
        await page.goto('/#login');
        await page.fill('#login-username', 'NewUser');
        await page.fill('#login-password', 'testpass');
        await Promise.all([
            page.waitForResponse(resp => resp.url().includes('action=login') && resp.status() === 200),
            page.click('#btn-submit-login')
        ]);
        await page.waitForURL('**/#home');

        // Navigate to preview game dashpoint (Game 3)
        await page.goto(`/#dashpoint?id=${targetDpId}`);
        await page.waitForSelector('#dp-id-label');

        // Click reroll button if visible and verify backend error response
        const rerollBtn = page.locator('#btn-reroll-dp');
        if (await rerollBtn.isVisible()) {
            let alertDialogMsg = '';
            page.on('dialog', async dialog => {
                if (dialog.type() === 'confirm') {
                    await dialog.accept();
                } else if (dialog.type() === 'alert') {
                    alertDialogMsg = dialog.message();
                    await dialog.accept();
                }
            });

            await rerollBtn.click();
            await page.fill('#reroll-reason-input', 'Inaccessible');

            await Promise.all([
                page.waitForResponse(resp => resp.url().includes('api/reroll.php')),
                page.click('#btn-confirm-reroll')
            ]);

            // Give alert dialog time to trigger post-fetch
            await page.waitForTimeout(500);
            expect(alertDialogMsg).toContain('1 verified find');
        }
    });

    test('Reroll button requires non-empty reason and confirm/cancel flow works', async ({ page }) => {
        // Authenticate as TestUser
        await page.goto('/#login');
        await page.fill('#login-username', 'TestUser');
        await page.fill('#login-password', 'testpass');
        await Promise.all([
            page.waitForResponse(resp => resp.url().includes('action=login') && resp.status() === 200),
            page.click('#btn-submit-login')
        ]);
        await page.waitForURL('**/#home');

        // Navigate to preview game dashpoint (Game 3)
        await page.goto(`/#dashpoint?id=${targetDpId}`);
        await page.waitForSelector('#dp-id-label');

        const rerollBtn = page.locator('#btn-reroll-dp');
        const rerollForm = page.locator('#dp-reroll-form');
        const reasonInput = page.locator('#reroll-reason-input');
        const confirmBtn = page.locator('#btn-confirm-reroll');
        const cancelBtn = page.locator('#btn-cancel-reroll');

        // Initial state: Form hidden, button visible
        await expect(rerollBtn).toBeVisible();
        await expect(rerollForm).toBeHidden();

        // 1. Show form
        await rerollBtn.click();
        await expect(rerollBtn).toBeHidden();
        await expect(rerollForm).toBeVisible();
        await expect(reasonInput).toBeFocused();

        // 2. Cancel form
        await cancelBtn.click();
        await expect(rerollBtn).toBeVisible();
        await expect(rerollForm).toBeHidden();

        // 3. Re-open and try empty validation
        await rerollBtn.click();
        let alertDialogMsg = '';
        page.on('dialog', async dialog => {
            if (dialog.type() === 'alert') {
                alertDialogMsg = dialog.message();
                await dialog.accept();
            } else if (dialog.type() === 'confirm') {
                await dialog.accept();
            }
        });

        // Click confirm without typing a reason
        await confirmBtn.click();
        expect(alertDialogMsg).toContain('reason is required');

        // 4. Fill reason and submit successfully
        await reasonInput.fill('Blocked by construction site');
        
        // Confirm should trigger page reload on success
        await Promise.all([
            page.waitForResponse(resp => resp.url().includes('api/reroll.php') && resp.status() === 200),
            confirmBtn.click()
        ]);

        // Expect page reload to hide reroll container (since it's now marked is_rerolled)
        await page.waitForSelector('#dp-reroll-notice');
        const rerollNotice = page.locator('#dp-reroll-notice');
        await expect(rerollNotice).toBeVisible();
        await expect(rerollBtn).toBeHidden();
    });
});



