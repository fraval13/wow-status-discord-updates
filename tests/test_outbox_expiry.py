"""Exports that never complete stop costing every delivery tick (#26)."""
import json
import time

from wow_status.store import INCOMPLETE_BATCH_SECONDS, Store

WEEK_AND_A_DAY = INCOMPLETE_BATCH_SECONDS + 86400


def summary(payload, clone, batch, part, total, level):
    p = clone(payload)
    p['settings']['discord_delivery'] = 'summary'
    p.update(upload_batch=batch, upload_part=part, upload_parts=total)
    p['events'] = [{'id': f'level-{level}', 'kind': 'level', 'at': p['exported_at'],
                    'data': {'level': level}}]
    return p


def statuses(store):
    return [row[0] for row in store.db.execute('SELECT status FROM outbox ORDER BY id')]


def receipts(store, batch):
    return store.db.execute('SELECT count(*) FROM upload_receipts WHERE batch=?',
                            (batch,)).fetchone()[0]


def age_receipts(store, seconds):
    with store.db:
        store.db.execute('UPDATE upload_receipts SET received=received-?', (seconds,))


def test_an_export_that_never_completes_expires_after_a_week(store, payload, clone):
    # The issue's case: part 1 of 10,000 arrives and the rest never does.
    store.ingest('owner', summary(payload, clone, 'a' * 64, 1, 10000, 11))
    queued = statuses(store)
    assert queued and set(queued) == {'pending'} and store.pending() is None
    now = time.time()
    assert store.expire_incomplete_batches(now + INCOMPLETE_BATCH_SECONDS - 60) == 0
    assert set(statuses(store)) == {'pending'}
    assert store.expire_incomplete_batches(now + INCOMPLETE_BATCH_SECONDS + 60) == len(queued)
    assert set(statuses(store)) == {'expired'} and store.pending() is None
    # Only the announcement expires: history and the archive keep the event.
    assert store.db.execute("SELECT count(*) FROM events WHERE id='level-11'").fetchone()[0] == 1
    archive = json.loads(next(store.archive_directory.glob('*.json')).read_text('utf-8'))
    assert '"expired"' in json.dumps(archive) and '"pending"' not in json.dumps(archive)


def test_a_batch_whose_parts_still_arrive_is_kept_and_completes(store, payload, clone):
    store.ingest('owner', summary(payload, clone, 'a' * 64, 1, 2, 11))
    age_receipts(store, WEEK_AND_A_DAY)  # Part 1 is old, but part 2 has just arrived.
    store.ingest('owner', summary(payload, clone, 'a' * 64, 2, 2, 12))
    assert store.expire_incomplete_batches() == 0
    items = store.summary_items(store.pending())
    assert {item['event_id'] for item in items} >= {'level-11', 'level-12'}


def test_complete_batches_and_per_event_deliveries_never_expire(store, payload, clone):
    store.ingest('owner', payload)  # Per-event delivery: no batch at all.
    other = summary(payload, clone, 'b' * 64, 1, 1, 11)
    other['identity']['guid'] = 'Player-other'
    store.ingest('owner', other)
    age_receipts(store, WEEK_AND_A_DAY)
    assert store.expire_incomplete_batches() == 0
    assert set(statuses(store)) == {'pending'}


def test_the_delivery_loop_expires_stale_batches(store, payload, clone):
    from wow_status.discord_bot import StatusBot
    store.ingest('owner', summary(payload, clone, 'a' * 64, 1, 10000, 11))
    age_receipts(store, WEEK_AND_A_DAY)
    StatusBot(store, 1, 2).schedule()  # Runs every 30 s in the delivery loop.
    assert set(statuses(store)) == {'expired'}


def test_a_batch_resumed_after_its_rows_expired_still_completes(store, payload, clone):
    store.ingest('owner', summary(payload, clone, 'a' * 64, 1, 3, 11))
    age_receipts(store, WEEK_AND_A_DAY)
    assert store.expire_incomplete_batches() > 0
    # Another member's upload runs the receipt cleanup: expired rows keep theirs.
    other = summary(payload, clone, 'b' * 64, 1, 1, 30)
    other['identity']['guid'] = 'Player-other'
    store.ingest('other-owner', other)
    assert receipts(store, 'a' * 64) == 1
    store.deliver_many(store.summary_items(store.pending()), 'sent')
    # The client comes back and sends the parts it still had: part 1 is not resent.
    for part in (2, 3):
        store.ingest('owner', summary(payload, clone, 'a' * 64, part, 3, 10 + part))
    items = store.summary_items(store.pending())
    assert {item['event_id'] for item in items} >= {'level-11', 'level-12', 'level-13'}
    assert 'expired' not in statuses(store)


def test_a_newer_export_brings_expired_announcements_back(store, payload, clone):
    store.ingest('owner', summary(payload, clone, 'a' * 64, 1, 3, 11))
    age_receipts(store, WEEK_AND_A_DAY)
    assert store.expire_incomplete_batches() > 0
    later = summary(payload, clone, 'b' * 64, 1, 1, 12)
    later['exported_at'] += 1
    store.ingest('owner', later)
    # Posted with the newer export, as they were before expiry existed.
    items = store.summary_items(store.pending())
    assert {item['event_id'] for item in items} >= {'level-11', 'level-12'}
    store.deliver_many(items, 'sent')
    # Nothing links to the stalled batch now, so the next upload drops its receipt.
    newest = summary(payload, clone, 'c' * 64, 1, 1, 13)
    newest['exported_at'] += 2
    store.ingest('owner', newest)
    assert receipts(store, 'a' * 64) == 0 and receipts(store, 'c' * 64) == 1


def test_retrying_an_expired_announcement_posts_it_on_its_own(store, payload, clone):
    store.ingest('owner', summary(payload, clone, 'a' * 64, 1, 3, 11))
    age_receipts(store, WEEK_AND_A_DAY)
    store.expire_incomplete_batches()
    row = store.db.execute("SELECT o.id FROM outbox o WHERE o.event_id='level-11'").fetchone()[0]
    store.delivery(row, 'pending')  # wow-status resolve <id> retry
    assert store.expire_incomplete_batches() == 0  # Not set aside again.
    item = store.pending()
    assert item['delivery_id'] == row and store.summary_items(item) == [item]


def test_community_filters_also_discard_expired_announcements(store, payload, clone):
    store.ingest('owner', summary(payload, clone, 'a' * 64, 1, 3, 11))
    age_receipts(store, WEEK_AND_A_DAY)
    store.expire_incomplete_batches()
    store.set_community_setting('immediate_mode', 'daily_only')
    assert set(statuses(store)) == {'discarded'}


def steps(store, ready_only):
    """SQLite VM steps pending() takes: wall-clock timing is too noisy for CI."""
    count = [0]

    def tick():
        count[0] += 1
        return 0
    store.db.set_progress_handler(tick, 10)
    try:
        item = store.pending(ready_only=ready_only)
    finally:
        store.db.set_progress_handler(None, 10)
    return count[0], item['event_id']


def backlog(store, payload, clone, sent, stale):
    """``sent`` delivered rows and ``stale`` rows of exports stuck at part 1 of 10,000,
    all queued before one deliverable announcement."""
    quiet = clone(payload)
    quiet['events'] = []
    cid = store.ingest('owner', quiet)['character_id']
    now = int(time.time())
    total = sent + stale
    with store.db:
        store.db.executemany(
            'INSERT INTO events(character,id,kind,at,received,data) VALUES(?,?,?,?,?,?)',
            [(cid, f'old-{i}', 'level', now, now, '{"level": 5}') for i in range(total)])
        store.db.executemany(
            'INSERT INTO outbox(character,event_id,status) VALUES(?,?,?)',
            [(cid, f'old-{i}', 'sent' if i < sent else 'pending') for i in range(total)])
        stuck = store.db.execute("SELECT id FROM outbox WHERE status='pending'").fetchall()
        store.db.executemany('INSERT INTO outbox_batches VALUES(?,?,?)',
                             [(row[0], 'owner', f'batch-{row[0]}') for row in stuck])
        store.db.executemany('INSERT INTO upload_receipts VALUES(?,?,?,?,?)',
                             [('owner', f'batch-{row[0]}', 1, 10000, now - WEEK_AND_A_DAY)
                              for row in stuck])
    deliverable = clone(payload)
    deliverable['exported_at'] += 1
    deliverable['events'] = [{'id': 'level-20', 'kind': 'level', 'at': now,
                              'data': {'level': 20}}]
    store.ingest('owner', deliverable)


def test_pending_work_does_not_grow_with_sent_or_expired_rows(store, payload, clone, tmp_path):
    backlog(store, payload, clone, 0, 0)
    baseline = {ready: steps(store, ready) for ready in (False, True)}
    assert baseline[False][1] == baseline[True][1] == 'level-20'
    large = Store(tmp_path / 'large.sqlite3')
    try:
        backlog(large, payload, clone, 3000, 3000)
        # The issue's growth: every stuck row is checked on every 2 s tick.
        assert steps(large, True)[0] > 10 * baseline[True][0] + 100
        assert large.expire_incomplete_batches() == 3000
        for ready in (False, True):
            count, event = steps(large, ready)
            assert event == 'level-20'
            # Sent rows are skipped by the index, expired ones by their status.
            assert count <= 2 * baseline[ready][0] + 20, (ready, count, baseline[ready])
    finally:
        large.close()
