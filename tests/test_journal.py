"""In-memory peer network; no game/server/Discord traffic."""
from test_addon import STUBS, make_lua


def actor(name, group='navsquad'):
    stubs = STUBS.replace('return "Thora" end', f'return "{name}" end').replace('return "Player-123-0001" end', f'return "Player-123-{name}" end')
    stubs += '''
        __now=1793000000;__mono=0
        function time() return math.floor(__now) end
        function GetTime() return __mono end
    '''
    lua = make_lua(stubs)
    lua.eval('WoWStatusGroups.update')(group, '')
    lua.execute('for id in pairs(character().group_ids) do __channelNames={WoWStatusGroups.channel(id)} end')
    return lua


def clock(lua, value):
    lua.execute(f'__now=1793000000+{value}; __mono={value}')


def mesh(clients, start=11, duration=40, reorder=False):
    """Deliver only log-prefix whispers; ignore popup packets deliberately."""
    delivered = {name: 0 for name in clients}
    fragments = {}
    roster = '{' + ','.join(f'"{name}-TestRealm"' for name in clients) + '}'
    for lua in clients.values():
        lua.execute('__peers=' + roster)
    for step in range(int(duration*2)):
        now = start + step/2
        for lua in clients.values():
            clock(lua, now)
            lua.eval('WoWStatusJournal.tick')()
        packets = []
        for name, lua in clients.items():
            count = lua.eval('#__sent')
            for i in range(delivered[name]+1, count+1):
                packet = lua.eval(f'__sent[{i}]')
                assert len(packet['text'].encode()) <= 243
                if packet['prefix'] == 'WoWStatusLog':
                    item = (name, packet['target'].split('-')[0], packet['text'])
                    if reorder and ' D ' in packet['text']:
                        words = packet['text'].split(' ')
                        key = (name, words[3], words[4])
                        part, total = map(int, words[5].split('/'))
                        chunks = fragments.setdefault(key, {})
                        chunks[part] = item
                        if len(chunks) == total:
                            packets.extend(chunks[i] for i in range(total, 0, -1))
                            packets.append(chunks[1])
                            del fragments[key]
                    else:
                        packets.append(item)
            delivered[name] = count
        for sender, target, text in packets:
            if target in clients:
                clients[target].eval('fire')('CHAT_MSG_ADDON', 'WoWStatusLog', text, 'WHISPER', sender+'-TestRealm')


def deliver_popup(sender, receiver):
    packet = sender.eval('__sent[1].text')
    receiver.eval('fire')('CHAT_MSG_ADDON', 'WoWStatus', packet, 'WHISPER', sender.eval('WoWStatusAdapter.playerName()')+'-TestRealm')


def test_offline_author_is_recovered_from_another_peer_once_without_popup():
    author, relay, late = actor('Thora'), actor('Eldrin'), actor('Mira')
    clock(author, 10)
    clock(relay, 10)
    author.eval('fire')('PLAYER_LEVEL_UP', 2)
    deliver_popup(author, relay)
    assert author.eval('#WoWStatusJournal.entries()') == 1
    assert relay.eval('#WoWStatusJournal.entries()') == 1
    event_id = author.eval('WoWStatusJournal.entries()[1].id')
    assert relay.eval('WoWStatusJournal.entries()[1].id') == event_id
    late.eval('WoWStatusJournal.sync')()
    mesh({'Eldrin': relay, 'Mira': late}, duration=40)
    assert late.eval('#WoWStatusJournal.entries()') == 1
    assert late.eval('WoWStatusJournal.entries()[1].id') == event_id
    assert late.eval('WoWStatusJournal.entries()[1].origin') == 'catchup'
    assert late.eval('WoWStatusLevelPopup') is None
    deliver_popup(author, late)
    assert late.eval('WoWStatusLevelPopup') is None
    assert late.eval('#character().events') == 0
    late.eval('WoWStatusJournal.sync')()
    mesh({'Eldrin': relay, 'Mira': late}, start=52, duration=40)
    assert late.eval('#WoWStatusJournal.entries()') == 1


def test_private_actions_log_locally_but_never_sync_and_previews_do_not_log():
    own, friend = actor('Thora'), actor('Mira')
    own.execute('''
        fire("QUEST_TURNED_IN",100)
        fire("QUEST_TURNED_IN",100)
        __slot="|Hitem:1|h[Test sword]|h"
        fire("PLAYER_EQUIPMENT_CHANGED",1)
        fire("PLAYER_EQUIPMENT_CHANGED",1)
        __skill=75
        function GetNumSkillLines() return 1 end
        function GetSkillLineInfo() return "Alchemy",nil,nil,__skill,0,0,150 end
        fire("SKILL_LINES_CHANGED")
        __skill=76;fire("SKILL_LINES_CHANGED")
        WoWStatusPopups.preview("level")
    ''')
    assert own.eval('#WoWStatusJournal.entries()') == 2
    assert own.eval('function() for _,e in ipairs(WoWStatusJournal.entries()) do if next(e.groups) then return false end end return true end')()
    friend.eval('WoWStatusJournal.sync')()
    mesh({'Thora': own, 'Mira': friend})
    assert friend.eval('#WoWStatusJournal.entries()') == 0


def test_join_boundary_and_unrelated_group_prevent_history_leaks():
    own = actor('Thora')
    clock(own, 10)
    own.eval('fire')('PLAYER_LEVEL_UP', 2)
    late = actor('Mira')
    clock(late, 20)
    late.eval('WoWStatusGroups.update')('', '')
    late.eval('WoWStatusGroups.update')('navsquad', '')
    mesh({'Thora': own, 'Mira': late}, start=21, duration=25)
    assert late.eval('#WoWStatusJournal.entries()') == 0
    outsider = actor('Eldrin', 'unrelated')
    group = own.eval('function() for id in pairs(character().group_ids) do return id end end')()
    assert not outsider.eval('WoWStatusJournal.receive')('J2 '+group+' Q test 0 1793000000', 'Thora-TestRealm', 'WHISPER')
    assert outsider.eval('#WoWStatusJournal.entries()') == 0


def test_revoked_privacy_cancels_sharing_and_group_removal_clears_remote_log():
    own, friend = actor('Thora'), actor('Mira')
    clock(own, 10)
    clock(friend, 10)
    own.eval('fire')('PLAYER_LEVEL_UP', 2)
    deliver_popup(own, friend)
    own.execute('character().settings.fields.level=false; WoWStatusJournal.privacyChanged()')
    assert own.eval('#WoWStatusJournal.entries()') == 0
    friend.eval('WoWStatusGroups.update')('', '')
    assert friend.eval('#WoWStatusJournal.entries()') == 0
    # A relay cannot reinsert a revoked own event as somebody else's activity.
    assert own.eval('#character().events') == 1


def test_log_ui_reuses_popup_art_and_virtualizes_rows_and_preserves_ids():
    lua = actor('Thora')
    clock(lua, 10)
    lua.eval('fire')('PLAYER_LEVEL_UP', 2)
    stable_id = lua.eval('WoWStatusJournal.entries()[1].id')
    lua.eval('SlashCmdList.WOWSTATUS')('activity')
    lua.eval('WoWStatusPopups.preview')('level')
    assert lua.eval('WoWStatusActivityLog.rows[1].icon.texture') == lua.eval('WoWStatusLevelPopup.icon.texture')
    assert lua.eval('#WoWStatusActivityLog.rows') == 6
    lua.execute('''
        WoWStatusJournal.init(WoWStatusDB,character())
        for i=1,50 do WoWStatusJournal.observe("professionprogress","Alchemy: "..i) end
        WoWStatusActivityLog.scroll.scroll=112*10
        WoWStatusActivityLog.scroll.OnVerticalScroll()
    ''')
    assert lua.eval('#WoWStatusActivityLog.rows') == 6
    assert lua.eval('WoWStatusActivityLog.rows[1].event_id') == lua.eval('WoWStatusActivityLog.entriesList[11].id')
    assert lua.eval('function(id) for _,e in ipairs(WoWStatusJournal.entries()) do if e.id==id then return true end end return false end')(stable_id)
    assert lua.eval('WoWStatusJournal.eventID("Thora-TestRealm","1-2")') != lua.eval('WoWStatusJournal.eventID("Mira-TestRealm","1-2")')


def test_unsolicited_malformed_and_non_member_sync_packets_are_ignored():
    lua = actor('Thora')
    group = lua.eval('function() for id in pairs(character().group_ids) do return id end end')()
    receive = lua.eval('WoWStatusJournal.receive')
    assert not receive('J2 '+group+' D unknown abc 1/1 abcd', 'Eldrin-TestRealm', 'WHISPER')
    assert not receive('J2 '+group+' Q request 0 1793000000', 'Stranger-TestRealm', 'WHISPER')
    assert not receive('J2 '+group+' Q request 999999 1793000000', 'Eldrin-TestRealm', 'WHISPER')
    assert not receive('J2 '+group+' Q request 0 1793000000', 'Eldrin-TestRealm', 'CHANNEL')
    assert not receive('J2 '+group+' Q request 0 1793000000'+'x'*300, 'Eldrin-TestRealm', 'WHISPER')
    assert lua.eval('#WoWStatusJournal.entries()') == 0


def test_multiple_inventory_pages_and_known_pages_reconcile_without_duplicates():
    relay, late = actor('Eldrin'), actor('Mira')
    channel = relay.eval('function() for id in pairs(character().group_ids) do return WoWStatusGroups.channel(id) end end')()
    for level in range(2, 22):
        clock(relay, 10+level)
        assert relay.eval('WoWStatusPopups.receive')(f'WSTATUS2 classic-era LEVEL {level} {1793000010+level} epoch-{level}',
                                                  'Thora-TestRealm', channel)
    mesh({'Eldrin': relay, 'Mira': late}, start=33, duration=90)
    assert late.eval('#WoWStatusJournal.entries()') == 20
    late.eval('WoWStatusJournal.sync')()
    mesh({'Eldrin': relay, 'Mira': late}, start=124, duration=35)
    assert late.eval('#WoWStatusJournal.entries()') == 20
    assert late.eval('WoWStatusLevelPopup') is None


def test_reordered_and_duplicate_fragments_are_reassembled_once():
    own, late = actor('Thora'), actor('Mira')
    clock(own, 10)
    own.eval('fire')('PLAYER_LEVEL_UP', 2)
    mesh({'Thora': own, 'Mira': late}, duration=40, reorder=True)
    assert late.eval('#WoWStatusJournal.entries()') == 1
    assert late.eval('WoWStatusJournal.entries()[1].text') == 'Reached level 2!'
    assert late.eval('WoWStatusLevelPopup') is None


def test_private_log_cap_does_not_evict_shared_announcement_and_scroll_anchor_stays():
    lua = actor('Thora')
    clock(lua, 10)
    lua.eval('fire')('PLAYER_LEVEL_UP', 2)
    shared = lua.eval('WoWStatusJournal.entries()[1].id')
    lua.execute('''
        for i=1,1010 do WoWStatusJournal.observe("professionprogress","Alchemy: "..i) end
        WoWStatusJournal.show()
        WoWStatusActivityLog.scroll.scroll=112*10
        WoWStatusActivityLog.scroll.OnVerticalScroll()
        __anchor=WoWStatusActivityLog.rows[1].event_id
        __now=1793000011
        WoWStatusJournal.observe("professionprogress","Alchemy: 1011")
        assert(WoWStatusActivityLog.rows[1].event_id==__anchor)
    ''')
    assert lua.eval('#WoWStatusJournal.entries()') == 1001
    assert lua.eval('WoWStatusJournal.contains')(shared)


def test_a_relay_cannot_restore_own_revoked_data():
    own, relay = actor('Thora'), actor('Mira')
    clock(own, 10)
    clock(relay, 10)
    own.eval('fire')('PLAYER_LEVEL_UP', 2)
    deliver_popup(own, relay)
    own.execute('character().settings.fields.level=false;WoWStatusJournal.privacyChanged()')
    mesh({'Thora': own, 'Mira': relay}, start=11, duration=40)
    assert own.eval('#WoWStatusJournal.entries()') == 0
    assert relay.eval('#WoWStatusJournal.entries()') == 1  # already shared copies are not recalled


def test_same_id_live_in_two_groups_preserves_scope_without_duplicate_toasts():
    own, friend = actor('Thora'), actor('Mira')
    own.eval('WoWStatusGroups.update')('navsquad\nother-group', '')
    friend.eval('WoWStatusGroups.update')('navsquad\nother-group', '')
    clock(own, 10)
    clock(friend, 10)
    own.eval('fire')('PLAYER_LEVEL_UP', 2)
    packet = own.eval('__sent[1].text').split(' ', 1)[1]
    ids = friend.eval('function() local result={} for id in pairs(character().group_ids) do table.insert(result,id) end return result end')()
    for i in [1, 2]:
        friend.eval('fire')('CHAT_MSG_ADDON', 'WoWStatus', ids[i]+' '+packet, 'WHISPER', 'Thora-TestRealm')
    assert friend.eval('#WoWStatusJournal.entries()') == 1
    assert friend.eval('#WoWStatusDB.popups.activity') == 1
    assert friend.eval('function() local n=0 for _ in pairs(WoWStatusJournal.entries()[1].groups) do n=n+1 end return n end')() == 2
    friend.eval('WoWStatusGroups.update')('other-group', '')
    assert friend.eval('#WoWStatusJournal.entries()') == 1
