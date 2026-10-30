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
import zipfile
from pathlib import Path


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args])


def build(root, output, addon_ref):
    revision = git(root, 'rev-parse', '--verify', f'{addon_ref}^{{commit}}').decode().strip()
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
    for edition in ('vanilla', 'forever', 'tbc'):
        prefix = f'addon/{edition}/'
        files = git(root, 'ls-tree', '-r', '--name-only', revision, '--', prefix + 'WoWStatus').decode().splitlines()
        if not files:
            raise ValueError(f'No {edition} addon in {revision}')
        toc = git(root, 'show', f'{revision}:{prefix}WoWStatus/WoWStatus.toc').decode()
        version = re.search(r'^## Version: ([\w.\-]+)$', toc, re.MULTILINE).group(1)
        archive = downloads / f'WoWStatus-{edition}.zip'
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as package:
            for file in sorted(files):
                # Stable timestamps keep repeated builds byte-identical.
                info = zipfile.ZipInfo(file.removeprefix(prefix), date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                package.writestr(info, git(root, 'show', f'{revision}:{file}'))
        with zipfile.ZipFile(archive) as package:
            if package.testzip() is not None:
                raise ValueError(f'Broken archive: {archive}')
            names = set(package.namelist())
            for line in toc.splitlines():
                relative = line.strip().replace('\\', '/')
                if relative and not relative.startswith('#') and f'WoWStatus/{relative}' not in names:
                    raise ValueError(f'Missing addon file: {relative}')
        releases[edition] = {'version': version, 'file': archive.name,
                             'bytes': archive.stat().st_size,
                             'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}
    if len({release['version'] for release in releases.values()}) != 1:
        raise ValueError('Addon versions must match before publishing')
    html = (output / 'index.html').read_text()
    html = html.replace('__VERSION__', releases['vanilla']['version'])
    for edition, release in releases.items():
        html = html.replace(f'__{edition.upper()}_SIZE__', f"{release['bytes'] / 1024:.0f} KB")
    if re.search(r'__[A-Z_]+__', html):
        raise ValueError('Unresolved homepage placeholder')
    (output / 'index.html').write_text(html)
    (downloads / 'release.json').write_text(json.dumps({'addon_revision': revision, 'editions': releases}, indent=2) + '\n')
    print(f"Homepage built at {output}; addon {releases['vanilla']['version']} ({revision[:7]})")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--addon-ref', default='HEAD')
    parser.add_argument('--output', type=Path, default=Path('dist/homepage'))
    args = parser.parse_args()
    build(Path(__file__).resolve().parents[1], args.output.resolve(), args.addon_ref)
