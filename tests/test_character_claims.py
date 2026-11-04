"""A character's real owner can recover it with its claim secret; others get 409 (#11)."""
import json
import sqlite3
import sys

import pytest
from aiohttp.test_utils import TestClient, TestServer

from wow_status import cli
from wow_status.companion import upload as companion_upload
from wow_status.group_routing import (
    for_group,
    group_key,
    memberships,
    scoped_claim_secret,
    withdrawal,
)
from wow_status.people import character_role, set_role
from wow_status.schema import ValidationError, validate
from wow_status.server import create_app
from wow_status.store import Conflict, Store

SECRET = '0123456789abcdef0123456789abcdef'
OTHER_SECRET = 'fedcba9876543210fedcba9876543210'
NAME = 'Weekend Crew'
GROUP = group_key(NAME)


def upload(payload, secret=None, later=0):
    value = json.loads(json.dumps(payload))
    value['exported_at'] += later
    if secret:
        value['claim_secret'] = secret
    return value


def owner_of(store, cid):
    return store.db.execute('SELECT owner FROM characters WHERE id=?', (cid,)).fetchone()['owner']


def claim(store, cid):
    row = store.db.execute('SELECT secret_hash FROM character_claims WHERE character=?',
                           (cid,)).fetchone()
    return row['secret_hash'] if row else None


def event_ids(store, cid):
    return {row['id'] for row in store.db.execute('SELECT id FROM events WHERE character=?', (cid,))}


def archived(store, cid):
    path = store.archive_directory / f'{cid}.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None


def test_only_a_32_lowercase_hex_secret_is_kept(payload):
    assert validate(upload(payload, SECRET))['claim_secret'] == SECRET
    assert 'claim_secret' not in validate(payload)
    # The secret is optional: a malformed one is dropped and the upload still goes through.
    for bad in ('', SECRET[:-1], SECRET + '0', SECRET.upper(), 'g' * 32, 42, None):
        assert 'claim_secret' not in validate(dict(payload, claim_secret=bad))


def test_second_owner_with_the_secret_takes_over_with_history(store, payload):
    cid = store.ingest('old-install', upload(payload, SECRET))['character_id']
    events = event_ids(store, cid)
    assert len(events) == 2
    store.ingest('new-install', upload(payload, SECRET, later=1))
    assert owner_of(store, cid) == 'new-install'
    assert event_ids(store, cid) == events
    assert store.characters('old-install') == []
    assert archived(store, cid)['character']['owner_id'] == 'new-install'
    # The previous installation can no longer update it.
    with pytest.raises(Conflict):
        store.ingest('old-install', upload(payload, later=2))


@pytest.mark.parametrize('secret', [None, OTHER_SECRET])
def test_wrong_or_missing_secret_gets_conflict_and_changes_nothing(store, payload, secret):
    cid = store.ingest('owner', upload(payload, SECRET))['character_id']
    before = claim(store, cid)
    with pytest.raises(Conflict, match='another linked user'):
        store.ingest('squatter', upload(payload, secret, later=1))
    assert owner_of(store, cid) == 'owner'
    assert claim(store, cid) == before


async def test_reenrolled_installation_recovers_character_over_http(tmp_path, payload):
    store = Store(tmp_path / 'group.sqlite3')
    client = TestClient(TestServer(create_app(store, GROUP, NAME)))
    await client.start_server()
    try:
        async def enroll():
            response = await client.post('/v1/group-enroll', headers={'X-WoW-Group': GROUP},
                                         json={'group_id': GROUP, 'group_name': NAME})
            body = await response.json()
            return body['owner'], {'X-WoW-Group': GROUP, 'Authorization': 'Bearer ' + body['token']}

        def body(secret, later):
            return dict(upload(payload, secret, later), group_id=GROUP, group_name=NAME)
        (first, first_auth), (lost, lost_auth), (_, squat_auth) = [await enroll() for _ in range(3)]
        response = await client.post('/v1/upload', json=body(SECRET, 0), headers=first_auth)
        assert response.status == 200
        cid = (await response.json())['character_id']
        # credentials.json was lost: a new enrollment presents the same secret.
        assert (await client.post('/v1/upload', json=body(SECRET, 1), headers=lost_auth)).status == 200
        assert owner_of(store, cid) == lost
        for secret in (OTHER_SECRET, None):
            response = await client.post('/v1/upload', json=body(secret, 2), headers=squat_auth)
            assert response.status == 409
        assert owner_of(store, cid) == lost
    finally:
        await client.close()
        store.close()


def test_takeover_needs_a_newer_export(store, payload):
    cid = store.ingest('old-install', upload(payload, SECRET, later=5))['character_id']
    for later in (0, 5):  # older, or the very same SavedVariables export
        with pytest.raises(Conflict, match='Stale export'):
            store.ingest('new-install', upload(payload, SECRET, later=later))
    assert owner_of(store, cid) == 'old-install'


def test_two_installations_with_one_save_do_not_trade_the_character(store, payload):
    cid = store.ingest('old-install', upload(payload, SECRET))['character_id']
    store.ingest('new-install', upload(payload, SECRET, later=1))
    # The old companion is still running: neither the same export nor a newer one,
    # with the right secret, takes the character back.
    for later in (1, 2):
        with pytest.raises(Conflict, match='moved to another installation'):
            store.ingest('old-install', upload(payload, SECRET, later=later))
    assert owner_of(store, cid) == 'new-install'
    store.ingest('new-install', upload(payload, SECRET, later=3))
    # The operator can still move it back on purpose.
    store.redeem(store.create_link('old-install'))
    assert store.release(cid, 'old-install') == 'moved'
    store.ingest('old-install', upload(payload, SECRET, later=4))
    assert owner_of(store, cid) == 'old-install'


def test_takeover_does_not_undo_a_privacy_pause(store, payload):
    cid = store.ingest('old-install', upload(payload, SECRET))['character_id']
    store.pause('old-install')
    with store.db:
        store.db.execute("INSERT INTO group_pauses VALUES('old-install')")
    with pytest.raises(Conflict, match='paused'):
        store.ingest('new-install', upload(payload, SECRET, later=1))
    assert owner_of(store, cid) == 'old-install'


def test_takeover_drops_the_previous_owners_role_label(store, payload):
    cid = store.ingest('old-install', upload(payload, SECRET))['character_id']
    set_role(store, 'old-install', cid, 'main', source='discord')
    payload['settings']['character_role'] = 'alt'
    store.ingest('new-install', upload(payload, SECRET, later=1))
    assert character_role(store, cid) == 'alt'
    assert store.db.execute('SELECT source FROM character_labels WHERE character=?',
                            (cid,)).fetchone()['source'] == 'addon'


def test_owner_rebinds_a_new_secret_after_savedvariables_reset(store, payload):
    cid = store.ingest('owner', upload(payload, SECRET))['character_id']
    store.ingest('owner', upload(payload, OTHER_SECRET, later=1))
    with pytest.raises(Conflict):
        store.ingest('new-install', upload(payload, SECRET, later=2))
    store.ingest('new-install', upload(payload, OTHER_SECRET, later=2))
    assert owner_of(store, cid) == 'new-install'


def test_uploads_without_a_secret_keep_working_and_bind_later(store, payload):
    # An old addon or companion sends no secret; the owner keeps uploading as before.
    cid = store.ingest('owner', payload)['character_id']
    store.ingest('owner', upload(payload, later=1))
    assert claim(store, cid) is None
    # Without a stored claim nobody can take it over, whatever they present.
    with pytest.raises(Conflict):
        store.ingest('new-install', upload(payload, SECRET, later=2))
    # The owner's first upload with a secret binds it, and a missing one keeps it.
    store.ingest('owner', upload(payload, SECRET, later=2))
    store.ingest('owner', upload(payload, later=3))
    assert claim(store, cid) == Store.claim_hash(cid, SECRET)
    store.ingest('new-install', upload(payload, SECRET, later=4))
    assert owner_of(store, cid) == 'new-install'


def test_existing_database_gains_the_claims_table(tmp_path, payload):
    path = tmp_path / 'old.sqlite3'
    store = Store(path)
    cid = store.ingest('owner', payload)['character_id']
    store.close()
    with sqlite3.connect(path) as db:
        db.execute('DROP TABLE character_claims')  # as created by the previous release
    store = Store(path)
    try:
        store.ingest('owner', upload(payload, SECRET, later=1))
        assert claim(store, cid) == Store.claim_hash(cid, SECRET)
    finally:
        store.close()


def test_stored_claim_is_a_per_character_hash(store, payload):
    cid = store.ingest('owner', upload(payload, SECRET))['character_id']
    other = upload(payload, SECRET)
    other['identity']['guid'] = 'Player-123-0002'
    other_cid = store.ingest('owner', other)['character_id']
    assert SECRET not in json.dumps([dict(row) for row in
                                     store.db.execute('SELECT * FROM character_claims')])
    assert claim(store, cid) != claim(store, other_cid)
    assert SECRET not in json.dumps(archived(store, cid))


def test_release_deletes_a_squatted_character_so_the_owner_can_claim_it(store, payload):
    cid = store.ingest('squatter', upload(payload, OTHER_SECRET))['character_id']
    with pytest.raises(Conflict):
        store.ingest('real-owner', upload(payload, SECRET, later=1))
    assert store.release(cid) == 'deleted'
    assert store.characters() == [] and claim(store, cid) is None
    assert archived(store, cid) is None
    # The squatter's companion uploads again before the real owner does.
    with pytest.raises(Conflict, match='moved to another installation'):
        store.ingest('squatter', upload(payload, OTHER_SECRET, later=1))
    assert store.characters() == []
    store.ingest('real-owner', upload(payload, SECRET, later=1))
    assert owner_of(store, cid) == 'real-owner'
    with pytest.raises(Conflict):
        store.ingest('squatter', upload(payload, OTHER_SECRET, later=2))
    # Deleting the squatter's data also forgets the release marker.
    store.delete('squatter')
    assert store.db.execute('SELECT COUNT(*) FROM former_owners').fetchone()[0] == 0


def test_a_mistaken_release_can_be_undone(store, payload):
    cid = store.ingest('real-owner', upload(payload, SECRET))['character_id']
    store.release(cid)
    with pytest.raises(Conflict):
        store.ingest('real-owner', upload(payload, SECRET, later=1))
    assert store.release(cid, 'real-owner') == 'unblocked'
    store.ingest('real-owner', upload(payload, SECRET, later=1))
    assert owner_of(store, cid) == 'real-owner'
    with pytest.raises(ValidationError, match='Unknown character'):
        store.release('0' * 64, 'real-owner')


def test_release_to_an_owner_lifts_their_release_marker(store, payload):
    cid = store.ingest('first', upload(payload))['character_id']
    store.redeem(store.create_link('first'))
    store.release(cid)
    store.ingest('second', upload(payload, later=1))
    store.release(cid, 'first')
    store.ingest('first', upload(payload, SECRET, later=2))
    assert owner_of(store, cid) == 'first'


def test_release_to_an_owner_keeps_history_and_their_next_upload_binds(store, payload):
    cid = store.ingest('lost-install', upload(payload, OTHER_SECRET))['character_id']
    events = event_ids(store, cid)
    token = store.redeem(store.create_link('new-install'))
    assert store.owner(token) == 'new-install'
    store.release(cid, 'new-install')
    assert owner_of(store, cid) == 'new-install' and event_ids(store, cid) == events
    assert claim(store, cid) is None
    assert archived(store, cid)['character']['owner_id'] == 'new-install'
    with pytest.raises(Conflict):
        store.ingest('lost-install', upload(payload, OTHER_SECRET, later=1))
    store.ingest('new-install', upload(payload, SECRET, later=1))
    assert claim(store, cid) == Store.claim_hash(cid, SECRET)


def test_release_rejects_unknown_character_or_owner(store, payload):
    cid = store.ingest('owner', payload)['character_id']
    with pytest.raises(ValidationError, match='Unknown character'):
        store.release('0' * 64)
    with pytest.raises(ValidationError, match='Unknown owner'):
        store.release(cid, 'nobody')
    store.redeem(store.create_link('paused'))
    with store.db:
        store.db.execute("INSERT INTO group_pauses VALUES('paused')")
    with pytest.raises(ValidationError, match='paused'):
        store.release(cid, 'paused')
    store.redeem(store.create_link('owner'))
    with pytest.raises(ValidationError, match='already belongs'):
        store.release(cid, 'owner')
    assert owner_of(store, cid) == 'owner'


def test_owners_lists_enrolled_owners_without_characters(store, payload):
    store.ingest('squatter', payload)
    store.redeem(store.create_link('real-owner'))
    with store.db:
        store.db.execute("INSERT INTO group_pauses VALUES('real-owner')")
    assert {row['owner']: (row['characters'], row['paused']) for row in store.owners()} == {
        'squatter': (1, False), 'real-owner': (0, True)}
    assert len(store.find_characters('THORA', 'test realm', 'Classic-Era')) == 1


def run_cli(monkeypatch, db, *arguments):
    monkeypatch.setattr(sys, 'argv', ['wow-status', 'release-character', '--db', str(db), *arguments])
    cli.main()


def test_release_command_finds_the_character_by_name_and_realm(tmp_path, payload, monkeypatch,
                                                              capsys):
    db = tmp_path / 'service.sqlite3'
    store = Store(db)
    cid = store.ingest('squatter', payload)['character_id']
    other = upload(payload)
    other['identity']['client'] = 'forever'
    other_cid = store.ingest('squatter', other)['character_id']
    store.close()
    with pytest.raises(SystemExit, match='Several characters match'):
        run_cli(monkeypatch, db, '--name', 'thora', '--realm', 'test realm')
    listed = capsys.readouterr().out
    assert cid in listed and other_cid in listed
    with pytest.raises(SystemExit, match='No character matches'):
        run_cli(monkeypatch, db, '--name', 'Nobody', '--realm', 'Test Realm')
    with pytest.raises(SystemExit, match='--character-id, or --name'):
        run_cli(monkeypatch, db, '--name', 'Thora')
    with pytest.raises(SystemExit, match='Unknown owner'):
        run_cli(monkeypatch, db, '--character-id', cid, '--to-owner', 'nobody')
    run_cli(monkeypatch, db, '--name', 'Thora', '--realm', 'Test Realm', '--client', 'classic-era')
    assert 'Released Thora (Test Realm, classic-era)' in capsys.readouterr().out
    store = Store(db)
    try:
        assert [char['id'] for char in store.characters()] == [other_cid]
    finally:
        store.close()
    # Undo: the released owner may claim the deleted character again.
    run_cli(monkeypatch, db, '--character-id', cid, '--to-owner', 'squatter')
    assert 'may claim character' in capsys.readouterr().out
    monkeypatch.setattr(sys, 'argv', ['wow-status', 'owners', '--db', str(db)])
    cli.main()
    assert capsys.readouterr().out.startswith('squatter\t')


def grouped(payload, *labels):
    value = upload(payload, SECRET)
    value['_groups'] = memberships({group_key(label): {'label': label, 'joined_at': 1}
                                    for label in labels}, value['exported_at'])
    return value


def test_each_group_service_gets_its_own_derived_secret(payload):
    value = grouped(payload, 'Weekend Crew', 'Raid Night')
    first, second = (group_key(label) for label in ('Weekend Crew', 'Raid Night'))
    derived = {target: for_group(value, target)['claim_secret'] for target in (first, second)}
    assert len(set(derived.values()) | {SECRET}) == 3
    for secret in derived.values():
        assert validate(dict(payload, claim_secret=secret))
    # A withdrawal must present the same value, or it would rebind the claim.
    assert withdrawal(value, first)['claim_secret'] == derived[first]
    assert for_group(value, first)['claim_secret'] == derived[first]


async def test_dry_run_hides_the_secret(tmp_path, capsys):
    from pathlib import Path
    source = (Path(__file__).parent / 'fixtures/WoWStatus.lua').read_text(encoding='utf-8')
    source = source.replace('["enrolled"] = true,', f'["enrolled"] = true, claim_secret="{SECRET}",')
    path = tmp_path / 'WoWStatus.lua'
    path.write_text(source, encoding='utf-8')
    assert await companion_upload([path], tmp_path / 'credentials.json', tmp_path / 'state.json',
                                  dry_run=True)
    output = capsys.readouterr().out
    assert '<hidden>' in output and SECRET not in output


async def test_companion_without_groups_uploads_a_derived_secret(tmp_path, payload):
    from pathlib import Path
    store = Store(tmp_path / 'service.sqlite3')
    client = TestClient(TestServer(create_app(store)))
    await client.start_server()
    try:
        url = str(client.make_url('')).rstrip('/')
        token = store.redeem(store.create_link('owner'))
        (tmp_path / 'credentials.json').write_text(json.dumps({'url': url, 'token': token}),
                                                    encoding='utf-8')
        source = (Path(__file__).parent / 'fixtures/WoWStatus.lua').read_text(encoding='utf-8')
        source = source.replace('["enrolled"] = true,',
                                f'["enrolled"] = true, claim_secret="{SECRET}",')
        saved = tmp_path / 'WoWStatus.lua'
        saved.write_text(source, encoding='utf-8')
        assert await companion_upload([saved], tmp_path / 'credentials.json',
                                      tmp_path / 'state.json', once=True)
        cid = store.characters()[0]['id']
        sent = scoped_claim_secret({'claim_secret': SECRET}, url)['claim_secret']
        assert sent != SECRET
        assert claim(store, cid) == Store.claim_hash(cid, sent)
    finally:
        await client.close()
        store.close()
