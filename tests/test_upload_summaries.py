import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from wow_status.discord_bot import StatusBot
from wow_status.output import upload_summary


def summary(payload, clone, part, total):
    p = clone(payload)
    p['settings']['discord_delivery'] = 'summary'
    p.update(upload_batch='a' * 64, upload_part=part, upload_parts=total)
    p['events'] = [{'id': f'level-{part}', 'kind': 'level', 'at': p['exported_at'],
                    'data': {'level': part + 1}}]
    return p


async def test_complete_export_produces_one_summary_and_retries_are_deduplicated(store, payload, clone):
    batches = [summary(payload, clone, i, 3) for i in [1, 2, 3]]
    for p in batches[:2]:
        store.ingest('owner', p)
        assert store.pending() is None
    store.ingest('owner', batches[0])  # duplicate first chunk cannot complete the batch
    assert store.pending() is None
    store.ingest('owner', batches[2])
    items = store.summary_items(store.pending())
    assert len(items) == 3
    assert '3 level-ups' in upload_summary(items)['content']
    bot = StatusBot(store, 123, 456)
    channel = SimpleNamespace(guild=SimpleNamespace(id=123),
                              send=AsyncMock(return_value=SimpleNamespace(id=789)))
    bot.wait_until_ready = AsyncMock()
    bot.get_channel = lambda _: channel
    task = asyncio.create_task(bot.deliver())
    try:
        await asyncio.sleep(0.05)
        channel.send.assert_awaited_once()
        assert '3 level-ups' in channel.send.call_args.kwargs['content']
        assert store.pending() is None
        assert store.db.execute("SELECT count(*) FROM outbox WHERE status='sent'").fetchone()[0] == 3
        for p in batches:
            store.ingest('owner', p)
        assert store.pending() is None
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await bot.close()


def test_multiple_characters_share_one_account_summary_and_snapshot_only_is_silent(store, payload, clone):
    first, second = [summary(payload, clone, i, 2) for i in [1, 2]]
    second['identity']['guid'] = 'Player-other'
    second['identity']['name'] = 'Other'
    store.ingest('owner', first)
    store.ingest('owner', second)
    items = store.summary_items(store.pending())
    text = upload_summary(items)['content']
    assert 'Thora' in text and 'Other' in text
    store.deliver_many(items, 'sent')
    newer = clone(first)
    newer.update(upload_batch='b' * 64, upload_part=1, upload_parts=1)
    newer['events'] = []
    store.ingest('owner', newer)
    assert store.pending() is None


async def test_privacy_change_during_channel_fetch_cancels_summary(store, payload, clone):
    store.ingest('owner', summary(payload, clone, 1, 1))
    bot = StatusBot(store, 123, 456)
    channel = SimpleNamespace(guild=SimpleNamespace(id=123), send=AsyncMock())
    bot.wait_until_ready = AsyncMock()
    bot.get_channel = lambda _: None

    async def fetch(_):
        store.pause('owner')
        return channel

    bot.fetch_channel = fetch
    task = asyncio.create_task(bot.deliver())
    try:
        await asyncio.sleep(0.05)
        channel.send.assert_not_awaited()
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await bot.close()


def test_new_export_absorbs_old_incomplete_batch(store, payload, clone):
    store.ingest('owner', summary(payload, clone, 1, 3))
    assert store.pending() is None
    new = summary(payload, clone, 1, 1)
    new['upload_batch'] = 'b' * 64
    new['events'][0]['id'] = 'level-later'
    new['events'][0]['data']['level'] = 5
    store.ingest('owner', new)
    assert len(store.summary_items(store.pending())) == 2


def test_summary_marks_whole_batch_uncertain_together(store, payload, clone):
    store.ingest('owner', summary(payload, clone, 1, 1))
    items = store.summary_items(store.pending())
    store.deliver_many(items, 'sending')
    store.deliver_many(items, 'uncertain')
    assert store.pending() is None
    assert store.db.execute("SELECT count(*) FROM outbox WHERE status='uncertain'").fetchone()[0] == 1
