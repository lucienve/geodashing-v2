/**
 * @fileoverview Multi-Game State and Context Switching E2E Tests.
 */

const { test, expect } = require('@playwright/test');

test.describe('Multi-Game State and Logic', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem('ga_consent', 'granted');
    });
    await page.goto('/');
  });

  test('Game Switcher renders pinned games and defaults to active game', async ({
    page,
  }) => {
    const switcherBtn = page.locator('#game-switcher-btn');
    await expect(switcherBtn).toBeVisible({ timeout: 10000 });
    await expect(switcherBtn).toContainText('Game 2');
    await expect(switcherBtn).toContainText('[ACTIVE]');

    // Open popover
    await switcherBtn.click();
    const popover = page.locator('#game-switcher-popover');
    await expect(popover).toBeVisible();

    const options = popover.locator('.game-switcher-option');
    await expect(options).toHaveCount(3);

    // Verify pinned section has Active (Game 2) and Preview (Game 3)
    const activeCard = popover.locator('.pinned-active');
    await expect(activeCard).toContainText('Game 2');
    await expect(activeCard).toHaveAttribute('aria-selected', 'true');
    await expect(activeCard.locator('.badge-active')).toContainText('[ACTIVE]');

    const previewCard = popover.locator('.pinned-preview');
    await expect(previewCard).toContainText('Game 3');
    await expect(previewCard.locator('.badge-preview')).toContainText(
      '[PREVIEW]',
    );

    // Verify archive section has Historical Game (Game 1)
    const archiveCard = popover.locator('.archive-card');
    await expect(archiveCard).toContainText('Game 1');
    await expect(archiveCard.locator('.badge-completed')).toContainText(
      '[COMPLETED]',
    );
  });

  test('Game Switcher displays compact label on mobile viewport without overflowing', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    const switcherBtn = page.locator('#game-switcher-btn');
    await expect(switcherBtn).toBeVisible({ timeout: 10000 });

    const compactLabel = switcherBtn.locator('.switcher-label-compact');
    await expect(compactLabel).toBeVisible();
    await expect(compactLabel).toContainText('G2 • ACTIVE ▾');

    const fullLabel = switcherBtn.locator('.switcher-label-full');
    await expect(fullLabel).toBeHidden();

    // Verify popover fits within screen width on mobile
    await switcherBtn.click();
    const popover = page.locator('#game-switcher-popover');
    await expect(popover).toBeVisible();
    const popoverBox = await popover.boundingBox();
    expect(popoverBox.x + popoverBox.width).toBeLessThanOrEqual(375);
  });

  test('Map Search updates when switching game context', async ({ page }) => {
    const switcherBtn = page.locator('#game-switcher-btn');
    await expect(switcherBtn).toBeVisible({ timeout: 10000 });

    // Home view map load triggers a search
    await page.goto('/#home');

    // We can intercept the search.php request to verify the game_id parameter
    const searchPromise2 = page.waitForResponse(
      (response) =>
        response.url().includes('api/search.php') &&
        response.url().includes('game_id=1'),
    );

    // Switch to Game 1
    await switcherBtn.click();
    await page.click('#game-switcher-popover [data-game-id="1"]');
    await searchPromise2;
  });

  test('Leaderboard switches context when game selector changes', async ({
    page,
  }) => {
    const switcherBtn = page.locator('#game-switcher-btn');
    await expect(switcherBtn).toBeVisible({ timeout: 10000 });

    // Go to leaderboard
    await page.goto('/#leaderboard');

    // Let's assume there's a row or no data. Game 2 has NO visits for TestUser yet.
    const leaderboardContainer = page.locator('#leaderboard-tbody');
    await expect(leaderboardContainer).not.toContainText('TestUser', {
      timeout: 10000,
    });

    // Switch to Game 1, which HAS a visit for TestUser (score 3)
    await switcherBtn.click();
    await page.click('#game-switcher-popover [data-game-id="1"]');

    // Wait for leaderboard to rerender, it should now contain TestUser
    await expect(leaderboardContainer).toContainText('TestUser', {
      timeout: 10000,
    });
    await expect(leaderboardContainer).toContainText('3', { timeout: 10000 });
  });

  test('Profile displays lifetime score and separates historical games', async ({
    page,
  }) => {
    // Visit TestUser's profile directly via URL hash
    await page.goto('/#profile?username=TestUser');

    const profileContainer = page.locator('#profile-container');

    // It should display lifetime score 3
    await expect(profileContainer).toContainText('3', { timeout: 10000 });

    // It should contain the historical game section
    await expect(profileContainer).toContainText('Historical Game', {
      timeout: 10000,
    });
    await expect(profileContainer).toContainText('GD000-AAAA', {
      timeout: 10000,
    });
  });

  test('Leaderboard loads specific game context when deep-linked', async ({
    page,
  }) => {
    // Go directly to game 1 leaderboard
    await page.goto('/#leaderboard?game=1');

    // Verify the game switcher button is set to Game 1
    const switcherBtn = page.locator('#game-switcher-btn');
    await expect(switcherBtn).toContainText('Game 1', {
      timeout: 10000,
    });

    // Verify leaderboard container contains Game 1 stats (TestUser with score 3)
    const leaderboardContainer = page.locator('#leaderboard-tbody');
    await expect(leaderboardContainer).toContainText('TestUser', {
      timeout: 10000,
    });
    await expect(leaderboardContainer).toContainText('3', { timeout: 10000 });
  });

  test('Leaderboard url updates and shows game ID when navigating to leaderboard menu after selecting completed game', async ({
    page,
  }) => {
    const switcherBtn = page.locator('#game-switcher-btn');
    await expect(switcherBtn).toBeVisible({ timeout: 10000 });

    // Switch to Game 1
    await switcherBtn.click();
    await page.click('#game-switcher-popover [data-game-id="1"]');

    // Go to leaderboard by changing the hash directly (viewport-independent simulation of navigation click)
    await page.evaluate(() => {
      window.location.hash = '#leaderboard';
    });

    // Verify the URL includes the game parameter redirecting correctly
    await expect(page).toHaveURL(/#leaderboard\?game=1/, { timeout: 10000 });

    // Verify leaderboard container contains Game 1 stats (TestUser with score 3)
    const leaderboardContainer = page.locator('#leaderboard-tbody');
    await expect(leaderboardContainer).toContainText('TestUser', {
      timeout: 10000,
    });
    await expect(leaderboardContainer).toContainText('3', { timeout: 10000 });
  });
});
