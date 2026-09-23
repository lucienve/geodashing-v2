/**
 * Geodashing Global API Fetch Wrapper
 *
 * Exposes asynchronous functions mapping the UI to the backend API.
 */

window.API = {
    getCsrfToken: function () {
        const match = document.cookie.match(new RegExp('(^| )csrf_token=([^;]+)'));
        return match ? match[2] : '';
    },

    getHeaders: function () {
        const h = { 'Accept': 'application/json' };
        const token = this.getCsrfToken();
        if (token) {
            h['X-CSRF-Token'] = token;
        }
        return h;
    },

    /**
     * Submit a visit log
     * @param {FormData} formData Includes images, lat, lon, and log text
     */
    logVisit: async function (formData) {
        try {
            const res = await fetch('api/report.php', {
                method: 'POST',
                headers: this.getHeaders(),
                body: formData // Bypassing Content-Type override for multipart/form-data.
            });
            const data = await res.json();
            if (data.status === 'success' && window.trackEvent) {
                window.trackEvent('visit_logged', { points: data.points, distance: data.distance });
            }
            return data;
        } catch (e) {
            console.error(e);
            return { status: 'error', message: 'API Network Timeout!' };
        }
    },

    editVisit: async function (formData) {
        try {
            const res = await fetch('api/edit.php', {
                method: 'POST',
                headers: this.getHeaders(),
                body: formData // Same multipart wrapper supporting JSON strings and Image Binaries
            });
            return await res.json();
        } catch (e) {
            console.error(e);
            return { status: 'error', message: 'API Network Timeout!' };
        }
    },

    /**
     * Get list of historical games
     */
    getGames: async function () {
        try {
            const res = await fetch('api/games.php', {
                method: 'GET',
                headers: this.getHeaders()
            });
            return await res.json();
        } catch (e) {
            console.error(e);
            return { status: 'error', message: 'API Network Timeout!' };
        }
    },

    /**
     * Get user profile details and historical stats
     * @param {string} username
     */
    getProfile: async function (username) {
        try {
            const res = await fetch(`api/profile.php?username=${encodeURIComponent(username)}`, {
                method: 'GET',
                headers: this.getHeaders()
            });
            return await res.json();
        } catch (e) {
            console.error(e);
            return { status: 'error', message: 'API Network Timeout!' };
        }
    },

    /**
     * Authenticate user session
     * @param {string} username 
     * @param {string} password 
     */
    login: async function (username, password) {
        try {
            const data = new URLSearchParams();
            data.append('username', username);
            data.append('password', password);

            const res = await fetch('api/auth.php?action=login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    ...this.getHeaders()
                },
                body: data.toString()
            });
            return await res.json();
        } catch (e) {
            console.error(e);
            return { status: 'error', message: 'Auth Network Failure!' };
        }
    },

    /**
     * Register a new user
     */
    signup: async function (username, email, password, subscribe) {
        try {
            const data = new URLSearchParams();
            data.append('username', username);
            data.append('email', email);
            data.append('password', password);
            data.append('subscribe', subscribe ? '1' : '0');

            const res = await fetch('api/auth.php?action=signup', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    ...this.getHeaders()
                },
                body: data.toString()
            });
            const json = await res.json();
            if (json.status === 'success' && window.trackEvent) {
                window.trackEvent('sign_up');
            }
            return json;
        } catch (e) {
            console.error(e);
            return { status: 'error', message: 'Registration Network Failure!' };
        }
    },

    /**
     * Email a password reset link to the address on file.
     * @param {string} username 
     */
    requestPasswordReset: async function (username) {
        try {
            const data = new URLSearchParams();
            data.append('username', username);

            const res = await fetch('api/auth.php?action=forgot_password', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    ...this.getHeaders()
                },
                body: data.toString()
            });
            return await res.json();
        } catch (e) {
            console.error(e);
            return { status: 'error', message: 'Recovery Network Failure!' };
        }
    },

    /**
     * Authenticate the token, and set the new password if valid.
     * @param {string} token 
     * @param {string} newPassword 
     */
    executePasswordReset: async function (token, newPassword) {
        try {
            const data = new URLSearchParams();
            data.append('token', token);
            data.append('password', newPassword);

            const res = await fetch('api/auth.php?action=reset_password', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    ...this.getHeaders()
                },
                body: data.toString()
            });
            return await res.json();
        } catch (e) {
            console.error(e);
            return { status: 'error', message: 'Credential Logic Failure!' };
        }
    },

    /**
     * Logout current session
     */
    logout: async function () {
        try {
            this.resetUserTagsCache();
            const res = await fetch('api/auth.php?action=logout', {
                method: 'POST',
                headers: this.getHeaders()
            });
            return await res.json();
        } catch (e) {
            console.error(e);
            return { status: 'error', message: 'Logout Network Failure!' };
        }
    },

    /**
     * Call the leaderboard API
     * @param {number} gameId Optional integer ID to query historic games
     */
    getLeaderboard: async function (gameId = null) {
        try {
            let url = 'api/leaderboard.php';
            if (gameId !== null) {
                url += `?game_id=${gameId}`;
            }

            const res = await fetch(url, {
                method: 'GET',
                headers: this.getHeaders()
            });
            return await res.json();
        } catch (e) {
            console.error(e);
            return { status: 'error', message: 'API Network Timeout!' };
        }
    },

    /**
     * Poll the current session to ensure the user is authorized.
     */
    checkSession: async function (gameId = null) {
        try {
            let url = 'api/auth.php?action=session';
            if (gameId !== null) {
                url += `&game_id=${gameId}`;
            }
            const res = await fetch(url, {
                method: 'POST', // Auth endpoint enforces POST mapped strictly
                headers: this.getHeaders()
            });
            return await res.json();
        } catch (_e) {
            return { status: 'error', message: 'Session Network Failure!' };
        }
    },

    /**
     * Reroll a preview dashpoint
     * @param {FormData} formData Includes dashpoint_id and optional reason
     */
    rerollDashpoint: async function (formData) {
        try {
            const res = await fetch('api/reroll.php', {
                method: 'POST',
                headers: this.getHeaders(),
                body: formData
            });
            return await res.json();
        } catch (e) {
            console.error(e);
            return { status: 'error', message: 'API Network Timeout!' };
        }
    },

    /**
     * Re-trigger the verification email.
     */

    resendVerification: async function () {
        try {
            const res = await fetch('api/auth.php?action=resend_verification', {
                method: 'POST',
                headers: this.getHeaders()
            });
            return await res.json();
        } catch (e) {
            console.error(e);
            return { status: 'error', message: 'API Network Timeout!' };
        }
    },

    _userTagsCacheGameId: null,
    _userTagsPromise: null,
    _userTagsPromiseGameId: null,
    _userTagsMeta: {},
    _inFlightMutations: new Set(),
    _tagBroadcastChannel: null,
    _tagPollInterval: null,
    _tagVisibilityManager: null,
    TAG_TTL_MS: 60000,

    /**
     * Initializes multi-tab broadcast listening and background visibility polling.
     */
    initTagSync: function () {
        if (typeof window === 'undefined') return;

        if (!this._tagBroadcastChannel && typeof window.BroadcastChannel !== 'undefined') {
            try {
                this._tagBroadcastChannel = new window.BroadcastChannel('geodashing_tags');
                this._tagBroadcastChannel.onmessage = (event) => {
                    this._handleTagBroadcast(event.data);
                };
            } catch (e) {
                console.warn("BroadcastChannel initialization skipped:", e);
            }
        }

        if (!this._tagVisibilityManager && typeof window.VisibilityManager === 'function') {
            this._tagVisibilityManager = new window.VisibilityManager(
                () => this._onPageVisible(),
                () => this._onPageHidden()
            );
            this._tagVisibilityManager.start();
        }
    },

    /**
     * Defensive handler for incoming peer-tab BroadcastChannel messages.
     * @param {any} msg
     */
    _handleTagBroadcast: function (msg) {
        if (!msg || typeof msg !== 'object') return;
        const { action, gameId, dashpointId, tag } = msg;
        if (!action || !dashpointId) return;
        if (!['SET_TAG', 'DELETE_TAG'].includes(action)) return;
        if (typeof dashpointId !== 'string') return;

        const currentGameId = window.currentGameContext ? window.currentGameContext.id : null;
        if (gameId && currentGameId && gameId !== currentGameId) return;

        window.currentUserTags = window.currentUserTags || {};
        if (action === 'SET_TAG' && tag && typeof tag === 'object') {
            window.currentUserTags[dashpointId] = {
                color: String(tag.color || ''),
                shape: String(tag.shape || ''),
                name: String(tag.name || '')
            };
            if (typeof window.updateMarkerTag === 'function') {
                window.updateMarkerTag(dashpointId, window.currentUserTags[dashpointId]);
            }
        } else if (action === 'DELETE_TAG') {
            delete window.currentUserTags[dashpointId];
            if (typeof window.updateMarkerTag === 'function') {
                window.updateMarkerTag(dashpointId, null);
            }
        }

        document.dispatchEvent(new CustomEvent('userTagsChanged', {
            detail: { action, gameId, dashpointId, tag: action === 'SET_TAG' ? tag : null }
        }));
    },

    /**
     * Broadcasts a local tag mutation to peer browser tabs.
     */
    _broadcastTagChange: function (action, gameId, dashpointId, tag = null) {
        if (this._tagBroadcastChannel) {
            try {
                this._tagBroadcastChannel.postMessage({
                    action,
                    gameId,
                    dashpointId,
                    tag
                });
            } catch (e) {
                console.warn("Broadcast postMessage error:", e);
            }
        }
    },

    _onPageVisible: function () {
        this._startTagHeartbeat();
        const gameId = window.currentGameContext ? window.currentGameContext.id : null;
        if (gameId) {
            const meta = this._userTagsMeta[gameId];
            if (!meta || (Date.now() - meta.loadedAt > 30000)) {
                this.syncUserTags(gameId);
            }
        }
    },

    _onPageHidden: function () {
        this._stopTagHeartbeat();
    },

    _startTagHeartbeat: function () {
        this._stopTagHeartbeat();
        this._tagPollInterval = setInterval(() => {
            if (typeof document !== 'undefined' && document.hidden) return;
            const gameId = window.currentGameContext ? window.currentGameContext.id : null;
            if (gameId) {
                this.syncUserTags(gameId);
            }
        }, this.TAG_TTL_MS);
    },

    _stopTagHeartbeat: function () {
        if (this._tagPollInterval) {
            clearInterval(this._tagPollInterval);
            this._tagPollInterval = null;
        }
    },

    resetUserTagsCache: function () {
        this._userTagsCacheGameId = null;
        this._userTagsPromise = null;
        this._userTagsPromiseGameId = null;
        this._userTagsMeta = {};
        this._stopTagHeartbeat();
        if (typeof window !== 'undefined') {
            window.currentUserTags = {};
        }
    },

    /**
     * Deduplicated loader for user tags of a game with TTL and ETag revalidation.
     * @param {number} gameId
     * @param {boolean} forceRefresh
     */
    loadUserTags: async function (gameId, forceRefresh = false) {
        if (!gameId) return {};
        if (typeof window === 'undefined') return {};

        this.initTagSync();
        window.currentUserTags = window.currentUserTags || {};

        const meta = this._userTagsMeta[gameId] || { etag: null, loadedAt: 0 };
        const isFresh = !forceRefresh && (this._userTagsCacheGameId === gameId) && (Date.now() - meta.loadedAt < this.TAG_TTL_MS);

        if (isFresh) {
            return window.currentUserTags;
        }

        if (this._userTagsPromise && this._userTagsPromiseGameId === gameId) {
            return this._userTagsPromise;
        }

        this._userTagsPromiseGameId = gameId;
        this._userTagsPromise = (async () => {
            try {
                const res = await this.getUserTags(gameId, meta.etag);

                if (res.status === 'not_modified') {
                    this._userTagsMeta[gameId] = {
                        etag: meta.etag,
                        loadedAt: Date.now()
                    };
                    this._userTagsCacheGameId = gameId;
                    return window.currentUserTags;
                }

                if (res.status === 'success' && res.tags) {
                    const serverTags = res.tags;

                    for (const [dpId, tagData] of Object.entries(serverTags)) {
                        if (!this._inFlightMutations.has(dpId)) {
                            window.currentUserTags[dpId] = tagData;
                        }
                    }

                    for (const dpId of Object.keys(window.currentUserTags)) {
                        if (!serverTags[dpId] && !this._inFlightMutations.has(dpId)) {
                            delete window.currentUserTags[dpId];
                        }
                    }

                    this._userTagsMeta[gameId] = {
                        etag: res.etag || null,
                        loadedAt: Date.now()
                    };
                    this._userTagsCacheGameId = gameId;

                    document.dispatchEvent(new CustomEvent('userTagsChanged', {
                        detail: { gameId, tags: window.currentUserTags }
                    }));
                }
                return window.currentUserTags;
            } catch (err) {
                console.error("Failed to load user tags:", err);
                return window.currentUserTags || {};
            } finally {
                this._userTagsPromise = null;
            }
        })();

        return this._userTagsPromise;
    },

    /**
     * Forces revalidation of user tags for a game.
     * @param {number} gameId
     */
    syncUserTags: async function (gameId) {
        return this.loadUserTags(gameId, true);
    },

    /**
     * Fetch user tags dictionary for a specific game with optional ETag
     * @param {number} gameId
     * @param {string|null} etag
     */
    getUserTags: async function (gameId, etag = null) {
        try {
            const headers = Object.assign({}, this.getHeaders());
            if (etag) {
                headers['If-None-Match'] = etag;
            }
            const res = await fetch(`api/user_tags.php?game_id=${encodeURIComponent(gameId)}`, {
                method: 'GET',
                headers: headers
            });

            if (res.status === 304) {
                return { status: 'not_modified' };
            }

            const json = await res.json();
            const responseEtag = res.headers.get('ETag');
            if (responseEtag) {
                json.etag = responseEtag;
            }
            return json;
        } catch (e) {
            console.error(e);
            return { status: 'error', message: 'API Network Timeout!' };
        }
    },

    /**
     * Set a private user tag on a dashpoint and broadcast to peer tabs
     * @param {string} dashpointId
     * @param {string} color
     * @param {string} shape
     */
    setUserTag: async function (dashpointId, color, shape) {
        this.initTagSync();
        this._inFlightMutations.add(dashpointId);
        try {
            const headers = Object.assign({}, this.getHeaders(), { 'Content-Type': 'application/json' });
            const res = await fetch('api/user_tags.php', {
                method: 'POST',
                headers: headers,
                body: JSON.stringify({ dashpoint_id: dashpointId, color: color, shape: shape })
            });
            const json = await res.json();
            if (json.status === 'success') {
                const currentGameId = window.currentGameContext ? window.currentGameContext.id : null;
                this._broadcastTagChange('SET_TAG', currentGameId, dashpointId, { color, shape });
                if (currentGameId && this._userTagsMeta[currentGameId]) {
                    this._userTagsMeta[currentGameId].loadedAt = Date.now();
                }
            }
            return json;
        } catch (e) {
            console.error(e);
            return { status: 'error', message: 'API Network Timeout!' };
        } finally {
            this._inFlightMutations.delete(dashpointId);
        }
    },

    /**
     * Delete a private user tag from a dashpoint and broadcast to peer tabs
     * @param {string} dashpointId
     */
    deleteUserTag: async function (dashpointId) {
        this.initTagSync();
        this._inFlightMutations.add(dashpointId);
        try {
            const headers = Object.assign({}, this.getHeaders(), { 'Content-Type': 'application/json' });
            const res = await fetch('api/user_tags.php', {
                method: 'DELETE',
                headers: headers,
                body: JSON.stringify({ dashpoint_id: dashpointId })
            });
            const json = await res.json();
            if (json.status === 'success') {
                const currentGameId = window.currentGameContext ? window.currentGameContext.id : null;
                this._broadcastTagChange('DELETE_TAG', currentGameId, dashpointId, null);
                if (currentGameId && this._userTagsMeta[currentGameId]) {
                    this._userTagsMeta[currentGameId].loadedAt = Date.now();
                }
            }
            return json;
        } catch (e) {
            console.error(e);
            return { status: 'error', message: 'API Network Timeout!' };
        } finally {
            this._inFlightMutations.delete(dashpointId);
        }
    }
};

// Expose standard custom Event hooks so the Router can wake up templates
document.addEventListener('routeLoaded', (_e) => {
    // When #report or #login loads dynamically, this event fires.
});
