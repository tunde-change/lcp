import json
import os

ALIAS_MAP = {
    "Caring Connection": ["Caring Connection"],
    "Fosters Team Play": ["Fosters Team Play", "Fosters Team-Play"],
    "Collaborator": ["Collaborator"],
    "Mentoring & Developing": ["Mentoring Developing", "Mentoring & Developing"],
    "Interpersonal Intelligence": ["Interpersonal Intelligence"],
    "Selfless Leader": ["Selﬂess Leader", "Selfless Leader"],
    "Balance": ["Balance"],
    "Composure": ["Composure"],
    "Personal Learner": ["Personal Learner"],
    "Integrity": ["Integrity"],
    "Courageous Authenticity": ["Courageous Authenticity"],
    "Community Concern": ["Community Concern"],
    "Sustainable Productivity": ["Sustainable Productivity"],
    "Systems Thinker": ["Systems Thinker"],
    "Strategic Focus": ["Strategic Focus"],
    "Purposeful & Visionary": ["Purposeful & Visionary"],
    "Achieves Results": ["Achieves Results"],
    "Decisiveness": ["Decisiveness"],
    "Perfect": ["Perfect"],
    "Driven": ["Driven"],
    "Ambition": ["Ambition"],
    "Autocratic": ["Autocratic"],
    "Arrogance": ["Arrogance"],
    "Critical": ["Critical"],
    "Distance": ["Distance"],
    "Passive": ["Passive"],
    "Belonging": ["Belonging"],
    "Pleasing": ["Pleasing"],
    "Conservative": ["Conservative"],
}

alias_lookup = {alias.strip(): canonical for canonical, aliases in ALIAS_MAP.items() for alias in aliases}

base_dir = os.path.dirname(__file__)
source_path = os.path.join(base_dir, 'lcp_definitions_raw.txt')
output_path = os.path.join(base_dir, 'lcp_definitions.json')

STOP_PHRASES = (
    'Leadership Brand',
    'Outer Dimension Rankings',
    'Below you will find',
)

def clean_text(line: str) -> str:
    replacements = {
        '\ufb01': 'fi',
        '\ufb02': 'fl',
        '\u2019': "'",
        '\u2014': '-',
        '\u2013': '-',
    }
    for bad, good in replacements.items():
        line = line.replace(bad, good)
    return line.strip()

entries = {key: [] for key in ALIAS_MAP.keys()}
current = None
buffer = ""

with open(source_path, 'r') as f:
    for raw_line in f:
        line = clean_text(raw_line)
        if not line:
            continue

        if any(phrase in line for phrase in STOP_PHRASES):
            current = None
            buffer = ""
            continue

        if line.isupper() and len(line) > 2:
            current = None
            buffer = ""
            continue

        alias_hit = None
        remainder = ""
        for alias, canonical in alias_lookup.items():
            if line == alias:
                alias_hit = canonical
                break
            if line.startswith(alias):
                alias_hit = canonical
                remainder = line[len(alias):].strip()
                break
        if alias_hit:
            current = alias_hit
            buffer = remainder
            continue

        if not current:
            continue

        if any(char.isdigit() for char in line):
            continue
        if line.startswith('©') or 'Leadership Circle' in line:
            continue

        if buffer:
            buffer = f"{buffer} {line}".strip()
        else:
            buffer = line

        if buffer.endswith(('.', '!', '?')):
            entries[current].append(buffer)
            buffer = ""

if current and buffer:
    entries[current].append(buffer)

entries = {k: v for k, v in entries.items() if v}

with open(output_path, 'w') as f:
    json.dump(entries, f, indent=2)

print(f"Wrote {len(entries)} dimensions to {output_path}")
