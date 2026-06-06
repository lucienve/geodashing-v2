/**
 * VisibilityManager Utility Class
 *
 * Tracks the page visibility state using the Page Visibility API (document.visibilityState
 * and visibilitychange) and calls custom callbacks to pause/resume expensive continuous 
 * resources (like GPS tracking or background polling).
 */
class VisibilityManager {
    /**
     * @param {Function} onVisible - Callback executed when the page is active/visible.
     * @param {Function} onHidden - Callback executed when the page goes to the background/hidden.
     */
    constructor(onVisible, onHidden) {
        if (typeof onVisible !== 'function' || typeof onHidden !== 'function') {
            throw new Error("VisibilityManager requires valid onVisible and onHidden functions.");
        }
        this.onVisible = onVisible;
        this.onHidden = onHidden;
        this.isActive = false;
        this._handleVisibilityChange = this._handleVisibilityChange.bind(this);
    }

    /**
     * Starts tracking visibility events and triggers onVisible if already visible.
     */
    start() {
        if (this.isActive) return;
        this.isActive = true;

        document.addEventListener('visibilitychange', this._handleVisibilityChange);

        // Requirement 3: Ensure the initial load checks the visibility state before starting the first poll/tracking.
        if (document.visibilityState === 'visible') {
            this.onVisible();
        }
    }

    /**
     * Stops tracking visibility events and triggers onHidden to release resources.
     */
    stop() {
        if (!this.isActive) return;
        this.isActive = false;

        document.removeEventListener('visibilitychange', this._handleVisibilityChange);
        this.onHidden();
    }

    /**
     * Internal handler to switch states when document visibility changes.
     * @private
     */
    _handleVisibilityChange() {
        if (document.visibilityState === 'visible') {
            this.onVisible();
        } else {
            this.onHidden();
        }
    }
}

// Expose to global window object
window.VisibilityManager = VisibilityManager;
