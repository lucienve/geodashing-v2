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
window.calculateDistance = function(lat1, lon1, lat2, lon2) {
    const r = 6371e3; // Earth radius in meters
    const rad = Math.PI / 180;
    const phi1 = lat1 * rad;
    const phi2 = lat2 * rad;
    const deltaPhi = (lat2 - lat1) * rad;
    const deltaLambda = (lon2 - lon1) * rad;

    const a = Math.sin(deltaPhi/2) * Math.sin(deltaPhi/2) +
              Math.cos(phi1) * Math.cos(phi2) *
              Math.sin(deltaLambda/2) * Math.sin(deltaLambda/2);
              
    return r * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
};

document.addEventListener('DOMContentLoaded', () => {
    // 1. Explicit Routing Logic Dictionary
    const routes = {
        '': null,
        '#home': null,
        '#dashpoint': 'templates/dashpoint.html',
        '#login': 'templates/login.html',
        '#report': 'templates/report.html',
        '#edit': 'templates/edit.html',
        '#search': 'templates/search.html',
        '#leaderboard': 'templates/leaderboard.html'
    };

    const contentDiv = document.getElementById('app-content');
    const navLinks = document.querySelectorAll('.nav-link');

    // 2. Bounding the SPA state natively
    async function loadRoute() {
        const fullHash = window.location.hash || '#home';
        
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
            contentDiv.innerHTML = '<div class="template-view"><h2>404 ERROR</h2><p class="data-input" style="color:var(--accent-red)">System route physically unmapped.</p></div>';
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
            console.error("Router Fatal Crash: ", err);
            contentDiv.innerHTML = '<div class="template-view"><h2>CONNECTION RUPTURE</h2><p class="data-input" style="color:var(--accent-red)">Failed allocating interface layer blocks across network bounds.</p></div>';
            contentDiv.style.opacity = '1';
        }
    }

    // 3. Native History API bindings (so the Phone's 'Back' button physically works)
    window.addEventListener('hashchange', loadRoute);
    
    // Initial Boot mapping
    loadRoute();

    // 4. One-time Global Data Boot: Pings the active game parameters explicitly into the Header Navigation Bar
    fetch('backend/api/game.php')
        .then(res => res.json())
        .then(json => {
            if (json.status === 'success') {
                const headerGameId = document.getElementById('header-game-id');
                if (headerGameId) {
                    headerGameId.innerText = `[ GAME ${json.data.game_id} ]`;
                }
            }
        })
        .catch(err => console.error("Could not fetch active GDx game strictly for visual banner."));

    // 5. Native Javascript Session Bootstrapper dynamically driving the Nav Auth state securely
    window.updateAuthState = async function() {
        const authBtn = document.getElementById('nav-auth-btn');
        const fab = document.getElementById('fab-report');
        
        try {
            const res = await API.checkSession();
            if (res.status === 'success') {
                authBtn.innerText = `LOGOUT [${res.username}]`;
                authBtn.href = '#';
                
                // Natively detaching previous listeners to prevent stack duplications
                const newBtn = authBtn.cloneNode(true);
                authBtn.replaceWith(newBtn);
                
                newBtn.addEventListener('click', async (e) => {
                    e.preventDefault();
                    await API.logout();
                    window.location.reload(); // Physical purge resets the SPA safely
                });

                if (fab) fab.classList.remove('d-none');
            } else {
                authBtn.innerText = `Player login`;
                authBtn.href = '#login';
                
                const newBtn = authBtn.cloneNode(true);
                authBtn.replaceWith(newBtn);
                
                if (fab) fab.classList.add('d-none');
            }
        } catch(e) {
            console.error("Session integrity check failed.");
        }
    };

    // Execute the Auth loop instantly mapping the initial load!
    window.updateAuthState();
});
