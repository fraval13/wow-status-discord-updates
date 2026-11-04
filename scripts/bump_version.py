"""Release tool: set one version in ``pyproject.toml`` and all four addon TOCs.

Feature pull requests do not change the version. A separate release pull request
runs this script, so the five files always change together and parallel feature
branches never compete for the same next number::

    python scripts/bump_version.py 0.14.13
    python scripts/bump_version.py --check   # report the current version, exit 1 on mismatch
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDITIONS = ('vanilla', 'forever', 'tbc', 'retail')
VERSION = re.compile(r'^\d+\.\d+\.\d+$')
PYPROJECT = re.compile(r'^(version = ")([^"]+)(")$', re.MULTILINE)
TOC = re.compile(r'^(## Version: )(\S+)()$', re.MULTILINE)


def files(root: Path) -> list[tuple[Path, re.Pattern[str]]]:
    return [(root / 'pyproject.toml', PYPROJECT)] + [
        (root / 'addon' / edition / 'WoWStatus' / 'WoWStatus.toc', TOC) for edition in EDITIONS
    ]


def current(root: Path = ROOT) -> dict[str, str]:
    found = {}
    for path, pattern in files(root):
        match = pattern.search(path.read_text(encoding='utf-8'))
        if match is None:
            raise SystemExit(f'No version line in {path.relative_to(root)}')
        found[path.relative_to(root).as_posix()] = match.group(2)
    return found


def bump(version: str, root: Path = ROOT) -> None:
    if not VERSION.match(version):
        raise SystemExit(f'Version must look like 1.2.3, not {version!r}')
    for path, pattern in files(root):
        text = path.read_text(encoding='utf-8')
        new, count = pattern.subn(lambda m: m.group(1) + version + m.group(3), text)
        if count != 1:
            raise SystemExit(f'Expected one version line in {path.relative_to(root)}, found {count}')
        with path.open('w', encoding='utf-8', newline='') as handle:
            handle.write(new)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('version', nargs='?', help='new version, for example 0.14.13')
    parser.add_argument('--check', action='store_true', help='only report the version in every file')
    args = parser.parse_args(argv)
    if args.check == bool(args.version):
        parser.error('give either a version or --check')
    if args.version:
        bump(args.version)
    found = current()
    for name, version in found.items():
        print(f'{version}  {name}')
    if len(set(found.values())) != 1:
        print('Versions differ', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
