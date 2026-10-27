import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from wow_status.archive import character_document, export_characters, timestamp
from wow_status.daily import DailyRecaps, report, window


def test_json_groups_level_timestamps_and_explicit_oslo_zone(store, payload, tmp_path):
    result = store.ingest('owner', payload)
    cid = result['character_id']
    document = character_document(store, cid)
    assert document['timezone'] == 'Europe/Oslo'
    level = document['progression']['level_history'][0]
    assert level['data']['level'] == 10
    assert level['recorded_at']['timezone'] == 'Europe/Oslo'
    assert datetime.fromisoformat(level['recorded_at']['iso']).tzinfo is not None
    assert 'PRIVATE' not in json.dumps(document)
    managed = store.archive_directory / f'{cid}.json'
    assert json.loads(managed.read_text(encoding='utf-8')) == document
    assert export_characters(store, tmp_path / 'export') == 1
    assert (tmp_path / 'export/manifest.json').exists()


def test_all_collected_levels_are_archived_without_immediate_posts(store, payload):
    payload['settings']['collection'] = {'level': True}
    payload['settings']['announcements'] = {'level': False}
    payload['events'][1]['data']['level'] = 11
    store.ingest('owner', payload)
    assert store.pending() is None
    history = character_document(store, store.characters()[0]['id'])
    assert history['progression']['level_history'][0]['data']['level'] == 11


def test_history_deduplicates_exports_and_scrubs_disabled_fields(store, payload):
    store.ingest('owner', payload)
    store.ingest('owner', payload)
    assert store.db.execute('SELECT count(*) FROM snapshots').fetchone()[0] == 1
    payload['settings']['fields']['level'] = False
    store.ingest('owner', payload)
    document = character_document(store, store.characters()[0]['id'])
    assert document['progression']['level_history'] == []
    assert all('level' not in s['fields'] for s in document['profile']['snapshot_history'])
    store.delete('owner')
    assert list(store.archive_directory.glob('*.json')) == []


def test_norwegian_timezone_tracks_summer_and_winter():
    assert timestamp(0)['timezone'] == 'Europe/Oslo'
    start, end = window('2026-03-29')
    assert end - start == 23 * 3600
    start, end = window('2026-10-25')
    assert end - start == 25 * 3600


def test_daily_recap_schedule_is_0005_and_deduplicated(store, payload):
    store.ingest('owner', payload)
    zone = ZoneInfo('Europe/Oslo')
    observed = datetime.fromtimestamp(payload['exported_at'], zone).date()
    tomorrow = observed + timedelta(days=1)
    recaps = DailyRecaps(store)
    recaps.schedule(datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 4, tzinfo=zone))
    assert recaps.pending() is None
    recaps.schedule(datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 5, tzinfo=zone))
    item = recaps.pending()
    assert item is not None
    assert item['report']['day'] == observed.isoformat()
    assert item['report']['event_counts']['level'] == 1
    recaps.delivery(item['key'], 'simulated')
    recaps.schedule(datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 6, tzinfo=zone))
    assert recaps.pending() is None


def test_no_events_character_is_included_and_pause_cancels(store, payload):
    payload['events'] = []
    store.ingest('owner', payload)
    zone = ZoneInfo('Europe/Oslo')
    day = datetime.fromtimestamp(payload['exported_at'], zone).date()
    recap = report(store, store.characters()[0]['id'], day)
    assert recap['event_counts'] == {}
    recaps = DailyRecaps(store)
    recaps.prepare(day)
    assert recaps.pending() is not None
    store.pause('owner')
    assert recaps.pending() is None


def test_late_upload_appears_only_in_assigned_upload_day(store, payload, monkeypatch):
    # Freeze the receiving time at Oslo noon; old event dates stay intact in JSON.
    zone = ZoneInfo('Europe/Oslo')
    today = datetime.now(zone).replace(hour=12, minute=0, second=0, microsecond=0)
    old = today - timedelta(days=2)
    payload['exported_at'] = int(old.timestamp())
    for event in payload['events']:
        event['at'] = int(old.timestamp())
    monkeypatch.setattr('wow_status.store.time.time', lambda: today.timestamp())
    store.ingest('owner', payload)
    cid = store.characters()[0]['id']
    assert report(store, cid, old.date(), int(today.timestamp()))['event_counts'] == {}
    received = report(store, cid, today.date(), int(today.timestamp()))
    assert received['event_counts']['level'] == 1
    assert all(e['late_upload'] for e in received['events'])


def test_recap_rebuild_respects_privacy_and_json_removes_summary_data(store, payload):
    store.ingest('owner', payload)
    cid = store.characters()[0]['id']
    day = datetime.fromtimestamp(payload['exported_at'], ZoneInfo('Europe/Oslo')).date()
    recaps = DailyRecaps(store)
    recaps.prepare(day)
    assert recaps.pending()['report']['event_counts']['level'] == 1
    payload['settings']['fields']['level'] = False
    store.ingest('owner', payload)
    recap = recaps.pending()['report']
    assert 'level' not in recap['profile_at_day_end']
    assert 'level' not in recap['event_counts']
    document = character_document(store, cid)
    assert 'level' not in document['daily_recaps'][0]['summary']['event_counts']


def test_item_references_link_loot_and_equipment_without_losing_original_link():
    from wow_status.archive import event_document, fields_document
    link = '|cff00ff00|Hitem:123:456:0:0|h[Test Sword]|h|r'
    loot = event_document({'item': link, 'quality': 4})
    gear = fields_document({'gear': {'16': link}})
    assert loot['item'] == link
    assert loot['item_reference']['item_id'] == gear['gear']['16']['item_id'] == 123
    assert loot['item_reference']['enchant_id'] == 456
