"""Generate the in-game "What's New" data from CHANGELOG.md.

``CHANGELOG.md`` is the single source for release notes: this script writes the
newest released sections to ``addon/shared/WhatsNewData.lua`` and the homepage
builder fills its release panel from the same file. ``--check`` changes nothing
and exits 1 when the Lua file is stale.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / 'CHANGELOG.md'
OUTPUT = ROOT / 'addon/shared/WhatsNewData.lua'
KEEP = 3  # Sections shipped in the addon; older notes stay in the repository.
HEADING = re.compile(r'^## (.+?)\s*$')
VERSION = re.compile(r'^\d+\.\d+\.\d+$')
MAX_NOTE = 120


def parse(text: str) -> list[tuple[str, list[str]]]:
    """Released sections, newest first, as (version, notes). Unreleased is skipped."""
    sections: list[tuple[str, list[str]]] = []
    current: list[str] | None = None
    for number, line in enumerate(text.splitlines(), 1):
        heading = HEADING.match(line)
        if heading:
            name = heading.group(1)
            if name == 'Unreleased':
                current = None
                continue
            if not VERSION.match(name):
                raise ValueError(f'CHANGELOG.md:{number}: heading must be a version or Unreleased, not {name!r}')
            if any(version == name for version, _ in sections):
                raise ValueError(f'CHANGELOG.md:{number}: {name} appears twice')
            current = []
            sections.append((name, current))
        elif current is not None and line.startswith('- '):
            note = line[2:].strip()
            if not note or len(note) > MAX_NOTE or '|' in note or not note.isprintable():
                raise ValueError(f'CHANGELOG.md:{number}: notes must be 1-{MAX_NOTE} printable characters without |')
            current.append(note)
        elif current is not None and line.strip():
            raise ValueError(f'CHANGELOG.md:{number}: only "- " notes belong in a release section')
    if not sections:
        raise ValueError('CHANGELOG.md has no released version')
    for version, notes in sections:
        if not notes:
            raise ValueError(f'CHANGELOG.md: {version} has no notes')
    keys = [tuple(int(part) for part in version.split('.')) for version, _ in sections]
    if keys != sorted(keys, reverse=True):
        raise ValueError('CHANGELOG.md versions must be newest first')
    return sections


def lua_string(text: str) -> str:
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'


def render(sections: list[tuple[str, list[str]]]) -> str:
    lines = ['-- Generated from CHANGELOG.md by scripts/whats_new.py. Do not edit.',
             'WoWStatusWhatsNewData = {']
    for version, notes in sections[:KEEP]:
        lines.append(f'    {{version={lua_string(version)}, notes={{')
        lines.extend(f'        {lua_string(note)},' for note in notes)
        lines.append('    }},')
    lines.append('}')
    return '\n'.join(lines) + '\n'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    expected = render(parse(CHANGELOG.read_text(encoding='utf-8')))
    actual = OUTPUT.read_text(encoding='utf-8') if OUTPUT.exists() else None
    if args.check:
        if actual != expected:
            print(f'{OUTPUT.relative_to(ROOT)} is stale; run python scripts/whats_new.py')
            return 1
        return 0
    if actual != expected:
        with OUTPUT.open('w', encoding='utf-8', newline='') as handle:
            handle.write(expected)
        print(f'wrote {OUTPUT.relative_to(ROOT)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
