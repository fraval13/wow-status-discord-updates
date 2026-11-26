"""Upload the verified release's separate edition ZIPs to Wago Addons.

WAGO_PROJECT_ID is the public eight-character project ID; WAGO_API_TOKEN is a
private developer API key. See docs/WAGO.md. --dry-run reads Wago's public game
catalogue and validates all selected packages without sending any upload.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parent))
from upload_curseforge import interface_version, multipart, release_notes, toc_fields  # noqa: E402

API = 'https://addons.wago.io/api'
ROOT = Path(__file__).resolve().parents[1]
EDITIONS = {
    'retail': ('retail', 'Retail'),
    'vanilla': ('classic', 'Classic Era'),
    'tbc': ('bc', 'TBC Anniversary'),
    'forever': ('forever', 'Forever'),
}


class UploadError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    """Never forward the developer's bearer token to a redirected URL."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPEN = build_opener(NoRedirect()).open


def call(request: Request, opener=OPEN, token: str = ''):
    try:
        with opener(request, timeout=180) as response:
            payload = response.read()
        # A successful upload can have an empty/non-JSON response. Do not turn
        # an accepted file into a failed attempt that the owner might duplicate.
        if request.get_method() == 'POST':
            return
        return json.loads(payload.decode('utf-8'))
    except HTTPError as error:
        hints = {
            401: 'Check the WAGO_API_TOKEN secret.',
            403: 'The token/account cannot publish to this project, or the project needs approval.',
            404: 'Check WAGO_PROJECT_ID in the Wago developer dashboard.',
            413: 'Wago refused the ZIP size; check the Forever voice bundle if that edition failed.',
            422: 'Wago rejected the release metadata; check its supported game patches and project state.',
        }
        # Do not print server bodies: they can repeat credentials or private data.
        message = f'Wago HTTP {error.code}. {hints.get(error.code, "Check the project dashboard before retrying.")}'
        if request.get_method() == 'GET':
            message = f'Wago catalogue HTTP {error.code}. Check public service access before uploading.'
    except (URLError, OSError, ValueError) as error:
        message = f'Wago request failed ({type(error).__name__}); check connectivity and the dashboard before retrying.'
    if token:
        message = message.replace(token, '[token]')
    raise UploadError(message)


def packages(downloads: Path, project: str, changelog: str, catalogue: dict, editions) -> list:
    """Preflight every selected file before the first POST, so a local problem
    cannot publish only half of a release. Never substitute another game's patch.
    """
    result, versions = [], set()
    if not isinstance(catalogue, dict) or not isinstance(catalogue.get('patches'), dict):
        raise UploadError('Wago returned no supported game patch catalogue.')
    for edition in editions:
        flavour, label = EDITIONS[edition]
        archive = downloads / f'WoWStatus-{edition}.zip'
        try:
            fields = toc_fields(archive)
            version = fields['Version']
            patch = interface_version(int(fields['Interface']))
        except (OSError, KeyError, ValueError, zipfile.BadZipFile) as error:
            raise UploadError(f'{archive.name} is missing or has an invalid TOC; build the release first.') from error
        if fields.get('X-Wago-ID') != project:
            raise UploadError(f'{archive.name} must declare X-Wago-ID {project}.')
        if not re.fullmatch(r'\d+\.\d+\.\d+', version) or f'## {version}' not in changelog.splitlines():
            raise UploadError(f'{archive.name} has no matching release in CHANGELOG.md.')
        supported = catalogue['patches'].get(flavour, [])
        if not isinstance(supported, list) or patch not in supported:
            raise UploadError(f'Wago does not list WoW client {patch} for {label}; no file was uploaded.')
        metadata = {
            'label': f'{version} ({label})',
            'stability': 'stable',
            'changelog': release_notes(changelog, version),
            f'supported_{flavour}_patches': [patch],
        }
        versions.add(version)
        result.append((archive, metadata, label, patch))
    if len(versions) != 1:
        raise UploadError('Selected edition ZIPs do not all have the same addon version.')
    return result


def upload(downloads: Path, project: str, token: str, changelog: str, *, editions=None,
           dry_run: bool = False, opener=OPEN) -> int:
    try:
        catalogue = call(Request(f'{API}/data/game', headers={
            'Accept': 'application/json', 'User-Agent': 'wow-status-release',
        }), opener)
        selected = packages(downloads, project, changelog, catalogue, editions or EDITIONS)
    except UploadError as error:
        print(f'::error::{error}')
        return 1
    failed = False
    for archive, metadata, label, patch in selected:
        if dry_run:
            print(f'DRY RUN {archive.name}: {json.dumps(metadata, ensure_ascii=True)}')
            continue
        try:
            body, content_type = multipart(metadata, archive.name, archive.read_bytes())
            request = Request(f'{API}/projects/{project}/version', data=body, method='POST', headers={
                'Authorization': f'Bearer {token}', 'Accept': 'application/json',
                'Content-Type': content_type, 'User-Agent': 'wow-status-release',
            })
            # Never automatically retry a POST: a timeout may follow acceptance.
            call(request, opener, token)
        except (UploadError, OSError) as error:
            message = str(error).replace(token, '[token]') if token else str(error)
            print(f'::error::{label} upload failed: {message}')
            failed = True
            continue
        print(f'Wago accepted {metadata["label"]} for WoW client {patch}.')
    return int(failed)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--downloads', type=Path, default=Path('dist/homepage/downloads'))
    parser.add_argument('--changelog', type=Path, default=ROOT / 'CHANGELOG.md')
    parser.add_argument('--edition', choices=['all', *EDITIONS], default='all')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    project = os.environ.get('WAGO_PROJECT_ID', '').strip()
    token = os.environ.get('WAGO_API_TOKEN', '').strip()
    if not re.fullmatch(r'[A-Za-z0-9]{8}', project):
        print('::error::WAGO_PROJECT_ID must be the eight-character ID from the Wago developer dashboard.')
        return 1
    if not args.dry_run and not token:
        print('::error::Set the WAGO_API_TOKEN GitHub Actions secret before uploading.')
        return 1
    try:
        notes = args.changelog.read_text(encoding='utf-8')
    except OSError:
        print('::error::Cannot read the release changelog.')
        return 1
    editions = EDITIONS if args.edition == 'all' else [args.edition]
    return upload(args.downloads, project, token, notes, editions=editions, dry_run=args.dry_run)


if __name__ == '__main__':
    sys.exit(main())
