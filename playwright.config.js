const { defineConfig, devices } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  retries: 2,
  workers: process.env.CI ? 2 : undefined,
  reporter: [['html', { open: 'never' }]],
  use: {
    baseURL: 'http://localhost:8081',
    trace: 'on-first-retry',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'iPhone 12',
      use: { ...devices['iPhone 12'] },
    },
    {
      name: 'Pixel 7',
      use: { ...devices['Pixel 7'] },
    },
  ],

  globalSetup: require.resolve('./e2e/global-setup.js'),

  webServer: {
    command: 'APP_ENV=testing GCS_EMULATOR_HOST=http://127.0.0.1:4443 php -S localhost:8081',
    url: 'http://localhost:8081',
    reuseExistingServer: !process.env.CI,
  },
});
