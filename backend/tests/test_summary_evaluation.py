"""End-to-end evaluation tests for Gemini models and system instructions."""
# pylint: disable=protected-access
# Accessing the internal _generate_summary helper function is necessary
# in this test to evaluate the system instruction prompt pipeline in isolation.

import configparser
import os
import re
import html.parser
import pytest
import pydantic
import google.genai
import google.genai.types

import backend.scripts.generate_summary

# Skip all tests in this module unless RUN_LIVE_API_EVAL=1 is set in the environment
pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_API_EVAL") != "1",
    reason="Live Gemini API evaluation runs on-demand only. "
           "Set RUN_LIVE_API_EVAL=1 to execute."
)


class EvaluationResult(pydantic.BaseModel):
    """Pydantic schema for structured evaluation from the LLM judge."""
    tone_score: int = pydantic.Field(
        ...,
        description="Score from 1 to 5 indicating if the tone is enthusiastic, "
                    "observational, and community-focused."
    )
    accuracy_score: int = pydantic.Field(
        ...,
        description="Score from 1 to 5 indicating if the summary accurately "
                    "reflects the stats (winners, runners up) without fabrication."
    )
    narrative_quality: int = pydantic.Field(
        ...,
        description="Score from 1 to 5 indicating if quotes and waypoints "
                    "are formatted correctly and are engaging."
    )
    justification: str = pydantic.Field(
        ...,
        description="Detailed review of the summary, explaining the scores, "
                    "noting any specific shortcomings or praise."
    )
    passed: bool = pydantic.Field(
        ...,
        description="True if the output meets all qualitative standards (scores >= 4)."
    )


class SummaryHTMLValidator(html.parser.HTMLParser):
    """Custom parser to validate strict HTML restrictions in generated summaries."""

    def __init__(self) -> None:
        super().__init__()
        self.errors: list[str] = []
        self.allowed_tags = {
            'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'div', 'span', 'br', 'hr',
            'strong', 'b', 'em', 'i', 'u', 'code', 'pre', 'blockquote',
            'ul', 'ol', 'li', 'a', 'img'
        }
        self.tag_stack: list[str] = []
        self.after_sampling_header = False
        self.current_anchor_href: str | None = None
        self.inside_anchor = False
        self.current_paragraph_chunks: list[str] | None = None

    def _check_anchor(self, href: str) -> None:
        """Validates SPA link absolute formats and profile username encodings."""
        if "#profile?username=" in href or "#dashpoint?id=" in href:
            if not href.startswith("https://www.geodashing.org/"):
                self.errors.append(
                    f"SPA link '{href}' does not start with absolute "
                    "base URL 'https://www.geodashing.org/'"
                )

        if "#profile?username=" in href:
            username_part = href.split("username=")[-1]
            if " " in username_part:
                self.errors.append(
                    f"Username in profile link contains unencoded spaces: {href}"
                )
            if "+" in username_part:
                self.errors.append(
                    f"Username in profile link contains + instead of %20: {href}"
                )

    def _check_image(self, attrs_dict: dict[str, str]) -> None:
        """Validates image tags, attribute presence, and thumbnail wrapping."""
        src = attrs_dict.get('src', '')
        alt = attrs_dict.get('alt', '')
        title = attrs_dict.get('title', '')
        if not src:
            self.errors.append("Image tag is missing the 'src' attribute")
        if not alt:
            self.errors.append("Image tag is missing the 'alt' description")
        if not title:
            self.errors.append("Image tag is missing the 'title' hovertext")

        if not self.inside_anchor:
            self.errors.append(
                f"Image tag src='{src}' is not wrapped in an anchor link (<a>)"
            )
        else:
            if self.current_anchor_href == src and "thumb" in src:
                self.errors.append(
                    "Anchor link wraps thumbnail but links to the same "
                    f"thumbnail: {src}"
                )

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tag_stack.append(tag)
        attrs_dict = {name: val for name, val in attrs if val is not None}

        if tag not in self.allowed_tags:
            self.errors.append(f"Forbidden HTML tag found: <{tag}>")

        if tag == 'h3':
            self.after_sampling_header = True

        if tag in ('hr', 'h2'):
            self.after_sampling_header = False

        if tag == 'p' and self.after_sampling_header:
            self.current_paragraph_chunks = []

        if tag == 'a':
            self.inside_anchor = True
            href = attrs_dict.get('href', '')
            self.current_anchor_href = href
            self._check_anchor(href)

        if tag == 'img':
            self._check_image(attrs_dict)

    def handle_endtag(self, tag: str) -> None:
        if self.tag_stack and self.tag_stack[-1] == tag:
            self.tag_stack.pop()

        if tag == 'p' and self.current_paragraph_chunks is not None:
            full_text = "".join(self.current_paragraph_chunks).strip()
            if full_text:
                match = re.search(r'[a-zA-Z]', full_text)
                if match:
                    first_char = match.group(0)
                    if first_char.isupper():
                        self.errors.append(
                            "Sampling waypoint entry starts with an uppercase "
                            f"letter: '{full_text[:35]}...'"
                        )
            self.current_paragraph_chunks = None

        if tag == 'a':
            self.inside_anchor = False
            self.current_anchor_href = None

    def handle_data(self, data: str) -> None:
        if self.current_paragraph_chunks is not None:
            self.current_paragraph_chunks.append(data)


def _parse_scores(score_text: str) -> list[tuple[str, int]]:
    """Helper to parse winners and runner-ups from scores section."""
    scores: list[tuple[str, int]] = []
    winner_match = re.search(
        r'Winner(?:s \(tied\))?:\s*(.*?)\s+with\s+(\d+)\s+point',
        score_text
    )
    if winner_match:
        names_str = winner_match.group(1)
        points = int(winner_match.group(2))
        names = [n.strip() for n in names_str.split(',')]
        for name in names:
            scores.append((name, points))

    other_matches = re.findall(r'-\s*(.*?):\s*(\d+)\s+point', score_text)
    for name, pts in other_matches:
        scores.append((name.strip(), int(pts)))
    return scores


def _parse_single_log(dp_id: str, block_content: str) -> backend.scripts.generate_summary.LogEntry:
    """Parses a single player log content block to extract notes and photos."""
    player_match = re.search(r'^Player:\s*([^\n]+)', block_content, re.MULTILINE)
    player = player_match.group(1).strip() if player_match else "Unknown"

    rest = re.sub(r'^Player:\s*[^\n]+\n*', '', block_content, flags=re.MULTILINE).strip()

    city_match = re.search(r'^[A-Z0-9-]+\s+is\s+near\s+([^\n.]+)', rest, re.MULTILINE)
    city = city_match.group(1).strip() if city_match else "Unknown Location"

    photos: list[dict[str, str]] = []
    photos_section_match = re.search(
        r'Photos:\n(.*?)(?=\n\n|\n[A-Z0-9-]+ is near|\Z)',
        rest,
        re.DOTALL
    )
    if photos_section_match:
        photos_text = photos_section_match.group(1)
        pairs = re.findall(r'Thumb:\s*([^\s|]+)\s*\|\s*Full:\s*([^\s]+)', photos_text)
        for thumb, full in pairs:
            photos.append({'thumb_url': thumb, 'url': full})

        single_fulls = re.findall(r'Full:\s*([^\s]+)', photos_text)
        for full in single_fulls:
            if not any(p['url'] == full for p in photos):
                photos.append({'thumb_url': full, 'url': full})

        rest = rest.replace(photos_section_match.group(0), "").strip()

    if city_match:
        rest = rest.replace(city_match.group(0), "").strip()

    rest = re.sub(r'Image Content:\n\[IMAGE DATA DETACHED\]', '', rest).strip()
    notes = rest if rest else None

    return {
        'dp_id': dp_id,
        'username': player,
        'city': city,
        'photos': photos,
        'notes': notes
    }


def _parse_logs(file_content: str) -> list[backend.scripts.generate_summary.LogEntry]:
    """Helper to parse player logs and metadata from raw text logs."""
    logs: list[backend.scripts.generate_summary.LogEntry] = []
    log_blocks = re.split(r'-{21,}\nLog:\s*([^\n]+)\.txt\n-{21,}', file_content)
    if len(log_blocks) <= 1:
        return logs

    for i in range(1, len(log_blocks), 2):
        logs.append(_parse_single_log(log_blocks[i].strip(), log_blocks[i + 1]))
    return logs


def parse_benchmark_input(
    file_content: str
) -> tuple[
    str,
    list[tuple[str, int]],
    list[backend.scripts.generate_summary.LogEntry]
]:
    """Parses static text representation of game logs back into structured data."""
    game_title = "Game"
    title_match = re.search(r'--- GAME TITLE ---\n([^\n]+)', file_content)
    if title_match:
        game_title = title_match.group(1).strip()

    scores: list[tuple[str, int]] = []
    score_section_match = re.search(
        r'--- SCORE RANKINGS ---\n(.*?)(?=\n---|\n---------------------)',
        file_content,
        re.DOTALL
    )
    if score_section_match:
        scores = _parse_scores(score_section_match.group(1))

    logs = _parse_logs(file_content)
    return game_title, scores, logs


def validate_deterministic_rules(html_content: str) -> list[str]:
    """Applies strict parser checks and regex verifications on raw generated HTML."""
    parser = SummaryHTMLValidator()
    parser.feed(html_content)
    errors = parser.errors

    if re.search(r'<br(?!\s*/>)', html_content):
        errors.append("Void tag <br> must be formatted as self-closing: <br />")
    if re.search(r'<hr(?!\s*/>)', html_content):
        errors.append("Void tag <hr> must be formatted as self-closing: <hr />")
    if re.search(r'<img(?![^>]*/>)', html_content):
        errors.append("Void tag <img> must be formatted as self-closing: <img ... />")

    placeholders = ["[Location]", "[Player]", "[Game Title]", "[Number]"]
    for p in placeholders:
        if p in html_content:
            errors.append(f"Remnant placeholder token '{p}' found in output summary")

    quotes_matches = re.findall(
        r'<blockquote>(.*?)</blockquote>\s*<p>(.*?)</p>',
        html_content,
        re.DOTALL
    )
    for _, attribution in quotes_matches:
        if 'lucienve' in attribution.lower():
            errors.append("User 'lucienve' was featured in a quote or attribution line")

    first_tag_match = re.search(r'^\s*<h2[^>]*>(.*?)</h2>', html_content, re.DOTALL)
    if not first_tag_match:
        errors.append("Output must start with an <h2> results title header")
    elif "results:" not in first_tag_match.group(1).lower():
        errors.append(f"Header <h2> must start with 'Results:': '{first_tag_match.group(1)}'")

    return errors


def evaluate_summary_quality(
    client: google.genai.Client,
    judge_model: str,
    input_text: str,
    generated_html: str
) -> EvaluationResult:
    """Invokes the judge LLM with a Pydantic response schema to score the summary quality."""
    prompt = f"""
You are the Quality Assurance Judge for the Geodashing Game Administrator summary generator.
Your role is to evaluate a generated HTML summary against the raw input logs and score rankings.

Evaluation Criteria:
1. Tone (1-5): The tone must be enthusiastic, observational, and community-focused. It should celebrate the players' journeys.
2. Accuracy (1-5): Ensure that the game title, winning player/team, scores, and country counts match the raw input data exactly. There must be no fabricated facts, names, or scores.
3. Narrative Quality (1-5): The featured quotes should be interesting and directly extracted from the logs (excluding user 'lucienve'). The sampling list must have lowercase prepositions, link to dashpoints correctly, and capture the essence of the logs.

[RAW INPUT DATA SET]
{input_text}

[GENERATED HTML SUMMARY]
{generated_html}

Evaluate the summary and return the scores, justification, and a final verdict. The final verdict 'passed' should be True only if all scores are 4 or 5.
"""

    response = client.models.generate_content(
        model=judge_model,
        contents=prompt,
        config=google.genai.types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=EvaluationResult
        )
    )

    result_text = response.text
    if not result_text:
        raise ValueError("Judge model returned an empty response")

    return EvaluationResult.model_validate_json(result_text)


def _get_eval_config(cfg_p: str) -> tuple[dict, google.genai.Client, str]:
    """Extracts candidate and judge configurations and OAuth clients."""
    ai_config = backend.scripts.generate_summary.configure_environment(cfg_p)
    client = backend.scripts.generate_summary.get_gemini_client(ai_config)

    config = configparser.ConfigParser()
    config.read(cfg_p)
    judge_model = "gemini-3.6-flash"
    if 'gemini' in config and 'GEMINI_EVAL_MODEL' in config['gemini']:
        val = config['gemini']['GEMINI_EVAL_MODEL']
        if val:
            judge_model = val.strip('"\'')
    return ai_config, client, judge_model


# pylint: disable=duplicate-code
# This duplicate code block is architecturally necessary because the test suite
# replicates the local temp file and remote GenAI file cleanup logic from
# generate_summary.py to ensure identical resource hygiene under test conditions.
def _cleanup_context(
    client: google.genai.Client,
    upload_context: backend.scripts.generate_summary.UploadContext
) -> None:
    """Closes and deletes all local temporary files and uploaded remote assets."""
    for local_file in upload_context["local_temp_files"]:
        try:
            if os.path.exists(local_file):
                os.unlink(local_file)
        except OSError as e:
            print(f"Failed to delete local temp file {local_file}: {e}")

    for uploaded_file in upload_context["uploaded_ai_files"]:
        try:
            if uploaded_file.name:
                client.files.delete(name=uploaded_file.name)
        except Exception as e:  # pylint: disable=broad-exception-caught
            print(f"Failed to delete remote AI Studio file {uploaded_file.name}: {e}")


def _load_benchmark_input(exs_d: str, prefix: str) -> str:
    """Reads the static benchmark input text file."""
    input_file_path = os.path.join(exs_d, f"{prefix}_input.txt")
    with open(input_file_path, 'r', encoding='utf-8') as f:
        return f.read()


@pytest.mark.parametrize("prefix", ["example_1", "example_2", "game_1", "game_2"])
def test_evaluate_benchmark_summary(prefix: str) -> None:
    """Runs the full E2E evaluation against a benchmark case."""
    c_dir = os.path.dirname(os.path.abspath(__file__))
    exs_d = os.path.join(c_dir, '../../data/summary_examples/')

    ai_config, client, judge_model = _get_eval_config(os.path.join(c_dir, '../config.ini'))

    raw_input_text = _load_benchmark_input(exs_d, prefix)
    parsed = parse_benchmark_input(raw_input_text)
    upload_context: backend.scripts.generate_summary.UploadContext = {
        "client": client,
        "local_temp_files": [],
        "uploaded_ai_files": []
    }

    try:
        prompt = backend.scripts.generate_summary.construct_new_data(
            parsed[0], parsed[1], parsed[2], upload_context
        )

        candidate_model = ai_config['model_name']
        assert candidate_model is not None
        inst_p = os.path.join(c_dir, '../../data/summary_system_instructions.txt')
        generated_html = backend.scripts.generate_summary._generate_summary(
            client, candidate_model, inst_p, exs_d, prompt
        )

        assert generated_html, "Candidate model returned an empty summary"

        # Tier 1: Deterministic Checks
        html_errors = validate_deterministic_rules(generated_html)
        assert not html_errors, (
            f"HTML Rule Violations for {prefix}:\n" + "\n".join(html_errors)
        )

        # Tier 2: Qualitative Evaluation (LLM-as-a-Judge)
        eval_result = evaluate_summary_quality(
            client, judge_model, raw_input_text, generated_html
        )

        # Print detailed diagnostic report
        print(f"\n--- Evaluation Report for {prefix} ---")
        print(f"Candidate Model: {candidate_model}")
        print(f"Judge Model: {judge_model}")
        print(f"Scores -> Tone: {eval_result.tone_score}/5 | "
              f"Accuracy: {eval_result.accuracy_score}/5 | "
              f"Narrative: {eval_result.narrative_quality}/5")
        print(f"Justification: {eval_result.justification}")
        print(f"Passed: {eval_result.passed}")

        assert eval_result.tone_score >= 4, (
            f"Tone score below threshold: {eval_result.tone_score}"
        )
        assert eval_result.accuracy_score >= 4, (
            f"Accuracy score below threshold: {eval_result.accuracy_score}"
        )
        assert eval_result.narrative_quality >= 4, (
            f"Narrative quality score below threshold: "
            f"{eval_result.narrative_quality}"
        )
        assert eval_result.passed, "Judge model did not pass the output summary"

    finally:
        _cleanup_context(client, upload_context)
