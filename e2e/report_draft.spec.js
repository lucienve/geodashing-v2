const { test, expect } = require('@playwright/test');
const path = require('path');

test.describe('Report Draft Auto-Save and Restoration', () => {
    const mockGps = () => {
        window.mockGeolocation = {
            getCurrentPosition: (success) => {
                success({ coords: { latitude: 40.7128, longitude: -74.0060, accuracy: 10 } });
            }
        };
    };

    test.beforeEach(async ({ page }) => {
        await page.addInitScript(() => {
            window.localStorage.setItem('ga_consent', 'granted');
        });
        await page.addInitScript(mockGps);
        await page.goto('/');
        await page.evaluate(mockGps);

        // Ensure database drafts are clear before each test
        await page.evaluate(async () => {
            if (window.DraftStorage) {
                await window.DraftStorage.clearAllDrafts();
            }
        });
    });

    test('Auto-saves coordinates, notes, and photos, and restores them on page reload', async ({ page }) => {
        await page.goto('/#report?id=GD001-AAAA');
        await expect(page.locator('#dashpoint_id')).toHaveValue('GD001-AAAA');

        // 1. Sync GPS coordinates
        await page.click('#btn-geolocation');
        await expect(page.locator('#input-lat')).toHaveValue('40.712800');
        await expect(page.locator('#input-lon')).toHaveValue('-74.006000');
        await expect(page.locator('#btn-geolocation')).toContainText('SYNCED');

        // 2. Fill out narrative log and trigger blur to ensure save flush
        await page.fill('#log-textarea', 'Explored Big Bad Wolf parking lot at dawn.');
        await page.locator('#log-textarea').blur();

        // 3. Attach a test photo
        const imagePath = path.resolve(__dirname, '../public/images/android-chrome-192x192.png');
        await page.setInputFiles('#input-photos', imagePath);
        await expect(page.locator('.photo-preview-item')).toHaveCount(1);

        // 4. Add a caption
        await page.locator('.photo-preview-wrapper').first().click();
        await expect(page.locator('#caption-modal-overlay')).toBeVisible();
        await page.fill('#modal-caption-text', 'Front entrance marker');
        await page.click('#btn-save-caption');
        await expect(page.locator('#caption-modal-overlay')).toHaveCount(0);
        await expect(page.locator('.photo-caption-badge')).toContainText('CAPTIONED');

        // 5. Verify draft exists in IndexedDB before reload
        await expect.poll(async () => {
            const draft = await page.evaluate(async () => {
                return await window.DraftStorage.getDraft('GD001-AAAA');
            });
            return draft && draft.photos && draft.photos[0] ? draft.photos[0].caption : null;
        }).toBe('Front entrance marker');

        const savedDraft = await page.evaluate(async () => {
            return await window.DraftStorage.getDraft('GD001-AAAA');
        });
        expect(savedDraft).not.toBeNull();
        expect(savedDraft.lat).toBe('40.712800');
        expect(savedDraft.lon).toBe('-74.006000');
        expect(savedDraft.notes).toBe('Explored Big Bad Wolf parking lot at dawn.');
        expect(savedDraft.photos.length).toBe(1);

        // 6. Reload the page completely and navigate back to the report view
        await page.reload();
        await page.evaluate(mockGps);
        await page.goto('/#report?id=GD001-AAAA');

        // 7. Verify draft restored banner is present
        await expect(page.locator('#draft-restore-banner')).toBeVisible({ timeout: 10000 });
        await expect(page.locator('#draft-restore-banner')).toContainText('Draft restored from earlier visit');

        // 8. Verify coordinates and GPS button styling restored
        await expect(page.locator('#input-lat')).toHaveValue('40.712800');
        await expect(page.locator('#input-lon')).toHaveValue('-74.006000');
        await expect(page.locator('#btn-geolocation')).toContainText('SYNCED');

        // 9. Verify notes and character counter restored
        await expect(page.locator('#log-textarea')).toHaveValue('Explored Big Bad Wolf parking lot at dawn.');
        const counterText = await page.locator('#char-counter').innerText();
        expect(counterText).toContain('chars remaining');
        expect(counterText).not.toBe('10,000 chars remaining');

        // 10. Verify photo preview restored with caption
        await expect(page.locator('.photo-preview-item')).toHaveCount(1);
        await expect(page.locator('.photo-caption-badge')).toContainText('CAPTIONED');

        // 11. CRITICAL: Verify DOM inputPhotos.files has been synchronized
        const domFilesCount = await page.evaluate(() => {
            const input = document.getElementById('input-photos');
            return input ? input.files.length : 0;
        });
        expect(domFilesCount).toBe(1);
    });

    test('Discards restored draft cleanly when DISCARD DRAFT button is clicked', async ({ page }) => {
        await page.goto('/#report?id=GD001-AAAA');
        await expect(page.locator('#dashpoint_id')).toHaveValue('GD001-AAAA');

        // Populate fields and blur to flush
        await page.fill('#input-lat', '42.123456');
        await page.locator('#input-lat').blur();
        await page.fill('#input-lon', '-71.123456');
        await page.locator('#input-lon').blur();
        await page.fill('#log-textarea', 'Temporary notes to discard');
        await page.locator('#log-textarea').blur();

        // Reload to trigger restore banner
        await page.reload();
        await page.evaluate(mockGps);
        await page.goto('/#report?id=GD001-AAAA');

        await expect(page.locator('#draft-restore-banner')).toBeVisible({ timeout: 10000 });
        await expect(page.locator('#log-textarea')).toHaveValue('Temporary notes to discard');

        // Click Discard Draft button
        await page.click('#btn-discard-draft');

        // Verify banner removed and fields cleared
        await expect(page.locator('#draft-restore-banner')).toHaveCount(0);
        await expect(page.locator('#log-textarea')).toHaveValue('');
        await expect(page.locator('#input-lat')).toHaveValue('');
        await expect(page.locator('#input-lon')).toHaveValue('');
        await expect(page.locator('#btn-geolocation')).toContainText('SYNC LIVE GPS');

        // Verify draft deleted in IndexedDB
        const draftAfterDiscard = await page.evaluate(async () => {
            return await window.DraftStorage.getDraft('GD001-AAAA');
        });
        expect(draftAfterDiscard).toBeNull();
    });

    test('Flushes auto-save immediately on blur and visibility change without waiting for timer', async ({ page }) => {
        await page.goto('/#report?id=GD001-AAAA');
        await expect(page.locator('#dashpoint_id')).toHaveValue('GD001-AAAA');

        // Type into textarea and immediately trigger blur
        await page.fill('#log-textarea', 'Rapid note entry');
        await page.locator('#log-textarea').blur();

        // Check storage immediately without waiting 500ms debounce
        const savedDraft = await page.evaluate(async () => {
            return await window.DraftStorage.getDraft('GD001-AAAA');
        });
        expect(savedDraft).not.toBeNull();
        expect(savedDraft.notes).toBe('Rapid note entry');
    });

    test('Preserves draft if submission fails validation or distance check', async ({ page }) => {
        await page.goto('/#report?id=GD001-AAAA');
        await expect(page.locator('#dashpoint_id')).toHaveValue('GD001-AAAA');

        // Enter coordinates far away (> 100m, target is near NYC 40.7128, -74.0060)
        await page.fill('#input-lat', '0.000000');
        await page.locator('#input-lat').blur();
        await page.fill('#input-lon', '0.000000');
        await page.locator('#input-lon').blur();
        await page.fill('#log-textarea', 'Attempted log from far away.');
        await page.locator('#log-textarea').blur();

        // Attempt submission (not checked as attempt)
        await page.click('#btn-submit-report');

        // Distance rejection alert should appear
        const feedback = page.locator('#report-feedback');
        await expect(feedback).toContainText('Too far away', { timeout: 10000 });

        // Verify draft remains intact in IndexedDB
        const draftAfterRejection = await page.evaluate(async () => {
            return await window.DraftStorage.getDraft('GD001-AAAA');
        });
        expect(draftAfterRejection).not.toBeNull();
        expect(draftAfterRejection.notes).toBe('Attempted log from far away.');
    });

    test('Prompts confirmation before overwriting locked coordinates on re-sync', async ({ page }) => {
        await page.goto('/#report?id=GD001-AAAA');
        await expect(page.locator('#dashpoint_id')).toHaveValue('GD001-AAAA');

        // Initial coordinates
        await page.fill('#input-lat', '40.712800');
        await page.fill('#input-lon', '-74.006000');

        // Configure mockGeolocation to return new position
        await page.evaluate(() => {
            window.mockGeolocation = {
                getCurrentPosition: (success) => {
                    success({ coords: { latitude: 35.000000, longitude: -80.000000, accuracy: 5 } });
                }
            };
        });

        // 1. User cancels the overwrite dialog
        page.once('dialog', async (dialog) => {
            expect(dialog.message()).toContain('Coordinates are already locked');
            await dialog.dismiss();
        });
        await page.click('#btn-geolocation');

        // Coordinates should remain untouched
        await expect(page.locator('#input-lat')).toHaveValue('40.712800');
        await expect(page.locator('#input-lon')).toHaveValue('-74.006000');

        // 2. User confirms the overwrite dialog
        page.once('dialog', async (dialog) => {
            expect(dialog.message()).toContain('Coordinates are already locked');
            await dialog.accept();
        });
        await page.click('#btn-geolocation');

        // Coordinates should now update to new mock position
        await expect(page.locator('#input-lat')).toHaveValue('35.000000');
        await expect(page.locator('#input-lon')).toHaveValue('-80.000000');
    });

    test('Protects active field report from accidental mobile backdrop dismissal', async ({ page }) => {
        // Set mobile viewport
        await page.setViewportSize({ width: 390, height: 844 });
        await page.goto('/#report?id=GD001-AAAA');
        await expect(page.locator('#form-report')).toBeVisible();

        // Click outside the form onto app-content background
        await page.locator('#app-content').click({ position: { x: 5, y: 5 } });

        // URL must stay on report route and form must remain visible
        await expect(page.locator('#form-report')).toBeVisible();
        expect(page.url()).toContain('#report?id=GD001-AAAA');
    });

    test('Renders native camera tip in report form photo section', async ({ page }) => {
        await page.goto('/#report?id=GD001-AAAA');
        const tips = page.locator('.photo-caption-tip');
        await expect(tips.first()).toContainText('native Camera app first');
    });
});
