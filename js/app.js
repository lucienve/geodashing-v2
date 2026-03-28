/**
 * Geodashing Vanilla SPA Router Engine
 * 
 * Intercepts completely native browser URL hashes (e.g. domain.com/#login) 
 * intercepting standard navigation and transparently loading HTML chunks over the map dynamically.
 */

document.addEventListener('DOMContentLoaded', () => {
    // 1. Explicit Routing Logic Dictionary
    const routes = {
        '': 'templates/dashboard.html',
        '#home': 'templates/dashboard.html',
        '#login': 'templates/login.html',
        '#report': 'templates/report.html',
        '#search': 'templates/search.html',
        '#leaderboard': 'templates/leaderboard.html'
    };

    const contentDiv = document.getElementById('app-content');
    const navLinks = document.querySelectorAll('.nav-link');

    // 2. Bounding the SPA state natively
    async function loadRoute() {
        const hash = window.location.hash || '#home';
        const templatePath = routes[hash];

        // Ensure active Nav items get highlighted aesthetically
        navLinks.forEach(link => {
            link.classList.remove('active');
            if (link.getAttribute('href') === hash) {
                link.classList.add('active');
            }
        });

        if (!templatePath) {
            contentDiv.innerHTML = '<div class="template-view"><h2>404 ERROR</h2><p class="data-input" style="color:var(--accent-red)">System route physically unmapped.</p></div>';
            return;
        }

        try {
            // Smoothly collapse the current UI out preventing janky HTML resets
            contentDiv.style.opacity = '0.3';
            
            const response = await fetch(templatePath);
            if (!response.ok) throw new Error("Template layout missing continuously.");
            
            const html = await response.text();
            
            setTimeout(() => {
                contentDiv.innerHTML = html;
                contentDiv.style.opacity = '1';
                
                // CRITICAL: Since we just dumped raw HTML into the DOM natively, 
                // any JS listeners tied to buttons inside it must be re-bound!
                // We fire a custom event telling `api.js` to wake up.
                document.dispatchEvent(new CustomEvent('routeLoaded', { detail: { route: hash } }));
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
});
