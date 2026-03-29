/**
 * Geodashing Map Rendering Module
 *
 * Hooks into the native Google Maps JS engine, mapping 
 * locations to our search API.
 */

let map;
let activeMarkers = [];

// CRITICAL: This exact function name is explicitly triggered by the Google Maps `<script>` callback string natively in index.html!
window.initMap = function () {
    // 1. Instantiate the Canvas directly into the persistent Layer 0 block
    map = new google.maps.Map(document.getElementById("map"), {
        center: { lat: 43.0606, lng: -88.1065 }, // Brookfield, Wisconsin Default
        zoom: 11,
        mapId: "GEODASH-V2-MAIN", // CRITICAL: AdvancedMarkerElement absolutely requires explicitly mapping a Map ID string over Google's bounds!
        disableDefaultUI: true, // Strips out the generic Google buttons leaving an ultra-clean Terminal mapping shell
        zoomControl: true, // Allow manual zooming if mouse-wheels fail

        // Native Google Satellite vs Terrain toggles
        mapTypeControl: true,
        mapTypeControlOptions: {
            position: google.maps.ControlPosition.RIGHT_BOTTOM,
            style: google.maps.MapTypeControlStyle.DEFAULT
        },

        backgroundColor: '#09090b',
        mapTypeId: google.maps.MapTypeId.TERRAIN // Automatically maps natural elevations/coastlines out natively supporting the 500m buffer logic structurally!
    });

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

    // 3. Optional Geographic Snapping Routine
    // Request user location dropping them perfectly into their active regional gaming sector
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition((position) => {
            map.setCenter({ lat: position.coords.latitude, lng: position.coords.longitude });
            map.setZoom(11); // Snap dynamically tightly matching typical hunting zones implicitly
        }, () => {
            console.log("Geolocation mapping completely refused or unavailable on this terminal.");
        });
    }
}

/**
 * Fetches dashpoints for the given bounding box
 */
function refreshDashpoints(bounds) {
    const query = new URLSearchParams(bounds).toString();

    // Dynamically pinging the backend routing through the Apache /api/ structure securely
    fetch(`backend/api/search.php?${query}`)
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
    // Flush old markers
    activeMarkers.forEach(m => m.setMap(null));
    activeMarkers = [];

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
            map: map,
            title: `Dashpoint ${pt.id}`,
            content: pinView
        });

        // AdvancedMarkerElement strictly enforces `gmp-click` mapping directly bypassing legacy DOM bubble overlaps perfectly!
        marker.addListener('gmp-click', () => {
            window.location.hash = `#dashpoint?id=${pt.id}`;
        });

        activeMarkers.push(marker);
    });
}
