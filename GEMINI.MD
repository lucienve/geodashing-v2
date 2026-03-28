# Development Guidelines
## Global Rules
* **No Unrequested Features:** Implement only what is explicitly asked for in the prompt. Do not over-engineer or add "nice-to-have" features unless approved.
* **Error Handling:** Always include try/except blocks for file I/O, database connections, and external requests. Fail gracefully.

## Backend (Python)
* **Style:** Strictly adhere to PEP 8 standards.  Use type hints.
* **Testing:** Write unit tests using `pytest` for all core logic, especially for the geographical distance calculations (Haversine formula) and the 500m water-exclusion logic.
* **Documentation:** Use clear docstrings (Google style) for all functions and classes.
* **Dependencies:** Use `pip` and a `requirements.txt` file for dependency management.
* **Database:** Use the `mysql-connector-python` (or PHP equivalent) driver; do not use an ORM. Use parameterized queries or prepared statements for all MySQL interactions to prevent SQL injection. Do not use raw string interpolation for SQL queries.

## Backend (PHP)
* **Style:** Strictly adhere to PSR standards.
* **Database:** Use the mysql driver; do not use an ORM. Use prepared statements for all MySQL interactions to prevent SQL injection. Do not use raw string interpolation for SQL queries.
* **Testing:** Use PHPUnit for unit testing.
* **Documentation:** Use clear docstrings (PHPDoc style) for all functions and classes.

## Frontend (Vanilla JS/HTML/CSS)
* **Frameworks:** Do not introduce React, Vue, or other heavy frameworks. Stick strictly to vanilla JavaScript (ES6+), semantic HTML5, and CSS3.
* **Performance:** Code must be usable by mobile browsers and desktop browsers alike. Avoid heavy libraries unless there is a compelling reason.
* **Separation of Concerns:** Keep HTML, CSS, and JS in separate files. Do not use inline styles or inline event handlers.

## Git & Version Control
* **Commit Messages:** If asked to generate a commit message, use the Conventional Commits format (e.g., `feat: add distance calculation logic`, `fix: correct tie-breaking query`).
* **Secrets:** Do not commit secrets, API keys, or sensitive credentials to version control. Use `.env` files for local development configuration and ensure they are added to `.gitignore`.