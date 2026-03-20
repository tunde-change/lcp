import json
import re
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

_PERCENT_PATTERN = re.compile(r"\s+([0-9]+\.?[0-9]*)%\s+([0-9]+\.?[0-9]*)%")


def _normalize(text: str) -> str:
    return text.replace("Selﬂess", "Selfless")


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
