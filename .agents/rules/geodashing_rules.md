---
trigger: always_on
description: Core constraints, architectural directives, and coding standards for the Geodashing V2 project.
---

# Geodashing V2 Context & Directives

You are working on the Geodashing V2 project. You must strictly adhere to these constraints and coding standards at all times to ensure project consistency.

## 1. Core Operating Principles
- **Scope Constriction:** Implement strictly what is explicitly requested. Do not over-engineer solutions or add unrequested "nice-to-have" features.
- **Resilient Execution:** Always wrap file I/O operations, database queries, and external network/API requests in robust error handling blocks (`try/except` in Python, `try/catch` in JS/PHP). Always fail gracefully.
- **Security Posture:** Never commit secrets, credentials, or API keys. Hardcode no sensitive data. Credentials must be read from files that are not tracked in .git, or other means to keep them from being exposed in github or source control.
- **Version Control:** When asked to generate commit messages, mandate the Conventional Commits format (e.g., `feat: [message]`, `fix: [message]`).

## 2. Infrastructure Target Versions
Ensure all code and syntax is explicitly compatible with the following versions:
- **PHP:** `8.3.6`
- **MySQL:** `8.4.8`
- **Python:** `3.12`

## 3. Backend Directives: Python
- **Syntax / Style:** Strictly follow PEP 8. Type hints are absolutely mandatory for all function signatures and complex variables.
- **Documentation:** Use Google-style docstrings for all modules, classes, and exposed functions.
- **Testing:** Use `pytest`. Test core logic rigorously.
- **Dependencies:** Manage dependencies using standard `pip` with a virtual environment (venv) and maintain an up-to-date `requirements.txt`.
- **Database Rules:** Connect using `mysql-connector-python`. **Do not use an ORM**. You must use strictly parameterized queries / prepared statements for all database interactions. String interpolation or concatenation for SQL queries is strictly forbidden to prevent SQL injections.

## 4. Backend Directives: PHP
- **Documentation:** Utilize clear PHPDoc-style block comments (`/** ... */`) for functions, classes, and properties.
- **Testing:** Employ `PHPUnit` for all backend unit testing.
- **Database Rules:** Connect using the native MySQL driver (e.g. PDO). **Do not use an ORM**. You must use prepared statements for all database interactions. Raw string interpolation for SQL queries is strictly forbidden.

## 5. Frontend & UI Directives
- **Stack Limitations:** Stick strictly to Vanilla JavaScript (ES6+), semantic HTML5, and vanilla CSS3. **Do not use React, Vue, Svelte, or any heavy frontend frameworks.**
- **Responsiveness:** Ensure layouts are highly responsive and accessible on both mobile and desktop. Refrain from importing heavy external JS/CSS dependencies unless explicitly approved by the user.
- **Separation of Concerns:** HTML, CSS, and JS logic must be completely decoupled into separate files. Inline styles (`style="..."`) and inline event handlers (`onclick="..."`) are strictly prohibited in the markup.