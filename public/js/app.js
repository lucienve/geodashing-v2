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
window.escapeHTML = function (str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
};


function initGlobalState() {
    // 0. Global game state binding for historical tracking.
    window.currentGameContext = {
        id: null,
        is_active: true,
        title: '',
        monthYear: ''
    };
    window.postMaxSize = '25M';
    window.postSizeBytes = 25 * 1024 * 1024; // Fallback fallback to 25MB
}

function initNavigation() {
    // --- BEGIN NAVIGATION BUILDER ---
    const APP_NAVIGATION = [
        { text: 'LEADERBOARD', mobileText: 'Leaderboard', href: '#leaderboard' },
        {
            text: 'HELP ▾', isDropdown: true, children: [
                { text: 'About', href: '#about' },
                { text: 'How to Play', href: '#how-to' },
                { text: 'Contact', href: '#contact' },
                { text: 'Export Game Data', mobileText: 'Export Data', href: '#search' }
            ]
        }
    ];

    const desktopContainer = document.getElementById('desktop-links');
    const mobileContainer = document.querySelector('.mobile-nav-links');
    const desktopAuthBtn = document.getElementById('nav-auth-btn');
    const mobileAuthBtn = document.getElementById('mobile-nav-auth-btn');

    APP_NAVIGATION.forEach(item => {
        if (item.isDropdown) {
            // Desktop Dropdown
            if (desktopContainer && desktopAuthBtn) {
                const dropDiv = document.createElement('div');
                dropDiv.className = 'dropdown';
                const mainLink = document.createElement('a');
                mainLink.href = '#';
                mainLink.className = 'nav-link';
                mainLink.innerText = item.text;
                const dropContent = document.createElement('div');
                dropContent.className = 'dropdown-content';
                item.children.forEach(child => {
                    const childLink = document.createElement('a');
                    childLink.href = child.href;
                    childLink.className = 'nav-link';
                    childLink.innerText = child.text;
                    dropContent.appendChild(childLink);
                });
                dropDiv.appendChild(mainLink);
                dropDiv.appendChild(dropContent);
                desktopContainer.insertBefore(dropDiv, desktopAuthBtn);
            }

            // Mobile Flat rendering (Help items are flattened directly into the drawer)
            if (mobileContainer && mobileAuthBtn) {
                item.children.forEach(child => {
                    const childLink = document.createElement('a');
                    childLink.href = child.href;
                    childLink.className = 'nav-link';
                    childLink.innerText = child.mobileText || child.text;
                    mobileContainer.insertBefore(childLink, mobileAuthBtn);
                });
            }
        } else {
            // Desktop Link
            if (desktopContainer && desktopAuthBtn) {
                const link = document.createElement('a');
                link.href = item.href;
                link.className = 'nav-link' + (item.defaultActive ? ' active' : '') + (item.extraClasses ? ' ' + item.extraClasses : '');
                if (item.idDesktop) link.id = item.idDesktop;
                link.innerText = item.text;
                desktopContainer.insertBefore(link, desktopAuthBtn);
            }

            // Mobile Link
            if (mobileContainer && mobileAuthBtn) {
                const link = document.createElement('a');
                link.href = item.href;
                link.className = 'nav-link' + (item.defaultActive ? ' active' : '') + (item.extraClasses ? ' ' + item.extraClasses : '');
                if (item.idMobile) link.id = item.idMobile;
                link.innerText = item.mobileText || item.text;
                mobileContainer.insertBefore(link, mobileAuthBtn);
            }
        }
    });
    // --- END NAVIGATION BUILDER ---
}

function initRouting() {
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
    const mobileMenuBtn = document.getElementById('mobile-menu-btn');
    const mobileNavDrawer = document.getElementById('mobile-nav-drawer');
    const mobileCloseBtn = document.getElementById('mobile-close-btn');
    const mobileNavBackdrop = document.getElementById('mobile-nav-backdrop');

    const closeMobileDrawer = () => {
        if (mobileNavDrawer) {
            mobileNavDrawer.classList.remove('open');
        }
        if (mobileNavBackdrop) {
            mobileNavBackdrop.classList.remove('open');
        }
    };

    if (mobileMenuBtn && mobileNavDrawer) {
        mobileMenuBtn.addEventListener('click', () => {
            mobileNavDrawer.classList.add('open');
            if (mobileNavBackdrop) {
                mobileNavBackdrop.classList.add('open');
            }
        });
    }

    if (mobileCloseBtn) {
        mobileCloseBtn.addEventListener('click', closeMobileDrawer);
    }

    if (mobileNavBackdrop) {
        mobileNavBackdrop.addEventListener('click', closeMobileDrawer);
    }

    if (contentDiv) {
        contentDiv.addEventListener('click', (e) => {
            if (e.target === contentDiv && window.innerWidth <= 768) {
                window.location.hash = '#home';
            }
        });
    }

    // 2. Bounding the SPA state
    window.loadRoute = async function () {
        closeMobileDrawer();
        
        let fullHash = window.location.hash;
        
        // SEO-friendly Query Parameter Fallback for indexing
        const urlParams = new URLSearchParams(window.location.search);
        if (!fullHash && urlParams.has('dashpoint')) {
            fullHash = `#dashpoint?id=${urlParams.get('dashpoint')}`;
        } else if (!fullHash && urlParams.has('summary')) {
            fullHash = '#leaderboard';
            window.autoOpenSummaryId = parseInt(urlParams.get('summary'), 10);
        } else if (!fullHash && urlParams.has('game')) {
            fullHash = `#leaderboard?game=${urlParams.get('game')}`;
        } else if (!fullHash && urlParams.has('page')) {
            fullHash = `#${urlParams.get('page')}`;
        } else if (!fullHash) {
            fullHash = '#home';
        }

        // Dynamically maintain the Canonical URL for Search Engines
        let canonicalTag = document.getElementById('canonical-link');
        if (!canonicalTag) {
            canonicalTag = document.createElement('link');
            canonicalTag.id = 'canonical-link';
            canonicalTag.rel = 'canonical';
            document.head.appendChild(canonicalTag);
        }

        if (fullHash.startsWith('#dashpoint?id=')) {
            const dpId = fullHash.split('?id=')[1];
            canonicalTag.href = `https://www.geodashing.org/?dashpoint=${dpId}`;
        } else if (fullHash.startsWith('#leaderboard')) {
            if (window.autoOpenSummaryId || (window.currentGameContext && !window.currentGameContext.is_active && window.currentGameContext.has_summary && !fullHash.includes('?'))) {
                const sumId = window.autoOpenSummaryId || window.currentGameContext.id;
                canonicalTag.href = `https://www.geodashing.org/?summary=${sumId}`;
            } else if (fullHash.includes('?')) {
                const hashParams = new URLSearchParams(fullHash.split('?')[1]);
                const gameId = hashParams.get('game') || hashParams.get('game_id');
                if (gameId) {
                    canonicalTag.href = `https://www.geodashing.org/?game=${gameId}`;
                } else {
                    canonicalTag.href = `https://www.geodashing.org/`;
                }
            } else {
                canonicalTag.href = `https://www.geodashing.org/`;
            }
        } else if (['#about', '#how-to', '#contact'].includes(fullHash)) {
            const pageId = fullHash.substring(1);
            canonicalTag.href = `https://www.geodashing.org/?page=${pageId}`;
        } else {
            canonicalTag.href = `https://www.geodashing.org/`;
        }

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
            contentDiv.classList.add('overlay-active');
            return;
        }

        try {
            // Smoothly collapse the current UI out preventing janky HTML resets
            contentDiv.style.opacity = '0.3';

            // Allow the router to purge the DOM overlay for map views.
            if (templatePath === null) {
                setTimeout(() => {
                    contentDiv.innerHTML = '';
                    contentDiv.classList.remove('overlay-active');
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
                contentDiv.classList.add('overlay-active');
                contentDiv.style.opacity = '1';

                // CRITICAL: Since we just injected raw HTML into the DOM, 
                // any JS listeners tied to buttons inside it must be re-bound.
                // We fire a custom event telling `controllers.js` to wake up and route the original query bounds.
                document.dispatchEvent(new CustomEvent('routeLoaded', { detail: { route: fullHash } }));
            }, 100);

        } catch (err) {
            console.error("Router Error: ", err);
            contentDiv.innerHTML = '<div class="template-view"><h2>NETWORK ERROR</h2><p class="data-input" style="color:var(--accent-red)">Oops! Having trouble communicating with the server.</p></div>';
            contentDiv.classList.add('overlay-active');
            contentDiv.style.opacity = '1';
        }
    };

    // 3. Native History API bindings (so the Phone's 'Back' button works)
    window.addEventListener('hashchange', window.loadRoute);

    // Initial Boot mapping
    window.loadRoute();
}

function initGameContext() {
    // 4. One-time Global Data Boot: Pings the active game parameters explicitly into the Header Navigation Bar
    const gameSelector = document.getElementById('game-selector');

    window.gameContextLoaded = API.getGames().then(json => {
        if (json.status === 'success' && json.data.length > 0) {
            // Find Active Game
            const activeGame = json.data.find(g => g.is_active == 1) || json.data[0];
            window.activeGameId = activeGame.id;

            let targetGameId = activeGame.id;
            let fullHash = window.location.hash;
            const urlParams = new URLSearchParams(window.location.search);
            if (!fullHash && urlParams.has('dashpoint')) {
                fullHash = `#dashpoint?id=${urlParams.get('dashpoint')}`;
            } else if (!fullHash && urlParams.has('summary')) {
                const parsedId = parseInt(urlParams.get('summary'), 10);
                if (!isNaN(parsedId) && json.data.find(g => g.id === parsedId)) {
                    targetGameId = parsedId;
                }
            } else if (!fullHash && urlParams.has('game')) {
                const parsedId = parseInt(urlParams.get('game'), 10);
                if (!isNaN(parsedId) && json.data.find(g => g.id === parsedId)) {
                    targetGameId = parsedId;
                }
            }
            if (fullHash.startsWith('#dashpoint?id=')) {
                const dpId = fullHash.split('?id=')[1];
                if (dpId && dpId.startsWith('GD')) {
                    const gameIdStr = dpId.split('-')[0].substring(2);
                    const parsedId = parseInt(gameIdStr, 10);
                    if (!isNaN(parsedId) && json.data.find(g => g.id === parsedId)) {
                        targetGameId = parsedId;
                    }
                }
            }
            if (fullHash.startsWith('#leaderboard')) {
                if (fullHash.includes('?')) {
                    const hashParams = new URLSearchParams(fullHash.split('?')[1]);
                    const gameIdStr = hashParams.get('game') || hashParams.get('game_id');
                    if (gameIdStr) {
                        const parsedId = parseInt(gameIdStr, 10);
                        if (!isNaN(parsedId) && json.data.find(g => g.id === parsedId)) {
                            targetGameId = parsedId;
                        }
                    }
                }
            }

            const selectedGame = json.data.find(g => g.id === targetGameId) || activeGame;

            window.currentGameContext.id = selectedGame.id;
            window.currentGameContext.is_active = selectedGame.is_active == 1;
            window.currentGameContext.title = selectedGame.title;
            window.currentGameContext.has_summary = selectedGame.has_summary == 1;
            const activeD = new Date(selectedGame.start_time);
            window.currentGameContext.monthYear = activeD.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });

            // Populate the Dropdown
            if (gameSelector) {
                gameSelector.innerHTML = '';
                const activeGameStart = new Date(activeGame.start_time).getTime();
                const fragment = document.createDocumentFragment();
                
                json.data.forEach(game => {
                    const d = new Date(game.start_time);
                    const gameStart = d.getTime();
                    const monthYear = d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
                    const option = document.createElement('option');
                    option.value = game.id;
                    option.dataset.isActive = game.is_active;
                    option.dataset.title = game.title;
                    option.dataset.monthYear = monthYear;
                    option.dataset.hasSummary = game.has_summary;

                    let statusTag = '';
                    if (game.id !== activeGame.id) {
                        if (gameStart > activeGameStart) {
                            statusTag = ' [PREVIEW]';
                        } else if (gameStart < activeGameStart) {
                            statusTag = ' [COMPLETED]';
                        }
                    }

                    // Removed titleStr to keep the option text short and prevent layout overflow on mobile
                    option.innerText = `Game ${game.id} (${monthYear})${statusTag}`;

                    if (game.id === selectedGame.id) {
                        option.selected = true;
                    }
                    fragment.appendChild(option);
                });

                gameSelector.appendChild(fragment);

                // Bind the Context Switching Handler
                gameSelector.addEventListener('change', (e) => {
                    const selOpt = e.target.options[e.target.selectedIndex];
                    const gameId = parseInt(e.target.value);
                    window.currentGameContext.id = gameId;
                    window.currentGameContext.is_active = selOpt.dataset.isActive == '1';
                    window.currentGameContext.title = selOpt.dataset.title;
                    window.currentGameContext.monthYear = selOpt.dataset.monthYear;
                    window.currentGameContext.has_summary = selOpt.dataset.hasSummary == '1';

                    if (window.location.hash.startsWith('#leaderboard')) {
                        const targetHash = (window.activeGameId && gameId === window.activeGameId) 
                            ? '#leaderboard' 
                            : `#leaderboard?game=${gameId}`;
                        
                        if (window.location.hash !== targetHash) {
                            window.location.hash = targetHash;
                        } else {
                            if (window.loadRoute) {
                                window.loadRoute();
                            }
                        }
                    } else if (window.location.hash === '' || window.location.hash === '#home') {
                        if (typeof window.refreshMapBounds === 'function') {
                            window.refreshMapBounds();
                        }
                    } else {
                        if (window.loadRoute) {
                            window.loadRoute();
                        }
                    }
                });
            }
        }
    }).catch(_err => console.error("Could not fetch active game configuration."));
}

function initAuthState() {
    // 5. Javascript Session Bootstrapper driving the Nav Auth state
    window.updateAuthState = async function () {
        const desktopContainer = document.getElementById('desktop-links');
        const mobileContainer = document.querySelector('.mobile-nav-links');

        // Locate or recover standard auth buttons, maintaining expected IDs cleanly
        let navAuthBtn = document.getElementById('nav-auth-btn') || document.getElementById('hidden-nav-auth-btn');
        let mobileAuthBtn = document.getElementById('mobile-nav-auth-btn') || document.getElementById('hidden-mobile-nav-auth-btn');

        if (navAuthBtn) {
            navAuthBtn.id = 'nav-auth-btn';
        }
        if (mobileAuthBtn) {
            mobileAuthBtn.id = 'mobile-nav-auth-btn';
        }

        // Clean up previously created dynamic DOM elements to prevent duplicate groups
        const oldUserDropdown = document.getElementById('nav-user-dropdown');
        if (oldUserDropdown) {
            oldUserDropdown.remove();
        }

        const oldMobileGroup = document.getElementById('mobile-player-group');
        if (oldMobileGroup) {
            oldMobileGroup.remove();
        }

        try {
            const res = await API.checkSession();
            if (res.status === 'success') {
                window.currentUser = res; // Bind the full Payload (including is_verified) globally
                if (res.post_max_size) {
                    window.postMaxSize = res.post_max_size;
                }
                if (res.post_max_size_bytes) {
                    window.postSizeBytes = res.post_max_size_bytes;
                }
                if (res.is_verified === 0) {
                    if (navAuthBtn) {
                        navAuthBtn.style.display = '';
                        navAuthBtn.innerText = `UNVERIFIED [CLICK TO RESEND]`;
                        navAuthBtn.href = '#login';
                        navAuthBtn.style.color = "var(--accent-amber)";
                        const newBtn = navAuthBtn.cloneNode(true);
                        navAuthBtn.replaceWith(newBtn);
                        navAuthBtn = newBtn;
                    }
                    if (mobileAuthBtn) {
                        mobileAuthBtn.style.display = '';
                        mobileAuthBtn.innerText = `UNVERIFIED [CLICK TO RESEND]`;
                        mobileAuthBtn.href = '#login';
                        mobileAuthBtn.style.color = "var(--accent-amber)";
                        const newBtn = mobileAuthBtn.cloneNode(true);
                        mobileAuthBtn.replaceWith(newBtn);
                        mobileAuthBtn = newBtn;
                    }
                } else {
                    // Authenticated & verified!
                    
                    // 1. Desktop Profile & Logout Dropdown Menu
                    if (navAuthBtn && desktopContainer) {
                        navAuthBtn.style.display = 'none';
                        navAuthBtn.id = 'hidden-nav-auth-btn';

                        const dropDiv = document.createElement('div');
                        dropDiv.id = 'nav-user-dropdown';
                        dropDiv.className = 'dropdown';

                        // Dropdown trigger anchor
                        const triggerBtn = document.createElement('a');
                        triggerBtn.id = 'nav-auth-btn';
                        triggerBtn.className = 'nav-link highlight';
                        triggerBtn.href = '#';
                        triggerBtn.innerText = `👤 ${res.username} ▾`;

                        triggerBtn.addEventListener('click', (e) => {
                            e.preventDefault();
                        });

                        const dropContent = document.createElement('div');
                        dropContent.className = 'dropdown-content';

                        const profileLink = document.createElement('a');
                        profileLink.id = 'nav-profile-link';
                        profileLink.className = 'nav-link';
                        profileLink.href = `#profile?username=${encodeURIComponent(res.username)}`;
                        profileLink.innerText = 'My Profile';

                        const logoutLink = document.createElement('a');
                        logoutLink.id = 'desktop-logout-link';
                        logoutLink.className = 'nav-link';
                        logoutLink.href = '#';
                        logoutLink.innerText = 'Logout';
                        logoutLink.addEventListener('click', async (e) => {
                            e.preventDefault();
                            await API.logout();
                            window.location.reload();
                        });

                        dropContent.appendChild(profileLink);
                        dropContent.appendChild(logoutLink);

                        dropDiv.appendChild(triggerBtn);
                        dropDiv.appendChild(dropContent);

                        desktopContainer.appendChild(dropDiv);
                    }

                    // 2. Mobile Grouped Navigation Setup
                    if (mobileAuthBtn && mobileContainer) {
                        mobileAuthBtn.style.display = 'none';
                        mobileAuthBtn.id = 'hidden-mobile-nav-auth-btn';

                        const mobileGroup = document.createElement('div');
                        mobileGroup.id = 'mobile-player-group';

                        const header = document.createElement('div');
                        header.className = 'mobile-player-header';
                        header.innerText = 'Player Actions';

                        const profileLink = document.createElement('a');
                        profileLink.id = 'mobile-nav-profile-link';
                        profileLink.className = 'nav-link mobile-player-link';
                        profileLink.href = `#profile?username=${encodeURIComponent(res.username)}`;
                        profileLink.innerText = 'Profile';

                        const logoutLink = document.createElement('a');
                        logoutLink.id = 'mobile-logout-link';
                        logoutLink.className = 'nav-link mobile-player-link';
                        logoutLink.href = '#';
                        logoutLink.innerText = 'Logout';
                        logoutLink.addEventListener('click', async (e) => {
                            e.preventDefault();
                            await API.logout();
                            window.location.reload();
                        });

                        mobileGroup.appendChild(header);
                        mobileGroup.appendChild(profileLink);
                        mobileGroup.appendChild(logoutLink);

                        mobileContainer.appendChild(mobileGroup);
                    }
                }
            } else {
                // Logged out!
                window.currentUser = null;

                if (navAuthBtn) {
                    navAuthBtn.style.display = '';
                    navAuthBtn.innerText = `Player login`;
                    navAuthBtn.href = '#login';
                    navAuthBtn.style.color = '';
                    const newBtn = navAuthBtn.cloneNode(true);
                    navAuthBtn.replaceWith(newBtn);
                    navAuthBtn = newBtn;
                }

                if (mobileAuthBtn) {
                    mobileAuthBtn.style.display = '';
                    mobileAuthBtn.innerText = `Player login`;
                    mobileAuthBtn.href = '#login';
                    mobileAuthBtn.style.color = '';
                    const newBtn = mobileAuthBtn.cloneNode(true);
                    mobileAuthBtn.replaceWith(newBtn);
                    mobileAuthBtn = newBtn;
                }

                const verifyBanner = document.getElementById('verify-banner');
                if (verifyBanner) verifyBanner.classList.add('d-none');
            }
        } catch (_e) {
            console.error("Session integrity check failed.");
        }
    };

    // Execute the auth loop mapping the initial load.
    window.updateAuthState();
}

document.addEventListener('DOMContentLoaded', () => {
    initGlobalState();
    initNavigation();
    initRouting();
    initGameContext();
    initAuthState();
});
