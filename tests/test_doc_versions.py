"""Current documentation must not state a release version as current (issue #198).

``AGENTS.md`` once said every edition was 0.14.14 while ``pyproject.toml`` was
thirty-odd releases further on. Each push to ``main`` bumps the version
(``scripts/prepare_release.py``), so any document that names the current release
as a plain fact is stale after the next merge. The version lives only in
``pyproject.toml`` (and the TOCs that ``scripts/sync_version.py`` keeps in step);
documents point there instead.

Which numbers count as addon releases comes from the project itself, not from a
list of client or tool names: every ``## x.y.z`` heading in ``CHANGELOG.md``, the
current version, anything older than the oldest changelog entry (the early 0.x
releases), and any later ``x.y.0`` of the current major series (a prediction).
Other numbers, such as WoW Forever 1.60.1 or Classic Era 1.15.9, are left alone.

A past release may still appear when the text marks it as history: "since
1.9.0", "added in version 0.10.0", "1.25.0 or later", "1.25.0+". A predicted
release is always reported, because no wording keeps it true. Superseded
documents in ``docs/history/`` and ``CHANGELOG.md`` itself are not scanned.
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
# Words just before a past release that say it is history. They only ever exempt a
# release that has already happened, so "will be fixed in 1.53.0" is still reported.
BEFORE = re.compile(
    r'(?:\bsince|\b(?:added|introduced|removed|changed|fixed) in)'
    r'(?:\s+(?:version|release))?[:\s]+$',
    re.IGNORECASE,
)
AFTER = re.compile(r'^(?:\+|\s+(?:or|and) (?:later|newer|above)\b)')
# How far back a marker may sit, so that one wrapped onto the previous line counts.
CONTEXT = 40

Version = tuple[int, int, int]


def project_version() -> Version:
    with (ROOT / 'pyproject.toml').open('rb') as handle:
        version = tomllib.load(handle)['project']['version']
    match = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)', version)
    assert match, f'project.version {version!r} is not a three-part version'
    return tuple(int(part) for part in match.groups())


def changelog_releases() -> set[Version]:
    text = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    return {
        tuple(int(part) for part in match.groups())
        for match in re.finditer(r'^## (\d+)\.(\d+)\.(\d+)\s*$', text, re.MULTILINE)
    }


def scanned_documents() -> list[Path]:
    history = ROOT / 'docs' / 'history'
    documents = [ROOT / 'AGENTS.md', ROOT / 'README.md', ROOT / 'CONTRIBUTING.md', ROOT / 'SECURITY.md']
    for folder in ('docs', 'deploy', 'website'):
        documents += sorted(
            path for path in (ROOT / folder).rglob('*.md') if history not in path.parents
        )
    return [path for path in documents if path.exists()]


def unmarked_versions(
    text: str, current: Version, releases: set[Version] = frozenset()
) -> list[tuple[int, str]]:
    """Return ``(line, version)`` for each addon release stated as a plain fact.

    ``releases`` are the changelog's release headings. Markers may sit on the
    neighbouring line of hard-wrapped Markdown.
    """
    oldest = min(releases | {current})
    found = []
    for match in VERSION.finditer(text):
        version = tuple(int(part) for part in match.groups())
        predicted = version > current and version[0] == current[0] and version[2] == 0
        released = version <= current and (
            version in releases or version == current or version < oldest
        )
        if not (predicted or released):
            continue  # A game client or tool version, not an addon release.
        if released:
            before = re.sub(r'\s+', ' ', text[max(0, match.start() - CONTEXT):match.start()])
            after = re.sub(r'\s+', ' ', text[match.end():match.end() + CONTEXT])
            if BEFORE.search(re.sub(r'[*_`(]', '', before)) or AFTER.match(after.lstrip('`*_')):
                continue
        found.append((text.count('\n', 0, match.start()) + 1, match.group(0)))
    return found


def test_documents_do_not_state_a_release_as_current():
    current = project_version()
    releases = changelog_releases()
    stale = []
    for path in scanned_documents():
        text = path.read_text(encoding='utf-8')
        for line, version in unmarked_versions(text, current, releases):
            stale.append(f'{path.relative_to(ROOT).as_posix()}:{line}: {version}')
    assert stale == [], (
        'These documents state a release version as current; point to pyproject.toml '
        'instead, mark it as history ("since", "added in", "or later"), or move the '
        'document to docs/history/:\n' + '\n'.join(stale)
    )


# A small changelog for the examples: releases from 0.14.12 up to the current 1.52.0.
RELEASES = {(0, 14, 12), (0, 14, 14), (0, 15, 0), (1, 9, 0), (1, 25, 0), (1, 40, 0), (1, 52, 0)}
CURRENT = (1, 52, 0)


@pytest.mark.parametrize('text', [
    'All four editions are version **0.14.14**.',
    'The first automatic release is expected to be 0.15.0.',
    '# Character status cards (0.10.0)',
    'Current release: 1.52.0',
    'Current release: v1.52.0',
    'Forever 1.52.0 and Retail 1.52.0 are the current editions.',
    'Latest patch 1.52.0 fixes the queue.',
    'Install `wowstatus` 1.52.0 from the downloads page.',
    'The next release is expected to be 1.53.0.',
    'Keep the old path until 1.53.0 ships.',
    'The bug will be fixed in 1.53.0.',
    'Since 1.60.0 ships next month, wait.',
])
def test_plain_release_numbers_are_reported(text):
    assert unmarked_versions(text, CURRENT, RELEASES)


@pytest.mark.parametrize('text', [
    '**Since 1.9.0 the warning popup is removed.**',
    '# Character status cards (added in 0.10.0)',
    'since version 1.9.0',
    'added in release 0.10.0',
    'for friends on 1.25.0 or later',
    'friends on 1.25.0 or above',
    'items equipped by friends on 1.25.0+.',
    'Removed in 0.14.10.',
    'Since: 1.9.0',
    'since `1.9.0`',
    'friends on 1.40.0 and later',
    'Status cards were added in\n0.10.0 and work.',
    'Since\n1.9.0 the popup is gone.',
    'WoW Forever 1.60.2 changed the roster API.',
    'Classic Era 1.15.9 still lacks C_Item.',
    'Vanilla 1.12.1 client',
    'Pinned ruff 0.15.4 in CI.',
    'The TBC Anniversary build targets interface 20506 (2.5.6),',
    '(`120105` → `12.1.5`).',
    'curl http://127.0.0.1:8080/health',
    'Forever 1.60.1.70790',
    'Checked in shallow clones: `classic_era` 1.15.9, `forever` 1.60.1.',
])
def test_marked_history_and_client_versions_are_allowed(text):
    assert unmarked_versions(text, CURRENT, RELEASES) == []
