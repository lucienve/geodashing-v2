const { test, expect } = require('@playwright/test');

test.describe('Multi-Game State and Logic', () => {
    test.beforeEach(async ({ page }) => {
        await page.addInitScript(() => {
            window.localStorage.setItem('ga_consent', 'granted');
        });
        await page.goto('/');
    });

    test('Game Selector renders both games and defaults to active game', async ({ page }) => {
        const options = page.locator('#game-selector option');
        await expect(options).toHaveCount(3, { timeout: 10000 });

        // Check text content - options should be ordered correctly
        const optionText1 = await options.nth(0).innerText();
        const optionText2 = await options.nth(1).innerText();
        const optionText3 = await options.nth(2).innerText();
        
        // The API sorts descending, so Game 3 is first, Game 2 is second, and Game 1 is third.
        expect(optionText1).toContain('Game 3');
        expect(optionText2).toContain('Game 2');
        expect(optionText3).toContain('Game 1');

        // Verify active game (id 2) is selected by default
        const selectedValue = await page.$eval('#game-selector', el => el.value);
        expect(selectedValue).toBe('2');
    });

    test('Map Search updates when switching game context', async ({ page }) => {
        await expect(page.locator('#game-selector option')).toHaveCount(3, { timeout: 10000 });

        // Home view map load triggers a search
        await page.goto('/#home');
        
        // We can intercept the search.php request to verify the game_id parameter
        const searchPromise2 = page.waitForResponse(response => 
            response.url().includes('api/search.php') && response.url().includes('game_id=1')
        );

        // Switch to Game 1
        await page.selectOption('#game-selector', '1');
        await searchPromise2;
    });

    test('Leaderboard switches context when game selector changes', async ({ page }) => {
        await expect(page.locator('#game-selector option')).toHaveCount(3, { timeout: 10000 });
        
        // Go to leaderboard
        await page.goto('/#leaderboard');
        
        // Let's assume there's a row or no data. Game 2 has NO visits for TestUser yet.
        const leaderboardContainer = page.locator('#leaderboard-tbody');
        await expect(leaderboardContainer).not.toContainText('TestUser', { timeout: 10000 });

        // Switch to Game 1, which HAS a visit for TestUser (score 3)
        await page.selectOption('#game-selector', '1');

        // Wait for leaderboard to rerender, it should now contain TestUser
        await expect(leaderboardContainer).toContainText('TestUser', { timeout: 10000 });
        await expect(leaderboardContainer).toContainText('3', { timeout: 10000 });
    });

    test('Profile displays lifetime score and separates historical games', async ({ page }) => {
        // Visit TestUser's profile directly via URL hash
        await page.goto('/#profile?username=TestUser');

        const profileContainer = page.locator('#profile-container');
        
        // It should display lifetime score 3
        await expect(profileContainer).toContainText('3', { timeout: 10000 });

        // It should contain the historical game section
        await expect(profileContainer).toContainText('Historical Game', { timeout: 10000 });
        await expect(profileContainer).toContainText('GD000-AAAA', { timeout: 10000 });
    });

    test('Leaderboard loads specific game context when deep-linked', async ({ page }) => {
        // Go directly to game 1 leaderboard
        await page.goto('/#leaderboard?game=1');

        // Verify the game selector is set to Game 1
        await expect(page.locator('#game-selector')).toHaveValue('1', { timeout: 10000 });

        // Verify leaderboard container contains Game 1 stats (TestUser with score 3)
        const leaderboardContainer = page.locator('#leaderboard-tbody');
        await expect(leaderboardContainer).toContainText('TestUser', { timeout: 10000 });
        await expect(leaderboardContainer).toContainText('3', { timeout: 10000 });
    });
});
