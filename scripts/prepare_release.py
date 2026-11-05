"""Prepare one committed minor release for a main pipeline run, without bumping on retries.

Only the trusted main job calls this with a write token. PR jobs never run it.
The returned revision must be checked out by validation, packaging and deployment;
pushing with GITHUB_TOKEN does not start another pipeline run.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import sync_version
import whats_new

ROOT = Path(__file__).resolve().parents[1]
SHA = re.compile(r'[0-9a-f]{40}')
VERSION = re.compile(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)')
MARKER = re.compile(r'^WoW-Status-Release-Source: ([0-9a-f]{40})$', re.MULTILINE)


def git(root: Path, *args: str, authenticated: bool = False) -> str:
    command = ['git', '-C', str(root)]
    if authenticated:
        # gh reads GH_TOKEN from the job environment. No token is written to disk,
        # passed on the command line, or retained in the checkout configuration.
        command += ['-c', 'credential.helper=', '-c', 'credential.helper=!gh auth git-credential']
    return subprocess.run([*command, *args], check=True, stdout=subprocess.PIPE,
                          encoding='utf-8').stdout.strip()


def read(path: Path) -> str:
    with path.open(encoding='utf-8', newline='') as handle:
        return handle.read()


def version_tuple(version: str) -> tuple[int, ...]:
    if not VERSION.fullmatch(version):
        raise ValueError('Automatic releases require a major.minor.patch version')
    return tuple(map(int, version.split('.')))


def next_version(version: str) -> str:
    major, minor, _ = version_tuple(version)
    return f'{major}.{minor + 1}.0'


def note_paths(root: Path) -> list[Path]:
    return [root / 'addon/shared/WhatsNewData.lua',
            *(root / f'addon/{edition}/WoWStatus/WhatsNewData.lua'
              for edition in sync_version.EDITIONS)]


def files(root: Path) -> list[Path]:
    return [root / 'pyproject.toml', root / 'CHANGELOG.md',
            *sync_version.toc_paths(root), *note_paths(root)]


def validate_release(root: Path) -> str:
    version = sync_version.project_version(root)
    version_tuple(version)
    if any(sync_version.toc_version(read(path)) != version for path in sync_version.toc_paths(root)):
        raise ValueError('Every addon TOC must match the project version before release')
    sections = whats_new.parse(read(root / 'CHANGELOG.md'))
    if sections[0][0] != version:
        raise ValueError('Newest release notes must match the project version')
    expected = whats_new.render(sections)
    for path in note_paths(root):
        if read(path) != expected:
            raise ValueError(f'{path.relative_to(root)} has stale release notes')
    return version


def promoted_notes(text: str, version: str, subject: str) -> str:
    unreleased = list(re.finditer(r'^## Unreleased[ \t]*\r?$', text, re.MULTILINE))
    if len(unreleased) > 1:
        raise ValueError('Only one Unreleased section is allowed')
    # The public commit subject is a useful fallback for a change without notes.
    subject = ''.join(char for char in subject if char.isprintable()).replace('|', '-')
    subject = subject.translate(str.maketrans('', '', '*`<>'))[:whats_new.MAX_NOTE].strip()
    fallback = '- ' + (subject or 'Latest addon and website improvements') + '\n\n'
    if unreleased:
        heading = unreleased[0]
        end = re.search(r'^## ', text[heading.end():], re.MULTILINE)
        stop = heading.end() + end.start() if end else len(text)
        body = text[heading.end():stop]
        if not body.strip():
            body = '\n\n' + fallback
        result = text[:heading.start()] + f'## {version}' + body + text[stop:]
    else:
        heading = re.search(r'^## \d+\.\d+\.\d+\s*$', text, re.MULTILINE)
        if not heading:
            raise ValueError('No released section to extend')
        result = text[:heading.start()] + f'## {version}\n\n' + fallback + text[heading.start():]
    sections = whats_new.parse(result)
    if sections[0][0] != version:
        raise ValueError('Unreleased notes must precede all released sections')
    return result


def bump(root: Path, version: str, subject: str) -> None:
    """Plan every generated file before writing any of them."""
    project = root / 'pyproject.toml'
    text = read(project)
    section = re.search(r'^\[project\]\s*\r?\n(.*?)(?=^\[|\Z)', text, re.MULTILINE | re.DOTALL)
    if not section:
        raise ValueError('No project table')
    body, count = re.subn(r'^(version\s*=\s*)([\'"])[^\'"\r\n]+\2',
                          lambda match: match[1] + match[2] + version + match[2],
                          section[1], flags=re.MULTILINE)
    if count != 1:
        raise ValueError('Expected one project.version')
    planned = {project: text[:section.start(1)] + body + text[section.end(1):]}
    changelog = root / 'CHANGELOG.md'
    planned[changelog] = promoted_notes(read(changelog), version, subject)
    for path in sync_version.toc_paths(root):
        planned[path] = sync_version.retarget(read(path), version)
    notes = whats_new.render(whats_new.parse(planned[changelog]))
    for path in note_paths(root):
        planned[path] = notes
    for path, content in planned.items():
        with path.open('w', encoding='utf-8', newline='') as handle:
            handle.write(content)
    validate_release(root)


def parent(root: Path, revision: str) -> str | None:
    parents = git(root, 'show', '-s', '--format=%P', revision).split()
    return parents[0] if parents else None


def at_version(root: Path, revision: str) -> str:
    return tomllib.loads(git(root, 'show', f'{revision}:pyproject.toml'))['project']['version']


def generated_source(root: Path, revision: str) -> str | None:
    marker = MARKER.search(git(root, 'show', '-s', '--format=%B', revision))
    if not marker:
        return None
    source = marker[1]
    if parent(root, revision) != source or at_version(root, revision) != next_version(at_version(root, source)):
        raise ValueError('Malformed automatic release commit')
    return source


def prepare(root: Path, source: str, remote: str = 'origin', branch: str = 'main') -> str:
    if not SHA.fullmatch(source) or git(root, 'rev-parse', 'HEAD') != source:
        raise ValueError('Checkout must be exactly the requested full source revision')
    if git(root, 'status', '--porcelain', '--untracked-files=no'):
        raise ValueError('Release preparation requires a clean tracked checkout')
    git(root, 'fetch', '--no-tags', remote, f'refs/heads/{branch}', authenticated=True)
    tip = git(root, 'rev-parse', 'FETCH_HEAD')
    if tip != source:
        if generated_source(root, tip) == source:
            # The earlier attempt pushed successfully. Reuse it even if that run
            # stopped before producing its output or before validation/deployment.
            git(root, 'checkout', '--detach', tip)
            validate_release(root)
            return tip
        print('::notice title=Release skipped::A newer main commit owns the next release.')
        return source
    version = validate_release(root)
    previous = parent(root, source)
    if generated_source(root, source):
        return source  # Manual dispatch/retry on an already-prepared release.
    if previous:
        before = at_version(root, previous)
        if version_tuple(version) < version_tuple(before):
            raise ValueError('A release must never decrease the project version')
        if version != before:
            return source  # An intentional release PR already chose its version.
    version = next_version(version)
    bump(root, version, git(root, 'show', '-s', '--format=%s', source))
    git(root, 'add', '--', *(str(path.relative_to(root)) for path in files(root)))
    git(root, '-c', 'user.name=github-actions[bot]',
        '-c', 'user.email=41898282+github-actions[bot]@users.noreply.github.com',
        'commit', '-m', f'Release {version}', '-m', f'WoW-Status-Release-Source: {source}')
    revision = git(root, 'rev-parse', 'HEAD')
    # No force: a main push arriving during preparation makes this fail instead
    # of overwriting it. That newer source gets its own run and release.
    git(root, 'push', remote, f'HEAD:refs/heads/{branch}', authenticated=True)
    print(f'Prepared release {version} at {revision}')
    return revision


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--revision', required=True)
    args = parser.parse_args(argv)
    try:
        revision = prepare(ROOT, args.revision)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f'Release preparation failed: {error}', file=sys.stderr)
        return 1
    output = os.environ.get('GITHUB_OUTPUT')
    if output:
        with open(output, 'a', encoding='utf-8') as handle:
            handle.write(f'revision={revision}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
