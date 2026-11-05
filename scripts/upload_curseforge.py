"""Upload the built addon ZIPs to the CurseForge project, one file per edition.

Reads the ZIPs that ``build_homepage.py`` wrote, takes each edition's game version
from its TOC ``## Interface:`` line and uploads it with the release's notes from
``CHANGELOG.md``. Standard library only.

Configuration comes from the environment so that nothing secret is in the
repository: ``CURSEFORGE_API_TOKEN`` (an API token from the CurseForge author
settings) and ``CURSEFORGE_PROJECT_ID`` (the number on the project's page).
Without both, it prints a notice and exits 0, so the pipeline step does nothing
until the project exists.

An edition whose game version CurseForge does not list (for example a client it
does not support) is skipped with a warning. Exit status: 0 when every edition
was uploaded or skipped and at least one was uploaded, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API = 'https://wow.curseforge.com'
ROOT = Path(__file__).resolve().parents[1]
EDITIONS = (
    ('retail', 'Retail'),
    ('vanilla', 'Classic Era'),
    ('tbc', 'TBC Anniversary'),
    ('forever', 'Forever'),
)


def interface_version(interface: int) -> str:
    """11509 -> '1.15.9'; 120105 -> '12.1.5'."""
    return f'{interface // 10000}.{interface // 100 % 100}.{interface % 100}'


def toc_fields(archive: Path) -> dict[str, str]:
    with zipfile.ZipFile(archive) as package:
        text = package.read('WoWStatus/WoWStatus.toc').decode('utf-8-sig')
    fields = {}
    for line in text.splitlines():
        match = re.match(r'^## ([^:]+):\s*(.*?)\s*$', line)
        if match:
            fields[match.group(1)] = match.group(2)
    return fields


def release_notes(changelog: str, version: str) -> str:
    """The `- ` lines under `## <version>`, as Markdown."""
    lines, inside = [], False
    for line in changelog.splitlines():
        if line.startswith('## '):
            if inside:
                break
            inside = line[3:].strip() == version
        elif inside and line.startswith('- '):
            lines.append(line)
    return '\n'.join(lines) or f'WoW Status {version}.'


def version_ids(versions: list[dict], name: str) -> tuple[list[int], str | None]:
    """IDs for an exact game version name, else the newest patch of the same
    major.minor (CurseForge can lag a new client patch). Returns (ids, used name)."""
    exact = [v['id'] for v in versions if v.get('name') == name]
    if exact:
        return exact, name
    prefix = name.rsplit('.', 1)[0] + '.'

    def patch(v: dict) -> int:
        tail = v['name'][len(prefix):]
        return int(tail) if tail.isdigit() else -1

    near = [v for v in versions if isinstance(v.get('name'), str) and v['name'].startswith(prefix) and patch(v) >= 0]
    if not near:
        return [], None
    best = max(patch(v) for v in near)
    chosen = [v for v in near if patch(v) == best]
    return [v['id'] for v in chosen], chosen[0]['name']


def multipart(metadata: dict, filename: str, payload: bytes) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="metadata"\r\n'
        f'Content-Type: application/json\r\n\r\n'.encode('utf-8') + json.dumps(metadata).encode('utf-8') + b'\r\n',
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f'Content-Type: application/zip\r\n\r\n'.encode('utf-8') + payload + b'\r\n',
        f'--{boundary}--\r\n'.encode('utf-8'),
    ]
    return b''.join(parts), f'multipart/form-data; boundary={boundary}'


class UploadError(Exception):
    pass


HINTS = {
    400: 'A "malformed" token is not an upload token: create one under API Tokens in your '
         'CurseForge author account (not a Core API key from console.curseforge.com).',
    401: 'The CURSEFORGE_API_TOKEN secret is empty or was not sent.',
    403: 'The token was refused: it may be revoked, or belong to an account without '
         'upload rights on this project.',
    404: 'Check CURSEFORGE_PROJECT_ID: no such project, or it is not a WoW project.',
}


def call(request: Request, opener=urlopen, token: str = ''):
    """JSON from CurseForge, or UploadError with its own message. CurseForge repeats a
    malformed token in its message, so the token is removed from anything reported."""
    try:
        with opener(request, timeout=120) as response:
            return json.loads(response.read().decode('utf-8'))
    except HTTPError as error:
        try:
            detail = json.loads(error.read().decode('utf-8', 'replace')).get('errorMessage', '')
        except (ValueError, AttributeError, OSError):
            detail = ''
        message = f'HTTP {error.code}' + (f': {detail}' if detail else '')
        if error.code in HINTS:
            message += ' ' + HINTS[error.code]
    except URLError as error:
        message = f'CurseForge could not be reached: {error.reason}'
    if token:
        message = message.replace(token, '[token]')
    raise UploadError(message)


def upload(downloads: Path, project_id: str, token: str, changelog: str, opener=urlopen) -> int:
    headers = {'X-Api-Token': token, 'User-Agent': 'wow-status-release'}
    try:
        versions = call(Request(f'{API}/api/game/versions', headers=headers), opener, token)
    except UploadError as error:
        print(f'::error::Reading CurseForge game versions failed: {error}')
        return 1
    uploaded, failed = [], []
    for edition, label in EDITIONS:
        archive = downloads / f'WoWStatus-{edition}.zip'
        if not archive.is_file():
            print(f'::error::{archive} is missing; build the homepage first.')
            failed.append(edition)
            continue
        fields = toc_fields(archive)
        version = fields['Version']
        wanted = interface_version(int(fields['Interface']))
        ids, used = version_ids(versions, wanted)
        if not ids:
            print(f'::warning::CurseForge lists no game version {wanted}; {label} was not uploaded.')
            continue
        if used != wanted:
            print(f'::warning::CurseForge has no {wanted} yet; {label} is tagged {used}.')
        metadata = {
            'changelog': release_notes(changelog, version),
            'changelogType': 'markdown',
            'displayName': f'WoW Status {version} ({label})',
            'gameVersions': ids,
            'releaseType': 'release',
        }
        body, content_type = multipart(metadata, archive.name, archive.read_bytes())
        request = Request(f'{API}/api/projects/{project_id}/upload-file', data=body, method='POST',
                          headers={**headers, 'Content-Type': content_type})
        try:
            result = call(request, opener, token)
        except UploadError as error:  # Report every edition, then fail.
            print(f'::error::{label} upload failed: {error}')
            failed.append(edition)
            continue
        print(f'Uploaded {label} {version} for {used} as CurseForge file {result.get("id")}.')
        uploaded.append(edition)
    return 0 if uploaded and not failed else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--downloads', type=Path, default=Path('dist/homepage/downloads'))
    parser.add_argument('--changelog', type=Path, default=ROOT / 'CHANGELOG.md')
    args = parser.parse_args(argv)
    token = os.environ.get('CURSEFORGE_API_TOKEN', '').strip()
    project_id = os.environ.get('CURSEFORGE_PROJECT_ID', '').strip()
    if not token or not project_id:
        print('::notice::CurseForge upload skipped: CURSEFORGE_API_TOKEN or CURSEFORGE_PROJECT_ID is not set.')
        return 0
    if not project_id.isdigit():
        print('::error::CURSEFORGE_PROJECT_ID must be the numeric project ID.')
        return 1
    return upload(args.downloads, project_id, token, args.changelog.read_text(encoding='utf-8'))


if __name__ == '__main__':
    sys.exit(main())
