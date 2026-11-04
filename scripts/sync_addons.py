"""Maintainer tool: mirror canonical shared addon files into every edition folder.

The source of truth is the set of Git-tracked files in ``addon/shared``: top-level
``*.lua`` files and everything under ``Textures/`` (subfolders included). Dotfiles
and untracked files are never copied. In each ``addon/<edition>/WoWStatus`` folder
the same scope (top-level ``*.lua`` and ``Textures/``) is made to match exactly:
changed files are rewritten and tracked copies whose shared source is gone are
deleted. Edition-owned files (the adapter Lua and the TOC) are left alone.

Untracked files in an edition's mirrored scope are reported but not deleted; the
release builder reads from Git and does not ship them. Edition copies of shared
files are overwritten, as before, so edit ``addon/shared`` rather than an edition.
The run stops before changing anything if a tracked shared file is missing from
disk (``git mv`` or ``git rm`` it), a file it would delete has unstaged edits, or
an edition copy would be deleted while its shared source is untracked.

``--check`` changes nothing and exits with status 1 when any edition is out of
sync. This only touches source files; it does not start a game, service or tests.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]

# Edition folder -> files in its mirrored scope that belong to the edition itself.
# A new edition-only file in scope must be listed here, or the sync deletes it
# (the repository test in tests/test_sync_addons.py fails first).
EDITIONS: dict[str, frozenset[str]] = {
    'vanilla': frozenset({'Vanilla.lua'}),
    'forever': frozenset({'Forever.lua'}),
    'tbc': frozenset({'TBC.lua'}),
    'retail': frozenset({'Retail.lua'}),
}


class SyncError(RuntimeError):
    """The sync cannot be planned safely; nothing has been changed."""


@dataclass
class Plan:
    copies: list[tuple[Path, Path]] = field(default_factory=list)
    # (edition folder, path relative to it)
    deletes: list[tuple[Path, PurePosixPath]] = field(default_factory=list)
    untracked_extras: list[Path] = field(default_factory=list)
    untracked_shared: list[Path] = field(default_factory=list)

    @property
    def in_sync(self) -> bool:
        return not self.copies and not self.deletes


def in_scope(relative: PurePosixPath) -> bool:
    """Whether a path relative to a shared/edition folder is a mirrored file."""
    if any(part.startswith('.') for part in relative.parts):
        return False
    if len(relative.parts) == 1:
        return relative.suffix == '.lua'
    return relative.parts[0] == 'Textures'


def _git_files(repo: Path, folder: Path, *options: str) -> set[PurePosixPath]:
    """Paths under ``folder`` (relative to it) listed by ``git ls-files [options]``."""
    try:
        result = subprocess.run(
            ['git', '-C', str(repo), 'ls-files', '-z', *options, '--',
             folder.relative_to(repo).as_posix()],
            check=True, capture_output=True, encoding='utf-8',
        )
    except (OSError, UnicodeDecodeError, subprocess.CalledProcessError) as error:
        detail = getattr(error, 'stderr', '') or error
        raise SyncError(f'git ls-files failed in {repo}: {detail}') from error
    prefix = PurePosixPath(folder.relative_to(repo).as_posix())
    return {PurePosixPath(name).relative_to(prefix) for name in result.stdout.split('\0') if name}


def _scoped_files(folder: Path) -> set[PurePosixPath]:
    """Mirrored-scope files present on disk under ``folder``."""
    found = {PurePosixPath(path.name) for path in folder.glob('*.lua') if path.is_file()}
    textures = folder / 'Textures'
    if textures.is_dir():
        found |= {
            PurePosixPath(path.relative_to(folder).as_posix())
            for path in textures.rglob('*') if path.is_file()
        }
    return {path for path in found if in_scope(path)}


def _folded(path: PurePosixPath) -> str:
    return path.as_posix().casefold()


def plan_sync(repo: Path = ROOT) -> Plan:
    """Work out every change before any file is written."""
    addon = repo / 'addon'
    shared = addon / 'shared'
    tracked_shared = {path for path in _git_files(repo, shared) if in_scope(path)}
    missing = sorted(path for path in tracked_shared if not (shared / path).is_file())
    if missing:
        names = ', '.join(f'addon/shared/{path}' for path in missing)
        raise SyncError(f'tracked but missing from disk (git mv/rm or restore it): {names}')
    if not tracked_shared:
        raise SyncError(f'no tracked shared files found under {shared}')
    sources = {path: (shared / path).read_bytes() for path in tracked_shared}
    untracked_shared = _scoped_files(shared) - tracked_shared
    plan = Plan(untracked_shared=sorted(shared / path for path in untracked_shared))
    for edition, owned_names in EDITIONS.items():
        destination = addon / edition / 'WoWStatus'
        if not destination.is_dir():
            raise SyncError(f'missing edition folder {destination}')
        owned = {PurePosixPath(name) for name in owned_names}
        clash = sorted(tracked_shared & owned)
        if clash:
            raise SyncError(f'{edition} owns {", ".join(map(str, clash))}, which is also shared')

        tracked_edition = _git_files(repo, destination)
        modified_edition = _git_files(repo, destination, '--modified')
        deleted_folded = set()
        for relative in sorted(_scoped_files(destination) - tracked_shared - owned):
            target = destination / relative
            if relative not in tracked_edition:
                plan.untracked_extras.append(target)
                continue
            if relative in untracked_shared:
                raise SyncError(f'addon/shared/{relative} is untracked, so its edition copies '
                                'would be deleted; git add it first')
            if relative in modified_edition:
                raise SyncError(f'{target} would be deleted but has unstaged edits; '
                                'commit or discard them first')
            plan.deletes.append((destination, relative))
            deleted_folded.add(_folded(relative))

        for relative in sorted(tracked_shared):
            target = destination / relative
            for parent in reversed(relative.parents):
                if (destination / parent).is_file():
                    raise SyncError(f'{destination / parent} is a file; expected a folder')
            if target.exists() and not target.is_file():
                raise SyncError(f'{target} is not a regular file')
            # On a case-insensitive filesystem a case-only rename makes the
            # deleted old name and this target the same file, so rewrite it after
            # the delete even when the bytes already match.
            if (_folded(relative) in deleted_folded or not target.exists()
                    or target.read_bytes() != sources[relative]):
                plan.copies.append((shared / relative, target))
    return plan


def apply(plan: Plan, report: Callable[[str, Path, Path | None], None] = lambda *_: None) -> None:
    """Delete stale copies first, then write, so case-only renames survive."""
    for destination, relative in plan.deletes:
        target = destination / relative
        target.unlink()
        report('deleted', target, None)
        # Drop folders inside Textures/ that the deletion left empty.
        stop = destination / 'Textures'
        parent = target.parent
        while parent != stop and parent != destination and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent
    for source, target in plan.copies:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        report('copied', target, source)


def main(argv: list[str] | None = None, repo: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(
        description='Mirror tracked shared addon files into every edition folder.')
    parser.add_argument('--check', action='store_true',
                        help='report differences and exit 1 instead of changing files')
    args = parser.parse_args(argv)

    def relative(path: Path) -> str:
        return path.relative_to(repo).as_posix()

    def report(action: str, target: Path, source: Path | None) -> None:
        origin = f'{relative(source)} -> ' if source else ''
        print(f'{action} {origin}{relative(target)}')

    try:
        plan = plan_sync(repo)
    except SyncError as error:
        print(f'sync_addons: {error}', file=sys.stderr)
        return 2
    for path in plan.untracked_shared:
        print(f'skipped untracked shared file (git add it to sync): {relative(path)}')
    for path in plan.untracked_extras:
        print(f'left untracked edition file in place: {relative(path)}')
    if args.check:
        for destination, path in plan.deletes:
            report('would delete', destination / path, None)
        for source, target in plan.copies:
            report('would copy', target, source)
        return 0 if plan.in_sync else 1
    apply(plan, report)
    renamed = {
        (destination / old, target)
        for destination, old in plan.deletes for _, target in plan.copies
        if target.parent == (destination / old).parent and target != destination / old
        and target.name.casefold() == old.name.casefold()
    }
    for old, new in sorted(renamed):
        print(f'case-only rename: on Windows/macOS run git mv {relative(old)} {relative(new)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
