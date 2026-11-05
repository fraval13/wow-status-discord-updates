"""Regression coverage for the open compatibility and milestone issues."""
from test_addon import STUBS, make_lua
from test_journal import actor, clock, deliver_popup, mesh


def test_empty_classic_mount_collection_still_observes_first_ride():
    lua = make_lua(STUBS + '''
        __mounted=false
        C_MountJournal={GetMountIDs=function() return {} end,GetMountInfoByID=function() end}
        function IsMounted() return __mounted end
    ''')
    lua.execute('''
        __mounted=true;fire("PLAYER_MOUNT_DISPLAY_CHANGED")
        assert(#character().events==1)
        assert(character().events[1].data.source=="observed_ride")
    ''')


def test_classic_empty_modern_professions_use_skill_lines():
    lua = make_lua(STUBS + '''
        function GetProfessions() return nil end
        function GetProfessionInfo() error("empty profession list") end
        function GetNumSkillLines() return 1 end
        function GetSkillLineInfo() return "Alchemy",false,true,150,0,0,225 end
    ''')
    lua.execute('''
        local professions=WoWStatusProgress.professions(true)
        assert(#professions==1 and professions[1].name=="Alchemy")
    ''')


def test_settings_failure_falls_back_to_addon_panel():
    lua = make_lua(STUBS + '''
        Settings={RegisterCanvasLayoutCategory=function() return {GetID=function() return 1 end} end,
            RegisterAddOnCategory=function() end,
            RegisterCanvasLayoutSubcategory=function() return {GetID=function() return 2 end} end,
            OpenToCategory=function() error("blocked settings API") end}
    ''')
    lua.eval('SlashCmdList.WOWSTATUS')('')
    assert lua.eval('WoWStatusSetup:IsShown()')


def test_raid_only_records_successful_first_kill_per_encounter():
    lua = make_lua(STUBS + '''
        __kind="raid"
        function GetInstanceInfo() return "Molten Core",__kind,1,"Normal",40,false,false,409 end
    ''')
    lua.execute('''
        fire("ENCOUNTER_END", 663, "Lucifron", 1, 40, 0)
        assert(#character().events==0)
        fire("ENCOUNTER_END", 663, "Lucifron", 1, 40, 1)
        fire("ENCOUNTER_END", 663, "Lucifron", 1, 40, 1)
        assert(#character().events==1 and character().events[1].kind=="raid")
        assert(character().events[1].data.text=="First raid boss: Lucifron")
        assert(WoWStatusPopups.bigMoment({kind="raid"}))
        fire("ENCOUNTER_END", 664, "Magmadar", 1, 40, 1)
        assert(#character().events==2)
        __kind="party";fire("ENCOUNTER_END", 665, "Boss", 1, 5, 1)
        assert(#character().events==2)
        local medals=WoWStatusFirsts.compute(WoWStatusJournal.entries())
        assert(medals.raid.text=="First raid boss: Lucifron")
        character().settings.enabled=false
        fire("ENCOUNTER_END", 666, "Boss", 1, 40, 1)
        assert(#character().events==2)
    ''')


EPIC = STUBS + '''
    __hasItem=false;__quality=4
    function GetContainerNumSlots(bag) return bag==0 and 1 or 0 end
    function GetContainerItemID() return __hasItem and 18767 or nil end
    function GetItemInfo(id) return "Swift Mistsaber", "item:18767", __quality, 60, 60,
        "Miscellaneous", "Mount", 1, "", 1, 0, 15, 5 end
'''


def test_epic_mount_requires_new_epic_mount_item():
    lua = make_lua(EPIC)
    lua.execute('''
        assert(#character().events==0)
        __hasItem=true;fire("BAG_UPDATE_DELAYED")
        assert(#character().events==1 and character().events[1].kind=="epicmount")
        fire("SPELLS_CHANGED");fire("BAG_UPDATE_DELAYED")
        assert(#character().events==1)
        assert(WoWStatusPopups.bigMoment({kind="epicmount"}))
    ''')
    existing = make_lua(EPIC + '__hasItem=true')
    existing.execute('fire("SPELLS_CHANGED");assert(#character().events==0)')
    ordinary = make_lua(EPIC + '__quality=3')
    ordinary.execute('__hasItem=true;fire("BAG_UPDATE_DELAYED");assert(#character().events==0)')


def test_new_kinds_live_and_quiet_catchup_roundtrip():
    a, b = actor('Thora'), actor('Eldrin')
    clock(a, 10)
    clock(b, 10)
    a.execute('''
        function GetInstanceInfo() return "Molten Core","raid",1,"Normal",40,false,false,409 end
        fire("ENCOUNTER_END",663,"Lucifron",1,40,1)
    ''')
    deliver_popup(a, b)
    assert b.eval('WoWStatusLevelPopup.message:GetText()').find('Lucifron') >= 0
    assert b.eval('WoWStatusJournal.entries()[1].kind') == 'raid'
    c = actor('Eldrin')
    mesh({'Thora': a, 'Eldrin': c})
    assert c.eval('WoWStatusJournal.entries()[1].kind') == 'raid'
    assert c.eval('WoWStatusLevelPopup') is None


def test_shared_recap_opt_in_strict_text_and_no_recursive_session():
    a, b = actor('Thora'), actor('Eldrin')
    clock(a, 10)
    clock(b, 10)
    a.execute('''
        assert(character().settings.in_game.recap==false)
        character().settings.in_game.recap=true
        -- Keep the real death in the recap but ignore its already-sent popup here.
        fire("PLAYER_DEAD");__sent={}
        assert(WoWStatusRecaps.close(time()))
        assert(character().session==nil)
        assert(WoWStatusJournal.entries()[1].kind=="recap")
        assert(WoWStatusJournal.entries()[1].text=="Session recap: 1 death.")
        assert(not WoWStatusRecaps.validShared("Session recap: arbitrary free text."))
        assert(not WoWStatusRecaps.validShared("Session recap: 1 death, 1 death."))
        assert(not WoWStatusRecaps.validShared("Session recap: 10001 deaths."))
        assert(not WoWStatusRecaps.validShared("Session recap: 1 deaths, ."))
    ''')
    clock(a, 11)
    a.eval("WoWStatusPopups.tick")()
    deliver_popup(a, b)
    assert b.eval('WoWStatusJournal.entries()[1].kind') == 'recap'
    assert b.eval('WoWStatusJournal.visible(WoWStatusJournal.entries()[1])')
    c = actor('Eldrin')
    mesh({'Thora': a, 'Eldrin': c})
    assert c.eval('WoWStatusJournal.entries()[1].kind') == 'recap'
    assert c.eval('WoWStatusLevelPopup') is None


def test_native_channel_selection_restores_without_optional_getter():
    lua = make_lua(STUBS + '''
        __selected=1;__ready=false
        function SetSelectedDisplayChannel(index) __selected=index end
        function hooksecurefunc(name,callback)
            local original=_G[name]
            _G[name]=function(...) original(...);callback(...) end
        end
        ChannelFrame={GetList=function() return {GetSelectedChannelIDAndSupportsText=function() return 1,true end} end}
    ''')
    lua.eval('WoWStatusGroups.update')('dawnwatch', '')
    lua.execute('''
        function GetNumDisplayChannels() return 2 end
        function GetChannelDisplayInfo(index)
            if index==1 then return "General",false,false,1,10 end
            for id in pairs(character().group_ids) do return WoWStatusGroups.channel(id),false,false,8,2 end
        end
        C_ChatInfo.GetChannelRosterInfo=function(index,member)
            if index==2 and __selected==2 and __ready then return ({"Thora-TestRealm","Eldrin-TestRealm"})[member] end
        end
        local group=next(character().group_ids)
        assert(#WoWStatusPopups.peers(group)==0 and __selected==2)
        __ready=true
        assert(WoWStatusPopups.peers(group)[1]=="Eldrin-TestRealm")
        assert(__selected==1)
    ''')


def test_shared_recap_respects_revoked_categories_and_is_bounded():
    lua = actor('Thora')
    lua.execute('''
        local session={counts={level=2,death=1,dungeon=3,raid=2,profession=4,mount=1,
            epicmount=1,loot=5,zone=6,quest=2,reputation=3,unlock=2,pvp=1}}
        local text=WoWStatusRecaps.sharedText(session)
        assert(#text<=120 and WoWStatusRecaps.validShared(text))
        character().settings.fields.level=false
        character().settings.in_game.dungeon=false
        text=WoWStatusRecaps.sharedText(session,character().settings)
        assert(not text:find("level",1,true) and not text:find("raid",1,true) and not text:find("dungeon",1,true))
    ''')


def test_optional_milestones_survive_companion_validation_and_archive(store, payload):
    from wow_status.archive import character_document
    from wow_status.schema import validate

    payload['settings']['collection'] = {'dungeon': True, 'mount': True, 'recap': True}
    payload['events'] = [
        {'id': 'raid-first', 'kind': 'raid', 'at': payload['exported_at'],
         'data': {'text': 'First raid boss: Lucifron', 'source': 'game_api'}},
        {'id': 'mount-first', 'kind': 'epicmount', 'at': payload['exported_at'],
         'data': {'text': 'First epic mount: Swift Mistsaber', 'source': 'game_api'}},
        {'id': 'recap-first', 'kind': 'recap', 'at': payload['exported_at'],
         'data': {'text': 'Session recap: 1 death.'}},
    ]
    assert len(validate(payload)['events']) == 3
    result = store.ingest('owner', payload)
    document = character_document(store, result['character_id'])
    assert document['activity']['dungeon_milestones'][0]['data']['text'] == 'First raid boss: Lucifron'
    assert document['activity']['mount_milestones'][0]['data']['text'].startswith('First epic mount:')
    assert document['activity']['addon_sessions'][0]['data']['text'] == 'Session recap: 1 death.'


def test_epic_mount_existing_uncached_item_and_late_api_are_quiet():
    lua = make_lua(EPIC + '''
        __hasItem=true;__cached=false
        local info=GetItemInfo
        function GetItemInfo(id) if __cached then return info(id) end end
    ''')
    lua.execute('''
        __cached=true;fire("GET_ITEM_INFO_RECEIVED",18767,true)
        assert(#character().events==0)
    ''')
    late = make_lua(EPIC + 'GetContainerNumSlots=nil')
    late.execute('''
        __hasItem=true
        function GetContainerNumSlots(bag) return bag==0 and 1 or 0 end
        fire("BAG_UPDATE_DELAYED")
        assert(#character().events==0)
    ''')


def test_raid_only_session_can_write_a_shared_recap():
    lua = actor('Thora')
    lua.execute('''
        character().settings.in_game.recap=true
        function GetInstanceInfo() return "Molten Core","raid",1,"Normal",40,false,false,409 end
        fire("ENCOUNTER_END",663,"Lucifron",1,40,1)
        assert(WoWStatusRecaps.close(time()))
        local found=false
        for _,e in ipairs(WoWStatusJournal.entries()) do
            if e.kind=="recap" then
                found=true;assert(e.text=="Session recap: 1 raid boss kill.")
            end
        end
        assert(found)
    ''')
