---
trigger: always_on
description: Core constraints, architectural directives, and coding standards for the Geodashing V2 project.
---

# Geodashing V2 Context & Directives

You are working on the Geodashing V2 project. You must strictly adhere to these constraints and coding standards at all times to ensure project consistency.

## 1. Project Specific Principles
- **Version Control:** When asked to generate commit messages, mandate the Conventional Commits format (e.g., `feat: [message]`, `fix: [message]`).

## 2. Infrastructure Target Versions
Ensure all code and syntax is explicitly compatible with the following versions:
- **PHP:** `8.3.6`
- **MySQL:** `8.4.8`
- **Python:** `3.11+` (Relaxed from 3.12 to support native Debian 12 developer environments while maintaining forward-compatibility with Ubuntu production servers).

## 3. Backend Directives: Python Architecture
- **Database Rules:** Connect using `mysql-connector-python`. **Do not use an ORM**. You must use strictly parameterized queries / prepared statements for all database interactions. String interpolation or concatenation for SQL queries is strictly forbidden to prevent SQL injections.

## 4. Backend Directives: PHP
- **Documentation:** Utilize clear PHPDoc-style block comments (`/** ... */`) for functions, classes, and properties.
- **Testing:** Employ `PHPUnit` for all backend unit testing. **You MUST put PHP test files strictly within the `backend/tests/` directory**, and mirror the logical file structure of the classes they test. Do NOT create a `tests/` directory at the project root.
- **Dependencies:** Use 'composer' for installing dependences.  Make sure to separate development and production requirements.
- **Database Rules:** Connect using the native MySQL driver (e.g. PDO). **Do not use an ORM**. You must use prepared statements for all database interactions. Raw string interpolation for SQL queries is strictly forbidden.

## 5. Frontend & UI Directives
- **Stack Limitations:** Stick strictly to Vanilla JavaScript (ES6+), semantic HTML5, and vanilla CSS3. **Do not use React, Vue, Svelte, or any heavy frontend frameworks.**
- **Responsiveness:** Ensure layouts are highly responsive and accessible on both mobile and desktop. Refrain from importing heavy external JS/CSS dependencies unless explicitly approved by the user.
- **Automated Layout Testing:** After every substantial UI or structural change, you must automatically run the Playwright E2E suite (`npx playwright test`) to verify that the layouts correctly constrain to mathematical device viewports without overflowing.
- **Separation of Concerns:** HTML, CSS, and JS logic must be completely decoupled into separate files. Inline styles (`style="..."`) and inline event handlers (`onclick="..."`) are strictly prohibited in the markup.
- **Validation:** ESLint must be utilized to catch syntax errors and undefined variables prior to any commit (`npm run lint`).
