---
trigger: always_on
description: Core operating principles and code philosophy.
---

# Core Operating Principles

You must strictly adhere to these fundamental principles during execution:

- **Scope Constriction:** Implement strictly what is explicitly requested. Do not over-engineer solutions or add unrequested "nice-to-have" features.
- **Resilient Execution:** Always wrap file I/O operations, network/API requests, and critical data mutations in robust error handling blocks. Always fail gracefully.
- **Security Posture:** Never commit secrets, credentials, or API keys. Do not hardcode sensitive data. Credentials must be read from environment variables or files that are not tracked in source control.
- **Comment Style:** Maintain a calm, professional, and informative tone in all code comments. Do not use exclamation marks or overly dramatic language (e.g., "explosively", "rigidly", "physically", "natively").

# Documentation Standards

- **Project Context:** Summarize the current plan, completed tasks, and architectural decisions into `docs/project_context.md`. You must aggressively keep this file up to date whenever major changes, structural decisions, or feature completions occur to ensure state persists successfully.
