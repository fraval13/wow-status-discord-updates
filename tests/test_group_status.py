from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from wow_status import output
from wow_status.group_status import GroupStatusReports, midnight, state
from wow_status.output import daily_status_message

ZONE = ZoneInfo('Europe/Oslo')


def yesterday_payload(payload, day, level=10, deaths=None):
    """One export recorded during the reported day, before the midnight cutoff."""
    recorded = int(datetime.combine(day, time(21, 0), ZONE).timestamp())
    payload = dict(payload, exported_at=recorded)
    payload['settings'] = dict(
        payload['settings'],
        fields=dict(payload['settings']['fields'], deaths=deaths is not None),
        collection=dict(payload['settings']['announcements'], death=deaths is not None),
        announcements=dict(payload['settings']['announcements'], death=deaths is not None))
    payload['snapshot'] = dict(payload['snapshot'], level=level)
    if deaths is not None:
        payload['snapshot']['deaths'] = deaths
        payload['snapshot']['deaths_since'] = recorded - 86400
    payload['events'] = [{'id': f'level-{level}', 'kind': 'level', 'at': recorded,
                          'data': {'level': level}}]
    return payload


def test_report_uses_values_observed_before_the_midnight_cutoff(store, payload):
    day = datetime.now(ZONE).date() - timedelta(days=1)
    cutoff = midnight(day + timedelta(days=1))
    store.ingest('owner', yesterday_payload(payload, day, level=24, deaths=7))
    # Today's progress must not leak into yesterday's standings.
    today = dict(yesterday_payload(payload, day, level=31, deaths=9),
                 exported_at=cutoff + 3600)
    today['events'] = [{'id': 'level-31', 'kind': 'level', 'at': cutoff + 3600,
                        'data': {'level': 31}}]
    store.ingest('owner', today)
    observed = state(store, store.character_id(payload['identity']), cutoff)
    assert observed['level'] == 24
    assert observed['deaths'] == 7


def test_unchanged_standings_are_not_reported_again(store, payload):
    day = datetime.now(ZONE).date() - timedelta(days=1)
    cutoff = midnight(day + timedelta(days=1))
    store.ingest('owner', yesterday_payload(payload, day, level=24, deaths=7))
    standings = GroupStatusReports(store)
    standings.prepare(datetime.fromtimestamp(cutoff + 60, ZONE))
    item = standings.pending()
    assert item is not None
    standings.delivery(item['key'], 'sent', ['1'])
    # A later day with no new observations must not repeat the same standings.
    standings.prepare(datetime.fromtimestamp(cutoff + 86400 + 60, ZONE))
    assert standings.pending() is None
    assert store.db.execute('SELECT count(*) FROM status_reports').fetchone()[0] == 1


def test_new_observations_after_a_sent_report_allow_the_next_one(store, payload):
    first_day = datetime.now(ZONE).date() - timedelta(days=2)
    second_day = first_day + timedelta(days=1)
    first_cutoff = midnight(second_day)
    store.ingest('owner', yesterday_payload(payload, first_day, level=24, deaths=7))
    standings = GroupStatusReports(store)
    standings.prepare(datetime.fromtimestamp(first_cutoff + 60, ZONE))
    first = standings.pending()
    assert first is not None
    standings.delivery(first['key'], 'sent', ['1'])
    store.ingest('owner', yesterday_payload(payload, second_day, level=27, deaths=8))
    standings.prepare(datetime.fromtimestamp(midnight(second_day + timedelta(days=1)) + 60, ZONE))
    item = standings.pending()
    assert item is not None
    assert item['rows'][0]['level'] == 27


def test_retries_and_restarts_do_not_create_a_second_post(store, payload):
    day = datetime.now(ZONE).date() - timedelta(days=1)
    cutoff = midnight(day + timedelta(days=1))
    store.ingest('owner', yesterday_payload(payload, day, level=24, deaths=7))
    standings = GroupStatusReports(store)
    standings.prepare(datetime.fromtimestamp(cutoff + 60, ZONE))
    standings.prepare(datetime.fromtimestamp(cutoff + 120, ZONE))
    assert store.db.execute('SELECT count(*) FROM status_reports').fetchone()[0] == 1
    item = standings.pending()
    standings.delivery(item['key'], 'sent', ['1'])
    assert standings.pending() is None


def test_withdrawn_consent_removes_a_character_from_an_unsent_report(store, payload):
    day = datetime.now(ZONE).date() - timedelta(days=1)
    cutoff = midnight(day + timedelta(days=1))
    store.ingest('owner', yesterday_payload(payload, day, level=24, deaths=7))
    standings = GroupStatusReports(store)
    standings.prepare(datetime.fromtimestamp(cutoff + 60, ZONE))
    assert standings.pending() is not None
    store.pause('owner')
    assert standings.pending() is None


def test_unknown_values_sort_after_known_ones_and_are_never_zero(store, payload, clone):
    day = datetime.now(ZONE).date() - timedelta(days=1)
    cutoff = midnight(day + timedelta(days=1))
    store.ingest('owner', yesterday_payload(payload, day, level=24, deaths=7))
    other = clone(payload)
    other['identity'] = dict(other['identity'], guid='Player-123-0002', name='Brunna')
    store.ingest('friend', yesterday_payload(other, day, level=29, deaths=None))
    standings = GroupStatusReports(store)
    standings.prepare(datetime.fromtimestamp(cutoff + 60, ZONE))
    rows = standings.pending()['rows']
    pages = daily_status_message(rows, cutoff, 'ronkalot')
    deaths = next(embed for embed in pages[0]['embeds'] if 'Recorded deaths' in embed.title)
    assert 'deaths not recorded' in deaths.description
    assert '0 deaths' not in deaths.description
    lines = deaths.description.splitlines()
    assert 'Thora' in lines[0] and 'Brunna' in lines[1]
    # Every row carries both values, so an unknown count stays visible in both lists.
    levels = next(embed for embed in pages[0]['embeds'] if 'Levels' in embed.title)
    assert 'deaths not recorded' in levels.description


def test_every_character_survives_continuation_into_further_embeds(store, payload, clone):
    day = datetime.now(ZONE).date() - timedelta(days=1)
    cutoff = midnight(day + timedelta(days=1))
    for index in range(60):
        other = clone(payload)
        other['identity'] = dict(other['identity'], guid=f'Player-9-{index:04d}',
                                 name=f'Hero{index:02d}')
        store.ingest(f'owner-{index}', yesterday_payload(other, day, level=index % 59 + 2,
                                                          deaths=index))
    standings = GroupStatusReports(store)
    standings.prepare(datetime.fromtimestamp(cutoff + 60, ZONE))
    rows = standings.pending()['rows']
    assert len(rows) == 60
    pages = daily_status_message(rows, cutoff, 'ronkalot')
    text = '\n'.join(embed.description or '' for page in pages for embed in page['embeds'])
    for index in range(60):
        assert f'Hero{index:02d}' in text
    assert all(len(page['embeds']) <= 10 for page in pages)
    assert all(len(embed.description or '') <= 4096 for page in pages for embed in page['embeds'])


def test_repeated_names_are_disambiguated_by_realm_and_edition(store, payload, clone):
    day = datetime.now(ZONE).date() - timedelta(days=1)
    cutoff = midnight(day + timedelta(days=1))
    store.ingest('owner', yesterday_payload(payload, day, level=24, deaths=7))
    twin = clone(payload)
    twin['identity'] = dict(twin['identity'], guid='Player-7-0002', realm='Other Realm')
    store.ingest('friend', yesterday_payload(twin, day, level=20, deaths=1))
    standings = GroupStatusReports(store)
    standings.prepare(datetime.fromtimestamp(cutoff + 60, ZONE))
    rows = standings.pending()['rows']
    pages = daily_status_message(rows, cutoff, 'ronkalot')
    levels = next(embed for embed in pages[0]['embeds'] if 'Levels' in embed.title)
    assert 'Other Realm' in levels.description
    assert 'Test Realm' in levels.description


def test_no_report_before_the_cutoff_has_passed(store, payload):
    day = datetime.now(ZONE).date() - timedelta(days=1)
    cutoff = midnight(day + timedelta(days=1))
    store.ingest('owner', yesterday_payload(payload, day, level=24, deaths=7))
    standings = GroupStatusReports(store)
    standings.prepare(datetime.fromtimestamp(cutoff - 600, ZONE))
    assert standings.pending() is None


def test_stale_observations_are_marked_rather_than_presented_as_current(store, payload):
    day = datetime.now(ZONE).date() - timedelta(days=1)
    cutoff = midnight(day + timedelta(days=1))
    store.ingest('owner', yesterday_payload(payload, day - timedelta(days=9), level=12, deaths=3))
    row = state(store, store.character_id(payload['identity']), cutoff)
    assert row['stale'] is True
    pages = daily_status_message([row], cutoff, 'ronkalot')
    levels = next(embed for embed in pages[0]['embeds'] if 'Levels' in embed.title)
    assert 'last seen' in levels.description


def test_deaths_from_events_update_the_cumulative_total(store, payload):
    day = datetime.now(ZONE).date() - timedelta(days=1)
    cutoff = midnight(day + timedelta(days=1))
    base = yesterday_payload(payload, day, level=24, deaths=7)
    recorded = int(datetime.combine(day, time(20, 30), ZONE).timestamp())
    base['events'] = base['events'] + [{'id': 'death-9', 'kind': 'death', 'at': recorded,
                                        'data': {'total_deaths': 9}}]
    store.ingest('owner', base)
    row = state(store, store.character_id(payload['identity']), cutoff)
    assert row['deaths'] == 9


def test_deleted_characters_drop_their_frozen_report_rows(store, payload):
    day = datetime.now(ZONE).date() - timedelta(days=1)
    cutoff = midnight(day + timedelta(days=1))
    store.ingest('owner', yesterday_payload(payload, day, level=24, deaths=7))
    standings = GroupStatusReports(store)
    standings.prepare(datetime.fromtimestamp(cutoff + 60, ZONE))
    assert store.db.execute('SELECT count(*) FROM status_report_rows').fetchone()[0] == 1
    store.delete('owner')
    assert store.db.execute('SELECT count(*) FROM status_report_rows').fetchone()[0] == 0
    assert standings.pending() is None


def test_names_are_escaped_and_cut_without_a_dangling_escape(store, payload, clone):
    """Truncating escaped text must not leave a lone backslash (see the clip helper)."""
    day = datetime.now(ZONE).date() - timedelta(days=1)
    cutoff = midnight(day + timedelta(days=1))
    hostile = clone(payload)
    hostile['identity'] = dict(hostile['identity'], guid='Player-5-0001', name='**x_' + '*' * 90)
    store.ingest('owner', yesterday_payload(hostile, day, level=24, deaths=7))
    standings = GroupStatusReports(store)
    standings.prepare(datetime.fromtimestamp(cutoff + 60, ZONE))
    rows = standings.pending()['rows']
    pages = daily_status_message(rows, cutoff, 'ronkalot')
    for page in pages:
        for embed in page['embeds']:
            text = embed.description or ''
            assert (len(text) - len(text.rstrip('\\'))) % 2 == 0, 'dangling escape'
            assert len(text) <= 4096
    levels = next(embed for embed in pages[0]['embeds'] if 'Levels' in embed.title)
    assert '\\*\\*x\\_' in levels.description


def test_report_dates_avoid_platform_specific_strftime():
    """%-d and %#d are platform extensions: one raises ValueError on the other OS."""
    source = Path(output.__file__).read_text(encoding='utf-8')
    rendered = source.split('def daily_status_message')[1]
    assert '%-' not in rendered and '%#' not in rendered


def test_header_states_the_cutoff_without_a_padded_day(store, payload):
    day = datetime.now(ZONE).date() - timedelta(days=1)
    cutoff = midnight(day + timedelta(days=1))
    store.ingest('owner', yesterday_payload(payload, day, level=24, deaths=7))
    standings = GroupStatusReports(store)
    standings.prepare(datetime.fromtimestamp(cutoff + 60, ZONE))
    rows = standings.pending()['rows']
    header = daily_status_message(rows, cutoff, 'ronkalot')[0]['embeds'][0]
    moment = datetime.fromtimestamp(cutoff, ZONE)
    assert f'{moment.day} {moment.strftime("%B %Y")}' in header.description
    assert 'Europe/Oslo' in header.description
