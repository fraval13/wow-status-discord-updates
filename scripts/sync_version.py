"""Maintainer tool: copy the pyproject version into every addon TOC.

``pyproject.toml``'s ``project.version`` is the single source of truth for the
released version. Each edition's ``WoWStatus.toc`` repeats it on its ``## Version:``
line, because the game reads the version from the TOC. Keeping those four lines in
step by hand is easy to get wrong: a missed TOC used to reach review as a version
mismatch, and ``scripts/build_homepage.py`` refuses to build when the TOCs and
``pyproject.toml`` disagree.

Set the version once in ``pyproject.toml``, then run this script to write it into
all four TOCs. Only the ``## Version:`` line changes; everything else in the file,
including line endings and the trailing newline, is left exactly as it was.

``--check`` changes nothing and exits with status 1 when any TOC is out of step, so
CI and tests can assert the repository is consistent. This only touches source
files; it does not start a game, service or tests, and it never chooses a version
number itself.
"""
from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDITIONS = ('vanilla', 'forever', 'tbc', 'retail')
# The TOC directive the game reads, captured so only its value is rewritten. The value
# excludes \r as well as \n: `.` matches a carriage return, so a `.*` value would eat the
# \r of a CRLF file and rewriting would quietly convert that one line to LF.
VERSION_LINE = re.compile(r'^(## Version:[ \t]*)([^\r\n]*)', re.MULTILINE)


def project_version(root: Path = ROOT) -> str:
    with (root / 'pyproject.toml').open('rb') as handle:
        data = tomllib.load(handle)
    try:
        version = data['project']['version']
    except (KeyError, TypeError):
        raise ValueError('No project.version in pyproject.toml') from None
    if not isinstance(version, str) or not version.strip():
        raise ValueError('project.version in pyproject.toml must be a non-empty string')
    return version


def toc_paths(root: Path = ROOT) -> list[Path]:
    return [root / 'addon' / edition / 'WoWStatus/WoWStatus.toc' for edition in EDITIONS]


def toc_version(text: str) -> str | None:
    match = VERSION_LINE.search(text)
    return match.group(2).strip() if match else None


def retarget(text: str, version: str) -> str:
    """Rewrite only the value on the ``## Version:`` line."""
    match = VERSION_LINE.search(text)
    if match is None:
        raise ValueError('No "## Version:" line')
    if len(VERSION_LINE.findall(text)) > 1:
        raise ValueError('More than one "## Version:" line')
    return text[:match.start()] + match.group(1) + version + text[match.end():]


def plan(root: Path = ROOT) -> tuple[str, list[tuple[Path, str]]]:
    """The wanted version, plus the TOCs that do not already carry it."""
    version = project_version(root)
    stale = []
    for path in toc_paths(root):
        if not path.exists():
            raise ValueError(f'Missing TOC: {path.relative_to(root)}')
        text = path.read_text(encoding='utf-8')
        current = toc_version(text)
        if current is None:
            raise ValueError(f'No "## Version:" line in {path.relative_to(root)}')
        if current != version:
            stale.append((path, current))
    return version, stale


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--check', action='store_true',
                        help='Report drift and exit 1 without changing any file.')
    args = parser.parse_args(argv)
    try:
        version, stale = plan()
    except ValueError as error:
        print(f'error: {error}', file=sys.stderr)
        return 2
    if not stale:
        print(f'All {len(EDITIONS)} addon TOCs already declare {version}.')
        return 0
    for path, current in stale:
        relative = path.relative_to(ROOT)
        if args.check:
            print(f'{relative}: declares {current}, expected {version}', file=sys.stderr)
            continue
        path.write_text(retarget(path.read_text(encoding='utf-8'), version), encoding='utf-8')
        print(f'updated {relative} -> {version}')
    if args.check:
        print(f'{len(stale)} addon TOC(s) out of step with pyproject.toml {version}; '
              'run scripts/sync_version.py', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
