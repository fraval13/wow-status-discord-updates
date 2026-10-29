"""Publish the built static homepage through the existing authorized SSH account.

Preserves both companion routes. Keeps the previous static release and Caddy
config for rollback. Does not restart either application or read its secrets.
"""
import argparse
import hashlib
import io
import json
import subprocess
import tarfile
import tempfile
from pathlib import Path

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
try:
    with tarfile.open(archive) as package:
        package.extractall(release, filter='data')
    candidate = release / '.Caddyfile'
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
    manifest=json.loads((release/'downloads/release.json').read_text())
    print(json.dumps({'url':'https://wow.frankvalde.com/','release':str(release),
                      'previous':previous,'addon_revision':manifest['addon_revision']}))
finally:
    archive.unlink(missing_ok=True)
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--directory', type=Path, default=Path('dist/homepage'))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    directory = args.directory.resolve()
    if not (directory / 'index.html').is_file() or not (directory / 'downloads/release.json').is_file():
        parser.error('Build the homepage before publishing')
    ssh = ['ssh', '-F', '/dev/null', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', args.host]
    old_config = subprocess.check_output([*ssh, 'cat /etc/caddy/Caddyfile'])
    # Refuse an unrelated host/config rather than replacing another site's setup.
    if b'wow.frankvalde.com {' not in old_config or b'127.0.0.1:18081' not in old_config or b'127.0.0.1:18082' not in old_config:
        parser.error('The target does not have the expected existing WoW gateway')
    import datetime
    release = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    remote_path = f'/tmp/wow-homepage-{release}.tar.gz'
    with tempfile.NamedTemporaryFile(suffix='.tar.gz') as temporary:
        with tarfile.open(fileobj=temporary, mode='w:gz') as package:
            for file in sorted(directory.rglob('*')):
                if file.is_file():
                    package.add(file, arcname=file.relative_to(directory), recursive=False)
            data = (root / 'deploy/Caddyfile.production').read_bytes()
            info = tarfile.TarInfo('.Caddyfile')
            info.size, info.mode = len(data), 0o644
            package.addfile(info, io.BytesIO(data))
        temporary.flush()
        subprocess.run(['scp','-F','/dev/null','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
                        temporary.name,f'{args.host}:{remote_path}'],check=True)
    variables = '\n'.join([f'PAYLOAD={json.dumps(remote_path)}', f'RELEASE={json.dumps(release)}',
                            f'EXPECTED={json.dumps(hashlib.sha256(old_config).hexdigest())}'])
    subprocess.run([*ssh, 'python3 -'],input=(variables + '\n' + REMOTE).encode(),check=True)


if __name__ == '__main__':
    main()
