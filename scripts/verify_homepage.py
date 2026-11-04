"""Verify the published homepage and every addon ZIP after a pipeline release.

The live site is compared with the release.json this machine just built, never only
with the manifest the site itself serves: a tampered site could regenerate that.
"""
import argparse
import hashlib
import importlib.util
import io
import json
import re
import time
import urllib.request
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

EDITIONS = ('vanilla', 'forever', 'tbc', 'retail')
MAX_BYTES = 32 * 1024 * 1024
FOLDER = 'WoWStatus/'


def _package_files():
    # The builder's own rule for what ships, so the two can never disagree.
    spec = importlib.util.spec_from_file_location(
        'build_homepage', Path(__file__).with_name('build_homepage.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.package_files


package_files = _package_files()


class DownloadLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = set()
        self.text = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.links.add(dict(attrs).get('href'))

    def handle_data(self, data):
        self.text.append(data)


def read(url):
    request = urllib.request.Request(url, headers={'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(request, timeout=20) as response:
        data = response.read(MAX_BYTES + 1)
        if response.status != 200 or len(data) > MAX_BYTES:
            raise ValueError('Invalid or oversized public response')
        return data


def check_entries(edition, package):
    """Require exactly the TOC, the files it lists and allowlisted assets, all inside WoWStatus/."""
    names = [item.filename for item in package.infolist()]
    if len(set(names)) != len(names):
        raise ValueError(f'The public {edition} ZIP has duplicate entries')
    for item in package.infolist():
        name = item.filename
        if (item.is_dir() or not name.startswith(FOLDER) or '\\' in name or ':' in name
                or any(part in ('', '.', '..') for part in name.split('/'))):
            raise ValueError(f'The public {edition} ZIP has an unexpected entry: {name!r}')
    present = {name.removeprefix(FOLDER) for name in names}
    if 'WoWStatus.toc' not in present:
        raise ValueError(f'The public {edition} ZIP has no TOC')
    toc = package.read(FOLDER + 'WoWStatus.toc').decode('utf-8')
    try:
        expected = package_files(toc, present)
    except ValueError as error:
        raise ValueError(f'The public {edition} ZIP is incomplete: {error}') from error
    unexpected = sorted(present.difference(expected))
    if unexpected:
        raise ValueError(f"The public {edition} ZIP has unexpected entries: {', '.join(unexpected)}")
    return toc


def verify(base, revision, fetch=read, *, expected):
    """Check the live site at base against expected, the release.json built locally for revision."""
    address = urlparse(base)
    if (address.username or address.password or address.query or address.fragment
            or (address.scheme != 'https' and not
                (address.scheme == 'http' and address.hostname in ('localhost', '127.0.0.1', '::1')))):
        raise ValueError('Use HTTPS, or a localhost preview URL')
    if not re.fullmatch('[a-f0-9]{40}', revision):
        raise ValueError('Expected a complete Git commit revision')
    if (expected.get('addon_revision') != revision
            or set(expected.get('editions', {})) != set(EDITIONS)):
        raise ValueError('The local release.json is not a complete build of this revision')
    base = base.rstrip('/')
    manifest = json.loads(fetch(base + '/downloads/release.json'))
    if not isinstance(manifest, dict) or manifest.get('addon_revision') != revision:
        raise ValueError('The live website is serving a different release revision')
    if manifest != expected:
        raise ValueError('The live release.json differs from the locally built one')
    html = fetch(base + '/').decode('utf-8')
    parser = DownloadLinks()
    parser.feed(html)
    text = ' '.join(parser.text)
    versions = set()
    for edition in EDITIONS:
        release = manifest['editions'][edition]
        name = f'WoWStatus-{edition}.zip'
        path = '/downloads/' + name
        if release.get('file') != name or path not in parser.links:
            raise ValueError(f'Missing or incorrect {edition} download link')
        data = fetch(base + path)
        # release is the local build's entry, since the served manifest equals it.
        if (len(data) != release.get('bytes') or
                hashlib.sha256(data).hexdigest() != release.get('sha256')):
            raise ValueError(f'The public {edition} ZIP does not match the locally built one')
        with zipfile.ZipFile(io.BytesIO(data)) as package:
            if (sum(item.file_size for item in package.infolist()) > MAX_BYTES
                    or package.testzip() is not None):
                raise ValueError(f'The public {edition} ZIP is invalid')
            toc = check_entries(edition, package)
            match = re.search(r'^## Version: ([\w.\-]+)$', toc, re.MULTILINE)
            if not match or match.group(1) != release.get('version'):
                raise ValueError(f'The public {edition} version is incorrect')
        versions.add(release['version'])
    if len(versions) != 1 or f'VERSION {next(iter(versions))}' not in text:
        raise ValueError('The homepage and addon versions do not agree')
    if re.search(r'__[A-Z_]+__', html):
        raise ValueError('The homepage contains unexpanded release placeholders')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--manifest', type=Path, required=True,
                        help='downloads/release.json from the local build of --revision')
    parser.add_argument('--attempts', type=int, default=1)
    parser.add_argument('--delay', type=float, default=5)
    args = parser.parse_args()
    if not 1 <= args.attempts <= 12 or not 0 <= args.delay <= 10:
        parser.error('Use 1–12 attempts and a delay of 0–10 seconds')
    try:
        expected = json.loads(args.manifest.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        parser.error(f'Cannot read the local manifest {args.manifest}: {error}')
    if not isinstance(expected, dict) or expected.get('addon_revision') != args.revision:
        parser.error(f'{args.manifest} was not built from revision {args.revision}')
    for attempt in range(args.attempts):
        try:
            result = verify(args.url, args.revision, expected=expected)
            print(f"Verified live release {args.revision}: " + ', '.join(
                f"{edition} {result['editions'][edition]['version']}" for edition in EDITIONS))
            break
        except (OSError, ValueError, KeyError, zipfile.BadZipFile):
            if attempt == args.attempts - 1:
                raise
            time.sleep(args.delay)
