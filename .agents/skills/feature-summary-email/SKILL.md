---
name: feature-summary-email
description: >-
  Draft and format monthly player-facing development summary emails for
  Geodashing, highlighting user-visible features and generating a
  Gmail-compatible HTML copy preview.
---

# Feature Summary Email

Use this skill when drafting, generating, or preparing monthly development
update emails for Geodashing players on the mailing list
(`dashers@geodashing.org`).

## Overview

Geodashing development updates are published approximately monthly to inform
players of new gameplay mechanics, user interface improvements, and field
logging tools. The process tracks commit history via Git tags, isolates
player-facing enhancements, and formats the summary into a theme-neutral HTML
preview artifact so rich text can be pasted into Gmail on Windows without losing
formatting.

---

## Workflow Steps

### 1. Identify the Commit Range

1. Find the most recent feature summary Git tag:

   ```bash
   git tag -l "email-summary/*" --sort=-creatordate | head -n 1
   ```

2. Inspect all commits introduced since that tag:

   ```bash
   git log <latest-email-tag>..HEAD --oneline
   ```

3. Cross-reference new commits with
   [project_context.md](../../../docs/project_context.md) to understand recent
   features, and inspect UI templates in `public/templates/` and controllers in
   `public/js/controllers.js` to ensure button labels, navigation paths, and
   terminology match the live application.

### 2. Filter for Player-Visible Features

Isolate changes that directly impact the player experience:

- **Include:**
  - Gameplay mechanics (e.g., dashpoint generation algorithms, minimum
    separation rules, preview game rollovers).
  - Map display and navigation (e.g., zoom preservation, visit markers,
    clustering).
  - Field logging and forms (e.g., offline draft saving, coordinate lock
    safeguards, photo attachment guidance).
  - Planning and export tools (e.g., private dashpoint tagging, multi-stop
    Google Maps route builder, GPX/KML export).
  - Account and profile management (e.g., mailing list subscription
    self-service).
  - Any specific contextual notes or community acknowledgments provided by the
    user.
- **Exclude:**
  - Internal refactoring, style guide standardizations, and linter fixes.
  - Dependency upgrades (Composer, npm, uv/Python).
  - CI/CD workflows, test runner configurations, and pre-commit hooks.
  - Cloud infrastructure management (Terraform, Cloud Batch, Artifact Registry).

### 3. Draft the Summary and Generate a Gmail Copy Preview

Draft a clear, friendly summary organized by logical feature areas.

Because the development environment runs within WSL under Windows 11, pasting
raw chat text or using WSL CLI clipboard utilities (`wl-copy`, `xclip`) into a
Windows browser will lose HTML formatting or fail due to clipboard format
incompatibilities (Windows requires `CF_HTML`).

To ensure rich text pastes cleanly into Gmail:

1. Present the draft text directly in the chat for review.
2. Generate an HTML preview artifact in the conversation artifact directory
   (e.g., `email_preview.html`) adhering to the `generative_ui` pattern.
3. In the preview artifact, provide:
   - A **Copy Subject** button.
   - A **Copy Body for Gmail** button that loads both `text/html` and
     `text/plain` MIME types into the Windows clipboard using
     `navigator.clipboard.write([new ClipboardItem(...)])` with an
     `execCommand('copy')` fallback.
   - A clean, theme-neutral HTML payload (`CLEAN_GMAIL_HTML`) using inline
     margins and standard typography (`<p>`, `<h3>`, `<ul>`, `<li>`, `<strong>`,
     `<a>`) with zero CSS dark-mode styles or CSS variables, ensuring the pasted
     email renders properly in light-mode email clients.

### 4. Tag the Sent Commit

After the user reviews and confirms that the email has been dispatched to the
mailing list, create an annotated Git tag on the corresponding commit:

```bash
git tag -a email-summary/YYYY-MM-DD -m "Feature summary email covering <highlights>"
```

_(Note: Staging or Git tag mutation commands require `BypassSandbox: true`.)_
