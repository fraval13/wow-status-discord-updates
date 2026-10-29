"""Forever adapter mocks only: these do not establish in-game compatibility."""
from datetime import datetime, timezone
from pathlib import Path

import pytest
from test_addon import STUBS, lupa


@pytest.fixture
def forever_lua():
    runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
    runtime.execute(STUBS)
    runtime.execute('''
        WOW_PROJECT_MAINLINE=1
        WOW_PROJECT_CAMELOT=18
        WOW_PROJECT_ID=18
        function GetBuildInfo() return "1.60.1", "70450", "test", 16001 end
        C_Item={GetItemInfo=GetItemInfo}
        GetItemInfo=nil
        SendChatMessage=nil
        __secret={}
        function issecretvalue(value) return value==__secret end
    ''')
    runtime.globals().date = lambda fmt, at: datetime.fromtimestamp(
        at, timezone.utc).strftime(fmt.lstrip('!'))
    root = Path(__file__).parents[1] / 'addon/forever/WoWStatus'
    for name in ('Safe.lua', 'Features.lua', 'CaseFold.lua', 'Forever.lua', 'Loot.lua', 'Progress.lua', 'History.lua', 'HistoryUI.lua',
                 'Groups.lua', 'Presentation.lua', 'Popups.lua', 'Journal.lua', 'Minimap.lua', 'Previews.lua', 'Milestones.lua', 'WoWStatus.lua'):
        runtime.execute((root / name).read_text(encoding='utf-8'))
    return runtime


def test_forever_collects_under_distinct_client_identity(forever_lua):
    lua = forever_lua
    lua.eval('fire')('PLAYER_LOGIN')
    assert lua.eval('character().identity.client') == 'forever'
    assert lua.eval('character().identity.interface') == 16001
    lua.eval('clickSharing')()
    lua.eval('fire')('PLAYER_LEVEL_UP', 2)
    assert lua.eval('character().history.events[1].data.level') == 2
    assert lua.eval('character().history.tracking.points[2].kind') == 'level'


def test_forever_rejects_other_editions(forever_lua):
    lua = forever_lua
    lua.execute('WOW_PROJECT_ID=2')
    assert lua.eval('WoWStatusAdapter.supported')() is False
    lua.execute('WOW_PROJECT_ID=1; function GetBuildInfo() return "retail","1","test",120105 end')
    assert lua.eval('WoWStatusAdapter.supported')() is False


def test_forever_waits_for_public_identity_then_initializes(forever_lua):
    lua = forever_lua
    lua.execute('function UnitGUID() return __secret end')
    lua.eval('fire')('PLAYER_LOGIN')
    assert lua.eval('next(WoWStatusDB.characters)') is None
    lua.execute('function UnitGUID() return "Player-123-0001" end')
    lua.eval('fire')('PLAYER_REGEN_ENABLED')
    assert lua.eval('character().identity.guid') == 'Player-123-0001'


def test_restricted_fields_are_omitted_and_secret_level_events_are_not_recorded(forever_lua):
    lua = forever_lua
    lua.eval('fire')('PLAYER_LOGIN')
    lua.eval('clickSharing')()
    lua.execute('''
        function UnitClass() return __secret end
        function UnitLevel() return __secret end
        fire("PLAYER_LEVEL_UP",__secret)
        fire("PLAYER_REGEN_ENABLED")
    ''')
    assert lua.eval('character().snapshot.class') is None
    assert lua.eval('character().snapshot.level') is None
    assert lua.eval('#character().history.events') == 0


def test_modern_item_api_is_used_without_legacy_global(forever_lua):
    lua = forever_lua
    lua.eval('fire')('PLAYER_LOGIN')
    lua.eval('clickSharing')()
    lua.execute('__slot="|Hitem:123|h[Sword]|h"; fire("PLAYER_EQUIPMENT_CHANGED",1)')
    assert lua.eval('character().history.events[1].kind') == 'loot'
    lua.execute('C_Item.GetItemInfo=function() return __secret,__secret,__secret end')
    item, quality = lua.eval('WoWStatusAdapter.item')('|Hitem:123|h[Sword]|h')
    assert item is None and quality is None


def test_forever_popups_reject_vanilla_packets_and_use_namespaced_chat(forever_lua):
    from wow_status.group_routing import group_key
    lua = forever_lua
    lua.eval('fire')('PLAYER_LOGIN')
    lua.eval('clickSharing')()
    lua.execute('WoWStatusGroups.announce=nil')
    lua.eval('WoWStatusGroups.update')('Weekend Crew', 'Frank')
    command = lua.eval('SlashCmdList.WOWSTATUS')
    command('popup on')
    channel = 'WStatus' + group_key('Weekend Crew')
    receive = lua.eval('WoWStatusPopups.receive')
    assert receive('WSTATUS2 classic-era LEVEL 25 1793000000 e1', 'Eldrin-TestRealm', channel) is False
    assert receive('WSTATUS1 LEVEL 25 1793000000 e1', 'Eldrin-TestRealm', channel) is False
    assert receive('WSTATUS2 forever LEVEL 25 1793000000 e1', 'Eldrin-TestRealm', channel) is True
    command('popup send on')
    lua.eval('fire')('PLAYER_LEVEL_UP', 2)
    assert ' WSTATUS2 forever LEVEL 2 ' in lua.eval('__sent[1].text')
    assert lua.eval('__sent[1].kind') == 'WHISPER'


def test_forever_missing_modern_chat_does_not_fall_back_to_legacy(forever_lua):
    lua = forever_lua
    lua.execute('C_ChatInfo=nil; SendChatMessage=function() error("legacy must not be called") end')
    assert lua.eval('WoWStatusAdapter.chatRestricted')() is True
    assert lua.eval('WoWStatusAdapter.chatSender')() is None


def test_each_client_is_a_complete_folder_with_identical_shared_files():
    root = Path(__file__).parents[1] / 'addon'
    shared = list((root / 'shared').glob('*.lua'))
    assert shared
    for client, adapter in [('vanilla', 'Vanilla.lua'), ('forever', 'Forever.lua')]:
        folder = root / client / 'WoWStatus'
        toc = (folder / 'WoWStatus.toc').read_text(encoding='utf-8')
        assert adapter in toc and toc.index('Safe.lua') < toc.index(adapter)
        assert (folder / adapter).exists()
        for source in shared:
            assert (folder / source.name).read_bytes() == source.read_bytes()
