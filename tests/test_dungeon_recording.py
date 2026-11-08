"""Normal dungeon endpoints without inventing clears from arbitrary boss kills."""
import pytest
from test_addon import make_lua
from test_client_compatibility import client_runtime
from test_journal import clock, deliver_popup


@pytest.mark.parametrize('edition', ['vanilla', 'forever', 'tbc', 'retail'])
def test_known_classic_final_boss_fills_the_medal_without_a_lockout_roster(edition):
    lua = client_runtime(edition)
    lua.execute('''
        WoWStatusGroups.update("Example Dungeon Crew", "")
        function GetInstanceInfo() return "The Deadmines","party",1,"Normal",5,false,false,36 end
        GetInstanceLockTimeRemaining=nil
        GetInstanceLockTimeRemainingEncounter=nil
        __before=#character().events
        fire("BOSS_KILL",2746,"Captain Greenskin") -- intermediate boss
        fire("ENCOUNTER_END",2747,"Edwin VanCleef",1,5,0) -- a failure is not a kill
        assert(#character().events==__before)
        fire("BOSS_KILL",2747,"Edwin VanCleef")
    ''')
    if edition == 'retail':
        # Retail's redesigned Deadmines has different terminal encounters.
        assert lua.eval('#character().events') == lua.eval('__before')
        return
    lua.execute('''
        assert(#character().events==__before+1)
        local event=character().events[#character().events]
        assert(event.kind=="dungeon" and event.data.instance_id==36 and event.data.source=="game_api")
        fire("ENCOUNTER_END",2747,"Edwin VanCleef",1,5,1)
        fire("BOSS_KILL",2747,"Edwin VanCleef")
        assert(#character().events==__before+1)
        local group=next(character().group_ids)
        assert(WoWStatusFirsts.compute(WoWStatusJournal.entries(),group).dungeon)
    ''')


@pytest.mark.parametrize('map_id,encounter', [(129,2785),(189,447),(429,346)])
def test_other_normal_dungeons_and_wings_accept_their_terminal_boss(map_id, encounter):
    lua = make_lua()
    lua.execute(f'''
        function GetInstanceInfo() return "Example Dungeon","party",1,"Normal",5,false,false,{map_id} end
        fire("ENCOUNTER_END",{encounter},"Localized boss name",1,5,1)
        assert(#character().events==1 and character().events[1].kind=="dungeon")
    ''')


@pytest.mark.parametrize('map_id,encounter', [(2998,3482),(2999,3354),(3065,3496)])
def test_forever_endpoints_use_public_ids_without_language_or_name_matching(map_id, encounter):
    lua = client_runtime('forever')
    lua.execute(f'''
        function GetInstanceInfo() return "Localized dungeon","party",1,"Normal",5,false,false,{map_id} end
        __before=#character().events
        fire("BOSS_KILL",{encounter},"Localized boss")
        assert(#character().events==__before+1)
        assert(character().events[#character().events].kind=="dungeon")
    ''')


def test_hall_of_thanes_records_durgen_when_forever_has_no_lockout_roster():
    lua = client_runtime('forever')
    lua.execute('''
        WoWStatusGroups.update("Example Dungeon Crew", "")
        function GetInstanceInfo() return "The Hall of Thanes","party",1,"Normal",5,false,false,3065 end
        function GetInstanceLockTimeRemaining() return 0,false,0,0 end
        __before=#character().events
        fire("BOSS_KILL",3493,"Faldrim Anvilmar")
        fire("BOSS_KILL",3495,"Infurnus")
        fire("BOSS_KILL",3494,"Plunder")
        fire("ENCOUNTER_END",3496,"Durgen Dirgehammer",1,5,0)
        assert(#character().events==__before)
        fire("BOSS_KILL",3496,"Durgen Dirgehammer")
        assert(#character().events==__before+1)
        local event=character().events[#character().events]
        assert(event.kind=="dungeon" and event.data.instance_id==3065)
        assert(event.data.text=="First clear: The Hall of Thanes")
        local first=WoWStatusFirsts.compute(WoWStatusJournal.entries(),next(character().group_ids))
        assert(first.dungeon and first.dungeon.sender==WoWStatusPopups.characterName(character()))
        fire("ENCOUNTER_END",3496,"Durgen Dirgehammer",1,5,1)
        fire("BOSS_KILL",3496,"Durgen Dirgehammer")
        assert(#character().events==__before+1)
    ''')


@pytest.mark.parametrize('case', ['wrong_map','raid','unknown_boss','secret_boss','secret_instance','disabled'])
def test_insufficient_or_unavailable_evidence_does_not_record_a_clear(case):
    lua = make_lua()
    lua.execute('''
        __map=36;__kind="party";__boss=2747
        __secret={};function issecretvalue(value) return value==__secret end
        function GetInstanceInfo() return "The Deadmines",__kind,1,"Normal",5,false,false,__map end
    ''')
    lua.execute({
        'wrong_map':'__map=33', 'raid':'__kind="raid"', 'unknown_boss':'__boss=999999',
        'secret_boss':'__boss=__secret', 'secret_instance':'__map=__secret',
        'disabled':'character().settings.enabled=false',
    }[case])
    lua.execute('fire("BOSS_KILL",__boss,"Boss");assert(#character().events==0)')


def test_a_confirmed_normal_clear_reaches_a_friend_and_is_not_replayed():
    from test_journal import actor
    sender, friend = actor('Mira'), actor('Thora')
    clock(sender, 10)
    clock(friend, 10)
    sender.execute('''
        function GetInstanceInfo() return "The Deadmines","party",1,"Normal",5,false,false,36 end
        fire("BOSS_KILL",2747,"Edwin VanCleef")
    ''')
    deliver_popup(sender,friend)
    assert 'First clear: The Deadmines' in friend.eval('WoWStatusLevelPopup.message.text')
    sender.execute('fire("BOSS_KILL",2747,"Edwin VanCleef")')
    assert sender.eval('#character().events') == 1


def test_an_empty_dungeon_medal_explains_that_no_clear_was_recorded():
    lua = make_lua()
    lua.execute('''
        WoWStatusGroups.update("Example Dungeon Crew", "")
        WoWStatusLocale.set("nn")
        SlashCmdList.WOWSTATUS("records")
        local found=false
        for _,row in ipairs(WoWStatusRecordsPage.rows) do
            if row.holder.text:find("Ingen rydding av fangehol",1,true) then found=true end
        end
        assert(found)
    ''')
