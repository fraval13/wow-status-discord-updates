"""Build the static homepage and standalone ZIPs from a committed addon revision.

Usage: python scripts/build_homepage.py [--addon-ref HEAD] [--output dist/homepage]
The website source comes from the workspace; addon downloads come only from Git,
so an unfinished local addon change can never leak into a public download.
Each build replaces the output folder as a whole: no file of an earlier build
survives, and an existing folder that is not an earlier build is refused.
"""
import argparse
import hashlib
import html as html_text
import json
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from whats_new import parse as parse_changelog  # noqa: E402

EDITIONS = ('vanilla', 'forever', 'tbc', 'retail')
# Files the game loads without a TOC line. Anything else committed beside the addon
# (editor files, a WTF/ folder, notes) stays out of the public ZIP.
# Dot files such as macOS ._Logo.tga resource forks never match.
ASSETS = (re.compile(r'Textures/[^/.][^/]*\.tga', re.IGNORECASE), re.compile(r'Bindings\.xml'))
# Website notes that never ship, and file-manager files (Finder, Explorer) anywhere in website/.
NOT_SHIPPED = ('README.md', 'ARTWORK.md')
DESKTOP_FILES = ('.DS_Store', 'Thumbs.db', 'desktop.ini')


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args])


def git_files(root, revision, paths):
    """Read many committed files with one `git cat-file --batch` process.

    One `git show` per file meant over a hundred processes per build, which is slow
    where starting a process is expensive (Windows).
    """
    specs = []
    for path in paths:
        if '\n' in path or '\r' in path:
            raise ValueError(f'Unsupported file name: {path!r}')
        specs.append(f'{revision}:{path}\n'.encode('utf-8'))
    output = subprocess.run(['git', '-C', str(root), 'cat-file', '--batch'], input=b''.join(specs),
                            stdout=subprocess.PIPE, check=True).stdout
    contents, position = {}, 0
    for path in paths:
        end = output.index(b'\n', position)
        header = output[position:end].split(b' ')
        if len(header) != 3 or header[1] != b'blob':
            raise ValueError(f'{path} is not a file in {revision}')
        size = int(header[2])
        start = end + 1
        contents[path] = output[start:start + size]
        if output[start + size:start + size + 1] != b'\n':
            raise ValueError(f'Malformed git output for {path}')
        position = start + size + 1
    return contents


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
    files = sorted({'WoWStatus.toc', *listed, *assets})
    # Players unzip on case-insensitive file systems, where one of the two would be lost.
    folded = {}
    for name in files:
        if (other := folded.setdefault(name.casefold(), name)) != name:
            raise ValueError(f'Addon files differ only by case: {other}, {name}')
    return files


def project_version(root, revision):
    try:
        pyproject = tomllib.loads(git(root, 'show', f'{revision}:pyproject.toml').decode())
        return pyproject['project']['version']
    except (subprocess.CalledProcessError, KeyError) as error:
        raise ValueError(f'No pyproject.toml project version in {revision}') from error


def release_notes(root, revision, version):
    """The CHANGELOG.md notes for this release; the addon's What's New page shows the same."""
    try:
        text = git(root, 'show', f'{revision}:CHANGELOG.md').decode('utf-8')
    except subprocess.CalledProcessError as error:
        raise ValueError(f'No CHANGELOG.md in {revision}') from error
    for section, notes in parse_changelog(text):
        if section == version:
            return notes
    raise ValueError(f'CHANGELOG.md has no notes for {version}; the release pull request adds them')


def earlier_build(folder):
    """True if folder holds a homepage build: an index.html and a build's release.json."""
    try:
        manifest = json.loads((folder / 'downloads/release.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return False
    return ((folder / 'index.html').is_file() and isinstance(manifest, dict)
            and re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}', str(manifest.get('addon_revision'))) is not None
            and isinstance(manifest.get('editions'), dict))


def replaceable(output):
    """Raise unless output is absent, empty or an earlier build, the only folders a build replaces."""
    if output.is_symlink() or output.exists() and not (output.is_dir() and (
            not any(output.iterdir()) or earlier_build(output))):
        raise ValueError(f'{output} is not an earlier homepage build; choose a new or empty --output folder')


def replace_output(staging, output):
    """Put the finished build at output in place of any earlier build."""
    if not output.exists():
        staging.rename(output)
        return
    # Windows can't rename onto an existing folder, so the earlier build moves aside first.
    aside = Path(tempfile.mkdtemp(prefix=f'.{output.name}-old-', dir=output.parent))
    try:
        output.rename(aside / 'build')
    except OSError as error:
        aside.rmdir()
        raise ValueError(f'Could not replace {output} ({error}); close any program using it and build again') from error
    try:
        staging.rename(output)
    except BaseException:
        try:
            (aside / 'build').rename(output)
        except OSError as error:
            raise ValueError(f'Could not put the earlier build back ({error}); it is in {aside / "build"}') from error
        aside.rmdir()
        raise
    shutil.rmtree(aside, ignore_errors=True)
    if aside.exists():
        print(f'Could not delete the earlier build in {aside}; delete it by hand', file=sys.stderr)


def write_package(root, revision, folder, files, archive):
    """Write one edition's ZIP: files read from folder (ending in /) at revision, under WoWStatus/."""
    contents = git_files(root, revision, [folder + file for file in files])
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as package:
        for file in files:
            # Stable timestamps keep repeated builds byte-identical.
            info = zipfile.ZipInfo(f'WoWStatus/{file}', date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            package.writestr(info, contents[folder + file])
    with zipfile.ZipFile(archive) as package:
        if package.testzip() is not None:
            raise ValueError(f'Broken archive: {archive}')


def write_site(root, output, revision, editions, version, notes):
    """Write the website and the four ZIPs into the new, empty folder output."""
    for source in (root / 'website').iterdir():
        if source.name in NOT_SHIPPED or source.name in DESKTOP_FILES:
            continue
        destination = output / source.name
        if source.is_dir():
            shutil.copytree(source, destination, ignore=shutil.ignore_patterns(*DESKTOP_FILES))
        else:
            shutil.copy2(source, destination)
    downloads = output / 'downloads'
    downloads.mkdir(exist_ok=True)
    releases = {}
    for edition, (files, edition_version) in editions.items():
        archive = downloads / f'WoWStatus-{edition}.zip'
        write_package(root, revision, f'addon/{edition}/WoWStatus/', files, archive)
        releases[edition] = {'version': edition_version, 'file': archive.name,
                             'bytes': archive.stat().st_size,
                             'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}
    html = (output / 'index.html').read_text(encoding='utf-8')
    html = html.replace('__VERSION__', version)
    html = html.replace('__WHATS_NEW__', ''.join(f'<li>{html_text.escape(note)}</li>' for note in notes))
    for edition, release in releases.items():
        html = html.replace(f'__{edition.upper()}_SIZE__', f"{release['bytes'] / 1024:.0f} KB")
    if re.search(r'__[A-Z_]+__', html):
        raise ValueError('Unresolved homepage placeholder')
    (output / 'index.html').write_text(html, encoding='utf-8')
    (downloads / 'release.json').write_text(json.dumps({'addon_revision': revision, 'editions': releases}, indent=2) + '\n', encoding='utf-8')


def build(root, output, addon_ref):
    revision = git(root, 'rev-parse', '--verify', f'{addon_ref}^{{commit}}').decode().strip()
    output = Path(output)
    replaceable(output)
    # Check every edition before writing anything.
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
        editions[edition] = files, match.group(1)
    expected = project_version(root, revision)
    if any(version != expected for _, version in editions.values()):
        found = ', '.join(f'{edition} {version}' for edition, (_, version) in editions.items())
        raise ValueError(f'Addon TOC versions ({found}) must all equal pyproject.toml version {expected}')
    notes = release_notes(root, revision, expected)
    # Build in a new folder beside the output and swap it in only when complete, so a
    # failed build leaves the earlier one untouched and no stale asset or old ZIP of an
    # earlier build survives a rebuild (issue #19).
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f'.{output.name}-', dir=output.parent))
    try:
        staging.chmod(0o755)  # mkdtemp's private mode would otherwise become the site folder's
        write_site(root, staging, revision, editions, expected, notes)
        replace_output(staging, output)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    print(f'Homepage built at {output}; addon {expected} ({revision[:7]})')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--addon-ref', default='HEAD')
    parser.add_argument('--output', type=Path, default=Path('dist/homepage'))
    args = parser.parse_args()
    # absolute(), not resolve(): a symlinked --output must reach replaceable() as a symlink.
    build(Path(__file__).resolve().parents[1], args.output.absolute(), args.addon_ref)
