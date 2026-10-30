"""Verify the published homepage and every addon ZIP after a pipeline release."""
import argparse
import hashlib
import io
import json
import re
import time
import urllib.request
import zipfile
from html.parser import HTMLParser
from urllib.parse import urlparse

EDITIONS = ('vanilla', 'forever', 'tbc', 'retail')
MAX_BYTES = 32 * 1024 * 1024


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


def verify(base, revision, fetch=read):
    address = urlparse(base)
    if (address.username or address.password or address.query or address.fragment
            or (address.scheme != 'https' and not
                (address.scheme == 'http' and address.hostname in ('localhost', '127.0.0.1', '::1')))):
        raise ValueError('Use HTTPS, or a localhost preview URL')
    if not re.fullmatch('[a-f0-9]{40}', revision):
        raise ValueError('Expected a complete Git commit revision')
    base = base.rstrip('/')
    manifest = json.loads(fetch(base + '/downloads/release.json'))
    if manifest.get('addon_revision') != revision:
        raise ValueError('The live website is serving a different release revision')
    if set(manifest.get('editions', {})) != set(EDITIONS):
        raise ValueError('The live website does not contain every addon edition')
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
        if (len(data) != release.get('bytes') or
                hashlib.sha256(data).hexdigest() != release.get('sha256')):
            raise ValueError(f'The public {edition} ZIP does not match its checksum')
        with zipfile.ZipFile(io.BytesIO(data)) as package:
            if (sum(item.file_size for item in package.infolist()) > MAX_BYTES
                    or package.testzip() is not None):
                raise ValueError(f'The public {edition} ZIP is invalid')
            toc = package.read('WoWStatus/WoWStatus.toc').decode('utf-8')
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
    parser.add_argument('--attempts', type=int, default=1)
    parser.add_argument('--delay', type=float, default=5)
    args = parser.parse_args()
    if not 1 <= args.attempts <= 12 or not 0 <= args.delay <= 10:
        parser.error('Use 1–12 attempts and a delay of 0–10 seconds')
    for attempt in range(args.attempts):
        try:
            result = verify(args.url, args.revision)
            print(f"Verified live release {args.revision}: " + ', '.join(
                f"{edition} {result['editions'][edition]['version']}" for edition in EDITIONS))
            break
        except (OSError, ValueError, KeyError, zipfile.BadZipFile):
            if attempt == args.attempts - 1:
                raise
            time.sleep(args.delay)
