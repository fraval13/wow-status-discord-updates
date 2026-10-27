import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from wow_status.archive import character_document
from wow_status.daily import DailyRecaps
from wow_status.formatting import announcement, roster_pages
from wow_status.people import character_role, decorate, nickname, person, remember, set_role
from wow_status.schema import ValidationError


def test_discord_name_default_nickname_override_and_reset(store, payload):
    remember(store, 'owner', 'Frank on Discord')
    cid = store.ingest('owner', payload)['character_id']
    assert person(store, 'owner')['display_name'] == 'Frank on Discord'
    assert 'Frank on Discord' in announcement(store.pending())
    nickname(store, 'owner', 'Frank')
    remember(store, 'owner', 'Changed Discord name')
    assert person(store, 'owner')['display_name'] == 'Frank'
    assert character_document(store, cid)['character']['friend']['name_source'] == 'nickname'
    nickname(store, 'owner', None)
    assert person(store, 'owner')['display_name'] == 'Changed Discord name'


def test_only_owner_can_choose_main_and_one_main_per_friend(store, payload, clone):
    first = store.ingest('owner', payload)['character_id']
    second_payload = clone(payload)
    second_payload['identity']['guid'] = 'Player-123-0002'
    second_payload['identity']['name'] = 'Eldrin'
    second = store.ingest('owner', second_payload)['character_id']
    with pytest.raises(ValidationError):
        set_role(store, 'other-friend', first, 'main')
    set_role(store, 'owner', first, 'main')
    set_role(store, 'owner', second, 'main')
    assert character_role(store, first) == 'alt'
    assert character_role(store, second) == 'main'
    payload['settings']['character_role'] = 'main'
    store.ingest('owner', payload)
    assert character_role(store, second) == 'main'  # explicit Discord selection wins


def test_roster_groups_friends_and_shows_main_first(store, payload, clone):
    remember(store, 'owner', 'Frank')
    store.ingest('owner', payload)
    other = clone(payload)
    other['identity']['guid'] = 'Player-123-0002'
    other['identity']['name'] = 'Eldrin'
    cid = store.ingest('owner', other)['character_id']
    set_role(store, 'owner', cid, 'main')
    text = '\n'.join(roster_pages(store, store.characters()))
    assert text.count('**Frank**') == 1
    assert text.index('Eldrin') < text.index('Thora')
    assert 'main' in text and 'alt' in text
    assert all(len(page) <= 1950 for page in roster_pages(store, store.characters()))


def test_combined_daily_report_includes_both_characters_without_duplicate_sends(store, payload, clone):
    remember(store, 'owner', 'Frank')
    store.ingest('owner', payload)
    other = clone(payload)
    other['identity']['guid'] = 'Player-123-0002'
    other['identity']['name'] = 'Eldrin'
    store.ingest('owner', other)
    day = datetime.fromtimestamp(payload['exported_at'], ZoneInfo('Europe/Oslo')).date()
    recaps = DailyRecaps(store)
    recaps.prepare(day)
    item = recaps.pending()
    assert len(item['reports']) == 2
    assert 'Frank' in item['text'] and 'Thora' in item['text'] and 'Eldrin' in item['text']
    recaps.delivery(item['key'], 'sent', 'message-123')
    assert recaps.pending() is None
    assert {r['message_id'] for r in store.db.execute('SELECT message_id FROM digest_parts')} == {'message-123'}


def test_daily_only_keeps_collection_and_deletion_removes_owner_label(store, payload):
    remember(store, 'owner', 'Frank')
    nickname(store, 'owner', 'Custom name')
    store.set_community_setting('immediate_mode', 'daily_only')
    cid = store.ingest('owner', payload)['character_id']
    assert store.pending() is None
    assert character_document(store, cid)['progression']['level_history']
    store.delete('owner')
    assert store.db.execute('SELECT count(*) FROM people').fetchone()[0] == 0
    assert store.db.execute('SELECT count(*) FROM character_labels').fetchone()[0] == 0


def test_mention_like_nicknames_are_safe_and_do_not_change_ownership(store, payload):
    remember(store, 'owner', '@everyone')
    store.ingest('owner', payload)
    char = decorate(store, store.characters()[0])
    assert '@everyone' not in announcement(store.pending())
    assert char['owner'] == 'owner'
    assert 'PRIVATE' not in json.dumps(character_document(store, char['id']))


def test_personal_and_group_milestones_both_must_allow_the_message(store, payload):
    settings = payload['settings']
    event = {'kind': 'level', 'data': {'level': 15, 'maximum': False}}
    store.set_community_setting('level_interval', '15')
    assert store.should_announce(settings, event) is False  # personal interval is 10
    event['data']['level'] = 30
    assert store.should_announce(settings, event) is True


def test_paginated_daily_report_keeps_every_character_once(store, payload, clone):
    remember(store, 'owner', 'Frank')
    names = [f'Character{i}' for i in range(18)]
    for index, name in enumerate(names):
        item = clone(payload)
        item['identity']['guid'] = f'Player-123-{index:04d}'
        item['identity']['name'] = name
        store.ingest('owner', item)
    day = datetime.fromtimestamp(payload['exported_at'], ZoneInfo('Europe/Oslo')).date()
    recaps = DailyRecaps(store)
    recaps.prepare(day)
    seen = []
    while item := recaps.pending():
        assert len(item['text']) <= 1950
        seen.extend(r['identity']['name'] for r in item['reports'])
        recaps.delivery(item['key'], 'simulated')
    assert sorted(seen) == sorted(names)


def test_synthetic_events_are_archived_but_not_daily_progress(store, payload):
    payload['events'][1]['data']['synthetic'] = True
    cid = store.ingest('owner', payload)['character_id']
    document = character_document(store, cid)
    assert document['progression']['level_history'][0]['evidence']['source'] == 'addon_test'
    day = datetime.fromtimestamp(payload['exported_at'], ZoneInfo('Europe/Oslo')).date()
    recaps = DailyRecaps(store)
    recaps.prepare(day)
    assert 'level' not in recaps.pending()['report']['event_counts']
