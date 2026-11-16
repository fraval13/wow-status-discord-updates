"""Generate the in-game "What's New" data from CHANGELOG.md.

``CHANGELOG.md`` is the single source for released notes: this script writes the
newest released sections to ``addon/shared/WhatsNewData.lua`` and the homepage
builder fills its release panel from the same file. Notes for the next release
wait as one file per pull request in ``changelog.d/``; ``scripts/prepare_release.py``
moves them into ``CHANGELOG.md``. ``--check`` changes nothing and exits 1 when the
Lua file is stale or a pending note file is invalid.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / 'CHANGELOG.md'
OUTPUT = ROOT / 'addon/shared/WhatsNewData.lua'
FRAGMENTS = 'changelog.d'  # One pending note file per pull request, relative to the root.
FRAGMENT_README = 'README.md'
FRAGMENT_NAME = re.compile(r'^[a-z0-9][a-z0-9._-]*\.md$')
KEEP = 3  # Sections shipped in the addon; older notes stay in the repository.
HEADING = re.compile(r'^## (.+?)\s*$')
VERSION = re.compile(r'^\d+\.\d+\.\d+$')
MAX_NOTE = 120
PLACEHOLDER = re.compile(r'__[A-Z_]+__')


def check_note(note: str, where: str) -> str:
    """One player-facing note: 1-MAX_NOTE printable characters without | or markup."""
    if not note or len(note) > MAX_NOTE or '|' in note or not note.isprintable():
        raise ValueError(f'{where}: notes must be 1-{MAX_NOTE} printable characters without |')
    if PLACEHOLDER.search(note):
        # The homepage build fills __NAME__ markers and refuses any left over.
        raise ValueError(f'{where}: notes may not contain __NAME__ placeholder text')
    if '`' in note or '**' in note:
        raise ValueError(f'{where}: notes are plain text; remove the ` or ** markup')
    return note


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
            current.append(check_note(line[2:].strip(), f'CHANGELOG.md:{number}'))
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


def fragment_order(path: Path) -> tuple[int, int, str]:
    """Issue-number order: 20-b.md before 100-a.md; names without a number come last."""
    number = re.match(r'\d+', path.name)
    return (0, int(number[0]), path.name) if number else (1, 0, path.name)


def fragment_paths(root: Path) -> list[Path]:
    """Pending note files in issue-number order (see fragment_order).

    Hidden files (.DS_Store, editor swap files) are ignored; anything else that is
    not a note file is an error, so a misnamed note is never silently dropped.
    """
    folder = root / FRAGMENTS
    if not folder.is_dir():
        return []
    paths = []
    for path in sorted(folder.iterdir(), key=fragment_order):
        if path.name == FRAGMENT_README or path.name.startswith('.'):
            continue
        if not path.is_file() or not FRAGMENT_NAME.match(path.name):
            raise ValueError(f'{FRAGMENTS}/{path.name}: pending notes must be files named '
                             'like 247-short-name.md (lowercase letters, digits, ., _ and -)')
        paths.append(path)
    return paths


def parse_fragment(text: str, name: str) -> list[str]:
    """The "- " notes of one pending note file; blank lines are allowed, nothing else."""
    notes = []
    for number, line in enumerate(text.splitlines(), 1):
        if line.startswith('- '):
            notes.append(check_note(line[2:].strip(), f'{FRAGMENTS}/{name}:{number}'))
        elif line.strip():
            raise ValueError(f'{FRAGMENTS}/{name}:{number}: only "- " notes belong in a note file')
    if not notes:
        raise ValueError(f'{FRAGMENTS}/{name} has no notes')
    return notes


def pending_notes(root: Path) -> list[tuple[Path, list[str]]]:
    """Every pending note file with its notes, validated, in issue-number order."""
    pending = []
    for path in fragment_paths(root):
        try:
            text = path.read_text(encoding='utf-8-sig')  # Tolerate a BOM from Windows editors.
        except UnicodeDecodeError as error:
            raise ValueError(f'{FRAGMENTS}/{path.name}: save the note file as UTF-8') from error
        pending.append((path, parse_fragment(text, path.name)))
    return pending


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
        try:
            pending_notes(ROOT)
        except ValueError as error:
            print(error)
            return 1
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
