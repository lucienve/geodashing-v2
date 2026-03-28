/**
 * Geodashing Vector Map Rendering Module
 *
 * Hooks into the native Google Maps JS engine, orchestrating the bounding box  
 * mathematics asynchronously mapping to our PHP SearchService seamlessly.
 */

let map;
let activeMarkers = [];

// CRITICAL: This exact function name is explicitly triggered by the Google Maps `<script>` callback string natively in index.html!
window.initMap = function() {
    // 1. Instantiate the Canvas directly into the persistent Layer 0 block securely
    map = new google.maps.Map(document.getElementById("map"), {
        center: { lat: 39.8, lng: -98.5 }, // North American Center Base Default
        zoom: 4,
        mapId: "GEODASH-V2-MAIN", // CRITICAL: AdvancedMarkerElement absolutely requires explicitly mapping a Map ID string over Google's bounds!
        disableDefaultUI: true, // Strips out the generic Google buttons leaving an ultra-clean Terminal mapping shell
        zoomControl: true, // Allow manual zooming if mouse-wheels fail
        backgroundColor: '#09090b',
        mapTypeId: google.maps.MapTypeId.TERRAIN // Automatically maps natural elevations/coastlines out natively supporting the 500m buffer logic structurally!
    });

    // 2. Bind the primary map movement listener. 
    // 'idle' physically fires exactly once instantly when a user definitively finishes sliding/zooming their finger mapping efficiency!
    google.maps.event.addListener(map, 'idle', function() {
        const bounds = map.getBounds();
        if(!bounds) return;

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
    // Physically request user location dropping them perfectly into their active regional gaming sector natively
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
 * Executes an outbound JSON fetch mapping directly to the Phase 3.5 Bounding Box API
 */
function refreshDashpoints(bounds) {
    const query = new URLSearchParams(bounds).toString();
    
    // Dynamically pinging the backend routing through the Apache /api/ structure securely
    fetch(`backend/api/search.php?${query}`)
        .then(response => response.json())
        .then(json => {
            if(json.status === 'success') {
                plotVectors(json.data);
            }
        })
        .catch(err => console.error("SQL Vector Frame Loading Failed:", err));
}

/**
 * Natively purges the DOM rendering structure allocating entirely fresh Google Map Marker objects
 */
function plotVectors(pointsArray) {
    // Securely flush volatile browser RAM preventing massive Map engine leaks
    activeMarkers.forEach(m => m.setMap(null));
    activeMarkers = [];

    pointsArray.forEach(pt => {
        // AdvancedMarkerElement natively replaces deprecated vector geometries with the new PinElement Engine
        const pinView = new google.maps.marker.PinElement({
            background: "#10b981",     // Glowing Neon Green mapping the CSS tokens
            borderColor: "#f59e0b",    // Bright Amber rim wrapping the point distinctively
            glyphColor: "#ffffff",
            scale: 0.95
        });

        const marker = new google.maps.marker.AdvancedMarkerElement({
            position: { lat: parseFloat(pt.lat), lng: parseFloat(pt.lon) },
            map: map,
            title: `Dashpoint ${pt.id}`,
            content: pinView.element
        });
        
        // If they tap a Dashpoint on their phone, physically inject the ID into the Report URL and swap the SPA template mapping it for them seamlessly!
        marker.addListener('click', () => {
            window.location.hash = `#dashpoint?id=${pt.id}`;
        });
        
        activeMarkers.push(marker);
    });
}
