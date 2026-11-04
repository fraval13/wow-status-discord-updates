"""A failing Discord bot must never take ingestion or /health down with it."""
import asyncio
import importlib.util
import json
import logging
import socket
import urllib.request
import warnings
from pathlib import Path

import aiohttp
import pytest
from aiohttp.test_utils import TestClient, TestServer

from wow_status import discord_bot
from wow_status.server import (
    DISCORD_RETRY_FIRST,
    DISCORD_RETRY_MAX,
    create_app,
    failure_name,
    run_discord,
    serve,
)


class LoginFailure(Exception):
    """Stands in for discord.LoginFailure (a revoked or reset bot token)."""
    __module__ = 'discord.errors'


class Forbidden(Exception):
    """Stands in for discord.Forbidden, which carries Discord's status and error code."""
    __module__ = 'discord.errors'
    status, code = 403, 50001


class Stop(BaseException):
    """Ends a supervision loop from a fake sleep; not an Exception, so never retried."""


async def health(client):
    response = await client.get('/health')
    assert response.status == 200
    return await response.json()


async def test_health_without_bot_reports_discord_disabled(store):
    client = TestClient(TestServer(create_app(store)))
    await client.start_server()
    try:
        body = await health(client)
        assert body['status'] == 'ok' and body['discord'] == 'disabled'
        assert 'discord_error' not in body
    finally:
        await client.close()


async def test_health_reports_ready_bot_and_retrying_bot_without_secrets(store):
    status = {}
    client = TestClient(TestServer(create_app(store, discord=status)))
    await client.start_server()
    try:
        status.update(state='starting', probe=lambda: None)
        assert (await health(client))['discord'] == 'starting'
        status['probe'] = lambda: {'discord': 'ready'}
        assert (await health(client))['discord'] == 'ready'
        status['probe'] = lambda: {'discord': 'delivery_retrying', 'discord_error': 'KeyError'}
        body = await health(client)
        assert body['discord'] == 'delivery_retrying' and body['discord_error'] == 'KeyError'
        status.update(state='retrying', probe=None, error='LoginFailure')
        body = await health(client)
        # The deploy receiver only accepts status 'ok'; a Discord outage must not fail it.
        assert body['status'] == 'ok'
        assert body['discord'] == 'retrying' and body['discord_error'] == 'LoginFailure'
    finally:
        await client.close()


def test_failure_name_adds_discord_http_status_and_code():
    assert failure_name(LoginFailure('Improper token has been passed.')) == 'LoginFailure'
    assert failure_name(Forbidden('Missing Access')) == 'Forbidden 403 50001'
    # aiohttp's `code` is a deprecated alias of `status`: name only, and no warning.
    error = aiohttp.ClientResponseError(None, (), status=503)
    with warnings.catch_warnings():
        warnings.simplefilter('error')
        assert failure_name(error) == 'ClientResponseError'


async def test_a_retry_clears_the_last_error_and_logs_the_traceback(caplog):
    seen, status = [], {}

    async def bot(state):
        seen.append(dict(state))
        raise LoginFailure()

    async def sleep(delay):
        if len(seen) == 2:
            raise Stop

    with caplog.at_level(logging.ERROR, logger='wow_status.server'), pytest.raises(Stop):
        await run_discord(bot, status, sleep=sleep)
    assert seen[1]['state'] == 'starting' and 'error' not in seen[1]
    record = caplog.records[0]
    assert 'LoginFailure' in record.getMessage() and record.exc_info[0] is LoginFailure


async def test_failures_are_retried_with_doubling_capped_backoff():
    calls, delays, status = [], [], {}

    async def bot(state):
        calls.append(dict(state))
        raise LoginFailure()

    async def sleep(delay):
        delays.append(delay)
        assert status['state'] == 'retrying' and status['error'] == 'LoginFailure'
        if len(delays) == 9:
            raise Stop

    with pytest.raises(Stop):
        await run_discord(bot, status, sleep=sleep)
    assert len(calls) == 9 and all(call['state'] == 'starting' for call in calls)
    assert delays == [30, 60, 120, 240, 480, 600, 600, 600, 600]
    assert delays[0] == DISCORD_RETRY_FIRST and max(delays) == DISCORD_RETRY_MAX


async def test_backoff_resets_after_a_long_session_and_a_clean_stop_is_retried():
    now, delays, errors, status = [0.0], [], [], {}
    sessions = iter([5, 5, DISCORD_RETRY_MAX, 5])

    async def bot(state):
        now[0] += next(sessions)  # How long this session stayed up before it ended.
        if len(delays) == 2:
            return  # client.start() returning still means the bot is gone.
        raise Forbidden()

    async def sleep(delay):
        delays.append(delay)
        errors.append(status['error'])
        if len(delays) == 4:
            raise Stop

    with pytest.raises(Stop):
        await run_discord(bot, status, sleep=sleep, clock=lambda: now[0])
    assert delays == [30, 60, 30, 60]
    assert errors == ['Forbidden 403 50001', 'Forbidden 403 50001', 'Stopped',
                      'Forbidden 403 50001']


async def test_cancelling_the_service_stops_the_bot_without_a_retry():
    started, status = asyncio.Event(), {}

    async def bot(state):
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(run_discord(bot, status))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert status['state'] == 'starting' and 'error' not in status


class FakeClient:
    instances = []

    def __init__(self, store, guild_id, channel_id):
        self.args = (guild_id, channel_id)
        self.closed = False
        FakeClient.instances.append(self)

    def state(self):
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        self.closed = True

    async def start(self, token):
        assert token == 'secret-token'
        raise LoginFailure()


async def test_each_session_uses_a_fresh_closed_client(store, monkeypatch):
    monkeypatch.setattr(discord_bot, 'StatusBot', FakeClient)
    FakeClient.instances.clear()
    bot = discord_bot.session(store, 1, 2, 'secret-token')
    for _ in range(2):
        status = {}
        with pytest.raises(LoginFailure):
            await bot(status)
        assert status['probe'] == FakeClient.instances[-1].state
    first, second = FakeClient.instances
    assert first is not second and first.closed and second.closed and first.args == (1, 2)


def outbox_status(store, delivery):
    return store.db.execute('SELECT status FROM outbox WHERE id=?', (delivery,)).fetchone()[0]


async def test_a_crashed_delivery_loop_restarts_without_ending_the_session(store, payload,
                                                                          monkeypatch, caplog):
    """Slash commands stay up; the failure shows on /health and in the journal, and an
    interrupted send is marked uncertain in the database and the character archive."""
    store.ingest('owner', payload)
    delivery = store.pending()['delivery_id']
    client = discord_bot.StatusBot(store, 1, 2)
    monkeypatch.setattr(client, 'is_ready', lambda: True)
    await client.on_ready()
    runs, pauses = [], []

    async def deliver():
        runs.append(1)
        if len(runs) <= 2:
            store.delivery(delivery, 'sending')
            raise KeyError('formatting bug')

    async def sleep(delay):
        pauses.append(delay)
        assert client.state() == {'discord': 'delivery_retrying', 'discord_error': 'KeyError'}
        assert outbox_status(store, delivery) == 'uncertain'
        archive = json.loads(next(store.archive_directory.glob('*.json')).read_text('utf-8'))
        assert 'sending' not in json.dumps(archive)

    monkeypatch.setattr(client, 'deliver', deliver)
    with caplog.at_level(logging.ERROR, logger='wow_status.discord_bot'):
        await client.keep_delivering(sleep=sleep)
    assert len(runs) == 3 and pauses == [30, 60]
    assert client.state() == {'discord': 'ready'} and not client.is_closed()
    assert [r.exc_info[0] for r in caplog.records if r.exc_info] == [KeyError, KeyError]


async def test_closing_marks_an_interrupted_send_uncertain_and_always_closes_discord(
        store, payload, monkeypatch):
    store.ingest('owner', payload)
    delivery = store.pending()['delivery_id']
    client = discord_bot.StatusBot(store, 1, 2)
    started = asyncio.Event()

    async def sending():
        store.delivery(delivery, 'sending')
        started.set()
        await asyncio.Event().wait()  # channel.send() still in flight

    client.worker = asyncio.create_task(sending())
    await started.wait()
    await client.close()
    assert client.is_closed() and outbox_status(store, delivery) == 'uncertain'

    other = discord_bot.StatusBot(store, 1, 2)
    other.worker = asyncio.create_task(asyncio.sleep(3600))

    def disk_full():
        raise OSError('disk full')

    monkeypatch.setattr(store, 'recover_interrupted_sends', disk_full)
    with pytest.raises(OSError):  # Reaches the session supervisor, which logs and retries.
        await other.close()
    assert other.is_closed()


async def test_bot_state_is_ready_only_while_the_gateway_is_connected(store, monkeypatch):
    client = discord_bot.StatusBot(store, 1, 2)
    assert client.state() is None  # still logging in
    monkeypatch.setattr(client, 'is_ready', lambda: True)
    await client.on_ready()
    assert client.state() == {'discord': 'ready'}
    await client.on_disconnect()
    assert client.state() == {'discord': 'reconnecting'}
    await client.on_resumed()
    assert client.state() == {'discord': 'ready'}


def free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


def fetch_health(port):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=3) as response:
        return response.status, json.load(response)


async def test_serve_keeps_ingestion_healthy_while_the_bot_keeps_failing(store, monkeypatch):
    """Regression for the deploys that failed after #33: a bot that died at login took
    the navsquad service down, so the receiver's health check never passed."""
    monkeypatch.setenv('WOW_STATUS_REVISION', 'a' * 40)
    attempts = []

    async def bot(state):
        attempts.append(1)
        raise LoginFailure()

    port = free_port()
    service = asyncio.create_task(serve(store, '127.0.0.1', port, bot))
    try:
        for _ in range(100):
            await asyncio.sleep(0.02)
            if attempts:
                break
        code, body = await asyncio.to_thread(fetch_health, port)
        assert code == 200 and body['status'] == 'ok'
        assert body['service'] == 'wow-character-status' and body['revision'] == 'a' * 40
        assert body['discord'] == 'retrying' and body['discord_error'] == 'LoginFailure'
        assert not service.done()  # The process stays up; systemd does not restart it.
    finally:
        service.cancel()
        with pytest.raises(asyncio.CancelledError):
            await service


ROOT = Path(__file__).parents[1]
REVISION = 'b' * 40


def report_module():
    spec = importlib.util.spec_from_file_location('report_discord_state',
                                                  ROOT / 'scripts/report_discord_state.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_report_reads_every_production_group_route_and_name():
    module = report_module()
    routes = module.group_routes((ROOT / 'deploy/Caddyfile.production').read_text(encoding='utf-8'))
    names = module.group_names((ROOT / 'deploy/install_release.py').read_text(encoding='utf-8'))
    assert sorted(names[port] for _, port in routes) == ['navsquad', 'ronkalot']


def test_report_waits_for_a_bot_to_settle_then_warns_only_for_broken_groups():
    module = report_module()
    routes = [('/groups/aa', '18081'), ('/groups/bb', '18082')]
    names = {'18081': 'ronkalot', '18082': 'navsquad'}
    replies = {
        '/groups/aa': iter([{'discord': 'disabled'}] * 3),
        '/groups/bb': iter([{'discord': 'starting'},
                            {'discord': 'retrying', 'discord_error': 'LoginFailure'},
                            {'discord': 'retrying', 'discord_error': 'LoginFailure'}]),
    }
    pauses = []

    def fetch(url):
        assert url.startswith('https://example.test/groups/') and url.endswith('/health')
        group = url[len('https://example.test'):-len('/health')]
        return dict(next(replies[group]), revision=REVISION)

    warnings = module.report('https://example.test/', routes, REVISION, names, fetch=fetch,
                             attempts=3, pause=5, sleep=pauses.append)
    assert warnings == ['navsquad: retrying LoginFailure']
    assert pauses == [5]  # 'retrying' can't change within the window, so it stops there.


def test_report_stops_polling_once_bots_are_ready_and_flags_unreachable_or_stale_groups():
    module = report_module()
    routes = [('/groups/aa', '18081'), ('/groups/bb', '18082')]
    ready = {'discord': 'ready', 'revision': REVISION}
    pauses = []
    assert module.report('https://example.test', routes, REVISION, fetch=lambda url: ready,
                         sleep=pauses.append) == []
    assert pauses == []

    def broken(url):
        if '/aa/' in url:
            raise TimeoutError
        return {'discord': 'ready', 'revision': 'c' * 40}

    notices = []
    assert module.report('https://example.test', routes, REVISION, fetch=broken, attempts=2,
                         sleep=pauses.append, notices=notices) == [
        'port 18081: health check failed (TimeoutError)']
    assert notices == ['port 18082 already serves another revision, so its bot was not '
                       'checked for this one']


def test_report_cannot_inject_workflow_commands_from_the_public_site(tmp_path, monkeypatch,
                                                                     capsys):
    module = report_module()
    (tmp_path / 'Caddyfile.production').write_text(
        'handle_path /groups/aa/* {\n reverse_proxy 127.0.0.1:18081\n}\n', encoding='utf-8')
    (tmp_path / 'install_release.py').write_text("GROUPS = {'ronkalot': 18081}\n",
                                                 encoding='utf-8')
    monkeypatch.setattr(module, 'DEPLOY', tmp_path)
    monkeypatch.setattr(module, 'read', lambda url: {
        'revision': REVISION, 'discord': 'retrying', 'discord_error': 'x\n::error::forged %0A'})
    monkeypatch.setattr('sys.argv', ['report', '--url', 'https://example.test',
                                     '--revision', REVISION])
    module.main()
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1 and lines[0].startswith('::warning title=Discord bot not connected::')
    assert '::error' not in lines[0] and 'ronkalot: retrying x???error??forged ?0A.' in lines[0]


def test_report_flags_replies_without_a_bot_state():
    module = report_module()
    routes = [('/groups/aa', '18081'), ('/groups/bb', '18082')]
    replies = {'/groups/aa': {'revision': REVISION}, '/groups/bb': ['not', 'an', 'object']}

    def fetch(url):
        return replies[url[len('https://example.test'):-len('/health')]]

    assert module.report('https://example.test', routes, REVISION, fetch=fetch, attempts=1) == [
        'port 18081: health check failed (KeyError)',
        'port 18082: health check failed (TypeError)']


def test_report_warns_when_it_finds_no_group_routes(tmp_path, monkeypatch, capsys):
    module = report_module()
    (tmp_path / 'Caddyfile.production').write_text('wow.example.test {\n}\n', encoding='utf-8')
    (tmp_path / 'install_release.py').write_text("GROUPS = {}\n", encoding='utf-8')
    monkeypatch.setattr(module, 'DEPLOY', tmp_path)
    monkeypatch.setattr('sys.argv', ['report', '--url', 'https://example.test',
                                     '--revision', REVISION])
    module.main()
    output = capsys.readouterr().out
    assert output.startswith('::warning ') and 'no group routes found' in output


def test_report_finds_routes_whatever_comes_before_the_upstream(tmp_path, monkeypatch, capsys):
    module = report_module()
    caddy = ('handle_path /groups/aa/* {\n  header X-Test {\n    a b\n  }\n'
             '  reverse_proxy 127.0.0.1:18081 {\n  }\n}\n'
             'handle_path /groups/bb/* {\n  respond "moved" 410\n}\n')
    assert module.group_routes(caddy) == [('/groups/aa', '18081'), ('/groups/bb', None)]
    (tmp_path / 'Caddyfile.production').write_text(caddy, encoding='utf-8')
    (tmp_path / 'install_release.py').write_text("GROUPS = {'ronkalot': 18081}\n",
                                                 encoding='utf-8')
    monkeypatch.setattr(module, 'DEPLOY', tmp_path)
    monkeypatch.setattr(module, 'read', lambda url: {'revision': REVISION, 'discord': 'ready'})
    monkeypatch.setattr('sys.argv', ['report', '--url', 'https://example.test',
                                     '--revision', REVISION])
    module.main()
    output = capsys.readouterr().out.splitlines()
    assert output == ['::warning title=Discord bot not connected::/groups/bb: no local upstream '
                      'found in deploy/Caddyfile.production, not checked. Ingestion is running; '
                      'see "Discord bot not connected" in deploy/SERVER.md.']
