"""Production group names are shared secrets and stay out of Git (issue #1).

The deployment reads them from private configuration: the server's groups.json for
services and Caddy routes, and one GitHub secret for Discord settings.
"""
import ast
import hashlib
import importlib
import json
import re
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from wow_status.group_routing import group_key

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / 'deploy'))  # the deploy scripts import each other by name

# SHA-256 of the group names and route keys that were once committed. They remain in
# Git history, so the hashes reveal nothing new, and the plain values stay out of here.
LEAKED = {
    '95bfd582eb363cb5d8459207a8bd6848956596ed041788584173786f984bc3ab',
    'b2c9c4d22b9013979b568edb74d94586033adc98cd5dc1f9aff2f3085c913cd0',
    'de0a6abc9cbfff57a010d717f0ff58d03e3c78d24925ecfd2887ff88e76520dd',
    '4e126022269ef888ca81496fa6fa536674159d1bd1e56000ef224e8407c3767d',
}
GROUPS = {'group-b': {'name': 'second quiet harbor lantern', 'port': 18082},
          'group-a': {'name': 'Copper Otter Ridge 47', 'port': 18081}}


def load(path):
    return importlib.import_module(Path(path).stem)


def receiver():
    return load('deploy/install_release.py')


def tracked_text():
    try:
        listing = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip('Needs a Git checkout')
    for name in filter(None, listing.decode('utf-8').split('\0')):
        path = ROOT / name
        if path.is_file() and b'\0' not in (data := path.read_bytes())[:8192]:
            yield name, data.decode('utf-8', 'replace').lower()


def test_no_tracked_file_contains_a_leaked_group_name_or_route_key():
    found = []
    for name, text in tracked_text():
        words = set(re.findall(r'[a-z0-9]+', text)) | set(re.findall(r'(?=([0-9a-f]{22}))', text))
        if any(hashlib.sha256(word.encode()).hexdigest() in LEAKED for word in words):
            found.append(name)
    assert found == []


def test_group_config_accepts_instances_with_names_and_ports():
    assert receiver().validate_groups(json.loads(json.dumps(GROUPS))) == GROUPS


@pytest.mark.parametrize('change', [
    {'../etc': {'name': 'x', 'port': 18083}},             # instance becomes a path and account
    {'deploy': {'name': 'x', 'port': 18083}},             # the pipeline's own accounts
    {'build': {'name': 'x', 'port': 18083}},
    {'Group-C': {'name': 'x', 'port': 18083}},
    {'group-with-a-long-label': {'name': 'x', 'port': 18083}},  # account name over 32 characters
    {'group-c': {'name': 'say "hi"', 'port': 18083}},      # breaks the environment file
    {'group-c': {'name': 'cost $5', 'port': 18083}},
    {'group-c': {'name': ' padded', 'port': 18083}},
    {'group-c': {'name': '-quiet-harbor', 'port': 18083}},  # read as an option by the service
    {'group-c': {'name': 'line\nbreak', 'port': 18083}},
    {'group-c': {'name': 'x' * 81, 'port': 18083}},
    {'group-c': {'name': 'x', 'port': '18083'}},
    {'group-c': {'name': 'x', 'port': True}},
    {'group-c': {'name': 'x', 'port': 80}},
    {'group-c': {'name': 'x', 'port': 18081}},            # port already used
    {'group-c': {'name': 'copper otter RIDGE 47', 'port': 18083}},  # same name, other case
    {'group-c': {'name': 'x', 'port': 18083, 'extra': 1}},
    {'group-c': {'name': 'x'}},
])
def test_group_config_rejects_unsafe_or_ambiguous_entries(change):
    with pytest.raises(ValueError):
        receiver().validate_groups({**GROUPS, **change})


def test_group_config_needs_one_to_eight_groups():
    module = receiver()
    with pytest.raises(ValueError):
        module.validate_groups({})
    with pytest.raises(ValueError):
        module.validate_groups({f'g{n}': {'name': f'name {n}', 'port': 18000 + n} for n in range(9)})


def test_first_run_migrates_groups_from_the_previous_receivers_env_files(tmp_path):
    module = receiver()
    for instance, group in GROUPS.items():
        # Exactly what the previous receiver wrote, where the instance was the name.
        (tmp_path / f'{instance}.env').write_text(module.environment({
            'DISCORD_GROUP_NAME': group['name'], 'WOW_STATUS_PORT': str(group['port']),
            'WOW_STATUS_REVISION': 'a' * 40,
            'WOW_STATUS_DATABASE': f'/var/lib/wow-character-{instance}/service.sqlite3',
            'DISCORD_BOT_TOKEN': ''}), encoding='utf-8')
    # A copy under another name (a backup, say) names another instance's database: skipped.
    (tmp_path / 'group-a-old.env').write_bytes((tmp_path / 'group-a.env').read_bytes())
    groups, migrated = module.load_groups(tmp_path)
    assert (groups, migrated) == (GROUPS, True)
    (tmp_path / 'groups.json').write_text(json.dumps({'group-a': GROUPS['group-a']}), encoding='utf-8')
    assert module.load_groups(tmp_path) == ({'group-a': GROUPS['group-a']}, False)


def test_without_groups_json_or_env_files_the_receiver_refuses(tmp_path):
    with pytest.raises(ValueError):
        receiver().load_groups(tmp_path)


def test_discord_settings_apply_to_known_instances_and_keep_existing_values():
    module = receiver()
    merged = {'group-a': {'bot_token': 'old.token', 'guild_id': '1', 'channel_id': '2'}}
    unknown = module.merge_discord(GROUPS, merged, {
        'group-a': {'channel_id': '3', 'bot_token': ''},
        'group-b': {'bot_token': 'new.token', 'guild_id': '4', 'channel_id': '5'},
        'retired': {'bot_token': 'ignored'}})
    assert unknown == 1
    assert merged == {'group-a': {'bot_token': 'old.token', 'guild_id': '1', 'channel_id': '3'},
                      'group-b': {'bot_token': 'new.token', 'guild_id': '4', 'channel_id': '5'}}
    assert module.merge_discord(GROUPS, merged, {}) == 0
    assert merged['group-b']['bot_token'] == 'new.token'


@pytest.mark.parametrize('incoming', [
    [], {'group-a': 'token'}, {'group-a': {'guild_id': 12}}, {'group-a': {'guild_id': 'abc'}},
    {'group-a': {'bot_token': 'bad token'}},
])
def test_invalid_discord_settings_stop_the_deployment(incoming):
    with pytest.raises(ValueError):
        receiver().merge_discord(GROUPS, {}, incoming)


def test_systemctl_output_stays_out_of_the_public_deploy_log(monkeypatch):
    seen = []
    monkeypatch.setattr(subprocess, 'run', lambda command, **kwargs: seen.append((command, kwargs)))
    receiver().systemctl('enable', 'group-c')
    command, kwargs = seen[0]
    assert command == ['systemctl', 'enable', 'wow-character-status@group-c.service']
    assert kwargs['stdout'] is subprocess.DEVNULL and kwargs['stderr'] is subprocess.DEVNULL


def test_service_environment_takes_the_group_name_from_private_config():
    text = receiver().service_environment('group-a', GROUPS['group-a'], {'guild_id': '1'}, 'b' * 40)
    assert 'DISCORD_GROUP_NAME="Copper Otter Ridge 47"\n' in text
    assert 'WOW_STATUS_PORT="18081"\n' in text
    assert 'WOW_STATUS_DATABASE="/var/lib/wow-character-group-a/service.sqlite3"\n' in text
    assert 'DISCORD_GUILD_ID="1"\n' in text and 'DISCORD_BOT_TOKEN=""\n' in text


def test_release_without_the_discord_secret_keeps_the_servers_settings(capsys):
    assert load('deploy/make_release.py').discord_config('') == {}
    assert 'Discord settings unchanged' in capsys.readouterr().out


def test_release_reads_discord_settings_from_one_json_secret(capsys):
    raw = json.dumps({'group-a': {'bot_token': 'abc.def', 'guild_id': 123456789012345678,
                                  'channel_id': '987'}})
    assert load('deploy/make_release.py').discord_config(raw) == {
        'group-a': {'bot_token': 'abc.def', 'guild_id': '123456789012345678', 'channel_id': '987'}}
    # Each token is masked on its own, not only as part of the whole JSON secret.
    assert capsys.readouterr().out == '::add-mask::abc.def\n'


@pytest.mark.parametrize('raw', ['{"group-a": {"bot_token": "s3cr3t-value"', '["s3cr3t-value"]',
                                 '{"group-a": {"password": "s3cr3t-value"}}',
                                 '{"group-a": {"bot_token": 7}}',
                                 '{"group-a": {"bot_token": "s3cr3t value"}}',
                                 '{"group-a": {"guild_id": -1, "bot_token": "s3cr3t"}}',
                                 '{"s3cr3t-Label": {"guild_id": "1"}}',
                                 '{"deploy": {"guild_id": "1", "bot_token": "s3cr3t"}}'])
def test_malformed_discord_secret_fails_on_the_runner_without_echoing_it(raw):
    with pytest.raises(SystemExit) as failure:
        load('deploy/make_release.py').discord_config(raw)
    assert 's3cr3t' not in str(failure.value) and 'WOW_STATUS_DISCORD_CONFIG' in str(failure.value)


def test_caddyfile_template_has_no_group_routes():
    template = (ROOT / 'deploy/Caddyfile.production.template').read_text(encoding='utf-8')
    assert 'handle_path /groups/' not in template
    assert not re.search(r'[0-9a-f]{22}', template)
    assert template.count(load('deploy/render_caddyfile.py').MARKER) == 1


def test_caddyfile_routes_render_from_private_config_in_port_order():
    rendered = load('deploy/render_caddyfile.py').render(GROUPS)
    first, second = (f'handle_path /groups/{group_key(GROUPS[instance]["name"])}/*'
                     for instance in ('group-a', 'group-b'))
    assert rendered.index(first) < rendered.index(second) < rendered.index('handle /groups/*')
    assert '127.0.0.1:18081' in rendered and '127.0.0.1:18082' in rendered
    assert rendered.count('header_up X-WoW-Client-IP {http.request.remote.host}') == 2
    assert '# GROUP ROUTES' not in rendered and 'Unknown group' in rendered


def test_caddyfile_render_rejects_invalid_private_config():
    with pytest.raises(ValueError):
        load('deploy/render_caddyfile.py').render({'group-a': {'name': 'a"b', 'port': 18081}})


def test_caddyfile_render_rejects_two_groups_with_one_route_key(monkeypatch):
    module = load('deploy/render_caddyfile.py')
    monkeypatch.setattr(module, 'group_key', lambda name: '0' * 22)
    with pytest.raises(ValueError, match='route key'):
        module.render(GROUPS)


def test_rendered_routes_are_read_back_with_their_ports():
    module = load('deploy/render_caddyfile.py')
    assert module.routes(module.render(GROUPS)) == {
        (group_key(group['name']), str(group['port'])) for group in GROUPS.values()}


def test_render_command_writes_the_caddyfile_from_a_groups_file(tmp_path):
    config, output = tmp_path / 'groups.json', tmp_path / 'Caddyfile'
    config.write_text(json.dumps(GROUPS), encoding='utf-8')
    subprocess.run([sys.executable, str(ROOT / 'deploy/render_caddyfile.py'), '--groups-config', str(config),
                    '--output', str(output)], check=True)
    assert output.read_text(encoding='utf-8') == load('deploy/render_caddyfile.py').render(GROUPS)
    printed = subprocess.run([sys.executable, str(ROOT / 'deploy/render_caddyfile.py'), '--groups-config',
                              str(config)], check=True, capture_output=True).stdout.decode('utf-8')
    assert printed.replace('\r\n', '\n') == output.read_text(encoding='utf-8')


OLD_ROUTE = (b'wow.frankvalde.com {\n    handle_path /groups/0123456789abcdef012345/* {\n'
             b'        reverse_proxy 127.0.0.1:18089 {\n        }\n    }\n}\n')


@pytest.fixture
def live():
    """The live Caddyfile: by default the one the private config renders."""
    return {'config': load('deploy/render_caddyfile.py').render(GROUPS).encode()}


@pytest.fixture
def fake_ssh(monkeypatch, live):
    calls = []

    def check_output(command, **kwargs):
        calls.append(command)
        assert command[-1] == 'cat /etc/caddy/Caddyfile'
        return live['config']

    def run(command, **kwargs):
        calls.append(command)
        if command[-1] == 'cat /etc/wow-character-status/groups.json':
            return subprocess.CompletedProcess(command, 0, json.dumps(GROUPS).encode(), b'')
        if command[0] == 'scp' and sys.platform != 'win32':
            with tarfile.open(command[-2]) as package:
                calls.append(('uploaded', package.getnames()))
        return subprocess.CompletedProcess(command, 0, b'', b'')

    monkeypatch.setattr(subprocess, 'check_output', check_output)
    monkeypatch.setattr(subprocess, 'run', run)
    return calls


def test_publish_dry_run_shows_the_caddy_change_from_the_servers_private_config(fake_ssh, live, capsys):
    live['config'] = OLD_ROUTE
    load('deploy/publish_homepage.py').main(['--host', 'root@example.test', '--dry-run'])
    printed = capsys.readouterr().out
    assert f'+    handle_path /groups/{group_key(GROUPS["group-a"]["name"])}/*' in printed
    assert '-    handle_path /groups/0123456789abcdef012345/*' in printed
    assert 'would remove 1 and add 2 group route(s)' in printed
    assert 'nothing was uploaded or changed' in printed
    assert not any(call[0] in ('scp', 'uploaded') or call[-1] == 'python3 -' for call in fake_ssh)


@pytest.mark.parametrize('ports', [{'group-a': 18081}, {'group-a': 18082, 'group-b': 18081}])
def test_publish_refuses_to_change_live_group_routes(fake_ssh, live, tmp_path, ports):
    # A partial or stale private config: a group missing, or two groups' ports swapped.
    changed = {instance: dict(GROUPS[instance], port=port) for instance, port in ports.items()}
    live['config'] = load('deploy/render_caddyfile.py').render(changed).encode()
    site = tmp_path / 'homepage'
    (site / 'downloads').mkdir(parents=True)
    (site / 'index.html').write_text('<!doctype html>', encoding='utf-8')
    (site / 'downloads/release.json').write_text('{}', encoding='utf-8')
    with pytest.raises(SystemExit):
        load('deploy/publish_homepage.py').main(['--host', 'root@example.test', '--directory', str(site)])
    assert not any(call[0] in ('scp', 'uploaded') or call[-1] == 'python3 -' for call in fake_ssh)


def test_publish_sends_the_rendered_caddyfile_over_ssh_not_in_the_upload(fake_ssh, tmp_path, monkeypatch):
    renderer = load('deploy/render_caddyfile.py')
    template = tmp_path / 'Caddyfile.template'  # any text survives, even outside the BMP
    template.write_text(renderer.TEMPLATE.read_text(encoding='utf-8') + '# \U0001f600\n', encoding='utf-8')
    monkeypatch.setattr(renderer, 'TEMPLATE', template)
    site = tmp_path / 'homepage'
    (site / 'downloads').mkdir(parents=True)
    (site / 'index.html').write_text('<!doctype html>', encoding='utf-8')
    (site / 'downloads/release.json').write_text('{}', encoding='utf-8')
    sent = {}
    run = subprocess.run

    def capture(command, **kwargs):
        if command[-1] == 'python3 -':
            sent['script'] = kwargs['input'].decode('utf-8')
        return run(command, **kwargs)

    monkeypatch.setattr(subprocess, 'run', capture)
    config = tmp_path / 'groups.json'
    config.write_text(json.dumps(GROUPS), encoding='utf-8')
    load('deploy/publish_homepage.py').main(['--host', 'root@example.test', '--directory', str(site),
                                             '--groups-config', str(config)])
    assert not any(call[-1] == 'cat /etc/wow-character-status/groups.json' for call in fake_ssh)
    variables = dict(line.split('=', 1) for line in sent['script'].split('\nimport ', 1)[0].splitlines())
    assert ast.literal_eval(variables['CADDYFILE']) == renderer.render(GROUPS)
    if sys.platform != 'win32':  # Windows can't reopen the open temporary upload
        uploaded = next(call[1] for call in fake_ssh if call[0] == 'uploaded')
        assert sorted(uploaded) == ['downloads/release.json', 'index.html']


def test_publish_without_private_config_on_the_host_stops_before_uploading(monkeypatch):
    monkeypatch.setattr(subprocess, 'check_output', lambda command, **kwargs: OLD_ROUTE)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 1, b'', b'No such file')

    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(SystemExit, match='groups.json'):
        load('deploy/publish_homepage.py').main(['--host', 'root@example.test', '--dry-run'])
    assert len(calls) == 1
