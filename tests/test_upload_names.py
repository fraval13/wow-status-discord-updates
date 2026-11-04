"""A group upload's player name is stored only when the whole upload is accepted (#10)."""
import json

import pytest
from aiohttp.test_utils import TestClient, TestServer

from wow_status import limits
from wow_status.group_routing import group_key
from wow_status.server import create_app
from wow_status.store import Conflict, Store

NAME = 'Weekend Crew'
GROUP = group_key(NAME)


def make_store(tmp_path):
    return Store(tmp_path / 'group.sqlite3')


async def started(store):
    client = TestClient(TestServer(create_app(store, GROUP, NAME)))
    await client.start_server()
    return client


async def enroll(client, player):
    response = await client.post('/v1/group-enroll', headers={'X-WoW-Group': GROUP},
                                 json={'group_id': GROUP, 'group_name': NAME, 'player_name': player})
    assert response.status == 200
    body = await response.json()
    return body['owner'], {'X-WoW-Group': GROUP, 'Authorization': 'Bearer ' + body['token']}


def group_payload(payload, guid='Player-123-0001', **changes):
    value = json.loads(json.dumps(payload))
    value['identity']['guid'] = guid
    value.update(group_id=GROUP, group_name=NAME, **changes)
    return value


def display_name(store, owner):
    row = store.db.execute('SELECT display_name,source FROM people WHERE owner=?', (owner,)).fetchone()
    return row['display_name'], row['source']


def archived_name(store, cid):
    document = json.loads((store.archive_directory / f'{cid}.json').read_text(encoding='utf-8'))
    return document['character']['friend']['display_name']


@pytest.fixture
async def group(tmp_path):
    store = make_store(tmp_path)
    client = await started(store)
    try:
        yield store, client
    finally:
        await client.close()
        store.close()


async def test_rejected_upload_does_not_persist_player_name(group, payload):
    store, client = group
    owner, headers = await enroll(client, 'Thora')
    invalid = group_payload(payload, version=2, player_name='Impersonated')
    assert (await client.post('/v1/upload', json=invalid, headers=headers)).status == 400
    assert display_name(store, owner) == ('Thora', 'addon')


async def test_conflicting_upload_does_not_persist_player_name_or_rewrite_archives(group, payload):
    store, client = group
    owner, headers = await enroll(client, 'Thora')
    accepted = await client.post('/v1/upload', json=group_payload(payload, player_name='Thora'),
                                 headers=headers)
    assert accepted.status == 200
    cid = (await accepted.json())['character_id']
    archive = store.archive_directory / f'{cid}.json'
    before = archive.read_bytes()
    stale = group_payload(payload, player_name='Impersonated', exported_at=payload['exported_at'] - 60)
    assert (await client.post('/v1/upload', json=stale, headers=headers)).status == 409
    assert display_name(store, owner) == ('Thora', 'addon')
    assert archive.read_bytes() == before


async def test_accepted_upload_renames_owner_on_every_archived_character(group, payload):
    store, client = group
    owner, headers = await enroll(client, 'Thora')
    first = await client.post('/v1/upload', json=group_payload(payload, player_name='Thora'),
                              headers=headers)
    first_cid = (await first.json())['character_id']
    renamed = group_payload(payload, guid='Player-123-0002', player_name='Brann')
    second = await client.post('/v1/upload', json=renamed, headers=headers)
    assert second.status == 200
    second_cid = (await second.json())['character_id']
    assert display_name(store, owner) == ('Brann', 'addon')
    assert archived_name(store, first_cid) == 'Brann'
    assert archived_name(store, second_cid) == 'Brann'


async def test_blank_player_name_falls_back_to_friend_label(group, payload):
    store, client = group
    owner, headers = await enroll(client, 'Thora')
    response = await client.post('/v1/upload', json=group_payload(payload, player_name=''),
                                 headers=headers)
    assert response.status == 200
    assert display_name(store, owner) == ('Friend ' + owner[-6:], 'unavailable')


def test_store_conflict_does_not_write_label(store, payload):
    store.ingest('group:owner', payload, name=('Thora', 'addon'))
    other_owner = dict(payload, exported_at=payload['exported_at'] + 1)
    with pytest.raises(Conflict):
        store.ingest('group:intruder', other_owner, name=('Intruder', 'addon'))
    assert store.db.execute("SELECT 1 FROM people WHERE owner='group:intruder'").fetchone() is None
    assert display_name(store, 'group:owner') == ('Thora', 'addon')


async def test_upload_that_stores_nothing_does_not_rename_owner(group, payload):
    store, client = group
    owner, headers = await enroll(client, 'Thora')
    empty = group_payload(payload, player_name='Impersonated')
    empty['settings']['enabled'] = False
    response = await client.post('/v1/upload', json=empty, headers=headers)
    assert response.status == 200 and (await response.json())['accepted'] == 0
    assert display_name(store, owner) == ('Thora', 'addon')


async def test_rename_with_role_change_writes_each_archive_once(group, payload, monkeypatch):
    store, client = group
    owner, headers = await enroll(client, 'Thora')
    for guid in ('Player-123-0001', 'Player-123-0002'):
        upload = group_payload(payload, guid=guid, player_name='Thora')
        assert (await client.post('/v1/upload', json=upload, headers=headers)).status == 200
    writes = []
    original = store.sync_archive
    monkeypatch.setattr(store, 'sync_archive', lambda cid: (writes.append(cid), original(cid)))
    renamed = group_payload(payload, player_name='Brann')
    renamed['settings']['character_role'] = 'main'
    assert (await client.post('/v1/upload', json=renamed, headers=headers)).status == 200
    assert sorted(writes) == sorted(char['id'] for char in store.characters(owner))
    assert store.db.execute("SELECT COUNT(*) FROM character_labels WHERE role='main'").fetchone()[0] == 1


async def test_existing_character_rename_rewrites_sibling_archives(group, payload):
    store, client = group
    owner, headers = await enroll(client, 'Thora')
    cids = []
    for guid in ('Player-123-0001', 'Player-123-0002'):
        upload = group_payload(payload, guid=guid, player_name='Thora')
        cids.append((await (await client.post('/v1/upload', json=upload, headers=headers)).json())
                    ['character_id'])
    # Same character and role as before: only the label changes.
    again = group_payload(payload, player_name='Brann', exported_at=payload['exported_at'] + 1)
    assert (await client.post('/v1/upload', json=again, headers=headers)).status == 200
    assert [archived_name(store, cid) for cid in cids] == ['Brann', 'Brann']


async def test_rejection_after_label_write_rolls_it_back(group, payload, monkeypatch):
    store, client = group
    owner, headers = await enroll(client, 'Thora')

    charge = limits.charge

    def exhausted(db, entries, now):
        if not any(scope.startswith('bytes:') for scope, *_ in entries):
            return charge(db, entries, now)  # request budgets
        # The upload's storage budget is charged last, after the label was written.
        assert db.execute('SELECT display_name FROM people WHERE owner=?',
                          (owner,)).fetchone()[0] == 'Impersonated'
        raise limits.Limited(60)

    monkeypatch.setattr('wow_status.store.limits.charge', exhausted)
    upload = group_payload(payload, player_name='Impersonated')
    assert (await client.post('/v1/upload', json=upload, headers=headers)).status == 429
    assert display_name(store, owner) == ('Thora', 'addon')


async def test_new_alt_rewrites_only_its_own_archive(group, payload, monkeypatch):
    store, client = group
    owner, headers = await enroll(client, 'Thora')
    upload = group_payload(payload, player_name='Thora')
    assert (await client.post('/v1/upload', json=upload, headers=headers)).status == 200
    writes = []
    original = store.sync_archive
    monkeypatch.setattr(store, 'sync_archive', lambda cid: (writes.append(cid), original(cid)))
    alt = group_payload(payload, guid='Player-123-0002', player_name='Thora')
    response = await client.post('/v1/upload', json=alt, headers=headers)
    assert writes == [(await response.json())['character_id']]
