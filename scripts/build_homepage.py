"""Build the static homepage and standalone ZIPs from a committed addon revision.

Usage: python scripts/build_homepage.py [--addon-ref HEAD] [--output dist/homepage]
The website source comes from the workspace; addon downloads come only from Git,
so an unfinished local addon change can never leak into a public download.
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

EDITIONS = ('vanilla', 'forever', 'tbc', 'retail')
# Files the game loads without a TOC line. Anything else committed beside the addon
# (editor files, a WTF/ folder, notes) stays out of the public ZIP.
# Dot files such as macOS ._Logo.tga resource forks never match.
ASSETS = (re.compile(r'Textures/[^/.][^/]*\.tga', re.IGNORECASE),)


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args])


def package_files(toc, tracked):
    """Return what ships for one edition: its TOC, every file the TOC lists and allowlisted assets.

    Paths are relative to the edition's WoWStatus/ folder. A listed file that is not
    committed fails the build, because the game would load a broken addon.
    """
    listed = []
    for line in toc.splitlines():
        relative = line.strip().replace('\\', '/')
        if relative and not relative.startswith('#'):
            listed.append(relative)
    for relative in listed:
        if relative not in tracked:
            raise ValueError(f'Missing addon file: {relative}')
    assets = {name for name in tracked if any(pattern.fullmatch(name) for pattern in ASSETS)}
    return sorted({'WoWStatus.toc', *listed, *assets})


def project_version(root, revision):
    pyproject = tomllib.loads(git(root, 'show', f'{revision}:pyproject.toml').decode())
    return pyproject['project']['version']


def build(root, output, addon_ref):
    revision = git(root, 'rev-parse', '--verify', f'{addon_ref}^{{commit}}').decode().strip()
    # Check every edition before writing anything, so a failed build leaves the output untouched.
    editions = {}
    for edition in EDITIONS:
        folder = f'addon/{edition}/WoWStatus/'
        # -z keeps non-ASCII paths unquoted.
        listing = git(root, 'ls-tree', '-r', '-z', '--name-only', revision, '--', folder).decode()
        tracked = {name.removeprefix(folder) for name in listing.split('\0') if name}
        if not tracked:
            raise ValueError(f'No {edition} addon in {revision}')
        if 'WoWStatus.toc' not in tracked:
            raise ValueError(f'No {edition} TOC in {revision}')
        toc = git(root, 'show', f'{revision}:{folder}WoWStatus.toc').decode()
        # The deploy receiver and the public verifier parse TOCs the same strict way.
        if toc.startswith('\ufeff') or '\r' in toc:
            raise ValueError(f'The {edition} TOC must be saved without a BOM and with LF line endings')
        match = re.search(r'^## Version: ([\w.\-]+)$', toc, re.MULTILINE)
        if match is None:
            raise ValueError(f'No version in the {edition} TOC')
        try:
            files = package_files(toc, tracked)
        except ValueError as error:
            raise ValueError(f'{edition}: {error}') from error
        skipped = sorted(tracked.difference(files))
        if skipped:
            print(f"Not packaging unlisted {edition} files: {', '.join(skipped)}", file=sys.stderr)
        editions[edition] = folder, files, match.group(1)
    expected = project_version(root, revision)
    versions = {version for _, _, version in editions.values()}
    if versions != {expected}:
        raise ValueError(f"Addon TOC versions {', '.join(sorted(versions))} must all equal "
                         f'pyproject.toml version {expected}')
    output.mkdir(parents=True, exist_ok=True)
    for source in (root / 'website').iterdir():
        if source.name in {'README.md', 'ARTWORK.md'}:
            continue
        destination = output / source.name
        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True)
        else:
            shutil.copy2(source, destination)
    downloads = output / 'downloads'
    downloads.mkdir(exist_ok=True)
    releases = {}
    for edition, (folder, files, version) in editions.items():
        archive = downloads / f'WoWStatus-{edition}.zip'
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as package:
            for file in files:
                # Stable timestamps keep repeated builds byte-identical.
                info = zipfile.ZipInfo(f'WoWStatus/{file}', date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                package.writestr(info, git(root, 'show', f'{revision}:{folder}{file}'))
        with zipfile.ZipFile(archive) as package:
            if package.testzip() is not None:
                raise ValueError(f'Broken archive: {archive}')
        releases[edition] = {'version': version, 'file': archive.name,
                             'bytes': archive.stat().st_size,
                             'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}
    html = (output / 'index.html').read_text(encoding='utf-8')
    html = html.replace('__VERSION__', releases['vanilla']['version'])
    for edition, release in releases.items():
        html = html.replace(f'__{edition.upper()}_SIZE__', f"{release['bytes'] / 1024:.0f} KB")
    if re.search(r'__[A-Z_]+__', html):
        raise ValueError('Unresolved homepage placeholder')
    (output / 'index.html').write_text(html, encoding='utf-8')
    (downloads / 'release.json').write_text(json.dumps({'addon_revision': revision, 'editions': releases}, indent=2) + '\n', encoding='utf-8')
    print(f"Homepage built at {output}; addon {releases['vanilla']['version']} ({revision[:7]})")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--addon-ref', default='HEAD')
    parser.add_argument('--output', type=Path, default=Path('dist/homepage'))
    args = parser.parse_args()
    build(Path(__file__).resolve().parents[1], args.output.resolve(), args.addon_ref)
