"""Publish the built static homepage through the existing authorized SSH account.

Renders the Caddyfile's group routes from the private groups.json (by default the
server's own copy; group names never come from Git). Keeps the previous static
release and Caddy config for rollback. Does not restart either application or read
its Discord secrets. --dry-run prints the Caddy change and stops; its output holds
the group route keys, so do not paste it anywhere public.
"""
import argparse
import difflib
import hashlib
import json
import subprocess
import tarfile
import tempfile
from pathlib import Path

import render_caddyfile

PRIVATE_GROUPS = render_caddyfile.GROUPS.as_posix()

REMOTE = r'''
import hashlib, json, os, pathlib, shutil, subprocess, tarfile, time
archive = pathlib.Path(PAYLOAD)
base = pathlib.Path('/srv/wow-status-homepage')
release = base / 'releases' / RELEASE
current = base / 'current'
config = pathlib.Path('/etc/caddy/Caddyfile')
old_config = config.read_bytes()
if hashlib.sha256(old_config).hexdigest() != EXPECTED:
    raise RuntimeError('Caddy changed since inspection; no configuration was changed')
previous = os.readlink(current) if current.is_symlink() else None
release.mkdir(parents=True, exist_ok=False)
# Outside the served release directory and private: it holds the group route keys.
candidate = base / ('.Caddyfile-' + RELEASE)
try:
    with tarfile.open(archive) as package:
        package.extractall(release, filter='data')
    with os.fdopen(os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8') as handle:
        handle.write(CADDYFILE)
    subprocess.run(['caddy','validate','--config',str(candidate),'--adapter','caddyfile'],check=True)
    backup = base / ('Caddyfile.before-' + RELEASE)
    backup.write_bytes(old_config)
    backup.chmod(0o600)
    swap = base / ('.current-' + RELEASE)
    swap.symlink_to(release)
    os.replace(swap,current)
    try:
        shutil.copyfile(candidate,config)
        config.chmod(0o644)
        subprocess.run(['systemctl','reload','caddy'],check=True)
        subprocess.run(['systemctl','is-active','--quiet','caddy'],check=True)
    except BaseException:
        config.write_bytes(old_config)
        if previous:
            swap.symlink_to(previous)
            os.replace(swap,current)
        else:
            current.unlink(missing_ok=True)
        subprocess.run(['systemctl','reload','caddy'],check=False)
        raise
    candidate.unlink()
    manifest=json.loads((release/'downloads/release.json').read_text(encoding='utf-8'))
    print(json.dumps({'url':'https://wow.frankvalde.com/','release':str(release),
                      'previous':previous,'addon_revision':manifest['addon_revision']}))
finally:
    archive.unlink(missing_ok=True)
    candidate.unlink(missing_ok=True)
'''


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
    directory = args.directory.resolve()
    if not args.dry_run and (not (directory / 'index.html').is_file()
                             or not (directory / 'downloads/release.json').is_file()):
        parser.error('Build the homepage before publishing')
    ssh = ['ssh', '-F', '/dev/null', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', args.host]
    old_config = subprocess.check_output([*ssh, 'cat /etc/caddy/Caddyfile'])
    # Refuse an unrelated host/config rather than replacing another site's setup.
    if b'wow.frankvalde.com {' not in old_config or b'handle_path /groups/' not in old_config:
        parser.error('The target does not have the expected existing WoW gateway')
    caddyfile = render_caddyfile.render(private_groups(args.groups_config, ssh))
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
    import datetime
    release = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    remote_path = f'/tmp/wow-homepage-{release}.tar.gz'
    with tempfile.NamedTemporaryFile(suffix='.tar.gz') as temporary:
        with tarfile.open(fileobj=temporary, mode='w:gz') as package:
            for file in sorted(directory.rglob('*')):
                if file.is_file():
                    package.add(file, arcname=file.relative_to(directory), recursive=False)
        temporary.flush()
        subprocess.run(['scp','-F','/dev/null','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
                        temporary.name,f'{args.host}:{remote_path}'],check=True)
    # The rendered Caddyfile travels on the SSH stdin, never through the world-readable /tmp upload.
    variables = '\n'.join([f'PAYLOAD={json.dumps(remote_path)}', f'RELEASE={json.dumps(release)}',
                            f'EXPECTED={json.dumps(hashlib.sha256(old_config).hexdigest())}',
                            f'CADDYFILE={caddyfile!r}'])  # repr: a valid literal for any text
    subprocess.run([*ssh, 'python3 -'],input=(variables + '\n' + REMOTE).encode(),check=True)


if __name__ == '__main__':
    main()
