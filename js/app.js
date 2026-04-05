/**
 * Geodashing Vanilla SPA Router Engine
 * 
 * Intercepts completely native browser URL hashes (e.g. domain.com/#login) 
 * intercepting standard navigation and transparently loading HTML chunks over the map dynamically.
 */
/**
 * Global Haversine Math Core
 * Calculates the precise physical distance in meters across the spherical curvature of the Earth.
 */
window.calculateDistance = function (lat1, lon1, lat2, lon2) {
    const r = 6371e3; // Earth radius in meters
    const rad = Math.PI / 180;
    const phi1 = lat1 * rad;
    const phi2 = lat2 * rad;
    const deltaPhi = (lat2 - lat1) * rad;
    const deltaLambda = (lon2 - lon1) * rad;

    const a = Math.sin(deltaPhi / 2) * Math.sin(deltaPhi / 2) +
        Math.cos(phi1) * Math.cos(phi2) *
        Math.sin(deltaLambda / 2) * Math.sin(deltaLambda / 2);

    return r * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
};

/**
 * Escapes raw strings for safe HTML injection, preventing XSS.
 */
window.escapeHTML = function(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
};


document.addEventListener('DOMContentLoaded', () => {
    // 0. Global Game State Binding for Historical Tracking!
    window.currentGameContext = {
        id: null,
        is_active: true
    };

    // 1. Explicit Routing Logic Dictionary
    const routes = {
        '': null,
        '#home': null,
        '#dashpoint': 'templates/dashpoint.html',
        '#login': 'templates/login.html',
        '#report': 'templates/report.html',
        '#edit': 'templates/edit.html',
        '#search': 'templates/search.html',
        '#leaderboard': 'templates/leaderboard.html',
        '#profile': 'templates/profile.html',
        '#about': 'templates/about.html',
        '#how-to': 'templates/how-to.html',
        '#contact': 'templates/contact.html'
    };

    const contentDiv = document.getElementById('app-content');
    const navLinks = document.querySelectorAll('.nav-link');
    const gameSelector = document.getElementById('game-selector');

    const mobileMenuBtn = document.getElementById('mobile-menu-btn');
    const mobileNavDrawer = document.getElementById('mobile-nav-drawer');
    const mobileCloseBtn = document.getElementById('mobile-close-btn');

    if (mobileMenuBtn && mobileNavDrawer) {
        mobileMenuBtn.addEventListener('click', () => {
            mobileNavDrawer.classList.add('open');
        });
    }

    if (mobileCloseBtn && mobileNavDrawer) {
        mobileCloseBtn.addEventListener('click', () => {
            mobileNavDrawer.classList.remove('open');
        });
    }

    // 2. Bounding the SPA state natively
    async function loadRoute() {
        if (mobileNavDrawer) {
            mobileNavDrawer.classList.remove('open');
        }
        const fullHash = window.location.hash || '#home';

        if (window.trackPageview) {
            window.trackPageview(fullHash);
        }

        // Strip out query parameters cleanly so the dictionary perfectly understands `#dashpoint?id=123`
        const hash = fullHash.split('?')[0];

        const templatePath = routes[hash];

        // Ensure active Nav items get highlighted aesthetically
        navLinks.forEach(link => {
            link.classList.remove('active');
            if (link.getAttribute('href') === hash || link.getAttribute('href') === fullHash) {
                link.classList.add('active');
            }
        });

        if (templatePath === undefined) {
            contentDiv.innerHTML = '<div class="template-view"><h2>PAGE NOT FOUND</h2><p class="data-input" style="color:var(--accent-red)">Could not locate that page.</p></div>';
            return;
        }

        try {
            // Smoothly collapse the current UI out preventing janky HTML resets
            contentDiv.style.opacity = '0.3';

            // Allow the router to completely purge the DOM overlay for 100% Map Views!
            if (templatePath === null) {
                setTimeout(() => {
                    contentDiv.innerHTML = '';
                    contentDiv.style.opacity = '1';
                    document.dispatchEvent(new CustomEvent('routeLoaded', { detail: { route: fullHash } }));
                }, 100);
                return;
            }

            const response = await fetch(templatePath);
            if (!response.ok) throw new Error("Template layout missing continuously.");

            const html = await response.text();

            setTimeout(() => {
                contentDiv.innerHTML = html;
                contentDiv.style.opacity = '1';

                // CRITICAL: Since we just dumped raw HTML into the DOM natively, 
                // any JS listeners tied to buttons inside it must be re-bound!
                // We fire a custom event telling `controllers.js` to wake up routing the original exact query bounds!
                document.dispatchEvent(new CustomEvent('routeLoaded', { detail: { route: fullHash } }));
            }, 100);

        } catch (err) {
            console.error("Router Error: ", err);
            contentDiv.innerHTML = '<div class="template-view"><h2>NETWORK ERROR</h2><p class="data-input" style="color:var(--accent-red)">Oops! Having trouble communicating with the server.</p></div>';
            contentDiv.style.opacity = '1';
        }
    }

    // 3. Native History API bindings (so the Phone's 'Back' button physically works)
    window.addEventListener('hashchange', loadRoute);

    // Initial Boot mapping
    loadRoute();

    // 4. One-time Global Data Boot: Pings the active game parameters explicitly into the Header Navigation Bar
    API.getGames().then(json => {
        if (json.status === 'success' && json.data.length > 0) {
            // Find Active Game natively
            const activeGame = json.data.find(g => g.is_active == 1) || json.data[0];
            
            // Sync the Global App Context
            window.currentGameContext = {
                id: activeGame.id,
                is_active: activeGame.is_active == 1
            };

            // Populate the Dropdown natively
            if (gameSelector) {
                gameSelector.innerHTML = '';
                json.data.forEach(game => {
                    const d = new Date(game.start_time);
                    const monthYear = d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
                    const option = document.createElement('option');
                    option.value = game.id;
                    option.dataset.isActive = game.is_active;
                    option.dataset.title = game.title;
                    
                    // Removed titleStr to keep the option text short and prevent layout overflow on mobile
                    option.innerText = `Game ${game.id} (${monthYear})`;
                    
                    if (game.id === activeGame.id) {
                        option.selected = true;
                    }
                    gameSelector.appendChild(option);
                });

                // Bind the Context Switching Handler
                gameSelector.addEventListener('change', (e) => {
                    const selOpt = e.target.options[e.target.selectedIndex];
                    window.currentGameContext.id = parseInt(e.target.value);
                    window.currentGameContext.is_active = selOpt.dataset.isActive == '1';
                    
                    if (window.location.hash === '' || window.location.hash === '#home') {
                        if (typeof window.refreshMapBounds === 'function') {
                            window.refreshMapBounds();
                        }
                    } else {
                        loadRoute();
                    }
                });
            }
        }
    }).catch(err => console.error("Could not fetch active game configuration."));

    // 5. Native Javascript Session Bootstrapper dynamically driving the Nav Auth state securely
    window.updateAuthState = async function () {
        const authBtns = [document.getElementById('nav-auth-btn'), document.getElementById('mobile-nav-auth-btn')].filter(Boolean);

        try {
            const res = await API.checkSession();
            if (res.status === 'success') {
                window.currentUser = res; // Bind the full Payload (including is_verified) globally
                if (res.is_verified === 0) {
                    authBtns.forEach(btn => {
                        btn.innerText = `UNVERIFIED [CLICK TO RESEND]`;
                        btn.href = '#login';
                        btn.style.color = "var(--accent-amber)";
                        const newBtn = btn.cloneNode(true);
                        btn.replaceWith(newBtn);
                    });
                } else {
                    authBtns.forEach(btn => {
                        btn.innerText = `LOGOUT [${res.username}]`;
                        btn.href = '#';

                        const newBtn = btn.cloneNode(true);
                        btn.replaceWith(newBtn);

                        newBtn.addEventListener('click', async (e) => {
                            e.preventDefault();
                            await API.logout();
                            window.location.reload(); 
                        });
                    });
                    
                    const profileLink = document.getElementById('nav-profile-link');
                    if (profileLink) {
                        profileLink.classList.remove('d-none');
                        profileLink.href = `#profile?id=${res.user_id}`;
                    }
                }
            } else {
                window.currentUser = null;
                authBtns.forEach(btn => {
                    btn.innerText = `Player login`;
                    btn.href = '#login';

                    const newBtn = btn.cloneNode(true);
                    btn.replaceWith(newBtn);
                });

                const verifyBanner = document.getElementById('verify-banner');
                if (verifyBanner) verifyBanner.classList.add('d-none');
            }
        } catch (e) {
            console.error("Session integrity check failed.");
        }
    };

    // Execute the Auth loop instantly mapping the initial load!
    window.updateAuthState();
});
