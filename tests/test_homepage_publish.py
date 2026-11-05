"""The manual homepage publish checks before it switches and never ships stale files (issue #19)."""
import ast
import hashlib
import importlib
import importlib.util
import inspect
import io
import json
import os
import random
import shutil
import stat
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / 'deploy'))  # the deploy scripts import each other by name
GROUPS = {'group-a': {'name': 'Copper Otter Ridge 47', 'port': 18081}}
TEMPLATE = 'deploy/Caddyfile.production.template'


def load_builder():
    spec = importlib.util.spec_from_file_location('homepage_build', ROOT / 'scripts/build_homepage.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load_builder()


def git(root, *args):
    # core.autocrlf=false: commit exactly the bytes a test writes, on Windows too.
    # core.hooksPath: a developer's global hooks must not run in the test repositories.
    return subprocess.run(['git', '-C', str(root), '-c', 'user.name=Test', '-c', 'user.email=test@example.com',
                           '-c', 'commit.gpgsign=false', '-c', 'core.autocrlf=false',
                           '-c', 'core.hooksPath=no-hooks', *args], check=True, capture_output=True).stdout


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def commit(repo, files):
    for name, data in files.items():
        write(repo / name, data)
    git(repo, 'add', '-A')
    git(repo, 'commit', '-q', '-m', 'change')


@pytest.fixture
def repo(tmp_path):
    """A Git checkout holding what a homepage build and publish read, committed and clean.

    Website, addons and the Caddyfile template come from HEAD; the builder is this
    working tree's, so the code under test is what runs.
    """
    repo = tmp_path / 'repo'
    archive = git(ROOT, 'archive', '--format=tar', 'HEAD', 'website', 'addon', 'pyproject.toml', 'CHANGELOG.md',
                  TEMPLATE)
    with tarfile.open(fileobj=io.BytesIO(archive)) as package:
        for member in package.getmembers():
            if member.isfile():
                write(repo / member.name, package.extractfile(member).read())
    for script in ('build_homepage.py', 'whats_new.py'):
        write(repo / 'scripts' / script, (ROOT / 'scripts' / script).read_bytes())
    git(repo, 'init', '-q')
    git(repo, 'add', '-A')
    git(repo, 'commit', '-q', '-m', 'release')
    return repo


def build(repo, output):
    builder.build(repo, output, 'HEAD')
    return output


def snapshot(folder):
    return {path.relative_to(folder).as_posix(): path.read_bytes() for path in folder.rglob('*') if path.is_file()}


# The builder always produces a fresh folder.

def test_a_rebuild_leaves_no_file_of_the_earlier_build(repo, tmp_path):
    site = build(repo, tmp_path / 'dist/homepage')
    clean = snapshot(site)
    write(site / 'assets/removed-artwork.png', b'\x89PNG')
    write(site / 'downloads/WoWStatus-classic.zip', b'PK')
    build(repo, site)
    assert snapshot(site) == clean
    assert sorted(path.name for path in site.parent.iterdir()) == ['homepage']  # no staging folder left


def test_a_failed_build_leaves_the_earlier_build_untouched(repo, tmp_path):
    site = build(repo, tmp_path / 'dist/homepage')
    before = snapshot(site)
    pyproject = (repo / 'pyproject.toml').read_text(encoding='utf-8')
    version = builder.project_version(repo, 'HEAD')
    commit(repo, {'pyproject.toml': pyproject.replace(f'version = "{version}"', 'version = "9.9.9"').encode()})
    with pytest.raises(ValueError, match='must all equal pyproject.toml version 9.9.9'):
        build(repo, site)
    assert snapshot(site) == before
    assert sorted(path.name for path in site.parent.iterdir()) == ['homepage']


def test_the_builder_refuses_to_replace_a_folder_that_is_not_a_build(repo, tmp_path):
    notes = tmp_path / 'notes'
    write(notes / 'keep.txt', b'mine')
    with pytest.raises(ValueError, match='not an earlier homepage build'):
        build(repo, notes)
    assert snapshot(notes) == {'keep.txt': b'mine'}
    assert sorted(path.name for path in tmp_path.iterdir()) == ['notes', 'repo']


# The publisher's checks, all before the host is contacted.

@pytest.fixture
def publisher(repo, monkeypatch):
    module = importlib.import_module('publish_homepage')
    monkeypatch.setattr(module, 'REPOSITORY', repo)
    return module


@pytest.fixture
def host(monkeypatch):
    """A fake host whose live Caddyfile has the private groups' routes; records every call."""
    renderer = importlib.import_module('render_caddyfile')
    host = {'calls': [], 'caddy': renderer.render(GROUPS).encode(), 'fail': ()}
    real_run, real_check_output = subprocess.run, subprocess.check_output

    def check_output(command, **kwargs):
        if command[0] == 'git':
            return real_check_output(command, **kwargs)
        host['calls'].append(command)
        assert command[-1] == 'cat /etc/caddy/Caddyfile'
        return host['caddy']

    def run(command, **kwargs):
        if command[0] == 'git':
            return real_run(command, **kwargs)
        host['calls'].append(command)
        if command[0] == 'scp':
            host['upload'] = Path(command[-2]).read_bytes()
        if command[-1] == 'python3 -':
            host['script'] = kwargs['input'].decode('utf-8')
        if command[0] in host['fail'] or command[-1] in host['fail']:
            raise subprocess.CalledProcessError(1, command)
        return subprocess.CompletedProcess(command, 0, b'', b'')

    monkeypatch.setattr(subprocess, 'check_output', check_output)
    monkeypatch.setattr(subprocess, 'run', run)
    return host


def publish(publisher, site, tmp_path):
    config = tmp_path / 'groups.json'
    config.write_text(json.dumps(GROUPS), encoding='utf-8')
    publisher.main(['--host', 'root@example.test', '--directory', str(site), '--groups-config', str(config)])


def refused(publisher, site, tmp_path, host, capsys):
    """Publish, expect a refusal, and return its message; nothing may reach the host first."""
    with pytest.raises(SystemExit):
        publish(publisher, site, tmp_path)
    assert host['calls'] == []
    return capsys.readouterr().err


def settings(script):
    line = next(line for line in script.splitlines() if line.startswith('SETTINGS = '))
    return ast.literal_eval(line.removeprefix('SETTINGS = '))


def test_publish_uploads_a_checked_fresh_build_of_head(repo, tmp_path, publisher, host):
    site = build(repo, tmp_path / 'dist/homepage')
    publish(publisher, site, tmp_path)
    with tarfile.open(fileobj=io.BytesIO(host['upload'])) as package:
        uploaded = {member.name: package.extractfile(member).read() for member in package.getmembers()}
    assert uploaded == snapshot(site)
    sent = settings(host['script'])
    assert sent['revision'] == git(repo, 'rev-parse', 'HEAD').decode().strip()
    assert sent['archive_sha256'] == hashlib.sha256(host['upload']).hexdigest()
    assert sent['caddy_sha256'] == hashlib.sha256(host['caddy']).hexdigest()
    # The server receives exactly install_homepage.install's arguments, and only ASCII.
    inspect.signature(importlib.import_module('install_homepage').install).bind(**sent)
    assert host['script'].isascii()


def test_publish_refuses_a_build_of_another_revision(repo, tmp_path, publisher, host, capsys):
    site = build(repo, tmp_path / 'dist/homepage')
    commit(repo, {'website/style.css': (repo / 'website/style.css').read_bytes() + b'\n/* newer */\n'})
    assert 'was built for revision' in refused(publisher, site, tmp_path, host, capsys)


@pytest.mark.parametrize('change', ['modified', 'untracked', 'ignored', 'builder'])
def test_publish_refuses_uncommitted_build_inputs(repo, tmp_path, publisher, host, capsys, change):
    if change == 'modified':
        write(repo / 'website/style.css', (repo / 'website/style.css').read_bytes() + b'\n/* draft */\n')
    elif change == 'untracked':
        write(repo / 'website/assets/draft.png', b'\x89PNG')
    elif change == 'ignored':
        (repo / '.gitignore').write_text('.DS_Store\n', encoding='utf-8')
        commit(repo, {})
        write(repo / 'website/.DS_Store', b'\0\0\0\1Bud1')
    else:
        write(repo / 'scripts/build_homepage.py', (repo / 'scripts/build_homepage.py').read_bytes() + b'\n')
    # Built from the changed tree, so the folder holds exactly what the change would ship.
    site = build(repo, tmp_path / 'dist/homepage')
    assert 'Uncommitted or untracked build input' in refused(publisher, site, tmp_path, host, capsys)


def test_publish_refuses_a_download_that_does_not_match_its_checksum(repo, tmp_path, publisher, host, capsys):
    site = build(repo, tmp_path / 'dist/homepage')
    package = site / 'downloads/WoWStatus-tbc.zip'
    package.write_bytes(package.read_bytes() + b'corrupt')
    assert 'WoWStatus-tbc.zip does not match its checksum' in refused(publisher, site, tmp_path, host, capsys)


@pytest.mark.parametrize('fault, message', [
    ('stale', 'stale or extra: downloads/WoWStatus-classic.zip'),
    ('missing', 'missing: flavour.js'),
    ('different', 'different: index.html'),
])
def test_publish_refuses_anything_but_a_fresh_build(repo, tmp_path, publisher, host, capsys, fault, message):
    site = build(repo, tmp_path / 'dist/homepage')
    if fault == 'stale':  # what merging into an old output folder used to leave behind
        write(site / 'downloads/WoWStatus-classic.zip', b'PK')
    elif fault == 'missing':
        (site / 'flavour.js').unlink()
    else:
        (site / 'index.html').write_bytes((site / 'index.html').read_bytes().replace(b'</body>', b'<p>x</p></body>'))
    assert message in refused(publisher, site, tmp_path, host, capsys)


def test_publish_renders_the_caddyfile_from_the_committed_template(repo, tmp_path, publisher, host):
    template = (repo / TEMPLATE).read_text(encoding='utf-8')
    commit(repo, {TEMPLATE: (template + '# committed \U0001f600\n').encode('utf-8')})  # any text, even outside the BMP
    write(repo / TEMPLATE, (template + '# uncommitted\n').encode('utf-8'))
    site = build(repo, tmp_path / 'dist/homepage')
    publish(publisher, site, tmp_path)
    renderer = importlib.import_module('render_caddyfile')
    assert settings(host['script'])['caddyfile'] == renderer.render(GROUPS, template + '# committed \U0001f600\n')
    assert host['script'].isascii()


@pytest.mark.parametrize('failing', ['scp', 'python3 -'])
def test_a_failed_upload_or_install_removes_the_uploaded_archive(repo, tmp_path, publisher, host, failing):
    site = build(repo, tmp_path / 'dist/homepage')
    host['fail'] = (failing,)
    with pytest.raises(subprocess.CalledProcessError):
        publish(publisher, site, tmp_path)
    remote = next(command for command in host['calls'] if command[0] == 'scp')[-1].split(':', 1)[1]
    assert remote.startswith('/tmp/wow-homepage-')
    assert host['calls'][-1][-1] == f'rm -f -- {remote}'


# The server side: deploy/install_homepage.py, which runs on the Linux host.

@pytest.fixture
def server(tmp_path, monkeypatch):
    if sys.platform == 'win32':
        pytest.skip('The server side runs on Linux')
    module = importlib.import_module('install_homepage')
    base = tmp_path / 'srv'
    old = base / 'releases/old'
    write(old / 'index.html', b'old site')
    (base / 'current').symlink_to(old)
    caddy = tmp_path / 'etc/Caddyfile'
    write(caddy, b'old caddy\n')
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        if command[:2] == ['caddy', 'validate']:
            candidate = Path(command[3])
            commands.append(('candidate', candidate, stat.S_IMODE(candidate.stat().st_mode), candidate.read_text(
                encoding='utf-8'), sorted(path.name for path in (base / 'releases/20261105T000000000000Z').rglob('*'))))
        failed = any(command[:len(prefix)] == prefix for prefix in server_state['fail'])
        if failed and kwargs.get('check'):
            raise subprocess.CalledProcessError(1, command)
        return subprocess.CompletedProcess(command, int(failed))

    server_state = {'module': module, 'base': base, 'old': old, 'caddy': caddy, 'commands': commands, 'fail': []}
    monkeypatch.setattr(subprocess, 'run', run)
    return server_state


def payload(tmp_path, data=None, revision='a' * 40):
    """An uploaded archive, and the settings the publisher would send with it."""
    if data is None:
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w:gz') as package:
            # Incompressible artwork, so half the archive holds only part of the files.
            for name, content in [('index.html', b'new site'), ('assets/art.png', random.Random(1).randbytes(65536)),
                                  ('downloads/release.json', json.dumps({'addon_revision': revision}).encode())]:
                info = tarfile.TarInfo(name)
                info.size = len(content)
                package.addfile(info, io.BytesIO(content))
        data = buffer.getvalue()
    upload = tmp_path / 'wow-homepage.tar.gz'
    upload.write_bytes(data)
    return {'payload': str(upload), 'release': '20261105T000000000000Z', 'revision': 'a' * 40,
            'archive_sha256': hashlib.sha256(data).hexdigest(),
            'caddy_sha256': hashlib.sha256(b'old caddy\n').hexdigest(), 'caddyfile': 'new caddy \U0001f600\n'}


def install(server, sent):
    return server['module'].install(**sent, base=server['base'], caddy=server['caddy'])


def unchanged(server, sent):
    base = server['base']
    assert Path(os.readlink(base / 'current')) == server['old']
    assert server['caddy'].read_bytes() == b'old caddy\n'
    assert sorted(path.name for path in (base / 'releases').iterdir()) == ['old']
    assert not any(path.name.startswith('.') for path in base.iterdir())  # no candidate or swap link
    assert not Path(sent['payload']).exists()


def test_install_validates_the_caddyfile_outside_the_web_root_then_switches(server, tmp_path):
    sent = payload(tmp_path)
    result = install(server, sent)
    base, release = server['base'], server['base'] / 'releases' / sent['release']
    assert Path(os.readlink(base / 'current')) == release
    assert (base / 'current/index.html').read_bytes() == b'new site'
    assert server['caddy'].read_text(encoding='utf-8') == sent['caddyfile']
    _, candidate, mode, text, served = next(item for item in server['commands'] if item[0] == 'candidate')
    assert candidate.parent == base and not candidate.is_relative_to(base / 'releases')
    assert (mode, text) == (0o600, sent['caddyfile'])
    assert 'Caddyfile' not in ' '.join(served)  # nothing of it inside the served release
    assert not candidate.exists() and not Path(sent['payload']).exists()
    backup = base / f'Caddyfile.before-{sent["release"]}'
    assert backup.read_bytes() == b'old caddy\n' and stat.S_IMODE(backup.stat().st_mode) == 0o600
    assert result['previous'] == str(server['old'])


def test_install_refuses_an_incomplete_upload_before_changing_anything(server, tmp_path):
    sent = payload(tmp_path)
    upload = Path(sent['payload'])
    upload.write_bytes(upload.read_bytes()[:-100])  # cut off in transit
    with pytest.raises(RuntimeError, match='incomplete'):
        install(server, sent)
    unchanged(server, sent)
    assert server['commands'] == []


def test_install_removes_a_partly_extracted_release(server, tmp_path):
    whole = payload(tmp_path)
    data = Path(whole['payload']).read_bytes()
    # A damaged archive that matches its checksum: extraction stops part way.
    sent = payload(tmp_path, data[:len(data) // 2])
    with pytest.raises((tarfile.TarError, EOFError)):
        install(server, sent)
    unchanged(server, sent)
    assert server['commands'] == []


def test_a_retry_never_touches_an_existing_release(server, tmp_path):
    sent = payload(tmp_path)
    existing = server['base'] / 'releases' / sent['release']
    write(existing / 'index.html', b'someone else')
    with pytest.raises(FileExistsError):
        install(server, sent)
    assert (existing / 'index.html').read_bytes() == b'someone else'
    assert not Path(sent['payload']).exists()
    assert server['commands'] == []


def test_install_refuses_a_caddyfile_changed_since_inspection(server, tmp_path):
    sent = payload(tmp_path)
    sent['caddy_sha256'] = hashlib.sha256(b'what the publisher saw\n').hexdigest()
    with pytest.raises(RuntimeError, match='Caddy changed'):
        install(server, sent)
    unchanged(server, sent)


def test_install_refuses_an_upload_of_another_revision(server, tmp_path):
    sent = payload(tmp_path, revision='b' * 40)
    with pytest.raises(RuntimeError, match='not the checked build'):
        install(server, sent)
    unchanged(server, sent)


@pytest.mark.parametrize('failing', [['caddy', 'validate'], ['systemctl', 'reload', 'caddy']])
def test_a_failed_validation_or_reload_restores_the_previous_site(server, tmp_path, failing):
    sent = payload(tmp_path)
    server['fail'] = [failing]
    with pytest.raises(subprocess.CalledProcessError):
        install(server, sent)
    unchanged(server, sent)
    reloads = [command for command in server['commands'] if command[:2] == ['systemctl', 'reload']]
    assert len(reloads) == (2 if failing[0] == 'systemctl' else 0)  # the failed reload, then the rollback's


def test_a_first_publish_that_fails_after_the_switch_leaves_no_site(server, tmp_path):
    (server['base'] / 'current').unlink()
    shutil.rmtree(server['old'])
    sent = payload(tmp_path)
    server['fail'] = [['systemctl', 'is-active', '--quiet', 'caddy']]
    with pytest.raises(subprocess.CalledProcessError):
        install(server, sent)
    assert not (server['base'] / 'current').exists() and not (server['base'] / 'current').is_symlink()
    assert server['caddy'].read_bytes() == b'old caddy\n'
    assert list((server['base'] / 'releases').iterdir()) == []
