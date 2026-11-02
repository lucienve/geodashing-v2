/**
 * @fileoverview Geodashing Vanilla SPA Router Engine.
 *
 * Intercepts native browser URL hashes (e.g. domain.com/#login),
 * loading HTML templates over the map dynamically.
 */

/**
 * Calculates the distance in meters across the spherical curvature of the Earth.
 * @param {number} lat1 Starting latitude in degrees.
 * @param {number} lon1 Starting longitude in degrees.
 * @param {number} lat2 Ending latitude in degrees.
 * @param {number} lon2 Ending longitude in degrees.
 * @returns {number} Distance in meters.
 */
window.calculateDistance = function (lat1, lon1, lat2, lon2) {
  const r = 6371e3; // Earth radius in meters
  const rad = Math.PI / 180;
  const phi1 = lat1 * rad;
  const phi2 = lat2 * rad;
  const deltaPhi = (lat2 - lat1) * rad;
  const deltaLambda = (lon2 - lon1) * rad;

  const a =
    Math.sin(deltaPhi / 2) * Math.sin(deltaPhi / 2) +
    Math.cos(phi1) *
      Math.cos(phi2) *
      Math.sin(deltaLambda / 2) *
      Math.sin(deltaLambda / 2);

  return r * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
};

/**
 * Escapes raw strings for safe HTML injection, preventing XSS.
 * @param {string} str Raw input string.
 * @returns {string} HTML-escaped string.
 */
window.escapeHTML = function (str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
};

/**
 * Initializes global application state and upload size defaults.
 */
function initGlobalState() {
  // 0. Global game state binding for historical tracking.
  window.currentGameContext = {
    id: null,
    is_active: true,
    is_preview: false,
    title: '',
    monthYear: '',
    start_time: '',
    has_summary: false,
  };
  window.gamesList = [];
  window.postMaxSize = '25M';
  window.postSizeBytes = 25 * 1024 * 1024; // Fallback to 25MB
}

/**
 * Dynamically builds the desktop and mobile navigation links.
 */
function initNavigation() {
  // --- BEGIN NAVIGATION BUILDER ---
  const APP_NAVIGATION = [
    { text: 'LEADERBOARD', mobileText: 'Leaderboard', href: '#leaderboard' },
    {
      text: 'HELP ▾',
      isDropdown: true,
      children: [
        { text: 'About', href: '#about' },
        { text: 'How to Play', href: '#how-to' },
        { text: 'Contact', href: '#contact' },
      ],
    },
  ];

  const desktopContainer = document.getElementById('desktop-links');
  const mobileContainer = document.querySelector('.mobile-nav-links');
  const desktopAuthBtn = document.getElementById('nav-auth-btn');
  const mobileAuthBtn = document.getElementById('mobile-nav-auth-btn');

  APP_NAVIGATION.forEach((item) => {
    if (item.isDropdown) {
      // Desktop Dropdown
      if (desktopContainer && desktopAuthBtn) {
        const dropDiv = document.createElement('div');
        dropDiv.className = 'dropdown';
        const mainLink = document.createElement('a');
        mainLink.href = '#';
        mainLink.className = 'nav-link';
        mainLink.innerText = item.text;
        const dropContent = document.createElement('div');
        dropContent.className = 'dropdown-content';
        item.children.forEach((child) => {
          const childLink = document.createElement('a');
          childLink.href = child.href;
          childLink.className = 'nav-link';
          childLink.innerText = child.text;
          dropContent.appendChild(childLink);
        });
        dropDiv.appendChild(mainLink);
        dropDiv.appendChild(dropContent);
        desktopContainer.insertBefore(dropDiv, desktopAuthBtn);
      }

      // Mobile Flat rendering (Help items are flattened directly into the drawer)
      if (mobileContainer && mobileAuthBtn) {
        item.children.forEach((child) => {
          const childLink = document.createElement('a');
          childLink.href = child.href;
          childLink.className = 'nav-link';
          childLink.innerText = child.mobileText || child.text;
          mobileContainer.insertBefore(childLink, mobileAuthBtn);
        });
      }
    } else {
      // Desktop Link
      if (desktopContainer && desktopAuthBtn) {
        const link = document.createElement('a');
        link.href = item.href;
        link.className =
          'nav-link' +
          (item.defaultActive ? ' active' : '') +
          (item.extraClasses ? ' ' + item.extraClasses : '');
        if (item.idDesktop) link.id = item.idDesktop;
        link.innerText = item.text;
        desktopContainer.insertBefore(link, desktopAuthBtn);
      }

      // Mobile Link
      if (mobileContainer && mobileAuthBtn) {
        const link = document.createElement('a');
        link.href = item.href;
        link.className =
          'nav-link' +
          (item.defaultActive ? ' active' : '') +
          (item.extraClasses ? ' ' + item.extraClasses : '');
        if (item.idMobile) link.id = item.idMobile;
        link.innerText = item.mobileText || item.text;
        mobileContainer.insertBefore(link, mobileAuthBtn);
      }
    }
  });
  // --- END NAVIGATION BUILDER ---
}

/**
 * Initializes the hash-based SPA router and mobile drawer listeners.
 */
function initRouting() {
  // 1. Explicit Routing Logic Dictionary
  const routes = {
    '': null,
    '#home': null,
    '#dashpoint': 'templates/dashpoint.html',
    '#login': 'templates/login.html',
    '#report': 'templates/report.html',
    '#edit': 'templates/edit.html',
    '#search': 'templates/search.html',
    '#leaderboard': 'templates/leaderboard.html',
    '#profile': 'templates/profile.html',
    '#about': 'templates/about.html',
    '#how-to': 'templates/how-to.html',
    '#contact': 'templates/contact.html',
  };

  const contentDiv = document.getElementById('app-content');
  const navLinks = document.querySelectorAll('.nav-link');
  const mobileMenuBtn = document.getElementById('mobile-menu-btn');
  const mobileNavDrawer = document.getElementById('mobile-nav-drawer');
  const mobileCloseBtn = document.getElementById('mobile-close-btn');
  const mobileNavBackdrop = document.getElementById('mobile-nav-backdrop');

  const closeMobileDrawer = () => {
    if (mobileNavDrawer) {
      mobileNavDrawer.classList.remove('open');
    }
    if (mobileNavBackdrop) {
      mobileNavBackdrop.classList.remove('open');
    }
  };

  if (mobileMenuBtn && mobileNavDrawer) {
    mobileMenuBtn.addEventListener('click', () => {
      mobileNavDrawer.classList.add('open');
      if (mobileNavBackdrop) {
        mobileNavBackdrop.classList.add('open');
      }
    });
  }

  if (mobileCloseBtn) {
    mobileCloseBtn.addEventListener('click', closeMobileDrawer);
  }

  if (mobileNavBackdrop) {
    mobileNavBackdrop.addEventListener('click', closeMobileDrawer);
  }

  if (contentDiv) {
    contentDiv.addEventListener('click', (e) => {
      if (e.target === contentDiv && window.innerWidth <= 768) {
        if (document.getElementById('form-report')) {
          return; // Protect active field log from accidental dismissal
        }
        window.location.hash = '#home';
      }
    });
  }

  /**
   * Loads the active route template based on the current URL hash or query parameters.
   * @returns {Promise<void>}
   */
  window.loadRoute = async function () {
    closeMobileDrawer();

    if (typeof window.updateGameContextBanner === 'function') {
      window.updateGameContextBanner();
    }

    let fullHash = window.location.hash;

    // Redirect '#leaderboard' to '#leaderboard?game=ID' if a non-current game is selected.
    if (fullHash === '#leaderboard') {
      if (
        window.currentGameContext &&
        window.currentGameContext.id &&
        window.activeGameId &&
        window.currentGameContext.id !== window.activeGameId
      ) {
        window.location.hash = `#leaderboard?game=${window.currentGameContext.id}`;
        return;
      }
    }

    // SEO-friendly Query Parameter Fallback for indexing
    const urlParams = new URLSearchParams(window.location.search);
    if (!fullHash && urlParams.has('dashpoint')) {
      fullHash = `#dashpoint?id=${urlParams.get('dashpoint')}`;
    } else if (!fullHash && urlParams.has('summary')) {
      fullHash = '#leaderboard';
      window.autoOpenSummaryId = parseInt(urlParams.get('summary'), 10);
    } else if (!fullHash && urlParams.has('game')) {
      fullHash = `#leaderboard?game=${urlParams.get('game')}`;
    } else if (!fullHash && urlParams.has('page')) {
      fullHash = `#${urlParams.get('page')}`;
    } else if (!fullHash) {
      fullHash = '#home';
    }

    // Dynamically maintain the Canonical URL for Search Engines
    let canonicalTag = document.getElementById('canonical-link');
    if (!canonicalTag) {
      canonicalTag = document.createElement('link');
      canonicalTag.id = 'canonical-link';
      canonicalTag.rel = 'canonical';
      document.head.appendChild(canonicalTag);
    }

    if (fullHash.startsWith('#dashpoint?id=')) {
      const dpId = fullHash.split('?id=')[1];
      canonicalTag.href = `https://www.geodashing.org/?dashpoint=${dpId}`;
    } else if (fullHash.startsWith('#leaderboard')) {
      if (
        window.autoOpenSummaryId ||
        (window.currentGameContext &&
          !window.currentGameContext.is_active &&
          window.currentGameContext.has_summary &&
          !fullHash.includes('?'))
      ) {
        const sumId = window.autoOpenSummaryId || window.currentGameContext.id;
        canonicalTag.href = `https://www.geodashing.org/?summary=${sumId}`;
      } else if (fullHash.includes('?')) {
        const hashParams = new URLSearchParams(fullHash.split('?')[1]);
        const gameId = hashParams.get('game') || hashParams.get('game_id');
        if (gameId) {
          canonicalTag.href = `https://www.geodashing.org/?game=${gameId}`;
        } else {
          canonicalTag.href = `https://www.geodashing.org/`;
        }
      } else {
        canonicalTag.href = `https://www.geodashing.org/`;
      }
    } else if (['#about', '#how-to', '#contact'].includes(fullHash)) {
      const pageId = fullHash.substring(1);
      canonicalTag.href = `https://www.geodashing.org/?page=${pageId}`;
    } else {
      canonicalTag.href = `https://www.geodashing.org/`;
    }

    if (window.trackPageview) {
      window.trackPageview(fullHash);
    }

    // Strip out query parameters cleanly so the dictionary perfectly understands `#dashpoint?id=123`
    const hash = fullHash.split('?')[0];

    const templatePath = routes[hash];

    // Ensure active Nav items get highlighted aesthetically
    navLinks.forEach((link) => {
      link.classList.remove('active');
      if (
        link.getAttribute('href') === hash ||
        link.getAttribute('href') === fullHash
      ) {
        link.classList.add('active');
      }
    });

    if (templatePath === undefined) {
      contentDiv.innerHTML =
        '<div class="template-view"><h2>PAGE NOT FOUND</h2><p class="data-input text-error">Could not locate that page.</p></div>';
      contentDiv.classList.add('overlay-active');
      return;
    }

    try {
      // Smoothly collapse the current UI out preventing janky HTML resets
      contentDiv.classList.add('content-fade');

      // Allow the router to purge the DOM overlay for map views.
      if (templatePath === null) {
        setTimeout(() => {
          contentDiv.innerHTML = '';
          contentDiv.classList.remove('overlay-active', 'content-fade');
          document.dispatchEvent(
            new CustomEvent('routeLoaded', { detail: { route: fullHash } }),
          );
        }, 100);
        return;
      }

      const response = await fetch(templatePath);
      if (!response.ok) {
        throw new Error('Template layout missing continuously.');
      }

      const html = await response.text();

      setTimeout(() => {
        contentDiv.innerHTML = html;
        contentDiv.classList.add('overlay-active');
        contentDiv.classList.remove('content-fade');

        // CRITICAL: Since we just injected raw HTML into the DOM,
        // any JS listeners tied to buttons inside it must be re-bound.
        // We fire a custom event telling `controllers.js` to wake up and route the original query bounds.
        document.dispatchEvent(
          new CustomEvent('routeLoaded', { detail: { route: fullHash } }),
        );
      }, 100);
    } catch (err) {
      console.error('Router Error: ', err);
      contentDiv.innerHTML =
        '<div class="template-view"><h2>NETWORK ERROR</h2><p class="data-input text-error">Oops! Having trouble communicating with the server.</p></div>';
      contentDiv.classList.add('overlay-active');
      contentDiv.classList.remove('content-fade');
    }
  };

  // 3. Native History API bindings (so the Phone's 'Back' button works)
  window.addEventListener('hashchange', window.loadRoute);

  // Initial Boot mapping
  window.loadRoute();
}

/**
 * Sets the active game context across the application and updates the UI switcher.
 * @param {number} gameId Target game ID.
 * @param {Object} [options]
 * @param {boolean} [options.triggerRouteUpdate=true] Whether to trigger routing/map updates.
 */
window.setGameContext = function (gameId, options = {}) {
  const { triggerRouteUpdate = true } = options;
  if (!window.gamesList || window.gamesList.length === 0) return;

  const game = window.gamesList.find((g) => g.id === gameId);
  if (!game) return;

  const activeGame =
    window.gamesList.find((g) => Number(g.is_active) === 1) ||
    window.gamesList[0];
  const activeStart = activeGame
    ? new Date(activeGame.start_time).getTime()
    : 0;
  const gameStart = new Date(game.start_time).getTime();
  const isActive = Number(game.is_active) === 1;
  const isPreview = !isActive && gameStart > activeStart;

  const d = new Date(game.start_time);
  const monthYear = d.toLocaleDateString('en-US', {
    month: 'short',
    year: 'numeric',
  });

  window.currentGameContext.id = game.id;
  window.currentGameContext.is_active = isActive;
  window.currentGameContext.is_preview = isPreview;
  window.currentGameContext.title = game.title;
  window.currentGameContext.monthYear = monthYear;
  window.currentGameContext.start_time = game.start_time;
  window.currentGameContext.has_summary = Number(game.has_summary) === 1;

  updateGameSwitcherUI(game);

  if (typeof window.updateGameContextBanner === 'function') {
    window.updateGameContextBanner();
  }

  if (!isActive && typeof window.hideRadarHUD === 'function') {
    window.hideRadarHUD();
  }

  if (typeof window.resetUserTags === 'function') {
    window.resetUserTags();
  }

  if (triggerRouteUpdate) {
    if (window.location.hash.startsWith('#leaderboard')) {
      const targetHash =
        window.activeGameId && game.id === window.activeGameId
          ? '#leaderboard'
          : `#leaderboard?game=${game.id}`;

      if (window.location.hash !== targetHash) {
        window.location.hash = targetHash;
      } else {
        if (window.loadRoute) {
          window.loadRoute();
        }
      }
    } else if (
      window.location.hash === '' ||
      window.location.hash === '#home' ||
      window.location.hash.startsWith('#home?')
    ) {
      if (typeof window.refreshMapBounds === 'function') {
        window.refreshMapBounds();
      }
    } else {
      if (window.loadRoute) {
        window.loadRoute();
      }
    }
  }
};

/**
 * Updates the game switcher button and popover selection state.
 * @param {Object} game Currently active game object.
 */
function updateGameSwitcherUI(game) {
  const btn = document.getElementById('game-switcher-btn');
  if (!btn) return;

  const activeGame =
    (window.gamesList &&
      window.gamesList.find((g) => Number(g.is_active) === 1)) ||
    (window.gamesList && window.gamesList[0]);
  const activeStart = activeGame
    ? new Date(activeGame.start_time).getTime()
    : 0;
  const gameStart = new Date(game.start_time).getTime();
  const isActive = Number(game.is_active) === 1;
  const isPreview = !isActive && gameStart > activeStart;

  const d = new Date(game.start_time);
  const monthYear = d.toLocaleDateString('en-US', {
    month: 'short',
    year: 'numeric',
  });

  btn.classList.remove('status-active', 'status-preview', 'status-completed');
  let statusBadge;
  let compactStatus;

  if (isActive) {
    btn.classList.add('status-active');
    statusBadge = ' [ACTIVE]';
    compactStatus = 'ACTIVE';
  } else if (isPreview) {
    btn.classList.add('status-preview');
    statusBadge = ' [PREVIEW]';
    compactStatus = 'PREVIEW';
  } else {
    btn.classList.add('status-completed');
    statusBadge = ' [COMPLETED]';
    compactStatus = 'PAST';
  }

  const fullSpan = btn.querySelector('.switcher-label-full');
  const compactSpan = btn.querySelector('.switcher-label-compact');
  if (fullSpan) {
    fullSpan.textContent = `Game ${game.id} (${monthYear})${statusBadge} ▾`;
  }
  if (compactSpan) {
    compactSpan.textContent = `G${game.id} • ${compactStatus} ▾`;
  }

  const popover = document.getElementById('game-switcher-popover');
  if (popover) {
    popover.querySelectorAll('.game-switcher-option').forEach((card) => {
      const cId = parseInt(card.getAttribute('data-game-id'), 10);
      const isSelected = cId === game.id;
      card.setAttribute('aria-selected', isSelected ? 'true' : 'false');
      if (isSelected) {
        card.classList.add('is-selected');
      } else {
        card.classList.remove('is-selected');
      }
    });
  }
}

/**
 * Formats countdown or timing string for game cards.
 * @param {Object} game Game object.
 * @param {boolean} isAct Is active game.
 * @param {boolean} isPrev Is preview game.
 * @returns {string} Formatted duration or empty string.
 */
function formatGameTiming(game, isAct, isPrev) {
  const now = Date.now();
  if (isAct && game.end_time) {
    const endMs = new Date(game.end_time).getTime();
    const diffMs = endMs - now;
    if (diffMs > 0) {
      const days = Math.floor(diffMs / (1000 * 60 * 60 * 24));
      const hours = Math.floor(
        (diffMs % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60),
      );
      return `Ends in ${days}d ${hours}h`;
    }
  }
  if (isPrev && game.start_time) {
    const startMs = new Date(game.start_time).getTime();
    const diffMs = startMs - now;
    if (diffMs > 0) {
      const days = Math.floor(diffMs / (1000 * 60 * 60 * 24));
      const hours = Math.floor(
        (diffMs % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60),
      );
      return `Starts in ${days}d ${hours}h`;
    }
  }
  return '';
}

/**
 * Renders the popover menu content for game selection.
 * @param {Array<Object>} games All games list.
 * @param {number} selectedGameId Selected game ID.
 */
function renderGameSwitcherPopover(games, selectedGameId) {
  const popover = document.getElementById('game-switcher-popover');
  if (!popover) return;

  const activeGame = games.find((g) => Number(g.is_active) === 1) || games[0];
  const activeStart = activeGame
    ? new Date(activeGame.start_time).getTime()
    : 0;

  const previewGames = games
    .filter(
      (g) =>
        Number(g.is_active) !== 1 &&
        new Date(g.start_time).getTime() > activeStart,
    )
    .sort(
      (a, b) =>
        new Date(a.start_time).getTime() - new Date(b.start_time).getTime(),
    );

  const completedGames = games
    .filter(
      (g) =>
        Number(g.is_active) !== 1 &&
        new Date(g.start_time).getTime() <= activeStart,
    )
    .sort(
      (a, b) =>
        new Date(b.start_time).getTime() - new Date(a.start_time).getTime(),
    );

  const gamesByYear = {};
  completedGames.forEach((g) => {
    const yr = new Date(g.start_time).getFullYear().toString();
    if (!gamesByYear[yr]) {
      gamesByYear[yr] = [];
    }
    gamesByYear[yr].push(g);
  });

  let html = '';

  html += '<div class="popover-section pinned-section">';
  html += '<div class="popover-section-title">Current &amp; Upcoming</div>';
  html += '<div class="pinned-cards-grid">';

  if (activeGame) {
    const isSel = activeGame.id === selectedGameId;
    const d = new Date(activeGame.start_time);
    const mY = d.toLocaleDateString('en-US', {
      month: 'short',
      year: 'numeric',
    });
    const timing = formatGameTiming(activeGame, true, false);
    html += `
      <button type="button" class="game-switcher-option pinned-card pinned-active ${isSel ? 'is-selected' : ''}" 
              data-game-id="${activeGame.id}" role="option" aria-selected="${isSel}">
        <div class="pinned-card-header">
          <span class="pinned-card-title">Game ${activeGame.id}</span>
          <span class="game-badge badge-active">[ACTIVE]</span>
        </div>
        <div class="pinned-card-meta">${mY} &bull; ${window.escapeHTML(activeGame.title)}</div>
        ${timing ? `<div class="pinned-card-timing">${timing}</div>` : ''}
      </button>`;
  }

  previewGames.forEach((prevGame) => {
    const isSel = prevGame.id === selectedGameId;
    const d = new Date(prevGame.start_time);
    const mY = d.toLocaleDateString('en-US', {
      month: 'short',
      year: 'numeric',
    });
    const timing = formatGameTiming(prevGame, false, true);
    html += `
      <button type="button" class="game-switcher-option pinned-card pinned-preview ${isSel ? 'is-selected' : ''}" 
              data-game-id="${prevGame.id}" role="option" aria-selected="${isSel}">
        <div class="pinned-card-header">
          <span class="pinned-card-title">Game ${prevGame.id}</span>
          <span class="game-badge badge-preview">[PREVIEW]</span>
        </div>
        <div class="pinned-card-meta">${mY} &bull; ${window.escapeHTML(prevGame.title)}</div>
        ${timing ? `<div class="pinned-card-timing">${timing}</div>` : ''}
      </button>`;
  });

  html += '</div></div>';

  const years = Object.keys(gamesByYear).sort((a, b) => Number(b) - Number(a));
  if (years.length > 0) {
    html += '<div class="popover-section archive-section">';
    html += '<div class="popover-section-title">Archive</div>';
    years.forEach((yr, idx) => {
      const isCurrentYear = idx === 0;
      const hasSelectedGame = gamesByYear[yr].some(
        (g) => g.id === selectedGameId,
      );
      const isOpen = isCurrentYear || hasSelectedGame ? 'open' : '';
      html += `<details class="game-archive-year" ${isOpen}>`;
      html += `<summary class="archive-year-summary">${yr}</summary>`;
      html += '<div class="archive-games-list">';
      gamesByYear[yr].forEach((g) => {
        const isSel = g.id === selectedGameId;
        const d = new Date(g.start_time);
        const mY = d.toLocaleDateString('en-US', {
          month: 'short',
          year: 'numeric',
        });
        html += `
          <button type="button" class="game-switcher-option archive-card ${isSel ? 'is-selected' : ''}" 
                  data-game-id="${g.id}" role="option" aria-selected="${isSel}">
            <div class="archive-card-header">
              <span class="archive-card-name">Game ${g.id} &bull; ${window.escapeHTML(g.title)}</span>
              <span class="game-badge badge-completed">[COMPLETED]</span>
            </div>
            <div class="pinned-card-meta">${mY}</div>
          </button>`;
      });
      html += '</div></details>';
    });
    html += '</div>';
  }

  popover.innerHTML = html;
}

let gameSwitcherEventsInitialized = false;

/**
 * Binds user interaction events for the game switcher button and popover.
 */
function initGameSwitcherEvents() {
  if (gameSwitcherEventsInitialized) return;
  gameSwitcherEventsInitialized = true;

  const switcher = document.getElementById('game-switcher');
  const btn = document.getElementById('game-switcher-btn');
  const popover = document.getElementById('game-switcher-popover');
  if (!switcher || !btn || !popover) return;

  /**
   * Opens the game switcher popover and sets focus to the active/first option.
   */
  function openPopover() {
    popover.classList.remove('d-none');
    btn.setAttribute('aria-expanded', 'true');
    const selectedOption =
      popover.querySelector('.game-switcher-option.is-selected') ||
      popover.querySelector('.game-switcher-option');
    if (selectedOption) {
      selectedOption.focus();
    }
  }

  /**
   * Closes the game switcher popover and updates the aria-expanded state.
   */
  function closePopover() {
    popover.classList.add('d-none');
    btn.setAttribute('aria-expanded', 'false');
  }

  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const isExpanded = btn.getAttribute('aria-expanded') === 'true';
    if (isExpanded) {
      closePopover();
    } else {
      openPopover();
    }
  });

  popover.addEventListener('click', (e) => {
    const optionBtn = e.target.closest('.game-switcher-option');
    if (optionBtn) {
      const gameId = parseInt(optionBtn.getAttribute('data-game-id'), 10);
      if (!isNaN(gameId) && typeof window.setGameContext === 'function') {
        window.setGameContext(gameId);
      }
      closePopover();
      btn.focus();
    }
  });

  document.addEventListener('click', (e) => {
    if (!switcher.contains(e.target)) {
      closePopover();
    }
  });

  switcher.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closePopover();
      btn.focus();
    }
  });
}

/**
 * Fetches the list of games and initializes the top-bar game switcher popover.
 */
function initGameContext() {
  window.gameContextLoaded = API.getGames()
    .then((json) => {
      if (json.status === 'success' && json.data.length > 0) {
        window.gamesList = json.data;

        // Find Active Game
        const activeGame =
          json.data.find((g) => Number(g.is_active) === 1) || json.data[0];
        window.activeGameId = activeGame.id;

        let targetGameId = activeGame.id;
        let fullHash = window.location.hash;
        const urlParams = new URLSearchParams(window.location.search);
        if (!fullHash && urlParams.has('dashpoint')) {
          fullHash = `#dashpoint?id=${urlParams.get('dashpoint')}`;
        } else if (!fullHash && urlParams.has('summary')) {
          const parsedId = parseInt(urlParams.get('summary'), 10);
          if (!isNaN(parsedId) && json.data.find((g) => g.id === parsedId)) {
            targetGameId = parsedId;
          }
        } else if (!fullHash && urlParams.has('game')) {
          const parsedId = parseInt(urlParams.get('game'), 10);
          if (!isNaN(parsedId) && json.data.find((g) => g.id === parsedId)) {
            targetGameId = parsedId;
          }
        }

        if (fullHash.startsWith('#leaderboard')) {
          if (fullHash.includes('?')) {
            const hashParams = new URLSearchParams(fullHash.split('?')[1]);
            const gameIdStr =
              hashParams.get('game') || hashParams.get('game_id');
            if (gameIdStr) {
              const parsedId = parseInt(gameIdStr, 10);
              if (
                !isNaN(parsedId) &&
                json.data.find((g) => g.id === parsedId)
              ) {
                targetGameId = parsedId;
              }
            }
          }
        }

        initGameSwitcherEvents();
        renderGameSwitcherPopover(json.data, targetGameId);

        const btnSwitchActive = document.getElementById(
          'btn-context-switch-active',
        );
        if (btnSwitchActive && !btnSwitchActive.dataset.bound) {
          btnSwitchActive.dataset.bound = 'true';
          btnSwitchActive.addEventListener('click', () => {
            if (
              window.activeGameId &&
              typeof window.setGameContext === 'function'
            ) {
              window.setGameContext(window.activeGameId);
            }
          });
        }

        window.setGameContext(targetGameId, { triggerRouteUpdate: false });
      }
    })
    .catch((_err) =>
      console.error('Could not fetch active game configuration.'),
    );
}

/**
 * Updates the visibility and text of the floating game context banner.
 */
window.updateGameContextBanner = function () {
  const banner = document.getElementById('game-context-banner');
  if (!banner) return;

  const isHome =
    window.location.hash === '' ||
    window.location.hash === '#home' ||
    window.location.hash.startsWith('#home?');

  if (
    !window.currentGameContext ||
    window.currentGameContext.is_active ||
    !isHome
  ) {
    banner.classList.add('d-none');
    return;
  }

  const textEl = document.getElementById('game-context-banner-text');
  const ctx = window.currentGameContext;
  banner.classList.remove('banner-preview');

  if (ctx.is_preview) {
    banner.classList.add('banner-preview');
    if (textEl) {
      textEl.textContent = `Viewing Upcoming Preview: Game ${ctx.id}${ctx.title ? ` (${ctx.title})` : ''}`;
    }
  } else {
    if (textEl) {
      textEl.textContent = `Viewing Past Game: Game ${ctx.id}${ctx.title ? ` (${ctx.title})` : ''}`;
    }
  }

  banner.classList.remove('d-none');
};

/**
 * Initializes authentication session checking and navigation auth UI updates.
 */
function initAuthState() {
  /**
   * Checks session status and updates desktop and mobile navigation auth controls.
   * @returns {Promise<void>}
   */
  window.updateAuthState = async function () {
    const desktopContainer = document.getElementById('desktop-links');
    const mobileContainer = document.querySelector('.mobile-nav-links');

    // Locate or recover standard auth buttons, maintaining expected IDs cleanly
    let navAuthBtn =
      document.getElementById('nav-auth-btn') ||
      document.getElementById('hidden-nav-auth-btn');
    let mobileAuthBtn =
      document.getElementById('mobile-nav-auth-btn') ||
      document.getElementById('hidden-mobile-nav-auth-btn');

    if (navAuthBtn) {
      navAuthBtn.id = 'nav-auth-btn';
    }
    if (mobileAuthBtn) {
      mobileAuthBtn.id = 'mobile-nav-auth-btn';
    }

    // Clean up previously created dynamic DOM elements to prevent duplicate groups
    const oldUserDropdown = document.getElementById('nav-user-dropdown');
    if (oldUserDropdown) {
      oldUserDropdown.remove();
    }

    const oldMobileGroup = document.getElementById('mobile-player-group');
    if (oldMobileGroup) {
      oldMobileGroup.remove();
    }

    try {
      const res = await API.checkSession();
      if (res.status === 'success') {
        window.currentUser = res; // Bind the full Payload (including is_verified) globally
        if (res.post_max_size) {
          window.postMaxSize = res.post_max_size;
        }
        if (res.post_max_size_bytes) {
          window.postSizeBytes = res.post_max_size_bytes;
        }
        if (res.is_verified === 0) {
          if (navAuthBtn) {
            navAuthBtn.classList.remove('d-none');
            navAuthBtn.innerText = `UNVERIFIED [CLICK TO RESEND]`;
            navAuthBtn.href = '#login';
            navAuthBtn.classList.add('nav-auth-unverified');
            const newBtn = navAuthBtn.cloneNode(true);
            navAuthBtn.replaceWith(newBtn);
            navAuthBtn = newBtn;
          }
          if (mobileAuthBtn) {
            mobileAuthBtn.classList.remove('d-none');
            mobileAuthBtn.innerText = `UNVERIFIED [CLICK TO RESEND]`;
            mobileAuthBtn.href = '#login';
            mobileAuthBtn.classList.add('nav-auth-unverified');
            const newBtn = mobileAuthBtn.cloneNode(true);
            mobileAuthBtn.replaceWith(newBtn);
            mobileAuthBtn = newBtn;
          }
        } else {
          // Authenticated and verified.

          // 1. Desktop Profile & Logout Dropdown Menu
          if (navAuthBtn && desktopContainer) {
            navAuthBtn.classList.add('d-none');
            navAuthBtn.id = 'hidden-nav-auth-btn';

            const dropDiv = document.createElement('div');
            dropDiv.id = 'nav-user-dropdown';
            dropDiv.className = 'dropdown';

            // Dropdown trigger anchor
            const triggerBtn = document.createElement('a');
            triggerBtn.id = 'nav-auth-btn';
            triggerBtn.className = 'nav-link highlight';
            triggerBtn.href = '#';
            triggerBtn.innerText = `👤 ${res.username} ▾`;

            triggerBtn.addEventListener('click', (e) => {
              e.preventDefault();
            });

            const dropContent = document.createElement('div');
            dropContent.className = 'dropdown-content';

            const profileLink = document.createElement('a');
            profileLink.id = 'nav-profile-link';
            profileLink.className = 'nav-link';
            profileLink.href = `#profile?username=${encodeURIComponent(res.username)}`;
            profileLink.innerText = 'My Profile';

            const exportLink = document.createElement('a');
            exportLink.id = 'nav-export-link';
            exportLink.className = 'nav-link';
            exportLink.href = '#search';
            exportLink.innerText = 'Export Game Data';

            const logoutLink = document.createElement('a');
            logoutLink.id = 'desktop-logout-link';
            logoutLink.className = 'nav-link';
            logoutLink.href = '#';
            logoutLink.innerText = 'Logout';
            logoutLink.addEventListener('click', async (e) => {
              e.preventDefault();
              await API.logout();
              window.location.reload();
            });

            dropContent.appendChild(profileLink);
            dropContent.appendChild(exportLink);
            dropContent.appendChild(logoutLink);

            dropDiv.appendChild(triggerBtn);
            dropDiv.appendChild(dropContent);

            desktopContainer.appendChild(dropDiv);
          }

          // 2. Mobile Grouped Navigation Setup
          if (mobileAuthBtn && mobileContainer) {
            mobileAuthBtn.classList.add('d-none');
            mobileAuthBtn.id = 'hidden-mobile-nav-auth-btn';

            const mobileGroup = document.createElement('div');
            mobileGroup.id = 'mobile-player-group';

            const header = document.createElement('div');
            header.className = 'mobile-player-header';
            header.innerText = 'Player Actions';

            const profileLink = document.createElement('a');
            profileLink.id = 'mobile-nav-profile-link';
            profileLink.className = 'nav-link mobile-player-link';
            profileLink.href = `#profile?username=${encodeURIComponent(res.username)}`;
            profileLink.innerText = 'Profile';

            const exportLink = document.createElement('a');
            exportLink.id = 'mobile-nav-export-link';
            exportLink.className = 'nav-link mobile-player-link';
            exportLink.href = '#search';
            exportLink.innerText = 'Export Data';

            const logoutLink = document.createElement('a');
            logoutLink.id = 'mobile-logout-link';
            logoutLink.className = 'nav-link mobile-player-link';
            logoutLink.href = '#';
            logoutLink.innerText = 'Logout';
            logoutLink.addEventListener('click', async (e) => {
              e.preventDefault();
              await API.logout();
              window.location.reload();
            });

            mobileGroup.appendChild(header);
            mobileGroup.appendChild(profileLink);
            mobileGroup.appendChild(exportLink);
            mobileGroup.appendChild(logoutLink);

            mobileContainer.appendChild(mobileGroup);
          }
        }
      } else {
        // Logged out.
        window.currentUser = null;

        if (navAuthBtn) {
          navAuthBtn.classList.remove('d-none');
          navAuthBtn.innerText = `Player login`;
          navAuthBtn.href = '#login';
          navAuthBtn.classList.remove('nav-auth-unverified');
          const newBtn = navAuthBtn.cloneNode(true);
          navAuthBtn.replaceWith(newBtn);
          navAuthBtn = newBtn;
        }

        if (mobileAuthBtn) {
          mobileAuthBtn.classList.remove('d-none');
          mobileAuthBtn.innerText = `Player login`;
          mobileAuthBtn.href = '#login';
          mobileAuthBtn.classList.remove('nav-auth-unverified');
          const newBtn = mobileAuthBtn.cloneNode(true);
          mobileAuthBtn.replaceWith(newBtn);
          mobileAuthBtn = newBtn;
        }

        const verifyBanner = document.getElementById('verify-banner');
        if (verifyBanner) verifyBanner.classList.add('d-none');
      }
    } catch (_e) {
      console.error('Session integrity check failed.');
    }
  };

  // Execute the auth loop mapping the initial load.
  window.updateAuthState();
}

document.addEventListener('DOMContentLoaded', () => {
  initGlobalState();
  initNavigation();
  initRouting();
  initGameContext();
  initAuthState();
  if (
    window.DraftStorage &&
    typeof window.DraftStorage.pruneExpiredDrafts === 'function'
  ) {
    window.DraftStorage.pruneExpiredDrafts(7).catch((err) => {
      console.warn('Failed to prune expired drafts during boot.', err);
    });
  }
});
