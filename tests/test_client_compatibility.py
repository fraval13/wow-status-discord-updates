"""Client API contracts and simulated peers; never a live-game certification."""
import pytest
from test_addon import make_lua
from test_forever import forever_runtime
from test_journal import clock, mesh
from test_retail import retail_runtime
from test_tbc import tbc_runtime


def client_runtime(edition, name='Thora', extra=''):
    if edition == 'vanilla':
        return make_lua(join_announcements=True)
    if edition == 'tbc':
        lua = tbc_runtime(name, extra, join_announcements=True)
    else:
        extra = '''
            __now=1793000000;__mono=0
            function time() return math.floor(__now) end
            function GetTime() return __mono end
            Enum={SendAddonMessageResult={Success=0}}
            local send=C_ChatInfo.SendAddonMessage
            C_ChatInfo.SendAddonMessage=function(...)
                send(...);return Enum.SendAddonMessageResult.Success
            end
        ''' + extra
        if edition == 'forever':
            lua = forever_runtime(name, extra)
            lua.eval('fire')('PLAYER_LOGIN')
        else:
            lua = retail_runtime(name, extra, join_announcements=True)
    return lua


@pytest.mark.parametrize('edition', ['vanilla', 'forever', 'tbc', 'retail'])
def test_join_notification_names_wow_status_group_and_remains_once_only(edition):
    lua = client_runtime(edition)
    lua.execute('''
        WoWStatusGroups.update("dawnwatch", "")
        assert(#character().events==1)
        assert(character().events[1].kind=="introduction")
        assert(WoWStatusJournal.entries()[1].text=="Joined the WoW Status group")
        assert(__sent[1].text:find("Joined the WoW Status group",1,true))
        WoWStatusGroups.update("dawnwatch", "")
        WoWStatusGroups.update("", "")
        WoWStatusGroups.update("dawnwatch", "")
        fire("PLAYER_LOGIN")
        assert(#character().events==1)
        WoWStatusPreviews.show()
        assert(WoWStatusNotificationPreviews.buttons.introduction:GetText()=="Joined the WoW Status group")
        WoWStatusPopups.preview("introduction")
        assert(WoWStatusLevelPopup.message:GetText():find("Joined the WoW Status group",1,true))
    ''')


@pytest.mark.parametrize('edition', ['forever', 'retail'])
def test_dungeon_uses_documented_third_return_and_requires_public_complete_roster(edition):
    lua = client_runtime(edition, extra='''
        __allKilled=false;__count=2
        function GetInstanceInfo() return "The Deadmines","party",1,"Normal",5,false,false,36 end
        function GetInstanceLockTimeRemaining() return 0,false,__count,__allKilled and 2 or 1 end
        function GetInstanceLockTimeRemainingEncounter(index)
            return "Boss",1,index==1 or __allKilled,false
        end
    ''')
    lua.execute('''
        fire("BOSS_KILL",1,"Boss")
        assert(#character().events==0)
        __allKilled=true;__count=__secret
        fire("BOSS_KILL",1,"Boss")
        assert(#character().events==0)
        __count=2;__allKilled=__secret
        fire("BOSS_KILL",1,"Boss")
        assert(#character().events==0)
        __allKilled=true
        fire("ENCOUNTER_END",1,"Boss",1,5,0)
        assert(#character().events==0)
        fire("ENCOUNTER_END",1,"Boss",1,5,1)
        assert(#character().events==1 and character().events[1].kind=="dungeon")
        fire("BOSS_KILL",1,"Boss")
        fire("LFG_COMPLETION_REWARD")
        assert(#character().events==1)
    ''')


@pytest.mark.parametrize('edition', ['forever', 'retail'])
def test_modern_restrictions_delay_delivery_and_login_sync_remains_two_way_and_quiet(edition):
    clients = {name: client_runtime(edition, name, extra=f'''
        function UnitGUID() return "Player-{name}" end
        __outgoingRestricted=true
        C_ChatInfo.AreOutgoingAddonChatMessagesRestricted=function() return __outgoingRestricted end
    ''') for name in ('Thora', 'Eldrin')}
    for lua in clients.values():
        lua.execute('''
            WoWStatusGroups.announce=nil
            WoWStatusGroups.update("dawnwatch", "")
            for id in pairs(character().group_ids) do __channelNames={WoWStatusGroups.channel(id)} end
        ''')
    own, friend = clients.values()
    own.eval('fire')('PLAYER_LEVEL_UP', 30)
    assert own.eval('#__sent') == 0
    assert own.eval('WoWStatusDB.popups.last_send.state') == 'chat_restricted'
    own.execute('__outgoingRestricted=false;WoWStatusPopups.tick()')
    assert own.eval('WoWStatusDB.popups.last_send.state') == 'attempted_no_receipt'
    packet = own.eval('__sent[1].text')
    friend.eval('fire')('CHAT_MSG_ADDON', 'WoWStatus', packet, 'WHISPER', 'Thora-TestRealm')
    assert friend.eval('WoWStatusLevelPopup.message:GetText()').endswith('level 30!')
    for lua in clients.values():
        clock(lua, 10)
        lua.execute('__outgoingRestricted=true')
    own.eval('fire')('PLAYER_LEVEL_UP', 31)
    friend.eval('fire')('PLAYER_LEVEL_UP', 32)
    for lua in clients.values():
        lua.execute('__outgoingRestricted=false')
    mesh(clients, start=11, duration=50, reorder=True)
    ids = []
    for lua in clients.values():
        entries = list(lua.eval('WoWStatusJournal.entries()').values())
        assert len(entries) == 3
        assert any(e['origin'] == 'catchup' for e in entries)
        ids.append({e['id'] for e in entries})
    assert ids[0] == ids[1]
    assert own.eval('WoWStatusLevelPopup') is None
    assert 'level 30!' in friend.eval('WoWStatusLevelPopup.message:GetText()')
    mesh(clients, start=62, duration=15)
    assert all(lua.eval('#WoWStatusJournal.entries()') == 3 for lua in clients.values())
