/**
 * Geodashing Map Rendering Module
 *
 * Hooks into the native Google Maps JS engine, mapping 
 * locations to our search API.
 */

let map;
let activeMarkers = [];
let appClusterer = null;
let activeCircles = [];
let activeVisitMarkers = [];
let dashpointsAbortController = null;
let visitsAbortController = null;

// Custom Algorithm for mapping Visited State priorities to Grouped Containers
const customClusterRenderer = {
    render: function ({ count, position, markers }) {
        let maxVisit = 0;
        // Prioritize finding visited nodes within the bucket
        markers.forEach(m => {
            if (m.visitCount > maxVisit) {
                maxVisit = m.visitCount;
            }
        });

        let bgColor = "#ef4444"; // Default Red: Everything is unvisited
        let rimColor = "#7f1d1d";

        if (maxVisit === 1) {
            bgColor = "#10b981"; // Green: Contains a visited point
            rimColor = "#064e3b";
        } else if (maxVisit > 1) {
            bgColor = "#facc15"; // Yellow: Contains a heavy-traffic point
            rimColor = "#713f12";
        }

        const pinView = new google.maps.marker.PinElement({
            background: bgColor,
            borderColor: rimColor,
            glyph: String(count),
            glyphColor: "#ffffff",
            scale: 1.2
        });

        return new google.maps.marker.AdvancedMarkerElement({
            position: position,
            content: pinView
        });
    }
};

// CRITICAL: This exact function name is explicitly triggered by the Google Maps <script> callback string in index.html.
window.initMap = function () {
    // 1. Instantiate the Canvas directly into the persistent Layer 0 block
    map = new google.maps.Map(document.getElementById("map"), {
        center: { lat: 43.0606, lng: -88.1065 }, // Brookfield, Wisconsin Default
        zoom: 11,
        mapId: "4dedb78dd8b6780fb403a0bd", // CRITICAL: AdvancedMarkerElement requires mapping a Map ID string over Google's bounds.
        disableDefaultUI: true, // Strips out the generic Google buttons leaving an ultra-clean Terminal mapping shell
        zoomControl: window.innerWidth > 768, // Only show zoom buttons on Desktop where mouse-wheels might fail; mobile users naturally pinch-to-zoom

        // Native Google Satellite vs Terrain toggles
        mapTypeControl: true,
        mapTypeControlOptions: {
            position: google.maps.ControlPosition.LEFT_BOTTOM,
            style: google.maps.MapTypeControlStyle.DEFAULT
        },

        // backgroundColor: '#09090b', // Removed to comply with Advanced Market mapId Cloud overrides without throwing Console Warnings
        mapTypeId: google.maps.MapTypeId.TERRAIN, // Maps natural elevations and coastlines, supporting the 500m buffer logic.

        // CRITICAL: Google Maps operates on Layer 0 and is completely unaware of the floating Header/Footer UI on Layer 1. 
        // Add padding so controls don't get trapped underneath the UI menus.
        padding: { top: 70, bottom: window.innerWidth < 768 ? 140 : 30, left: 10, right: 10 }
    });

    // Expose the native map instance globally specifically for E2E Testing evaluation
    window.__geodashingMap = map;

    // 2. Bind the primary map movement listener. 
    // 'idle' fires when a user finishes sliding/zooming their map
    google.maps.event.addListener(map, 'idle', function () {
        const bounds = map.getBounds();
        if (!bounds) return;

        const NE = bounds.getNorthEast();
        const SW = bounds.getSouthWest();

        const searchMatrix = {
            n: NE.lat(),
            s: SW.lat(),
            e: NE.lng(),
            w: SW.lng() // Inherently passes exact Pacific boundary splits to ensure Date Line SQL works perfectly
        };

        refreshDashpoints(searchMatrix);

        if (map.getZoom() >= 15) {
            refreshVisitLogs(searchMatrix);
        } else {
            clearVisitLogs();
        }
    });

    // 2b. Listen for zoom changes to toggle 100m dashpoint radius visibility
    google.maps.event.addListener(map, 'zoom_changed', function () {
        const showCircles = map.getZoom() >= 14;
        activeCircles.forEach(c => {
            if (showCircles && !c.getMap()) {
                c.setMap(map);
            } else if (!showCircles && c.getMap()) {
                c.setMap(null);
            }
        });

        const showVisits = map.getZoom() >= 15;
        if (!showVisits) {
            clearVisitLogs();
        }
    });

    // 3. Optional Geographic Snapping Routine
    // Request user location dropping them perfectly into their active regional gaming sector
    const geoProvider = window.mockGeolocation || navigator.geolocation;
    if (geoProvider) {
        let userLocationMarker = null;

        // Google Maps style blue dot SVG for current location
        const userLocationWrapper = document.createElement("div");
        userLocationWrapper.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" class="marker-pin-svg">
                <circle cx="12" cy="12" r="10" fill="rgba(66, 133, 244, 0.3)" />
                <circle cx="12" cy="12" r="6" fill="#4285F4" stroke="#ffffff" stroke-width="2"/>
            </svg>
        `;

        // Center map initially, unless the user is explicitly deep-linked to a dashpoint
        geoProvider.getCurrentPosition((position) => {
            if (!window.location.hash.startsWith('#dashpoint')) {
                map.setCenter({ lat: position.coords.latitude, lng: position.coords.longitude });
                map.setZoom(11); // Snap dynamically tightly matching typical hunting zones implicitly
            }
        });

        // Continuously update user marker and check proximity radar when visible
        let watchId = null;
        let currentTrackingMode = null; // 'high', 'low', or null
        let gpsBuffer = []; // array of {lat, lng} of size max 3. Covers ~3s in high accuracy (1Hz ticks) or ~30-60s in low accuracy.
        let inRangeLockId = null; // id of the dashpoint currently locked "in range"
        let lastVibratedId = null; // to ensure haptic vibration fires only once per entry
        let radarLine = null;

        const startLocationWatch = (mode = 'high') => {
            // Check if map route is active (hash is empty or #home)
            const hash = window.location.hash.split('?')[0];
            if (hash !== '' && hash !== '#home') {
                return;
            }

            if (watchId !== null) {
                if (currentTrackingMode === mode) return; // already in this mode
                geoProvider.clearWatch(watchId);
                watchId = null;
            }

            currentTrackingMode = mode;
            const options = mode === 'high' 
                ? { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
                : { enableHighAccuracy: false, timeout: 20000, maximumAge: 10000 };

            watchId = geoProvider.watchPosition((position) => {
                const rawLat = position.coords.latitude;
                const rawLon = position.coords.longitude;

                // 1. Coordinate averaging/smoothing (rolling buffer of size 3) - Only in high accuracy
                let pos;
                if (currentTrackingMode === 'high') {
                    gpsBuffer.push({ lat: rawLat, lng: rawLon });
                    if (gpsBuffer.length > 3) {
                        gpsBuffer.shift();
                    }
                    const avgLat = gpsBuffer.reduce((sum, p) => sum + p.lat, 0) / gpsBuffer.length;
                    const avgLon = gpsBuffer.reduce((sum, p) => sum + p.lng, 0) / gpsBuffer.length;
                    pos = { lat: avgLat, lng: avgLon };
                } else {
                    gpsBuffer = [];
                    pos = { lat: rawLat, lng: rawLon };
                }

                // Store current smoothed position globally
                window.currentUserPosition = pos;
                
                // Hide GPS error banner if visible on success
                const banner = document.getElementById('gps-error-banner');
                if (banner) banner.classList.add('d-none');

                if (!userLocationMarker) {
                    userLocationMarker = new google.maps.marker.AdvancedMarkerElement({
                        map: map,
                        position: pos,
                        content: userLocationWrapper,
                        title: "Your Location",
                        zIndex: 99999
                    });
                } else {
                    userLocationMarker.position = pos;
                }

                // If template overlay is active, hide HUD and clear radar line
                const currentHash = window.location.hash.split('?')[0];
                if (currentHash !== '' && currentHash !== '#home') {
                    hideRadarHUD();
                    return;
                }

                // Run proximity radar processing
                processProximityRadar(pos);

            }, (error) => {
                console.error("GPS Watch error:", error);
                // Show GPS error banner on failure
                const banner = document.getElementById('gps-error-banner');
                if (banner) banner.classList.remove('d-none');
            }, options);
        };

        const stopLocationWatch = () => {
            if (watchId !== null) {
                geoProvider.clearWatch(watchId);
                watchId = null;
            }
            currentTrackingMode = null;
            gpsBuffer = [];
            hideRadarHUD();
            // Ensure error banner is hidden when watch is stopped
            const banner = document.getElementById('gps-error-banner');
            if (banner) banner.classList.add('d-none');
        };

        function processProximityRadar(pos) {
            if (!window.loadedDashpoints || window.loadedDashpoints.length === 0) {
                hideRadarHUD();
                return;
            }

            // Calculate distance to all loaded dashpoints
            let points = window.loadedDashpoints.map(dp => {
                const dist = window.calculateDistance(pos.lat, pos.lng, parseFloat(dp.lat), parseFloat(dp.lon));
                return { dp, dist };
            });

            // Multi-point focus lock
            let targetPoint = null;
            if (inRangeLockId) {
                const currentLock = points.find(p => p.dp.id === inRangeLockId);
                if (currentLock && currentLock.dist <= 110) {
                    targetPoint = currentLock;
                } else {
                    inRangeLockId = null; // broke range lock
                }
            }

            // If no locked point, pick the closest one
            if (!targetPoint) {
                points.sort((a, b) => a.dist - b.dist);
                const closest = points[0];
                if (closest) {
                    targetPoint = closest;
                }
            }

            if (!targetPoint) {
                hideRadarHUD();
                return;
            }

            const distance = targetPoint.dist;
            const dp = targetPoint.dp;

            // Dynamic GPS Accuracy Gating (Battery Save)
            if (distance > 500) {
                hideRadarHUD();
                startLocationWatch('low');
                return;
            } else {
                startLocationWatch('high');
            }

            // Proximity State & Hysteresis logic (enter <=100m, exit >110m)
            let inRange = false;
            if (distance <= 100) {
                inRange = true;
                inRangeLockId = dp.id; // Lock focus
            } else if (inRangeLockId === dp.id && distance <= 110) {
                inRange = true;
            }

            // Update HUD elements
            const hud = document.getElementById('radar-hud');
            const targetIdSpan = document.getElementById('radar-target-id');
            const distanceText = document.getElementById('radar-distance-text');
            const logBtn = document.getElementById('radar-btn-log');

            if (hud) {
                hud.classList.remove('d-none');
                if (inRange) {
                    hud.classList.remove('out-of-range');
                    hud.classList.add('in-range');
                    if (distanceText) distanceText.innerHTML = `IN RANGE &mdash; ${distance.toFixed(1)}m away`;
                    if (logBtn) {
                        logBtn.style.display = 'block';
                        logBtn.disabled = false;
                        logBtn.onclick = () => {
                            window.location.hash = `#report?id=${dp.id}`;
                        };
                    }
                    
                    // Trigger single vibration on entry
                    if (lastVibratedId !== dp.id && navigator.vibrate) {
                        navigator.vibrate([100, 50, 100]);
                        lastVibratedId = dp.id;
                    }
                } else {
                    hud.classList.remove('in-range');
                    hud.classList.add('out-of-range');
                    if (distanceText) distanceText.innerHTML = `${distance.toFixed(1)}m away`;
                    if (logBtn) {
                        logBtn.style.display = 'none';
                        logBtn.disabled = true;
                    }
                    // Reset vibration when out of range
                    if (lastVibratedId === dp.id) {
                        lastVibratedId = null;
                    }
                }
                if (targetIdSpan) targetIdSpan.innerText = dp.id;
            }

            // Draw or update neon Polyline on map
            const lineCoords = [
                pos,
                { lat: parseFloat(dp.lat), lng: parseFloat(dp.lon) }
            ];

            const lineSymbol = {
                path: 'M 0,-1 0,1',
                strokeOpacity: 1,
                scale: 2
            };

            const strokeColor = inRange ? '#10b981' : '#f59e0b';

            if (!radarLine) {
                radarLine = new google.maps.Polyline({
                    path: lineCoords,
                    strokeColor: strokeColor,
                    strokeOpacity: 0,
                    icons: [
                        {
                            icon: lineSymbol,
                            offset: '0',
                            repeat: '20px'
                        }
                    ],
                    map: map
                });
            } else {
                radarLine.setPath(lineCoords);
                radarLine.setOptions({
                    strokeColor: strokeColor,
                    map: map
                });
            }
        }

        window.processProximityRadar = processProximityRadar;

        function hideRadarHUD() {
            const hud = document.getElementById('radar-hud');
            if (hud) hud.classList.add('d-none');
            if (radarLine) {
                radarLine.setMap(null);
                radarLine = null;
            }
            inRangeLockId = null;
            lastVibratedId = null;
        }

        const locationVisibility = new window.VisibilityManager(
            () => startLocationWatch('high'),
            stopLocationWatch
        );
        locationVisibility.start();

        // Collapsible HUD toggle bindings
        const toggleBtn = document.getElementById('radar-hud-toggle');
        const hudElement = document.getElementById('radar-hud');
        if (toggleBtn && hudElement) {
            toggleBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                const isCollapsed = hudElement.classList.toggle('collapsed');
                toggleBtn.innerHTML = isCollapsed ? '▼' : '▲';
                toggleBtn.setAttribute('aria-label', isCollapsed ? 'Expand panel' : 'Collapse panel');
            });
        }

        // Router-aware sleep/wake controller
        document.addEventListener('routeLoaded', (event) => {
            const route = event.detail.route;
            const hash = route.split('?')[0];
            
            if (hash === '' || hash === '#home') {
                if (document.visibilityState === 'visible') {
                    startLocationWatch('high');
                }
            } else {
                stopLocationWatch();
            }
        });

        // Add Custom "My Location" Button mapped securely to the Google Control Position array
        const locationButton = document.createElement("button");
        locationButton.className = "map-location-btn";

        // Material Design "My Location" SVG
        const myLocationSvg = `<svg focusable="false" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" class="map-location-icon"><path d="M12 8c-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4-1.79-4-4-4zm8.94 3c-.46-4.17-3.77-7.48-7.94-7.94V1h-2v2.06C6.83 3.52 3.52 6.83 3.06 11H1v2h2.06c.46 4.17 3.77 7.48 7.94 7.94V23h2v-2.06c4.17-.46 7.48-3.77 7.94-7.94H23v-2h-2.06zM12 19c-3.87 0-7-3.13-7-7s3.13-7 7-7 7 3.13 7 7-3.13 7-7 7z"></path></svg>`;

        locationButton.innerHTML = myLocationSvg;
        locationButton.title = "Recenter Map on Current Location";

        map.controls[google.maps.ControlPosition.RIGHT_BOTTOM].push(locationButton);

        locationButton.addEventListener("click", () => {
            locationButton.classList.add("locating");
            geoProvider.getCurrentPosition((position) => {
                map.panTo({ lat: position.coords.latitude, lng: position.coords.longitude });
                locationButton.classList.remove("locating");
            }, () => {
                locationButton.classList.remove("locating");
                locationButton.classList.add("error");
                setTimeout(() => locationButton.classList.remove("error"), 2000);
            });
        });
    }
}

// Expose map refresher so the SPA router can trigger a map refresh.
window.refreshMapBounds = function () {
    if (typeof map !== 'undefined' && map) {
        google.maps.event.trigger(map, 'idle');
    }
};

// =========================================================================
// Private Point Tagging Marker Integration
// =========================================================================

const tagShapeSvgs = {
    star: '<svg class="tag-svg-icon" viewBox="0 0 24 24"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>',
    diamond: '<svg class="tag-svg-icon" viewBox="0 0 24 24"><path d="M12 2L2 12l10 10 10-10L12 2z"/></svg>',
    triangle: '<svg class="tag-svg-icon" viewBox="0 0 24 24"><path d="M12 3L2 21h20L12 3z"/></svg>',
    square: '<svg class="tag-svg-icon" viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="2"/></svg>'
};

const tagColorClasses = {
    '#1a73e8': 'pin-badge-google-blue',
    '#8e24aa': 'pin-badge-google-purple',
    '#e64a19': 'pin-badge-google-orange',
    '#d81b60': 'pin-badge-google-magenta'
};

function createTagBadge(tag) {
    const badge = document.createElement('div');
    const colorKey = (tag.color || '').toLowerCase();
    const shapeKey = (tag.shape || '').toLowerCase();
    const colorClass = tagColorClasses[colorKey] || 'pin-badge-google-blue';
    badge.className = `pin-tag-badge ${colorClass}`;
    badge.innerHTML = tagShapeSvgs[shapeKey] || '';
    return badge;
}

window.resetUserTags = function () {
    if (typeof API !== 'undefined' && API.resetUserTagsCache) {
        API.resetUserTagsCache();
    } else {
        window.currentUserTags = {};
    }
    decorateActiveMarkersWithTags();
};

document.addEventListener('userTagsChanged', () => {
    decorateActiveMarkersWithTags();
});

function decorateActiveMarkersWithTags() {
    if (!activeMarkers || !window.currentUserTags) return;
    activeMarkers.forEach(m => {
        if (!m.dashpointId || !m.customContainer) return;
        const tag = window.currentUserTags[m.dashpointId];
        const existingBadge = m.customContainer.querySelector('.pin-tag-badge');
        if (tag && !existingBadge) {
            m.customContainer.appendChild(createTagBadge(tag));
        } else if (!tag && existingBadge) {
            existingBadge.remove();
        } else if (tag && existingBadge) {
            const colorKey = (tag.color || '').toLowerCase();
            const shapeKey = (tag.shape || '').toLowerCase();
            existingBadge.className = `pin-tag-badge ${tagColorClasses[colorKey] || 'pin-badge-google-blue'}`;
            existingBadge.innerHTML = tagShapeSvgs[shapeKey] || '';
        }
    });
}

function loadUserTagsForGame(gameId) {
    if (!gameId) return;

    if (typeof API !== 'undefined' && API.checkSession && API.loadUserTags) {
        API.checkSession(gameId).then(auth => {
            if (auth.status === 'success' && auth.tags_enabled) {
                API.loadUserTags(gameId).then(() => {
                    decorateActiveMarkersWithTags();
                }).catch(err => {
                    console.error("Failed to load user tags:", err);
                });
            }
        }).catch(_ => {});
    }
}

window.updateMarkerTag = function (dashpointId, tagData) {
    if (!activeMarkers) return;
    const marker = activeMarkers.find(m => m.dashpointId === dashpointId);
    if (!marker || !marker.customContainer) return;
    const existingBadge = marker.customContainer.querySelector('.pin-tag-badge');
    if (existingBadge) {
        existingBadge.remove();
    }
    if (tagData) {
        marker.customContainer.appendChild(createTagBadge(tagData));
    }
};

/**
 * Fetches dashpoints for the given bounding box
 */
function refreshDashpoints(bounds) {
    if (window.currentGameContext && window.currentGameContext.id) {
        bounds.game_id = window.currentGameContext.id;
        loadUserTagsForGame(bounds.game_id);
    } else {
        console.warn("Skipping dashpoint refresh: No active game context selected.");
        return;
    }

    if (dashpointsAbortController) {
        dashpointsAbortController.abort();
    }
    dashpointsAbortController = new AbortController();

    const query = new URLSearchParams(bounds).toString();

    // Dynamically pinging the backend routing through the Apache /api/ structure securely
    fetch(`api/search.php?${query}`, { signal: dashpointsAbortController.signal })
        .then(response => response.json())
        .then(json => {
            if (json.status === 'success') {
                plotVectors(json.data);
            }
        })
        .catch(err => {
            if (err.name === 'AbortError') return;
            console.error("SQL Vector Frame Loading Failed:", err);
        });
}

/**
 * Purges the DOM rendering structure allocating entirely fresh Google Map Marker objects
 */
function plotVectors(pointsArray) {
    // Save loaded dashpoints globally for the proximity radar HUD check
    window.loadedDashpoints = pointsArray || [];

    // Flush old markers and circles
    if (appClusterer) {
        appClusterer.clearMarkers();
    } else {
        activeMarkers.forEach(m => m.setMap(null));
    }
    activeMarkers = [];

    activeCircles.forEach(c => c.setMap(null));
    activeCircles = [];

    pointsArray.forEach(pt => {
        let vCount = 0;
        if (pt.visit_count) {
            vCount = parseInt(pt.visit_count);
        }

        // Dynamically style based on visit count
        let bgColor = "#ef4444"; // Default Red: Unvisited dashpoint
        let rimColor = "#7f1d1d";

        if (vCount === 1) {
            bgColor = "#10b981"; // Green: Successfully visited
            rimColor = "#064e3b";
        } else if (vCount > 1) {
            bgColor = "#facc15"; // Yellow: Multiple visits
            rimColor = "#713f12";
        }

        // AdvancedMarkerElement replaces deprecated vector geometries with the new PinElement Engine
        const pinView = new google.maps.marker.PinElement({
            background: bgColor,
            borderColor: rimColor,
            glyphColor: "#ffffff",
            scale: 0.95
        });

        const container = document.createElement('div');
        container.className = 'custom-pin-container';
        container.appendChild(pinView.element);

        const userTag = window.currentUserTags ? window.currentUserTags[pt.id] : null;
        if (userTag) {
            container.appendChild(createTagBadge(userTag));
        }

        const marker = new google.maps.marker.AdvancedMarkerElement({
            position: { lat: parseFloat(pt.lat), lng: parseFloat(pt.lon) },
            title: `Dashpoint ${pt.id}`,
            content: container
        });

        // Store state on marker for lookup and clustering
        marker.dashpointId = pt.id;
        marker.customContainer = container;
        marker.pinView = pinView;
        marker.visitCount = vCount;

        // AdvancedMarkerElement uses `gmp-click` mapping to bypass DOM bubble overlaps.
        marker.addListener('gmp-click', () => {
            window.location.hash = `#dashpoint?id=${pt.id}`;
        });

        activeMarkers.push(marker);

        // Draw 100m radius circle (only visible at high zoom levels > 14)
        const circle = new google.maps.Circle({
            strokeColor: rimColor,
            strokeOpacity: 0.8,
            strokeWeight: 1,
            fillColor: bgColor,
            fillOpacity: 0.15,
            map: map.getZoom() >= 14 ? map : null,
            center: { lat: parseFloat(pt.lat), lng: parseFloat(pt.lon) },
            radius: 100,
            clickable: false // Ensure circles don't block clicking pins / dragging the map
        });

        activeCircles.push(circle);
    });

    if (!appClusterer) {
        appClusterer = new markerClusterer.MarkerClusterer({
            map: map,
            markers: activeMarkers,
            renderer: customClusterRenderer
        });
    } else {
        appClusterer.addMarkers(activeMarkers);
    }

    // If we already have the user's position, run the proximity radar immediately
    if (window.currentUserPosition && typeof window.processProximityRadar === 'function') {
        window.processProximityRadar(window.currentUserPosition);
    }
}

/**
 * Fetches actual user log/visit locations for the given bounding box
 */
function refreshVisitLogs(bounds) {
    if (window.currentGameContext && window.currentGameContext.id) {
        bounds.game_id = window.currentGameContext.id;
    } else {
        return;
    }

    if (visitsAbortController) {
        visitsAbortController.abort();
    }
    visitsAbortController = new AbortController();

    const query = new URLSearchParams(bounds).toString();

    fetch(`api/search_visits.php?${query}`, { signal: visitsAbortController.signal })
        .then(response => response.json())
        .then(json => {
            if (json.status === 'success') {
                plotVisitMarkers(json.data);
            }
        })
        .catch(err => {
            if (err.name === 'AbortError') return;
            console.error("Visits Loading Failed:", err);
        });
}

/**
 * Clears all active user log/visit markers from the map
 */
function clearVisitLogs() {
    if (visitsAbortController) {
        visitsAbortController.abort();
        visitsAbortController = null;
    }
    activeVisitMarkers.forEach(m => m.setMap(null));
    activeVisitMarkers = [];
}

/**
 * Plots actual user log/visit markers on the map
 */
function plotVisitMarkers(visitsArray) {
    clearVisitLogs();

    (visitsArray || []).forEach(visit => {
        const container = document.createElement('div');
        container.className = 'visit-marker-container';
        if (visit.is_attempt) {
            container.classList.add('attempt');
        }

        const dot = document.createElement('div');
        dot.className = 'visit-marker-dot';

        const label = document.createElement('div');
        label.className = 'visit-marker-label';
        label.textContent = visit.username;

        container.appendChild(dot);
        container.appendChild(label);

        container.addEventListener('click', () => {
            window.location.hash = `#dashpoint?id=${visit.dashpoint_id}`;
        });

        const marker = new google.maps.marker.AdvancedMarkerElement({
            map: map,
            position: { lat: parseFloat(visit.lat), lng: parseFloat(visit.lon) },
            title: `${visit.username}'s ${visit.is_attempt ? 'Attempt' : 'Visit'}`,
            content: container,
            zIndex: 9999, // Ensure visits render on top of default markers but below user location (99999)
            anchorLeft: "-50%",
            anchorTop: "-50%"
        });

        marker.addListener('gmp-click', () => {
            window.location.hash = `#dashpoint?id=${visit.dashpoint_id}`;
        });

        activeVisitMarkers.push(marker);
    });
}
