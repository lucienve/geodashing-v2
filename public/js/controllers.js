/**
 * Geodashing Global Template Controllers
 *
 * Listens for the Vanilla SPA's `routeLoaded` custom event and dynamically attaches 
 * listeners and API fetches exclusively to the freshly injected DOM nodes.
 */

let activeIntervals = [];

/**
 * Opens a glassmorphic modal to view the image, show EXIF details, and write a caption.
 */
function openCaptionModal(imgSrc, initialCaption, onSave) {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.id = 'caption-modal-overlay';

    const content = document.createElement('div');
    content.className = 'modal-content caption-modal-content';

    const closeBtn = document.createElement('span');
    closeBtn.className = 'modal-close';
    closeBtn.innerHTML = '&times;';
    const closeModal = () => {
        overlay.remove();
    };
    closeBtn.addEventListener('click', closeModal);
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeModal();
    });

    content.innerHTML = `
        <h3 class="caption-modal-title">
            Photo Caption
        </h3>
        <div class="caption-modal-img-wrap">
            <img src="${imgSrc}" class="caption-modal-img">
        </div>
        <div class="form-group caption-modal-group">
            <label for="modal-caption-text" class="caption-modal-label">
                Caption (Max 200 chars)
            </label>
            <textarea id="modal-caption-text" class="data-input caption-textarea" maxlength="200" placeholder="Describe what you saw here..."></textarea>
            <div id="modal-char-counter" class="caption-modal-counter">200 chars remaining</div>
        </div>
        <button type="button" class="btn btn-primary caption-modal-save-btn" id="btn-save-caption">Save Caption</button>
    `;

    content.insertBefore(closeBtn, content.firstChild);
    overlay.appendChild(content);
    document.body.appendChild(overlay);

    const textarea = document.getElementById('modal-caption-text');
    if (textarea) {
        textarea.value = initialCaption || '';
        textarea.focus();
        
        const updateCounter = () => {
            const len = textarea.value.length;
            const remaining = 200 - len;
            const counter = document.getElementById('modal-char-counter');
            if (counter) {
                counter.innerText = `${remaining} chars remaining`;
                counter.classList.toggle('warning', remaining <= 10);
            }
        };
        textarea.addEventListener('input', updateCounter);
        updateCounter();
    }

    const saveBtn = document.getElementById('btn-save-caption');
    if (saveBtn) {
        saveBtn.addEventListener('click', () => {
            const captionValue = textarea ? textarea.value.trim() : '';
            onSave(captionValue);
            closeModal();
        });
    }
}

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
        fetch(`api/dashpoint.php?id=${dpId}`)
            .then(res => res.json())
            .then(json => {
                if (json.status === 'success') {
                    const dp = json.data;

                    // Switch global context if necessary to ensure map rendering aligns with the dashpoint's game
                    if (window.currentGameContext && dp.game_id && window.currentGameContext.id !== dp.game_id) {
                        window.currentGameContext.id = parseInt(dp.game_id);
                        const gameSelector = document.getElementById('game-selector');
                        if (gameSelector) {
                            gameSelector.value = dp.game_id;
                            const selOpt = gameSelector.options[gameSelector.selectedIndex];
                            if (selOpt) {
                                window.currentGameContext.is_active = selOpt.dataset.isActive == '1';
                                window.currentGameContext.title = selOpt.dataset.title;
                                window.currentGameContext.monthYear = selOpt.dataset.monthYear;
                            }
                        }
                    }

                    if (dpIdLabel) dpIdLabel.innerText = `${dp.id}`;
                    if (dpCoordLabel) dpCoordLabel.innerText = `[ LAT: ${dp.lat.toFixed(5)} | LON: ${dp.lon.toFixed(5)} ]`;

                    // Recenter the map on the loaded dashpoint and set zoom to city-level
                    if (typeof map !== 'undefined' && map && typeof google !== 'undefined' && google.maps) {
                        map.setCenter({ lat: parseFloat(dp.lat), lng: parseFloat(dp.lon) });
                        map.setZoom(10);
                    }

                    // Evaluate Ownership & Authentication dynamically wrapping the Primary Button State
                    if (btnLog) {
                        if (window.currentGameContext && !window.currentGameContext.is_active) {
                            // Hide actions representing the read-only state.
                            btnLog.style.display = 'none';
                        } else {
                            API.checkSession().then(res => {
                                if (res.status === 'success') {
                                    // 1. Scan the Ledger for an exact Username match proving log ownership
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

                            const isAttempt = visit.is_attempt == 1 || visit.is_attempt === true;
                            const titleColor = isAttempt ? '#888' : 'var(--accent-amber)';
                            const scoreLabel = isAttempt ? 'ATTEMPT' : `+${visit.score_awarded} PT`;
                            const scoreColor = isAttempt ? '#888' : 'var(--accent-green)';
                            const scoreBorder = isAttempt ? '1px solid #888' : '1px solid var(--accent-green)';

                            let html = `
                                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem; opacity:${isAttempt ? '0.7' : '1'};">
                                    <span style="font-size:0.9rem; color:${titleColor}; font-weight:bold;">${index + 1}. ${window.escapeHTML(visit.username)}</span>
                                    <span style="font-size:0.8rem; color:${scoreColor}; border:${scoreBorder}; padding:2px 6px;">${scoreLabel}</span>
                                </div>
                                <div style="color:#888; font-size:0.75rem; margin-bottom:1rem;">> LOG_TIME: ${tStr}</div>
                            `;

                            // Map the newly registered Spatial Temporal Edit constraint
                            if (visit.edited_at) {
                                const ed = new Date(visit.edited_at);
                                const edStr = `${ed.getFullYear()}.${(ed.getMonth() + 1).toString().padStart(2, '0')}.${ed.getDate().toString().padStart(2, '0')} @ ${ed.getHours().toString().padStart(2, '0')}:${ed.getMinutes().toString().padStart(2, '0')}`;
                                html += `<div style="color:var(--accent-amber); font-size:0.75rem; margin-bottom:1rem;">> EDITED_AT: ${edStr}</div>`;
                            }

                            // We always show the VIEW DETAILS toggler to display the reported coordinates and distance
                            html += `<button type="button" class="btn btn-secondary btn-toggle-details" style="width:100%; font-size:0.7rem;">VIEW DETAILS</button>`;
                            html += `<div style="display:none; margin-top:1rem; padding-top:1rem; border-top:1px dashed #444;">`;

                            if (visit.reported_lat !== undefined && visit.reported_lon !== undefined && visit.distance_meters !== undefined) {
                                html += `<div style="color:var(--text-main); font-size:0.8rem; margin-bottom:1rem;">> REPORTED LOCATION: ${parseFloat(visit.reported_lat).toFixed(5)}, ${parseFloat(visit.reported_lon).toFixed(5)}</div>`;
                                html += `<div style="color:var(--text-main); font-size:0.8rem; margin-bottom:1rem;">> DISTANCE FROM DASHPOINT: ${visit.distance_meters}m</div>`;
                            }

                            if (visit.notes && visit.notes.trim() !== '') {
                                html += `<p style="color:#ddd; margin-bottom:1rem; font-style:italic;">"${window.escapeHTML(visit.notes)}"</p>`;
                            }

                            if (visit.photos && visit.photos.length > 0) {
                                html += `<div style="display:grid; grid-template-columns: 1fr; gap:1rem;">`;
                                visit.photos.forEach(photo => {
                                    let encodedUrl = encodeURI(photo.url);
                                    let thumbUrl = encodeURI(photo.thumb_url);
                                    let imgHtml = `<img src="${thumbUrl}" class="log-photo" data-dpid="${window.escapeHTML(dp.id)}" data-url="${encodedUrl}" style="width:100%; height:auto; border:1px solid var(--accent-amber); cursor:pointer;" loading="lazy">`;

                                    if (photo.lat !== null && photo.lon !== null && dp.lat !== undefined) {
                                        // Native JS Haversine Distance Mapper cleanly invoking the global SPA utility
                                        const distance = window.calculateDistance(photo.lat, photo.lon, dp.lat, dp.lon);

                                        imgHtml += `<div style="text-align:center; font-size:0.75rem; color:var(--accent-green); margin-top:0.3rem;">[ EXIF GPS: ${photo.lat.toFixed(5)}, ${photo.lon.toFixed(5)} | DISTANCE FROM DASHPOINT: ${distance.toFixed(1)}m ]</div>`;
                                    }

                                    let captionHtml = '';
                                    if (photo.caption && photo.caption.trim() !== '') {
                                        captionHtml = `<div class="photo-caption-text">"${window.escapeHTML(photo.caption)}"</div>`;
                                    }

                                    html += `<div style="margin-bottom: 0.5rem;">${imgHtml}${captionHtml}</div>`;
                                });
                                html += `</div>`;
                            }
                            html += `</div>`;

                            visitDiv.innerHTML = html;

                            // Bind click listeners to completely avoid attribute breakouts
                            const photoImgs = visitDiv.querySelectorAll('img.log-photo');
                            photoImgs.forEach(img => {
                                img.addEventListener('click', function () {
                                    if (window.trackEvent) {
                                        window.trackEvent('view_photo', {
                                            dashpoint_id: this.getAttribute('data-dpid'),
                                            image_url: this.getAttribute('data-url')
                                        });
                                    }
                                    window.open(this.getAttribute('data-url'), '_blank');
                                });
                            });

                            const toggleBtns = visitDiv.querySelectorAll('button.btn-toggle-details');
                            toggleBtns.forEach(btn => {
                                btn.addEventListener('click', function () {
                                    const nextEl = this.nextElementSibling;
                                    if (nextEl) {
                                        const isHidden = nextEl.style.display === 'none';
                                        nextEl.style.display = isHidden ? 'block' : 'none';
                                        this.innerText = isHidden ? 'HIDE DETAILS' : 'VIEW DETAILS';
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

        // Dynamically enable numeric/decimal input modes on non-iOS devices
        // iOS does not allow the minus sign on the decimal keypad, so it falls back to text.
        const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
        if (!isIOS) {
            if (latInput) latInput.setAttribute('inputmode', 'decimal');
            if (lonInput) lonInput.setAttribute('inputmode', 'decimal');
        }

        const btnAddPhotos = document.getElementById('btn-add-photos');
        const inputPhotos = document.getElementById('input-photos');
        const previewGrid = document.getElementById('photo-preview-grid');

        let currentPhotoQueue = new DataTransfer();

        let photoCaptions = [];

        const renderPhotoGrid = () => {
            if (!previewGrid) return;
            previewGrid.innerHTML = '';
            Array.from(currentPhotoQueue.files).forEach((file, index) => {
                const wrapper = document.createElement('div');
                wrapper.classList.add('photo-preview-wrapper');
                wrapper.draggable = true;
                wrapper.dataset.index = index;

                const img = document.createElement('img');
                img.src = URL.createObjectURL(file);
                img.classList.add('photo-preview-item');

                const deleteBtn = document.createElement('button');
                deleteBtn.type = 'button';
                deleteBtn.classList.add('photo-delete-btn');
                deleteBtn.innerHTML = '&times;';
                deleteBtn.addEventListener('click', (ev) => {
                    ev.preventDefault();
                    ev.stopPropagation();
                    const newDt = new DataTransfer();
                    const newCaptions = [];
                    Array.from(currentPhotoQueue.files).forEach((f, i) => {
                        if (i !== index) {
                            newDt.items.add(f);
                            newCaptions.push(photoCaptions[i]);
                        }
                    });
                    currentPhotoQueue = newDt;
                    photoCaptions = newCaptions;
                    if (inputPhotos) inputPhotos.files = currentPhotoQueue.files;
                    renderPhotoGrid();
                });

                // Tap to add caption
                wrapper.addEventListener('click', (e) => {
                    if (e.target === deleteBtn) return;
                    const imgSrc = URL.createObjectURL(file);
                    openCaptionModal(imgSrc, photoCaptions[index], (newCaption) => {
                        photoCaptions[index] = newCaption;
                        renderPhotoGrid();
                    });
                });

                const badge = document.createElement('div');
                badge.className = 'photo-caption-badge';
                const hasCaption = photoCaptions[index] && photoCaptions[index].trim() !== '';
                if (hasCaption) {
                    badge.classList.add('has-caption');
                    badge.innerText = '💬 CAPTIONED';
                } else {
                    badge.innerText = '➕ ADD CAPTION';
                }
                wrapper.appendChild(badge);

                // Drag and Drop implementation
                wrapper.addEventListener('dragstart', (ev) => {
                    ev.dataTransfer.effectAllowed = 'move';
                    ev.dataTransfer.setData('text/plain', index);
                    setTimeout(() => wrapper.style.opacity = '0.5', 0);
                });

                wrapper.addEventListener('dragend', () => {
                    wrapper.style.opacity = '1';
                });

                wrapper.addEventListener('dragover', (ev) => {
                    ev.preventDefault();
                    ev.dataTransfer.dropEffect = 'move';
                    wrapper.classList.add('photo-drag-over');
                });

                wrapper.addEventListener('dragleave', () => {
                    wrapper.classList.remove('photo-drag-over');
                });

                wrapper.addEventListener('drop', (ev) => {
                    ev.preventDefault();
                    wrapper.classList.remove('photo-drag-over');
                    const sourceIndex = parseInt(ev.dataTransfer.getData('text/plain'), 10);
                    const targetIndex = index;

                    if (sourceIndex !== targetIndex && !isNaN(sourceIndex)) {
                        const filesArray = Array.from(currentPhotoQueue.files);
                        const [movedFile] = filesArray.splice(sourceIndex, 1);
                        filesArray.splice(targetIndex, 0, movedFile);

                        const [movedCaption] = photoCaptions.splice(sourceIndex, 1);
                        photoCaptions.splice(targetIndex, 0, movedCaption);

                        const newDt = new DataTransfer();
                        filesArray.forEach(f => newDt.items.add(f));
                        currentPhotoQueue = newDt;
                        if (inputPhotos) inputPhotos.files = currentPhotoQueue.files;
                        renderPhotoGrid();
                    }
                });

                wrapper.appendChild(img);
                wrapper.appendChild(deleteBtn);
                previewGrid.appendChild(wrapper);
            });
        };

        if (btnAddPhotos && inputPhotos) {
            btnAddPhotos.addEventListener('click', () => {
                inputPhotos.click();
            });

            inputPhotos.addEventListener('change', (e) => {
                const newFiles = Array.from(e.target.files);
                let exceeded = false;

                newFiles.forEach(file => {
                    if (currentPhotoQueue.files.length < 10) {
                        currentPhotoQueue.items.add(file);
                        photoCaptions.push('');
                    } else {
                        exceeded = true;
                    }
                });

                if (exceeded) {
                    alert("Maximum 10 photos allowed.");
                }

                let totalSize = 0;
                Array.from(currentPhotoQueue.files).forEach(file => {
                    totalSize += file.size;
                });
                const limitBytes = window.postSizeBytes || (25 * 1024 * 1024);
                if (totalSize > limitBytes) {
                    alert(`Warning: The total size of selected photos (${(totalSize / 1024 / 1024).toFixed(1)}MB) exceeds the ${window.postMaxSize || '25M'} server upload limit. Please select fewer or smaller images.`);
                }

                inputPhotos.files = currentPhotoQueue.files;
                renderPhotoGrid();
            });
        }

        // Add sanitization listeners to coordinates
        const sanitizeCoordinate = function () {
            // Convert typographical dashes/minus signs to standard hyphen
            let val = this.value.replace(/[\u2013\u2014\u2212]/g, '-');
            val = val.replace(/[^0-9.-]/g, '');
            if (this.value !== val) {
                this.value = val;
            }
        };

        if (latInput) {
            latInput.addEventListener('blur', sanitizeCoordinate);
        }
        if (lonInput) {
            lonInput.addEventListener('blur', sanitizeCoordinate);
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
                btnGeo.classList.add('btn-loading');

                const geoTarget = window.mockGeolocation || navigator.geolocation;
                if (geoTarget) {
                    geoTarget.getCurrentPosition(
                        (position) => {
                            latInput.value = position.coords.latitude.toFixed(6);
                            lonInput.value = position.coords.longitude.toFixed(6);

                            btnGeo.classList.remove('btn-loading');
                            btnGeo.innerText = "SYNCED";
                            btnGeo.style.color = "var(--accent-green)";
                            btnGeo.style.borderColor = "var(--accent-green)";
                        },
                        (error) => {
                            console.error(error);
                            btnGeo.classList.remove('btn-loading');
                            btnGeo.innerText = "GPS CAPTURE FAILED";
                            btnGeo.style.color = "var(--accent-red)";
                        },
                        { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
                    );
                } else {
                    btnGeo.classList.remove('btn-loading');
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

        // Final Logging Form Submitter trapping the Data matrix into api.js
        const reportForm = document.getElementById('form-report');
        if (reportForm) {
            reportForm.addEventListener('submit', async (ev) => {
                ev.preventDefault();

                const submitBtn = document.getElementById('btn-submit-report');
                const feedbackStatus = document.getElementById('report-feedback');

                // 1. Initial Local Coordinate Validation Matrix preventing impossible values
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
                    const targetRes = await fetch(`api/dashpoint.php?id=${targetId}`);
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

                    const isAttempt = document.getElementById('input-is-attempt').checked;

                    // Reject log client-side before photo transfers if not an attempt
                    if (!isAttempt && distance > 100) {
                        feedbackStatus.innerHTML = `<div class="alert alert-error" style="background:#2a0000; border:1px solid var(--accent-red); color:var(--accent-red);">[-] Too far away. You are <strong>${distance.toFixed(1)}m</strong> from the dashpoint. You must be within 100m.</div>`;
                        submitBtn.disabled = false;
                        submitBtn.innerText = "SUBMIT LOG";
                        return;
                    }

                    // Check file size client-side before sending
                    let totalSize = 0;
                    if (inputPhotos && inputPhotos.files) {
                        Array.from(inputPhotos.files).forEach(file => {
                            totalSize += file.size;
                        });
                    }
                    const limitBytes = window.postSizeBytes || (25 * 1024 * 1024);
                    if (totalSize > limitBytes) {
                        feedbackStatus.innerHTML = `<div class="alert alert-error" style="background:#2a0000; border:1px solid var(--accent-red); color:var(--accent-red);">[-] Upload rejected: Total photo size (${(totalSize / 1024 / 1024).toFixed(1)}MB) exceeds the ${window.postMaxSize || '25M'} server limit. Please reduce image resolution or attach fewer photos.</div>`;
                        submitBtn.disabled = false;
                        submitBtn.innerText = "SUBMIT LOG";
                        return;
                    }

                    submitBtn.innerText = "Uploading photo...";

                    // 4. Actuating the standard POST request wrapper wrapping all data safely
                    const formData = new FormData(reportForm);
                    photoCaptions.forEach(c => {
                        formData.append('captions[]', c);
                    });
                    const result = await API.logVisit(formData);

                    if (result.status === 'success') {
                        if (isAttempt) {
                            feedbackStatus.innerHTML = `<div class="alert" style="color:var(--accent-amber); border:1px solid var(--accent-amber);">[+] Attempt logged. We saved your attempt at ${userLat.toFixed(5)}, ${userLon.toFixed(5)} (${result.distance.toFixed(1)}m away). You earned 0 points.</div>`;
                        } else {
                            feedbackStatus.innerHTML = `<div class="alert" style="color:var(--accent-green); border:1px solid var(--accent-green);">[+] Success! We logged your visit at ${userLat.toFixed(5)}, ${userLon.toFixed(5)} at a distance of ${result.distance.toFixed(1)}m from the point. You scored ${result.points} points!</div>`;
                        }

                        // Capture the target before the form reset.
                        const targetPersistence = document.getElementById('dashpoint_id').value;
                        reportForm.reset();
                        document.getElementById('dashpoint_id').value = targetPersistence;
                        currentPhotoQueue = new DataTransfer();
                        photoCaptions = [];
                        renderPhotoGrid();

                        btnGeo.innerText = "SYNC LIVE GPS";
                        btnGeo.style.color = ""; // Reset inline CSS

                        // Hide the form to make the success message clearly visible
                        reportForm.style.display = 'none';

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

        // Execute imperative reset pane override bypassing standard user states
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
                    // Dynamically build the Victory overlay replacing the bounds
                    const verifiedInject = document.createElement('div');
                    verifiedInject.className = 'verified-success-box';

                    let mailtoSection = '';
                    if (urlArgs.includes('subscribe=1')) {
                        mailtoSection = `
                        <div class="verify-subscribe-box">
                            <h4>Subscribe to Mailing List</h4>
                            <p>
                                You requested to join the <strong>dashers@geodashing.org</strong> mailing list. Stay active in the community with game announcements, game results, player discussions, and real-time logs. Click below to launch your email client, then hit send to request to join. You can unsubscribe at any time.
                            </p>
                            <a href="mailto:dashers+subscribe@geodashing.org?subject=Subscribe&body=Please%20add%20me%20to%20the%20dashers%40geodashing.org%20mailing%20list." class="btn btn-secondary btn-send-subscribe">
                                ✉ SEND SUBSCRIPTION EMAIL
                            </a>
                            <p class="verify-subscribe-fallback">
                                <em>Trouble with the button?</em> Manually send a blank email to <strong style="color:var(--text-main);">dashers+subscribe@geodashing.org</strong> from your registered email address.
                            </p>
                        </div>
                        `;
                    }

                    verifiedInject.innerHTML = `
                    <h3>Email confirmed.</h3>
                    <p>Welcome to Geodashing!</p>
                    ${mailtoSection}
                    <a href="#home" class="btn btn-primary ${mailtoSection ? 'btn-primary-reduced' : ''}">Return to the map.</a>
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

            // Dynamically validate matching passwords to lock the submission button
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
                const subscribe = document.getElementById('signup-subscribe').checked;

                const res = await API.signup(user, email, pass, subscribe);
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
        let profileUsername = null;
        if (route.includes('?')) {
            const hashParams = new URLSearchParams(route.split('?')[1]);
            profileUsername = hashParams.get('username');
        }

        const container = document.getElementById('profile-container');
        if (!container) return;

        if (!profileUsername) {
            container.innerHTML = `<div class="alert alert-error">[-] Profile username missing.</div>`;
            return;
        }

        API.getProfile(profileUsername).then(json => {
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
                                    ${game.title ? `- ${window.escapeHTML(game.title)}` : ''} 
                                    ${game.is_active ? `<span style="color:var(--accent-amber); font-size:0.8rem; margin-left:0.5rem;">[ACTIVE]</span>` : ''}
                                </strong>
                                <span style="color:var(--accent-green);">${game.game_total_score} PT</span>
                            </div>
                            <div style="font-size:0.9rem; color:var(--text-muted); border-top:1px dashed #333; padding-top:0.5rem;">
                                ${game.visits ? game.visits.length : 0} Recorded Logs
                            </div>
                            <div style="margin-top:1rem; display:grid; gap:0.5rem;">
                    `;

                    game.visits.forEach((v, index) => {
                        const logTime = new Date(v.reported_time).toLocaleDateString();
                        const isAttempt = v.is_attempt == 1 || v.is_attempt === true;
                        const scoreLabel = isAttempt ? 'ATTEMPT' : `+${v.score_awarded}`;
                        const scoreColor = isAttempt ? '#888' : 'var(--accent-green)';
                        const borderStyle = isAttempt ? '1px dashed #555' : '1px solid #333';
                        const textOpacity = isAttempt ? '0.7' : '1';

                        html += `
                            <a href="https://www.geodashing.org/#dashpoint?id=${encodeURIComponent(v.dashpoint_id)}" class="nav-link" style="display:block; padding:0.5rem; border:${borderStyle}; background:rgba(0,0,0,0.3); border-radius:3px; opacity:${textOpacity};">
                                <div style="display:flex; justify-content:space-between;">
                                    <span style="color:${isAttempt ? '#888' : 'inherit'}">${index + 1}. ${window.escapeHTML(v.dashpoint_id)}</span>
                                    <span style="color:${scoreColor};">${scoreLabel}</span>
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

            fetch(`api/dashpoint.php?id=${dpId}`)
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

                    // 2. Pre-fill the decoupled Interface
                    document.getElementById('edit-notes').value = userVisit.notes || '';

                    let keptPhotosArray = [];

                    // 3. Render historical blobs and wrap them in deletion callbacks.
                    if (userVisit.photos && userVisit.photos.length > 0) {
                        existingPhotosContainer.innerHTML = ''; // Pop the generic "None" message

                        userVisit.photos.forEach((photo) => {
                            const urlStr = typeof photo === 'string' ? photo : photo.url;
                            const captionStr = typeof photo === 'string' ? '' : (photo.caption || '');
                            keptPhotosArray.push({ url: urlStr, caption: captionStr });

                            const wrap = document.createElement('div');
                            wrap.style.position = 'relative';
                            wrap.className = 'photo-preview-wrapper';
                            wrap.style.width = '100%';
                            wrap.style.height = '120px';
                            wrap.style.cursor = 'pointer';

                            const img = document.createElement('img');
                            img.src = urlStr;
                            img.style.width = '100%';
                            img.style.height = '100%';
                            img.style.objectFit = 'cover';
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
                            delBtn.style.zIndex = '10';

                            delBtn.onclick = (e) => {
                                e.stopPropagation();
                                keptPhotosArray = keptPhotosArray.filter(item => item.url !== urlStr);
                                keptPhotosInput.value = JSON.stringify(keptPhotosArray);
                                wrap.remove();

                                if (keptPhotosArray.length === 0) {
                                    existingPhotosContainer.innerHTML = `<p style="color:var(--text-muted); font-size:0.8rem; text-align:center; padding:1rem; border:1px dashed var(--border-color);">[ NO EXISTING MEDIA RETAINED ]</p>`;
                                }
                            };

                            const badge = document.createElement('div');
                            badge.className = 'photo-caption-badge';
                            
                            const updateBadgeVisual = () => {
                                const currentItem = keptPhotosArray.find(item => item.url === urlStr);
                                const hasCap = currentItem && currentItem.caption && currentItem.caption.trim() !== '';
                                if (hasCap) {
                                    badge.classList.add('has-caption');
                                    badge.innerText = '💬 CAPTIONED';
                                } else {
                                    badge.classList.remove('has-caption');
                                    badge.innerText = '✏️ EDIT CAPTION';
                                }
                            };

                            wrap.addEventListener('click', (e) => {
                                if (e.target === delBtn) return;
                                
                                const targetIndex = keptPhotosArray.findIndex(item => item.url === urlStr);
                                if (targetIndex !== -1) {
                                    openCaptionModal(urlStr, keptPhotosArray[targetIndex].caption, (newCaption) => {
                                        keptPhotosArray[targetIndex].caption = newCaption;
                                        keptPhotosInput.value = JSON.stringify(keptPhotosArray);
                                        updateBadgeVisual();
                                    });
                                }
                            });

                            updateBadgeVisual();
                            wrap.appendChild(badge);
                            wrap.appendChild(delBtn);
                            existingPhotosContainer.appendChild(wrap);
                        });

                        keptPhotosInput.value = JSON.stringify(keptPhotosArray);
                    }
                });
        });

        // 4. Capture new files and captions during edit
        const editPhotosInput = document.getElementById('edit-photos');
        const editNewPhotoPreviewGrid = document.getElementById('edit-new-photo-preview-grid');
        const btnAddEditPhotos = document.getElementById('btn-add-edit-photos');

        let newPhotoQueue = new DataTransfer();
        let newPhotoCaptions = [];

        const renderEditNewPhotoGrid = () => {
            if (!editNewPhotoPreviewGrid) return;
            editNewPhotoPreviewGrid.innerHTML = '';
            Array.from(newPhotoQueue.files).forEach((file, index) => {
                const wrapper = document.createElement('div');
                wrapper.classList.add('photo-preview-wrapper');
                wrapper.draggable = true;
                wrapper.dataset.index = index;

                const img = document.createElement('img');
                img.src = URL.createObjectURL(file);
                img.classList.add('photo-preview-item');

                const deleteBtn = document.createElement('button');
                deleteBtn.type = 'button';
                deleteBtn.classList.add('photo-delete-btn');
                deleteBtn.innerHTML = '&times;';
                deleteBtn.addEventListener('click', (ev) => {
                    ev.preventDefault();
                    ev.stopPropagation();
                    const newDt = new DataTransfer();
                    const newCaptions = [];
                    Array.from(newPhotoQueue.files).forEach((f, i) => {
                        if (i !== index) {
                            newDt.items.add(f);
                            newCaptions.push(newPhotoCaptions[i]);
                        }
                    });
                    newPhotoQueue = newDt;
                    newPhotoCaptions = newCaptions;
                    if (editPhotosInput) editPhotosInput.files = newPhotoQueue.files;
                    renderEditNewPhotoGrid();
                });

                // Tap to add caption
                wrapper.addEventListener('click', (e) => {
                    if (e.target === deleteBtn) return;
                    const imgSrc = URL.createObjectURL(file);
                    openCaptionModal(imgSrc, newPhotoCaptions[index], (newCaption) => {
                        newPhotoCaptions[index] = newCaption;
                        renderEditNewPhotoGrid();
                    });
                });

                const badge = document.createElement('div');
                badge.className = 'photo-caption-badge';
                const hasCaption = newPhotoCaptions[index] && newPhotoCaptions[index].trim() !== '';
                if (hasCaption) {
                    badge.classList.add('has-caption');
                    badge.innerText = '💬 CAPTIONED';
                } else {
                    badge.innerText = '➕ ADD CAPTION';
                }
                wrapper.appendChild(badge);

                // Drag and Drop implementation
                wrapper.addEventListener('dragstart', (ev) => {
                    ev.dataTransfer.effectAllowed = 'move';
                    ev.dataTransfer.setData('text/plain', index);
                    setTimeout(() => wrapper.style.opacity = '0.5', 0);
                });

                wrapper.addEventListener('dragend', () => {
                    wrapper.style.opacity = '1';
                });

                wrapper.addEventListener('dragover', (ev) => {
                    ev.preventDefault();
                    ev.dataTransfer.dropEffect = 'move';
                    wrapper.classList.add('photo-drag-over');
                });

                wrapper.addEventListener('dragleave', () => {
                    wrapper.classList.remove('photo-drag-over');
                });

                wrapper.addEventListener('drop', (ev) => {
                    ev.preventDefault();
                    wrapper.classList.remove('photo-drag-over');
                    const sourceIndex = parseInt(ev.dataTransfer.getData('text/plain'), 10);
                    const targetIndex = index;

                    if (sourceIndex !== targetIndex && !isNaN(sourceIndex)) {
                        const filesArray = Array.from(newPhotoQueue.files);
                        const [movedFile] = filesArray.splice(sourceIndex, 1);
                        filesArray.splice(targetIndex, 0, movedFile);

                        const [movedCaption] = newPhotoCaptions.splice(sourceIndex, 1);
                        newPhotoCaptions.splice(targetIndex, 0, movedCaption);

                        const newDt = new DataTransfer();
                        filesArray.forEach(f => newDt.items.add(f));
                        newPhotoQueue = newDt;
                        if (editPhotosInput) editPhotosInput.files = newPhotoQueue.files;
                        renderEditNewPhotoGrid();
                    }
                });

                wrapper.appendChild(img);
                wrapper.appendChild(deleteBtn);
                editNewPhotoPreviewGrid.appendChild(wrapper);
            });
        };

        if (btnAddEditPhotos && editPhotosInput) {
            btnAddEditPhotos.addEventListener('click', () => {
                editPhotosInput.click();
            });

            editPhotosInput.addEventListener('change', (e) => {
                const newFiles = Array.from(e.target.files);
                let exceeded = false;

                newFiles.forEach(file => {
                    let keptCount = 0;
                    try {
                        const kept = JSON.parse(keptPhotosInput.value);
                        if (Array.isArray(kept)) keptCount = kept.length;
                    } catch (err) {
                        console.warn("Parsing kept photos failed:", err);
                    }

                    if (keptCount + newPhotoQueue.files.length < 10) {
                        newPhotoQueue.items.add(file);
                        newPhotoCaptions.push('');
                    } else {
                        exceeded = true;
                    }
                });

                if (exceeded) {
                    alert("Maximum 10 photos allowed.");
                }

                editPhotosInput.files = newPhotoQueue.files;
                renderEditNewPhotoGrid();
            });
        }

        if (editForm) {
            editForm.addEventListener('submit', async (e) => {
                e.preventDefault();

                // Validate photos count and size
                let keptPhotosCount = 0;
                try {
                    const keptPhotos = JSON.parse(keptPhotosInput.value);
                    if (Array.isArray(keptPhotos)) {
                        keptPhotosCount = keptPhotos.length;
                    }
                } catch (_) {
                    keptPhotosCount = 0;
                }

                let newPhotosCount = newPhotoQueue.files.length;
                let newPhotosSize = 0;
                Array.from(newPhotoQueue.files).forEach(file => {
                    newPhotosSize += file.size;
                });

                if (keptPhotosCount + newPhotosCount > 10) {
                    statusDiv.innerHTML = `<div class="alert alert-error">[-] EDIT REJECTED: Maximum 10 photos allowed (retained + new). You have ${keptPhotosCount} retained and selected ${newPhotosCount} new photos.</div>`;
                    return;
                }

                const limitBytes = window.postSizeBytes || (25 * 1024 * 1024);
                if (newPhotosSize > limitBytes) {
                    statusDiv.innerHTML = `<div class="alert alert-error">[-] EDIT REJECTED: Total new photo size (${(newPhotosSize / 1024 / 1024).toFixed(1)}MB) exceeds the ${window.postMaxSize || '25M'} server limit. Please reduce image resolution or attach fewer photos.</div>`;
                    return;
                }

                submitBtn.disabled = true;
                submitBtn.innerText = "UPDATING LOG...";

                try {
                    const formData = new FormData(editForm);

                    // Append new photo captions
                    newPhotoCaptions.forEach(c => {
                        formData.append('new_captions[]', c);
                    });

                    const result = await API.editVisit(formData);

                    if (result.status === 'success') {
                        statusDiv.innerHTML = `<div class="alert" style="color:var(--accent-green); border:1px solid var(--accent-green);">[+] SYNCHRONIZED: ${result.message}</div>`;
                        submitBtn.innerText = "EDITS SAVED";
                        
                        // Clear new photos queue since they are now uploaded & saved
                        newPhotoQueue = new DataTransfer();
                        newPhotoCaptions = [];
                        if (editPhotosInput) editPhotosInput.files = newPhotoQueue.files;
                        renderEditNewPhotoGrid();
                        
                        // Wait briefly then reload hash to refresh details drawer
                        setTimeout(() => {
                            window.location.reload();
                        }, 1000);
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
    if (route.startsWith('#leaderboard')) {
        const initLeaderboard = () => {
            const tbody = document.getElementById('leaderboard-tbody');
            if (tbody) {
                let gameId = null;
                if (route.includes('?')) {
                    const hashParams = new URLSearchParams(route.split('?')[1]);
                    const gameIdStr = hashParams.get('game') || hashParams.get('game_id');
                    if (gameIdStr) {
                        gameId = parseInt(gameIdStr, 10);
                    }
                }

                if (gameId) {
                    const gameSelector = document.getElementById('game-selector');
                    if (gameSelector && parseInt(gameSelector.value) !== gameId) {
                        const option = Array.from(gameSelector.options).find(opt => parseInt(opt.value) === gameId);
                        if (option) {
                            gameSelector.value = gameId.toString();
                            window.currentGameContext.id = gameId;
                            window.currentGameContext.is_active = option.dataset.isActive == '1';
                            window.currentGameContext.title = option.dataset.title;
                            window.currentGameContext.monthYear = option.dataset.monthYear;
                            window.currentGameContext.has_summary = option.dataset.hasSummary == '1';
                        }
                    }
                }

                let ldParams = null;
                if (window.currentGameContext && window.currentGameContext.id) {
                    ldParams = window.currentGameContext.id;
                    const cycleTitle = document.getElementById('leaderboard-cycle-title');
                    if (cycleTitle && window.currentGameContext.title) {
                        cycleTitle.innerText = `${window.currentGameContext.monthYear} - Game ${window.currentGameContext.id}: ${window.escapeHTML(window.currentGameContext.title)}`;
                    }
                }

                // Display and bind Game Summary Button if available
                const summaryContainer = document.getElementById('leaderboard-summary-container');
                const btnViewSummary = document.getElementById('btn-view-summary');

                if (summaryContainer && btnViewSummary) {
                    if (window.currentGameContext && window.currentGameContext.has_summary) {
                        summaryContainer.classList.remove('d-none');

                        btnViewSummary.onclick = async () => {
                            const originalText = btnViewSummary.innerHTML;
                            btnViewSummary.disabled = true;
                            btnViewSummary.innerText = "LOADING SUMMARY...";

                            try {
                                const res = await fetch(`api/summary.php?game_id=${window.currentGameContext.id}`);
                                const data = await res.json();

                                if (data.status === 'success' && data.summary) {
                                    // Dynamic Creation of the Glassmorphic Modal Overlay
                                    const overlay = document.createElement('div');
                                    overlay.className = 'modal-overlay';
                                    overlay.id = 'summary-modal-overlay';

                                    const content = document.createElement('div');
                                    content.className = 'modal-content';

                                    const close = document.createElement('div');
                                    close.className = 'modal-close';
                                    close.innerHTML = '&times;';
                                    close.onclick = () => overlay.remove();

                                    const title = document.createElement('h2');
                                    title.innerText = `${window.currentGameContext.monthYear} Game Summary`;

                                    const richDiv = document.createElement('div');
                                    richDiv.className = 'summary-rich-content';
                                    richDiv.innerHTML = data.summary;

                                    content.appendChild(close);
                                    content.appendChild(title);
                                    content.appendChild(richDiv);
                                    overlay.appendChild(content);

                                    document.body.appendChild(overlay);

                                    // Close on click outside modal content
                                    overlay.onclick = (e) => {
                                        if (e.target === overlay) {
                                            overlay.remove();
                                        }
                                    };
                                } else {
                                    alert("Failed to load summary: " + (data.message || "Unknown error"));
                                }
                            } catch (err) {
                                console.error("Summary Fetch Error:", err);
                                alert("Failed to load summary due to network or server failure.");
                            } finally {
                                btnViewSummary.disabled = false;
                                btnViewSummary.innerHTML = originalText;
                            }
                        };

                        // Auto-open summary if deep linked
                        if (window.autoOpenSummaryId && window.autoOpenSummaryId === window.currentGameContext.id) {
                            window.autoOpenSummaryId = null;
                            btnViewSummary.click();
                        }
                    } else {
                        summaryContainer.classList.add('d-none');
                    }
                }

                // Ping the JSON endpoint directly mapping the arrays
                API.getLeaderboard(ldParams).then(json => {
                    if (json.status === 'success') {
                        const data = json.data;

                        if (data.length === 0) {
                            tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; padding:2rem; color:var(--text-muted);">[ NO LOGS YET ]</td></tr>`;
                            return;
                        }

                        // Group consecutive tied players by score
                        const groups = [];
                        let currentGroup = [];

                        for (let i = 0; i < data.length; i++) {
                            const player = data[i];
                            if (currentGroup.length === 0) {
                                currentGroup.push(player);
                            } else {
                                const prevPlayer = currentGroup[0];
                                if (player.total_score === prevPlayer.total_score) {
                                    currentGroup.push(player);
                                } else {
                                    groups.push(currentGroup);
                                    currentGroup = [player];
                                }
                            }
                        }
                        if (currentGroup.length > 0) {
                            groups.push(currentGroup);
                        }

                        // Dynamically render the Glassmorphism Table using Strategy 4
                        let html = '';
                        groups.forEach(group => {
                            const isTied = group.length > 1;
                            const firstPlayer = group[0];
                            const rankNum = firstPlayer.rank;

                            // Rank label: T1 for ties, #3 for singletons
                            const rankLabel = isTied ? `T${rankNum}` : `#${rankNum}`;

                            // Determine rank styling class
                            let rankStyleClass = 'leaderboard-rank-cell';
                            if (isTied) {
                                rankStyleClass += ' tie-rank';
                            }

                            if (rankNum === 1) {
                                rankStyleClass += ' rank-gold';
                            } else if (rankNum === 2) {
                                rankStyleClass += ' rank-silver';
                            } else if (rankNum === 3) {
                                rankStyleClass += ' rank-bronze';
                            } else {
                                rankStyleClass += ' rank-other';
                            }

                            group.forEach((player, index) => {
                                const isFirst = index === 0;
                                const isLast = index === group.length - 1;

                                let rowClass = 'leaderboard-row';
                                if (isTied) {
                                    rowClass += ' tie-group-row';
                                    if (isFirst) rowClass += ' tie-group-start';
                                    if (isLast) rowClass += ' tie-group-end';
                                }

                                html += `<tr class="${rowClass}">`;

                                // Only render the rank cell for the first player of the group (using rowspan)
                                if (isFirst) {
                                    const rowspanAttr = isTied ? ` rowspan="${group.length}"` : '';
                                    html += `<td class="${rankStyleClass}"${rowspanAttr}>${rankLabel}</td>`;
                                }

                                html += `
                                    <td class="leaderboard-user-cell">
                                        <a href="#profile?username=${encodeURIComponent(player.username)}">
                                            ${window.escapeHTML(player.username)}
                                        </a>
                                    </td>
                                    <td class="leaderboard-score-cell">${player.total_score}</td>
                                    <td class="leaderboard-logs-cell">${player.total_finds}</td>
                                </tr>
                                `;
                            });
                        });

                        tbody.innerHTML = html;
                    } else {
                        tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; padding:2rem; color:var(--accent-red);">[-] Global rankings currently unavailable.</td></tr>`;
                    }
                }).catch(_err => {
                    tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; padding:2rem; color:var(--accent-red);">[-] SYNC RUPTURED: Network Timeout.</td></tr>`;
                });
            }
        };

        if (window.gameContextLoaded) {
            window.gameContextLoaded.then(initLeaderboard);
        } else {
            initLeaderboard();
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
    // Controller: EXPORT ROUTINES (#search)
    // ==========================================================
    if (route === '#search') {
        const btnGPX = document.getElementById('btn-export-gpx');
        const btnLOC = document.getElementById('btn-export-loc');
        const btnKML = document.getElementById('btn-export-kml');
        const btnGrabBounds = document.getElementById('btn-grab-bounds');
        const searchFeedback = document.getElementById('search-feedback');
        const gameInfoDiv = document.getElementById('export-game-info');

        if (gameInfoDiv) {
            if (window.currentGameContext && window.currentGameContext.id) {
                const titleText = window.currentGameContext.title ? ` - ${window.escapeHTML(window.currentGameContext.title)}` : '';
                gameInfoDiv.innerHTML = `Exporting: Game ${window.currentGameContext.id}${titleText} (${window.currentGameContext.monthYear})`;
            } else {
                gameInfoDiv.innerHTML = `Exporting: Active Game`;
            }
        }

        const enforceExportAuth = async () => {
            const disableExportUI = () => {
                if (btnGPX) btnGPX.disabled = true;
                if (btnLOC) btnLOC.disabled = true;
                if (btnKML) btnKML.disabled = true;
                if (searchFeedback) searchFeedback.innerHTML = `<div class="alert alert-error" style="background:#2a0000; border:1px solid var(--accent-red); color:var(--accent-red);">[-] Please log in to download Dashpoint coordinates.</div>`;
            };

            if (!window.currentUser || window.currentUser.status !== 'success') {
                try {
                    const res = await API.checkSession();
                    if (res.status !== 'success') {
                        disableExportUI();
                    } else {
                        window.currentUser = res;
                    }
                } catch (_e) {
                    disableExportUI();
                }
            }
        };
        enforceExportAuth();

        const populateBoundsFromMap = () => {
            if (typeof map !== 'undefined' && map && map.getBounds()) {
                const bounds = map.getBounds();
                const ne = bounds.getNorthEast();
                const sw = bounds.getSouthWest();

                const nInput = document.getElementById('search-n');
                const sInput = document.getElementById('search-s');
                const eInput = document.getElementById('search-e');
                const wInput = document.getElementById('search-w');

                if (nInput) nInput.value = ne.lat().toFixed(5);
                if (sInput) sInput.value = sw.lat().toFixed(5);
                if (eInput) eInput.value = ne.lng().toFixed(5);
                if (wInput) wInput.value = sw.lng().toFixed(5);
            }
        };

        // Automatically pre-fill the fields with the current visible map area
        const nInput = document.getElementById('search-n');
        if (nInput && !nInput.value) {
            populateBoundsFromMap();
        }

        if (btnGrabBounds) {
            btnGrabBounds.addEventListener('click', () => {
                populateBoundsFromMap();
            });
        }

        // Dynamically extract bounds from the DOM boxes
        const getBounds = () => ({
            n: parseFloat(document.getElementById('search-n').value),
            s: parseFloat(document.getElementById('search-s').value),
            e: parseFloat(document.getElementById('search-e').value),
            w: parseFloat(document.getElementById('search-w').value)
        });

        // Exporters ping the Backend using fetch to trigger downloads asynchronously
        const downloadPayload = async (format) => {
            if (searchFeedback) searchFeedback.innerHTML = '';

            const b = getBounds();
            if (isNaN(b.n) || isNaN(b.s) || isNaN(b.e) || isNaN(b.w)) {
                if (searchFeedback) {
                    searchFeedback.innerHTML = `<div class="alert alert-error" style="background:#2a0000; border:1px solid var(--accent-red); color:var(--accent-red);">[-] Error: Missing coordinates. Please specify the complete bounding region.</div>`;
                }
                return;
            }

            const btnTarget = format === 'gpx' ? btnGPX : (format === 'loc' ? btnLOC : btnKML);
            const originalText = btnTarget.innerText;
            btnTarget.disabled = true;
            btnTarget.innerText = "DOWNLOADING...";

            try {
                let url = `api/export.php?n=${b.n}&s=${b.s}&e=${b.e}&w=${b.w}&format=${format}`;
                let gameSuffix = '';
                if (window.currentGameContext && window.currentGameContext.id) {
                    url += `&game_id=${window.currentGameContext.id}`;
                    gameSuffix = `_game_${window.currentGameContext.id}`;
                } else {
                    if (searchFeedback) {
                        searchFeedback.innerHTML = `<div class="alert alert-error" style="background:#2a0000; border:1px solid var(--accent-red); color:var(--accent-red);">[-] Error: Missing game context. Please select a game.</div>`;
                    }
                    btnTarget.disabled = false;
                    btnTarget.innerText = originalText;
                    return;
                }
                const response = await fetch(url);

                if (!response.ok) {
                    let errMsg = "Download failed due to server error.";
                    if (response.status === 401) {
                        errMsg = "Unauthorized: You must be logged in to export Dashpoint data.";
                    } else if (response.status === 400) {
                        errMsg = "Invalid bounding box boundaries provided.";
                    }
                    if (searchFeedback) {
                        searchFeedback.innerHTML = `<div class="alert alert-error" style="background:#2a0000; border:1px solid var(--accent-red); color:var(--accent-red);">[-] ${errMsg}</div>`;
                    }
                    btnTarget.disabled = false;
                    btnTarget.innerText = originalText;
                    return;
                }

                const blob = await response.blob();
                const downloadUrl = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.style.display = 'none';
                a.href = downloadUrl;
                a.download = `geodashing_v2${gameSuffix}_export.${format}`;
                document.body.appendChild(a);
                a.click();

                // Cleanup
                window.URL.revokeObjectURL(downloadUrl);
                a.remove();

                btnTarget.disabled = false;
                btnTarget.innerText = originalText;

            } catch (_error) {
                if (searchFeedback) {
                    searchFeedback.innerHTML = `<div class="alert alert-error" style="background:#2a0000; border:1px solid var(--accent-red); color:var(--accent-red);">[-] Network Error: Unable to fetch export.</div>`;
                }
                btnTarget.disabled = false;
            }
        };

        if (btnGPX) btnGPX.addEventListener('click', () => downloadPayload('gpx'));
        if (btnLOC) btnLOC.addEventListener('click', () => downloadPayload('loc'));
        if (btnKML) btnKML.addEventListener('click', () => downloadPayload('kml'));
    }
});
