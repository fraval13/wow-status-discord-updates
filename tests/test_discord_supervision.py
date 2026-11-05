"""A failing Discord bot must never take ingestion or /health down with it."""
import asyncio
import importlib.util
import json
import logging
import socket
import time
import urllib.request
import warnings
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

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
    a group's service down, so the receiver's health check never passed."""
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


def test_report_takes_routes_from_the_private_discord_secret(capsys):
    module = report_module()
    raw = json.dumps({'group-b': {'bot_token': 't', 'route': 'b' * 22},
                      'group-a': {'route': 'a' * 22}, 'group-c': {'bot_token': 't'}})
    assert module.configured_routes(raw) == (
        [('/groups/' + 'a' * 22, 'group-a'), ('/groups/' + 'b' * 22, 'group-b')], 1)
    # A route key alone admits someone to the group, so each one is masked in the log.
    assert capsys.readouterr().out.splitlines() == ['::add-mask::' + 'a' * 22, '::add-mask::' + 'b' * 22]
    assert module.configured_routes('') == ([], 0)
    for broken in ('{"group-a": ', '["x"]', '{"group-a": "x"}'):
        with pytest.raises(ValueError):
            module.configured_routes(broken)


def test_report_waits_for_a_bot_to_settle_then_warns_only_for_broken_groups():
    module = report_module()
    routes = [('/groups/aa', '18081'), ('/groups/bb', '18082')]
    names = {'18081': 'group-a', '18082': 'group-b'}
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
    assert warnings == ['group-b: retrying LoginFailure']
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


def test_report_cannot_inject_workflow_commands_from_the_public_site(monkeypatch, capsys):
    module = report_module()
    monkeypatch.setenv('WOW_STATUS_DISCORD_CONFIG', json.dumps({'group-a': {'route': 'a' * 22}}))
    monkeypatch.setattr(module, 'read', lambda url: {
        'revision': REVISION, 'discord': 'retrying', 'discord_error': 'x\n::error::forged %0A'})
    monkeypatch.setattr('sys.argv', ['report', '--url', 'https://example.test',
                                     '--revision', REVISION])
    module.main()
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == '::add-mask::' + 'a' * 22
    assert len(lines) == 2 and lines[1].startswith('::warning title=Discord bot not connected::')
    assert '::error' not in lines[1] and 'group-a: retrying x???error??forged ?0A.' in lines[1]


def test_report_flags_replies_without_a_bot_state():
    module = report_module()
    routes = [('/groups/aa', '18081'), ('/groups/bb', '18082')]
    replies = {'/groups/aa': {'revision': REVISION}, '/groups/bb': ['not', 'an', 'object']}

    def fetch(url):
        return replies[url[len('https://example.test'):-len('/health')]]

    assert module.report('https://example.test', routes, REVISION, fetch=fetch, attempts=1) == [
        'port 18081: health check failed (KeyError)',
        'port 18082: health check failed (TypeError)']


@pytest.mark.parametrize('config, expected', [
    ('', '::notice title=Discord bot not checked::no group routes in WOW_STATUS_DISCORD_CONFIG'),
    ('{"group-a": {"bot_token": "t"}}', '::notice title=Discord bot not checked::1 instance(s)'),
    ('not json', '::warning title=Discord bot not connected::WOW_STATUS_DISCORD_CONFIG is not'),
])
def test_report_without_routes_says_so_and_passes(monkeypatch, capsys, config, expected):
    module = report_module()
    monkeypatch.setenv('WOW_STATUS_DISCORD_CONFIG', config)
    monkeypatch.setattr(module, 'read', lambda url: pytest.fail('no route to check'))
    monkeypatch.setattr('sys.argv', ['report', '--url', 'https://example.test',
                                     '--revision', REVISION])
    module.main()
    output = capsys.readouterr().out
    assert output.startswith(expected) and 'not json' not in output


async def deliver_until(client, done, seconds=5):
    """Run the real delivery loop until ``done()``, then stop it; fails if it ended early."""
    task = asyncio.create_task(client.deliver())
    try:
        deadline = asyncio.get_running_loop().time() + seconds
        while not done() and asyncio.get_running_loop().time() < deadline:
            assert not task.done(), 'the delivery loop ended'
            await asyncio.sleep(0.01)
        assert done() and not task.done()
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await client.close()


def delivering_bot(store, monkeypatch, send):
    client = discord_bot.StatusBot(store, 1, 2)
    channel = SimpleNamespace(guild=SimpleNamespace(id=1), send=send)
    client.wait_until_ready = AsyncMock()
    client.get_channel = lambda _: channel
    return client, channel


async def test_one_unformattable_delivery_waits_while_the_next_is_sent(store, payload,
                                                                      monkeypatch, caplog):
    """#26: the per-delivery catch-all. Without it the loop restarts and picks the same
    delivery again, so one bad row would stop every post."""
    store.ingest('owner', payload)  # The introduction, then the level-10 announcement.
    bad, good = [row[0] for row in store.db.execute('SELECT id FROM outbox ORDER BY id')]
    original = discord_bot.announcement_message
    errors = []

    def message(store_, item, emojis):
        if item['delivery_id'] == bad:
            raise KeyError('formatting bug')
        errors.append(client.delivery_error)  # Shown on /health while it waits.
        return original(store_, item, emojis)

    monkeypatch.setattr(discord_bot, 'announcement_message', message)
    client, channel = delivering_bot(store, monkeypatch,
                                     AsyncMock(return_value=SimpleNamespace(id=789)))
    before = time.time()
    with caplog.at_level(logging.ERROR, logger='wow_status.discord_bot'):
        await deliver_until(client, lambda: outbox_status(store, good) == 'sent')
    # Never claimed, so never posted: still queued, behind the rest, and no cooldown or
    # attempt was spent on it. A fix to the formatting posts it without operator work.
    status, attempts, next_try = store.db.execute(
        'SELECT status,attempts,next_try FROM outbox WHERE id=?', (bad,)).fetchone()
    assert status == 'pending' and attempts == 0
    assert next_try >= before + discord_bot.UNEXPECTED_RETRY_SECONDS
    channel.send.assert_awaited_once()
    assert [r.exc_info[0] for r in caplog.records if r.exc_info] == [KeyError]
    assert errors == ['KeyError'] and client.delivery_error is None  # Cleared by the post.


async def test_an_unexpected_error_during_the_send_marks_it_uncertain(store, payload,
                                                                      monkeypatch):
    # aiohttp's ServerDisconnectedError is no OSError, so no other handler takes it.
    store.ingest('owner', payload)
    first = store.pending()['delivery_id']
    client, channel = delivering_bot(store, monkeypatch,
                                     AsyncMock(side_effect=aiohttp.ServerDisconnectedError()))
    await deliver_until(client, lambda: outbox_status(store, first) == 'uncertain')
    channel.send.assert_awaited_once()
    assert client.delivery_error == 'ServerDisconnectedError'


async def test_a_post_whose_record_fails_is_never_marked_unsent(store, payload, monkeypatch):
    """Once Discord has the message, only the supervisor's recovery may change its row."""
    store.ingest('owner', payload)
    first = store.pending()['delivery_id']
    client, channel = delivering_bot(store, monkeypatch,
                                     AsyncMock(return_value=SimpleNamespace(id=789)))
    original = store.deliver_many

    def deliver_many(items, status, **kwargs):
        if status == 'sent':
            raise RuntimeError('archive rebuild failed')
        return original(items, status, **kwargs)

    monkeypatch.setattr(store, 'deliver_many', deliver_many)
    try:
        with pytest.raises(RuntimeError):  # To keep_delivering, which logs and restarts.
            await client.deliver()
        assert outbox_status(store, first) == 'sending'  # Not overwritten as unsent.
        await client.recover_sends()  # What keep_delivering does before the restart.
        assert outbox_status(store, first) == 'uncertain'
    finally:
        await client.close()
    channel.send.assert_awaited_once()


class FakeReports:
    """One queued recap or status report, recording the delivery states it gets."""

    def __init__(self, broken=None):
        self.states, self.broken, self.reads = [], broken, 0

    def pending(self):
        self.reads += 1
        if self.broken:
            raise self.broken
        return {'key': 'day', 'text': 'Recap'} if not self.states else None

    def delivery(self, key, status, *args, delay=0):
        self.states.append((status, delay))

    def schedule(self):
        pass


RETRY = discord_bot.UNEXPECTED_RETRY_SECONDS


@pytest.mark.parametrize('stage,expected', [('claim', ('pending', RETRY)),
                                            ('send', ('uncertain', 0))])
@pytest.mark.parametrize('kind', ['recap', 'standings'])
async def test_one_bad_recap_or_report_does_not_stop_delivery(store, monkeypatch, caplog,
                                                              kind, stage, expected):
    """Recaps and reports are posted from the same loop, so they get the same catch-all."""
    send = AsyncMock(side_effect=RuntimeError('unexpected') if stage == 'send' else None)
    client, _ = delivering_bot(store, monkeypatch, send)
    reports = FakeReports()

    def claim(*args):
        if stage == 'claim':
            raise RuntimeError('formatting bug')
        return {'key': 'day', 'text': 'Recap'} if kind == 'recap' else [{'content': 'Report'}]

    try:
        with caplog.at_level(logging.ERROR, logger='wow_status.discord_bot'):
            if kind == 'recap':
                monkeypatch.setattr(client, 'claim_recap', claim)
                await client.deliver_recap(reports)
            else:
                monkeypatch.setattr(client, 'standings', reports)
                monkeypatch.setattr(client, 'claim_standings', claim)
                await client.deliver_standings()
    finally:
        await client.close()
    assert reports.states == [expected]
    assert [r.exc_info[0] for r in caplog.records if r.exc_info] == [RuntimeError]
    assert client.delivery_error == 'RuntimeError'


async def test_a_recap_that_cannot_render_pauses_only_that_kind(store, payload, monkeypatch,
                                                                caplog):
    """Recaps are rendered while they are read, before there is a row to mark."""
    store.ingest('owner', payload)
    client, channel = delivering_bot(store, monkeypatch,
                                     AsyncMock(return_value=SimpleNamespace(id=789)))
    broken = FakeReports(broken=KeyError('bad digest'))
    monkeypatch.setattr(client, 'recaps', broken)
    first = store.pending()['delivery_id']
    with caplog.at_level(logging.ERROR, logger='wow_status.discord_bot'):
        # The loop reads recaps before announcements, every tick while idle.
        await deliver_until(client, lambda: outbox_status(store, first) == 'sent')
    assert broken.reads == 1 and broken.states == []  # Paused, not read on every tick.
    assert [r.exc_info[0] for r in caplog.records if r.exc_info] == [KeyError]
