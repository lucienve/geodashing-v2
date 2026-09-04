# Gemini Model and System Instructions Evaluation Suite

This directory contains an on-demand end-to-end evaluation suite to validate new Gemini models and changes to [summary_system_instructions.txt](../data/summary_system_instructions.txt). Since generative LLM outputs are qualitative and non-deterministic, this suite checks correctness via strict rule assertions and an LLM-as-a-Judge model rather than a simple string comparison.

---

## Purpose

When modifying system instructions or switching target models, it is easy to inadvertently introduce:
1.  **HTML Parsing Breaks:** e.g., missing self-closing tags (`<br>` instead of `<br />`) or illegal formatting tags.
2.  **Qualitative Drift:** e.g., tone shifting away from enthusiastic/community-focused, or poor choice of featured quotes.
3.  **Missing/Incorrect Anchors:** e.g., failing to link usernames to profiles or missing/broken image thumbnails.
4.  **Factuality Issues:** e.g., winner lists or stats that mismatch the raw input logs.

This suite runs candidate models against a static benchmark of historical games (located in [summary_examples](../data/summary_examples/)) to catch these regressions before deploying prompt or model changes to production.

---

## Configuration

To run the live API evaluation, you must configure your local environment with billable access to the Google AI Studio / Gemini API.

### 1. API Keys & Billing Setup
The test suite respects the standard config lookup logic. Ensure your [config.ini](../backend/config.ini) contains the following under the `[gemini]` section:

```ini
[gemini]
GEMINI_API_KEY = "your-api-key"
GEMINI_MODEL = "gemini-3.8-flash"  # The candidate model being validated
GEMINI_THINKING_LEVEL = "medium"   # Configurable thinking level (low/medium/high)
GEMINI_PROJECT_ID = "your-gcp-project-id"  # For project-level quota billing
GEMINI_EVAL_MODEL = "gemini-3.8-flash"  # The locked judge model (optional)
```

Alternatively, you can export `GEMINI_API_KEY` and `GOOGLE_APPLICATION_CREDENTIALS` into your shell environment variables.

---

## Running the Tests

To prevent unwanted API charges and speed up standard test execution, this E2E evaluation is skipped by default during normal runs of `pytest`. 

To run the evaluation manually on demand, set the `RUN_LIVE_API_EVAL=1` environment variable:

```bash
# Run the evaluation suite in verbose mode
RUN_LIVE_API_EVAL=1 pytest backend/tests/test_summary_evaluation.py -v
```

---

## How it Works

The evaluation is executed across three sequential check tiers:

### Tier 1: Deterministic Checks
A custom Python `HTMLParser` parses the generated HTML summary to enforce the following project rules:
*   **Whitelisted HTML Tags:** Only tags specified in the instructions are allowed (`h2`, `h3`, `h4`, `h5`, `h6`, `p`, `div`, `span`, `br`, `hr`, `strong`, `b`, `em`, `i`, `u`, `code`, `pre`, `blockquote`, `ul`, `ol`, `li`, `a`, `img`).
*   **XHTML Self-Closing Void Tags:** `<br />`, `<hr />`, and `<img />` tags must end strictly with ` />`.
*   **Profile Link URL-Encoding:** Every player profile hyperlink must match `https://www.geodashing.org/#profile?username=[username]` where spaces are URL-encoded as `%20`.
*   **Image Anchors:** Images must use pre-computed `thumb_url` paths wrapped in `<a>` tags pointing to the full-size `url`.
*   **Negative Checks:** Asserts that placeholder tokens like `[Location]` or the system username `lucienve` do not appear in the generated content.

### Tier 2: LLM-as-a-Judge
A separate judge model (defined by `GEMINI_EVAL_MODEL` or falling back to `gemini-3.8-flash`) evaluates the generated summary against the raw input text. The judge returns a structured JSON object scoring three criteria from 1 to 5:
*   **Tone:** Observational, enthusiastic, and community-focused.
*   **Accuracy:** Matches input score rankings and winner claims exactly.
*   **Narrative Quality:** Checks if the featured quotes and waypoints sampling list are well-selected and flow naturally.

If any score is less than `4/5`, the judge fails the test and prints a detailed justification.
