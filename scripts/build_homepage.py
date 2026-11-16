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
import struct
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from whats_new import parse as parse_changelog  # noqa: E402

EDITIONS = ('vanilla', 'forever', 'tbc', 'retail')
# Files the game loads without a TOC line. Anything else committed beside the addon
# (editor files, a WTF/ folder, notes) stays out of the public ZIP.
# Dot files such as macOS ._Logo.tga resource forks never match.
# Sounds/Voices/<clip>.ogg are the spoken reactions that ship inside the addon
# (scripts/voices.py sample), named by their 12-character clip id.
ASSETS = (re.compile(r'Textures/[^/.][^/]*\.tga', re.IGNORECASE), re.compile(r'Bindings\.xml'),
          re.compile(r'Sounds/Voices/[0-9a-f]{12}\.ogg'))
# Website notes that never ship, and file-manager files (Finder, Explorer) anywhere in website/.
NOT_SHIPPED = ('README.md', 'ARTWORK.md')
DESKTOP_FILES = ('.DS_Store', 'Thumbs.db', 'desktop.ini')
# The link preview chat clients show for a pasted homepage link (issue #190).
# scripts/make_link_preview.py draws it from the page's artwork; the build only checks it.
LINK_PREVIEW = '/assets/link-preview.jpg'
LINK_PREVIEW_SIZE = (1200, 630)
# Tags whose value is fixed; the text tags below must be present and not empty.
PREVIEW_TAGS = {'og:type': 'website', 'og:image:type': 'image/jpeg',
                'og:image:width': str(LINK_PREVIEW_SIZE[0]), 'og:image:height': str(LINK_PREVIEW_SIZE[1]),
                'twitter:card': 'summary_large_image'}
PREVIEW_TEXT = ('og:site_name', 'og:title', 'og:description', 'og:url', 'og:image', 'og:image:alt',
                'twitter:title', 'twitter:description', 'twitter:image', 'twitter:image:alt')


class MetaTags(HTMLParser):
    """Every <meta property|name=... content=...> tag of a page, in order."""
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        key = attrs.get('property') or attrs.get('name')
        if tag == 'meta' and key:
            self.tags.append((key, attrs.get('content') or ''))


def jpeg_size(data):
    """(width, height) of a complete baseline or progressive JPEG, or None if data is not one."""
    if not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9'):
        return None
    position = 2
    while position + 4 <= len(data) and data[position] == 0xFF:
        marker = data[position + 1]
        length = struct.unpack('>H', data[position + 2:position + 4])[0]
        # SOF0-SOF15, except DHT (C4), JPG (C8) and DAC (CC), carry the frame size.
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            if position + 9 > len(data):
                return None
            height, width = struct.unpack('>HH', data[position + 5:position + 9])
            return width, height
        position += 2 + length
    return None


def check_link_preview(html, read):
    """Check the page's Open Graph and Twitter card tags and the image they name.

    read(path) returns the bytes served at that site path. Discord and other chat
    clients show a large card only with twitter:card and the image's size, so an
    incomplete set fails the build and the live verification.
    """
    parser = MetaTags()
    parser.feed(html)
    tags, wrong = {}, []
    for key, value in parser.tags:
        if key in tags and (key in PREVIEW_TAGS or key in PREVIEW_TEXT):
            wrong.append(f'{key} (repeated)')  # scrapers disagree on which one wins
        tags.setdefault(key, value)
    wrong += [key for key, value in PREVIEW_TAGS.items() if tags.get(key) != value]
    wrong += [key for key in PREVIEW_TEXT if not tags.get(key, '').strip()]
    site = urlparse(tags.get('og:url', ''))
    image = urlparse(tags.get('og:image', ''))
    if site.scheme != 'https' or not site.hostname:
        wrong.append('og:url')
    # The image must come from this site, where the build put it and verification fetched it.
    # A query such as ?v=2 is allowed: it makes chat clients fetch a changed image again.
    if (image.scheme, image.netloc) != (site.scheme, site.netloc) or image.path != LINK_PREVIEW \
            or image.params or image.fragment:
        wrong.append('og:image')
    if tags.get('twitter:image') != tags.get('og:image'):
        wrong.append('twitter:image')
    if wrong:
        raise ValueError(f"Missing or incorrect link preview tags: {', '.join(sorted(set(wrong)))}")
    if jpeg_size(read(LINK_PREVIEW)) != LINK_PREVIEW_SIZE:
        raise ValueError(f'{LINK_PREVIEW} must be a complete {LINK_PREVIEW_SIZE[0]}×{LINK_PREVIEW_SIZE[1]} '
                         'JPEG; run python scripts/make_link_preview.py')


def site_file(folder):
    """A read() for check_link_preview: the file at that site path below folder, or b''."""
    def read(path):
        file = folder / path.lstrip('/')
        return file.read_bytes() if file.is_file() else b''
    return read
# __NAME__ markers the build fills in website pages; the public verifier rejects any left over.
PLACEHOLDER = re.compile(r'__([A-Z_]+)__')


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


def changelog_sections(root, revision, version):
    """CHANGELOG.md sections at revision from version down, newest first, as (version, notes).

    The parser is the one behind the addon's What's New page, so a changelog it cannot
    parse fails the build, and the release being built must have notes.
    """
    try:
        text = git(root, 'show', f'{revision}:CHANGELOG.md').decode('utf-8')
    except subprocess.CalledProcessError as error:
        raise ValueError(f'No CHANGELOG.md in {revision}') from error
    sections = parse_changelog(text)
    built = [section for section, _ in sections]
    if version not in built:
        raise ValueError(f'CHANGELOG.md has no notes for {version}; the release pull request adds them')
    # Sections above the built version are not released yet (notes committed before the
    # version bump, or an older --addon-ref), so they stay off the public site.
    return sections[built.index(version):]


def changelog_anchor(version):
    """The stable fragment for one release on /changelog/, e.g. v1.52.0."""
    return f'v{version}'


def note_items(notes):
    """Release notes as <li> items, for the homepage release panel and /changelog/ alike."""
    return ''.join(f'<li>{html_text.escape(note)}</li>' for note in notes)


def render_changelog(sections):
    """The /changelog/ entries: one section per release with a linkable anchor.

    The first section, the version being built, is marked as the latest release.
    """
    entries = []
    for index, (version, notes) in enumerate(sections):
        anchor = changelog_anchor(version)
        latest = ' <small>LATEST</small>' if index == 0 else ''
        items = note_items(notes)
        entries.append(f'<section class="release-entry" id="{anchor}" aria-labelledby="{anchor}-title">'
                       f'<h2 id="{anchor}-title"><a href="#{anchor}">Patch {version}</a>{latest}</h2>'
                       f'<ul>{items}</ul></section>')
    return '\n'.join(entries)


def fill(path, values):
    """Replace every __NAME__ placeholder in the file at path in one pass.

    One pass, so an inserted value is never searched for later placeholders. A template
    placeholder without a value fails, and so does inserted text that would look like
    one: scripts/verify_homepage.py rejects any such text on the live site.
    """
    text = path.read_text(encoding='utf-8')
    unknown = sorted(set(PLACEHOLDER.findall(text)) - set(values))
    if unknown:
        raise ValueError(f"Unresolved placeholder in {path.name}: {', '.join(unknown)}")
    text = PLACEHOLDER.sub(lambda match: values[match.group(1)], text)
    if (leftover := PLACEHOLDER.search(text)) is not None:
        raise ValueError(f'{path.name}: a release note may not contain placeholder text like {leftover.group(0)}')
    path.write_text(text, encoding='utf-8')


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


def write_site(root, output, revision, editions, version, sections):
    """Write the website, its changelog page and the four ZIPs into the new, empty folder output.

    sections is the parsed CHANGELOG.md from version, the release being built, down.
    """
    for source in (root / 'website').iterdir():
        if source.name in NOT_SHIPPED or source.name in DESKTOP_FILES:
            continue
        destination = output / source.name
        if source.is_dir():
            shutil.copytree(source, destination, ignore=shutil.ignore_patterns(*NOT_SHIPPED, *DESKTOP_FILES))
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
    shared = {'VERSION': version, 'LATEST_ANCHOR': changelog_anchor(version)}
    sizes = {f'{edition.upper()}_SIZE': f"{release['bytes'] / 1024:.0f} KB" for edition, release in releases.items()}
    fill(output / 'index.html', {**shared, **sizes, 'WHATS_NEW': note_items(sections[0][1])})
    changelog = output / 'changelog/index.html'
    if not changelog.is_file():
        raise ValueError('website/changelog/index.html is missing; the homepage links to it')
    count = len(sections)
    fill(changelog, {**shared, 'RELEASES': f"{count} release{'' if count == 1 else 's'}",
                     'CHANGELOG': render_changelog(sections)})
    (downloads / 'release.json').write_text(json.dumps({'addon_revision': revision, 'editions': releases}, indent=2) + '\n', encoding='utf-8')


def build(root, output, addon_ref):
    revision = git(root, 'rev-parse', '--verify', f'{addon_ref}^{{commit}}').decode().strip()
    output = Path(output)
    replaceable(output)
    website = root / 'website'
    check_link_preview((website / 'index.html').read_text(encoding='utf-8'), site_file(website))
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
    sections = changelog_sections(root, revision, expected)
    # Build in a new folder beside the output and swap it in only when complete, so a
    # failed build leaves the earlier one untouched and no stale asset or old ZIP of an
    # earlier build survives a rebuild (issue #19).
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f'.{output.name}-', dir=output.parent))
    try:
        staging.chmod(0o755)  # mkdtemp's private mode would otherwise become the site folder's
        write_site(root, staging, revision, editions, expected, sections)
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
