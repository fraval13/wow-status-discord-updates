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
        [522]="Somebody Likes Me",[2141]="Stable Keeper",[116]="Professional Journeyman",[6]="Level 10",
        [7]="Level 20",[8]="Level 30",[9]="Level 40",[10]="Level 50",[11]="Level 60",[999]="Not On The List"}
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
    for bad in ('043', '43a', '', ' 43', '-43', '4300000', '999', 999, 43.5, 0, None, '1e2'):
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
        for _,id in ipairs({6,7,8,9,10,11,42}) do fire("ACHIEVEMENT_EARNED",id,false) end
        assert(#character().events==WoWStatusAchievements.SESSION_CAP)
    ''')
    receive, group = friend.eval('WoWStatusPopups.receive'), channel(friend)
    friend.execute('WoWStatusAchievements.RECEIVE_CAP=2')
    count = 'function() local n=0 for _,e in ipairs(WoWStatusJournal.entries()) do if e.kind=="achievement" then n=n+1 end end return n end'
    for n in (6, 7, 8):
        receive(f'WSTATUS4 retail achievement 1793000000 n{n} {n}', 'Thora-TestRealm', group)
    assert friend.eval(count)() == 2


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
