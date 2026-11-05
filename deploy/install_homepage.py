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

It holds the pipeline receiver's deployment lock throughout, so it never switches
`current` while a pipeline deployment does (issue #27), and it refuses if `current`
no longer points where the publisher saw it, rather than replacing a site that a
pipeline deployment switched to since with this build. After a successful switch
only the newest releases and Caddyfile backups are kept.
"""
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

BASE = Path('/srv/wow-status-homepage')  # Caddy serves BASE/current
CADDY = Path('/etc/caddy/Caddyfile')
# The lock deploy/install_release.py holds while it deploys; it switches BASE/current too.
LOCK = Path('/opt/wow-character-status/deployment.lock')
LOCK_WAIT = 600  # seconds; a pipeline deployment builds a venv while it holds the lock
KEEP_RELEASES = 5  # newest releases kept, the new one among them; the one live before is kept too
RELEASE = re.compile(r'[0-9]{8}T[0-9]{12}Z')  # the publisher's UTC timestamp


@contextlib.contextmanager
def deployment_lock(path, wait):
    """Hold the receiver's lock, waiting up to `wait` seconds; skipped where no receiver exists."""
    if not path.parent.is_dir():
        yield
        return
    import fcntl  # Linux only; the publisher imports this module's helpers on any platform
    with open(path, 'ab') as handle:
        deadline = time.monotonic() + wait
        waiting = False
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('A pipeline deployment is still running; nothing was changed') from None
                if not waiting:
                    print('Waiting for a pipeline deployment to finish.', file=sys.stderr)
                    waiting = True
                time.sleep(1)
        yield


def prune(base, keep, protect):
    """Delete all but the newest `keep` releases (never one in protect) and Caddyfile backups."""
    releases = sorted((path for path in (base / 'releases').iterdir()
                       if RELEASE.fullmatch(path.name) and path.is_dir() and not path.is_symlink()), reverse=True)
    removed = 0
    for path in releases[keep:]:
        if path.resolve() not in protect:
            shutil.rmtree(path)
            removed += 1
    for path in sorted(base.glob('Caddyfile.before-*'), reverse=True)[keep:]:
        path.unlink()
    return removed


def write_private(path, data):
    """Create path with mode 0600 before any byte is written; never replaces a file."""
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as handle:
        handle.write(data)


def point(link, target):
    """Atomically make the symlink link point at target (as deploy/install_release.py does)."""
    swap = link.with_name(f'.{link.name}-{os.getpid()}')
    swap.unlink(missing_ok=True)
    swap.symlink_to(target)
    try:
        os.replace(swap, link)
    except BaseException:
        swap.unlink(missing_ok=True)
        raise


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
    result = {'url': 'https://wow.frankvalde.com/', 'release': str(target), 'previous': previous,
              'addon_revision': revision}
    try:  # the new site is live; tidying up must not undo that
        protect = {target.resolve(), *([(base / previous).resolve()] if previous else [])}
        result['pruned_releases'] = prune(base, KEEP_RELEASES, protect)
    except OSError as error:
        result['prune_error'] = type(error).__name__
    return result


def site_link(base):
    """Where base/current points, or '' when there is no site yet; the publisher reads it too."""
    current = base / 'current'
    return os.readlink(current) if current.is_symlink() else ''


def install(payload, release, revision, archive_sha256, caddy_sha256, caddyfile, site=None, base=BASE,
            caddy=CADDY, lock=LOCK):
    """Install the upload; `site` is where `current` pointed when the publisher inspected the host."""
    archive = Path(payload)
    seen = site_link(base) if site is None else site
    # Folders this run creates, such as a first releases/, must be readable by Caddy.
    umask = os.umask(0o022)
    try:
        with deployment_lock(lock, LOCK_WAIT):
            if site_link(base) != seen:
                raise RuntimeError('A pipeline deployment switched the site since this publish inspected it; '
                                   'nothing was changed. Rebuild from the new main and publish again if still needed.')
            old_config = caddy.read_bytes()
            if hashlib.sha256(old_config).hexdigest() != caddy_sha256:
                raise RuntimeError('Caddy changed since inspection; no configuration was changed')
            data = archive.read_bytes()
            if hashlib.sha256(data).hexdigest() != archive_sha256:
                raise RuntimeError('The upload is incomplete or changed; nothing was changed')
            return switch(data, release, revision, old_config, caddyfile, base, caddy)
    finally:
        archive.unlink(missing_ok=True)
        os.umask(umask)
