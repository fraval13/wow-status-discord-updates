"""Observed milestones, conservative baselines and spoiler-safe friend delivery."""
import pytest
from test_addon import STUBS, make_lua

from wow_status.archive import character_document
from wow_status.formatting import announcement
from wow_status.schema import validate


def test_modern_reputation_only_announces_new_major_standings():
    lua = make_lua(STUBS + '''
        __standing=5
        C_Reputation={GetNumFactions=function() return 1 end,
            GetFactionDataByIndex=function() return {name="Ironforge",reaction=__standing,factionID=47} end}
    ''')
    lua.execute('''
        assert(#character().events==0)
        fire("UPDATE_FACTION")
        assert(#character().events==0)
        __standing=6; fire("UPDATE_FACTION")
        assert(#character().events==1 and character().events[1].data.text=="Honored with Ironforge")
        __standing=7; fire("UPDATE_FACTION")
        __standing=8; fire("UPDATE_FACTION")
        assert(#character().events==3)
        __standing=6; fire("UPDATE_FACTION")
        __standing=8; fire("UPDATE_FACTION")
        assert(#character().events==3)
    ''')


def test_legacy_reputation_api_and_paused_baselines():
    lua = make_lua(STUBS + '''
        __standing=6
        function GetNumFactions() return 1 end
        function GetFactionInfo() return "Ironforge","",__standing,0,0,0,false,false,false,false,true,false,false,47 end
    ''')
    lua.execute('''
        assert(#character().events==0)
        character().settings.enabled=false
        __standing=7;fire("UPDATE_FACTION")
        character().settings.enabled=true
        fire("UPDATE_FACTION")
        assert(#character().events==0)
        __standing=8;fire("UPDATE_FACTION")
        assert(#character().events==1 and character().events[1].data.text=="Exalted with Ironforge")
    ''')


def test_mount_collection_first_acquisition_is_announced_once():
    lua = make_lua(STUBS + '''
        __collected=false
        C_MountJournal={GetMountIDs=function() return {1} end,
            GetMountInfoByID=function() return "Brown Horse",458,1,false,true,1,false,false,nil,false,__collected end}
    ''')
    lua.execute('''
        __collected=true;fire("NEW_MOUNT_ADDED",1)
        assert(#character().events==1)
        assert(character().events[1].kind=="mount")
        assert(character().events[1].data.text=="First mount: Brown Horse")
        fire("NEW_MOUNT_ADDED",1)
        fire("SPELLS_CHANGED")
        assert(#character().events==1)
    ''')


def test_existing_and_late_loaded_mount_collections_are_silent():
    lua = make_lua(STUBS + '''
        __collected=true
        C_MountJournal={GetMountIDs=function() return {1} end,
            GetMountInfoByID=function() return "Brown Horse",458,1,false,true,1,false,false,nil,false,__collected end}
    ''')
    lua.execute('fire("NEW_MOUNT_ADDED",1); assert(#character().events==0)')
    late = make_lua(STUBS + '''
        __collected=false
        C_MountJournal={GetMountIDs=function() return {1} end,
            GetMountInfoByID=function() return "Brown Horse",458,1,false,true,1,false,false,nil,false,__collected end}
    ''')
    late.execute('''
        __collected=true;fire("SPELLS_CHANGED")
        fire("PLAYER_MOUNT_DISPLAY_CHANGED")
        assert(#character().events==0)
    ''')


def test_classic_first_mount_ride_is_labelled_as_an_observation():
    lua = make_lua(STUBS + '''
        __mounted=false
        function IsMounted() return __mounted end
    ''')
    lua.execute('''
        __mounted=true;fire("PLAYER_MOUNT_DISPLAY_CHANGED")
        assert(#character().events==1)
        assert(character().events[1].data.text=="First mount ride recorded!")
        assert(character().events[1].data.source=="observed_ride")
        __mounted=false;fire("PLAYER_MOUNT_DISPLAY_CHANGED")
        __mounted=true;fire("PLAYER_MOUNT_DISPLAY_CHANGED")
        assert(#character().events==1)
    ''')


def test_major_class_unlocks_and_pvp_promotions_are_deduplicated():
    lua = make_lua(STUBS + '''
        __known=false;__rank=0
        function IsSpellKnown(id) return id==71 and __known end
        function GetSpellInfo(id) if id==71 then return "Defensive Stance" end end
        function UnitPVPRank() return __rank end
        function GetPVPRankInfo(rank) return rank>0 and "Sergeant" or "Unranked",rank end
    ''')
    lua.execute('''
        assert(#character().events==0)
        __known=true;fire("SPELLS_CHANGED")
        assert(#character().events==1 and character().events[1].kind=="unlock")
        assert(character().events[1].data.text=="Unlocked Defensive Stance")
        fire("SPELLS_CHANGED")
        __known=false;fire("SPELLS_CHANGED")
        __known=true;fire("SPELLS_CHANGED")
        assert(#character().events==1)
        __rank=1;fire("PLAYER_PVP_RANK_CHANGED")
        assert(#character().events==2 and character().events[2].kind=="pvp")
        __rank=0;fire("HONOR_XP_UPDATE")
        __rank=1;fire("HONOR_XP_UPDATE")
        assert(#character().events==2)
    ''')


def test_dungeon_requires_success_and_complete_roster_not_just_any_boss():
    lua = make_lua(STUBS + '''
        __allKilled=false;__kind="party"
        function GetInstanceInfo() return "The Deadmines",__kind,1,"Normal",5,false,false,36 end
        function GetInstanceLockTimeRemaining() return 0,2 end
        function GetInstanceLockTimeRemainingEncounter(index) return "Boss",1,index==1 or __allKilled end
    ''')
    lua.execute('''
        fire("BOSS_KILL",1,"Boss")
        fire("ENCOUNTER_END",1,"Boss",1,5,0)
        assert(#character().events==0)
        __allKilled=true
        fire("ENCOUNTER_END",1,"Boss",1,5,0)
        assert(#character().events==0)
        fire("ENCOUNTER_END",1,"Boss",1,5,1)
        assert(#character().events==1 and character().events[1].kind=="dungeon")
        fire("LFG_COMPLETION_REWARD")
        assert(#character().events==1)
        __kind="raid";fire("LFG_COMPLETION_REWARD")
        assert(#character().events==1)
    ''')


def test_no_dungeon_api_never_guesses_and_manual_clear_is_once():
    lua = make_lua(STUBS + '''
        function GetInstanceInfo() return "The Deadmines","party" end
    ''')
    lua.execute('''
        fire("BOSS_KILL",1,"Boss")
        assert(#character().events==0)
        SlashCmdList.WOWSTATUS("dungeon The Deadmines")
        SlashCmdList.WOWSTATUS("dungeon the deadmines")
        assert(#character().events==1)
        assert(character().events[1].data.source=="player_entered")
        SlashCmdList.WOWSTATUS("milestones")
        assert(WoWStatusMilestoneSettings:IsShown())
        assert(WoWStatusMilestoneSettings.discovery~=nil)
    ''')


def test_discovery_full_text_roundtrip_and_spoiler_reveal():
    sender = make_lua()
    sender.eval('WoWStatusGroups.update')('navsquad', '')
    detail = 'A hidden cave beyond the waterfall with a strange inscription and a treasure chest. Bring a torch!'
    sender.eval('SlashCmdList.WOWSTATUS')('discover ' + detail)
    packet = sender.eval('__sent[1].text')
    assert len(packet.encode()) <= 243
    assert 'WSTATUS4' in packet and detail in packet
    receiver = make_lua(STUBS.replace('return "Thora" end', 'return "Eldrin" end'))
    receiver.eval('WoWStatusGroups.update')('navsquad', '')
    receiver.eval('fire')('CHAT_MSG_ADDON', 'WoWStatus', packet, 'WHISPER', 'Thora-TestRealm')
    assert detail not in receiver.eval('WoWStatusLevelPopup.message:GetText()')
    assert receiver.eval('WoWStatusDB.popups.activity[1].text') == detail
    receiver.eval('WoWStatusPopups.showActivity')()
    assert detail not in receiver.eval('WoWStatusActivity.text:GetText()')
    receiver.execute('''
        for _, frame in ipairs(__frames) do
            if frame.text=="Reveal discoveries" then frame.OnClick(frame) end
        end
    ''')
    assert detail in receiver.eval('WoWStatusActivity.text:GetText()')
    receiver.eval('WoWStatusPopups.showActivity')()
    assert detail not in receiver.eval('WoWStatusActivity.text:GetText()')
    assert receiver.eval('#character().events') == 0
    sender.eval('SlashCmdList.WOWSTATUS')('discover |Hspell:1|h[bad]|h')
    assert sender.eval('#character().events') == 1


def test_all_new_previews_queue_and_never_record_or_send_progress():
    lua = make_lua()
    lua.eval('SlashCmdList.WOWSTATUS')('previews')
    kinds = ['dungeon','mount','reputation','unlock','pvp','discovery']
    for kind in kinds:
        lua.execute(f'WoWStatusNotificationPreviews.buttons.{kind}.OnClick()')
    headings = []
    for i in range(len(kinds)):
        lua.execute(f'function time() return {1793000000 + 7*i} end; WoWStatusPopups.tick()')
        headings.append(lua.eval('WoWStatusLevelPopup.heading:GetText()'))
    assert len(set(headings)) == 6
    assert lua.eval('#character().events') == 0
    assert lua.eval('#__sent') == 0
    assert lua.eval('#WoWStatusDB.popups.activity') == 0
    assert lua.eval('WoWStatusNotificationPreviews.buttons.invitation') is None


@pytest.mark.parametrize('kind', ['dungeon','mount','reputation','unlock','pvp','discovery'])
def test_milestone_schema_archive_rendering_and_privacy(store, payload, kind):
    payload['settings']['collection'] = {kind: True}
    payload['settings']['announcements'] = {kind: True}
    payload['events'] = [{'id':'new-'+kind, 'kind':kind,'at':payload['exported_at'],
                          'data':{'text':'A milestone', 'source':'player_entered'}}]
    assert validate(payload)['events'][0]['kind'] == kind
    result = store.ingest('owner', payload)
    document = character_document(store, result['character_id'])
    assert document['activity'][kind+'_milestones'][0]['data']['text'] == 'A milestone'
    text = announcement({'kind':kind,'identity':payload['identity'],'data':payload['events'][0]['data'],
                         'at':payload['exported_at']})
    assert 'A milestone' in text
    if kind == 'discovery':
        assert '||A milestone||' in text
    payload['settings']['collection'][kind] = False
    assert validate(payload)['events'] == []


def test_no_optional_event_can_abort_startup():
    required = {'ADDON_LOADED','PLAYER_LOGIN','PLAYER_ENTERING_WORLD','PLAYER_REGEN_ENABLED',
                'PLAYER_LOGOUT','PLAYER_LEVEL_UP','PLAYER_EQUIPMENT_CHANGED','CHAT_MSG_LOOT',
                'ZONE_CHANGED_NEW_AREA','PLAYER_DEAD','TIME_PLAYED_MSG','PLAYER_XP_UPDATE',
                'QUEST_TURNED_IN','QUEST_LOG_UPDATE','SKILL_LINES_CHANGED','PLAYER_ALIVE','PLAYER_UNGHOST',
                'CHAT_MSG_CHANNEL','CHAT_MSG_ADDON','CHANNEL_ROSTER_UPDATE','PLAYER_REGEN_DISABLED'}
    allowed = '{' + ','.join(f'["{name}"]=true' for name in sorted(required)) + '}'
    stubs = STUBS.replace('function methods:RegisterEvent(name)',
                         'function methods:RegisterEvent(name)\n'
                         '    if not (' + allowed + ')[name] then error("Unknown optional event") end')
    lua = make_lua(stubs)
    assert lua.eval('type(SlashCmdList.WOWSTATUS)') == 'function'
    lua.eval('SlashCmdList.WOWSTATUS')('milestones')
    assert lua.eval('WoWStatusMilestoneSettings:IsShown()') is True


def test_existing_class_and_pvp_progress_is_silent_and_first_pvp_rank_works():
    lua = make_lua(STUBS + '''
        __rank=0
        function IsSpellKnown(id) return id==71 end
        function GetSpellInfo(id) if id==71 then return "Defensive Stance" end end
        function UnitPVPRank() return __rank end
        function GetPVPRankInfo(rank) if rank>0 then return "Private",rank end end
    ''')
    lua.execute('''
        fire("SPELLS_CHANGED")
        assert(#character().events==0)
        __rank=1;fire("PLAYER_PVP_RANK_CHANGED")
        assert(#character().events==1 and character().events[1].kind=="pvp")
    ''')
