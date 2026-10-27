from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from wow_status.people import remember
from wow_status.weekly import WeeklyRecaps


def test_weekly_waits_for_monday_0005_and_retries_do_not_repeat(store, payload):
    remember(store, 'owner', 'Frank')
    store.ingest('owner', payload)
    zone = ZoneInfo('Europe/Oslo')
    observed = datetime.fromtimestamp(payload['exported_at'], zone).date()
    next_monday = observed + timedelta(days=7 - observed.weekday())
    weekly = WeeklyRecaps(store)
    weekly.schedule(datetime.combine(next_monday, time(0, 4), zone))
    assert weekly.pending() is None
    weekly.schedule(datetime.combine(next_monday, time(0, 5), zone))
    item = weekly.pending()
    assert item is not None
    assert 'Frank' in item['text'] and 'Weekly adventures' in item['text']
    assert 'ranking' not in item['text']
    weekly.delivery(item['key'], 'simulated')
    weekly.schedule(datetime.combine(next_monday, time(0, 6), zone))
    assert weekly.pending() is None


def test_pause_and_deletion_cancel_weekly_and_clear_managed_json(store, payload):
    store.ingest('owner', payload)
    observed = datetime.fromtimestamp(payload['exported_at'], ZoneInfo('Europe/Oslo')).date()
    week = observed - timedelta(days=observed.weekday())
    weekly = WeeklyRecaps(store)
    weekly.prepare(week)
    assert weekly.pending() is not None
    store.pause('owner')
    assert weekly.pending() is None
    store.delete('owner')
    assert store.db.execute('SELECT count(*) FROM weekly_parts').fetchone()[0] == 0
