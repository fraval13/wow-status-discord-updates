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
told apart from addon releases by a newer major version, or by a
client, tool or build named next to them.
"""
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]

# A three-part version, optionally written ``v1.2.3``, not embedded in a longer
# dotted number (IP addresses, the four-part ``1.60.1.70790`` client builds) or a
# word. Two-part numbers are left alone: "Lua 5.1" and interface patches use them.
VERSION = re.compile(r'(?<![\w.])v?(\d+)\.(\d+)\.(\d+)(?![\w]|\.\d)')
# Words just before a version that say it is history rather than the current state.
# "before" and "until" are deliberately absent: they usually introduce predictions.
BEFORE = re.compile(
    r'(?:\bsince|\b(?:added|introduced|removed|changed|fixed) in)[:\s]+$',
    re.IGNORECASE,
)
AFTER = re.compile(r'^(?:\+|\s+(?:or|and) (?:later|newer)\b)')
# Game clients and tools whose own versions share the addon's major numbers
# (WoW Forever 1.60.x, Classic Era 1.15.x), named just before the version, or a
# build number just after it.
CLIENT_BEFORE = re.compile(
    r'(?:\binterface \d+ |`\d+` → `'
    r'|\b(?:forever|classic(?:[ _]era|[ _]anniversary)?|era|retail|live|tbc|anniversary'
    r'|client|patch|build|lua|lupa|python|node|ruff|pytest|uv|pip)`?:?\s+)$',
    re.IGNORECASE,
)
CLIENT_AFTER = re.compile(r'^\s+build\b')
# How far back a marker may sit, so that one wrapped onto the previous line counts.
CONTEXT = 40


def project_version() -> tuple[int, int, int]:
    with (ROOT / 'pyproject.toml').open('rb') as handle:
        version = tomllib.load(handle)['project']['version']
    match = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)', version)
    assert match, f'project.version {version!r} is not a three-part version'
    return tuple(int(part) for part in match.groups())


def scanned_documents() -> list[Path]:
    history = ROOT / 'docs' / 'history'
    documents = [ROOT / 'AGENTS.md', ROOT / 'README.md']
    for folder in ('docs', 'deploy', 'website'):
        documents += sorted(
            path for path in (ROOT / folder).rglob('*.md') if history not in path.parents
        )
    return [path for path in documents if path.exists()]


def unmarked_versions(text: str, current: tuple[int, int, int]) -> list[tuple[int, str]]:
    """Return ``(line, version)`` for each release number stated as a plain fact.

    Every version whose major number is at most the current one counts, the current
    release and any predicted future one included: the next merge bumps the
    version, so both go stale. A newer major number is taken to be a game client
    version. Markers may sit on the neighbouring line of hard-wrapped Markdown.
    """
    found = []
    for match in VERSION.finditer(text):
        version = tuple(int(part) for part in match.groups())
        if version[0] > current[0]:
            continue  # A game client version (TBC 2.5.6, Retail 12.1.5).
        before = re.sub(r'\s+', ' ', text[max(0, match.start() - CONTEXT):match.start()])
        after = re.sub(r'\s+', ' ', text[match.end():match.end() + CONTEXT])
        if CLIENT_BEFORE.search(re.sub(r'[*(]', '', before)) or CLIENT_AFTER.match(after):
            continue
        if BEFORE.search(re.sub(r'[*_`(]', '', before)) or AFTER.match(after.lstrip('`*_')):
            continue
        found.append((text.count('\n', 0, match.start()) + 1, match.group(0)))
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
    'Current release: v1.52.0',
    'The next release is expected to be 1.53.0.',
    'Keep the old path until 1.53.0 ships.',
    'Install `wowstatus` 1.52.0 from the downloads page.',
])
def test_plain_release_numbers_are_reported(text):
    assert unmarked_versions(text, (1, 52, 0))


@pytest.mark.parametrize('text', [
    '**Since 1.9.0 the warning popup is removed.**',
    '# Character status cards (added in 0.10.0)',
    'for friends on 1.25.0 or later',
    'items equipped by friends on 1.25.0+.',
    'Removed in 0.14.10.',
    'Since: 1.9.0',
    'since `1.9.0`',
    'friends on 1.40.0 and later',
    'Status cards were added in\n0.10.0 and work.',
    'Since\n1.9.0 the popup is gone.',
    'WoW Forever 1.60.2 changed the roster API.',
    'Classic Era 1.15.9 still lacks C_Item.',
    'Pinned ruff 0.14.2 in CI.',
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
