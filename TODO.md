# Geodashing V2 - Future Roadmap & Ideas

This document serves as a high-level backlog for features and architectural expansions.

### 1. User Profiles & Historical Data
*   **Trophy Cabinet**: (Optional) Award digital badges for milestones (e.g. "First 100 Points" or "Dashed in 3 Countries").

### 2. Team Play Architecture
While the original database schema was structurally designed to support 'Teams' (via the `team_id` in the `users` table and the `teams` relational table), the UI currently focuses strictly on Solo Global Leaderboards. To fully implement Team Play in the future, the following systems must be built:

*   **Team Creation & Joins:**
    *   Add a UI portal allowing users to securely instantiate a new Team or request to join an existing one.
    *   Build a PHP Service parsing the `teams` database table natively.
*   **Team Leaderboards:**
    *   Update `LeaderboardService.php` to include an isolated `getTeamRankings()` method.
    *   The SQL aggregation must `SUM()` the total points of *all* approved visits fired by any player mathematically bound to the same `team_id`.
*   **The UI Switcher:**
    *   Re-introduce the `[ SOLO | TEAM ]` Glassmorphism toggle inside `templates/leaderboard.html`.
    *   Hook `js/controllers.js` to clear the table DOM and conditionally fetch `/api/leaderboard.php?type=team`.
*   **Player Logs & Attribution:**
    *   Update the `Log Visit` logic so that when a player successfully secures a Dashpoint, the resulting global ticker announcement natively attributes the visual points to both the Player *and* their Team.

### 3. Geographic records
Which the old site used to do in some way.
*   ***Farthest east/west/north/south in a country or state

### 4. Build Pipeline Modernization (Vite)
*   **Cache Busting**: As the application scales, introduce **Vite** natively as a Vanilla JS bundler to definitively solve aggressive mobile cache stagnation.
*   **Mechanism**: Vite uniquely hashes JS/CSS dynamically (e.g. `app.d73f.js`) into a `dist/` directory for absolute cache breakage on updates.
*   **Template Refactor**: Consolidate the dynamic `fetch()` calls in `js/app.js` into native `import` module strings to embed templates directly into the Javascript engine.
*   **Status**: Currently deferred to avoid adding a compile step to the lightweight PHP production deploy environment.