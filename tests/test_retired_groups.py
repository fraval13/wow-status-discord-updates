"""Retired groups cannot rejoin, transmit, enroll or expose routing configuration."""
import os
import re
import stat
from pathlib import Path

import pytest
from test_addon import make_lua

import wow_status.group_routing as routing
from wow_status.schema import ValidationError
from wow_status.server import create_app

ROOT = Path(__file__).parents[1]
LABEL = 'Retired synthetic test group'


@pytest.fixture
def retired(monkeypatch):
    key = routing.group_key(LABEL)
    fingerprint = routing._hash_group_bytes(key.encode('ascii'))
    monkeypatch.setattr(routing, 'RETIRED_GROUP_FINGERPRINTS', frozenset({fingerprint}))
    original = Path.read_text

    def read_text(path, *args, **kwargs):
        text = original(path, *args, **kwargs)
        if path.name == 'Groups.lua':
            text = text.replace('local RETIRED = {', 'local RETIRED = {\n    ["' + fingerprint + '"]=true,')
        return text

    monkeypatch.setattr(Path, 'read_text', read_text)
    return key


@pytest.mark.parametrize("legacy", [False, True])
def test_lua_rejects_retired_names_and_ids_and_leaves_saved_channels(retired, legacy):
    lua = make_lua()
    lua.globals().retired_id = retired
    lua.globals().retired_label = LABEL
    lua.globals().legacy_upload_choice = legacy
    lua.execute('''
        assert(not WoWStatusGroups.valid(retired_id))
        assert(WoWStatusGroups.retired(retired_id))
        assert(WoWStatusGroups.key(retired_label)==nil)
        assert(WoWStatusGroups.key(retired_id)==nil)
        assert(WoWStatusGroups.key(retired_id:upper())==nil)
        local ok,message=WoWStatusGroups.update(retired_label,"")
        assert(ok==false and message==WoWStatusGroups.RETIRED_MESSAGE)
        local channel=WoWStatusGroups.channel(retired_id)
        assert(WoWStatusGroups.channelId(channel)==nil)
        WoWStatusDB.account_groups={[retired_id]=retired_label}
        character().group_ids={[retired_id]={label=retired_label,joined_at=time()}}
        WoWStatusDB.characters.other=WoWStatusHistory.copy(character())
        WoWStatusDB.popups.joined_channels={[channel]=true}
        local left,reports={},{}
        function LeaveChannelByName(name) left[#left+1]=name end
        character().legacy_upload=legacy_upload_choice
        local before=#character().events
        WoWStatusGroups.init(WoWStatusDB,character,function(message) reports[#reports+1]=message end)
        assert(next(WoWStatusDB.account_groups)==nil)
        for _,saved in pairs(WoWStatusDB.characters) do assert(saved.group_ids[retired_id]==nil) end
        assert(#left>=1 and left[1]==channel)
        assert(WoWStatusDB.popups.joined_channels[channel]==nil)
        assert(#reports==1 and reports[1]==WoWStatusGroups.RETIRED_MESSAGE)
        assert(#character().events==before and #__sent==0)
        WoWStatusGroups.show()
        assert(WoWStatusGroupWindow.status:GetText()==WoWStatusGroups.RETIRED_MESSAGE)
        assert(WoWStatusGroups.update("A new synthetic private group", ""))
        assert(not WoWStatusDB.retired_groups_removed)
    ''')


def test_legacy_character_import_does_not_restore_retired_groups(retired):
    lua = make_lua()
    lua.globals().retired_id = retired
    lua.globals().retired_label = LABEL
    lua.execute('''
        WoWStatusDB.account_groups=nil
        character().group_ids={[retired_id]={label=retired_label,joined_at=time()}}
        local left={}
        function LeaveChannelByName(name) left[#left+1]=name end
        WoWStatusGroups.init(WoWStatusDB,character,function() end)
        assert(next(character().group_ids)==nil and next(WoWStatusDB.account_groups)==nil)
        assert(#left>=1)
    ''')


def test_backend_refuses_retired_destinations_and_credentials(retired, store, payload):
    assert routing.retired_group_id(retired)
    with pytest.raises(ValidationError, match='retired'):
        routing.group_id(retired)
    with pytest.raises(ValidationError, match='retired'):
        routing.group_label(retired)
    with pytest.raises(ValidationError, match='retired'):
        routing.group_label(retired.upper())
    with pytest.raises(ValidationError, match='retired'):
        routing.memberships({retired: {'label': LABEL, 'joined_at': payload['exported_at']}},
                            payload['exported_at'])
    with pytest.raises(ValidationError, match='retired'):
        create_app(store, retired, LABEL)
    key = routing.group_key('An unrelated private test group')
    assert routing.group_id(key) == key
    assert routing.memberships({key: {'label': 'An unrelated private test group',
                                     'joined_at': payload['exported_at']}}, payload['exported_at'])


def test_all_editions_and_backend_use_the_same_retired_fingerprints():
    expected = routing.RETIRED_GROUP_FINGERPRINTS
    for edition in ('shared', 'vanilla', 'forever', 'tbc', 'retail'):
        root = ROOT / 'addon' / edition
        path = root / ('Groups.lua' if edition == 'shared' else 'WoWStatus/Groups.lua')
        assert set(re.findall(r'\["([a-f0-9]{22})"\]=true', path.read_text(encoding='utf-8'))) == expected


def test_rendered_private_routing_file_is_not_world_readable(tmp_path):
    import importlib.util
    import sys

    sys.path.insert(0, str(ROOT / 'deploy'))
    spec = importlib.util.spec_from_file_location('private_render', ROOT / 'deploy/render_caddyfile.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    groups = tmp_path / 'groups.json'
    groups.write_text('{"group-a":{"name":"A synthetic private test group","port":18081}}', encoding='utf-8')
    output = tmp_path / 'Caddyfile'
    assert module.main(['--groups-config', str(groups), '--output', str(output)]) is None
    if os.name != 'nt':
        assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_a_previously_retired_notice_is_dropped_when_nothing_is_retired():
    lua = make_lua()
    lua.execute('''
        WoWStatusDB.retired_groups_removed = true
        WoWStatusGroups.init(WoWStatusDB, function() return character() end, function() end)
        assert(WoWStatusDB.retired_groups_removed == nil)
        assert(WoWStatusGroups.update("A group friends already use", ""))
    ''')
