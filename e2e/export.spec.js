/**
 * @fileoverview Export Functionality E2E Tests.
 */

const { test, expect } = require('@playwright/test');
const fs = require('fs');

test.describe('Export Functionality', () => {
  test.setTimeout(90000);

  test.beforeEach(async ({ page }) => {
    // Authenticate as TestUser to access export endpoint
    await page.goto('/#login');
    await page.fill('#login-username', 'TestUser');
    await page.fill('#login-password', 'testpass');

    // Hide cookie banner unconditionally to prevent interception
    await page.evaluate(() => {
      const style = document.createElement('style');
      style.innerHTML = '#cookie-consent-banner { display: none !important; }';
      document.head.appendChild(style);
    });

    // Trigger login and ensure the API call completes
    await Promise.all([
      page.waitForResponse(
        (resp) => resp.url().includes('action=login') && resp.status() === 200,
      ),
      page.click('#btn-submit-login'),
    ]);

    // Ensure successful login navigates away
    await page.waitForURL('**/#home');

    // Navigate to the scanner/search interface
    await page.goto('/#search');
    await expect(page.locator('#btn-export-gpx')).toBeVisible();
    await expect(page.locator('#export-game-info')).toContainText(
      'Exporting: Game',
      { timeout: 10000 },
    );
  });

  test('Successful GPX Export with Dashpoints', async ({ page }) => {
    // Enter bounds containing NYC mock dashpoint (GD001-AAAA)
    await page.fill('#search-n', '45.0');
    await page.fill('#search-s', '35.0');
    await page.fill('#search-e', '-70.0');
    await page.fill('#search-w', '-80.0');

    // Setup download listener
    const downloadPromise = page.waitForEvent('download');

    // Trigger export
    await page.click('#btn-export-gpx', { force: true });

    // Wait for download to trigger and complete
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe(
      'geodashing_v2_game_2_export.gpx',
    );

    // Read the downloaded file stream in memory
    const path = await download.path();
    const fileContent = fs.readFileSync(path, 'utf8');

    // Assert valid GPX syntax and the presence of the mock point
    expect(fileContent).toContain('<?xml version="1.0" encoding="UTF-8"?>');
    expect(fileContent).toContain('version="1.1"');
    expect(fileContent).toContain('<name>GD001-AAAA</name>');
    expect(fileContent).toContain('</gpx>');
  });

  test('Successful LOC Export with Dashpoints', async ({ page }) => {
    // Enter bounds containing NYC mock dashpoint (GD001-AAAA)
    await page.fill('#search-n', '45.0');
    await page.fill('#search-s', '35.0');
    await page.fill('#search-e', '-70.0');
    await page.fill('#search-w', '-80.0');

    // Setup download listener
    const downloadPromise = page.waitForEvent('download');

    // Trigger export
    await page.click('#btn-export-loc', { force: true });

    // Wait for download to trigger and complete
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe(
      'geodashing_v2_game_2_export.loc',
    );

    // Read the downloaded file stream in memory
    const path = await download.path();
    const fileContent = fs.readFileSync(path, 'utf8');

    // Assert valid LOC syntax and the presence of the mock point
    expect(fileContent).toContain('<?xml version="1.0" encoding="UTF-8"?>');
    expect(fileContent).toContain('<loc version="1.0"');
    expect(fileContent).toContain('<name id="GD001-AAAA">GD001-AAAA</name>');
    expect(fileContent).toContain('</loc>');
  });

  test('Successful KML Export with Dashpoints', async ({ page }) => {
    // Enter bounds containing NYC mock dashpoint (GD001-AAAA)
    await page.fill('#search-n', '45.0');
    await page.fill('#search-s', '35.0');
    await page.fill('#search-e', '-70.0');
    await page.fill('#search-w', '-80.0');

    // Setup download listener
    const downloadPromise = page.waitForEvent('download');

    // Trigger export
    await page.click('#btn-export-kml', { force: true });

    // Wait for download to trigger and complete
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe(
      'geodashing_v2_game_2_export.kml',
    );

    // Read the downloaded file stream in memory
    const path = await download.path();
    const fileContent = fs.readFileSync(path, 'utf8');

    // Assert valid KML syntax and the presence of the mock point
    expect(fileContent).toContain('<?xml version="1.0" encoding="UTF-8"?>');
    expect(fileContent).toContain(
      '<kml xmlns="http://www.opengis.net/kml/2.2">',
    );
    expect(fileContent).toContain('<name>GD001-AAAA</name>');
    expect(fileContent).toContain('<altitudeMode>clampToGround</altitudeMode>');
    expect(fileContent).toContain(
      '<coordinates>-74.006,40.7128,0</coordinates>',
    );
    expect(fileContent).toContain('</kml>');
  });

  test('Empty GPX Export when No Dashpoints in Region', async ({ page }) => {
    // Enter bounds safely far away from NYC (Lat 0-10, Lon 0-10)
    await page.fill('#search-n', '10.0');
    await page.fill('#search-s', '0.0');
    await page.fill('#search-e', '10.0');
    await page.fill('#search-w', '0.0');

    // Setup download listener
    const downloadPromise = page.waitForEvent('download');

    // Trigger export
    await page.click('#btn-export-gpx', { force: true });

    // Wait for download to trigger and complete
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe(
      'geodashing_v2_game_2_export.gpx',
    );

    // Read the downloaded file stream in memory
    const path = await download.path();
    const fileContent = fs.readFileSync(path, 'utf8');

    // Assert valid GPX syntax but explicitly lacking wpt nodes
    expect(fileContent).toContain('<?xml version="1.0" encoding="UTF-8"?>');
    expect(fileContent).toContain('version="1.1"');
    expect(fileContent).not.toContain('<wpt');
  });

  test('Validation Error on Missing Coordinates', async ({ page }) => {
    // Intentionally missing the West coordinate
    await page.fill('#search-n', '45.0');
    await page.fill('#search-s', '35.0');
    await page.fill('#search-e', '-70.0');
    await page.fill('#search-w', '');

    await page.click('#btn-export-gpx', { force: true });

    // Verify the native DOM feedback triggers securely without navigating
    const feedback = page.locator('#search-feedback');
    await expect(feedback).toBeVisible();
    await expect(feedback).toContainText('Error: Missing coordinates.');
  });

  test('Honors Historical Game Selection from Dropdown', async ({ page }) => {
    // Intercept the API request to verify the game_id parameter is present
    const requestPromise = page.waitForRequest(
      (request) =>
        request.url().includes('api/export.php') &&
        request.url().includes('game_id='),
    );

    // Enter valid bounds for London (Game 1 historical dashpoint GD000-AAAA)
    await page.fill('#search-n', '55.0');
    await page.fill('#search-s', '50.0');
    await page.fill('#search-e', '5.0');
    await page.fill('#search-w', '-5.0');

    // Select a different game from the top nav dropdown (assuming game ID 1 exists as historical)
    // Wait for game selector to be visible and have options
    await expect(page.locator('#game-selector')).toBeVisible();

    // Select Game 1 (Historical Game)
    await page.selectOption('#game-selector', '1');

    // Ensure the export overlay reflects the new game
    await expect(page.locator('#export-game-info')).toContainText(
      'Exporting: Game',
    );

    // Trigger export
    const downloadPromise = page.waitForEvent('download');
    await page.click('#btn-export-gpx', { force: true });

    // Assert the request was made with game_id
    const request = await requestPromise;
    expect(request.url()).toContain('game_id=1');

    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe(
      'geodashing_v2_game_1_export.gpx',
    );

    // Read the downloaded file stream in memory
    const path = await download.path();
    const fileContent = fs.readFileSync(path, 'utf8');

    // Assert valid GPX syntax and the presence of the Game 1 historical point
    expect(fileContent).toContain('<?xml version="1.0" encoding="UTF-8"?>');
    expect(fileContent).toContain('version="1.1"');
    expect(fileContent).toContain('<name>GD000-AAAA</name>');
    expect(fileContent).toContain('</gpx>');
  });

  test('Multi-Stop Route Planner UI Visibility and Swatches', async ({
    page,
  }) => {
    const routeBlock = page.locator('#export-route-block');
    await expect(routeBlock).toBeVisible({ timeout: 10000 });

    const markBar = page.locator('#route-mark-bar');
    await expect(markBar).toBeVisible();

    const blueBtn = page.locator('.route-mark-btn.swatch-google-blue');
    const purpleBtn = page.locator('.route-mark-btn.swatch-google-purple');
    const anyBtn = page.locator('.route-mark-any');

    await expect(blueBtn).toHaveAttribute('aria-pressed', 'true');
    await expect(blueBtn).toHaveClass(/active/);
    await expect(purpleBtn).toHaveAttribute('aria-pressed', 'false');
    await expect(anyBtn).toHaveAttribute('aria-pressed', 'false');

    await expect(page.locator('#btn-route-scope-game')).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await expect(page.locator('#route-origin-select')).toBeVisible();
    await expect(page.locator('#btn-open-gmaps-route')).toBeVisible();
  });

  test('Generates Multi-Stop Route with Nearest-Neighbor Stops and Google Maps URL', async ({
    page,
  }) => {
    // Inject mock user tags with spatial coordinates
    await page.evaluate(() => {
      window.currentUserPosition = { lat: 40.7128, lng: -74.006 };
      window.currentUserTags = {
        'GD001-AAAA': {
          color: '#1a73e8',
          shape: 'star',
          name: 'Blue Star',
          lat: 40.7128,
          lon: -74.006,
        },
        'GD001-AAAB': {
          color: '#1a73e8',
          shape: 'star',
          name: 'Blue Star',
          lat: 40.6782,
          lon: -73.9442,
        },
        'GD001-AAAC': {
          color: '#1a73e8',
          shape: 'star',
          name: 'Blue Star',
          lat: 40.7282,
          lon: -73.7949,
        },
      };
      document.dispatchEvent(
        new CustomEvent('userTagsChanged', {
          detail: { action: 'SET_TAG' },
        }),
      );
    });

    await expect(page.locator('#route-mark-count-label')).toHaveText(
      'Blue Star (3)',
    );
    await expect(page.locator('#route-stops-summary')).toContainText('3 Stops');

    const stopItems = page.locator('#route-stops-list .route-stop-item');
    await expect(stopItems).toHaveCount(3);
    await expect(stopItems.nth(0)).toContainText('1 (A).');
    await expect(stopItems.nth(1)).toContainText('2 (B).');
    await expect(stopItems.nth(2)).toContainText('3 (C).');

    const gmapsBtn = page.locator('#btn-open-gmaps-route');
    await expect(gmapsBtn).not.toHaveClass(/disabled/);
    const href = await gmapsBtn.getAttribute('href');
    expect(href).toContain('https://www.google.com/maps/dir/?api=1');
    expect(href).toContain('destination=');
    expect(href).toContain('travelmode=driving');
  });

  test('Enforces 10-Stop Cap and Displays Warning Banner', async ({ page }) => {
    // Inject 13 mock points for Purple Diamond
    await page.evaluate(() => {
      window.currentUserPosition = { lat: 40.7128, lng: -74.006 };
      const tags = {};
      for (let i = 1; i <= 13; i++) {
        const id = `GD001-PR${String(i).padStart(2, '0')}`;
        tags[id] = {
          color: '#8e24aa',
          shape: 'diamond',
          name: 'Purple Diamond',
          lat: 40.7128 + i * 0.01,
          lon: -74.006 - i * 0.01,
        };
      }
      window.currentUserTags = tags;
      document.dispatchEvent(
        new CustomEvent('userTagsChanged', {
          detail: { action: 'SET_TAG' },
        }),
      );
    });

    // Select Purple Diamond swatch
    await page.click('.route-mark-btn.swatch-google-purple');

    await expect(page.locator('#route-mark-count-label')).toHaveText(
      'Purple Diamond (13)',
    );
    const capWarning = page.locator('#route-cap-warning');
    await expect(capWarning).toBeVisible();
    await expect(capWarning).toContainText('Capped at 10 nearest stops');
    await expect(capWarning).toContainText('3 additional omitted');

    const stopItems = page.locator('#route-stops-list .route-stop-item');
    await expect(stopItems).toHaveCount(10);
    await expect(stopItems.nth(9)).toContainText('10 (J).');

    const gmapsBtn = page.locator('#btn-open-gmaps-route');
    const href = await gmapsBtn.getAttribute('href');
    expect(href).toContain('waypoints=');
  });

  test('Filters Stops by Visible Bounds Scope and Toggles Origin Mode', async ({
    page,
  }) => {
    await page.evaluate(() => {
      window.currentUserPosition = { lat: 40.7128, lng: -74.006 };
      window.currentUserTags = {
        'GD001-AAAA': {
          color: '#1a73e8',
          shape: 'star',
          name: 'Blue Star',
          lat: 40.7128,
          lon: -74.006,
        },
        'GD001-AAAB': {
          color: '#1a73e8',
          shape: 'star',
          name: 'Blue Star',
          lat: 40.6782,
          lon: -73.9442,
        },
      };
      document.dispatchEvent(
        new CustomEvent('userTagsChanged', {
          detail: { action: 'SET_TAG' },
        }),
      );
    });

    // Constrain bounding box inputs to only enclose GD001-AAAA
    await page.fill('#search-n', '40.72');
    await page.fill('#search-s', '40.70');
    await page.fill('#search-e', '-74.00');
    await page.fill('#search-w', '-74.02');

    // Switch to Visible Bounds
    await page.click('#btn-route-scope-bounds');
    await expect(page.locator('#btn-route-scope-bounds')).toHaveClass(/active/);

    const stopItems = page.locator('#route-stops-list .route-stop-item');
    await expect(stopItems).toHaveCount(1);
    await expect(stopItems.nth(0)).toContainText('GD001-AAAA');

    // Switch Origin to 1st Marked Point
    await page.selectOption('#route-origin-select', 'first');
    await expect(stopItems.nth(0)).toContainText('Origin');

    // Single point in first mode produces direct destination URL without origin
    const gmapsBtn = page.locator('#btn-open-gmaps-route');
    const href = await gmapsBtn.getAttribute('href');
    expect(href).toContain('destination=40.71280,-74.00600');
    expect(href).not.toContain('origin=');

    // Switch back to Entire Game scope
    await page.click('#btn-route-scope-game');
    await expect(
      page.locator('#route-stops-list .route-stop-item'),
    ).toHaveCount(2);
  });
});
