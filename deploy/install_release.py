#!/usr/bin/python3
"""Root-owned deployment receiver. Its authority is limited to this project's fixed paths."""
import io
import fcntl
import json
import os
import pwd
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path, PurePosixPath

BASE = Path('/opt/wow-character-status')
CONFIG = Path('/etc/wow-character-status')
GROUPS = {'ronkalot': 18081, 'navsquad': 18082}
LIMIT = 64 * 1024 * 1024


def run(*args):
    subprocess.run(args, check=True, stdin=subprocess.DEVNULL)


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


def main():
    if os.geteuid() != 0:
        raise SystemExit('Receiver requires the dedicated sudo rule')
    os.umask(0o077)
    deployment_lock = (BASE / 'deployment.lock').open('a')
    fcntl.flock(deployment_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    raw = sys.stdin.buffer.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError('Release archive is too large')
    releases = BASE / 'releases'
    stage = Path(tempfile.mkdtemp(prefix='.incoming-', dir=releases))
    old_target = (BASE / 'current').resolve() if (BASE / 'current').exists() else None
    old_config = {name: (CONFIG / name).read_bytes() if (CONFIG / name).exists() else None
                  for name in ['config.json', 'ronkalot.env', 'navsquad.env']}
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
        revision = (stage / '.deploy/REVISION').read_text().strip()
        if not re.fullmatch('[a-f0-9]{40}', revision):
            raise ValueError('Invalid revision')
        incoming = json.loads((stage / '.deploy/CONFIG.json').read_text())
        merged = json.loads(old_config['config.json']) if old_config['config.json'] else {}
        for group in GROUPS:
            values = merged.setdefault(group, {})
            for key in ('bot_token', 'guild_id', 'channel_id'):
                value = incoming.get(group, {}).get(key, '')
                if not isinstance(value, str):
                    raise ValueError('Invalid Discord setting')
                if value:
                    pattern = r'[A-Za-z0-9._=-]+' if key == 'bot_token' else r'[0-9]{1,30}'
                    if not re.fullmatch(pattern, value):
                        raise ValueError('Invalid Discord credential format')
                    values[key] = value
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
        for group, port in GROUPS.items():
            values = merged[group]
            data = environment({
                'DISCORD_GROUP_NAME': group, 'WOW_STATUS_PORT': str(port),
                'WOW_STATUS_REVISION': revision,
                'WOW_STATUS_DATABASE': f'/var/lib/wow-character-{group}/service.sqlite3',
                'DISCORD_BOT_TOKEN': values.get('bot_token', ''),
                'DISCORD_GUILD_ID': values.get('guild_id', ''),
                'DISCORD_CHANNEL_ID': values.get('channel_id', '')})
            (CONFIG / f'{group}.env').write_text(data)
            (CONFIG / f'{group}.env').chmod(0o600)
        (CONFIG / 'config.json').write_text(json.dumps(merged))
        (CONFIG / 'config.json').chmod(0o600)
        swap = BASE / 'next'
        swap.unlink(missing_ok=True)
        swap.symlink_to(candidate)
        swap.replace(BASE / 'current')
        activated = True
        for group in GROUPS:
            run('systemctl', 'restart', f'wow-character-status@{group}.service')
        for _ in range(20):
            if all(healthy(port, revision) for port in GROUPS.values()):
                for group in GROUPS:
                    run('systemctl', 'enable', f'wow-character-status@{group}.service')
                print('Activated', revision, 'for ronkalot and navsquad; both local health endpoints passed.')
                return
            time.sleep(1)
        raise RuntimeError('New release did not become healthy')
    except Exception:
        if activated and old_target:
            rollback = BASE / 'rollback'
            rollback.unlink(missing_ok=True)
            rollback.symlink_to(old_target)
            rollback.replace(BASE / 'current')
            for name, value in old_config.items():
                path = CONFIG / name
                if value is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(value)
                    path.chmod(0o600)
            for group in GROUPS:
                subprocess.run(['systemctl', 'restart', f'wow-character-status@{group}.service'], check=False)
            print('Deployment failed; restored the preceding project release.', file=sys.stderr)
        elif activated:
            for group in GROUPS:
                subprocess.run(['systemctl', 'stop', f'wow-character-status@{group}.service'], check=False)
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
