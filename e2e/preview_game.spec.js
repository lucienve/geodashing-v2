/**
 * @fileoverview Dashpoint Preview Functionality E2E Tests.
 */

const { test, expect } = require('@playwright/test');

test.describe('Dashpoint Preview Functionality', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem('ga_consent', 'granted');
    });
    await page.goto('/');
  });

  test('UI properly labels and enforces read-only states for Preview games', async ({
    page,
  }) => {
    // Wait for switcher button to load and populate from the API
    const switcherBtn = page.locator('#game-switcher-btn');
    await expect(switcherBtn).not.toContainText('[ Loading ... ]', {
      timeout: 10000,
    });

    // Open the switcher popover
    await switcherBtn.click();
    const popover = page.locator('#game-switcher-popover');
    await expect(popover).toBeVisible();

    // Verify the option labels are dynamically tagged based on chronological date checks
    const options = popover.locator('.game-switcher-option');
    const count = await options.count();
    expect(count).toBeGreaterThan(1);

    // Ensure at least one option contains [PREVIEW] and [COMPLETED] tags
    const allText = await popover.textContent();
    expect(allText).toContain('[PREVIEW]');
    expect(allText).toContain('[COMPLETED]');

    // Select the preview game
    // We know Game 3 is the preview game from setup-test-db.sh
    await popover.locator('[data-game-id="3"]').click();

    // Navigate to a specific dashpoint in the preview game
    await page.goto('/#dashpoint?id=GD002-AAAA');

    // Wait for it to load
    await expect(page.locator('#dp-id-label')).toContainText('GD002-AAAA', {
      timeout: 10000,
    });

    // The LOG VISIT button must be hidden or absent for an inactive preview game
    const logBtn = page.locator('#btn-goto-report');
    await expect(logBtn).toBeHidden();
  });

  test('Leaderboard displays preview notice and active game shortcut when viewing preview game', async ({
    page,
  }) => {
    // Navigate directly to preview game leaderboard
    await page.goto('/#leaderboard?game=3');
    await expect(page.locator('#view-leaderboard')).toBeVisible({
      timeout: 10000,
    });

    // Preview notice banner should be displayed
    const previewNotice = page.locator('#leaderboard-preview-notice');
    await expect(previewNotice).toBeVisible({ timeout: 10000 });
    await expect(previewNotice).toContainText('Game Preview Mode');

    // Table body should display preview mode empty state
    const tbody = page.locator('#leaderboard-tbody');
    await expect(tbody).toContainText('GAME IN PREVIEW MODE', {
      timeout: 10000,
    });

    // Active game shortcut should be visible
    const shortcutContainer = page.locator('#leaderboard-active-shortcut');
    await expect(shortcutContainer).toBeVisible();

    const activeBtn = page.locator('#btn-leaderboard-active');
    await expect(activeBtn).toBeVisible();
    await activeBtn.click();

    // Should return to active game leaderboard (#leaderboard)
    await expect(page).toHaveURL(/#leaderboard$/, { timeout: 10000 });
    await expect(previewNotice).toBeHidden();
    await expect(shortcutContainer).toBeHidden();
  });
});
