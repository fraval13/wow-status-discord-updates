"""Install one uploaded static homepage release on the server, as root.

deploy/publish_homepage.py sends this file's source over SSH, followed by one
install(...) call, and the server's own python3 runs it, so it uses only the
standard library and stays ASCII. Before changing anything it checks that the live
Caddyfile is the one the publisher inspected and that the upload is byte for byte
the archive the publisher checked (issue #19). It extracts the release, then writes
and validates the candidate Caddyfile outside the web root with mode 0600, because
it holds the group route keys. Only then does it switch the `current` symlink and
reload Caddy. A failure before the switch removes the partial release; a failure
after it restores the previous site and Caddyfile first and restarts Caddy if it
stopped. The uploaded archive and the candidate Caddyfile are always deleted.
"""
import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

BASE = Path('/srv/wow-status-homepage')  # Caddy serves BASE/current
CADDY = Path('/etc/caddy/Caddyfile')


def write_private(path, data):
    """Create path with mode 0600 before any byte is written; never replaces a file."""
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as handle:
        handle.write(data)


def point(link, target):
    """Atomically make the symlink link point at target."""
    swap = link.with_name(f'.{link.name}-{os.getpid()}')
    swap.unlink(missing_ok=True)
    swap.symlink_to(target)
    os.replace(swap, link)


def public_tree(path):
    """Make the extracted release readable by Caddy whatever umask built or extracted it."""
    for parent, dirs, files in os.walk(path):
        os.chmod(parent, 0o755)
        for name in files:
            os.chmod(os.path.join(parent, name), 0o644)


def switch(data, release, revision, old_config, caddyfile, base, caddy):
    current = base / 'current'
    previous = os.readlink(current) if current.is_symlink() else None
    target = base / 'releases' / release
    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir()  # an existing release is never touched, not even to clean it up
    candidate = base / f'.Caddyfile-{release}'  # beside, not inside, the served directory
    backup = base / f'Caddyfile.before-{release}'
    backed_up = switched = False
    try:
        # The checked bytes themselves, not the upload path, which could change after the check.
        with tarfile.open(fileobj=io.BytesIO(data)) as package:
            package.extractall(target, filter='data')
        public_tree(target)
        manifest = json.loads((target / 'downloads/release.json').read_text(encoding='utf-8'))
        if manifest.get('addon_revision') != revision:
            raise RuntimeError('The uploaded release is not the checked build; nothing was changed')
        write_private(candidate, caddyfile.encode('utf-8'))
        subprocess.run(['caddy', 'validate', '--config', str(candidate), '--adapter', 'caddyfile'], check=True)
        write_private(backup, old_config)
        backed_up = True
        point(current, target)
        switched = True
        shutil.copyfile(candidate, caddy)
        caddy.chmod(0o644)
        subprocess.run(['systemctl', 'reload', 'caddy'], check=True)
        subprocess.run(['systemctl', 'is-active', '--quiet', 'caddy'], check=True)
    except BaseException:
        if switched:
            caddy.write_bytes(old_config)
            if previous:
                point(current, previous)
            else:
                current.unlink(missing_ok=True)
            # A plain reload can't start Caddy again if the new configuration stopped it.
            subprocess.run(['systemctl', 'reload-or-restart', 'caddy'], check=False)
        # Reached only once current no longer points at the new release and the live
        # Caddyfile is the old one again, so neither the release nor the backup is needed.
        shutil.rmtree(target, ignore_errors=True)
        if backed_up:
            backup.unlink(missing_ok=True)
        raise
    finally:
        candidate.unlink(missing_ok=True)
    return {'url': 'https://wow.frankvalde.com/', 'release': str(target), 'previous': previous,
            'addon_revision': revision}


def install(payload, release, revision, archive_sha256, caddy_sha256, caddyfile, base=BASE, caddy=CADDY):
    archive = Path(payload)
    try:
        old_config = caddy.read_bytes()
        if hashlib.sha256(old_config).hexdigest() != caddy_sha256:
            raise RuntimeError('Caddy changed since inspection; no configuration was changed')
        data = archive.read_bytes()
        if hashlib.sha256(data).hexdigest() != archive_sha256:
            raise RuntimeError('The upload is incomplete or changed; nothing was changed')
        return switch(data, release, revision, old_config, caddyfile, base, caddy)
    finally:
        archive.unlink(missing_ok=True)
