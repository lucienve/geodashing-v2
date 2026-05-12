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
            w: SW.lng() // Inherently passes exact Pacific boundary splits natively ensuring Date Line SQL works perfectly
        };

        refreshDashpoints(searchMatrix);
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
    });

    // 3. Optional Geographic Snapping Routine
    // Request user location dropping them perfectly into their active regional gaming sector
    if (navigator.geolocation) {
        let userLocationMarker = null;

        // Google Maps style blue dot SVG for current location
        const userLocationWrapper = document.createElement("div");
        userLocationWrapper.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" style="filter: drop-shadow(0px 0px 4px rgba(0,0,0,0.4));">
                <circle cx="12" cy="12" r="10" fill="rgba(66, 133, 244, 0.3)" />
                <circle cx="12" cy="12" r="6" fill="#4285F4" stroke="#ffffff" stroke-width="2"/>
            </svg>
        `;

        // Center map initially, unless the user is explicitly deep-linked to a dashpoint
        navigator.geolocation.getCurrentPosition((position) => {
            if (!window.location.hash.startsWith('#dashpoint')) {
                map.setCenter({ lat: position.coords.latitude, lng: position.coords.longitude });
                map.setZoom(11); // Snap dynamically tightly matching typical hunting zones implicitly
            }
        });

        // Continuously update user marker
        navigator.geolocation.watchPosition((position) => {
            const pos = { lat: position.coords.latitude, lng: position.coords.longitude };
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
        }, null, { enableHighAccuracy: true });

        // Add Custom "My Location" Button mapped securely to the Google Control Position array natively
        const locationButton = document.createElement("button");

        // Material Design "My Location" SVG
        const myLocationSvg = `<svg focusable="false" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" style="width: 18px; height: 18px; fill: currentColor; display: block; margin: auto;"><path d="M12 8c-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4-1.79-4-4-4zm8.94 3c-.46-4.17-3.77-7.48-7.94-7.94V1h-2v2.06C6.83 3.52 3.52 6.83 3.06 11H1v2h2.06c.46 4.17 3.77 7.48 7.94 7.94V23h2v-2.06c4.17-.46 7.48-3.77 7.94-7.94H23v-2h-2.06zM12 19c-3.87 0-7-3.13-7-7s3.13-7 7-7 7 3.13 7 7-3.13 7-7 7z"></path></svg>`;

        locationButton.innerHTML = myLocationSvg;
        locationButton.style.backgroundColor = "rgba(0,0,0,0.8)";
        locationButton.style.border = "1px solid var(--accent-amber)";
        locationButton.style.borderRadius = "4px";
        locationButton.style.color = "var(--accent-amber)";
        locationButton.style.cursor = "pointer";
        locationButton.style.margin = "10px";
        locationButton.style.padding = "10px";
        locationButton.style.width = "40px";
        locationButton.style.height = "40px";
        locationButton.style.display = "flex";
        locationButton.style.alignItems = "center";
        locationButton.style.justifyContent = "center";
        locationButton.style.transition = "background-color 0.2s, opacity 0.2s";
        locationButton.title = "Recenter Map on Current Location";

        map.controls[google.maps.ControlPosition.RIGHT_BOTTOM].push(locationButton);

        locationButton.addEventListener("click", () => {
            locationButton.style.opacity = "0.5";
            navigator.geolocation.getCurrentPosition((position) => {
                map.panTo({ lat: position.coords.latitude, lng: position.coords.longitude });
                locationButton.style.opacity = "1";
            }, () => {
                locationButton.style.backgroundColor = "var(--accent-red)";
                locationButton.style.opacity = "1";
                setTimeout(() => locationButton.style.backgroundColor = "rgba(0,0,0,0.8)", 2000);
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

/**
 * Fetches dashpoints for the given bounding box
 */
function refreshDashpoints(bounds) {
    if (window.currentGameContext && window.currentGameContext.id) {
        bounds.game_id = window.currentGameContext.id;
    }
    const query = new URLSearchParams(bounds).toString();

    // Dynamically pinging the backend routing through the Apache /api/ structure securely
    fetch(`api/search.php?${query}`)
        .then(response => response.json())
        .then(json => {
            if (json.status === 'success') {
                plotVectors(json.data);
            }
        })
        .catch(err => console.error("SQL Vector Frame Loading Failed:", err));
}

/**
 * Natively purges the DOM rendering structure allocating entirely fresh Google Map Marker objects
 */
function plotVectors(pointsArray) {
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

        // AdvancedMarkerElement natively replaces deprecated vector geometries with the new PinElement Engine
        const pinView = new google.maps.marker.PinElement({
            background: bgColor,
            borderColor: rimColor,
            glyphColor: "#ffffff",
            scale: 0.95
        });

        const marker = new google.maps.marker.AdvancedMarkerElement({
            position: { lat: parseFloat(pt.lat), lng: parseFloat(pt.lon) },
            title: `Dashpoint ${pt.id}`,
            content: pinView
        });

        // Store state natively on the marker object for the Cluster Renderer
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
}
