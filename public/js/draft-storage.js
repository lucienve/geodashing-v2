/**
 * Geodashing V2 - Draft Storage Service
 *
 * Provides offline client-side persistence for visit report drafts using IndexedDB.
 * Supports binary Blobs for uploaded photos alongside form metadata and locked GPS coordinates.
 * Includes graceful in-memory fallback for Private Browsing environments where IndexedDB is blocked.
 */

(function () {
    'use strict';

    const DB_NAME = 'geodashing_db';
    const DB_VERSION = 1;
    const STORE_NAME = 'report_drafts';

    let dbInstance = null;
    let dbOpenPromise = null;
    let isIndexedDBSupported = true;
    const memoryFallbackStore = new Map();

    /**
     * Clones a draft record and reconstitutes photo Blob objects from stored ArrayBuffers.
     * Ensures consistent object representation across IndexedDB and in-memory fallback paths.
     *
     * @param {Object|null} record Raw stored draft record.
     * @returns {Object|null} Hydrated draft record with usable Blobs.
     */
    function hydrateRecord(record) {
        if (!record) {
            return null;
        }

        const clone = { ...record };
        if (Array.isArray(clone.photos)) {
            clone.photos = clone.photos.map((photo) => {
                if (!photo || typeof photo !== 'object') {
                    return photo;
                }
                const photoClone = { ...photo };
                if (photoClone.buffer && !photoClone.blob) {
                    photoClone.blob = new Blob([photoClone.buffer], {
                        type: photoClone.type || 'image/jpeg'
                    });
                }
                return photoClone;
            });
        }
        return clone;
    }

    /**
     * Opens or retrieves the cached IndexedDB database connection.
     * Gracefully falls back to an in-memory Map if IndexedDB is blocked or unavailable.
     *
     * @returns {Promise<IDBDatabase|null>} The active database instance, or null if using fallback.
     */
    async function getDb() {
        if (!isIndexedDBSupported) {
            return null;
        }

        if (dbInstance) {
            return dbInstance;
        }

        if (dbOpenPromise) {
            return dbOpenPromise;
        }

        if (typeof window === 'undefined' || !window.indexedDB) {
            isIndexedDBSupported = false;
            return null;
        }

        dbOpenPromise = new Promise((resolve) => {
            try {
                const request = window.indexedDB.open(DB_NAME, DB_VERSION);

                request.onupgradeneeded = (event) => {
                    const db = event.target.result;
                    if (!db.objectStoreNames.contains(STORE_NAME)) {
                        db.createObjectStore(STORE_NAME, { keyPath: 'dashpoint_id' });
                    }
                };

                request.onsuccess = (event) => {
                    dbInstance = event.target.result;
                    dbInstance.onversionchange = () => {
                        dbInstance.close();
                        dbInstance = null;
                    };
                    dbInstance.onclose = () => {
                        dbInstance = null;
                    };
                    dbOpenPromise = null;
                    resolve(dbInstance);
                };

                request.onblocked = (event) => {
                    console.warn('DraftStorage: IndexedDB open request blocked by another connection.', event);
                };

                request.onerror = (event) => {
                    console.warn('DraftStorage: IndexedDB access failed, using in-memory store.', event.target.error);
                    isIndexedDBSupported = false;
                    dbOpenPromise = null;
                    resolve(null);
                };
            } catch (err) {
                console.warn('DraftStorage: Security exception opening IndexedDB, using in-memory store.', err);
                isIndexedDBSupported = false;
                dbOpenPromise = null;
                resolve(null);
            }
        });

        return dbOpenPromise;
    }

    /**
     * Persists a visit report draft.
     *
     * @param {string} dashpointId Unique identifier of the target dashpoint.
     * @param {Object} draftData Serialized form fields and photo blobs.
     * @returns {Promise<boolean>} True if successfully saved, false otherwise.
     */
    async function saveDraft(dashpointId, draftData) {
        if (!dashpointId || !draftData || typeof draftData !== 'object') {
            return false;
        }

        // Convert any photo Blobs to ArrayBuffers for robust cross-browser IndexedDB compatibility
        // (WebKit on some platforms throws UnknownError: Error preparing Blob/File data)
        const processedPhotos = [];
        if (Array.isArray(draftData.photos)) {
            for (const photo of draftData.photos) {
                if (!photo || typeof photo !== 'object') {
                    continue;
                }

                const mimeType = photo.type || (photo.blob && photo.blob.type) || 'image/jpeg';
                const fileName = photo.name || (photo.blob && photo.blob.name) || 'photo.jpg';
                const caption = photo.caption || '';

                if (photo.blob && typeof photo.blob.arrayBuffer === 'function') {
                    try {
                        const buffer = await photo.blob.arrayBuffer();
                        processedPhotos.push({
                            buffer,
                            name: fileName,
                            type: mimeType,
                            caption
                        });
                    } catch (photoErr) {
                        console.warn('DraftStorage: Failed to read photo blob into ArrayBuffer.', photoErr);
                    }
                } else if (photo.buffer) {
                    processedPhotos.push({
                        buffer: photo.buffer,
                        name: fileName,
                        type: mimeType,
                        caption
                    });
                }
            }
        }

        const record = {
            ...draftData,
            dashpoint_id: dashpointId,
            photos: processedPhotos,
            updated_at: Date.now()
        };

        const db = await getDb();
        if (!db) {
            memoryFallbackStore.set(dashpointId, record);
            return true;
        }

        return new Promise((resolve) => {
            try {
                const transaction = db.transaction([STORE_NAME], 'readwrite');
                const store = transaction.objectStore(STORE_NAME);
                const request = store.put(record);

                request.onsuccess = () => resolve(true);

                request.onerror = (event) => {
                    const error = event.target.error;
                    if (error && error.name === 'QuotaExceededError') {
                        console.warn('DraftStorage: Device storage quota exceeded while saving draft.');
                    } else {
                        console.warn('DraftStorage: Failed to persist draft.', error);
                    }
                    resolve(false);
                };
            } catch (err) {
                console.warn('DraftStorage: Error creating save transaction.', err);
                resolve(false);
            }
        });
    }

    /**
     * Retrieves a stored visit report draft for a specific dashpoint.
     *
     * @param {string} dashpointId Unique identifier of the target dashpoint.
     * @returns {Promise<Object|null>} The hydrated draft record, or null if none exists.
     */
    async function getDraft(dashpointId) {
        if (!dashpointId) {
            return null;
        }

        const db = await getDb();
        if (!db) {
            const fallbackRecord = memoryFallbackStore.get(dashpointId);
            return hydrateRecord(fallbackRecord);
        }

        return new Promise((resolve) => {
            try {
                const transaction = db.transaction([STORE_NAME], 'readonly');
                const store = transaction.objectStore(STORE_NAME);
                const request = store.get(dashpointId);

                request.onsuccess = (event) => {
                    resolve(hydrateRecord(event.target.result));
                };

                request.onerror = (event) => {
                    console.warn('DraftStorage: Failed to retrieve draft.', event.target.error);
                    resolve(null);
                };
            } catch (err) {
                console.warn('DraftStorage: Error creating read transaction.', err);
                resolve(null);
            }
        });
    }

    /**
     * Deletes a stored draft from persistent storage upon submission or manual discard.
     *
     * @param {string} dashpointId Unique identifier of the target dashpoint.
     * @returns {Promise<boolean>} True if successfully deleted, false otherwise.
     */
    async function deleteDraft(dashpointId) {
        if (!dashpointId) {
            return false;
        }

        memoryFallbackStore.delete(dashpointId);

        const db = await getDb();
        if (!db) {
            return true;
        }

        return new Promise((resolve) => {
            try {
                const transaction = db.transaction([STORE_NAME], 'readwrite');
                const store = transaction.objectStore(STORE_NAME);
                const request = store.delete(dashpointId);

                request.onsuccess = () => resolve(true);

                request.onerror = (event) => {
                    console.warn('DraftStorage: Failed to delete draft.', event.target.error);
                    resolve(false);
                };
            } catch (err) {
                console.warn('DraftStorage: Error creating delete transaction.', err);
                resolve(false);
            }
        });
    }

    /**
     * Retrieves all stored drafts across all dashpoints.
     *
     * @returns {Promise<Array<Object>>} List of all stored drafts with hydrated Blobs.
     */
    async function getAllDrafts() {
        const db = await getDb();
        if (!db) {
            return Array.from(memoryFallbackStore.values()).map(hydrateRecord);
        }

        return new Promise((resolve) => {
            try {
                const transaction = db.transaction([STORE_NAME], 'readonly');
                const store = transaction.objectStore(STORE_NAME);
                const request = store.getAll();

                request.onsuccess = (event) => {
                    const records = event.target.result || [];
                    resolve(records.map(hydrateRecord));
                };

                request.onerror = (event) => {
                    console.warn('DraftStorage: Failed to read all drafts.', event.target.error);
                    resolve([]);
                };
            } catch (err) {
                console.warn('DraftStorage: Error creating getAll transaction.', err);
                resolve([]);
            }
        });
    }

    /**
     * Removes drafts that have not been updated within the specified retention window.
     *
     * @param {number} maxAgeDays Maximum draft age in days before pruning (default: 7).
     * @returns {Promise<number>} Count of pruned drafts.
     */
    async function pruneExpiredDrafts(maxAgeDays = 7) {
        const validAgeDays = (typeof maxAgeDays === 'number' && !isNaN(maxAgeDays) && maxAgeDays >= 0)
            ? maxAgeDays
            : 7;
        const cutoffTime = Date.now() - (validAgeDays * 24 * 60 * 60 * 1000);
        let prunedCount = 0;

        const db = await getDb();
        if (!db) {
            for (const [key, value] of memoryFallbackStore.entries()) {
                if (!value || !value.updated_at || value.updated_at < cutoffTime) {
                    memoryFallbackStore.delete(key);
                    prunedCount++;
                }
            }
            return prunedCount;
        }

        return new Promise((resolve) => {
            try {
                const transaction = db.transaction([STORE_NAME], 'readwrite');
                const store = transaction.objectStore(STORE_NAME);
                const request = store.openCursor();

                transaction.oncomplete = () => resolve(prunedCount);
                transaction.onerror = (event) => {
                    console.warn('DraftStorage: Transaction error during draft pruning.', event.target.error);
                    resolve(prunedCount);
                };

                request.onsuccess = (event) => {
                    const cursor = event.target.result;
                    if (cursor) {
                        const record = cursor.value;
                        if (!record || !record.updated_at || record.updated_at < cutoffTime) {
                            cursor.delete();
                            prunedCount++;
                        }
                        cursor.continue();
                    }
                };

                request.onerror = (event) => {
                    console.warn('DraftStorage: Error opening pruning cursor.', event.target.error);
                    resolve(prunedCount);
                };
            } catch (err) {
                console.warn('DraftStorage: Error creating pruning transaction.', err);
                resolve(prunedCount);
            }
        });
    }

    /**
     * Purges all stored drafts from the object store.
     *
     * @returns {Promise<boolean>} True if cleared successfully.
     */
    async function clearAllDrafts() {
        memoryFallbackStore.clear();

        const db = await getDb();
        if (!db) {
            return true;
        }

        return new Promise((resolve) => {
            try {
                const transaction = db.transaction([STORE_NAME], 'readwrite');
                const store = transaction.objectStore(STORE_NAME);
                const request = store.clear();

                request.onsuccess = () => resolve(true);
                request.onerror = () => resolve(false);
            } catch (_err) {
                resolve(false);
            }
        });
    }

    const DraftStorage = {
        saveDraft,
        getDraft,
        deleteDraft,
        getAllDrafts,
        pruneExpiredDrafts,
        clearAllDrafts
    };

    if (typeof window !== 'undefined') {
        window.DraftStorage = DraftStorage;
    }

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = DraftStorage;
    }
})();
