const { test, expect } = require('@playwright/test');

test.describe('Dashpoint Preview Functionality', () => {
    test.beforeEach(async ({ page }) => {
        await page.addInitScript(() => {
            window.localStorage.setItem('ga_consent', 'granted');
        });
        await page.goto('/');
    });

    test('UI properly labels and enforces read-only states for Preview games', async ({ page }) => {
        // Wait for the dropdown to load and populate from the API
        const gameSelector = page.locator('#game-selector');
        await expect(gameSelector).not.toContainText('[ Loading ... ]', { timeout: 10000 });

        // Verify the option labels are dynamically tagged based on chronological date checks
        const options = gameSelector.locator('option');
        const count = await options.count();
        expect(count).toBeGreaterThan(1);
        
        // Ensure at least one option contains [PREVIEW] and [COMPLETED] tags
        const allText = await gameSelector.textContent();
        expect(allText).toContain('[PREVIEW]');
        expect(allText).toContain('[COMPLETED]');
        
        // Select the preview game
        // We know Game 3 is the preview game from setup-test-db.sh
        // Use evaluate to force change value if hidden on mobile
        await gameSelector.selectOption({ value: '3' }, { force: true });

        // Navigate to a specific dashpoint in the preview game
        await page.goto('/#dashpoint?id=GD002-AAAA');
        
        // Wait for it to load
        await expect(page.locator('#dp-id-label')).toContainText('GD002-AAAA', { timeout: 10000 });
        
        // The LOG VISIT button must be hidden or absent for an inactive preview game
        const logBtn = page.locator('#btn-goto-report');
        await expect(logBtn).toBeHidden();
    });
});
