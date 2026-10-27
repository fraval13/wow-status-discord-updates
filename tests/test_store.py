import pytest

from wow_status.schema import ValidationError
from wow_status.store import Conflict, Store


def test_link_is_one_use_and_token_can_be_revoked(store):
    code = store.create_link('owner')
    token = store.redeem(code)
    assert store.owner(token) == 'owner'
    with pytest.raises(ValidationError):
        store.redeem(code)
    store.delete('owner')
    assert store.owner(token) is None


def test_introduction_dedup_survives_reinstall_and_restart(tmp_path, payload):
    path = tmp_path / 'db.sqlite3'
    store = Store(path)
    assert store.ingest('owner', payload)['accepted'] == 2
    store.close()
    store = Store(path)
    payload['events'][0]['id'] = 'new-addon-install-intro'
    assert store.ingest('owner', payload)['accepted'] == 0
    assert len(store.characters()) == 1
    store.close()


def test_character_ownership_and_stale_exports(store, payload):
    store.ingest('owner', payload)
    with pytest.raises(Conflict):
        store.ingest('someone-else', payload)
    payload['exported_at'] -= 10
    with pytest.raises(Conflict):
        store.ingest('owner', payload)


def test_disabling_field_removes_history_and_queue(store, payload):
    store.ingest('owner', payload)
    payload['settings']['fields']['level'] = False
    store.ingest('owner', payload)
    char = store.characters()[0]
    assert 'level' not in char['snapshot']
    rows = store.db.execute("SELECT * FROM events WHERE kind='level'").fetchall()
    assert rows[0]['data'] == '{}' and rows[0]['suppressed'] == 1
    assert store.db.execute('SELECT count(*) FROM outbox').fetchone()[0] == 1
    # Re-enabling must not resurrect a previously scrubbed event.
    payload['settings']['fields']['level'] = True
    assert store.ingest('owner', payload)['accepted'] == 0


def test_pause_cancels_pending_and_scrubs_content(store, payload):
    store.ingest('owner', payload)
    store.pause('owner')
    assert store.pending() is None
    char = store.characters()[0]
    assert char['snapshot'] == {} and char['settings']['enabled'] is False


def test_delete_cascades_and_future_enrollment_can_introduce(store, payload):
    store.ingest('owner', payload)
    store.delete('owner')
    assert store.characters() == []
    assert store.db.execute('SELECT count(*) FROM events').fetchone()[0] == 0
    assert store.ingest('owner', payload)['accepted'] == 2


def test_interrupted_send_becomes_uncertain(tmp_path, payload):
    path = tmp_path / 'db.sqlite3'
    store = Store(path)
    store.ingest('owner', payload)
    delivery = store.pending()['delivery_id']
    store.delivery(delivery, 'sending')
    store.close()
    store = Store(path)
    assert store.db.execute('SELECT status FROM outbox WHERE id=?',
                            (delivery,)).fetchone()[0] == 'uncertain'
    assert store.pending()['delivery_id'] != delivery
    store.close()


def test_failed_validation_does_not_partially_commit(store, payload):
    payload['events'][1]['data']['level'] = -1
    with pytest.raises(ValidationError):
        store.ingest('owner', payload)
    assert store.characters() == []
