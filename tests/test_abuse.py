"""Abuse controls must not reject plausible gameplay or discard deferred updates."""
import copy
import json

import pytest
from aiohttp.test_utils import TestClient, TestServer

from wow_status import limits
from wow_status.formatting import safe
from wow_status.schema import ValidationError, validate
from wow_status.server import create_app
from wow_status.store import Store


@pytest.mark.parametrize('client', ['classic-era', 'forever'])
def test_cap_is_server_controlled_everywhere(payload, client):
    payload['identity']['client'] = client
    payload['events'][1]['data'].update(level=10, maximum=True)
    assert validate(payload)['events'][1]['data']['maximum'] is False
    payload['events'][1]['data'].update(level=60, maximum=False)
    assert validate(payload)['events'][1]['data']['maximum'] is True
    payload['events'][1]['data']['level'] = 61
    with pytest.raises(ValidationError):
        validate(payload)
    payload['events'] = []
    payload['snapshot']['level'] = 61
    with pytest.raises(ValidationError):
        validate(payload)
    payload['snapshot']['level'] = 60
    payload['tracking'] = {'points': [{'kind': 'level', 'level': 61,
        'at': payload['exported_at'], 'segment': 'a'}]}
    with pytest.raises(ValidationError):
        validate(payload)


def test_duplicate_level_claim_with_new_id_does_not_inflate_history(store, payload):
    store.ingest('owner', payload)
    payload['events'][1]['id'] = 'another-id'
    assert store.ingest('owner', payload)['accepted'] == 0
    assert store.db.execute("SELECT count(*) FROM events WHERE kind='level'").fetchone()[0] == 1
    assert store.db.execute('SELECT count(*) FROM outbox').fetchone()[0] == 2


def test_repeated_levels_stay_deduplicated_after_restart(tmp_path, payload):
    path = tmp_path / 'db.sqlite3'
    with_store = Store(path)
    with_store.ingest('owner', payload)
    with_store.close()
    reopened = Store(path)
    try:
        payload['events'][1]['id'] = 'new-install-event'
        assert reopened.ingest('owner', payload)['accepted'] == 0
    finally:
        reopened.close()


def test_fast_skipped_out_of_order_and_existing_high_levels_are_allowed(store, payload):
    payload['snapshot']['level'] = 60
    payload['events'] = [{'id': 'e' + str(level), 'kind': 'level',
        'at': payload['exported_at'] - age, 'data': {'level': level}}
        for level, age in [(60, 0), (10, 2000), (35, 0), (36, 0)]]
    assert store.ingest('owner', payload)['accepted'] == 4
    assert store.db.execute("SELECT count(*) FROM events WHERE kind='level'").fetchone()[0] == 4


def test_growth_limit_rolls_back_and_retry_costs_no_extra_budget(store, payload, monkeypatch):
    monkeypatch.setattr(limits, 'NEW_EVENTS_PER_OWNER_DAY', 2)
    store.ingest('owner', payload)
    assert store.ingest('owner', payload)['accepted'] == 0
    extra = copy.deepcopy(payload)
    extra['events'] = [{'id': 'new', 'kind': 'level', 'at': payload['exported_at'], 'data': {'level': 20}}]
    with pytest.raises(limits.Limited):
        store.ingest('owner', extra)
    assert store.db.execute('SELECT count(*) FROM events').fetchone()[0] == 2
    # Existing data is retained and another installation has an independent owner budget.
    extra['identity']['guid'] = 'Player-other'
    assert store.ingest('other', extra)['accepted'] == 1
    payload['settings']['enabled'] = False
    store.ingest('owner', payload)
    assert store.characters('owner')[0]['snapshot'] == {}


def test_post_cooldowns_preserve_queue_and_allow_other_characters(store, payload, monkeypatch):
    store.ingest('owner', payload)
    second = copy.deepcopy(payload)
    second['identity']['guid'] = 'Player-other'
    second['identity']['name'] = 'Other'
    store.ingest('other', second)
    first = store.pending(ready_only=True)
    now = first['uploaded']
    monkeypatch.setattr('wow_status.store.time.time', lambda: now)
    store.delivery(first['delivery_id'], 'sending')
    store.delivery(first['delivery_id'], 'sent')
    assert store.pending(ready_only=True) is None
    assert store.db.execute("SELECT count(*) FROM outbox WHERE status='pending'").fetchone()[0] == 3
    monkeypatch.setattr('wow_status.store.time.time', lambda: now + limits.GROUP_POST_SECONDS + 1)
    assert store.pending(ready_only=True)['identity']['name'] == 'Other'
    monkeypatch.setattr('wow_status.store.time.time', lambda: now + limits.CHARACTER_POST_SECONDS + 1)
    assert store.pending(ready_only=True)['id'] == first['id']


async def test_upload_rate_limits_are_per_owner_and_retryable(store, payload, monkeypatch):
    monkeypatch.setattr(limits, 'UPLOADS_PER_MINUTE', 1)
    tokens = [store.redeem(store.create_link(owner)) for owner in ('a', 'b')]
    client = TestClient(TestServer(create_app(store)))
    await client.start_server()
    try:
        headers = {'Authorization': 'Bearer ' + tokens[0]}
        assert (await client.post('/v1/upload', json=payload, headers=headers)).status == 200
        response = await client.post('/v1/upload', json=payload, headers=headers)
        assert response.status == 429 and int(response.headers['Retry-After']) > 0
        other = copy.deepcopy(payload)
        other['identity']['guid'] = 'Player-b'
        assert (await client.post('/v1/upload', json=other,
            headers={'Authorization': 'Bearer ' + tokens[1]})).status == 200
    finally:
        await client.close()


async def test_proxy_header_only_trusted_when_explicit_and_local(store, monkeypatch):
    from wow_status.group_routing import group_key
    monkeypatch.setattr(limits, 'ENROLLMENTS_PER_IP_HOUR', 1)
    group = group_key('navsquad')
    client = TestClient(TestServer(create_app(store, group, 'navsquad', trust_proxy=True)))
    await client.start_server()
    try:
        body = {'group_id': group, 'group_name': 'navsquad'}
        headers = {'X-WoW-Group': group, 'X-WoW-Client-IP': '192.0.2.1'}
        assert (await client.post('/v1/group-enroll', json=body, headers=headers)).status == 200
        assert (await client.post('/v1/group-enroll', json=body, headers=headers)).status == 429
        headers['X-WoW-Client-IP'] = '192.0.2.2'
        assert (await client.post('/v1/group-enroll', json=body, headers=headers)).status == 200
    finally:
        await client.close()
    client = TestClient(TestServer(create_app(store, group, 'navsquad')))
    await client.start_server()
    try:
        assert (await client.post('/v1/group-enroll', json=body, headers=headers)).status == 200
        headers['X-WoW-Client-IP'] = '192.0.2.3'
        assert (await client.post('/v1/group-enroll', json=body, headers=headers)).status == 429
    finally:
        await client.close()


def test_user_text_cannot_create_mentions_or_clickable_urls():
    output = safe('@everyone [click](https://evil.example) discord.gg/abc www.evil.example')
    assert '@everyone' not in output
    assert 'https://' not in output and 'discord.gg/' not in output and 'www.' not in output


def test_post_queue_rotates_between_owners(store, payload, monkeypatch):
    now = payload['exported_at']
    monkeypatch.setattr('wow_status.store.time.time', lambda: now)
    for i in range(4):
        item = copy.deepcopy(payload)
        item['identity']['guid'] = f'Player-spam-{i}'
        store.ingest('busy-owner', item)
    other = copy.deepcopy(payload)
    other['identity']['guid'] = 'Player-friend'
    store.ingest('friend', other)
    first = store.pending(ready_only=True)
    store.delivery(first['delivery_id'], 'sending')
    store.delivery(first['delivery_id'], 'sent')
    monkeypatch.setattr('wow_status.store.time.time', lambda: now + limits.GROUP_POST_SECONDS + 1)
    assert store.pending(ready_only=True)['owner'] == 'friend'


async def test_group_client_honours_retry_after_without_acknowledging_data(tmp_path, payload):
    from wow_status.group_client import GroupUploader

    class Response:
        status = 429
        headers = {'Retry-After': '600'}
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    class Session:
        calls = 0
        def post(self, *args, **kwargs):
            self.calls += 1
            return Response()

    route = {'url': 'https://example.com', 'token': 'private-token'}
    session = Session()
    config = {'groups': {'test': route}}
    uploader = GroupUploader(config, tmp_path / 'credentials.json', {}, tmp_path / 'state.json',
                             session, lambda **kw: None)
    assert await uploader.send('test', route, payload, 'fingerprint') is False
    assert await uploader.send('test', route, payload, 'fingerprint') is False
    assert session.calls == 1
    assert 'fingerprint' not in uploader.cache
    assert json.loads((tmp_path / 'credentials.json').read_text(encoding='utf-8'))['groups']['test']['retry_upload_at'] > payload['exported_at']
