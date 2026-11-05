#!/usr/bin/python3
"""Root-owned deployment receiver. Its authority is limited to this project's fixed paths.

Group names are shared secrets (docs/GROUPS.md), so they are not in Git. The services
this receiver may restart come from root-maintained /etc/wow-character-status/groups.json:

    {"<instance>": {"name": "<exact group name>", "port": 18081}, ...}

The instance is a short local label for the systemd unit, account and data directory.
"""
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

BASE = Path('/opt/wow-character-status')
CONFIG = Path('/etc/wow-character-status')
HOMEPAGE = Path('/srv/wow-status-homepage')
LIMIT = 64 * 1024 * 1024
GROUPS_FILE = CONFIG / 'groups.json'
# Pins every package the server installs by version and SHA-256 (scripts/lock_requirements.py).
LOCKFILE = 'requirements.txt'
# A release folder is <revision>-<activation time in ns>.
RELEASE = re.compile(r'([0-9a-f]{40})-([0-9]+)')
# Newest releases kept, the live one among them; the rollback target and the homepage's
# release are kept even when older.
KEEP_RELEASES = 5
# The last activation and what preceded it, so a failed public check can roll it back.
STATE = 'last-deployment.json'
# Sent by the deploy job instead of a release archive when the public site fails verification.
ROLLBACK_REQUEST = re.compile(rb'wow-status-rollback ([0-9a-f]{40})\n?')
# How long a deployment waits for a manual homepage publish (deploy/install_homepage.py).
LOCK_WAIT = 600
# Becomes systemd instance wow-character-status@<instance>, account wow-character-<instance>
# (at most 32 characters) and /var/lib/wow-character-<instance>.
INSTANCE = re.compile(r'[a-z][a-z0-9-]{0,17}')
# Labels whose account already exists for the pipeline itself.
RESERVED = {'build', 'deploy'}
# A subset of what the addon accepts: no quotes, backslashes or dollar signs, so the name
# is written to a systemd environment file unchanged; no leading '-', so the service's
# command line can't read it as an option.
GROUP_NAME = re.compile(r'[A-Za-z0-9](?:[A-Za-z0-9 ._-]{0,78}[A-Za-z0-9._-])?')
DISCORD = {'bot_token': re.compile(r'[A-Za-z0-9._=-]+'), 'guild_id': re.compile(r'[0-9]{1,30}'),
           'channel_id': re.compile(r'[0-9]{1,30}')}


class Refused(Exception):
    """A refusal whose fixed message is safe for the public Actions log (no names or secrets)."""


def discord_value(key, value):
    """Raise unless an empty or well-formed Discord setting; never includes the value."""
    if key not in DISCORD or not isinstance(value, str):
        raise ValueError('Invalid Discord setting')
    if value and not DISCORD[key].fullmatch(value):
        raise ValueError(f'Invalid Discord {key} format')
    return value


def write_private(path, text):
    path.write_text(text, encoding='utf-8')
    path.chmod(0o600)


def validate_groups(raw):
    """Instance -> {'name', 'port'}; rejects anything unsafe for paths, units or env files."""
    if not isinstance(raw, dict) or not 1 <= len(raw) <= 8:
        raise ValueError('Group configuration needs 1 to 8 group instances')
    groups, names, ports = {}, set(), set()
    for instance, entry in raw.items():
        if not isinstance(instance, str) or not INSTANCE.fullmatch(instance) or instance in RESERVED:
            raise ValueError('Invalid group instance label')
        if not isinstance(entry, dict) or set(entry) != {'name', 'port'}:
            raise ValueError('Each group instance needs exactly a name and a port')
        name, port = entry['name'], entry['port']
        if not isinstance(name, str) or not GROUP_NAME.fullmatch(name):
            raise ValueError('Invalid group name')
        if type(port) is not int or not 1024 <= port <= 65535:
            raise ValueError('Invalid group port')
        if name.casefold() in names or port in ports:
            raise ValueError('Group names and ports must be unique')
        names.add(name.casefold())
        ports.add(port)
        groups[instance] = {'name': name, 'port': port}
    return groups


def legacy_groups(config):
    """Groups from the <instance>.env files an earlier receiver wrote before groups.json.

    A file counts only if its database path names its own instance, so a copy such as
    a backup under another name is skipped.
    """
    groups = {}
    for path in sorted(config.glob('*.env')):
        values = dict(re.findall(r'^([A-Z_]+)="([^"\n]*)"$', path.read_text(encoding='utf-8'), re.MULTILINE))
        if values.get('WOW_STATUS_DATABASE') != f'/var/lib/wow-character-{path.stem}/service.sqlite3':
            continue
        port = values.get('WOW_STATUS_PORT', '')
        groups[path.stem] = {'name': values.get('DISCORD_GROUP_NAME'),
                             'port': int(port) if port.isdigit() else None}
    return groups


def load_groups(config=CONFIG):
    """The private group list, or (once) the one the previous receiver's env files imply.

    Returns (groups, migrated). With groups.json absent, every *.env file counts, so
    remove a retired instance's env file along with its groups.json entry.
    """
    path = config / GROUPS_FILE.name
    if path.exists():
        return validate_groups(json.loads(path.read_text(encoding='utf-8'))), False
    return validate_groups(legacy_groups(config)), True


def merge_discord(groups, merged, incoming):
    """Apply nonempty incoming Discord settings for known instances; keep the rest.

    Returns how many incoming instances are not configured on this server.
    """
    if not isinstance(incoming, dict) or not isinstance(merged, dict):
        raise ValueError('Invalid Discord setting')
    for instance in groups:
        values = merged.setdefault(instance, {})
        supplied = incoming.get(instance, {})
        if not isinstance(supplied, dict) or not isinstance(values, dict):
            raise ValueError('Invalid Discord setting')
        for key in DISCORD:
            if discord_value(key, supplied.get(key, '')):
                values[key] = supplied[key]
    return len(set(incoming) - set(groups))


def service_environment(instance, group, values, revision):
    return environment({
        'DISCORD_GROUP_NAME': group['name'], 'WOW_STATUS_PORT': str(group['port']),
        'WOW_STATUS_REVISION': revision,
        'WOW_STATUS_DATABASE': f'/var/lib/wow-character-{instance}/service.sqlite3',
        'DISCORD_BOT_TOKEN': values.get('bot_token', ''),
        'DISCORD_GUILD_ID': values.get('guild_id', ''),
        'DISCORD_CHANNEL_ID': values.get('channel_id', '')})


def run(*args):
    subprocess.run(args, check=True, stdin=subprocess.DEVNULL)


def systemctl(action, instance, check=True):
    # systemctl output names the unit, and this receiver's output reaches the public
    # Actions log, so it is discarded; read journalctl on the server instead.
    subprocess.run(['systemctl', action, f'wow-character-status@{instance}.service'], check=check,
                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def environment(values):
    for key, value in values.items():
        if not re.fullmatch('[A-Z_]+', key) or any(c in str(value) for c in '\r\n\x00'):
            raise ValueError('Invalid service environment')
    return ''.join(f'{key}="{value}"\n' for key, value in values.items())


def root_readonly_tree(path):
    for parent, dirs, files in os.walk(path, followlinks=False):
        for name in dirs + files:
            item = Path(parent) / name
            mode = item.lstat().st_mode
            os.chown(item, 0, 0, follow_symlinks=False)
            if not item.is_symlink():
                item.chmod(0o755 if item.is_dir() or mode & 0o111 else 0o644)
    path.chmod(0o755)
    os.chown(path, 0, 0)


def healthy(port, revision):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=3) as response:
            data = json.load(response)
            return (response.status == 200 and data.get('status') == 'ok'
                    and data.get('service') == 'wow-character-status'
                    and data.get('revision') == revision)
    except Exception:
        return False


def prepare_homepage(stage, revision):
    """Check the public payload before making it part of a sealed release."""
    public = stage / '.deploy/HOMEPAGE'
    manifest = json.loads((public / 'downloads/release.json').read_text(encoding='utf-8'))
    if manifest.get('addon_revision') != revision:
        raise ValueError('Homepage revision does not match application release')
    html = (public / 'index.html').read_text(encoding='utf-8')
    for edition in ('vanilla', 'forever', 'tbc', 'retail'):
        item = manifest['editions'][edition]
        filename = f'WoWStatus-{edition}.zip'
        if item['file'] != filename:
            raise ValueError('Unexpected public download path')
        archive = public / 'downloads' / filename
        if (archive.stat().st_size != item['bytes'] or
                hashlib.sha256(archive.read_bytes()).hexdigest() != item['sha256']):
            raise ValueError('Public addon checksum mismatch')
        toc_path = 'WoWStatus/WoWStatus.toc'
        expected = (stage / 'addon' / edition / toc_path).read_bytes()
        with zipfile.ZipFile(archive) as package:
            if (sum(info.file_size for info in package.infolist()) > LIMIT or
                    any(not name.startswith('WoWStatus/') or '..' in PurePosixPath(name).parts
                        for name in package.namelist()) or package.testzip() is not None or
                    package.read(toc_path) != expected):
                raise ValueError('Invalid public addon ZIP')
        version = re.search(r'^## Version: ([\w.\-]+)$', expected.decode(), re.MULTILINE).group(1)
        if item['version'] != version or f'VERSION {version}' not in html:
            raise ValueError('Homepage version does not match addon')
    target = stage / 'public-homepage'
    public.rename(target)
    return target


def point(link, target):
    """Atomically make the symlink link point at target (as deploy/install_homepage.py does)."""
    swap = link.with_name(f'.{link.name}-{os.getpid()}')
    swap.unlink(missing_ok=True)
    swap.symlink_to(target)
    try:
        swap.replace(link)
    except BaseException:
        swap.unlink(missing_ok=True)
        raise


def switch_homepage(target):
    HOMEPAGE.mkdir(mode=0o755, parents=True, exist_ok=True)
    HOMEPAGE.chmod(0o755)  # The receiver's private umask must not hide public files.
    point(HOMEPAGE / 'current', target)


def live(link):
    """The resolved target of the symlink link, or None when it is missing or dangling."""
    return link.resolve() if link.exists() else None


def wait_for_lock(path, wait):
    """Hold an exclusive lock on path, waiting up to `wait` seconds; return the open file.

    deploy/install_homepage.py takes the same lock, so a manual homepage publish and a
    pipeline deployment never switch the homepage's `current` symlink at the same time.
    """
    import fcntl
    handle = path.open('ab')
    deadline = time.monotonic() + wait
    waiting = False
    while True:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic() >= deadline:
                handle.close()
                raise Refused('Another deployment or homepage publish is still running; nothing was changed') from None
            if not waiting:
                print('Waiting for another deployment or homepage publish to finish.', file=sys.stderr)
                waiting = True
            time.sleep(1)
    if waiting:
        # The deploy job may have been cancelled meanwhile, and a newer one may be waiting
        # too. sshd closes a gone client's pipe, so this write fails before anything changes.
        try:
            print('Got the lock; continuing.', file=sys.stderr, flush=True)
        except BrokenPipeError:
            handle.close()
            raise Refused('The deploy job disconnected while this waited; nothing was changed') from None
    return handle


def snapshot_config(groups):
    """The private files a deployment rewrites, to restore after a failure (None: absent)."""
    names = ['config.json', GROUPS_FILE.name, *(f'{instance}.env' for instance in groups)]
    return {name: (CONFIG / name).read_bytes() if (CONFIG / name).exists() else None for name in names}


def restore_config(snapshot):
    for name, value in snapshot.items():
        path = CONFIG / name
        if value is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(value)
            path.chmod(0o600)


def write_config(groups, merged, revision):
    for instance, group in groups.items():
        write_private(CONFIG / f'{instance}.env', service_environment(instance, group, merged.get(instance, {}), revision))
    write_private(CONFIG / 'config.json', json.dumps(merged))


def start(groups, revision, check=True):
    """Restart every group service; True once all report revision within about 20 seconds."""
    for instance in groups:
        systemctl('restart', instance, check=check)
    for _ in range(20):
        if all(healthy(group['port'], revision) for group in groups.values()):
            return True
        time.sleep(1)
    return False


def install_dependencies(candidate):
    """Build the release's venv as the build user from hash-pinned packages only (issue #27).

    requirements.txt pins every runtime package and setuptools by version and SHA-256,
    and only wheels are accepted, so no unpinned build tool runs. The project itself is
    then built from the release with no index and no build isolation: nothing is fetched.
    """
    build = ('runuser', '-u', 'wow-character-build', '--')
    run(*build, '/usr/bin/python3', '-m', 'venv', str(candidate / '.venv'))
    pip = (*build, str(candidate / '.venv/bin/python'), '-m', 'pip', 'install', '--disable-pip-version-check',
           '--no-input')
    run(*pip, '--require-hashes', '--only-binary', ':all:', '-r', str(candidate / LOCKFILE))
    run(*pip, '--no-deps', '--no-build-isolation', '--no-index', str(candidate))


def prune(releases, keep, protect):
    """Delete all but the newest `keep` releases and leftover stages; return how many went.

    A release that a path in `protect` lies in (the running one, the rollback target and
    whatever the homepage serves) is always kept. So are entries named any other way.
    """
    found = sorted(((int(match.group(2)), path) for path in releases.iterdir()
                    if (match := RELEASE.fullmatch(path.name)) and path.is_dir() and not path.is_symlink()),
                   reverse=True)
    removed = 0
    for _, path in found[keep:]:
        if not any(kept.is_relative_to(path) for kept in protect):
            shutil.rmtree(path)
            removed += 1
    for path in releases.glob('.incoming-*'):  # left behind by a receiver that was killed
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
    return removed


def read_state():
    """The last activation's record, or None when there is none or it can't be read."""
    try:
        state = json.loads((BASE / STATE).read_text(encoding='utf-8'))
    except (FileNotFoundError, ValueError):  # ValueError: cut short, say; the next activation rewrites it
        return None
    return state if isinstance(state, dict) else None


def record(revision, candidate, previous, previous_homepage, added):
    """After an activation: remember what a rollback returns to, then prune old releases.

    A redeploy of the live revision (say "Re-run all jobs" after a refused rollback)
    keeps the earlier rollback target, so a rollback never "returns" to the same code.
    `added` names the instances this deploy started for the first time. Neither step
    may fail the deployment, which is live and healthy by now, and neither depends on
    the other.
    """
    releases = (BASE / 'releases').resolve()
    try:
        if previous is not None and previous.name.startswith(revision):
            state = read_state()
            if state is not None and state.get('revision') == revision:
                # The homepage that deploy replaced, unless a manual publish has replaced
                # that deploy's own homepage since: then the published one was live before.
                if previous_homepage == previous / 'public-homepage':
                    previous_homepage = Path(state['previous_homepage']) if state.get('previous_homepage') else None
                previous = releases / state['previous'] if state.get('previous') else None
                added = sorted(set(added) | set(state.get('added', [])))
            else:  # nothing is recorded to return to but the same code
                previous = previous_homepage = None
        swap = BASE / f'.{STATE}-{os.getpid()}'
        try:
            write_private(swap, json.dumps({
                'revision': revision, 'release': candidate.name,
                'previous': previous.name if previous else None,
                'previous_homepage': str(previous_homepage) if previous_homepage else None,
                'added': sorted(added)}))
            swap.replace(BASE / STATE)  # whole or not at all: a full disk never leaves half a record
        finally:
            swap.unlink(missing_ok=True)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'Could not record the rollback target ({type(error).__name__}).', file=sys.stderr)
    try:
        protect = {candidate, *filter(None, [previous, previous_homepage, live(HOMEPAGE / 'current')])}
        removed = prune(releases, KEEP_RELEASES, protect)
        if removed:
            print(f'Removed {removed} old release(s).')
    except OSError as error:
        print(f'Could not prune old releases ({type(error).__name__}).', file=sys.stderr)


def deploy(raw, groups, migrated):
    import pwd
    # Resolved, like the symlink targets it is compared with before anything is deleted.
    releases = (BASE / 'releases').resolve()
    stage = Path(tempfile.mkdtemp(prefix='.incoming-', dir=releases))
    current = BASE / 'current'
    old_target = live(current)
    old_homepage = live(HOMEPAGE / 'current')
    old_config = snapshot_config(groups)
    config_written = False
    activated = False
    candidate = None
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as archive:
            seen, total = set(), 0
            for member in archive:
                name = PurePosixPath(member.name)
                if (name.is_absolute() or '..' in name.parts or not name.parts
                        or '.git' in name.parts or str(name) in seen
                        or not (member.isfile() or member.isdir())):
                    raise ValueError('Unsafe archive entry')
                seen.add(str(name))
                target = stage.joinpath(*name.parts)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                total += member.size
                if total > LIMIT:
                    raise ValueError('Expanded archive is too large')
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, target.open('xb') as output:
                    shutil.copyfileobj(source, output)
        revision = (stage / '.deploy/REVISION').read_text(encoding='utf-8').strip()
        if not re.fullmatch('[a-f0-9]{40}', revision):
            raise ValueError('Invalid revision')
        incoming = json.loads((stage / '.deploy/CONFIG.json').read_text(encoding='utf-8'))
        merged = json.loads(old_config['config.json']) if old_config['config.json'] else {}
        unknown = merge_discord(groups, merged, incoming)
        if unknown:
            # Count only: instance labels may be old group names, and this log is public.
            print(f'Ignored Discord settings for {unknown} instance(s) not in groups.json.', file=sys.stderr)
        prepare_homepage(stage, revision)
        shutil.rmtree(stage / '.deploy')  # credentials never become part of the installed release
        builder = pwd.getpwnam('wow-character-build')
        for parent, dirs, files in os.walk(stage):
            for name in dirs + files:
                os.chown(Path(parent) / name, builder.pw_uid, builder.pw_gid)
        os.chown(stage, builder.pw_uid, builder.pw_gid)
        stage.chmod(0o755)
        candidate = releases / (revision + '-' + str(time.time_ns()))
        stage.rename(candidate)
        # Build tools and project code run as a separate unprivileged account, never as root.
        install_dependencies(candidate)
        root_readonly_tree(candidate)
        config_written = True
        write_config(groups, merged, revision)
        if migrated:
            write_private(CONFIG / GROUPS_FILE.name, json.dumps(groups, indent=2) + '\n')
        point(current, candidate)
        activated = True
        if not start(groups, revision):
            raise RuntimeError('New release did not become healthy')
        for instance in groups:
            systemctl('enable', instance)
        switch_homepage(candidate / 'public-homepage')  # last: nothing after it can fail the deploy
    except Exception:
        if config_written and old_target:
            # Also before activation: the old release must keep running with its own config.
            restore_config(old_config)
        if activated and old_target:
            point(current, old_target)
            for instance in groups:
                if old_config[f'{instance}.env'] is not None:
                    systemctl('restart', instance, check=False)
                else:  # added by this deploy, and its env file is gone again
                    systemctl('stop', instance, check=False)
                    systemctl('disable', instance, check=False)
            print('Deployment failed; restored the preceding project release.', file=sys.stderr)
        elif activated:
            for instance in groups:
                systemctl('stop', instance, check=False)
            print('Initial activation failed; project services stopped.', file=sys.stderr)
        if candidate is not None and live(current) != candidate:
            shutil.rmtree(candidate, ignore_errors=True)  # a failed candidate never lingers with its venv
        raise
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    added = [instance for instance in groups if old_config[f'{instance}.env'] is None]
    record(revision, candidate, old_target, old_homepage, added)  # before any output that could fail
    # No instance labels or group names: this output reaches the public Actions log.
    print('Activated', revision, f'for {len(groups)} group services and the homepage;',
          'all local health endpoints passed.')


def roll_back(revision, groups):
    """Return production to the release before `revision`, while `revision` is still live.

    The deploy job asks for this when the public site fails verification after this
    receiver activated `revision` (issue #27). It refuses, changing nothing, unless the
    last activation recorded was `revision`, that release and its homepage are still
    live, and the release and homepage it replaced are still installed. A homepage that
    a manual publish replaced since explains the failed check by itself. Instances
    that deployment started for the first time are stopped, as a failed deploy does.
    """
    current, homepage = BASE / 'current', HOMEPAGE / 'current'
    releases = (BASE / 'releases').resolve()
    state = read_state()
    if state is None:
        raise Refused('No recorded deployment to roll back; nothing was changed')
    failed = releases / state['release']
    if state.get('revision') != revision or not RELEASE.fullmatch(failed.name) or live(current) != failed:
        raise Refused('The live release is not the one to roll back; nothing was changed')
    if live(homepage) != failed / 'public-homepage':
        raise Refused('A manual publish replaced the homepage since this deployment; nothing was changed')
    previous = releases / (state.get('previous') or '')
    match = RELEASE.fullmatch(previous.name)
    if not match or match.group(1) == revision or not (previous / '.venv/bin/python').is_file():
        raise Refused('No earlier release to roll back to; nothing was changed')
    earlier = [Path(state['previous_homepage'])] if state.get('previous_homepage') else []
    old_homepage = next((path for path in [*earlier, previous / 'public-homepage'] if path.is_dir()), None)
    if old_homepage is None:
        raise Refused('No earlier homepage to roll back to; nothing was changed')
    old_revision = match.group(1)
    added = [instance for instance in state.get('added', []) if instance in groups]
    kept = {instance: group for instance, group in groups.items() if instance not in added}
    merged = json.loads((CONFIG / 'config.json').read_text(encoding='utf-8'))
    snapshot = snapshot_config(groups)
    switched = False  # from here on a service may run the earlier release
    try:
        write_config(kept, merged, old_revision)
        point(current, previous)
        switched = True
        if not start(kept, old_revision):
            raise RuntimeError('The earlier release did not become healthy')
        switch_homepage(old_homepage)
    except Exception:
        # Each step on its own: one that fails again must not keep the services from restarting.
        restored = True
        for undo in (lambda: restore_config(snapshot), lambda: point(current, failed),
                     lambda: switch_homepage(failed / 'public-homepage')):
            try:
                undo()
            except Exception:
                restored = False
        # Before the switch no service was touched, so none needs a restart.
        healthy = start(groups, revision, check=False) if switched else True
        if not (restored and healthy):
            print('Rollback failed, and the release that failed verification could not be fully restored; '
                  'check the group services on the server (deploy/SERVER.md).', file=sys.stderr)
        elif switched:
            print('Rollback failed; the release that failed verification is live and healthy again.',
                  file=sys.stderr)
        else:
            print('Rollback failed before any service restarted; the release that failed verification '
                  'is still live.', file=sys.stderr)
        raise
    for instance in added:  # the earlier release never ran these
        systemctl('stop', instance, check=False)
        systemctl('disable', instance, check=False)
        (CONFIG / f'{instance}.env').unlink(missing_ok=True)
    try:
        (BASE / STATE).unlink()
    except OSError as error:  # production is rolled back; only a repeat request could act on it
        print(f'Could not remove {STATE} ({type(error).__name__}).', file=sys.stderr)
    print('Rolled back', revision, 'to', old_revision, f'for {len(kept)} group services and the homepage.')


def main():
    if os.geteuid() != 0:
        raise SystemExit('Receiver requires the dedicated sudo rule')
    os.umask(0o077)
    # The whole request first: the runner's upload must not stall while this waits for the lock.
    raw = sys.stdin.buffer.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError('Release archive is too large')
    with wait_for_lock(BASE / 'deployment.lock', LOCK_WAIT):
        groups, migrated = load_groups(CONFIG)
        if migrated:
            print(f'No groups.json yet: using {len(groups)} existing service env files.', file=sys.stderr)
        request = ROLLBACK_REQUEST.fullmatch(raw)
        if request:
            roll_back(request.group(1).decode('ascii'), groups)
        else:
            deploy(raw, groups, migrated)


def entry():
    try:
        main()
    except Refused as exc:
        raise SystemExit(f'Deployment refused: {exc}') from None
    except Exception as exc:
        # Never print config contents, credentials or request bodies.
        raise SystemExit(f'Deployment failed ({type(exc).__name__}).') from None


if __name__ == '__main__':
    entry()
