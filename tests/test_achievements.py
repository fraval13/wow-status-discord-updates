"""Retail achievements (#165): whitelisted IDs travel, names come from the receiver.

Mocked clients only: live ACHIEVEMENT_EARNED delivery is the owner's in-game check.
"""
import pytest
from test_addon import make_lua
from test_journal import actor, clock, deliver_popup, mesh
from test_retail import retail_runtime

from wow_status.schema import ValidationError, validate

# Each client answers in its own language: the shown name must be the receiver's.
ACHIEVEMENTS = '''
    __names=__names or {[42]="Explore Eastern Kingdoms",[43]="Explore Kalimdor",[46]="World Explorer",
        [522]="Somebody Likes Me",[523]="5 Exalted Reputations",[2141]="Stable Keeper",[2142]="Filling Up The Barn",
        [116]="Professional Journeyman",[1283]="Classic Dungeonmaster",[7]="Level 20",[999]="Not On The List"}
    function GetAchievementInfo(id)
        local name=__names[id]
        if not name then return nil end
        return id,name,10,true,1,1,26,"Description",0,236000+id,"",false,true,"",false
    end
'''
GERMAN = '__names={[42]="Erkundung der Östlichen Königreiche",[43]="Erkundung von Kalimdor"}\n'


def enable(lua):
    lua.execute('''
        character().settings.collection.achievement=true
        character().settings.in_game.achievement=true
    ''')


def joined(retail_sender, retail_receiver):
    for lua in (retail_sender, retail_receiver):
        lua.eval('WoWStatusGroups.update')('dawnwatch', '')


def channel(lua):
    return lua.eval('function() for g in pairs(character().group_ids) do return WoWStatusGroups.channel(g) end end')()


def test_retail_achievements_are_off_by_default_and_only_offered_on_retail():
    lua = retail_runtime(extra=ACHIEVEMENTS)
    lua.execute('''
        assert(WoWStatusAchievements.available())
        local s=character().settings
        assert(s.collection.achievement==false and s.in_game.achievement==false and s.announcements.achievement==false)
        fire("ACHIEVEMENT_EARNED",43,false)
        assert(#character().events==0 and #__sent==0)
    ''')
    assert lua.eval('__events.ACHIEVEMENT_EARNED') is not None
    for client_lua in (make_lua(), make_lua(ACHIEVEMENTS_CLASSIC)):
        assert client_lua.eval('WoWStatusAchievements.available()') is False
        assert client_lua.eval('__events.ACHIEVEMENT_EARNED') is None
        client_lua.execute('''
            for _,e in ipairs(WoWStatusJournal.TYPES) do assert(not e[2].achievement) end
            WoWStatusAchievements.earned(43,false)
            assert(#character().events==0)
        ''')


# A Classic-family client with a stray achievement API is still unaffected.
ACHIEVEMENTS_CLASSIC = __import__('test_addon').STUBS + ACHIEVEMENTS


def test_only_whitelisted_first_earns_are_recorded_and_the_packet_has_no_name():
    lua = retail_runtime(extra=ACHIEVEMENTS)
    lua.eval('WoWStatusGroups.update')('dawnwatch', '')
    enable(lua)
    lua.execute('''
        fire("ACHIEVEMENT_EARNED",999,false)      -- real, but not on the list
        fire("ACHIEVEMENT_EARNED",7,false)        -- Level 20: the level-up already says it
        fire("ACHIEVEMENT_EARNED",44,false)       -- listed, unknown to this client
        fire("ACHIEVEMENT_EARNED",42,true)        -- earned before on this account
        assert(#character().events==0)
        fire("ACHIEVEMENT_EARNED",43,false)
        assert(#character().events==1)
        local event=character().events[1]
        assert(event.kind=="achievement" and event.data.achievement_id==43 and event.data.name==nil)
        assert(WoWStatusPopups.eventText(event)=="Earned achievement: Explore Kalimdor")
        assert(WoWStatusJournal.entries()[1].text=="Earned achievement: Explore Kalimdor")
        assert(WoWStatusJournal.entries()[1].achievement_id==43)
    ''')
    packet = lua.eval('__sent[1].text')
    assert ' WSTATUS4 retail achievement ' in packet and packet.endswith(' 43')
    assert 'Kalimdor' not in packet


@pytest.mark.parametrize('raw', ['43', 43])
def test_whitelist_accepts_only_listed_well_formed_ids(raw):
    lua = retail_runtime(extra=ACHIEVEMENTS)
    ident = lua.eval('WoWStatusAchievements.id')
    assert ident(raw) == 43
    for bad in (7, '6', '043', '43a', '', ' 43', '-43', '4300000', '999', 999, 43.5, 0, None, '1e2'):
        assert ident(bad) is None, bad
    assert lua.eval('WoWStatusAchievements.LIST[43]') == 'exploration'


def test_receiver_names_the_achievement_itself_and_rejects_forged_names():
    own = retail_runtime(extra=ACHIEVEMENTS)
    friend = retail_runtime('Eldrin', extra=GERMAN + ACHIEVEMENTS)
    joined(own, friend)
    enable(own)
    own.eval('fire')('ACHIEVEMENT_EARNED', 43, False)
    packet = own.eval('__sent[1].text')
    friend.eval('fire')('CHAT_MSG_ADDON', 'WoWStatus', packet, 'WHISPER', 'Thora-TestRealm')
    assert 'Earned achievement: Erkundung von Kalimdor' in friend.eval('WoWStatusLevelPopup.message:GetText()')
    entry = friend.eval('WoWStatusJournal.entries()[1]')
    assert entry.text == 'Earned achievement: Erkundung von Kalimdor' and entry.achievement_id == 43
    assert friend.eval('WoWStatusPresentation.theme')(entry)[0] == 236043
    receive, group = friend.eval('WoWStatusPopups.receive'), channel(friend)
    for forged in ('Explore Free Gold', 'Earned achievement: Free Gold', '43 Free Gold', '043', '999', '44', '-1', '43|r'):
        assert not receive(f'WSTATUS4 retail achievement 1793000000 f{len(forged)} {forged}', 'Thora-TestRealm', group), forged
    # Only the raw (WSTATUS4) form exists; old hex and extended forms are refused.
    assert not receive('WSTATUS3 retail achievement 1793000000 hex 3433', 'Thora-TestRealm', group)
    assert not receive('WSTATUS8 retail achievement 1793000000 ext 43', 'Thora-TestRealm', group)
    assert friend.eval('#WoWStatusJournal.entries()') == 1


def test_sender_and_receiver_counts_are_bounded_per_session():
    own = retail_runtime(extra=ACHIEVEMENTS)
    friend = retail_runtime('Eldrin', extra=ACHIEVEMENTS)
    joined(own, friend)
    enable(own)
    own.execute('''
        -- Without a group nothing is queued, so nothing uses the cap.
        local groups=character().group_ids;character().group_ids={}
        fire("ACHIEVEMENT_EARNED",1283,false)
        character().group_ids=groups
        assert(WoWStatusDB.popups.last_send.state~="session_cap")
        local ids={42,43,46,522,523,2141,2142}
        for i,id in ipairs(ids) do
            fire("ACHIEVEMENT_EARNED",id,false)
            assert((WoWStatusDB.popups.last_send.state=="session_cap")==(i>WoWStatusAchievements.SESSION_CAP))
        end
        -- Every one is recorded and logged; only the first five go out live.
        assert(#character().events==#ids+1)
        assert(WoWStatusDB.popups.last_send.state=="session_cap")
        assert(not WoWStatusAchievements.spend())
    ''')
    receive, group = friend.eval('WoWStatusPopups.receive'), channel(friend)
    friend.execute('WoWStatusAchievements.RECEIVE_CAP=2')
    count = 'function() local n=0 for _,e in ipairs(WoWStatusJournal.entries()) do if e.kind=="achievement" then n=n+1 end end return n end'
    # A copy of the same update (second group, resend) does not use up the cap.
    for n, nonce in ((42, 'a'), (42, 'a'), (43, 'b'), (46, 'c')):
        receive(f'WSTATUS4 retail achievement 1793000000 {nonce} {n}', 'Thora-TestRealm', group)
    # Past the cap the update is still logged; only the popup is skipped.
    assert friend.eval(count)() == 3
    key = friend.eval('WoWStatusPopups.senderKey')('Thora-TestRealm')
    assert friend.eval('WoWStatusAchievements.admit')(key, 'c') is False
    assert friend.eval('WoWStatusAchievements.admit')(key, 'a') is True


def test_catch_up_carries_only_the_id_and_each_client_names_it():
    author, relay, late = actor('Thora'), actor('Eldrin'), actor('Mira')
    for lua, names in ((author, ''), (relay, ''), (late, GERMAN)):
        lua.execute(names + ACHIEVEMENTS + '''
            WoWStatusAdapter.achievements=true
            character().settings.collection.achievement=true
            character().settings.in_game.achievement=true
        ''')
    clock(author, 10)
    clock(relay, 10)
    author.execute('assert(WoWStatusAchievements.earned(43,false))')
    deliver_popup(author, relay)
    assert relay.eval('WoWStatusJournal.entries()[1].text') == 'Earned achievement: Explore Kalimdor'
    # A relay that rewrote the name could not change what the next member shows.
    relay.execute('WoWStatusJournal.entries()[1].text="Earned achievement: Free Gold"')
    late.eval('WoWStatusJournal.sync')()
    mesh({'Eldrin': relay, 'Mira': late}, duration=40)
    assert late.eval('#WoWStatusJournal.entries()') == 1
    entry = late.eval('WoWStatusJournal.entries()[1]')
    assert entry.text == 'Earned achievement: Erkundung von Kalimdor'
    assert entry.achievement_id == 43 and entry.origin == 'catchup'


def test_achievement_text_validation_and_nynorsk_display():
    lua = retail_runtime(extra=ACHIEVEMENTS)
    lua.execute('''
        assert(WoWStatusJournal.validText("achievement","Earned achievement: Explore Kalimdor"))
        assert(not WoWStatusJournal.validText("achievement","Earned achievement:  "))
        assert(not WoWStatusJournal.validText("achievement","FREE GOLD"))
        WoWStatusLocale.set("nn")
        assert(WoWStatusLocale.T("Earned achievement: Explore Kalimdor")=="Fekk bragda Explore Kalimdor")
        assert(WoWStatusLocale.T("ACHIEVEMENT EARNED!")=="NY BRAGD!")
        assert(WoWStatusLocale.T("Achievements")=="Bragder")
    ''')


def test_companion_schema_keeps_only_the_achievement_id(payload, clone):
    retail = clone(payload)
    retail['identity']['client'] = 'retail'
    retail['settings'].setdefault('collection', dict(retail['settings']['announcements']))['achievement'] = True
    retail['settings']['announcements']['achievement'] = True
    retail['events'] = [{'id': 'ach', 'kind': 'achievement', 'at': retail['exported_at'],
                         'data': {'achievement_id': 43, 'name': 'Forged', 'text': 'Free gold'}}]
    assert validate(retail)['events'][0]['data'] == {'achievement_id': 43}
    retail['events'][0]['data'] = {'achievement_id': 'x'}
    with pytest.raises(ValidationError):
        validate(retail)


def test_overview_and_own_recap_name_achievements_and_keep_a_captioned_kind():
    lua = retail_runtime(extra=ACHIEVEMENTS)
    lua.execute('''
        local text=WoWStatusRecaps.text({counts={achievement=2,death=1},dungeons={}},"Thora",1793000000)
        assert(text:find("died once, 2 achievements",1,true),text)
        WoWStatusLocale.set("nn")
        assert(WoWStatusLocale.T("earned 2 achievements")=="fekk 2 bragder")
        assert(WoWStatusLocale.T("earned an achievement")=="fekk ei bragd")
    ''')
    assert lua.eval('WoWStatusRecaps.sharedText')(
        lua.eval('{counts={achievement=1}}'), None) is None


def test_discord_text_names_the_achievement_id(payload, clone):
    from wow_status.formatting import announcement
    text = announcement({'identity': {'name': 'Thora', 'realm': 'Test'}, 'kind': 'achievement',
                         'data': {'achievement_id': 43}, 'at': 1793000000})
    assert text.startswith('**Thora** · earned achievement 43\n')


def test_unticking_stops_recording_and_legacy_sends_use_the_cap():
    lua = retail_runtime(extra=ACHIEVEMENTS)
    lua.eval('WoWStatusGroups.update')('dawnwatch', '')
    enable(lua)
    lua.execute('''
        fire("ACHIEVEMENT_EARNED",42,false)
        assert(#character().events==1)
        character().settings.in_game.achievement=false   -- collection stays true after a tick
        fire("ACHIEVEMENT_EARNED",43,false)
        assert(#character().events==1)
        -- The legacy channel (no group) counts toward the session cap too.
        character().settings.in_game.achievement=true
        character().group_ids={};WoWStatusDB.popups.legacy_channel=true
        for _,id in ipairs({43,46,522,523,2141,2142}) do fire("ACHIEVEMENT_EARNED",id,false) end
        assert(WoWStatusDB.popups.last_send.state=="session_cap")
    ''')
