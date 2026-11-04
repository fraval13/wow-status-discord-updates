"""Maintainer tool: mirror canonical shared addon files into every edition folder.

The source of truth is the set of Git-tracked files in ``addon/shared``: top-level
``*.lua`` files and everything under ``Textures/`` (subfolders included). Dotfiles
and untracked files are never copied. In each ``addon/<edition>/WoWStatus`` folder
the same scope (top-level ``*.lua`` and ``Textures/``) is made to match exactly:
changed files are rewritten and tracked copies whose shared source is gone are
deleted. Edition-owned files (the adapter Lua and the TOC) are left alone.

Untracked files in an edition's mirrored scope are reported but not deleted, so
uncommitted work is never lost; the release builder reads from Git and does not
ship them.

``--check`` changes nothing and exits with status 1 when any edition is out of
sync. This only touches source files; it does not start a game, service or tests.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]

# Edition folder -> files in its mirrored scope that belong to the edition itself.
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
    deletes: list[Path] = field(default_factory=list)
    untracked_extras: list[Path] = field(default_factory=list)
    untracked_shared: list[Path] = field(default_factory=list)

    @property
    def in_sync(self) -> bool:
        return not self.copies and not self.deletes


def _in_scope(relative: PurePosixPath) -> bool:
    """Whether a path relative to a shared/edition folder is a mirrored file."""
    if any(part.startswith('.') for part in relative.parts):
        return False
    if len(relative.parts) == 1:
        return relative.suffix == '.lua'
    return relative.parts[0] == 'Textures'


def _git_files(repo: Path, folder: Path, *extra: str) -> set[PurePosixPath]:
    """Paths under ``folder`` (relative to it) listed by ``git ls-files``."""
    try:
        result = subprocess.run(
            ['git', '-C', str(repo), 'ls-files', '-z', *extra, '--',
             folder.relative_to(repo).as_posix()],
            check=True, capture_output=True, encoding='utf-8',
        )
    except (OSError, subprocess.CalledProcessError) as error:
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
    return {path for path in found if _in_scope(path)}


def plan_sync(repo: Path = ROOT) -> Plan:
    """Work out every change before any file is written."""
    addon = repo / 'addon'
    shared = addon / 'shared'
    tracked_shared = {
        path for path in _git_files(repo, shared)
        if _in_scope(path) and (shared / path).is_file()
    }
    if not tracked_shared:
        raise SyncError(f'no tracked shared files found under {shared}')
    plan = Plan(untracked_shared=sorted(
        shared / path for path in _scoped_files(shared) - tracked_shared
    ))
    for edition, owned in EDITIONS.items():
        destination = addon / edition / 'WoWStatus'
        if not destination.is_dir():
            raise SyncError(f'missing edition folder {destination}')
        owned = {PurePosixPath(name) for name in owned}
        clash = sorted(tracked_shared & owned)
        if clash:
            raise SyncError(f'{edition} owns {", ".join(map(str, clash))}, which is also shared')
        for relative in sorted(tracked_shared):
            source, target = shared / relative, destination / relative
            for parent in reversed(target.relative_to(destination).parents):
                if (destination / parent).is_file():
                    raise SyncError(f'{destination / parent} is a file; expected a folder')
            if target.exists() and not target.is_file():
                raise SyncError(f'{target} is not a regular file')
            if not target.exists() or target.read_bytes() != source.read_bytes():
                plan.copies.append((source, target))
        present = _scoped_files(destination) - tracked_shared - owned
        tracked_edition = _git_files(repo, destination)
        for relative in sorted(present):
            target = destination / relative
            if relative in tracked_edition:
                plan.deletes.append(target)
            else:
                plan.untracked_extras.append(target)
    return plan


def apply(plan: Plan) -> None:
    for source, target in plan.copies:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    for target in plan.deletes:
        target.unlink()
        # Drop folders inside Textures/ that the deletion left empty.
        parent = target.parent
        while parent.name != 'WoWStatus' and parent.name != 'Textures' and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent


def _relative(path: Path, repo: Path) -> str:
    return path.relative_to(repo).as_posix()


def main(argv: list[str] | None = None, repo: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--check', action='store_true',
                        help='report differences and exit 1 instead of changing files')
    args = parser.parse_args(argv)
    try:
        plan = plan_sync(repo)
    except SyncError as error:
        print(f'sync_addons: {error}', file=sys.stderr)
        return 2
    for path in plan.untracked_shared:
        print(f'skipped untracked shared file (git add it to sync): {_relative(path, repo)}')
    for path in plan.untracked_extras:
        print(f'left untracked edition file in place: {_relative(path, repo)}')
    verb_copy, verb_delete = ('would copy', 'would delete') if args.check else ('copied', 'deleted')
    for source, target in plan.copies:
        print(f'{verb_copy} {_relative(source, repo)} -> {_relative(target, repo)}')
    for target in plan.deletes:
        print(f'{verb_delete} {_relative(target, repo)}')
    if args.check:
        return 0 if plan.in_sync else 1
    apply(plan)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
