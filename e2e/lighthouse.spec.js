const { test, chromium } = require('@playwright/test');

// Dynamic import for playwright-lighthouse is recommended to avoid ES module issues in CJS
let playAudit;

test.describe('Lighthouse Audits', () => {
    test.skip(({ browserName }) => browserName !== 'chromium', 'Lighthouse only supports Chromium');
    // Run tests sequentially to avoid port collision
    test.describe.configure({ mode: 'serial' });

    let browser;
    let context;
    let page;
    let PORT;

    test.beforeAll(async ({ _browserName }, testInfo) => {
        PORT = 9222 + testInfo.workerIndex;

        // Load playAudit dynamically
        const lighthouseModule = await import('playwright-lighthouse');
        playAudit = lighthouseModule.playAudit;

        // Launch a standalone Chromium instance for Lighthouse
        browser = await chromium.launch({
            args: [
                `--remote-debugging-port=${PORT}`,
                '--no-sandbox',
                '--disable-gpu'
            ],
            headless: true
        });
        context = await browser.newContext();
        page = await context.newPage();
    });

    test.afterAll(async () => {
        if (browser) {
            await browser.close();
        }
    });

    // Lighthouse audits take significant time
    test.setTimeout(90000);

    const thresholds = {
        seo: 100,
        accessibility: 90,
        'best-practices': 90,
        performance: 50
    };

    test('Home Page meets SEO and Best Practices', async () => {
        await page.goto('http://localhost:8081/#home');
        // Wait for SPA routing and canonical tag generation
        await page.waitForTimeout(1000);
        await page.waitForLoadState('networkidle');

        await playAudit({
            page,
            thresholds,
            port: PORT,
            reports: {
                formats: {
                    html: true
                },
                name: `lighthouse-report-home-${PORT}`,
                directory: 'playwright-report'
            }
        });
    });

    test('Help/About Page meets SEO and Best Practices', async () => {
        await page.goto('http://localhost:8081/#about');
        await page.waitForTimeout(1000);
        await page.waitForLoadState('networkidle');

        await playAudit({
            page,
            thresholds,
            port: PORT,
            reports: {
                formats: { html: true },
                name: `lighthouse-report-about-${PORT}`,
                directory: 'playwright-report'
            }
        });
    });

    test('Dashpoint Page meets SEO and Best Practices', async () => {
        await page.goto('http://localhost:8081/?dashpoint=GD001-001');
        await page.waitForTimeout(1000);
        await page.waitForLoadState('networkidle');

        await playAudit({
            page,
            thresholds,
            port: PORT,
            reports: {
                formats: { html: true },
                name: `lighthouse-report-dashpoint-${PORT}`,
                directory: 'playwright-report'
            }
        });
    });
});
