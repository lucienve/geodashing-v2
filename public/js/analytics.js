/**
 * @fileoverview Analytics Interface Module.
 *
 * Implements GA4 securely adhering strictly to standard privacy regulations.
 */

window.dataLayer = window.dataLayer || [];

/**
 * Pushes Google Analytics command arguments onto the global dataLayer queue.
 */
function gtag() {
  dataLayer.push(arguments);
}

/**
 * Initializes Google Analytics configuration or prompts for cookie consent.
 */
window.initAnalyticsConfig = function () {
  const consent = localStorage.getItem('ga_consent');

  if (consent === 'granted') {
    // Boot the GA4 tracking pipeline
    const script = document.createElement('script');
    script.src = 'https://www.googletagmanager.com/gtag/js?id=G-RSCKJ16QXT';
    script.async = true;
    document.head.appendChild(script);

    gtag('js', new Date());

    // Prevent automatic pageviews because our SPA router controls history directly
    gtag('config', 'G-RSCKJ16QXT', { send_page_view: false });

    window.analyticsLoaded = true;
  } else if (consent === null) {
    // Prompt user
    const banner = document.getElementById('cookie-consent-banner');
    if (banner) banner.classList.remove('d-none');
  }
};

/**
 * Grants analytics cookie consent and initializes GA4 tracking.
 */
function acceptCookies() {
  localStorage.setItem('ga_consent', 'granted');
  const banner = document.getElementById('cookie-consent-banner');
  if (banner) banner.parentElement.removeChild(banner);
  window.initAnalyticsConfig();

  // Explicitly record the active view immediately since the boot sequence missed it
  if (window.trackPageview) {
    window.trackPageview(window.location.hash || '#home');
  }
}

/**
 * Denies analytics cookie consent and dismisses the consent banner.
 */
function denyCookies() {
  localStorage.setItem('ga_consent', 'denied');
  const banner = document.getElementById('cookie-consent-banner');
  if (banner) banner.parentElement.removeChild(banner);
}

// -------------------------------------------------------------
// SPA Instrumentation Hooks
// -------------------------------------------------------------

/**
 * Records a virtual SPA pageview event in Google Analytics.
 * @param {string} path Virtual route path or hash fragment.
 */
window.trackPageview = function (path) {
  if (window.analyticsLoaded) {
    gtag('event', 'page_view', {
      page_path: path,
    });
  }
};

/**
 * Records a custom analytics event in Google Analytics.
 * @param {string} eventName Name of the analytics event.
 * @param {Object} [params={}] Optional key-value event parameters.
 */
window.trackEvent = function (eventName, params = {}) {
  if (window.analyticsLoaded) {
    gtag('event', eventName, params);
  }
};

// Kickoff
document.addEventListener('DOMContentLoaded', () => {
  window.initAnalyticsConfig();

  const acceptBtn = document.getElementById('btn-accept-cookies');
  if (acceptBtn) {
    acceptBtn.addEventListener('click', acceptCookies);
  }

  const denyBtn = document.getElementById('btn-deny-cookies');
  if (denyBtn) {
    denyBtn.addEventListener('click', denyCookies);
  }
});
