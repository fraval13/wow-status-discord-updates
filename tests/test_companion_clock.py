"""The companion reads realm-time stamps on a PC whose clock can be off (issue #7).

The addon stamps exports with realm time and saves how far the PC clock is from
it (clock_offset, PC minus realm). The companion runs on the same PC, so it
checks those stamps against its clock minus that offset.
"""
from pathlib import Path

import pytest
from test_groups import RecordingSession, routed

from wow_status import schema
from wow_status.companion import exports
from wow_status.group_routing import for_group
from wow_status.schema import ValidationError

REALM = 1793000000
FIXTURE = (Path(__file__).parent / 'fixtures/WoWStatus.lua').read_text(encoding='utf-8')


def saved(tmp_path, extra=''):
    path = tmp_path / 'WoWStatus.lua'
    path.write_text(FIXTURE.replace('["exported_at"] = 1793000000,', '["exported_at"] = 1793000000,' + extra),
                    encoding='utf-8')
    return path


def pc_clock(monkeypatch, seconds):
    monkeypatch.setattr(schema.time, 'time', lambda: float(seconds))


def test_an_export_from_a_slow_pc_validates_with_its_clock_offset(tmp_path, monkeypatch):
    pc_clock(monkeypatch, REALM - 600)
    values = list(exports(saved(tmp_path, ' clock_offset = -600,')))
    assert [v['exported_at'] for v in values] == [REALM]
    assert values[0]['_clock_offset'] == -600
    assert 'clock_offset' not in values[0]


def test_without_a_clock_offset_the_pc_clock_is_used_as_before(tmp_path, monkeypatch):
    pc_clock(monkeypatch, REALM - 600)
    with pytest.raises(ValidationError, match='exported_at'):
        list(exports(saved(tmp_path)))
    pc_clock(monkeypatch, REALM)
    assert list(exports(saved(tmp_path)))[0]['_clock_offset'] == 0


@pytest.mark.parametrize('value', ['"-600"', '-600.5', str(2 ** 33)])
def test_a_malformed_clock_offset_is_rejected(tmp_path, monkeypatch, value):
    pc_clock(monkeypatch, REALM)
    with pytest.raises(ValidationError, match='clock offset'):
        list(exports(saved(tmp_path, f' clock_offset = {value},')))


def test_a_pc_clock_months_behind_still_exports(tmp_path, monkeypatch):
    behind = 40 * 86400
    pc_clock(monkeypatch, REALM - behind)
    assert list(exports(saved(tmp_path, f' clock_offset = {-behind},')))[0]['exported_at'] == REALM


def test_group_scoping_on_a_slow_pc_uses_the_clock_offset(payload, clone, monkeypatch):
    source, first, _ = routed(payload, clone)
    pc_clock(monkeypatch, source['exported_at'] - 600)
    with pytest.raises(ValidationError, match='exported_at'):
        for_group(source, first)
    source['_clock_offset'] = -600
    assert for_group(source, first)['exported_at'] == source['exported_at']


async def test_a_resume_time_on_a_fast_pc_is_compared_in_realm_time(tmp_path, payload, clone, monkeypatch):
    """Resumed 100 s ago on a PC 600 s fast: the later event is sent, the earlier one not."""
    from wow_status.group_client import GroupUploader
    source, first, second = routed(payload, clone)
    realm = source['exported_at']
    source['_groups'].pop(second)
    source['_groups'][first]['joined_at'] = realm - 1000
    source['events'][0]['at'] = realm - 200
    source['events'][1]['at'] = realm - 50
    source['_event_targets'] = {event['id']: [first] for event in source['events']}
    source['_clock_offset'] = 600
    pc_clock(monkeypatch, realm + 600)
    config = {'mode': 'groups', 'url': 'https://example.com', 'groups': {first: {
        'url': 'https://example.com/groups/' + first, 'token': 'private-token-' + first,
        'owner': 'group:' + first, 'blocked': False, 'min_joined_at': realm + 500}}}
    session, statuses = RecordingSession(), []
    uploader = GroupUploader(config, tmp_path / 'credentials.json', {}, tmp_path / 'upload-state.json',
                             session, lambda **values: statuses.append(values))
    assert await uploader.upload(source)
    uploads = [body for url, body, headers in session.requests if url.endswith('/v1/upload')]
    assert [e['id'] for e in uploads[0]['events'] if e['kind'] != 'introduction'] == ['level-10']
    assert not any('Run /reload' in str(s.get('connection')) for s in statuses)
