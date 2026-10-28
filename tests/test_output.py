"""Timing, privacy and Discord presentation checks; executed remotely in CI."""
import copy
from datetime import datetime
from zoneinfo import ZoneInfo

from wow_status.daily import render_group, report, window
from wow_status.output import message
from wow_status.schema import validate


def level_payload(payload):
    payload['settings']['fields'].update(zone=True, playtime=True)
    payload['events'] = [payload['events'][1]]
    payload['events'][0]['data'].update(zone='Westfall', played_level_seconds=2880)
    at = payload['events'][0]['at']
    payload['tracking'] = {'points': [
        {'kind': 'level', 'level': 9, 'at': at - 7200, 'segment': 'same', 'event_id': 'level-9'},
        {'kind': 'level', 'level': 10, 'at': at, 'segment': 'same', 'event_id': 'level-10'}]}
    return payload


def test_level_has_separate_played_elapsed_location_today_and_milestone(store, payload):
    store.ingest('owner', level_payload(payload))
    result = message(store, store.pending(), {'wow_levelup': '<:wow_levelup:123>'})
    text = result['content']
    assert text.startswith('<:wow_levelup:123>')
    assert '48m played' in text and '2h elapsed' in text
    assert 'includes offline' in text and 'Westfall' in text
    assert '1 recorded level-up today' in text
    assert 'milestone' in result['embed'].title


def test_partial_timing_and_gaps_are_honest(store, payload):
    payload = level_payload(payload)
    payload['tracking']['points'][0]['kind'] = 'baseline'
    store.ingest('owner', payload)
    text = message(store, store.pending())['content']
    assert 'partial level' in text and '2h elapsed' not in text
    payload['tracking']['points'][0]['segment'] = 'other'
    store.ingest('owner', payload)
    text = message(store, store.pending())['content']
    assert 'partial level' not in text and 'includes offline' not in text


def test_hidden_metadata_is_scrubbed_from_existing_events_and_json(store, payload):
    store.ingest('owner', level_payload(payload))
    payload['settings']['fields'].update(zone=False, playtime=False)
    store.ingest('owner', payload)
    data = store.pending()['data']
    assert 'zone' not in data and 'played_level_seconds' not in data
    archive = next(store.archive_directory.glob('*.json')).read_text(encoding='utf-8')
    assert 'Westfall' not in archive and 'played_level_seconds' not in archive
    assert 'playtime_recorded_at' not in validate(payload)['snapshot']


def test_item_links_are_client_specific_and_quality_colours_are_preserved(store, payload):
    payload['events'] = [{'id': 'loot1', 'kind': 'loot', 'at': payload['exported_at'],
        'data': {'item': '|cffa335ee|Hitem:123:0|h[Great Sword]|h|r', 'quality': 4}}]
    store.ingest('owner', payload)
    item = store.pending()
    embed = message(store, item)['embed']
    assert embed.title == 'Great Sword'
    assert embed.url == 'https://www.wowhead.com/classic/item=123'
    assert embed.colour.value == 0xA335EE and embed.description == 'Epic'
    item['identity']['client'] = 'forever'
    assert message(store, item)['embed'].url is None


def test_cap_has_gold_embed_without_invented_timing(store, payload):
    payload['events'] = [payload['events'][1]]
    payload['events'][0]['data'] = {'level': 60, 'maximum': True}
    store.ingest('owner', payload)
    output = message(store, store.pending())
    assert output['embed'].colour.value == 0xFFD700
    assert 'Level cap' in output['embed'].title
    assert 'played from' not in output['content'] and 'elapsed since' not in output['content']


def test_daily_time_uses_observed_samples_only_inside_oslo_day(store, payload, monkeypatch):
    day = datetime.fromtimestamp(payload['exported_at'], ZoneInfo('Europe/Oslo')).date()
    start, end = window(day)
    # Use yesterday if today's clock is too close to midnight for these fixed observations.
    if start + 4000 > payload['exported_at']:
        from datetime import timedelta
        day -= timedelta(days=1)
        start, end = window(day)
    monkeypatch.setattr('wow_status.store.time.time', lambda: start + 4000)
    payload['settings']['fields']['playtime'] = True
    payload['events'] = []
    first = copy.deepcopy(payload)
    first['exported_at'] = start + 10
    first['snapshot'].update(playtime=500, playtime_recorded_at=start - 10)
    store.ingest('owner', first)
    for at, total in [(start + 100, 1000), (start + 3700, 2800)]:
        payload['exported_at'] = at
        payload['snapshot'].update(playtime=total, playtime_recorded_at=at)
        store.ingest('owner', payload)
    cid = store.characters()[0]['id']
    recap = report(store, cid, day, generated=end + 300)
    summary = recap['activity_summary']
    assert summary['played_seconds_lower_bound'] == 1800
    assert summary['playtime_sample_count'] == 2
    assert 'at least 30m played' in render_group(store, [recap], 'Daily recap')


def test_unobserved_playtime_is_omitted_from_daily_output(store, payload):
    store.ingest('owner', payload)
    day = datetime.fromtimestamp(payload['exported_at'], ZoneInfo('Europe/Oslo')).date()
    recap = report(store, store.characters()[0]['id'], day)
    assert recap['activity_summary']['played_seconds_lower_bound'] is None
    assert 'played (' not in render_group(store, [recap], 'Daily recap')


def test_status_card_is_cumulative_tidy_and_uses_custom_faction_and_class_emojis():
    import json
    from pathlib import Path

    from wow_status.output import upload_summary
    item = json.loads((Path(__file__).parent/'fixtures/status_preview.json').read_text())
    result = upload_summary([item], {'wow_warlock':'<:wow_warlock:123>','wow_alliance':'<:wow_alliance:456>'},preview=True)
    assert 'TEST STATUS' in result['content']
    card = result['embeds'][0]
    assert '<:wow_warlock:123>' in card.title
    fields = {field.name:field.value for field in card.fields}
    assert fields['💀 Total deaths'] == '15'
    assert fields['⬆️ Level'] == '33'
    assert fields['<:wow_alliance:456> Faction'] == 'Alliance'
    assert '37.5%' in fields['📈 XP progress']
    assert fields['📜 Completed quests'] == '236'
    assert '185 / 225' in fields['Professions']
    assert '150 / 225' in fields['Professions']
    assert not any('since last' in field.value for field in card.fields)
    assert len(card) < 2000
    item['friend']['name_source'] = 'unavailable'
    hidden = upload_summary([item])['embeds'][0]
    assert not any('Player' in field.name for field in hidden.fields)


def test_status_metrics_and_skill_ranks_are_filtered_with_profile_privacy():
    import json
    from pathlib import Path
    item = json.loads((Path(__file__).parent/'fixtures/status_preview.json').read_text())
    item['settings']['fields'].update(deaths=False, quests=False, level=False, professions=False, **{'class':False})
    result = validate(item)['snapshot']
    for key in ['deaths','deaths_since','quests_completed','quests_source','quests_since',
                'level','xp_current','xp_max','xp_percent','professions','class','class_id']:
        assert key not in result
