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


def switch_homepage(target):
    HOMEPAGE.mkdir(mode=0o755, parents=True, exist_ok=True)
    HOMEPAGE.chmod(0o755)  # The receiver's private umask must not hide public files.
    swap = HOMEPAGE / '.next'
    swap.unlink(missing_ok=True)
    swap.symlink_to(target)
    swap.replace(HOMEPAGE / 'current')


def main():
    # Linux-only modules, imported here so tests can load the helpers above anywhere.
    import fcntl
    import pwd
    if os.geteuid() != 0:
        raise SystemExit('Receiver requires the dedicated sudo rule')
    os.umask(0o077)
    deployment_lock = (BASE / 'deployment.lock').open('ab')
    fcntl.flock(deployment_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    groups, migrated = load_groups()
    if migrated:
        print(f'No groups.json yet: using {len(groups)} existing service env files.', file=sys.stderr)
    raw = sys.stdin.buffer.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError('Release archive is too large')
    releases = BASE / 'releases'
    stage = Path(tempfile.mkdtemp(prefix='.incoming-', dir=releases))
    old_target = (BASE / 'current').resolve() if (BASE / 'current').exists() else None
    old_homepage = (HOMEPAGE / 'current').resolve() if (HOMEPAGE / 'current').exists() else None
    old_config = {name: (CONFIG / name).read_bytes() if (CONFIG / name).exists() else None
                  for name in ['config.json', 'groups.json', *(f'{instance}.env' for instance in groups)]}
    config_written = False
    activated = False
    homepage_activated = False
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
        run('runuser', '-u', 'wow-character-build', '--', '/usr/bin/python3', '-m', 'venv', str(candidate / '.venv'))
        run('runuser', '-u', 'wow-character-build', '--', str(candidate / '.venv/bin/python'),
            '-m', 'pip', 'install', '--disable-pip-version-check', str(candidate))
        root_readonly_tree(candidate)
        config_written = True
        for instance, group in groups.items():
            write_private(CONFIG / f'{instance}.env', service_environment(instance, group, merged[instance], revision))
        write_private(CONFIG / 'config.json', json.dumps(merged))
        if migrated:
            write_private(GROUPS_FILE, json.dumps(groups, indent=2) + '\n')
        swap = BASE / 'next'
        swap.unlink(missing_ok=True)
        swap.symlink_to(candidate)
        swap.replace(BASE / 'current')
        activated = True
        for instance in groups:
            systemctl('restart', instance)
        for _ in range(20):
            if all(healthy(group['port'], revision) for group in groups.values()):
                for instance in groups:
                    systemctl('enable', instance)
                switch_homepage(candidate / 'public-homepage')
                homepage_activated = True
                # No instance labels or group names: this output reaches the public Actions log.
                print('Activated', revision, f'for {len(groups)} group services and the homepage;',
                      'all local health endpoints passed.')
                return
            time.sleep(1)
        raise RuntimeError('New release did not become healthy')
    except Exception:
        if homepage_activated:
            if old_homepage:
                switch_homepage(old_homepage)
            else:
                (HOMEPAGE / 'current').unlink(missing_ok=True)
        if config_written and old_target:
            # Also before activation: the old release must keep running with its own config.
            for name, value in old_config.items():
                path = CONFIG / name
                if value is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(value)
                    path.chmod(0o600)
        if activated and old_target:
            rollback = BASE / 'rollback'
            rollback.unlink(missing_ok=True)
            rollback.symlink_to(old_target)
            rollback.replace(BASE / 'current')
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
        raise
    finally:
        if stage.exists():
            shutil.rmtree(stage)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Never print config contents, credentials or request bodies.
        raise SystemExit(f'Deployment failed ({type(exc).__name__}).') from None
