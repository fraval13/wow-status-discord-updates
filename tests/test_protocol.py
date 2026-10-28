import json

import pytest

from wow_status.companion import endpoint, exports
from wow_status.savedvariables import MAX_BYTES, ParseError, parse
from wow_status.schema import ValidationError, should_announce, validate


def test_parser_accepts_only_data_and_preserves_unicode():
    value = parse(r'''-- Saved by WoW
WoWStatusDB = {version=1, ["name"]="Th\195\179ra", ["events"]={[1]={kind="level"}}, ok=true}
''')
    assert value['name'] == 'Thóra'
    assert value['events'][1]['kind'] == 'level'
    assert value['ok'] is True


@pytest.mark.parametrize('source', [
    'WoWStatusDB = os.execute("bad")',
    'WoWStatusDB = {}; os.execute("bad")',
    'WoWStatusDB = { x = function() end }',
    'WoWStatusDB = setmetatable({}, {})',
    'WoWStatusDB = {x=1,x=2}',
    'WoWStatusDB = {x=1+2}',
    'OtherAddon = {}',
    'WoWStatusDB = {' * 30,
])
def test_parser_rejects_executable_and_malformed_lua(source):
    with pytest.raises(ParseError):
        parse(source)


def test_parser_limits_size_and_nesting():
    with pytest.raises(ParseError):
        parse('WoWStatusDB = {' + 'x={' * 30 + '}' * 31)
    with pytest.raises(ParseError):
        parse(' ' * (MAX_BYTES + 1))


def test_privacy_filters_fields_and_events(payload):
    result = validate(payload)
    assert 'zone' not in result['snapshot']
    payload['settings']['fields']['level'] = False
    result = validate(payload)
    assert 'level' not in result['snapshot']
    assert all(e['kind'] != 'level' for e in result['events'])
    payload['settings']['enabled'] = False
    result = validate(payload)
    assert result['events'] == [] and result['snapshot'] == {}


def test_introduction_requires_confirmation(payload):
    payload['settings']['introduction_confirmed'] = False
    assert all(e['kind'] != 'introduction' for e in validate(payload)['events'])


def test_level_and_loot_filters(payload):
    payload['events'][1]['data']['level'] = 11
    payload['events'].append({'id': 'loot', 'kind': 'loot', 'at': payload['exported_at'],
                              'data': {'quality': 3, 'item': 'Rare sword'}})
    result = validate(payload)
    assert [e['kind'] for e in result['events']] == ['introduction', 'level', 'loot']
    assert [e['kind'] for e in result['events']
            if should_announce(result['settings'], e)] == ['introduction']


def test_untrusted_event_types_are_rejected(payload):
    payload['events'][0]['kind'] = 'dungeon_complete'
    with pytest.raises(ValidationError):
        validate(payload)


@pytest.mark.parametrize('url', ['http://example.com', 'ftp://localhost',
                               'https://user:secret@example.com', 'https://example.com/?key=x'])
def test_remote_credentials_require_https_without_url_secrets(url):
    with pytest.raises(ValueError):
        endpoint(url)


def test_explicit_export_skips_nonconsenting_characters(tmp_path):
    path = tmp_path / 'WoWStatus.lua'
    path.write_text('WoWStatusDB = {version=1, characters={x={enrolled=false}}}')
    assert list(exports(path)) == []


def test_fixture_exports_only_selected_data():
    from pathlib import Path
    values = list(exports(Path(__file__).parent / 'fixtures/WoWStatus.lua'))
    assert len(values) == 1
    assert 'PRIVATE' not in json.dumps(values)


def test_forever_is_accepted_and_other_unknown_clients_are_rejected(payload):
    payload['identity']['client'] = 'forever'
    assert validate(payload)['identity']['client'] == 'forever'
    payload['identity']['client'] = 'retail'
    with pytest.raises(ValidationError):
        validate(payload)



@pytest.mark.parametrize('flag,enabled,expected', [
    ('', True, 1),
    ('', False, 0),
    ('["enrolled"] = false,', True, 0),
    ('["enrolled"] = false,', False, 0),
])
def test_exports_recover_enabled_characters_missing_enrollment(tmp_path, flag, enabled, expected):
    from pathlib import Path
    fixture = (Path(__file__).parent / 'fixtures/WoWStatus.lua').read_text()
    fixture = fixture.replace('["enrolled"] = true,', flag)
    if not enabled:
        fixture = fixture.replace('enabled=true,', 'enabled=false,', 1)
    path = tmp_path / 'WoWStatus.lua'
    path.write_text(fixture)
    values = list(exports(path))
    assert len(values) == expected
    if expected:
        assert values[0]['settings']['enabled'] is True
        assert values[0]['identity']['name'] == 'Thora'


def test_discord_opt_out_skips_new_characters_and_emits_only_pause_for_prior_opt_in(tmp_path):
    from pathlib import Path
    source = (Path(__file__).parent / 'fixtures/WoWStatus.lua').read_text()
    source = source.replace('discord_enabled=true', 'discord_enabled=false')
    path = tmp_path / 'WoWStatus.lua'
    path.write_text(source)
    assert list(exports(path)) == []
    source = source.replace('["enrolled"] = true,', '["enrolled"] = true, discord_enrolled=true,')
    path.write_text(source)
    paused = list(exports(path))
    assert len(paused) == 1
    assert paused[0]['settings']['enabled'] is False
    assert paused[0]['snapshot'] == {} and paused[0]['events'] == []
    assert paused[0]['_discord_opt_out'] is True


def test_discord_opt_in_does_not_backfill_earlier_local_history(tmp_path):
    from pathlib import Path
    source = (Path(__file__).parent / 'fixtures/WoWStatus.lua').read_text()
    source = source.replace('["enrolled"] = true,', '["enrolled"] = true, discord_since=1793000001,')
    source = source.replace('["exported_at"] = 1793000000', '["exported_at"] = 1793000002')
    path = tmp_path / 'WoWStatus.lua'
    path.write_text(source)
    batch = list(exports(path))[0]
    assert batch['events'] == []
    assert batch['settings']['discord_delivery'] == 'summary'
    assert batch['upload_part'] == batch['upload_parts'] == 1
