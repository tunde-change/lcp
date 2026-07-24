import json
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Tuple

BASE_DIR = Path(__file__).parent
DEFINITIONS_PATH = BASE_DIR / "lcp_definitions.json"

with open(DEFINITIONS_PATH, "r") as f:
    LCP_DEFINITIONS: Dict[str, List[str]] = json.load(f)

CREATIVE_DIMENSIONS: List[str] = [
    "Caring Connection",
    "Fosters Team Play",
    "Collaborator",
    "Mentoring & Developing",
    "Interpersonal Intelligence",
    "Selfless Leader",
    "Balance",
    "Composure",
    "Personal Learner",
    "Integrity",
    "Courageous Authenticity",
    "Community Concern",
    "Sustainable Productivity",
    "Systems Thinker",
    "Strategic Focus",
    "Purposeful & Visionary",
    "Achieves Results",
    "Decisiveness",
]

REACTIVE_DIMENSIONS: List[str] = [
    "Perfect",
    "Driven",
    "Ambition",
    "Autocratic",
    "Arrogance",
    "Critical",
    "Distance",
    "Passive",
    "Belonging",
    "Pleasing",
    "Conservative",
]

ALL_DIMENSIONS = CREATIVE_DIMENSIONS + REACTIVE_DIMENSIONS

# Handles both report layouts:
#   v1.1.1  "Caring Connection 80.0% 88.0%"
#   v1.5    "Caring Connection 80 % 88 % - 80 % 86 % - -"   (Self, then Evaluators)
_PERCENT_PATTERN = re.compile(r"\s*([0-9]+\.?[0-9]*)\s*%\s*([0-9]+\.?[0-9]*)\s*%")


def _normalize(text: str) -> str:
    return text.replace("Selﬂess", "Selfless")


EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

# v1.1.1 header: "Leadership Circle Profile | v1.1.1 | NEELAM RATHOD - English | 2026-05-11"
# v1.5 header:   "LEADERSHIP CIRCLE PROFILE(TM) ... Tunde Lukacs  - English<date>"
_HEADER_NAME = re.compile(r"(?m)^(?:.*\|\s*)?([^|\n]{2,60}?)\s+-\s+[A-Za-zÀ-ÿ]{2,12}(?:[\s|(]|$)")
# v1.1.1 page footer: "Neelam Rathod: 2026-05-11"
_FOOTER_NAME = re.compile(r"([A-ZÀ-Þ][\w'’\-]+(?:\s+[A-ZÀ-Þ][\w'’\-]+){0,3})\s*:\s*\d{4}-\d{2}-\d{2}")
# v1.5 page footer: "(c) The Leadership Circle 2026 Tunde Lukacs page 3"
_COPYRIGHT_NAME = re.compile(r"©\s*The Leadership Circle\s+\d{4}\s+(.{2,60}?)\s+page\s+\d+", re.IGNORECASE)

_DIMENSION_WORDS = {d.lower() for name in ALL_DIMENSIONS for d in name.split()}


_NAME_NOISE = (
    "leadership circle",
    "the leadership",
    "percentile",
    "profile",
    "self",
    "evaluator",
    "report",
    "copyright",
)


def _plausible_name(candidate: str) -> str:
    cleaned = " ".join(candidate.replace("™", " ").split()).strip(" .,:-")
    if not 2 <= len(cleaned) <= 60:
        return ""
    lowered = cleaned.lower()
    if any(noise in lowered for noise in _NAME_NOISE):
        return ""
    if any(ch.isdigit() for ch in cleaned):
        return ""
    return cleaned


def detect_client_name(text: str) -> str:
    """Best guess at the profile owner's name, from the report header or the page footers.

    Covers both known LCP layouts. Returns "" when unsure, so the UI asks the user.
    """
    repeated: List[str] = [m.group(1) for m in _FOOTER_NAME.finditer(text)]
    repeated += [m.group(1) for m in _COPYRIGHT_NAME.finditer(text)]
    repeated = [n for n in (_plausible_name(n) for n in repeated) if n]
    if repeated:
        return max(set(repeated), key=repeated.count)

    for match in _HEADER_NAME.finditer(text[:1500]):
        name = _plausible_name(match.group(1))
        if name:
            return name
    return ""


def build_removal_terms(name: str, extra: str = "") -> List[str]:
    """Split a name and any extra terms into individual words/phrases worth removing."""
    terms: List[str] = []
    for chunk in [name] + [line for line in re.split(r"[,\n;]", extra)]:
        chunk = " ".join(chunk.split())
        if not chunk:
            continue
        terms.append(chunk)
        if " " in chunk:
            terms.extend(part for part in chunk.split(" ") if len(part) > 2)

    unique: List[str] = []
    for term in terms:
        if len(term) < 3:
            continue
        if term not in unique:
            unique.append(term)
    unique.sort(key=len, reverse=True)  # longest first, so "Neelam Rathod" goes before "Neelam"
    return unique


def dimension_collisions(terms: List[str]) -> List[str]:
    """Terms that are also part of an LCP dimension name, for example a client called Grace Perfect.

    These are still removed, because a name must never leak. The caller should warn that the
    matching dimension label will look redacted in the text the model sees.
    """
    return [t for t in terms if t.lower() in _DIMENSION_WORDS]


_ACCENT_GROUPS = [
    "aàáâäãåāăą", "eèéêëēĕėęě", "iìíîïĩīĭįı", "oòóôöõøōŏő", "uùúûüũūŭůűų",
    "cçćĉċč", "nñńņň", "sśŝşš", "zźżž", "yýÿŷ", "gĝğġģ", "lĺļľłŀ", "rŕŗř", "tţťŧ", "dďđ",
]
_ACCENT_CLASS = {group[0]: group for group in _ACCENT_GROUPS}


def _fold(char: str) -> str:
    stripped = "".join(c for c in unicodedata.normalize("NFKD", char) if not unicodedata.combining(c))
    return stripped or char


def _term_pattern(term: str) -> str:
    """Match a name regardless of accents or odd spacing, so "Tunde" also catches "Tünde"."""
    parts = []
    for char in term:
        if char.isspace():
            parts.append(r"\s+")
            continue
        base = _fold(char).lower()
        group = _ACCENT_CLASS.get(base)
        parts.append(f"[{group}{group.upper()}]" if group else re.escape(char))
    return "".join(parts)


def scrub_text(text: str, terms: List[str], placeholder: str = "[CLIENT]") -> Tuple[str, Dict[str, int]]:
    """Remove identifiers before anything leaves the app. Returns the scrubbed text and a hit count."""
    report: Dict[str, int] = {}
    scrubbed = text

    for term in terms:
        # No word boundaries on purpose. PDF extraction glues words together
        # ("...step intoNeelam Rathod: 2026-05-11"), and a boundary would let those through.
        # Over-redacting a few characters is the safer failure.
        pattern = re.compile(_term_pattern(term), re.IGNORECASE)
        scrubbed, hits = pattern.subn(placeholder, scrubbed)
        if hits:
            report[term] = hits

    scrubbed, email_hits = EMAIL_PATTERN.subn("[EMAIL]", scrubbed)
    if email_hits:
        report["email addresses"] = email_hits

    return scrubbed, report


def remaining_identifiers(scrubbed: str, terms: List[str]) -> List[str]:
    """Terms that still appear after scrubbing. Should always be empty; a safety net."""
    return [t for t in terms if re.search(re.escape(t), scrubbed, re.IGNORECASE)]


def extract_dimension_scores(text: str) -> Dict[str, Dict[str, float]]:
    scores: Dict[str, Dict[str, float]] = {}
    normalized = _normalize(text)
    for name in ALL_DIMENSIONS:
        pattern = re.compile(rf"{re.escape(name)}{_PERCENT_PATTERN.pattern}")
        match = pattern.search(normalized)
        if match:
            scores[name] = {
                "self": float(match.group(1)),
                "evaluators": float(match.group(2)),
            }
    return scores


def pick_top_dimensions(
    scores: Dict[str, Dict[str, float]],
    dimension_list: List[str],
    count: int = 2,
) -> List[Tuple[str, Dict[str, float]]]:
    filtered = [(name, scores[name]) for name in dimension_list if name in scores]
    filtered.sort(key=lambda item: item[1]["evaluators"], reverse=True)
    return filtered[:count]


def get_definition_sections(scores: Dict[str, Dict[str, float]]):
    sections = []
    creative = pick_top_dimensions(scores, CREATIVE_DIMENSIONS, 2)
    reactive = pick_top_dimensions(scores, REACTIVE_DIMENSIONS, 2)

    for label, payload in creative:
        sections.append(
            {
                "name": label,
                "type": "Creative",
                "self": payload["self"],
                "evaluators": payload["evaluators"],
                "statements": LCP_DEFINITIONS.get(label, []),
            }
        )

    for label, payload in reactive:
        sections.append(
            {
                "name": label,
                "type": "Reactive",
                "self": payload["self"],
                "evaluators": payload["evaluators"],
                "statements": LCP_DEFINITIONS.get(label, []),
            }
        )

    return sections


def render_definition_markdown(scores: Dict[str, Dict[str, float]]) -> str:
    sections = get_definition_sections(scores)
    if not sections:
        return "Could not parse the precise dimension percentiles from this PDF.\n"

    blocks = []
    for item in sections:
        statements = item["statements"]
        if statements:
            bullets = "\n".join(f"- {stmt}" for stmt in statements)
        else:
            bullets = "_No official statements found for this dimension._"

        blocks.append(
            "\n".join(
                [
                    f"#### {item['name']} ({item['type']})",
                    f"- Evaluators: {item['evaluators']:.1f}%  |  Self: {item['self']:.1f}%",
                    "",
                    "**Official Survey Statements**",
                    bullets,
                ]
            )
        )

    return "\n\n".join(blocks)
