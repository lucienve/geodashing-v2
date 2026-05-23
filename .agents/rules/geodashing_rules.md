---
trigger: always_on
description: Core constraints, architectural directives, and coding standards for the Geodashing V2 project.
---

# Geodashing V2 Context & Directives

You are working on the Geodashing V2 project. You must strictly adhere to these constraints and coding standards at all times to ensure project consistency.

## 1. Project Specific Principles
- **Version Control:** When asked to generate commit messages, mandate the Conventional Commits format (e.g., `feat: [message]`, `fix: [message]`).
- **Media Optimization:** When rendering images in emails or generated summaries, always prioritize using pre-computed thumbnails (`thumb_url`) instead of having the browser dynamically resize the full-size versions (`url`). Ensure that clicking the thumbnail links to the full-size image.

## 2. Infrastructure Target Versions
Ensure all code and syntax is explicitly compatible with the following versions:
- **PHP:** `8.3.6`
- **MySQL:** `8.4.8`
- **Python:** `3.11+` (Relaxed from 3.12 to support native Debian 12 developer environments while maintaining forward-compatibility with Ubuntu production servers).

## 3. Backend Directives: Python Architecture
- **Database Rules:** Connect using `mysql-connector-python`. **Do not use an ORM**. You must use strictly parameterized queries / prepared statements for all database interactions. String interpolation or concatenation for SQL queries is strictly forbidden to prevent SQL injections.
- **Testing & Linting Commands:** Run `pytest backend/` for testing and `pylint backend/` for linting.

## 4. Backend Directives: PHP
- **Documentation:** Utilize clear PHPDoc-style block comments (`/** ... */`) for functions, classes, and properties.
- **Testing:** Employ `PHPUnit` for all backend unit testing. **You MUST put PHP test files strictly within the `backend/tests/` directory**, and mirror the logical file structure of the classes they test. Do NOT create a `tests/` directory at the project root. Run tests via `composer run test`.
- **Linting:** Run `composer run lint` to invoke `phpcs` against modified PHP files, and `composer run lint:fix` to auto-format.
- **Dependencies:** Use 'composer' for installing dependences.  Make sure to separate development and production requirements.
- **Database Rules:** Connect using the native MySQL driver (e.g. PDO). **Do not use an ORM**. You must use prepared statements for all database interactions. Raw string interpolation for SQL queries is strictly forbidden.

## 5. Frontend & UI Directives
- **Stack Limitations:** Stick strictly to Vanilla JavaScript (ES6+), semantic HTML5, and vanilla CSS3. **Do not use React, Vue, Svelte, or any heavy frontend frameworks.**
- **Responsiveness:** Ensure layouts are highly responsive and accessible on both mobile and desktop. Refrain from importing heavy external JS/CSS dependencies unless explicitly approved by the user.
- **Automated Layout Testing:** After every substantial UI or structural change, you must automatically run the Playwright E2E suite to verify that the layouts correctly constrain to mathematical device viewports without overflowing. Because of the environment path config, `npx` requires `node` to be actively mapped in the shell path. **Always run:** `export PATH="/home/lucienve/.config/nvm/versions/node/v22.22.2/bin:$PATH" && npx playwright test --reporter=list`. Do not let Playwright hang or automatically open web browsers to serve results; ensure background runs exit cleanly.
- **Separation of Concerns:** HTML, CSS, and JS logic must be completely decoupled into separate files. Inline styles (`style="..."`) and inline event handlers (`onclick="..."`) are strictly prohibited in the markup.
- **Native SPA Routing:** Navigation routing relies strictly on hash fragments instead of standard query parameters. When linking across the ecosystem, always use the SPA structures (e.g., `#profile?username=[username]` and `#dashpoint?id=[id]`).
- **Validation:** ESLint must be utilized to catch syntax errors and undefined variables prior to any commit (`npm run lint`).

## 6. E2E Testing Synchronization
- **Schema & Test Data Parity:** Whenever you modify `schema.sql`, you must systematically evaluate the constraints of the new schema elements against the E2E test database structure. You MUST update `e2e/setup-test-db.sh` to ensure any mock data seeded for Playwright respects the newly defined columns, foreign keys, or logic requirements without diverging.
- **Test execution limits:** Explicitly avoid running `reporter='html'` such that it opens up a web browser visually natively. The CI configuration or `playwright.config.js` should explicitly possess `reporter: [['html', { open: 'never' }]]` manually.

## 7. Environments (Local vs. Production)
- **Local Environment:** This is the local workspace where you are running commands, testing, formatting, and verifying code. This environment leverages mocked data (like GCS fakes) and safe database seeds (`setup-test-db.sh`) configured strictly for local development and testing.
- **Production Environment:** The live server is isolated and completely unreachable by the agent (this antigravity instance runs strictly on a local development machine with no access to production servers, databases, or live environment data).
  - **No Direct Operations:** The agent must never attempt to run shell commands on production, execute database queries against production, or request credentials/connections to production.
  - **Human Operator Orchestration:** If diagnostic data, schema changes, or database modifications from production are required, the agent must provide the precise reasoning, the exact SQL scripts, or the explicit CLI commands for the human operator to manually execute on the production environment and transfer the results/data back into this conversation.

