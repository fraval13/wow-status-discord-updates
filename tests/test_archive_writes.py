"""Uploads write only what changed, and heavy work stays off the event loop (#2)."""
import asyncio
import json
import threading
import time
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer

import wow_status.archive as archive_module
import wow_status.store as store_module
from wow_status.group_routing import group_key
from wow_status.server import create_app
from wow_status.store import Store

NAME = 'Weekend Crew'
GROUP = group_key(NAME)


def payload(exported_at, events=(), **settings):
    value = {'version': 1, 'group_id': GROUP, 'group_name': NAME,
             'identity': {'guid': 'Player-1-0001', 'name': 'Thora', 'realm': 'Test Realm', 'client': 'classic-era'},
             'settings': {'enabled': True, 'introduction_confirmed': True,
                          'fields': {'level': True, 'zone': True}, 'collection': {'level': True, 'zone': True},
                          'announcements': {}, 'discord_delivery': 'events'},
             'snapshot': {'level': 10}, 'exported_at': exported_at, 'events': list(events)}
    value['settings'].update(settings)
    return value


def zones(batch, now, count=500):
    return [{'id': f'z{batch}-{i}', 'kind': 'zone', 'at': now - 2000, 'data': {'zone': 'Elwynn Forest'}}
            for i in range(count)]


def history(store, monkeypatch, batches, now):
    """``batches`` uploads of 500 zone events each, without writing archives meanwhile."""
    monkeypatch.setattr(Store, 'sync_archive', lambda self, cid: None)
    for batch in range(batches):
        store.ingest('group:a', payload(now - 1000 + batch, zones(batch, now)))
    monkeypatch.undo()
    return store.characters('group:a')[0]['id']


def count_validations(monkeypatch):
    calls = []
    original = store_module.validate
    monkeypatch.setattr(store_module, 'validate', lambda value: (calls.append(1), original(value))[1])
    return calls


# The issue's reproduction, verbatim.
def test_noop_retry_does_not_rewrite_whole_history(tmp_path, monkeypatch):
    store = Store(tmp_path / 'service.sqlite3')
    create_app(store, GROUP, NAME)
    now = int(time.time())
    monkeypatch.setattr(Store, 'sync_archive', lambda self, cid: None)
    for batch in range(20):
        events = [{'id': f'z{batch}-{i}', 'kind': 'zone', 'at': now - 2000, 'data': {'zone': 'Elwynn Forest'}}
                  for i in range(500)]
        store.ingest('group:a', payload(now - 1000 + batch, events))
    monkeypatch.undo()
    store.sync_archive(store.characters('group:a')[0]['id'])
    written = []
    original = archive_module.atomic_json
    monkeypatch.setattr(archive_module, 'atomic_json',
                        lambda path, data, **options: (original(path, data, **options), written.append(Path(path).stat().st_size)))
    assert store.ingest('group:a', payload(now - 1000 + 19))['accepted'] == 0
    assert sum(written) <= 256_000, f'retry rewrote {sum(written):,} archive bytes'


def test_noop_retry_changes_no_database_row(store):
    now = int(time.time())
    store.ingest('group:a', payload(now - 10, zones(0, now, 3)))
    before = store.characters()[0]
    changes = store.db.total_changes
    assert store.ingest('group:a', payload(now - 10, zones(0, now, 3)))['accepted'] == 0
    assert store.db.total_changes == changes
    # The upload time stays the time of the upload the archive shows.
    assert store.characters()[0]['uploaded'] == before['uploaded']


def test_real_change_still_rewrites_the_archive(store):
    now = int(time.time())
    cid = store.ingest('group:a', payload(now - 10))['character_id']
    store.ingest('group:a', payload(now - 5, zones(1, now, 2)))
    document = json.loads((store.archive_directory / f'{cid}.json').read_text(encoding='utf-8'))
    assert len(document['activity']['zones']) == 2
    assert document['profile']['last_exported_at']['unix'] == now - 5


def test_announcement_setting_change_skips_history_but_still_filters_the_queue(store, monkeypatch):
    now = int(time.time())
    level = {'id': 'level-10', 'kind': 'level', 'at': now - 20, 'data': {'level': 10}}
    events = zones(0, now, 50) + [level]
    store.ingest('group:a', payload(now - 10, events, announcements={'level': True}))
    assert store.db.execute('SELECT count(*) FROM outbox').fetchone()[0] == 1
    calls = count_validations(monkeypatch)
    # Same export, only the level interval changed: level 10 no longer qualifies.
    store.ingest('group:a', payload(now - 10, announcements={'level': True}, level_interval=20))
    assert len(calls) == 1  # the upload itself, not 51 stored events
    assert store.db.execute('SELECT count(*) FROM outbox').fetchone()[0] == 0
    assert store.db.execute('SELECT count(*) FROM events WHERE suppressed=0').fetchone()[0] == 51


def test_widening_privacy_skips_history_and_narrowing_still_scrubs(store, monkeypatch):
    now = int(time.time())
    store.ingest('group:a', payload(now - 10, zones(0, now, 20)))
    calls = count_validations(monkeypatch)
    wider = payload(now - 10)
    wider['settings']['fields']['gear'] = True
    store.ingest('group:a', wider)
    assert len(calls) == 1
    assert store.db.execute('SELECT count(*) FROM events WHERE suppressed=0').fetchone()[0] == 20
    narrower = payload(now - 10)
    narrower['settings']['fields']['zone'] = False
    store.ingest('group:a', narrower)
    assert len(calls) > 20  # every stored event and snapshot is filtered again
    assert store.db.execute('SELECT count(*) FROM events WHERE suppressed=0').fetchone()[0] == 0


def test_storage_budget_charges_archive_and_database_bytes(store):
    now = int(time.time())
    cid = store.ingest('group:a', payload(now - 10, zones(0, now)))['character_id']
    charged = store.db.execute(
        "SELECT sum(amount) FROM resource_usage WHERE scope='bytes:group:a'").fetchone()[0]
    archive = (store.archive_directory / f'{cid}.json').stat().st_size
    rows = sum(len(row['data']) + len(row['id']) for row in store.db.execute('SELECT * FROM events'))
    assert charged >= archive + rows, (charged, archive, rows)
    # A retry stores nothing, so it costs nothing.
    store.ingest('group:a', payload(now - 10, zones(0, now)))
    assert store.db.execute("SELECT sum(amount) FROM resource_usage WHERE scope='bytes:group:a'"
                            ).fetchone()[0] == charged


async def test_archives_are_rebuilt_once_at_startup(tmp_path, monkeypatch):
    path = tmp_path / 'service.sqlite3'
    first = Store(path)
    now = int(time.time())
    for guid in ('Player-1-0001', 'Player-1-0002'):
        upload = payload(now - 10)
        upload['identity']['guid'] = guid
        first.ingest('group:a', upload)
    first.close()
    syncs, written = [], []
    original_sync, original_write = Store.sync_archives, archive_module.atomic_json
    monkeypatch.setattr(Store, 'sync_archives', lambda self: (syncs.append(1), original_sync(self)))
    monkeypatch.setattr(archive_module, 'atomic_json',
                        lambda path, data, **options: (written.append(Path(path).name), original_write(path, data, **options)))
    store = Store(path)
    client = TestClient(TestServer(create_app(store, GROUP, NAME)))
    await client.start_server()
    try:
        store.flush_archives()
        assert len(syncs) == 1
        assert sorted(written) == sorted(f"{char['id']}.json" for char in store.characters())
    finally:
        await client.close()
        store.close()


async def test_store_work_runs_on_one_store_thread_while_serving(store):
    loop_thread = threading.get_ident()
    assert await store.call(threading.get_ident) == loop_thread  # inline before the service runs
    client = TestClient(TestServer(create_app(store, GROUP, NAME)))
    await client.start_server()
    try:
        first, second = await asyncio.gather(store.call(threading.get_ident),
                                             store.call(threading.get_ident))
        assert first == second != loop_thread
    finally:
        await client.close()
    assert await store.call(threading.get_ident) == loop_thread


async def test_health_stays_responsive_during_large_uploads(tmp_path, monkeypatch):
    store = Store(tmp_path / 'service.sqlite3')
    now = int(time.time())
    history(store, monkeypatch, 40, now)
    client = TestClient(TestServer(create_app(store, GROUP, NAME)))
    await client.start_server()
    try:
        response = await client.post('/v1/group-enroll', headers={'X-WoW-Group': GROUP},
                                     json={'group_id': GROUP, 'group_name': NAME})
        body = await response.json()
        headers = {'X-WoW-Group': GROUP, 'Authorization': 'Bearer ' + body['token']}
        # Give the character to the enrolled owner so the HTTP uploads land in its history.
        with store.db:
            store.db.execute('UPDATE characters SET owner=?', (body['owner'],))
        latencies, waiting = [], []

        async def poll():
            while True:
                waiting[:] = [time.perf_counter()]
                assert (await client.get('/health')).status == 200
                latencies.append(time.perf_counter() - waiting.pop())
                await asyncio.sleep(0.01)

        async def uploads():
            # 500 new events into 20,000 stored ones, then a privacy change that filters
            # all stored history again; each also rebuilds a ~13 MB archive.
            for upload in (payload(now - 900, zones('new', now)), payload(now - 899, fields={'level': True})):
                response = await client.post('/v1/upload', json=upload, headers=headers)
                assert response.status == 200, await response.text()
            await asyncio.to_thread(store.flush_archives)

        poller = asyncio.create_task(poll())
        started = time.perf_counter()
        await uploads()
        busy = time.perf_counter() - started
        # A request still unanswered counts with its wait so far.
        latencies.extend(time.perf_counter() - since for since in waiting)
        poller.cancel()
        try:
            await poller
        except asyncio.CancelledError:
            pass
        cid = store.characters()[0]['id']
        document = json.loads((store.archive_directory / f'{cid}.json').read_text(encoding='utf-8'))
        assert document['activity']['zones'] == []  # the privacy change reached the archive
        # Before #2 one such upload held the loop for its whole duration (1.4 s here). Now
        # only the GIL is shared: about 0.08 s at worst locally, against 2.4 s of work.
        assert max(latencies) < min(0.5, busy / 4), (max(latencies), busy)
        assert len(latencies) >= 5
    finally:
        await client.close()
        store.close()


def test_drop_wins_over_a_rebuild_that_read_the_database_first(store, monkeypatch):
    now = int(time.time())
    cid = store.ingest('owner', payload(now - 10))['character_id']
    archive = store.archive_directory / f'{cid}.json'
    assert archive.exists()
    reading, release = threading.Event(), threading.Event()
    original = archive_module.character_document

    def slow(store, cid):
        document = original(store, cid)
        reading.set()
        release.wait(5)
        return document

    monkeypatch.setattr(archive_module, 'character_document', slow)
    store.start_background()
    try:
        store.sync_archive(cid)
        assert reading.wait(5)
        store.delete('owner')  # drops the archive while the rebuild holds old data
        release.set()
        store.flush_archives()
        assert not archive.exists()
    finally:
        store.stop_background()


def test_marks_made_during_a_rebuild_are_written_once_more(store, monkeypatch):
    now = int(time.time())
    cid = store.ingest('owner', payload(now - 10))['character_id']
    reading, release = threading.Event(), threading.Event()
    builds = []
    original = archive_module.character_document

    def slow(store, cid):
        builds.append(cid)
        if len(builds) == 1:
            reading.set()
            release.wait(5)
        return original(store, cid)

    monkeypatch.setattr(archive_module, 'character_document', slow)
    store.start_background()
    try:
        store.sync_archive(cid)
        assert reading.wait(5)
        store.ingest('owner', payload(now - 5, zones(0, now, 1)))
        for _ in range(3):
            store.sync_archive(cid)
        release.set()
        store.flush_archives()
    finally:
        store.stop_background()
    assert builds == [cid, cid]  # four later marks, one more rebuild
    document = json.loads((store.archive_directory / f'{cid}.json').read_text(encoding='utf-8'))
    assert len(document['activity']['zones']) == 1


def test_a_failed_rebuild_does_not_stop_the_archive_thread(store, monkeypatch, caplog):
    now = int(time.time())
    cid = store.ingest('owner', payload(now - 10))['character_id']
    original = archive_module.character_document
    failures = []

    def flaky(store, cid):
        if not failures:
            failures.append(cid)
            raise OSError('disk full')
        return original(store, cid)

    monkeypatch.setattr(archive_module, 'character_document', flaky)
    store.start_background()
    try:
        store.sync_archive(cid)
        store.flush_archives()
        store.ingest('owner', payload(now - 5, zones(0, now, 1)))
        store.flush_archives()
    finally:
        store.stop_background()
    assert 'Character archive could not be written (OSError)' in caplog.text
    document = json.loads((store.archive_directory / f'{cid}.json').read_text(encoding='utf-8'))
    assert len(document['activity']['zones']) == 1


def test_new_events_in_an_unchanged_export_still_move_the_upload_time(store, monkeypatch):
    now = int(time.time())
    store.ingest('group:a', payload(now - 10, zones(0, now, 1)))
    monkeypatch.setattr('wow_status.store.time.time', lambda: now + 60)
    store.ingest('group:a', payload(now - 10, zones(1, now, 1)))  # e.g. a later batch part
    assert store.characters()[0]['uploaded'] == now + 60


def test_a_rebuild_reads_one_database_snapshot(store, monkeypatch):
    cid = store.ingest('owner', payload(int(time.time()) - 10))['character_id']
    seen = []
    original = archive_module.character_document

    def check(store, cid):
        seen.append(store.db.in_transaction)
        return original(store, cid)

    monkeypatch.setattr(archive_module, 'character_document', check)
    store.start_background()
    try:
        store.sync_archive(cid)
        store.flush_archives()
    finally:
        store.stop_background()
    assert seen == [True]


async def test_queued_store_work_still_runs_when_its_caller_is_cancelled(store):
    store.start_background()
    try:
        busy, release, done = threading.Event(), threading.Event(), []
        blocker = asyncio.ensure_future(store.call(lambda: (busy.set(), release.wait(5))))
        await asyncio.to_thread(busy.wait, 5)
        queued = asyncio.ensure_future(store.call(done.append, 'recorded'))
        await asyncio.sleep(0)
        queued.cancel()  # e.g. the bot shutting down right after posting
        release.set()
        await blocker
    finally:
        await asyncio.to_thread(store.stop_background)
    assert done == ['recorded']


def other_character(exported_at, events=()):
    value = payload(exported_at, events)
    value['identity'] = dict(value['identity'], guid='Player-1-0002', name='Brann')
    return value


def archived(store, cid):
    return json.loads((store.archive_directory / f'{cid}.json').read_text(encoding='utf-8'))


def block_first_rebuild(monkeypatch):
    """Hold the first rebuild after it read the database, until ``release`` is set."""
    reading, release, builds = threading.Event(), threading.Event(), []
    original = archive_module.character_document

    def slow(store, cid):
        document = original(store, cid)
        builds.append(cid)
        if len(builds) == 1:
            reading.set()
            release.wait(5)
        return document

    monkeypatch.setattr(archive_module, 'character_document', slow)
    return reading, release, builds


def test_withdrawn_data_leaves_the_archive_before_the_change_is_answered(store, monkeypatch):
    now = int(time.time())
    cid = store.ingest('owner', payload(now - 10, zones(0, now, 2)))['character_id']
    busy = store.ingest('owner', other_character(now - 10))['character_id']
    reading, release, _ = block_first_rebuild(monkeypatch)
    store.start_background()
    try:
        store.sync_archive(busy)  # the archive thread is busy with another character
        assert reading.wait(5)
        store.ingest('owner', payload(now - 5, zones(1, now, 1)))
        assert len(archived(store, cid)['activity']['zones']) == 2  # an ordinary change waits
        narrower = payload(now - 4)
        narrower['settings']['fields']['zone'] = False
        store.ingest('owner', narrower)
        assert archived(store, cid)['activity']['zones'] == []
        store.pause('owner', cid)
        assert archived(store, cid)['profile']['current'] == {}
        release.set()
        store.flush_archives()
    finally:
        release.set()
        store.stop_background()
    assert archived(store, cid)['profile']['current'] == {}


def test_an_older_rebuild_never_overwrites_a_newer_one(store, monkeypatch):
    now = int(time.time())
    cid = store.ingest('owner', payload(now - 10))['character_id']
    reading, release, builds = block_first_rebuild(monkeypatch)
    written = []
    original = archive_module.atomic_json
    monkeypatch.setattr(archive_module, 'atomic_json',
                        lambda path, data, **options: (written.append(data['profile']['current']),
                                            original(path, data, **options)))
    store.start_background()
    try:
        store.sync_archive(cid)
        assert reading.wait(5)  # it read the snapshot before the pause
        store.pause('owner', cid)
        release.set()
        store.flush_archives()
    finally:
        release.set()
        store.stop_background()
    assert builds == [cid, cid] and written == [{}]
    assert archived(store, cid)['profile']['current'] == {}


def test_a_rebuild_is_written_even_when_a_newer_mark_waits(store, monkeypatch):
    now = int(time.time())
    cid = store.ingest('owner', payload(now - 10))['character_id']
    reading, release, builds = block_first_rebuild(monkeypatch)
    written = []
    original = archive_module.atomic_json
    monkeypatch.setattr(archive_module, 'atomic_json',
                        lambda path, data, **options: (written.append(len(data['activity']['zones'])),
                                            original(path, data, **options)))
    store.start_background()
    try:
        store.sync_archive(cid)
        assert reading.wait(5)
        store.ingest('owner', payload(now - 5, zones(0, now, 1)))
        release.set()
        store.flush_archives()
    finally:
        release.set()
        store.stop_background()
    assert written == [0, 1]


def test_stopping_waits_only_for_the_rebuild_in_progress(store, monkeypatch):
    now = int(time.time())
    cid = store.ingest('owner', payload(now - 10))['character_id']
    other = store.ingest('owner', other_character(now - 10))['character_id']
    reading, release, builds = block_first_rebuild(monkeypatch)
    store.start_background()
    stopper = threading.Thread(target=store.stop_background)
    try:
        store.sync_archive(cid)
        assert reading.wait(5)
        store.sync_archive(other)
        stopper.start()
        deadline = time.monotonic() + 5
        while not store.archives._stopping and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        release.set()
        stopper.join(5)
    assert not stopper.is_alive()
    assert builds == [cid]  # the next startup rebuilds the other one
    store.sync_archive(other)  # with the thread gone, at once
    assert builds == [cid, other]


async def test_stopping_from_the_loop_finishes_queued_calls_first(store):
    store.start_background()
    busy, release, ran = threading.Event(), threading.Event(), []

    def record(name):
        ran.append((name, threading.current_thread().name))

    first = asyncio.ensure_future(store.call(lambda: (busy.set(), release.wait(5), record('first'))))
    await asyncio.to_thread(busy.wait, 5)
    stopping = asyncio.ensure_future(store.stop_background_from_loop())
    await asyncio.sleep(0)
    # A call made while the stop waits queues behind the running one, never beside it.
    second = asyncio.ensure_future(store.call(record, 'second'))
    await asyncio.sleep(0.05)
    assert ran == []
    release.set()
    await asyncio.gather(first, second, stopping)
    await store.call(record, 'after')
    assert [name for name, _ in ran] == ['first', 'second', 'after']
    assert all(thread.startswith('wow-status-store') for _, thread in ran[:2])
    assert ran[2][1] == threading.current_thread().name


async def test_a_bad_token_costs_one_store_call(store, monkeypatch):
    monkeypatch.setattr(store_module.limits, 'AUTH_FAILURES_PER_IP_MINUTE', 2)
    monkeypatch.setattr('wow_status.store.time.time', lambda: 1_800_000_030.0)
    client = TestClient(TestServer(create_app(store, GROUP, NAME)))
    await client.start_server()
    calls = []
    original = store.call
    monkeypatch.setattr(store, 'call', lambda *args, **kwargs: (calls.append(1),
                                                                 original(*args, **kwargs))[1])
    try:
        headers = {'X-WoW-Group': GROUP, 'Authorization': 'Bearer wrong'}
        statuses = [(await client.post('/v1/upload', json={}, headers=headers)).status
                    for _ in range(3)]
    finally:
        await client.close()
    assert statuses == [401, 401, 429]
    assert len(calls) == 3


def test_archives_are_written_in_batches_with_the_same_text(tmp_path, monkeypatch):
    import wow_status.companion as companion
    data = {'name': 'Þóra', 'events': [{'id': i, 'zone': 'Elwynn Forest'} for i in range(200)]}
    expected = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
    monkeypatch.setattr(companion, 'WRITE_BATCH', 64)
    companion.atomic_json(tmp_path / 'small.json', data)
    monkeypatch.undo()
    companion.atomic_json(tmp_path / 'large.json', data)
    for name in ('small.json', 'large.json'):
        assert (tmp_path / name).read_text(encoding='utf-8') == expected


def test_archives_reach_the_disk_before_they_replace_the_old_file(tmp_path, monkeypatch):
    # #26: without fsync before the rename, a crash could leave an empty archive or
    # credentials file in place of the old one.
    import os

    import wow_status.companion as companion
    data = {'name': 'Þóra', 'events': [{'id': i} for i in range(50)]}
    calls, fsync, replace = [], os.fsync, os.replace

    def recording_fsync(fd):
        calls.append(('fsync', os.fstat(fd).st_size))
        fsync(fd)

    def recording_replace(source, target):
        calls.append(('replace', Path(source).name, Path(target).name))
        replace(source, target)

    monkeypatch.setattr(companion.os, 'fsync', recording_fsync)
    monkeypatch.setattr(companion.os, 'replace', recording_replace)
    companion.atomic_json(tmp_path / 'credentials.json', data)
    # The whole text (with Windows line endings there) is synced, then renamed.
    size = (tmp_path / 'credentials.json').stat().st_size
    assert calls == [('fsync', size), ('replace', 'credentials.tmp', 'credentials.json')]


def test_service_archives_skip_the_sync_because_startup_rebuilds_them(store, monkeypatch):
    import wow_status.companion as companion
    synced = []
    monkeypatch.setattr(companion.os, 'fsync', lambda fd: synced.append(fd))
    cid = store.ingest('owner', payload(int(time.time()) - 10))['character_id']
    assert archived(store, cid) and synced == []


def test_a_failed_rewrite_of_withdrawn_data_is_tried_again(store, monkeypatch):
    now = int(time.time())
    cid = store.ingest('owner', payload(now - 10, zones(0, now, 2)))['character_id']
    monkeypatch.setattr(archive_module, 'RETRY_SECONDS', 0.05)
    original = archive_module.atomic_json
    failures = []

    def disk_full(path, data, **options):
        if not failures:
            failures.append(path)
            raise OSError('disk full')
        original(path, data, **options)

    monkeypatch.setattr(archive_module, 'atomic_json', disk_full)
    narrower = payload(now - 5)
    narrower['settings']['fields']['zone'] = False
    store.start_background()
    try:
        try:
            store.ingest('owner', narrower)
        except OSError:
            pass  # committed, but the archive still holds the zones
        assert failures and len(archived(store, cid)['activity']['zones']) == 2
        # The companion's retry changes nothing, so only the archive thread can fix the file.
        assert store.ingest('owner', narrower)['accepted'] == 0
        deadline = time.monotonic() + 5
        while archived(store, cid)['activity']['zones'] and time.monotonic() < deadline:
            time.sleep(0.02)
    finally:
        store.stop_background()
    assert archived(store, cid)['activity']['zones'] == []
