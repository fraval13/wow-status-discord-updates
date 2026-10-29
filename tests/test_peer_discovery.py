"""Asynchronous roster loading and server-delivered group-chat evidence."""
from test_journal import actor, clock


def group_id(lua):
    return lua.eval('function() for id in pairs(character().group_ids) do return id end end')()


def test_roster_selection_waits_for_reply_then_restores_and_uses_cache():
    lua = actor('Thora')
    lua.execute('''
        __selected=1;__ready=false
        function GetNumDisplayChannels() return 2 end
        function GetChannelDisplayInfo(index)
            if index==1 then return "General",false,false,1,10 end
            for id in pairs(character().group_ids) do return WoWStatusGroups.channel(id),false,false,8,2 end
        end
        function GetSelectedDisplayChannel() return __selected end
        function SetSelectedDisplayChannel(index) __selected=index end
        C_ChatInfo.GetChannelRosterInfo=function(index,member)
            if index==2 and __selected==2 and __ready then return ({"Thora-TestRealm","Eldrin-TestRealm"})[member] end
        end
    ''')
    peers = lua.eval('WoWStatusPopups.peers')
    group = group_id(lua)
    assert len(peers(group)) == 0
    assert lua.eval('__selected') == 2  # Must not switch back before data arrives.
    clock(lua, 1)
    lua.execute('__ready=true')
    assert peers(group)[1] == 'Eldrin-TestRealm'
    assert lua.eval('__selected') == 1
    assert peers(group)[1] == 'Eldrin-TestRealm'  # Roster disappears from API after restore.


def test_real_group_chat_unblocks_waiting_sender_without_roster_api():
    lua = actor('Thora')
    lua.execute('C_ChatInfo.GetChannelRosterInfo=function() return nil end')
    lua.eval('fire')('PLAYER_LEVEL_UP', 2)
    assert lua.eval('WoWStatusDB.popups.last_send.state') == 'waiting_for_group_peers'
    assert lua.eval('#__sent') == 0
    channel = 'WStatus'+group_id(lua)
    lua.eval('fire')('CHAT_MSG_CHANNEL', 'normal chat', 'Pettertest-TestRealm', None,None,None,None,None,8,channel)
    assert lua.eval('__sent[1].target') == 'Pettertest-TestRealm'
    assert lua.eval('__sent[1].prefix') == 'WoWStatus'
    assert lua.eval('#WoWStatusJournal.entries()') == 1  # The ordinary chat text is not logged.
    assert lua.eval('WoWStatusLevelPopup') is None
    assert lua.eval('WoWStatusPopups.peers')(group_id(lua))[1] == 'Pettertest-TestRealm'


def test_a_whisper_alone_does_not_authorize_returning_group_history():
    lua = actor('Thora')
    lua.execute('C_ChatInfo.GetChannelRosterInfo=function() return nil end')
    lua.eval('fire')('PLAYER_LEVEL_UP', 2)
    assert lua.eval('#__sent') == 0
    channel = 'WStatus'+group_id(lua)
    assert lua.eval('WoWStatusPopups.receive')('WSTATUS2 classic-era LEVEL 3 1793000000 friend-3', 'Eldrin-TestRealm', channel)
    assert lua.eval('#__sent') == 0
    assert len(lua.eval('WoWStatusPopups.peers')(group_id(lua))) == 0
    assert lua.eval('#WoWStatusJournal.entries()') == 2
    assert lua.eval('WoWStatusDB.popups.last_receive.state') == 'displayed'


def test_unrelated_channel_and_invalid_packet_do_not_create_peers():
    lua = actor('Thora')
    lua.execute('C_ChatInfo.GetChannelRosterInfo=function() return nil end')
    lua.eval('fire')('CHAT_MSG_CHANNEL','chat','Stranger-TestRealm',None,None,None,None,None,1,'General')
    group = group_id(lua)
    assert len(lua.eval('WoWStatusPopups.peers')(group)) == 0
    assert not lua.eval('WoWStatusPopups.receive')('WSTATUS2 forever LEVEL 3 1793000000 other', 'Stranger-TestRealm','WStatus'+group)
    assert len(lua.eval('WoWStatusPopups.peers')(group)) == 0
    lua.eval('WoWStatusPopups.notePeer')(group,'Eldrin-TestRealm')
    assert len(lua.eval('WoWStatusPopups.peers')(group)) == 1
    clock(lua, 301)
    assert len(lua.eval('WoWStatusPopups.peers')(group)) == 0
