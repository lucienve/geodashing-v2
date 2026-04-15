const { defineConfig, devices } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  retries: 2,
  workers: 2,
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
    command: 'APP_ENV=testing php -S localhost:8081',
    url: 'http://localhost:8081',
    reuseExistingServer: !process.env.CI,
  },
});
