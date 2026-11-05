"""The root release receiver end to end, with the server's commands faked (issue #27).

Covers what deploy/install_release.py does around an activation: the hash-locked
install, restoring the private configuration after a failure, removing a failed
candidate, pruning old releases, waiting for the lock it shares with the manual
homepage publish, and rolling back when the deploy job's public check fails.
"""
import importlib.util
import io
import itertools
import json
import os
import stat
import subprocess
import sys
import tarfile
import types
from pathlib import Path

import pytest

if sys.platform == 'win32':
    pytest.skip('The root deployment receiver is Linux-only', allow_module_level=True)

ROOT = Path(__file__).parents[1]
GROUPS = {'group-a': {'name': 'Copper Otter Ridge 47', 'port': 18081},
          'group-b': {'name': 'second quiet harbor lantern', 'port': 18082}}
A, B, C = 'a' * 40, 'b' * 40, 'c' * 40


def load_receiver():
    spec = importlib.util.spec_from_file_location('release_receiver', ROOT / 'deploy/install_release.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def archive(revision, config=None, mode=0o644):
    """A release archive as deploy/make_release.py builds it, with a one-page homepage."""
    buffer = io.BytesIO()
    files = {'pyproject.toml': b'[project]\n', 'requirements.txt': b'# locked\n',
             '.deploy/REVISION': revision.encode(), '.deploy/CONFIG.json': json.dumps(config or {}).encode(),
             '.deploy/HOMEPAGE/index.html': f'site {revision}'.encode()}
    with tarfile.open(fileobj=buffer, mode='w') as package:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), mode
            package.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


class Server:
    """Temporary BASE, CONFIG and HOMEPAGE; records the commands the receiver runs."""

    def __init__(self, tmp_path, monkeypatch):
        self.module = module = load_receiver()
        self.base, self.config, self.homepage = tmp_path / 'opt', tmp_path / 'etc', tmp_path / 'srv'
        (self.base / 'releases').mkdir(parents=True)
        self.config.mkdir()
        self.homepage.mkdir()
        (self.config / 'groups.json').write_text(json.dumps(GROUPS), encoding='utf-8')
        self.commands, self.broken, self.pip_fails = [], set(), False
        self.on_sleep = None
        self.clock = iter(range(10**6))
        monkeypatch.setattr(module, 'BASE', self.base)
        monkeypatch.setattr(module, 'CONFIG', self.config)
        monkeypatch.setattr(module, 'HOMEPAGE', self.homepage)
        monkeypatch.setattr(module, 'run', self.run)
        monkeypatch.setattr(module, 'systemctl', self.systemctl)
        monkeypatch.setattr(module, 'healthy', self.healthy)
        # prepare_homepage has its own tests (test_homepage_release.py) and needs real ZIPs.
        monkeypatch.setattr(module, 'prepare_homepage',
                            lambda stage, revision: (stage / '.deploy/HOMEPAGE').rename(stage / 'public-homepage'))
        monkeypatch.setattr(module, 'time', types.SimpleNamespace(
            time_ns=lambda: 1000 + next(self.clock), monotonic=itertools.count().__next__, sleep=self.sleep))
        monkeypatch.setattr(module.os, 'geteuid', lambda: 0)
        monkeypatch.setattr(module.os, 'chown', lambda *args, **kwargs: None)
        monkeypatch.setitem(sys.modules, 'pwd', types.SimpleNamespace(
            getpwnam=lambda name: types.SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid())))
        self.monkeypatch = monkeypatch

    def run(self, *args):
        self.commands.append(args)
        if 'venv' in args:
            python = Path(args[-1]) / 'bin/python'
            python.parent.mkdir(parents=True)
            python.write_text('', encoding='utf-8')
        elif 'pip' in args and self.pip_fails:
            raise subprocess.CalledProcessError(1, args)

    def systemctl(self, action, instance, check=True):
        self.commands.append(('systemctl', action, instance))

    def healthy(self, port, revision):
        """A service reports the revision its env file names, and runs the live release."""
        live = self.module.live(self.base / 'current')
        return live is not None and live.name.startswith(revision) and revision not in self.broken

    def sleep(self, seconds):
        if self.on_sleep:
            self.on_sleep()

    def send(self, data, run=None):
        """Feed data to the receiver on stdin and run main() (or `run`, such as its entry())."""
        self.commands.clear()
        self.monkeypatch.setattr(sys, 'stdin', types.SimpleNamespace(buffer=io.BytesIO(data)))
        umask = os.umask(0o022)
        os.umask(umask)
        try:
            (run or self.module.main)()
        finally:
            os.umask(umask)  # main() sets the receiver's private umask

    def deploy(self, revision, config=None, mode=0o644):
        self.send(archive(revision, config, mode))

    def roll_back(self, revision):
        self.send(f'wow-status-rollback {revision}\n'.encode())

    def live(self):
        return self.module.live(self.base / 'current')

    def homepage_text(self):
        return (self.homepage / 'current/index.html').read_text(encoding='utf-8')

    def releases(self):
        return sorted(path.name for path in (self.base / 'releases').iterdir())

    def private(self):
        return {path.name: path.read_bytes() for path in sorted(self.config.iterdir())}

    def env_revision(self, instance):
        text = (self.config / f'{instance}.env').read_text(encoding='utf-8')
        return next(line for line in text.splitlines() if line.startswith('WOW_STATUS_REVISION=')).split('"')[1]


@pytest.fixture
def server(tmp_path, monkeypatch):
    return Server(tmp_path, monkeypatch)


def deployed(server, *revisions):
    """Deploy each revision in turn; return the live release folder."""
    for revision in revisions:
        server.deploy(revision)
    return server.live()


# Installing from the hash-pinned lock.

def test_the_release_venv_installs_only_hash_pinned_wheels_then_the_project_offline(server):
    live = deployed(server, A)
    pip = [command for command in server.commands if 'pip' in command]
    assert pip == [
        ('runuser', '-u', 'wow-character-build', '--', str(live / '.venv/bin/python'), '-m', 'pip', 'install',
         '--disable-pip-version-check', '--no-input', '--require-hashes', '--only-binary', ':all:',
         '-r', str(live / 'requirements.txt')),
        ('runuser', '-u', 'wow-character-build', '--', str(live / '.venv/bin/python'), '-m', 'pip', 'install',
         '--disable-pip-version-check', '--no-input', '--no-deps', '--no-build-isolation', '--no-index',
         str(live))]


def test_a_failed_install_leaves_no_candidate_and_changes_nothing(server):
    first = deployed(server, A)
    before = server.private()
    server.pip_fails = True
    with pytest.raises(subprocess.CalledProcessError):
        server.deploy(B)
    assert server.live() == first
    assert server.releases() == [first.name]
    assert server.private() == before
    assert not any(command[0] == 'systemctl' for command in server.commands)


# Restoring the private configuration.

def test_a_release_that_never_becomes_healthy_is_removed_and_the_config_restored(server):
    first = deployed(server, A)
    before = server.private()
    server.broken.add(B)
    with pytest.raises(RuntimeError, match='did not become healthy'):
        server.deploy(B, {'group-a': {'bot_token': 'new.token', 'guild_id': '1', 'channel_id': '2'}})
    assert server.live() == first
    assert server.private() == before  # env files name A again, and the new token is gone
    assert server.releases() == [first.name]
    assert server.homepage_text() == f'site {A}'
    assert ('systemctl', 'restart', 'group-a') in server.commands[-2:]


def test_a_failure_while_the_config_is_written_restores_it_before_activation(server, monkeypatch):
    """The window the issue names: env files are written, `current` still points at A."""
    first = deployed(server, A)
    before = server.private()
    real = server.module.write_private

    def write_private(path, text):
        if path.name == 'config.json':
            raise OSError('disk full')
        real(path, text)

    monkeypatch.setattr(server.module, 'write_private', write_private)
    with pytest.raises(OSError):
        server.deploy(B)
    assert server.private() == before
    assert server.live() == first
    assert server.releases() == [first.name]


# Pruning.

def test_only_recent_releases_survive_and_nothing_in_use_is_pruned(server):
    releases = server.base / 'releases'
    old = [releases / f'{C}-{time}' for time in range(1, 9)]  # 1 oldest ... 8 newest
    for release in old:
        (release / 'public-homepage').mkdir(parents=True)
    (releases / 'hand-made-backup').mkdir()
    (releases / '.incoming-interrupted').mkdir()
    os.symlink(old[2], server.base / 'current')  # the release this deploy replaces
    os.symlink(old[0] / 'public-homepage', server.homepage / 'current')
    live = deployed(server, A)
    kept = {live.name, *(path.name for path in old[4:]), old[2].name, old[0].name, 'hand-made-backup'}
    assert set(server.releases()) == kept
    assert len(old[4:]) + 1 == server.module.KEEP_RELEASES


def test_a_second_deploy_keeps_the_one_it_replaced_for_rollback(server):
    first = deployed(server, A)
    second = deployed(server, B)
    assert server.releases() == sorted([first.name, second.name])
    state = json.loads((server.base / server.module.STATE).read_text(encoding='utf-8'))
    assert state == {'revision': B, 'release': second.name, 'previous': first.name,
                     'previous_homepage': str(first / 'public-homepage'), 'added': []}


def test_redeploying_the_live_revision_keeps_the_earlier_rollback_target(server):
    first = deployed(server, A)
    deployed(server, B)
    third = deployed(server, B)  # "Re-run all jobs" on B after its rollback was refused
    state = json.loads((server.base / server.module.STATE).read_text(encoding='utf-8'))
    assert (state['release'], state['previous']) == (third.name, first.name)
    server.roll_back(B)
    assert server.live() == first and server.env_revision('group-a') == A


def test_a_redeploy_without_a_record_of_the_earlier_release_cannot_roll_back(server):
    deployed(server, B)
    third = deployed(server, B)
    with pytest.raises(server.module.Refused, match='No earlier release'):
        server.roll_back(B)
    assert server.live() == third


# The lock shared with the manual homepage publish.

def hold(path):
    import fcntl  # Linux only; imported here so Windows reaches the module-level skip
    handle = open(path, 'ab')
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    return handle


def test_a_deploy_waits_for_a_manual_homepage_publish(server, capsys):
    holder = hold(server.base / 'deployment.lock')
    unread = []

    def publish_finishes():
        unread.append(sys.stdin.buffer.read())  # the receiver read the whole upload first
        holder.close()

    server.on_sleep = publish_finishes
    live = deployed(server, A)
    assert live.name.startswith(A) and unread == [b'']
    assert 'Waiting for another deployment or homepage publish' in capsys.readouterr().err


def test_a_deploy_that_cannot_get_the_lock_changes_nothing(server, monkeypatch):
    holder = hold(server.base / 'deployment.lock')
    monkeypatch.setattr(server.module, 'LOCK_WAIT', 0)
    with pytest.raises(server.module.Refused, match='still running'):
        server.deploy(A)
    holder.close()
    assert server.live() is None and server.releases() == [] and server.commands == []


def test_the_homepage_publish_takes_the_same_lock():
    sys.path.insert(0, str(ROOT / 'deploy'))
    try:
        import install_homepage
    finally:
        sys.path.remove(str(ROOT / 'deploy'))
    assert install_homepage.LOCK == load_receiver().BASE / 'deployment.lock'


# Rolling back after the public verification fails.

def test_a_rollback_restores_the_previous_release_config_and_homepage(server):
    first = deployed(server, A)
    deployed(server, B)
    server.roll_back(B)
    assert server.live() == first
    assert server.env_revision('group-a') == server.env_revision('group-b') == A
    assert server.homepage_text() == f'site {A}'
    assert [command for command in server.commands if command[1] == 'restart'] == [
        ('systemctl', 'restart', 'group-a'), ('systemctl', 'restart', 'group-b')]
    with pytest.raises(server.module.Refused, match='No recorded deployment'):
        server.roll_back(B)  # once only
    assert server.live() == first


@pytest.mark.parametrize('revision', [A, C])
def test_a_rollback_for_another_revision_changes_nothing(server, revision):
    deployed(server, A)
    second = deployed(server, B)
    before = server.private()
    with pytest.raises(server.module.Refused, match='not the one to roll back'):
        server.roll_back(revision)
    assert server.live() == second and server.private() == before and server.commands == []


def test_a_rollback_without_an_earlier_release_changes_nothing(server):
    first = deployed(server, A)
    with pytest.raises(server.module.Refused, match='No earlier release'):
        server.roll_back(A)
    assert server.live() == first and server.commands == []


def test_a_rollback_whose_target_is_unhealthy_keeps_the_live_release(server):
    deployed(server, A)
    second = deployed(server, B)
    before = server.private()
    server.broken.add(A)
    with pytest.raises(RuntimeError, match='earlier release did not become healthy'):
        server.roll_back(B)
    assert server.live() == second and server.private() == before
    assert server.homepage_text() == f'site {B}'


def test_a_rollback_after_a_manual_publish_changes_nothing(server):
    """The manual publish explains the failed check; the release itself may be fine."""
    deployed(server, A)
    second = deployed(server, B)
    manual = server.homepage / 'releases/20261105T000000000000Z'
    manual.mkdir(parents=True)
    (manual / 'index.html').write_text('manual', encoding='utf-8')
    server.module.point(server.homepage / 'current', manual)
    before = server.private()
    with pytest.raises(server.module.Refused, match='manual publish replaced the homepage'):
        server.roll_back(B)
    assert server.live() == second and server.private() == before and server.commands == []
    assert server.homepage_text() == 'manual'


def test_a_rollback_without_an_earlier_homepage_changes_nothing(server):
    first = deployed(server, A)
    second = deployed(server, B)
    (first / 'public-homepage/index.html').unlink()
    (first / 'public-homepage').rmdir()
    with pytest.raises(server.module.Refused, match='No earlier homepage'):
        server.roll_back(B)
    assert server.live() == second and server.commands == []
    assert server.homepage_text() == f'site {B}'


def test_a_rollback_stops_services_the_failed_deploy_started_first(server):
    first = deployed(server, A)
    groups = {**GROUPS, 'group-c': {'name': 'third quiet harbor', 'port': 18083}}
    (server.config / 'groups.json').write_text(json.dumps(groups), encoding='utf-8')
    deployed(server, B)
    server.roll_back(B)
    assert server.live() == first
    assert not (server.config / 'group-c.env').exists()
    assert ('systemctl', 'restart', 'group-c') not in server.commands
    assert server.commands[-2:] == [('systemctl', 'stop', 'group-c'), ('systemctl', 'disable', 'group-c')]


def test_a_rollback_that_cannot_forget_its_record_still_reports_success(server, monkeypatch, capsys):
    first = deployed(server, A)
    deployed(server, B)
    real = Path.unlink

    def unlink(path, missing_ok=False):
        if path.name == server.module.STATE:
            raise PermissionError('read-only')
        real(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, 'unlink', unlink)
    server.roll_back(B)
    assert server.live() == first
    assert f'Rolled back {B} to {A}' in capsys.readouterr().out


def test_a_failed_homepage_switch_rolls_the_services_forward_again(server, monkeypatch, capsys):
    first = deployed(server, A)
    second = deployed(server, B)
    before = server.private()
    real = server.module.switch_homepage

    def switch_homepage(target):
        if target == first / 'public-homepage':
            raise OSError('read-only file system')
        real(target)

    monkeypatch.setattr(server.module, 'switch_homepage', switch_homepage)
    with pytest.raises(OSError):
        server.roll_back(B)
    assert server.live() == second and server.private() == before
    assert server.homepage_text() == f'site {B}'
    assert 'live and healthy again' in capsys.readouterr().err


def test_refusals_explain_themselves_and_failures_show_only_their_type(server):
    with pytest.raises(SystemExit, match='^Deployment refused: No recorded deployment to roll back'):
        server.send(f'wow-status-rollback {A}'.encode(), server.module.entry)
    with pytest.raises(SystemExit) as failure:
        server.send(b'not a tar s3cr3t', server.module.entry)
    assert str(failure.value) == 'Deployment failed (ReadError).'


def test_the_deploy_job_rolls_back_only_after_a_failed_verification():
    workflow = (ROOT / '.github/workflows/checks.yml').read_text(encoding='utf-8')
    deploy = workflow[workflow.index('\n  deploy:\n'):]
    steps = deploy.split('\n      - ')
    verify = next(step for step in steps if step.startswith('name: Verify live homepage'))
    rollback = next(step for step in steps if step.startswith('name: Roll back'))
    assert 'id: verify' in verify
    assert "if: failure() && steps.verify.outcome == 'failure' && steps.verify.outputs.status != '3'" in rollback
    assert 'echo "status=$status" >> "$GITHUB_OUTPUT"' in verify  # 3: the site was unreachable
    assert steps.index(verify) + 1 == steps.index(rollback)
    # What the step sends is exactly what the receiver accepts as a rollback request.
    request = rollback.split("printf '", 1)[1].split("'", 1)[0].replace('%s', B).replace('\\n', '\n')
    assert load_receiver().ROLLBACK_REQUEST.fullmatch(request.encode())


# The receiver ignores the archive's file modes (issue #27, tar modes).

def test_installed_files_are_public_whatever_modes_the_archive_carries(server):
    server.deploy(A, mode=0o600)
    live = server.live()
    modes = {path.relative_to(live).as_posix(): stat.S_IMODE(path.stat().st_mode)
             for path in [live / 'public-homepage', live / 'public-homepage/index.html', live / 'pyproject.toml']}
    assert modes == {'public-homepage': 0o755, 'public-homepage/index.html': 0o644, 'pyproject.toml': 0o644}
