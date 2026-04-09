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
        // The dashboard is transparent, allowing full-screen map layouts.
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
            document.getElementById('dp-visits-container').innerHTML = "<span style='color:var(--accent-red);'>[ ERROR: No dashpoint ID provided ]</span>";
            return;
        }

        const dpIdLabel = document.getElementById('dp-id-label');
        const dpCoordLabel = document.getElementById('dp-coord-label');
        const visitsContainer = document.getElementById('dp-visits-container');
        const btnLog = document.getElementById('btn-goto-report');

        // The Button Controller logic is executed exclusively post-fetch to allow spatial ownership diffing

        // Poll the backend.
        fetch(`backend/api/dashpoint.php?id=${dpId}`)
            .then(res => res.json())
            .then(json => {
                if (json.status === 'success') {
                    const dp = json.data;
                    if (dpIdLabel) dpIdLabel.innerText = `${dp.id}`;
                    if (dpCoordLabel) dpCoordLabel.innerText = `[ LAT: ${dp.lat.toFixed(5)} | LON: ${dp.lon.toFixed(5)} ]`;

                    // Evaluate Ownership & Authentication dynamically wrapping the Primary Button State
                    if (btnLog) {
                        if (window.currentGameContext && !window.currentGameContext.is_active) {
                            // Immutability: Purely hide actions natively representing the read-only state.
                            btnLog.style.display = 'none';
                        } else {
                            API.checkSession().then(res => {
                                if (res.status === 'success') {
                                    // 1. Scan the Ledger for an exact Username match proving physical ownership
                                    const userOwnedVisit = dp.visits.find(v => v.username === res.username);
                                if (userOwnedVisit) {
                                    btnLog.innerText = "EDIT LOG";
                                    btnLog.style.background = "var(--accent-amber)";
                                    btnLog.style.color = "#000";
                                    btnLog.style.border = "none";
                                    btnLog.addEventListener('click', () => { window.location.hash = `#edit?id=${dp.id}`; });
                                } else {
                                    btnLog.innerText = "LOG VISIT";
                                    btnLog.addEventListener('click', () => { window.location.hash = `#report?id=${dp.id}`; });
                                }
                            } else {
                                // 2. Unauthenticated Identity - Enforce Login Array Flow 
                                btnLog.innerText = "LOGIN TO LOG VISIT";
                                btnLog.style.background = "transparent";
                                btnLog.style.color = "var(--accent-red)";
                                btnLog.style.border = "1px solid var(--accent-red)";
                                btnLog.addEventListener('click', () => { window.location.hash = `#login`; });
                            }
                        });
                        }
                    }

                    // Generate the beautiful HTML5 Ledgers directly from MySQL bounds
                    if (dp.visits.length === 0) {
                        visitsContainer.innerHTML = `<div style="text-align:center; padding:1.5rem; color:var(--text-muted); border:1px solid #333; margin-top:1rem;">ZERO VISITS. <br><br>Dashpoint is unvisited.</div>`;
                    } else {
                        visitsContainer.innerHTML = ''; // Purge "LOADING"

                        dp.visits.forEach((visit, index) => {
                            // Extract standard timestamps cleanly for the CLI UI
                            const d = new Date(visit.reported_time);
                            const tStr = `${d.getFullYear()}.${(d.getMonth() + 1).toString().padStart(2, '0')}.${d.getDate().toString().padStart(2, '0')} @ ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;

                            // Generate a DOM block to separate the rows.
                            const visitDiv = document.createElement('div');
                            visitDiv.style.border = '1px solid var(--text-muted)';
                            visitDiv.style.marginBottom = '1rem';
                            visitDiv.style.padding = '1rem';
                            visitDiv.style.background = 'rgba(0, 0, 0, 0.4)';

                            let html = `
                                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
                                    <span style="font-size:0.9rem; color:var(--accent-amber); font-weight:bold;">${index + 1}. ${window.escapeHTML(visit.username)}</span>
                                    <span style="font-size:0.8rem; color:var(--accent-green); border:1px solid var(--accent-green); padding:2px 6px;">+${visit.score_awarded} PT</span>
                                </div>
                                <div style="color:#888; font-size:0.75rem; margin-bottom:1rem;">> LOG_TIME: ${tStr}</div>
                            `;

                            // Map the newly registered Spatial Temporal Edit constraint natively
                            if (visit.edited_at) {
                                const ed = new Date(visit.edited_at);
                                const edStr = `${ed.getFullYear()}.${(ed.getMonth() + 1).toString().padStart(2, '0')}.${ed.getDate().toString().padStart(2, '0')} @ ${ed.getHours().toString().padStart(2, '0')}:${ed.getMinutes().toString().padStart(2, '0')}`;
                                html += `<div style="color:var(--accent-amber); font-size:0.75rem; margin-bottom:1rem;">> EDITED_AT: ${edStr}</div>`;
                            }

                            // If they provided notes or uploaded physical Photos to GCP, expose the [ VIEW DETAILS ] toggler natively
                            if ((visit.notes && visit.notes.trim() !== '') || (visit.photos && visit.photos.length > 0)) {
                                html += `<button type="button" class="btn btn-secondary" style="width:100%; font-size:0.7rem;" onclick="this.nextElementSibling.style.display = this.nextElementSibling.style.display === 'none' ? 'block' : 'none';">VIEW DETAILS</button>`;
                                html += `<div style="display:none; margin-top:1rem; padding-top:1rem; border-top:1px dashed #444;">`;

                                if (visit.notes) {
                                    html += `<p style="color:#ddd; margin-bottom:1rem; font-style:italic;">"${window.escapeHTML(visit.notes)}"</p>`;
                                }

                                if (visit.photos && visit.photos.length > 0) {
                                    html += `<div style="display:grid; grid-template-columns: 1fr; gap:1rem;">`;
                                    visit.photos.forEach(photo => {
                                        let encodedUrl = encodeURI(photo.url);
                                        let imgHtml = `<img src="${encodedUrl}" class="log-photo" data-dpid="${window.escapeHTML(dp.id)}" data-url="${encodedUrl}" style="width:100%; height:auto; border:1px solid var(--accent-amber); cursor:pointer;" loading="lazy">`;

                                        if (photo.lat !== null && photo.lon !== null && dp.lat !== undefined) {
                                            // Native JS Haversine Distance Mapper cleanly invoking the global SPA utility
                                            const distance = window.calculateDistance(photo.lat, photo.lon, dp.lat, dp.lon);

                                            imgHtml += `<div style="text-align:center; font-size:0.75rem; color:var(--accent-green); margin-top:0.3rem;">[ EXIF GPS: ${photo.lat.toFixed(5)}, ${photo.lon.toFixed(5)} | DISTANCE FROM DASHPOINT: ${distance.toFixed(1)}m ]</div>`;
                                        }

                                        html += `<div>${imgHtml}</div>`;
                                    });
                                    html += `</div>`;
                                }
                                html += `</div>`;
                            } else {
                                html += `<p style="color:#555; font-style:italic;">No details provided.</p>`;
                            }

                            visitDiv.innerHTML = html;

                            // Bind click listeners natively to completely avoid attribute breakouts
                            const photoImgs = visitDiv.querySelectorAll('img.log-photo');
                            photoImgs.forEach(img => {
                                img.addEventListener('click', function() {
                                    if(window.trackEvent) {
                                        window.trackEvent('view_photo', { 
                                            dashpoint_id: this.getAttribute('data-dpid'), 
                                            image_url: this.getAttribute('data-url') 
                                        });
                                    }
                                });
                            });

                            visitsContainer.appendChild(visitDiv);
                        });
                    }
                } else {
                    if (visitsContainer) visitsContainer.innerHTML = `<span style='color:var(--accent-red);'>[-] Error: ${json.message}</span>`;
                }
            })
            .catch(err => {
                console.error(err);
                if (visitsContainer) visitsContainer.innerHTML = `<span style='color:var(--accent-red);'>[-] Network error.</span>`;
            });
    }

    // ==========================================================
    // Controller: LOG A VISIT (#report)
    // ==========================================================
    if (route.startsWith('#report')) {
        const btnGeo = document.getElementById('btn-geolocation');
        const latInput = document.getElementById('input-lat');
        const lonInput = document.getElementById('input-lon');

        const btnAddPhotos = document.getElementById('btn-add-photos');
        const inputPhotos = document.getElementById('input-photos');
        const previewGrid = document.getElementById('photo-preview-grid');
        
        // eslint-disable-next-line no-unused-vars
        let selectedFiles = []; // Track to enforce limit and show previews

        if (btnAddPhotos && inputPhotos) {
            btnAddPhotos.addEventListener('click', () => {
                inputPhotos.click();
            });

            inputPhotos.addEventListener('change', (e) => {
                const files = Array.from(e.target.files);
                if (files.length > 10) {
                    alert("Maximum 10 photos allowed.");
                    // In a DataTransfer object we can filter the files back to 10
                    const dt = new DataTransfer();
                    files.slice(0, 10).forEach(file => dt.items.add(file));
                    inputPhotos.files = dt.files;
                }
                
                // Clear previous previews
                previewGrid.innerHTML = '';
                Array.from(inputPhotos.files).forEach(file => {
                    const img = document.createElement('img');
                    img.src = URL.createObjectURL(file);
                    img.style.width = '100%';
                    img.style.height = '60px';
                    img.style.objectFit = 'cover';
                    img.style.borderRadius = '4px';
                    img.style.border = '1px solid var(--accent-amber)';
                    previewGrid.appendChild(img);
                });
            });
        }

        // If they click map markers, the ID gets injected into the URL ?id=GD...
        // Parse this from the SPA routing hash.
        if (route.includes('?')) {
            const hashParams = new URLSearchParams(route.split('?')[1]);
            const targetId = hashParams.get('id');
            if (targetId) {
                const idInput = document.getElementById('dashpoint_id');
                if (idInput) idInput.value = targetId;
            }
        }

        // HTML5 geolocation binder. Inputs are not globally readonly.
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

                            btnGeo.innerText = "SYNCED";
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

        // Dynamic log character counter.
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
                    feedbackStatus.innerHTML = `<div class="alert alert-error" style="background:#2a0000; border:1px solid var(--accent-red); color:var(--accent-red);">[-] Oops! Log text must be between 1 and 10,000 characters.</div>`;
                    return;
                }

                if (isNaN(userLat) || userLat < -90 || userLat > 90) {
                    feedbackStatus.innerHTML = `<div class="alert alert-error" style="background:#2a0000; border:1px solid var(--accent-red); color:var(--accent-red);">[-] Oops! Latitude must be between -90 and 90 degrees.</div>`;
                    return;
                }
                if (isNaN(userLon) || userLon < -180 || userLon > 180) {
                    feedbackStatus.innerHTML = `<div class="alert alert-error" style="background:#2a0000; border:1px solid var(--accent-red); color:var(--accent-red);">[-] Oops! Longitude must be between -180 and 180 degrees.</div>`;
                    return;
                }

                submitBtn.disabled = true;
                submitBtn.innerText = "Checking distance...";

                try {
                    // 2. Safely Fetch target constraints transparently before throwing Heavy User Photos across the bandwidth
                    const targetRes = await fetch(`backend/api/dashpoint.php?id=${targetId}`);
                    const targetJson = await targetRes.json();

                    if (targetJson.status !== 'success') {
                        feedbackStatus.innerHTML = `<div class="alert alert-error">[-] Error: Could not find that dashpoint.</div>`;
                        submitBtn.disabled = false;
                        submitBtn.innerText = "SUBMIT LOG";
                        return;
                    }

                    const targetLat = targetJson.data.lat;
                    const targetLon = targetJson.data.lon;

                    const distance = window.calculateDistance(userLat, userLon, targetLat, targetLon);

                    // Reject log client-side before photo transfers 
                    if (distance > 100) {
                        feedbackStatus.innerHTML = `<div class="alert alert-error" style="background:#2a0000; border:1px solid var(--accent-red); color:var(--accent-red);">[-] Too far away. You are <strong>${distance.toFixed(1)}m</strong> from the dashpoint. You must be within 100m.</div>`;
                        submitBtn.disabled = false;
                        submitBtn.innerText = "SUBMIT LOG";
                        return;
                    }

                    submitBtn.innerText = "Uploading photo...";

                    // 4. Actuating the standard POST injection seamlessly wrapper wrapping all data safely
                    const formData = new FormData(reportForm);
                    const result = await API.logVisit(formData);

                    if (result.status === 'success') {
                        feedbackStatus.innerHTML = `<div class="alert" style="color:var(--accent-green); border:1px solid var(--accent-green);">[+] Success! We logged your visit at ${result.distance.toFixed(1)}m. You scored ${result.points} points!</div>`;

                        // Capture the target before the form reset.
                        const targetPersistence = document.getElementById('dashpoint_id').value;
                        reportForm.reset();
                        document.getElementById('dashpoint_id').value = targetPersistence;

                        btnGeo.innerText = "SYNC LIVE GPS";
                        btnGeo.style.color = ""; // Reset inline CSS

                        // Trigger a map refresh to implicitly update the dashpoint marker's state and colors
                        if (typeof map !== 'undefined' && map && typeof google !== 'undefined' && google.maps) {
                            google.maps.event.trigger(map, 'idle');
                        }
                    } else {
                        feedbackStatus.innerHTML = `<div class="alert alert-error">[-] Upload rejected: ${result.message}</div>`;
                    }
                } catch (_err) {
                    feedbackStatus.innerHTML = `<div class="alert alert-error">[-] Error: Upload failed.</div>`;
                }

                submitBtn.disabled = false;
                submitBtn.innerText = "SUBMIT LOG";
            });
        }
    }

    // ==========================================================
    // Controller: AUTHENTICATION MODULE (#login)
    // ==========================================================
    if (route.startsWith('#login')) {
        const loginForm = document.getElementById('form-login');
        const signupForm = document.getElementById('form-signup');
        const loginFeedback = document.getElementById('login-feedback');
        const signupFeedback = document.getElementById('signup-feedback');

        const urlArgs = route || '';
        const user = window.currentUser || null;

        // CSS Tab Toggles Native Integration
        const toggleSignup = document.getElementById('toggle-signup');
        const toggleLogin = document.getElementById('toggle-login');
        const toggleForgot = document.getElementById('toggle-forgot');
        const toggleLoginFromForgot = document.getElementById('toggle-login-from-forgot');

        const loginPane = document.getElementById('login-pane');
        const signupPane = document.getElementById('signup-pane');
        const verifyPane = document.getElementById('verify-pane');
        const forgotPane = document.getElementById('forgot-pane');
        const resetPane = document.getElementById('reset-pane');

        // Dynamically parse the exact query parameter mapping if a recovery token exists
        const resetTokenRaw = urlArgs.split('?')[1] || '';
        const rawUrlParams = new URLSearchParams(resetTokenRaw);
        const resetToken = rawUrlParams.get('reset_token');

        // Execute imperative reset pane override physically bypassing standard user states
        if (resetToken && resetPane) {
            if (loginPane) loginPane.style.display = 'none';
            if (signupPane) signupPane.style.display = 'none';
            if (verifyPane) verifyPane.style.display = 'none';
            if (forgotPane) forgotPane.style.display = 'none';
            resetPane.style.display = 'block';
            // Do not return here so standard form hooks (including the reset form) can bind.
        } else {
            // --- DYNAMIC STATE: Fully Authenticated & Verified ---
            if (user && user.is_verified == 1) {
                if (loginPane) loginPane.style.display = 'none';
                if (signupPane) signupPane.style.display = 'none';
                if (verifyPane) verifyPane.style.display = 'none';

                if (urlArgs.includes('verified=true')) {
                    // Dynamically build the Victory overlay physically replacing the bounds
                    const verifiedInject = document.createElement('div');
                    verifiedInject.style.cssText = "border:1px solid var(--accent-green); padding:2.5rem; background:rgba(42, 212, 115, 0.05); text-align:center; margin-top:1rem;";
                    verifiedInject.innerHTML = `
                    <h3 style="color:var(--accent-green); margin-bottom:1rem; border-bottom:1px dashed var(--accent-green); padding-bottom:1rem;">Email confirmed.</h3>
                    <p style="color:var(--text-main); line-height:1.6; font-size:1.1rem;">Welcome to Geodashing!</p>
                    <a href="#home" class="btn btn-primary" style="display:inline-block; margin-top:2rem; font-size:1.2rem; padding:12px 24px;">Return to the map.</a>
                `;
                    document.getElementById('view-login').appendChild(verifiedInject);
                } else {
                    window.location.hash = '#home';
                }
                return;
            }

            if (urlArgs.includes('error=invalid_token') && loginFeedback) {
                loginFeedback.innerHTML = `<div class="alert alert-error" style="background:#2a0000; border:1px solid var(--accent-red); color:var(--accent-red);">[-] Error: Invalid or expired verification link.</div>`;
            }

            // Using double equals protects against weak-typed JSON coercion.
            if (user && user.is_verified == 0 && verifyPane) {
                if (loginPane) loginPane.style.display = 'none';
                if (signupPane) signupPane.style.display = 'none';
                verifyPane.classList.remove('d-none');

                const resendBtn = document.getElementById('resend-verify-btn');
                const logoutBtn = document.getElementById('verify-logout-btn');
                const verifyFeedback = document.getElementById('verify-feedback');

                if (resendBtn) {
                    resendBtn.addEventListener('click', async () => {
                        resendBtn.innerText = "Sending Email...";
                        resendBtn.disabled = true;
                        const resendRes = await API.resendVerification();
                        if (resendRes.status === 'success') {
                            verifyFeedback.innerHTML = `<div class="alert" style="color:var(--accent-green); border:1px solid var(--accent-green);">[+] Success! Email sent successfully. Check your inbox.</div>`;
                            resendBtn.innerText = "Email Sent";
                        } else {
                            verifyFeedback.innerHTML = `<div class="alert alert-error" style="background:#2a0000; border:1px solid var(--accent-red); color:var(--accent-red);">[-] ERROR: ${resendRes.message}</div>`;
                            resendBtn.innerText = "Click here to resend validation email";
                            resendBtn.disabled = false;
                        }
                    });
                }
                if (logoutBtn) {
                    logoutBtn.addEventListener('click', async () => {
                        await API.logout();
                        window.location.reload();
                    });
                }
                return; // Prevent standard forms from attaching if verified
            }
        } // Close the 'resetToken else' conditional.

        // --- STANDARD LOGIN HOOKS ---
        if (toggleSignup && toggleLogin && toggleForgot && toggleLoginFromForgot && loginPane && signupPane && forgotPane) {
            toggleSignup.addEventListener('click', (ev) => {
                ev.preventDefault();
                loginPane.style.display = 'none';
                forgotPane.style.display = 'none';
                signupPane.style.display = 'block';
            });
            toggleLogin.addEventListener('click', (ev) => {
                ev.preventDefault();
                signupPane.style.display = 'none';
                forgotPane.style.display = 'none';
                loginPane.style.display = 'block';
            });
            toggleForgot.addEventListener('click', (ev) => {
                ev.preventDefault();
                loginPane.style.display = 'none';
                signupPane.style.display = 'none';
                forgotPane.style.display = 'block';
            });
            toggleLoginFromForgot.addEventListener('click', (ev) => {
                ev.preventDefault();
                forgotPane.style.display = 'none';
                loginPane.style.display = 'block';
            });
        }

        if (loginForm) {
            loginForm.addEventListener('submit', async (ev) => {
                ev.preventDefault();
                const btn = document.getElementById('btn-submit-login');
                btn.disabled = true;
                btn.innerText = "Logging in...";

                const user = document.getElementById('login-username').value;
                const pass = document.getElementById('login-password').value;

                const res = await API.login(user, pass);
                if (res.status === 'success') {
                    loginFeedback.innerHTML = `<div class="alert" style="color:var(--accent-green); border:1px solid var(--accent-green);">[+] Login Successful.</div>`;
                    if (typeof window.updateAuthState === 'function') window.updateAuthState();

                    // Route unverified users to the verify pane.
                    if (res.is_verified === 0) {
                        setTimeout(() => window.location.reload(), 400);
                    } else {
                        setTimeout(() => window.location.hash = '#home', 800);
                    }
                } else {
                    loginFeedback.innerHTML = `<div class="alert alert-error" style="background:#2a0000; border:1px solid var(--accent-red); color:var(--accent-red);">[-] ERROR: ${res.message}</div>`;
                    btn.disabled = false;
                    btn.innerText = "LOGIN";
                }
            });
        }

        if (signupForm) {
            const signupBtn = document.getElementById('btn-submit-signup');
            const pass1 = document.getElementById('signup-password');
            const pass2 = document.getElementById('signup-password-verify');

            // Dynamically validate matching passwords natively locking the submission button
            const validatePasswords = () => {
                if (pass1.value.length >= 6 && pass1.value === pass2.value) {
                    signupBtn.disabled = false;
                    pass2.style.borderColor = "var(--accent-green)";
                } else {
                    signupBtn.disabled = true;
                    if (pass2.value.length > 0) {
                        pass2.style.borderColor = "var(--accent-red)";
                    } else {
                        pass2.style.borderColor = "var(--text-muted)";
                    }
                }
            };

            if (pass1 && pass2) {
                pass1.addEventListener('input', validatePasswords);
                pass2.addEventListener('input', validatePasswords);
            }

            signupForm.addEventListener('submit', async (ev) => {
                ev.preventDefault();
                signupBtn.disabled = true;
                signupBtn.innerText = "Creating account...";

                const user = document.getElementById('signup-username').value;
                const email = document.getElementById('signup-email').value;
                const pass = pass1.value;

                const res = await API.signup(user, email, pass);
                if (res.status === 'success') {
                    signupFeedback.innerHTML = `<div class="alert" style="color:var(--accent-green); border:1px solid var(--accent-green);">[+] WELCOME: Account created.</div>`;
                    if (typeof window.updateAuthState === 'function') window.updateAuthState();

                    // Route to the new verification pane.
                    setTimeout(() => window.location.reload(), 400);
                } else {
                    signupFeedback.innerHTML = `<div class="alert alert-error" style="background:#2a0000; border:1px solid var(--accent-red); color:var(--accent-red);">[-] ERROR: ${res.message}</div>`;
                    signupBtn.disabled = false;
                    signupBtn.innerText = "CREATE ACCOUNT";
                }
            });
        }

        const formForgot = document.getElementById('form-forgot');
        if (formForgot) {
            formForgot.addEventListener('submit', async (ev) => {
                ev.preventDefault();
                const btn = document.getElementById('btn-submit-forgot');
                const feedback = document.getElementById('forgot-feedback');

                btn.disabled = true;
                btn.innerText = "Sending email";

                const username = document.getElementById('forgot-username').value;
                const res = await API.requestPasswordReset(username);

                if (res.status === 'success') {
                    feedback.innerHTML = `<div class="alert" style="color:var(--accent-green); border:1px solid var(--accent-green);">[+] ${res.message}</div>`;
                    btn.innerText = "Email sent";
                } else {
                    feedback.innerHTML = `<div class="alert alert-error" style="background:#2a0000; border:1px solid var(--accent-red); color:var(--accent-red);">[-] ERROR: ${res.message}</div>`;
                    btn.disabled = false;
                    btn.innerText = "Send email";
                }
            });
        }

        const formReset = document.getElementById('form-reset');
        if (formReset) {
            const resetBtn = document.getElementById('btn-submit-reset');
            const feedback = document.getElementById('reset-feedback');
            const pass1 = document.getElementById('reset-password');
            const pass2 = document.getElementById('reset-password-verify');

            const validateResetPasswords = () => {
                if (pass1.value.length >= 6 && pass1.value === pass2.value) {
                    resetBtn.disabled = false;
                    pass2.style.borderColor = "var(--accent-green)";
                } else {
                    resetBtn.disabled = true;
                    if (pass2.value.length > 0) {
                        pass2.style.borderColor = "var(--accent-red)";
                    } else {
                        pass2.style.borderColor = "var(--text-muted)";
                    }
                }
            };

            if (pass1 && pass2) {
                pass1.addEventListener('input', validateResetPasswords);
                pass2.addEventListener('input', validateResetPasswords);
            }

            formReset.addEventListener('submit', async (ev) => {
                ev.preventDefault();
                resetBtn.disabled = true;
                resetBtn.innerText = "Resetting password...";

                const newPass = pass1.value;
                const res = await API.executePasswordReset(resetToken, newPass);

                if (res.status === 'success') {
                    feedback.innerHTML = `<div class="alert" style="color:var(--accent-green); border:1px solid var(--accent-green);">[+] SUCCESS: ${res.message}</div>`;
                    resetBtn.innerText = "Password reset";
                    setTimeout(() => window.location.assign('#login'), 1500);
                } else {
                    feedback.innerHTML = `<div class="alert alert-error" style="background:#2a0000; border:1px solid var(--accent-red); color:var(--accent-red);">[-] ERROR: ${res.message}</div>`;
                    resetBtn.disabled = false;
                    resetBtn.innerText = "Reset password";
                }
            });
        }
    }

    // ==========================================================
    // Controller: USER PROFILE (#profile)
    // ==========================================================
    if (route.startsWith('#profile')) {
        let profileId = null;
        if (route.includes('?')) {
            const hashParams = new URLSearchParams(route.split('?')[1]);
            profileId = hashParams.get('id');
        }

        const container = document.getElementById('profile-container');
        if (!container) return;

        if (!profileId) {
            container.innerHTML = `<div class="alert alert-error">[-] Profile ID missing.</div>`;
            return;
        }

        API.getProfile(profileId).then(json => {
            if (json.status !== 'success') {
                container.innerHTML = `<div class="alert alert-error">[-] Error loading profile data.</div>`;
                return;
            }

            const data = json.data;
            const u = data.user;
            
            // Calculate total finds client-side from games history array
            let totalFinds = 0;
            if (data.games && data.games.length > 0) {
                totalFinds = data.games.reduce((acc, g) => acc + (g.visits ? g.visits.length : 0), 0);
            }

            let html = `
                <div class="dash-block" style="margin-bottom: 2rem; border-top: 1px dashed var(--accent-green);">
                    <h3 style="color:var(--accent-amber); font-size:1.8rem; margin-bottom:0.5rem; text-transform:uppercase;">${window.escapeHTML(u.username)}</h3>
                    <div style="color:var(--text-muted); font-size:0.9rem; margin-bottom:1rem;">
                        [ JOINED: ${new Date(u.created_at).toLocaleDateString()} ]
                    </div>
                    <div style="display:grid; grid-template-columns:1fr 1fr; gap:1rem; border-top:1px dashed var(--text-muted); padding-top:1rem;">
                        <div><strong style="color:var(--text-main);">TOTAL SCORE:</strong> ${u.lifetime_score} PT</div>
                        <div><strong style="color:var(--text-main);">LIFETIME CLAIMS:</strong> ${totalFinds}</div>
                    </div>
                </div>
            `;

            if (data.games && data.games.length > 0) {
                html += `<h4 style="color:var(--text-main); margin-bottom:1rem; text-transform:uppercase;">Historical Activity</h4>`;
                
                data.games.forEach(game => {
                    html += `
                        <div class="dash-block" style="margin-bottom:1rem; border-left:3px solid var(--accent-amber);">
                            <div style="display:flex; justify-content:space-between; margin-bottom:1rem;">
                                <strong style="color:#ddd;">Game ${game.game_id} 
                                    ${game.game_title ? `- ${window.escapeHTML(game.game_title)}` : ''} 
                                    ${game.is_active ? `<span style="color:var(--accent-amber); font-size:0.8rem; margin-left:0.5rem;">[ACTIVE]</span>` : ''}
                                </strong>
                                <span style="color:var(--accent-green);">${game.game_total_score} PT</span>
                            </div>
                            <div style="font-size:0.9rem; color:var(--text-muted); border-top:1px dashed #333; padding-top:0.5rem;">
                                ${game.game_visits_count} Recorded Logs
                            </div>
                            <div style="margin-top:1rem; display:grid; gap:0.5rem;">
                    `;
                    
                    game.visits.forEach((v, index) => {
                        const logTime = new Date(v.reported_time).toLocaleDateString();
                        html += `
                            <a href="#dashpoint?id=${v.dashpoint_id}" class="nav-link" style="display:block; padding:0.5rem; border:1px solid #333; background:rgba(0,0,0,0.3); border-radius:3px;">
                                <div style="display:flex; justify-content:space-between;">
                                    <span>${index + 1}. ${v.dashpoint_id}</span>
                                    <span style="color:var(--accent-green);">+${v.score_awarded}</span>
                                </div>
                                <div style="font-size:0.75rem; color:#888; margin-top:0.3rem;">[ LOGGED: ${logTime} ]</div>
                            </a>
                        `;
                    });

                    html += `</div></div>`;
                });
            } else {
                html += `<div style="text-align:center; padding:2rem; border:1px dashed #333; color:var(--text-muted);">[ NO GAME HISTORY FOUND ]</div>`;
            }

            container.innerHTML = html;
        }).catch(_err => {
            container.innerHTML = `<div class="alert alert-error">[-] System Offline. Profile unavailable.</div>`;
        });
    }

    // ==========================================================
    // Controller: EDIT A VISIT (#edit)
    // ==========================================================
    if (route.startsWith('#edit')) {
        let dpId = null;
        if (route.includes('?')) {
            const hashParams = new URLSearchParams(route.split('?')[1]);
            dpId = hashParams.get('id');
        }

        if (!dpId) {
            document.getElementById('edit-status').innerHTML = "<div class='alert alert-error'>[-] Could not find the dashpoint.</div>";
            return;
        }

        const editForm = document.getElementById('form-edit');
        const submitBtn = document.getElementById('btn-submit-edit');
        const statusDiv = document.getElementById('edit-status');
        const keptPhotosInput = document.getElementById('edit_kept_photos');
        const existingPhotosContainer = document.getElementById('edit-existing-photos');

        document.getElementById('edit_dashpoint_id').value = dpId;

        // 1. Authenticate and Map the specific Visit dynamically
        API.checkSession().then(auth => {
            if (auth.status !== 'success') {
                if (statusDiv) statusDiv.innerHTML = `<div class='alert alert-error'>[-] AUTHENTICATION FAILED.</div>`;
                return;
            }

            fetch(`backend/api/dashpoint.php?id=${dpId}`)
                .then(res => res.json())
                .then(json => {
                    if (json.status !== 'success') return;

                    const dp = json.data;
                    const userVisit = dp.visits.find(v => v.username === auth.username);

                    if (!userVisit) {
                        statusDiv.innerHTML = `<div class='alert alert-error'>[-] EDIT REJECTED: You do not own a physical log mapped to this exact Dashpoint.</div>`;
                        editForm.style.display = 'none';
                        return;
                    }

                    // 2. Pre-fill the decoupled Interface natively
                    document.getElementById('edit-notes').value = userVisit.notes || '';

                    let keptPhotosArray = [];

                    // 3. Render historical blobs and wrap them in deletion callbacks.
                    if (userVisit.photos && userVisit.photos.length > 0) {
                        existingPhotosContainer.innerHTML = ''; // Pop the generic "None" message

                        userVisit.photos.forEach(photo => {
                            // Extract String uniquely ensuring structural backwards-compatibility
                            const urlStr = typeof photo === 'string' ? photo : photo.url;
                            keptPhotosArray.push(urlStr);

                            const wrap = document.createElement('div');
                            wrap.style.position = 'relative';

                            const img = document.createElement('img');
                            img.src = urlStr;
                            img.style.width = '100%';
                            img.style.border = '1px solid var(--accent-amber)';
                            wrap.appendChild(img);

                            const delBtn = document.createElement('div');
                            delBtn.innerHTML = "&times;";
                            delBtn.style.position = 'absolute';
                            delBtn.style.top = '5px';
                            delBtn.style.right = '5px';
                            delBtn.style.background = 'var(--accent-red)';
                            delBtn.style.color = '#fff';
                            delBtn.style.width = '25px';
                            delBtn.style.height = '25px';
                            delBtn.style.textAlign = 'center';
                            delBtn.style.lineHeight = '25px';
                            delBtn.style.cursor = 'pointer';
                            delBtn.style.fontWeight = 'bold';
                            delBtn.style.borderRadius = '3px';

                            delBtn.onclick = () => {
                                // Purge the URL from the retained struct.
                                keptPhotosArray = keptPhotosArray.filter(u => u !== urlStr);
                                keptPhotosInput.value = JSON.stringify(keptPhotosArray);
                                wrap.remove();

                                if (keptPhotosArray.length === 0) {
                                    existingPhotosContainer.innerHTML = `<p style="color:var(--text-muted); font-size:0.8rem; text-align:center; padding:1rem; border:1px dashed var(--border-color);">[ NO EXISTING MEDIA RETAINED ]</p>`;
                                }
                            };

                            wrap.appendChild(delBtn);
                            existingPhotosContainer.appendChild(wrap);
                        });

                        keptPhotosInput.value = JSON.stringify(keptPhotosArray);
                    }
                });
        });

        // 4. Capture the form submission securely routing to the new Diff endpoint
        if (editForm) {
            editForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                submitBtn.disabled = true;
                submitBtn.innerText = "UPDATING LOG...";

                try {
                    const formData = new FormData(editForm);
                    const result = await API.editVisit(formData);

                    if (result.status === 'success') {
                        statusDiv.innerHTML = `<div class="alert" style="color:var(--accent-green); border:1px solid var(--accent-green);">[+] SYNCHRONIZED: ${result.message}</div>`;
                        submitBtn.innerText = "EDITS SAVED";
                    } else {
                        statusDiv.innerHTML = `<div class="alert alert-error">[-] EDIT REJECTED: ${result.message}</div>`;
                        submitBtn.disabled = false;
                        submitBtn.innerText = "SAVE EDITS";
                    }
                } catch (_err) {
                    statusDiv.innerHTML = `<div class="alert alert-error">[-] System error.</div>`;
                    submitBtn.disabled = false;
                    submitBtn.innerText = "COMMIT REVISION";
                }
            });
        }
    }

    // ==========================================================
    // Controller: GLOBAL LEADERBOARDS (#leaderboard)
    // ==========================================================
    if (route === '#leaderboard') {
        const tbody = document.getElementById('leaderboard-tbody');
        if (tbody) {
            let ldParams = '';
            if (window.currentGameContext && window.currentGameContext.id) {
                ldParams = `?game_id=${window.currentGameContext.id}`;
            }

            // Ping the JSON endpoint directly mapping the arrays
            API.getLeaderboard(ldParams).then(json => {
                if (json.status === 'success') {
                    const data = json.data;

                    if (data.length === 0) {
                        tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; padding:2rem; color:var(--text-muted);">[ NO STATISTICAL DATA PRESENT ]</td></tr>`;
                        return;
                    }

                    // Dynamically render the Glassmorphism Table natively
                    let html = '';
                    data.forEach(row => {
                        let rankStyle = "color:var(--text-muted);";
                        if (row.rank === 1) rankStyle = "color:var(--accent-amber); font-weight:bold;";
                        else if (row.rank === 2) rankStyle = "color:#ccc; font-weight:bold;";
                        else if (row.rank === 3) rankStyle = "color:#b08d55; font-weight:bold;"; // Bronze

                        html += `
                            <tr style="border-bottom:1px solid #222; transition: background 0.2s;">
                                <td style="padding:10px; ${rankStyle}">#${row.rank}</td>
                                <td style="padding:10px; color:var(--text-main); font-family:var(--font-mono);">${window.escapeHTML(row.username)}</td>
                                <td style="padding:10px; color:var(--accent-amber); text-align:right;">${row.total_score}</td>
                                <td style="padding:10px; color:var(--text-muted); text-align:right;">${row.total_finds}</td>
                            </tr>
                        `;
                    });

                    tbody.innerHTML = html;
                } else {
                    tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; padding:2rem; color:var(--accent-red);">[-] Global rankings currently unavailable.</td></tr>`;
                }
            }).catch(_err => {
                tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; padding:2rem; color:var(--accent-red);">[-] SYNC RUPTURED: Network Timeout.</td></tr>`;
            });
        }
    }

    // ==========================================================
    // Controller: STATIC DOCUMENTATION (#about, #how-to, #contact)
    // ==========================================================
    if (['#about', '#how-to', '#contact'].includes(route)) {
        // Custom API querying is strictly unnecessary for entirely static views.
        // `app.js` performs DOM injection via `<main id="app-content">`.
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
        if (btnTeleport) {
            btnTeleport.addEventListener('click', () => {
                const b = getBounds();
                if (isNaN(b.n) || isNaN(b.s) || isNaN(b.e) || isNaN(b.w)) {
                    alert("INVALID MATRIX: Coordinates strictly require decimals.");
                    return;
                }

                const sw = new google.maps.LatLng(b.s, b.w);
                const ne = new google.maps.LatLng(b.n, b.e);
                const googleBounds = new google.maps.LatLngBounds(sw, ne);
                map.fitBounds(googleBounds); // Wraps the map.

                // Return to the home dashboard to display results.
                window.location.hash = '#home';
            });
        }

        // Exporters ping the Backend purely using `backend/api/export.php` triggering raw XML downloads
        const downloadPayload = (format) => {
            const b = getBounds();
            if (isNaN(b.n) || isNaN(b.s) || isNaN(b.e) || isNaN(b.w)) {
                alert("INVALID MATRIX: Coordinates tightly required for regional exports.");
                return;
            }
            // Explicitly ping the Phase 3.5 architecture forcing the browser to physically download the block
            window.location.href = `backend/api/export.php?n=${b.n}&s=${b.s}&e=${b.e}&w=${b.w}&format=${format}`;
        };

        if (btnGPX) btnGPX.addEventListener('click', () => downloadPayload('gpx'));
        if (btnLOC) btnLOC.addEventListener('click', () => downloadPayload('loc'));
    }
});
