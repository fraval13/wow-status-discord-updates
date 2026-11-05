"""Publish the built static homepage through the existing authorized SSH account.

Before contacting the host it checks the build folder (issue #19). It must be a
build of this checkout's HEAD commit, the website/ files and builder it was built
from must match Git, every ZIP must match its release.json checksum, and it must
equal a fresh build made now, file for file, so no stale or changed file ships.
What it uploads is that fresh build.

Renders the Caddyfile's group routes from the template in that commit and the
private groups.json (by default the server's own copy; group names never come from
Git). On the server, deploy/install_homepage.py checks the upload's checksum,
validates the candidate Caddyfile outside the web root, keeps the previous static
release and Caddy config for rollback and cleans up after any failure. Does not
restart either application or read its Discord secrets. --dry-run prints the
Caddy change and stops; its output holds the group route keys, so do not paste it
anywhere public.
"""
import argparse
import contextlib
import datetime
import difflib
import hashlib
import importlib.util
import io
import json
import shlex
import subprocess
import tarfile
import tempfile
from pathlib import Path

import render_caddyfile

PRIVATE_GROUPS = render_caddyfile.GROUPS.as_posix()
DEPLOY = Path(__file__).resolve().parent
REPOSITORY = DEPLOY.parent
TEMPLATE = 'deploy/Caddyfile.production.template'
# The build reads these from the working tree; everything else it reads from Git.
BUILD_INPUTS = ('website', 'scripts/build_homepage.py', 'scripts/whats_new.py')
REBUILD = 'Rebuild with python scripts/build_homepage.py and publish again.'


def git(*args):
    return subprocess.check_output(['git', '-C', str(REPOSITORY), *args])


def files(folder):
    """Relative POSIX path -> path of every file below folder."""
    found = {}
    for path in sorted(folder.rglob('*')):
        if path.is_symlink():
            raise ValueError(f'{path} is a symlink; the homepage may not contain symlinks')
        if path.is_file():
            found[path.relative_to(folder).as_posix()] = path
    return found


def check_build(directory, revision, fresh):
    """Raise ValueError unless directory is a fresh build of revision; return the folder to upload.

    Builds the reference into fresh, a path that does not exist yet.
    """
    manifest = directory / 'downloads/release.json'
    if not (directory / 'index.html').is_file() or not manifest.is_file():
        raise ValueError('Build the homepage before publishing')
    release = json.loads(manifest.read_text(encoding='utf-8'))
    release = release if isinstance(release, dict) else {}
    if release.get('addon_revision') != revision:
        raise ValueError(f'{directory} was built for revision {release.get("addon_revision")}, but this '
                         f'checkout is at {revision}. {REBUILD}')
    status = git('status', '--porcelain', '-z', '--no-renames', '--untracked-files=all', '--ignored',
                 '--', *BUILD_INPUTS).decode('utf-8')
    uncommitted = [entry[3:] for entry in status.split('\0') if entry]
    if uncommitted:
        raise ValueError(f'Uncommitted or untracked build input: {", ".join(uncommitted)}. The build would '
                         'ship it, but the revision does not hold it. Commit or remove it, rebuild and publish again.')
    builder = load_builder()
    editions = release.get('editions') if isinstance(release.get('editions'), dict) else {}
    for edition in builder.EDITIONS:
        item = editions.get(edition) if isinstance(editions.get(edition), dict) else {}
        archive = directory / 'downloads' / f'WoWStatus-{edition}.zip'
        if (item.get('file') != archive.name or not archive.is_file() or archive.stat().st_size != item.get('bytes')
                or hashlib.sha256(archive.read_bytes()).hexdigest() != item.get('sha256')):
            raise ValueError(f'downloads/{archive.name} does not match its checksum in release.json. {REBUILD}')
    with contextlib.redirect_stdout(io.StringIO()):
        builder.build(REPOSITORY, fresh, revision)
    built, expected = files(directory), files(fresh)
    problems = [(label, names) for label, names in [
        ('stale or extra', sorted(built.keys() - expected.keys())),
        ('missing', sorted(expected.keys() - built.keys())),
        ('different', sorted(name for name in built.keys() & expected.keys()
                             if built[name].read_bytes() != expected[name].read_bytes()))] if names]
    if problems:
        found = '; '.join(f'{label}: {", ".join(names)}' for label, names in problems)
        raise ValueError(f'{directory} is not a fresh build of {revision} ({found}). {REBUILD}')
    return fresh


def load_builder():
    spec = importlib.util.spec_from_file_location('build_homepage', REPOSITORY / 'scripts/build_homepage.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def private_groups(path, ssh):
    """The private group list: a local file if given, otherwise the server's own."""
    if path is not None:
        return json.loads(path.read_text(encoding='utf-8'))
    result = subprocess.run([*ssh, 'cat ' + PRIVATE_GROUPS], capture_output=True)
    if result.returncode:
        raise SystemExit(f'Could not read {PRIVATE_GROUPS} on the host. The current deployment receiver '
                         'writes it on its first run; or create it (deploy/SERVER.md), or pass --groups-config.')
    return json.loads(result.stdout.decode('utf-8'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--directory', type=Path, default=Path('dist/homepage'))
    parser.add_argument('--groups-config', type=Path,
                        help=f'Local private groups.json instead of the host\'s {PRIVATE_GROUPS}')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show how the live Caddyfile would change, then stop without uploading anything')
    args = parser.parse_args(argv)
    revision = git('rev-parse', '--verify', 'HEAD^{commit}').decode('utf-8').strip()
    with tempfile.TemporaryDirectory(prefix='wow-homepage-') as temporary:
        temporary = Path(temporary)
        site = None
        if not args.dry_run:
            try:  # every local check runs before the host is contacted
                site = check_build(args.directory.resolve(), revision, temporary / 'homepage')
            except ValueError as error:
                parser.error(str(error))
        ssh = ['ssh', '-F', '/dev/null', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', args.host]
        old_config = subprocess.check_output([*ssh, 'cat /etc/caddy/Caddyfile'])
        # Refuse an unrelated host/config rather than replacing another site's setup.
        if b'wow.frankvalde.com {' not in old_config or b'handle_path /groups/' not in old_config:
            parser.error('The target does not have the expected existing WoW gateway')
        # The committed template: an uncommitted local edit never reaches the server.
        template = git('show', f'{revision}:{TEMPLATE}').decode('utf-8')
        caddyfile = render_caddyfile.render(private_groups(args.groups_config, ssh), template)
        # Publishing the homepage never changes group routes. Differing routes mean a partial
        # or stale --groups-config, a checkout whose key derivation differs from the deployed
        # one, or the wrong host; any of them could cut a group off.
        live_routes, new_routes = render_caddyfile.routes(old_config.decode('utf-8')), render_caddyfile.routes(caddyfile)
        refusal = (f'The rendered Caddyfile would remove {len(live_routes - new_routes)} and add '
                   f'{len(new_routes - live_routes)} group route(s). The homepage publisher keeps the live '
                   'routes; change them with deploy/render_caddyfile.py on the server (deploy/SERVER.md).')
        if args.dry_run:
            diff = ''.join(difflib.unified_diff(old_config.decode('utf-8').splitlines(True), caddyfile.splitlines(True),
                                                '/etc/caddy/Caddyfile (live)', 'rendered from private groups.json'))
            print(diff or 'The rendered Caddyfile matches the live one.')
            if live_routes != new_routes:
                print('Publishing would stop here: ' + refusal)
            print('Dry run: nothing was uploaded or changed.')
            return
        if live_routes != new_routes:
            parser.error(refusal)
        release = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        remote_path = f'/tmp/wow-homepage-{release}.tar.gz'
        upload = temporary / 'upload.tar.gz'
        with tarfile.open(upload, 'w:gz') as package:
            for name, path in files(site).items():
                package.add(path, arcname=name, recursive=False)
        settings = {'payload': remote_path, 'release': release, 'revision': revision,
                    'archive_sha256': hashlib.sha256(upload.read_bytes()).hexdigest(),
                    'caddy_sha256': hashlib.sha256(old_config).hexdigest(), 'caddyfile': caddyfile}
        # The rendered Caddyfile travels on the SSH stdin, never through the world-readable /tmp
        # upload. ascii() is a valid literal for any text and keeps the script ASCII.
        script = ((DEPLOY / 'install_homepage.py').read_text(encoding='utf-8')
                  + f'\nSETTINGS = {ascii(settings)}\nprint(json.dumps(install(**SETTINGS)))\n')
        try:
            subprocess.run(['scp', '-F', '/dev/null', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                            str(upload), f'{args.host}:{remote_path}'], check=True)
            subprocess.run([*ssh, 'python3 -'], input=script.encode('utf-8'), check=True)
        except BaseException:
            # The server deletes the upload itself; this covers a broken copy or connection.
            subprocess.run([*ssh, 'rm -f -- ' + shlex.quote(remote_path)], check=False)
            raise


if __name__ == '__main__':
    main()
