import json

from wow_status.archive import character_document
from wow_status.companion import exports
from wow_status.progression import timeline


def tracking(at):
    return {'observed_until': at + 2000, 'points': [
        {'kind': 'baseline', 'level': 1, 'at': at, 'segment': 'first'},
        {'kind': 'level', 'level': 2, 'at': at + 600, 'segment': 'first', 'event_id': 'level-2'},
        {'kind': 'level', 'level': 3, 'at': at + 1500, 'segment': 'first', 'event_id': 'level-3'},
        {'kind': 'baseline', 'level': 8, 'at': at + 2000, 'segment': 'gap'}]}


def test_timeline_uses_clock_time_and_marks_partial_and_gaps():
    graph = timeline(tracking(1793000000))
    assert graph['x_axis'] == 'elapsed_seconds' and graph['y_axis'] == 'level'
    assert graph['timezone'] == 'Europe/Oslo'
    assert graph['points'][2]['elapsed_seconds'] == 1500
    assert len(graph['durations']) == 2
    assert graph['durations'][0]['partial'] is True
    assert graph['durations'][0]['elapsed_seconds'] is None
    assert graph['durations'][0]['elapsed_lower_bound_seconds'] == 600
    assert graph['durations'][1]['elapsed_seconds'] == 900


def test_graph_data_survives_json_archive_and_is_scrubbed_with_level_privacy(store, payload):
    payload['tracking'] = tracking(payload['exported_at'] - 2000)
    cid = store.ingest('owner', payload)['character_id']
    document = character_document(store, cid)
    assert len(document['progression']['level_timeline']['points']) == 4
    assert 'Europe/Oslo' in json.dumps(document['progression']['level_timeline'])
    payload['settings']['fields']['level'] = False
    store.ingest('owner', payload)
    assert character_document(store, cid)['progression']['level_timeline']['points'] == []


def test_full_local_history_is_uploaded_in_small_batches(tmp_path):
    records = ','.join('{id="e%d",kind="level",at=1793000000,data={level=10}}' % i
                       for i in range(275))
    text = '''WoWStatusDB = {
        version=1,
        characters={
            x={
                enrolled=true,
                identity={guid="p1",name="Thora",realm="Test",client="classic-era"},
                settings={enabled=true,discord_enabled=true,fields={level=true},collection={level=true},announcements={}},
                snapshot={level=10},exported_at=1793000000,events={},
                history={events={%s},tracking={points={}}},
            },
        },
    }''' % records
    path = tmp_path / 'WoWStatus.lua'
    path.write_text(text)
    batches = list(exports(path))
    assert [len(batch['events']) for batch in batches] == [100, 100, 75]
    assert len({event['id'] for batch in batches for event in batch['events']}) == 275


def test_backward_clock_starts_disconnected_segment_without_negative_durations():
    source = {'points': [
        {'kind': 'level', 'level': 2, 'at': 1793001000, 'segment': 'before'},
        {'kind': 'level', 'level': 3, 'at': 1793000000, 'segment': 'after'}]}
    graph = timeline(source)
    assert graph['durations'] == []
    assert all(point['elapsed_seconds'] >= 0 for point in graph['points'])
