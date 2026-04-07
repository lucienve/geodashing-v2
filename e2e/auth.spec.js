const { test, expect } = require('@playwright/test');

test.describe('Authentication Flow & Session Integrity', () => {
    test('Handles session integrity check failure (catch block execution)', async ({ page }) => {
        // Intercept the checkSession POST request and make it return 'null'
        // This will cause `res.status` in updateAuthState to throw a TypeError,
        // which simulates a malformed/invalid response hitting the catch block.
        await page.route('**/backend/api/auth.php?action=session', async route => {
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: 'null'
            });
        });

        const consoleMessages = [];
        page.on('console', msg => {
            if (msg.type() === 'error') {
                consoleMessages.push(msg.text());
            }
        });

        await page.goto('/');

        // Wait for the app to initialize and run updateAuthState
        // We can wait for the session integrity check failure message in the console
        await expect.poll(() => consoleMessages).toContain('Session integrity check failed.');
    });
});
