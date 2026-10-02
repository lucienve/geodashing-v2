const { test, expect } = require('@playwright/test');

test.describe('DraftStorage Service Unit & Integration Tests', () => {
    test.beforeEach(async ({ page }) => {
        await page.goto('/');
    });

    test('DraftStorage is globally defined and loaded', async ({ page }) => {
        const isDefined = await page.evaluate(() => {
            return typeof window.DraftStorage !== 'undefined' &&
                typeof window.DraftStorage.saveDraft === 'function' &&
                typeof window.DraftStorage.getDraft === 'function' &&
                typeof window.DraftStorage.deleteDraft === 'function' &&
                typeof window.DraftStorage.getAllDrafts === 'function' &&
                typeof window.DraftStorage.pruneExpiredDrafts === 'function' &&
                typeof window.DraftStorage.clearAllDrafts === 'function';
        });
        expect(isDefined).toBe(true);
    });

    test('Saves, retrieves, and deletes draft records including Blobs', async ({ page }) => {
        const testResult = await page.evaluate(async () => {
            const uniqueId = 'GD-BLOB-' + Date.now() + '-' + Math.floor(Math.random() * 10000);
            const mockBlob = new Blob(['mock-image-binary-data'], { type: 'image/jpeg' });
            const draftData = {
                lat: '42.123456',
                lon: '-71.123456',
                synced_at: 1727823456000,
                gps_display: 'LOCKED (SYNCED)',
                notes: 'Found in the back corner of the parking lot.',
                is_attempt: false,
                suppress_email: true,
                photos: [
                    {
                        blob: mockBlob,
                        name: 'evidence.jpg',
                        type: 'image/jpeg',
                        caption: 'Corner marker'
                    }
                ]
            };

            const saved = await window.DraftStorage.saveDraft(uniqueId, draftData);
            if (!saved) return { success: false, reason: 'Failed to save' };

            const retrieved = await window.DraftStorage.getDraft(uniqueId);
            if (!retrieved) return { success: false, reason: 'Failed to retrieve' };

            const retrievedBlobText = await retrieved.photos[0].blob.text();

            const deleted = await window.DraftStorage.deleteDraft(uniqueId);
            const afterDelete = await window.DraftStorage.getDraft(uniqueId);

            return {
                success: true,
                saved,
                retrievedNotes: retrieved.notes,
                retrievedLat: retrieved.lat,
                retrievedLon: retrieved.lon,
                retrievedCaption: retrieved.photos[0].caption,
                retrievedBlobText,
                deleted,
                afterDelete
            };
        });

        expect(testResult.reason || 'OK').toBe('OK');
        expect(testResult.success).toBe(true);
        expect(testResult.retrievedNotes).toBe('Found in the back corner of the parking lot.');
        expect(testResult.retrievedLat).toBe('42.123456');
        expect(testResult.retrievedLon).toBe('-71.123456');
        expect(testResult.retrievedCaption).toBe('Corner marker');
        expect(testResult.retrievedBlobText).toBe('mock-image-binary-data');
        expect(testResult.deleted).toBe(true);
        expect(testResult.afterDelete).toBeNull();
    });

    test('Preserves non-JPEG MIME types and handles missing input gracefully', async ({ page }) => {
        const result = await page.evaluate(async () => {
            const uniqueId = 'GD-PNG-' + Date.now() + '-' + Math.floor(Math.random() * 10000);
            const pngBlob = new Blob(['png-header-bytes'], { type: 'image/png' });

            const invalidCall = await window.DraftStorage.saveDraft(null, { notes: 'bad' });
            const invalidData = await window.DraftStorage.saveDraft(uniqueId, null);

            await window.DraftStorage.saveDraft(uniqueId, {
                notes: 'PNG Test',
                photos: [
                    {
                        blob: pngBlob,
                        name: 'chart.png'
                    }
                ]
            });

            const retrieved = await window.DraftStorage.getDraft(uniqueId);
            await window.DraftStorage.deleteDraft(uniqueId);

            return {
                invalidCall,
                invalidData,
                mimeType: retrieved.photos[0].blob.type,
                name: retrieved.photos[0].name
            };
        });

        expect(result.invalidCall).toBe(false);
        expect(result.invalidData).toBe(false);
        expect(result.mimeType).toBe('image/png');
        expect(result.name).toBe('chart.png');
    });

    test('pruneExpiredDrafts correctly cleans up only stale records and closes test handle', async ({ page }) => {
        const pruneResult = await page.evaluate(async () => {
            const prefix = 'GD-PRUNE-' + Date.now() + '-' + Math.floor(Math.random() * 10000);
            const freshId = prefix + '-FRESH';
            const staleId = prefix + '-STALE';

            // Save one fresh draft and one stale draft (older than 7 days)
            const freshData = {
                notes: 'Recent draft',
                updated_at: Date.now()
            };
            const staleData = {
                notes: 'Stale draft from 10 days ago',
                updated_at: Date.now() - (10 * 24 * 60 * 60 * 1000)
            };

            await window.DraftStorage.saveDraft(freshId, freshData);
            await window.DraftStorage.saveDraft(staleId, staleData);

            // Override stale draft updated_at since saveDraft sets it to Date.now()
            const db = await new Promise(resolve => {
                const req = indexedDB.open('geodashing_db', 1);
                req.onsuccess = () => resolve(req.result);
            });
            await new Promise((resolve, reject) => {
                const tx = db.transaction(['report_drafts'], 'readwrite');
                tx.objectStore('report_drafts').put({
                    dashpoint_id: staleId,
                    notes: 'Stale draft from 10 days ago',
                    updated_at: Date.now() - (10 * 24 * 60 * 60 * 1000)
                });
                tx.oncomplete = () => {
                    db.close();
                    resolve();
                };
                tx.onerror = () => {
                    db.close();
                    reject(tx.error);
                };
            });

            const prunedCount = await window.DraftStorage.pruneExpiredDrafts(7);
            const remainingFresh = await window.DraftStorage.getDraft(freshId);
            const remainingStale = await window.DraftStorage.getDraft(staleId);

            // Clean up fresh test record
            await window.DraftStorage.deleteDraft(freshId);

            return {
                prunedCount,
                hasFresh: remainingFresh !== null,
                hasStale: remainingStale !== null
            };
        });

        expect(pruneResult.prunedCount).toBeGreaterThanOrEqual(1);
        expect(pruneResult.hasFresh).toBe(true);
        expect(pruneResult.hasStale).toBe(false);
    });

    test('In-memory fallback mode correctly hydrates Blobs when IndexedDB is unavailable', async ({ page }) => {
        // Run in an isolated evaluate context where window.indexedDB is undefined
        const fallbackResult = await page.evaluate(async () => {
            const iframe = document.createElement('iframe');
            document.body.appendChild(iframe);

            // Redefine indexedDB to undefined in the iframe
            Object.defineProperty(iframe.contentWindow, 'indexedDB', {
                get: () => undefined
            });

            // Dynamically load draft-storage.js into the iframe
            const script = iframe.contentDocument.createElement('script');
            script.src = 'js/draft-storage.js';
            await new Promise(resolve => {
                script.onload = resolve;
                iframe.contentDocument.body.appendChild(script);
            });

            const iframeStorage = iframe.contentWindow.DraftStorage;
            const testId = 'GD-FALLBACK-TEST';
            const mockBlob = new iframe.contentWindow.Blob(['fallback-blob-content'], { type: 'image/webp' });

            const saved = await iframeStorage.saveDraft(testId, {
                notes: 'Fallback note in private mode',
                photos: [
                    {
                        blob: mockBlob,
                        name: 'fallback.webp',
                        type: 'image/webp',
                        caption: 'Fallback caption'
                    }
                ]
            });

            const retrieved = await iframeStorage.getDraft(testId);
            const allDrafts = await iframeStorage.getAllDrafts();

            const isBlob = retrieved && retrieved.photos[0].blob instanceof iframe.contentWindow.Blob;
            const textContent = isBlob ? await retrieved.photos[0].blob.text() : null;

            await iframeStorage.deleteDraft(testId);
            const afterDelete = await iframeStorage.getDraft(testId);

            document.body.removeChild(iframe);

            return {
                saved,
                retrievedNotes: retrieved ? retrieved.notes : null,
                isBlob,
                textContent,
                allCount: allDrafts.length,
                afterDelete
            };
        });

        expect(fallbackResult.saved).toBe(true);
        expect(fallbackResult.retrievedNotes).toBe('Fallback note in private mode');
        expect(fallbackResult.isBlob).toBe(true);
        expect(fallbackResult.textContent).toBe('fallback-blob-content');
        expect(fallbackResult.allCount).toBe(1);
        expect(fallbackResult.afterDelete).toBeNull();
    });
});
