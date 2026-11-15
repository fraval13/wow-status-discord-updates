"""Current documentation must not state a release version as current (issue #198).

``AGENTS.md`` once said every edition was 0.14.14 while ``pyproject.toml`` was
thirty-odd releases further on. Each push to ``main`` bumps the version
(``scripts/prepare_release.py``), so any document that names the current release
as a plain fact is stale after the next merge. The version lives only in
``pyproject.toml`` (and the TOCs that ``scripts/sync_version.py`` keeps in step);
documents point there instead.

A release number may still appear when the text marks it as history: "since
1.9.0", "added in 0.10.0", "1.25.0 or later", "1.25.0+". Superseded documents in
``docs/history/`` and ``CHANGELOG.md`` are not scanned. Game client versions are
told apart from addon releases by being newer than the current release, or by a
"build" number, interface mapping or client branch name next to them.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]

# A three-part version not embedded in a longer dotted number (IP addresses, the
# four-part ``1.60.1.70790`` client builds) or a word.
VERSION = re.compile(r'(?<![\w.])(\d+)\.(\d+)\.(\d+)(?![\w]|\.\d)')
# Words just before a version that say it is history rather than the current state.
BEFORE = re.compile(
    r'(?:\bsince|\b(?:added|introduced|removed|changed|fixed) in|\bbefore|\buntil)\s+$',
    re.IGNORECASE,
)
AFTER = re.compile(r'^(?:\+|\s+or (?:later|newer)\b)')
# Game client versions written next to their build or interface number.
CLIENT = re.compile(r'^\s+build\b')
CLIENT_BEFORE = re.compile(r'(?:interface \d+ \(|`\d+` → `|`[a-z_]+` )$')


def project_version() -> tuple[int, int, int]:
    text = (ROOT / 'pyproject.toml').read_text(encoding='utf-8')
    match = re.search(r'^version\s*=\s*"(\d+)\.(\d+)\.(\d+)"', text, re.MULTILINE)
    assert match, 'pyproject.toml has no three-part project.version'
    return tuple(int(part) for part in match.groups())


def scanned_documents() -> list[Path]:
    documents = [ROOT / 'AGENTS.md', ROOT / 'README.md']
    documents += sorted((ROOT / 'docs').glob('*.md'))
    documents += sorted((ROOT / 'deploy').glob('*.md'))
    documents += [ROOT / 'website' / 'README.md']
    return [path for path in documents if path.exists()]


def unmarked_versions(text: str, current: tuple[int, int, int]) -> list[tuple[int, str]]:
    """Return ``(line, version)`` for each release number stated as a plain fact."""
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        for match in VERSION.finditer(line):
            version = tuple(int(part) for part in match.groups())
            if version > current:
                continue  # Not a release yet: a game client version.
            before = line[:match.start()].replace('*', '').replace('_', '')
            after = line[match.end():]
            if BEFORE.search(before.lstrip('(')) or AFTER.match(after):
                continue
            if CLIENT.match(after) or CLIENT_BEFORE.search(before):
                continue
            found.append((number, match.group(0)))
    return found


def test_documents_do_not_state_a_release_as_current():
    current = project_version()
    stale = []
    for path in scanned_documents():
        for line, version in unmarked_versions(path.read_text(encoding='utf-8'), current):
            stale.append(f'{path.relative_to(ROOT).as_posix()}:{line}: {version}')
    assert stale == [], (
        'These documents state a release version as current; point to pyproject.toml '
        'instead, mark it as history ("since", "added in", "or later"), or move the '
        'document to docs/history/:\n' + '\n'.join(stale)
    )


@pytest.mark.parametrize('text', [
    'All four editions are version **0.14.14**.',
    'The first automatic release is expected to be 0.15.0.',
    '# Character status cards (0.10.0)',
    'Current release: 1.52.0',
])
def test_plain_release_numbers_are_reported(text):
    assert unmarked_versions(text, (1, 52, 0))


@pytest.mark.parametrize('text', [
    '**Since 1.9.0 the warning popup is removed.**',
    '# Character status cards (added in 0.10.0)',
    'for friends on 1.25.0 or later',
    'items equipped by friends on 1.25.0+.',
    'Removed in 0.14.10.',
    'The TBC Anniversary build targets interface 20506 (2.5.6),',
    '`68e0a2e` (2.5.6 build 70577).',
    '(`120105` → `12.1.5`).',
    'Retail 12.1.5 is newer than any release.',
    'curl http://127.0.0.1:8080/health',
    'Forever 1.60.1.70790',
    'Checked in shallow clones: `classic_era` 1.15.9, `forever` 1.60.1.',
])
def test_marked_history_and_client_versions_are_allowed(text):
    assert unmarked_versions(text, (2, 60, 0)) == []
