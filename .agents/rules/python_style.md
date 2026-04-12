---
trigger: always_on
description: Python coding standards, testing, and stylistic requirements.
---

# Python Directives

You must strictly adhere to these coding standards at all times to ensure consistent Python code quality.

## Python Formatting & Style
- **Syntax / Style:** Strictly follow the Google Python Style Guide (https://google.github.io/styleguide/pyguide.html). Type hints are absolutely mandatory for all function signatures and complex variables. Crucially, strictly adhere to the import rule: use `import package` or `import module` and namespace your calls. Do not use `from module import function_or_class` (except for `typing`).
- **Linting:** Automatically invoke `pylint` against any modified Python files and strictly resolve any lint warnings, unused imports, or trailing whitespaces before returning the code.
- **Documentation:** Use Google-style docstrings for all modules, classes, and exposed functions.
- **Testing:** Use `pytest` for python. Test core logic rigorously.
- **Dependencies:** Manage dependencies using standard `pip` with a virtual environment (venv) and maintain an up-to-date `requirements.txt`.
