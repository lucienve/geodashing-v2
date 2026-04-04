/**
 * Geodashing Global API Fetch Wrapper
 *
 * Exposes asynchronous functions mapping the UI to the backend API.
 */

const API = {
    getCsrfToken: function() {
        const match = document.cookie.match(new RegExp('(^| )csrf_token=([^;]+)'));
        return match ? match[2] : '';
    },

    getHeaders: function() {
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
            const res = await fetch('backend/api/report.php', {
                method: 'POST',
                headers: this.getHeaders(),
                body: formData // Specifically bypassing Content-Type override allowing multipart/form-data bounding natively!
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
            const res = await fetch('backend/api/edit.php', {
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
    getGames: async function() {
        try {
            const res = await fetch('backend/api/games.php', {
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
     * @param {number} userId
     */
    getProfile: async function(userId) {
        try {
            const res = await fetch(`backend/api/profile.php?id=${userId}`, {
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

            const res = await fetch('backend/api/auth.php?action=login', {
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
    signup: async function (username, email, password) {
        try {
            const data = new URLSearchParams();
            data.append('username', username);
            data.append('email', email);
            data.append('password', password);

            const res = await fetch('backend/api/auth.php?action=signup', {
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

            const res = await fetch('backend/api/auth.php?action=forgot_password', {
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

            const res = await fetch('backend/api/auth.php?action=reset_password', {
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
            const res = await fetch('backend/api/auth.php?action=logout', {
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
            let url = 'backend/api/leaderboard.php';
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
    checkSession: async function () {
        try {
            const res = await fetch('backend/api/auth.php?action=session', {
                method: 'POST', // Auth endpoint enforces POST mapped strictly
                headers: this.getHeaders()
            });
            return await res.json();
        } catch (e) {
            return { status: 'error', message: 'Session Network Failure!' };
        }
    },

    /**
     * Re-trigger the verification email.
     */
    resendVerification: async function () {
        try {
            const res = await fetch('backend/api/auth.php?action=resend_verification', {
                method: 'POST',
                headers: this.getHeaders()
            });
            return await res.json();
        } catch (e) {
            console.error(e);
            return { status: 'error', message: 'API Network Timeout!' };
        }
    }
};

// Expose standard custom Event hooks so the Router can wake up templates
document.addEventListener('routeLoaded', (e) => {
    // When #report or #login loads dynamically, this event physical fires natively!
    // E.g. console.log("New UI View Array Mapped:", e.detail.route);
});
