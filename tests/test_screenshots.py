"""Optional automatic screenshots (#55) and the hidden-interface option (#56)."""
from test_addon import STUBS, make_lua

SHOTS = STUBS + '''
__shots = {}
__timers = {}
__uiShown = true
UIParent = {IsShown=function() return __uiShown end,
    Hide=function() if __combat then error("blocked") end; __uiShown=false end,
    Show=function() if __combat then error("blocked") end; __uiShown=true end}
function Screenshot() table.insert(__shots, {ui=__uiShown}) end
C_Timer.After = function(seconds, fn) table.insert(__timers, {seconds=seconds, fn=fn}) end
function runTimers()
    while #__timers > 0 do table.remove(__timers, 1).fn() end
end
function options() return character().settings.screenshots end
'''

DUNGEON = '''
function GetInstanceInfo() return "The Deadmines","party",1,"Normal",5,false,false,36 end
function GetInstanceLockTimeRemaining() return 0,false,1,1 end
function GetInstanceLockTimeRemainingEncounter() return "Boss",1,true end
'''


def test_options_default_off_and_are_saved_per_character():
    lua = make_lua(SHOTS)
    assert lua.eval('options().level == false and options().dungeon == false and options().hide_ui == false')
    lua.execute('''
        local found = {}
        for _, entry in ipairs(WoWStatusSetup.checks) do
            if entry.group == "screenshots" then found[entry.key] = entry.widget end
        end
        assert(found.level and found.dungeon and found.hide_ui)
        found.level:SetChecked(true); found.level.OnClick(found.level)
        assert(options().level == true and options().dungeon == false)
    ''')


def test_no_screenshot_while_the_options_are_off():
    lua = make_lua(SHOTS)
    lua.execute('fire("PLAYER_LEVEL_UP", 10); runTimers()')
    assert lua.eval('#character().events') == 1
    assert lua.eval('#__shots') == 0


def test_level_up_takes_exactly_one_delayed_screenshot():
    lua = make_lua(SHOTS)
    lua.execute('''
        options().level = true
        fire("PLAYER_LEVEL_UP", 10)
        assert(#__shots == 0 and __timers[1].seconds == 1)
        runTimers()
        assert(#__shots == 1 and __shots[1].ui == true)
        fire("SCREENSHOT_SUCCEEDED")
        fire("PLAYER_LEVEL_UP", 11); runTimers()
        assert(#__shots == 2)
    ''')


def test_first_dungeon_clear_takes_one_screenshot_and_repeat_clears_none():
    lua = make_lua(SHOTS + DUNGEON)
    lua.execute('''
        options().dungeon = true
        fire("LFG_COMPLETION_REWARD"); runTimers()
        assert(#character().events == 1 and #__shots == 1)
        fire("SCREENSHOT_SUCCEEDED")
        fire("LFG_COMPLETION_REWARD"); runTimers()
        assert(#__shots == 1)
    ''')


def test_synthetic_test_events_and_received_or_synced_entries_take_no_screenshot():
    lua = make_lua(SHOTS)
    lua.execute('''
        options().level = true; options().dungeon = true
        SlashCmdList.WOWSTATUS("test"); runTimers()
        assert(#__shots == 0)
        -- Entries from friends and login catch-up go through the journal, not the
        -- local event queue, so they can never trigger a shot.
        WoWStatusJournal.recordLocal({id="x", kind="level", at=time(), data={level=20}, group_ids={}})
        runTimers()
        assert(#__shots == 0)
    ''')


def test_no_screenshot_function_hides_the_options():
    lua = make_lua(SHOTS + 'Screenshot = nil')
    lua.execute('''
        for _, entry in ipairs(WoWStatusSetup.checks) do assert(entry.group ~= "screenshots") end
        options().level = true
        fire("PLAYER_LEVEL_UP", 10); runTimers()
        assert(#character().events == 1)
    ''')


def test_hide_interface_hides_for_the_next_frame_and_always_restores():
    lua = make_lua(SHOTS)
    lua.execute('''
        options().level = true; options().hide_ui = true
        fire("PLAYER_LEVEL_UP", 10)
        table.remove(__timers, 1).fn()   -- the one-second delay
        assert(__uiShown == false and #__shots == 0)
        table.remove(__timers, 1).fn()   -- next frame
        assert(#__shots == 1 and __shots[1].ui == false)
        fire("SCREENSHOT_SUCCEEDED")
        assert(__uiShown == true)
        runTimers()                      -- the stale fallback changes nothing
        assert(__uiShown == true)
    ''')


def test_interface_is_restored_by_the_fallback_when_no_event_arrives_or_the_shot_fails():
    lua = make_lua(SHOTS)
    lua.execute('''
        options().level = true; options().hide_ui = true
        fire("PLAYER_LEVEL_UP", 10); runTimers()
        assert(#__shots == 1 and __uiShown == true)
        Screenshot = function() error("disk full") end
        fire("PLAYER_LEVEL_UP", 11)
        table.remove(__timers, 1).fn(); assert(__uiShown == false)
        table.remove(__timers, 1).fn(); assert(__uiShown == true)
    ''')


def test_combat_takes_a_normal_screenshot_and_combat_start_restores_the_interface():
    lua = make_lua(SHOTS)
    lua.execute('''
        options().level = true; options().hide_ui = true
        __combat = true
        fire("PLAYER_LEVEL_UP", 10); runTimers()
        assert(#__shots == 1 and __shots[1].ui == true and __uiShown == true)
        fire("SCREENSHOT_SUCCEEDED")
        __combat = false
        fire("PLAYER_LEVEL_UP", 11)
        table.remove(__timers, 1).fn(); assert(__uiShown == false)
        fire("PLAYER_REGEN_DISABLED")    -- fires before lockdown begins
        assert(__uiShown == true)
        __combat = true
        runTimers()
        assert(__uiShown == true and #__shots == 2)
    ''')


def test_manual_screenshot_command_honours_the_hide_option():
    lua = make_lua(SHOTS)
    lua.execute('''
        options().hide_ui = true
        SlashCmdList.WOWSTATUS("screenshot")
        assert(__uiShown == false)
        runTimers()
        assert(#__shots == 1 and __shots[1].ui == false and __uiShown == true)
    ''')
