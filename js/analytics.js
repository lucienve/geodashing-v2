/**
 * Analytics Interface Module
 *
 * Implements GA4 securely natively adhering strictly to standard privacy regulations.
 */

window.dataLayer = window.dataLayer || [];
function gtag() { dataLayer.push(arguments); }

window.initAnalyticsConfig = function () {
    const consent = localStorage.getItem('ga_consent');

    if (consent === 'granted') {
        // Officially boot the GA4 tracking pipeline mechanically
        const script = document.createElement('script');
        script.src = "https://www.googletagmanager.com/gtag/js?id=G-RSCKJ16QXT";
        script.async = true;
        document.head.appendChild(script);

        gtag('js', new Date());
        
        // Prevent automatic pageviews because our SPA router physically controls history natively
        gtag('config', 'G-RSCKJ16QXT', { send_page_view: false }); 
        
        window.analyticsLoaded = true;

    } else if (consent === null) {
        // Prompt user
        const banner = document.getElementById('cookie-consent-banner');
        if (banner) banner.classList.remove('d-none');
    }
}

window.acceptCookies = function () {
    localStorage.setItem('ga_consent', 'granted');
    const banner = document.getElementById('cookie-consent-banner');
    if (banner) banner.parentElement.removeChild(banner);
    window.initAnalyticsConfig();
    
    // Explicitly record the active view immediately since the boot sequence missed it
    if (window.trackPageview) {
        window.trackPageview(window.location.hash || '#home');
    }
}

window.denyCookies = function () {
    localStorage.setItem('ga_consent', 'denied');
    const banner = document.getElementById('cookie-consent-banner');
    if (banner) banner.parentElement.removeChild(banner);
}

// -------------------------------------------------------------
// SPA Instrumentation Hooks
// -------------------------------------------------------------

window.trackPageview = function (path) {
    if (window.analyticsLoaded) {
        gtag('event', 'page_view', {
            page_path: path
        });
    }
}

window.trackEvent = function (eventName, params = {}) {
    if (window.analyticsLoaded) {
        gtag('event', eventName, params);
    }
}

// Kickoff
document.addEventListener('DOMContentLoaded', () => {
    window.initAnalyticsConfig();
});
