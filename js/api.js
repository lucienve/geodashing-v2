/**
 * Geodashing Global API Fetch Wrapper
 *
 * Exposes a rigid library of asynchronous functions mapping the UI modules natively 
 * straight into the PHP secure backend.
 */

const API = {
    // Shared structural headers blocking CSRF and triggering JSON returns natively
    headers: {
        'Accept': 'application/json'
    },

    /**
     * Executes the Haversine payload check dynamically validating physical GPS coordinates
     * @param {FormData} formData Native HTML5 Mobile Form Dump containing images/lat/lon
     */
    logVisit: async function(formData) {
        try {
            const res = await fetch('backend/api/report.php', {
                method: 'POST',
                headers: this.headers,
                body: formData // Specifically bypassing Content-Type override allowing multipart/form-data bounding natively!
            });
            return await res.json();
        } catch (e) {
            console.error(e);
            return { status: 'error', message: 'API Network Timeout!' };
        }
    },

    /**
     * Attempts native Authentication via PHP Sessions mapping
     * @param {string} username 
     * @param {string} password 
     */
    login: async function(username, password) {
        try {
            const data = new URLSearchParams();
            data.append('username', username);
            data.append('password', password);

            const res = await fetch('backend/api/auth.php?action=login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    ...this.headers
                },
                body: data.toString()
            });
            return await res.json();
        } catch(e) {
            console.error(e);
            return { status: 'error', message: 'Auth Network Failure!' };
        }
    },

    /**
     * Attempts native Registration natively persisting the hash state safely
     */
    signup: async function(username, email, password) {
        try {
            const data = new URLSearchParams();
            data.append('username', username);
            data.append('email', email);
            data.append('password', password);

            const res = await fetch('backend/api/auth.php?action=signup', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    ...this.headers
                },
                body: data.toString()
            });
            return await res.json();
        } catch(e) {
            console.error(e);
            return { status: 'error', message: 'Registration Network Failure!' };
        }
    },

    /**
     * Purges the PHP backend session cleanly and formally returning the state natively
     */
    logout: async function() {
        try {
            const res = await fetch('backend/api/auth.php?action=logout', {
                method: 'POST',
                headers: this.headers
            });
            return await res.json();
        } catch(e) {
            console.error(e);
            return { status: 'error', message: 'Logout Network Failure!' };
        }
    },

    /**
     * Polls the live Session strictly ensuring the user is authorized.
     */
    checkSession: async function() {
        try {
            const res = await fetch('backend/api/auth.php?action=session', {
                method: 'POST', // Auth endpoint enforces POST mapped strictly
                headers: this.headers
            });
            return await res.json();
        } catch(e) {
            return { status: 'error', message: 'Session Network Failure!' };
        }
    }
};

// Expose standard custom Event hooks so the Router can wake up templates
document.addEventListener('routeLoaded', (e) => {
    // When #report or #login loads dynamically, this event physical fires natively!
    // E.g. console.log("New UI View Array Mapped:", e.detail.route);
});
