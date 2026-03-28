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
        // The dashboard is now a purely transparent state allowing 100% full-screen map layouts natively!
        // (Game ID is now pinged globally on boot in app.js and injected directly into the header block)
    }

    // ==========================================================
    // Controller: DASHPOINT LEDGER (#dashpoint)
    // ==========================================================
    if (route.startsWith('#dashpoint')) {
        let dpId = null;
        if (route.includes('?')) {
            const hashParams = new URLSearchParams(route.split('?')[1]);
            dpId = hashParams.get('id');
        }

        if (!dpId) {
            document.getElementById('dp-visits-container').innerHTML = "<span style='color:var(--accent-red);'>[ ERROR: NO DASHPOINT ID PROVIDED ]</span>";
            return;
        }

        const dpIdLabel = document.getElementById('dp-id-label');
        const dpCoordLabel = document.getElementById('dp-coord-label');
        const visitsContainer = document.getElementById('dp-visits-container');
        const btnLog = document.getElementById('btn-goto-report');

        // Dynamically shift the URL mapping right back over to the Log forms if they click it!
        if (btnLog) {
            btnLog.addEventListener('click', () => {
                window.location.hash = `#report?id=${dpId}`;
            });
        }

        // Poll the new Phase 5.4 Backend directly!
        fetch(`backend/api/dashpoint.php?id=${dpId}`)
            .then(res => res.json())
            .then(json => {
                if (json.status === 'success') {
                    const dp = json.data;
                    if(dpIdLabel) dpIdLabel.innerText = `${dp.id}`;
                    if(dpCoordLabel) dpCoordLabel.innerText = `[ LAT: ${dp.lat.toFixed(5)} | LON: ${dp.lon.toFixed(5)} ]`;

                    // Generate the beautiful HTML5 Ledgers directly from MySQL bounds
                    if (dp.visits.length === 0) {
                        visitsContainer.innerHTML = `<div style="text-align:center; padding:1.5rem; color:var(--text-muted); border:1px solid #333; margin-top:1rem;">ZERO VISITS. <br><br>Dashpoint is unvisited.</div>`;
                    } else {
                        visitsContainer.innerHTML = ''; // Purge "LOADING"

                        dp.visits.forEach((visit, index) => {
                            // Extract standard timestamps cleanly for the CLI UI
                            const d = new Date(visit.reported_time);
                            const tStr = `${d.getFullYear()}.${(d.getMonth()+1).toString().padStart(2,'0')}.${d.getDate().toString().padStart(2,'0')} @ ${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`;

                            // Generate a pure Javascript DOM block specifically separating the rows safely!
                            const visitDiv = document.createElement('div');
                            visitDiv.style.border = '1px solid var(--text-muted)';
                            visitDiv.style.marginBottom = '1rem';
                            visitDiv.style.padding = '1rem';
                            visitDiv.style.background = 'rgba(0, 0, 0, 0.4)';

                            let html = `
                                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
                                    <span style="font-size:0.9rem; color:var(--accent-amber); font-weight:bold;">${index + 1}. ${visit.username}</span>
                                    <span style="font-size:0.8rem; color:var(--accent-green); border:1px solid var(--accent-green); padding:2px 6px;">+${visit.score_awarded} PT</span>
                                </div>
                                <div style="color:#888; font-size:0.75rem; margin-bottom:1rem;">> LOG_TIME: ${tStr}</div>
                            `;

                            // If they provided notes or uploaded physical Photos to GCP, expose the [ VIEW DETAILS ] toggler natively
                            if ((visit.notes && visit.notes.trim() !== '') || (visit.photos && visit.photos.length > 0)) {
                                html += `<button type="button" class="btn btn-secondary" style="width:100%; font-size:0.7rem;" onclick="this.nextElementSibling.style.display = this.nextElementSibling.style.display === 'none' ? 'block' : 'none';">VIEW DETAILS</button>`;
                                html += `<div style="display:none; margin-top:1rem; padding-top:1rem; border-top:1px dashed #444;">`;
                                
                                if (visit.notes) {
                                    html += `<p style="color:#ddd; margin-bottom:1rem; font-style:italic;">"${visit.notes}"</p>`;
                                }
                                
                                if (visit.photos && visit.photos.length > 0) {
                                    html += `<div style="display:grid; grid-template-columns: 1fr 1fr; gap:0.5rem;">`;
                                    visit.photos.forEach(photoPath => {
                                        // Renders raw GCS URL tokens securely into HTML5 DOM nodes!
                                        html += `<img src="${photoPath}" style="width:100%; height:auto; border:1px solid var(--accent-amber);" loading="lazy">`;
                                    });
                                    html += `</div>`;
                                }
                                html += `</div>`;
                            } else {
                                html += `<p style="color:#555; font-style:italic;">No details provided.</p>`;
                            }

                            visitDiv.innerHTML = html;
                            visitsContainer.appendChild(visitDiv);
                        });
                    }
                } else {
                    if (visitsContainer) visitsContainer.innerHTML = `<span style='color:var(--accent-red);'>[-] ERROR: ${json.message}</span>`;
                }
            })
            .catch(err => {
                console.error(err);
                if (visitsContainer) visitsContainer.innerHTML = `<span style='color:var(--accent-red);'>[-] UPLINK SEVERED.</span>`;
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
        // We parse that securely out of the SPA Routing hash!
        if (route.includes('?')) {
            const hashParams = new URLSearchParams(route.split('?')[1]);
            const targetId = hashParams.get('id');
            if(targetId) {
                const idInput = document.getElementById('dashpoint_id');
                if(idInput) idInput.value = targetId;
            }
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
                            
                            btnGeo.innerText = "[ COORDINATES SYNCED ]";
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
        
        // Dynamic Log Character Counter natively optimizing the UX!
        const logArea = document.getElementById('log-textarea');
        const charCounter = document.getElementById('char-counter');
        if (logArea && charCounter) {
            logArea.addEventListener('input', () => {
                const len = logArea.value.length;
                const remaining = 10000 - len;
                
                charCounter.innerText = `${remaining.toLocaleString()} chars remaining`;
                
                if (remaining <= 50) {
                    charCounter.style.color = "var(--accent-red)";
                    charCounter.style.fontWeight = "bold";
                } else {
                    charCounter.style.color = "var(--accent-amber)";
                    charCounter.style.fontWeight = "normal";
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
                
                // 1. Initial Local Coordinate Validation Matrix natively preventing impossible values
                const userLat = parseFloat(latInput.value);
                const userLon = parseFloat(lonInput.value);
                const targetId = document.getElementById('dashpoint_id').value;
                const logLength = logArea ? logArea.value.length : 0;

                if (logLength === 0 || logLength > 10000) {
                    feedbackStatus.innerHTML = `<div class="alert alert-error" style="background:#2a0000; border:1px solid var(--accent-red); color:var(--accent-red);">[-] LOG REJECTED: Mandatory field observations must be between 1 and 10,000 characters.</div>`;
                    return;
                }

                if (isNaN(userLat) || userLat < -90 || userLat > 90) {
                    feedbackStatus.innerHTML = `<div class="alert alert-error" style="background:#2a0000; border:1px solid var(--accent-red); color:var(--accent-red);">[-] GEOPHYSICAL REJECTION: Latitude strictly bounded between -90 and 90 degrees.</div>`;
                    return;
                }
                if (isNaN(userLon) || userLon < -180 || userLon > 180) {
                    feedbackStatus.innerHTML = `<div class="alert alert-error" style="background:#2a0000; border:1px solid var(--accent-red); color:var(--accent-red);">[-] GEOPHYSICAL REJECTION: Longitude strictly bounded between -180 and 180 degrees.</div>`;
                    return;
                }
                
                submitBtn.disabled = true;
                submitBtn.innerText = "CALCULATING PROXIMITY...";
                
                try {
                    // 2. Safely Fetch target constraints transparently before throwing Heavy User Photos across the bandwidth
                    const targetRes = await fetch(`backend/api/dashpoint.php?id=${targetId}`);
                    const targetJson = await targetRes.json();
                    
                    if (targetJson.status !== 'success') {
                        feedbackStatus.innerHTML = `<div class="alert alert-error">[-] TARGET CORRUPTION: System could not identify target node bounds.</div>`;
                        submitBtn.disabled = false;
                        submitBtn.innerText = "SUBMIT LOG";
                        return;
                    }

                    const targetLat = targetJson.data.lat;
                    const targetLon = targetJson.data.lon;

                    // 3. Mathematical Haversine Proximity Core natively checking the 100m limits dynamically
                    const R = 6371e3; // Earth radius strictly modeled in meters
                    const rad = Math.PI / 180;
                    const phi1 = userLat * rad;
                    const phi2 = targetLat * rad;
                    const deltaPhi = (targetLat - userLat) * rad;
                    const deltaLambda = (targetLon - userLon) * rad;

                    const a = Math.sin(deltaPhi/2) * Math.sin(deltaPhi/2) +
                              Math.cos(phi1) * Math.cos(phi2) *
                              Math.sin(deltaLambda/2) * Math.sin(deltaLambda/2);
                    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
                    const distance = R * c; 

                    // Reject log client-side before massive bandwidth photo transfers commence
                    if (distance > 100) {
                        feedbackStatus.innerHTML = `<div class="alert alert-error" style="background:#2a0000; border:1px solid var(--accent-red); color:var(--accent-red);">[-] PROXIMITY ALERT: Out of bounds. You are <strong>${distance.toFixed(1)}m</strong> from the target radius. Submissions strictly require &le; 100m.</div>`;
                        submitBtn.disabled = false;
                        submitBtn.innerText = "SUBMIT LOG";
                        return;
                    }

                    submitBtn.innerText = "UPLOADING PAYLOAD...";
                    
                    // 4. Actuating the standard POST injection seamlessly wrapper wrapping all data safely
                    const formData = new FormData(reportForm);
                    const result = await API.logVisit(formData);
                    
                    if(result.status === 'success') {
                        feedbackStatus.innerHTML = `<div class="alert" style="color:var(--accent-green); border:1px solid var(--accent-green);">[+] LOG_ACCEPTED: Server logged coordinates at strictly ${result.distance.toFixed(1)}m. You scored ${result.points_awarded} points!</div>`;
                        reportForm.reset();
                        btnGeo.innerText = "[ SYNC LIVE GPS ]";
                        btnGeo.style.color = ""; // Reset inline CSS
                    } else {
                        feedbackStatus.innerHTML = `<div class="alert alert-error">[-] UPLOAD REJECTED: ${result.message}</div>`;
                    }
                } catch(err) {
                    feedbackStatus.innerHTML = `<div class="alert alert-error">[-] UPLINK RUPTURED: Critical system upload execution error natively crashed.</div>`;
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
