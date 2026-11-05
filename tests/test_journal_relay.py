"""Companion shared-journal relay and dated peer checkpoints (#49)."""
import asyncio
from datetime import datetime, timedelta
from datetime import time as day_time
from zoneinfo import ZoneInfo

from test_group_status import yesterday_payload
from test_http import NAME, group_app, started

from wow_status import journal_relay
from wow_status.companion import journal_entries
from wow_status.group_client import GroupUploader
from wow_status.group_status import GroupStatusReports, midnight, state

ZONE = ZoneInfo('Europe/Oslo')


def at(day, hour):
    return int(datetime.combine(day, day_time(hour, 0), ZONE).timestamp())


def upload(store, owner, entries, client='classic-era'):
    return journal_relay.ingest(store, owner, {'group_id': 'g', 'client': client, 'entries': entries})


def test_entries_are_validated_and_deduplicated_whoever_uploads_them(store):
    day = datetime.now(ZONE).date() - timedelta(days=1)
    good = {'id': 'Mira-TestRealm:1793-4', 'sender': 'Mira-TestRealm', 'kind': 'level', 'at': at(day, 20), 'level': 31}
    death = {'id': 'x2', 'sender': 'Mira-Azjol-Nerub', 'kind': 'death', 'at': at(day, 21), 'text': 'Total deaths: 6'}
    bad = [dict(good, id='bad id'), dict(good, sender='Mira'), dict(good, sender='Mi|ra-Realm'), dict(good, level=99),
           dict(good, at=5), dict(good, kind='zone'), dict(good, level='31'), 'nonsense']
    assert upload(store, 'one', [good, death, *bad]) == {'status': 'accepted', 'entries': 2, 'new': 2}
    # Another companion uploading the same entries adds nothing; times and IDs are kept.
    assert upload(store, 'two', [dict(good, at=at(day, 22)), death])['new'] == 0
    rows = store.db.execute('SELECT id,at,uploader,deaths FROM journal_entries ORDER BY id').fetchall()
    assert [(r['id'], r['at'], r['uploader'], r['deaths']) for r in rows] == [
        ('Mira-TestRealm:1793-4', at(day, 20), 'one', None), ('x2', at(day, 21), 'one', 6)]
    # A death entry without a recorded total is kept but gives no total.
    upload(store, 'one', [dict(death, id='x3', text='Died')])
    assert store.db.execute("SELECT deaths FROM journal_entries WHERE id='x3'").fetchone()[0] is None


def test_report_includes_characters_seen_only_through_the_journal(store, payload):
    day = datetime.now(ZONE).date() - timedelta(days=1)
    cutoff = midnight(day + timedelta(days=1))
    store.ingest('owner', yesterday_payload(payload, day, level=24, deaths=7))
    upload(store, 'owner', [
        {'id': 'm1', 'sender': 'Mira-TestRealm', 'kind': 'level', 'at': at(day, 10), 'level': 30},
        {'id': 'm2', 'sender': 'Mira-TestRealm', 'kind': 'level', 'at': at(day, 12), 'level': 31},
        {'id': 'm3', 'sender': 'Mira-TestRealm', 'kind': 'death', 'at': at(day, 13), 'text': 'Total deaths: 4'},
        # After the cutoff: never part of this report.
        {'id': 'm4', 'sender': 'Mira-TestRealm', 'kind': 'level', 'at': cutoff + 60, 'level': 40},
        # A dated peer checkpoint for the directly uploading character raises its level.
        {'id': 't1', 'sender': 'Thora-TestRealm', 'kind': 'level', 'at': at(day, 22), 'level': 25}])
    assert state(store, store.character_id(payload['identity']), cutoff)['level'] == 25
    standings = GroupStatusReports(store)
    standings.prepare(datetime.fromtimestamp(cutoff + 120, ZONE))
    rows = {row['identity']['name']: row for row in standings.pending()['rows']}
    assert set(rows) == {'Thora', 'Mira'}
    assert rows['Mira']['level'] == 31 and rows['Mira']['deaths'] == 4
    assert rows['Mira']['source'] == 'shared_journal' and rows['Mira']['identity']['realm'] == 'TestRealm'
    assert rows['Thora']['level'] == 25 and rows['Thora']['deaths'] == 7


def test_journal_alone_triggers_a_report_and_paused_characters_stay_out(store, payload):
    day = datetime.now(ZONE).date() - timedelta(days=1)
    cutoff = midnight(day + timedelta(days=1))
    upload(store, 'owner', [{'id': 'm1', 'sender': 'Mira-TestRealm', 'kind': 'level', 'at': at(day, 10), 'level': 30}])
    # Thora uploads directly but has paused: peers' entries about her are withheld too.
    store.ingest('owner', yesterday_payload(payload, day, level=24))
    store.pause('owner')
    upload(store, 'other', [{'id': 't1', 'sender': 'Thora-TestRealm', 'kind': 'level', 'at': at(day, 11), 'level': 26}])
    standings = GroupStatusReports(store)
    standings.prepare(datetime.fromtimestamp(cutoff + 120, ZONE))
    rows = standings.pending()['rows']
    assert [row['identity']['name'] for row in rows] == ['Mira']


def test_deleting_an_installation_removes_what_it_uploaded(store):
    upload(store, 'gone', [{'id': 'a', 'sender': 'Mira-TestRealm', 'kind': 'level', 'at': 1_700_000_000, 'level': 3}])
    upload(store, 'kept', [{'id': 'b', 'sender': 'Mira-TestRealm', 'kind': 'level', 'at': 1_700_000_100, 'level': 4}])
    store.delete('gone')
    assert [row[0] for row in store.db.execute('SELECT id FROM journal_entries')] == ['b']


async def test_journal_route_needs_group_credentials_and_the_right_group(store):
    from wow_status.group_routing import group_key
    group = group_key(NAME)
    client = await started(group_app(store))
    try:
        response = await client.post('/v1/group-enroll', headers={'X-WoW-Group': group},
                                     json={'group_id': group, 'group_name': NAME})
        auth = {'X-WoW-Group': group, 'Authorization': 'Bearer ' + (await response.json())['token']}
        body = {'group_id': group, 'client': 'classic-era',
                'entries': [{'id': 'a', 'sender': 'Mira-TestRealm', 'kind': 'level', 'at': 1_700_000_000, 'level': 3}]}
        assert (await client.post('/v1/journal', json=body, headers={'X-WoW-Group': group})).status == 401
        assert (await client.post('/v1/journal', json=dict(body, group_id='other'), headers=auth)).status == 400
        assert (await client.post('/v1/journal', json=dict(body, client='mars'), headers=auth)).status == 400
        response = await client.post('/v1/journal', json=body, headers=auth)
        assert response.status == 200 and (await response.json())['new'] == 1
    finally:
        await client.close()


def test_companion_selects_only_entries_shared_with_that_group():
    db = {'journal': {'entries': {
        1: {'id': 'a', 'sender': 'Mira-TestRealm', 'kind': 'level', 'level': 5, 'at': 10,
            'client': 'classic-era', 'groups': {'g': True}, 'text': 'Reached level 5!'},
        2: {'id': 'b', 'sender': 'Mira-TestRealm', 'kind': 'death', 'at': 20, 'client': 'classic-era',
            'groups': {'g': True}, 'text': 'Total deaths: 2'},
        3: {'id': 'c', 'sender': 'Mira-TestRealm', 'kind': 'level', 'level': 6, 'at': 30,
            'client': 'classic-era', 'groups': {'other': True}},
        4: {'id': 'd', 'sender': 'Mira-TestRealm', 'kind': 'zone', 'at': 40, 'client': 'classic-era', 'groups': {'g': True}},
        5: {'id': 'e', 'sender': 'Me-TestRealm', 'kind': 'level', 'level': 7, 'at': 50, 'client': 'classic-era',
            'groups': {}, 'owner': 'Player-1'},
        6: {'id': 'f', 'sender': 'Mira-TestRealm', 'kind': 'level', 'level': 8, 'at': 60, 'client': 'retail',
            'groups': {'g': True}},
        7: {'id': 'g', 'sender': 'Old-TestRealm', 'kind': 'level', 'level': 9, 'at': 70, 'client': 'classic-era',
            'groups': {'g': True}, 'legacy': True}}}}
    assert journal_entries(db, 'g', 'classic-era') == [
        {'id': 'b', 'sender': 'Mira-TestRealm', 'kind': 'death', 'at': 20, 'text': 'Total deaths: 2'},
        {'id': 'a', 'sender': 'Mira-TestRealm', 'kind': 'level', 'at': 10, 'level': 5}]


class _Response:
    def __init__(self, status):
        self.status, self.headers = status, {}

    async def read(self):
        return b''

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Session:
    def __init__(self, status):
        self.status, self.posts = status, []

    def post(self, url, json, headers, allow_redirects):
        self.posts.append((url, json))
        return _Response(self.status)


def uploader(tmp_path, status, token='secret'):
    route = {'url': 'https://example.test/groups/g', 'label': 'G'}
    if token:
        route['token'] = token
    session = _Session(status)
    upload = GroupUploader({'groups': {'g': route}}, tmp_path / 'credentials.json', {},
                           tmp_path / 'state.json', session, lambda **kw: None)
    return upload, session


DB = {'journal': {'entries': [{'id': 'a', 'sender': 'Mira-TestRealm', 'kind': 'level', 'level': 5, 'at': 10,
                               'client': 'classic-era', 'groups': {'g': True}}]}}
PAYLOADS = [{'settings': {'enabled': True}, '_groups': {'g': {}}, 'identity': {'client': 'classic-era'}}]


def test_companion_uploads_once_and_tolerates_services_without_the_relay(tmp_path):
    upload, session = uploader(tmp_path, 200)
    assert asyncio.run(upload.upload_journal(DB, PAYLOADS)) is True
    assert asyncio.run(upload.upload_journal(DB, PAYLOADS)) is True
    assert len(session.posts) == 1 and session.posts[0][0].endswith('/v1/journal')
    assert session.posts[0][1]['entries'][0]['id'] == 'a'
    old, session = uploader(tmp_path, 404)
    assert asyncio.run(old.upload_journal(DB, PAYLOADS)) is True
    failing, session = uploader(tmp_path, 500)
    assert asyncio.run(failing.upload_journal(DB, PAYLOADS)) is False


def test_companion_never_enrolls_or_uploads_for_opted_out_characters(tmp_path):
    upload, session = uploader(tmp_path, 200, token=None)
    assert asyncio.run(upload.upload_journal(DB, PAYLOADS)) is True and session.posts == []
    upload, session = uploader(tmp_path, 200)
    opted_out = [dict(PAYLOADS[0], _discord_opt_out=True)]
    assert asyncio.run(upload.upload_journal(DB, opted_out)) is True and session.posts == []
