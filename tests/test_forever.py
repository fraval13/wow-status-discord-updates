"""Forever adapter mocks only: these do not establish in-game compatibility."""
from datetime import datetime, timezone
from pathlib import Path

import pytest
from test_addon import PERSONALITY_FILES, STUBS, lupa


def forever_runtime(name='Thora', extra=''):
    runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
    runtime.execute(STUBS.replace('return "Thora" end', f'return "{name}" end'))
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
    ''' + extra)
    runtime.globals().date = lambda fmt, at: datetime.fromtimestamp(
        at, timezone.utc).strftime(fmt.lstrip('!'))
    root = Path(__file__).parents[1] / 'addon/forever/WoWStatus'
    for name in ('Safe.lua', 'Locale.lua', 'LocaleNN.lua', 'Features.lua', 'CaseFold.lua', 'Forever.lua', 'Loot.lua', 'Progress.lua', 'History.lua', 'HistoryUI.lua',
                 'Groups.lua', 'Share.lua', 'Flavour.lua', 'FlavourNN.lua', *PERSONALITY_FILES, 'Theme.lua', 'MainWindow.lua', 'Overview.lua', 'Guide.lua', 'Presentation.lua', 'Popups.lua', 'Journal.lua', 'WhatsNewData.lua', 'WhatsNew.lua', 'Firsts.lua', 'Recaps.lua', 'Equipment.lua', 'Roster.lua', 'Profile.lua', 'Minimap.lua', 'StatusLine.lua', 'Previews.lua', 'Screenshots.lua', 'Milestones.lua', 'WoWStatus.lua'):
        runtime.execute((root / name).read_text(encoding='utf-8'))
    return runtime


@pytest.fixture
def forever_lua():
    return forever_runtime()


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
    # The level-up packet (a delivery confirmation for Eldrin's update may come first).
    packet = next(p for p in lua.eval('__sent').values() if ' WSTATUS2 forever LEVEL 2 ' in p['text'])
    assert packet['kind'] == 'WHISPER'


def test_forever_missing_modern_chat_does_not_fall_back_to_legacy(forever_lua):
    lua = forever_lua
    lua.execute('C_ChatInfo=nil; SendChatMessage=function() error("legacy must not be called") end')
    assert lua.eval('WoWStatusAdapter.chatRestricted')() is True
    assert lua.eval('WoWStatusAdapter.chatSender')() is None


def test_each_client_has_its_adapter_after_safe_in_the_toc():
    # Shared files are compared both ways in test_sync_addons.py.
    root = Path(__file__).parents[1] / 'addon'
    for client, adapter in [('vanilla', 'Vanilla.lua'), ('forever', 'Forever.lua'), ('tbc','TBC.lua'), ('retail','Retail.lua')]:
        folder = root / client / 'WoWStatus'
        toc = (folder / 'WoWStatus.toc').read_text(encoding='utf-8')
        assert adapter in toc and toc.index('Safe.lua') < toc.index(adapter)
        assert (folder / adapter).exists()


def test_forever_professions_use_namespaced_skill_api_without_classic_globals(forever_lua):
    lua = forever_lua
    lua.execute('''
        GetProfessions=nil;GetProfessionInfo=nil
        GetNumSkillLines=nil;GetSkillLineInfo=nil;GetSpellInfo=nil
        __learned=false;__maximum=75
        C_SkillInfo={GetSkillLineInfoByID=function(id)
            if id==164 and __learned then
                return {skillID=164,name="Blacksmithing",rank=1,maxRank=__maximum,isHeader=false}
            end
        end}
        fire("PLAYER_LOGIN")
        __learned=true;fire("SKILL_LINES_CHANGED")
        assert(#character().events==1)
        assert(character().events[1].data.learned)
        assert(character().snapshot.professions[1].name=="Blacksmithing")
        __maximum=150;fire("SKILL_LINES_CHANGED")
        assert(#character().events==2 and character().events[2].data.title=="Journeyman")
        fire("SKILL_LINES_CHANGED")
        assert(#character().events==2)
        C_SkillInfo.GetSkillLineInfoByID=function() return __secret end
        fire("SKILL_LINES_CHANGED")
        assert(#character().events==2)
    ''')


def test_forever_sends_unless_chat_is_in_lockdown(forever_lua):
    # Live Forever client (#25): "outgoing addon chat restricted" is true in the open
    # world while lockdown is false and messages work, so only lockdown holds sends.
    lua=forever_lua
    lua.execute('''
        C_ChatInfo.AreOutgoingAddonChatMessagesRestricted=function() return true end
        assert(not WoWStatusAdapter.chatRestricted())
        __restricted=true
        assert(WoWStatusAdapter.chatRestricted())
        C_ChatInfo.InChatMessagingLockdown=function() return __secret end
        assert(WoWStatusAdapter.chatRestricted())
    ''')


def test_a_lockdown_answer_from_the_game_is_retried_not_forced(forever_lua):
    lua=forever_lua
    lua.execute('''
        Enum=Enum or {}
        Enum.SendAddonMessageResult={Success=0,AddOnMessageLockdown=11}
        assert(WoWStatusPopups.sendResult(true,11)=="throttled")
    ''')


def test_forever_pvp_uses_client_rank_points_and_season_baselines(forever_lua):
    lua=forever_lua
    lua.execute('''
        UnitPVPRank=nil;GetPVPRankInfo=nil
        __rank=0;__season=1
        C_MajorFactions={GetMajorFactionProgressionInfo=function(id)
            assert(id==2800)
            return {renownLevel=__rank}
        end}
        Enum={PvPRanks={Rank_1=5}}
        function GetCurrentArenaSeason() return __season end
        function UnitSex() return 2 end
        function GetText(key,sex)
            assert(sex==2)
            return ({PVP_RANK_5_1="Private",PVP_RANK_6_1="Corporal"})[key]
        end
        fire("PLAYER_LOGIN")
        assert(#character().events==0)
        __rank=1;fire("MAJOR_FACTION_RENOWN_LEVEL_CHANGED",2800,1)
        assert(#character().events==1 and character().events[1].data.text=="Promoted to Private")
        fire("UPDATE_FACTION")
        assert(#character().events==1)
        __rank=2;fire("UPDATE_FACTION")
        assert(#character().events==2 and character().events[2].data.text=="Promoted to Corporal")
        __season=2;__rank=0;fire("UPDATE_FACTION")
        assert(#character().events==2)
        __rank=1;fire("UPDATE_FACTION")
        assert(#character().events==3)
        __rank=__secret;fire("UPDATE_FACTION")
        assert(#character().events==3)
    ''')


def test_forever_drops_names_without_a_last_name():
    # Live report: "Unshaved" and an old "Edith" stayed listed next to the full names.
    lua = forever_runtime()
    lua.eval('fire')('PLAYER_LOGIN')
    lua.execute('''
        WoWStatusGroups.announce=nil
        WoWStatusGroups.update("dawnwatch","")
        local group=next(character().group_ids)
        assert(not WoWStatusJournal.received({sender="Unshaved-TestRealm",nonce="1-1-aaaa",kind="level",level=5,at=time(),group_id=group}))
        assert(WoWStatusJournal.received({sender="Unshaved Brittlebeard-TestRealm",nonce="1-2-bbbb",kind="level",level=6,at=time(),group_id=group}))
        assert(#WoWStatusJournal.entries()==1)
        -- An old own record with a first name only is dropped; the current character stays.
        WoWStatusDB.characters["forever:TestRealm:old"]={identity={client="forever",realm="TestRealm",guid="old",name="Edith"},
            settings=character().settings,roster_info={race="Human",sex=3,class="PALADIN",level=1}}
        WoWStatusRoster.observe(character())
        local names={}
        for _,g in ipairs(WoWStatusRoster.groups()) do for _,r in ipairs(g.rows) do names[r.name]=true end end
        assert(names["Thora-TestRealm"] and not names["Edith-TestRealm"] and not names["Unshaved-TestRealm"])
        assert(names["Unshaved Brittlebeard-TestRealm"])
    ''')


def test_forever_sends_its_character_list_only_with_the_full_name():
    # Live report: many members stayed "Not announced" because their list went out
    # with the first name only, before the full name was learnt, and never again.
    lua = forever_runtime(extra='function UnitRace() return "Human","Human" end function UnitSex() return 3 end')
    lua.eval('fire')('PLAYER_LOGIN')
    lua.execute('''
        WoWStatusGroups.announce=nil
        WoWStatusGroups.update("dawnwatch","")
        local group=next(character().group_ids)
        __channelNames={WoWStatusGroups.channel(group)}
        WoWStatusRoster.observe(character())
        local function lists()
            local found={}
            for _,p in ipairs(__sent) do if p.prefix=="WoWStatusChr" and p.text:sub(1,2)=="C " then found[#found+1]=p.text end end
            return found
        end
        __mono=0
        function GetTime() return __mono end
        local function pump() for i=1,40 do __mono=__mono+1;WoWStatusRoster.tick() end end
        __peers={"x","y"}
        C_ChatInfo.GetChannelRosterInfo=function(_, i)
            local list={{"Thora Stone",UnitGUID("player")},{"Eldrin Vale","Player-2"}}
            local item=__learn and list[i] or ({{"Eldrin Vale","Player-2"}})[i]
            if item then return item[1],false,false,item[2] end
        end
        __peers={"x"}
        WoWStatusPopups.peers(group); for _=1,3 do WoWStatusPopups.tick() end
        pump()
        assert(#lists()==0, "no first-name-only list")
        __learn=true;__peers={"x","y"}
        WoWStatusPopups.peers(group); for _=1,3 do WoWStatusPopups.tick() end
        assert(character().chat_name=="Thora Stone")
        pump()
        local sent=lists()
        assert(#sent>=1 and sent[1]:find("Thora_Stone-TestRealm",1,true), tostring(sent[1]))
    ''')


def test_forever_learns_its_full_name_from_its_guid_at_login():
    # Live check: GetPlayerInfoByGUID(UnitGUID("player")) gave "Edith Aateigen"
    # where UnitName gave "Edith"; lists no longer wait for a channel roster read.
    lua = forever_runtime(extra='''
        function UnitRace() return "Human","Human" end function UnitSex() return 3 end
        function GetPlayerInfoByGUID(guid)
            if guid == UnitGUID("player") then return "Paladin","PALADIN","Human","Human",3,__guidName,"" end
        end
        __guidName = "Thora Stone"
    ''')
    lua.eval('fire')('PLAYER_LOGIN')
    lua.execute('''
        assert(character().chat_name == "Thora Stone")
        assert(WoWStatusPopups.characterName(character()) == "Thora Stone-TestRealm")
        -- Anything that is not a longer form of the game's own name is ignored.
        character().chat_name = nil
        __guidName = "Someone Else"
        assert(not WoWStatusPopups.learnOwnName() and character().chat_name == nil)
    ''')


def test_forever_lists_each_character_once_whatever_its_realm():
    # Live screenshot: "Annie Fett-CAMWOWEU5Realm3PvE" from her list and "Annie Fett"
    # from the channel roster were listed twice (the roster name got this realm).
    lua = forever_runtime(extra='function UnitRace() return "Human","Human" end function UnitSex() return 3 end')
    lua.eval('fire')('PLAYER_LOGIN')
    lua.execute('''
        WoWStatusGroups.announce=nil
        WoWStatusGroups.update("dawnwatch","")
        local group=next(character().group_ids)
        assert(WoWStatusRoster.key("Annie Fett-CAMWOWEU5Realm3PvE") == WoWStatusRoster.key("Annie Fett"))
        -- A saved list keyed with the realm, and the same member seen in the roster.
        WoWStatusDB.roster.players.p1 = {name="Garvik", groups={[group]=true}, characters={
            ["anniefett-camwoweu5realm3pve"]={name="Annie Fett-CAMWOWEU5Realm3PvE",race="Human",sex=3,class="MAGE",level=12,at=time()}}}
        WoWStatusDB.roster.seen = {["anniefett-testrealm"]={name="Annie Fett",at=time(),groups={[group]=true}}}
        WoWStatusDB.roster.realmless = nil
        WoWStatusRoster.init(WoWStatusDB, character())
        local count = 0
        for _,g in ipairs(WoWStatusRoster.groups()) do
            for _,r in ipairs(g.rows) do if r.name:find("Annie Fett",1,true) then count = count + 1 end end
        end
        assert(count == 1, count)
        assert(WoWStatusRoster.playerOf("Annie Fett") == "Garvik")
    ''')


def test_forever_never_registers_for_the_combat_log(forever_lua):
    # WoW Forever (a Midnight-era client) stops an addon that registers for the
    # combat log with a "blocked action" dialog; pcall cannot prevent it.
    assert forever_lua.eval('__events.COMBAT_LOG_EVENT_UNFILTERED') is None
    assert forever_lua.eval('__events.PLAYER_DEAD') is not None
