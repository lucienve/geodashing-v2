/**
 * Geodashing Global Template Controllers
 *
 * Listens for the Vanilla SPA's `routeLoaded` custom event and dynamically attaches 
 * listeners and API fetches exclusively to the freshly injected DOM nodes.
 */

let activeIntervals = [];

document.addEventListener('routeLoaded', (e) => {
    const route = e.detail.route;
    
    // Purge any lingering Javascript intervals (like the countdown timer) from previous views
    activeIntervals.forEach(clearInterval);
    activeIntervals = [];

    // ==========================================================
    // Controller: HOME DASHBOARD (#home)
    // ==========================================================
    if (route === '#home' || route === '') {
        const timerDisplay = document.getElementById('timer-display');
        const gameIdDisplay = document.getElementById('dash-game-id');
        const liveTicker = document.getElementById('live-ticker');

        // Ping Game State metrics from the backend purely dynamically
        fetch('backend/api/game.php')
            .then(res => res.json())
            .then(json => {
                if (json.status === 'success') {
                    const game = json.data;
                    gameIdDisplay.innerHTML = `<span style="color:var(--accent-green)">[ ACTIVE MISSION: GDx${game.game_id} ]</span>`;
                    
                    const endDate = new Date(game.end_time).getTime();
                    
                    // Boot the Retro-terminal countdown clock cleanly 
                    const timerId = setInterval(() => {
                        const now = new Date().getTime();
                        const distance = endDate - now;

                        if (distance < 0) {
                            clearInterval(timerId);
                            timerDisplay.innerText = "00:00:00:00";
                            timerDisplay.style.color = 'var(--accent-red)';
                            return;
                        }

                        const days = Math.floor(distance / (1000 * 60 * 60 * 24)).toString().padStart(2, '0');
                        const hours = Math.floor((distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60)).toString().padStart(2, '0');
                        const minutes = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60)).toString().padStart(2, '0');
                        const seconds = Math.floor((distance % (1000 * 60)) / 1000).toString().padStart(2, '0');

                        timerDisplay.innerText = `${days}:${hours}:${minutes}:${seconds}`;
                    }, 1000);
                    
                    activeIntervals.push(timerId);
                    
                    // Tiny aesthetic ticker update mapping retro lore!
                    setTimeout(() => {
                        liveTicker.innerHTML += "<br>> SYNC_ESTABLISHED: SATELLITES LOCKED.";
                        liveTicker.scrollTo(0, liveTicker.scrollHeight);
                    }, 800);
                } else {
                    gameIdDisplay.innerHTML = `<span style="color:var(--accent-red)">[ NO ACTIVE MISSIONS ]</span>`;
                }
            })
            .catch(err => {
                console.error("Dashboard Fetch RUPTURED:", err);
                gameIdDisplay.innerHTML = `<span style="color:var(--accent-red)">[ SYSTEM FAULT ]</span>`;
            });
    }

    // ==========================================================
    // Controller: LOG A VISIT (#report)
    // ==========================================================
    if (route.startsWith('#report')) {
        const btnGeo = document.getElementById('btn-geolocation');
        const latInput = document.getElementById('input-lat');
        const lonInput = document.getElementById('input-lon');
        
        // If they click map markers, the ID gets injected into the URL ?id=GD...
        // We parse that securely and drop it into the form statically.
        const urlParams = new URL(window.location.href).searchParams;
        if(urlParams.get('id')) {
            const idInput = document.getElementById('input-id');
            if(idInput) idInput.value = urlParams.get('id');
        }

        // HTML5 Geolocation Binder - Note: Inputs are NOT readonly globally!
        if (btnGeo) {
            btnGeo.addEventListener('click', (ev) => {
                ev.preventDefault();
                btnGeo.innerText = "PULLING GPS...";
                btnGeo.style.color = "var(--accent-amber)";
                
                if (navigator.geolocation) {
                    navigator.geolocation.getCurrentPosition(
                        (position) => {
                            latInput.value = position.coords.latitude.toFixed(6);
                            lonInput.value = position.coords.longitude.toFixed(6);
                            
                            btnGeo.innerText = "COORDINATES LOCKED";
                            btnGeo.style.color = "var(--accent-green)";
                            btnGeo.style.borderColor = "var(--accent-green)";
                        },
                        (error) => {
                            console.error(error);
                            btnGeo.innerText = "GPS CAPTURE FAILED";
                            btnGeo.style.color = "var(--accent-red)";
                        },
                        { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
                    );
                } else {
                    btnGeo.innerText = "BROWSER REJECTED GPS";
                }
            });
        }
        
        // Final Logging Form Submitter trapping the Data matrix natively into api.js
        const reportForm = document.getElementById('form-report');
        if (reportForm) {
            reportForm.addEventListener('submit', async (ev) => {
                ev.preventDefault();
                
                const submitBtn = document.getElementById('btn-submit-report');
                const feedbackStatus = document.getElementById('report-feedback');
                
                submitBtn.disabled = true;
                submitBtn.innerText = "UPLOADING...";
                
                // Natively traps the raw DOM element wrapping all file streams into a payload
                const formData = new FormData(reportForm);
                
                try {
                    // Call out to the wrapper securely built in Phase 4.3!
                    const result = await API.logVisit(formData);
                    
                    if(result.status === 'success') {
                        feedbackStatus.innerHTML = `<div class="alert" style="color:var(--accent-green); border:1px solid var(--accent-green);">[+] LOG_ACCEPTED: Server logged coordinates at ping distance ${result.distance.toFixed(1)}m. You scored ${result.points_awarded} points!</div>`;
                        reportForm.reset();
                        btnGeo.innerText = "PULL CURRENT GPS LOCATION";
                        btnGeo.style.color = ""; // Reset inline CSS
                    } else {
                        // Display error directly in the console HUD
                        feedbackStatus.innerHTML = `<div class="alert alert-error">[-] REJECTED: ${result.message}</div>`;
                    }
                } catch(err) {
                    feedbackStatus.innerHTML = `<div class="alert alert-error">[-] UPLINK RUPTURED: Critical system error.</div>`;
                }
                
                submitBtn.disabled = false;
                submitBtn.innerText = "SUBMIT LOG";
            });
        }
    }

    // ==========================================================
    // Controller: SCANNER EXPORT ROUTINES (#search)
    // ==========================================================
    if (route === '#search') {
        const btnTeleport = document.getElementById('btn-teleport');
        const btnGPX = document.getElementById('btn-export-gpx');
        const btnLOC = document.getElementById('btn-export-loc');
        
        // Dynamically extract bounds from the DOM boxes
        const getBounds = () => ({
            n: parseFloat(document.getElementById('search-n').value),
            s: parseFloat(document.getElementById('search-s').value),
            e: parseFloat(document.getElementById('search-e').value),
            w: parseFloat(document.getElementById('search-w').value)
        });

        // Natively shift the underlying Google Maps engine asynchronously 
        if(btnTeleport) {
            btnTeleport.addEventListener('click', () => {
                const b = getBounds();
                if(isNaN(b.n) || isNaN(b.s) || isNaN(b.e) || isNaN(b.w)) {
                    alert("INVALID MATRIX: Coordinates strictly require decimals.");
                    return;
                }
                
                const sw = new google.maps.LatLng(b.s, b.w);
                const ne = new google.maps.LatLng(b.n, b.e);
                const googleBounds = new google.maps.LatLngBounds(sw, ne);
                map.fitBounds(googleBounds); // Physically wraps the map!
                
                // Jump the UI router back to the Home Dashboard instantly revealing the results!
                window.location.hash = '#home';
            });
        }

        // Exporters ping the Backend purely using `backend/api/export.php` triggering raw XML downloads
        const downloadPayload = (format) => {
            const b = getBounds();
            if(isNaN(b.n) || isNaN(b.s) || isNaN(b.e) || isNaN(b.w)) {
                alert("INVALID MATRIX: Coordinates tightly required for regional exports.");
                return;
            }
            // Explicitly ping the Phase 3.5 architecture forcing the browser to physically download the block
            window.location.href = `backend/api/export.php?n=${b.n}&s=${b.s}&e=${b.e}&w=${b.w}&format=${format}`;
        };

        if(btnGPX) btnGPX.addEventListener('click', () => downloadPayload('gpx'));
        if(btnLOC) btnLOC.addEventListener('click', () => downloadPayload('loc'));
    }
});
