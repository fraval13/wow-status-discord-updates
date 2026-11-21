"""Quiet hours (#180): friends' notifications stay off screen during a daily clock window.

The test clock starts at 07:33 (UTC stands in for the local clock here). Updates
arriving in the window go to the activity log only and never come back as popups.
"""
import pytest
from test_addon import make_lua
from test_journal import actor, clock, deliver_popup

MINUTE = 60
START = 7 * 60 + 33  # The test clock's minute of the day at offset 0.


def at_minute(lua, minute_of_day):
    """Move the clock forward to the given minute of the day (wrapping to the next day)."""
    clock(lua, ((minute_of_day - START) % (24 * 60)) * MINUTE + 10)


def level_up():
    own, friend = actor('Mira'), actor('Thora')
    clock(own, 10)
    clock(friend, 10)
    own.eval('fire')('PLAYER_LEVEL_UP', 42)
    return own, friend


def shown(lua):
    return bool(lua.eval('WoWStatusLevelPopup ~= nil and WoWStatusLevelPopup:IsShown()'))


def logged_level(lua):
    return lua.eval('''(function()
        for _, e in ipairs(WoWStatusJournal.entries()) do
            if e.kind == "level" and e.level == 42 and not e.owner then return true end
        end
        return false
    end)()''')


@pytest.mark.parametrize('start, stop, minute, inside', [
    (22 * 60, 7 * 60, 23 * 60, True),       # Crosses midnight: late evening.
    (22 * 60, 7 * 60, 3 * 60, True),        # Crosses midnight: small hours.
    (22 * 60, 7 * 60, 7 * 60, False),       # The end minute is outside.
    (22 * 60, 7 * 60, 22 * 60, True),       # The start minute is inside.
    (22 * 60, 7 * 60, 12 * 60, False),
    (9 * 60, 17 * 60, 12 * 60, True),       # Same day.
    (9 * 60, 17 * 60, 20 * 60, False),
    (8 * 60, 8 * 60, 8 * 60, False),        # Equal start and end: never quiet.
    (8 * 60, 8 * 60, 20 * 60, False),
])
def test_window_membership(start, stop, minute, inside):
    lua = make_lua()
    assert lua.eval(f'WoWStatusPopups.inQuietHours({minute}, {start}, {stop})') is inside


def test_quiet_hours_are_off_by_default_and_popups_show():
    own, friend = level_up()
    assert friend.eval('WoWStatusPopups.quietHours().enabled') is False
    deliver_popup(own, friend)
    friend.eval('WoWStatusPopups.tick')()
    assert shown(friend)
    assert friend.eval('WoWStatusPopups.quietHoursText()') is None


def test_a_window_across_midnight_hides_notifications_logs_them_and_never_replays_them():
    own, friend = level_up()
    friend.execute('''
        WoWStatusPopups.setQuietHours("start", 23 * 60)
        WoWStatusPopups.setQuietHours("stop", 8 * 60)
        WoWStatusPopups.setQuietHours("enabled", true)
    ''')
    assert friend.eval('WoWStatusPopups.quietHoursActive()') is True  # 07:33
    assert friend.eval('WoWStatusPopups.quietHoursText()') == 'Quiet hours until 08:00'
    deliver_popup(own, friend)
    friend.eval('WoWStatusPopups.tick')()
    assert not shown(friend)
    assert logged_level(friend)
    assert friend.eval('WoWStatusDB.popups.last_receive.state') == 'quiet_hours'
    # After the window: nothing comes back as a popup.
    at_minute(friend, 8 * 60 + 1)
    assert friend.eval('WoWStatusPopups.quietHoursActive()') is False
    for step in range(3):
        clock(friend, 30 * MINUTE + step * 10)
        friend.eval('WoWStatusPopups.tick')()
        assert not shown(friend)


def test_a_popup_from_before_the_window_leaves_and_never_comes_back():
    own, friend = level_up()
    friend.execute('WoWStatusPopups.setQuietHours("start", 7 * 60 + 35); WoWStatusPopups.setQuietHours("stop", 9 * 60)')
    friend.execute('WoWStatusPopups.setQuietHours("enabled", true)')
    deliver_popup(own, friend)
    friend.eval('WoWStatusPopups.tick')()
    assert shown(friend)  # 07:33, before the window.
    at_minute(friend, 7 * 60 + 35)
    friend.eval('WoWStatusPopups.tick')()
    assert not shown(friend)
    assert logged_level(friend)
    at_minute(friend, 9 * 60 + 1)
    friend.eval('WoWStatusPopups.tick')()
    assert not shown(friend)


def test_a_burst_in_quiet_hours_is_all_logged_and_previews_still_show():
    # Nothing is queued in quiet hours, so the per-sender cap never drops an update from the log.
    own, friend = actor('Mira'), actor('Thora')
    clock(own, 10)
    clock(friend, 10)
    friend.execute('''
        WoWStatusPopups.setQuietHours("start", 0)
        WoWStatusPopups.setQuietHours("stop", 23 * 60)
        WoWStatusPopups.setQuietHours("enabled", true)
    ''')
    friend.execute('__peers = {"Mira-TestRealm", "Thora-TestRealm"}')
    own.execute('__peers = {"Mira-TestRealm", "Thora-TestRealm"}')
    delivered = 0
    for step, level in enumerate(range(40, 46)):
        clock(own, 10 + step * 20)
        clock(friend, 10 + step * 20)
        own.eval('fire')('PLAYER_LEVEL_UP', level)
        for _ in range(20):
            own.eval('WoWStatusPopups.tick')()
            own.execute('__mono = __mono + 1; __now = __now + 1')
        for i in range(delivered + 1, own.eval('#__sent') + 1):
            packet = own.eval(f'__sent[{i}]')
            if packet['prefix'] == 'WoWStatus' and packet['target'].startswith('Thora'):
                friend.eval('fire')('CHAT_MSG_ADDON', 'WoWStatus', packet['text'], 'WHISPER', 'Mira-TestRealm')
        delivered = own.eval('#__sent')
    levels = friend.eval('''(function()
        local n = 0
        for _, e in ipairs(WoWStatusJournal.entries()) do
            if e.kind == "level" and not e.owner then n = n + 1 end
        end
        return n
    end)()''')
    assert levels == 6
    friend.execute('WoWStatusPopups.preview("level"); WoWStatusPopups.tick()')
    assert shown(friend)


def test_an_update_waiting_for_the_roster_across_the_end_never_pops_up():
    own, friend = level_up()
    friend.execute('''
        WoWStatusPopups.setQuietHours("start", 23 * 60)
        WoWStatusPopups.setQuietHours("stop", 7 * 60 + 34)
        WoWStatusPopups.setQuietHours("enabled", true)
    ''')
    # The sender is not in the roster yet, so the update waits to be verified.
    packet = own.eval('__sent[1].text')
    friend.eval('fire')('CHAT_MSG_ADDON', 'WoWStatus', packet, 'WHISPER', 'Mira-TestRealm')
    assert friend.eval('WoWStatusDB.popups.last_receive.state') == 'verifying_sender'
    at_minute(friend, 7 * 60 + 34)  # The window has ended; now the roster lists Mira.
    friend.execute('__peers = {"Mira-TestRealm", "Thora-TestRealm"}')
    for step in range(3):
        clock(friend, 2 * MINUTE + 10 + step)
        friend.eval('WoWStatusPopups.tick')()
    assert logged_level(friend)
    assert not shown(friend)
    assert friend.eval('WoWStatusDB.popups.last_receive.state') == 'quiet_hours'


def test_friends_reactions_are_not_read_aloud_in_quiet_hours():
    """Someone may be asleep nearby: a friend's voiced GZ! stays text-only (Forever voices)."""
    from test_spoken_reactions import VOICE_DATA
    own, friend = actor('Mira'), actor('Thora')
    for lua in (own, friend):
        lua.execute(VOICE_DATA)
    friend.execute('''
        WoWStatusPopups.CLICK_GUARD = 0
        WoWStatusPersonalities.setReaction("wholesome")
        WoWStatusLocale.set("nn")
        WoWStatusVoices.SAMPLE_SHARE = 1
    ''')
    clock(own, 10)
    clock(friend, 10)
    own.eval('fire')('PLAYER_LEVEL_UP', 42)
    deliver_popup(own, friend)
    whispered = friend.eval('''(function()
        WoWStatusPopups.tick()
        local button = WoWStatusLevelPopup.reactions[1]
        button.OnClick(button)
        return WoWStatusLevelPopup.item.whispered
    end)()''')
    own.execute(f'''
        WoWStatusPopups.setQuietHours("start", 0)
        WoWStatusPopups.setQuietHours("stop", 23 * 60)
        WoWStatusPopups.setQuietHours("enabled", true)
        __peers = {{"Mira-TestRealm", "Thora-TestRealm"}}
        for id in pairs(character().group_ids) do WoWStatusPopups.peers(id) end
        for _ = 1, 3 do WoWStatusPopups.tick() end
        fire("CHAT_MSG_WHISPER", {whispered!r}, "Thora-TestRealm")
        assert(#__played == 0, "read aloud in quiet hours")
    ''')


def test_outside_the_window_and_with_equal_times_popups_show():
    own, friend = level_up()
    friend.execute('''
        WoWStatusPopups.setQuietHours("start", 8 * 60)
        WoWStatusPopups.setQuietHours("stop", 8 * 60)
        WoWStatusPopups.setQuietHours("enabled", true)
    ''')
    deliver_popup(own, friend)
    friend.eval('WoWStatusPopups.tick')()
    assert shown(friend)


def test_settings_previews_still_show_in_quiet_hours():
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute('''
        WoWStatusPopups.setQuietHours("start", 0)
        WoWStatusPopups.setQuietHours("stop", 23 * 60)
        WoWStatusPopups.setQuietHours("enabled", true)
        assert(WoWStatusPopups.quietHoursActive())
        WoWStatusPopups.preview("death")
        WoWStatusPopups.tick()
        assert(WoWStatusLevelPopup:IsShown())
        -- A local notice about a friend (a new First) is skipped instead; the player's own is not.
        assert(WoWStatusPopups.notice({sender="Mira-TestRealm", kind="first", text="First!"}) == false)
        assert(WoWStatusPopups.notice({sender="Thora-TestRealm", kind="first", text="First!"}) == true)
    ''')


def test_quiet_hours_and_instance_quiet_mode_are_independent():
    lua = make_lua()
    lua.execute('''
        WoWStatusPopups.setQuietHours("enabled", true)
        assert(not WoWStatusPopups.quietSettings().enabled)
        WoWStatusPopups.setQuiet("enabled", true)
        WoWStatusPopups.setQuietHours("enabled", false)
        assert(WoWStatusPopups.quietSettings().enabled)
        assert(not WoWStatusPopups.quietHours().enabled)
    ''')


@pytest.mark.parametrize('saved', [
    '"broken"', '{enabled="yes", start="ten", stop=-5}', '{start=1440, stop=7.5}', '{start=0/0, stop=1/0}',
])
def test_malformed_saved_values_fall_back_to_safe_defaults(saved):
    lua = make_lua()
    lua.execute(f'WoWStatusDB.popups.quiet_hours = {saved}')
    hours = lua.eval('WoWStatusPopups.quietHours()')
    assert hours.enabled is False
    assert (hours.start, hours.stop) == (22 * 60, 7 * 60)
    assert lua.eval('WoWStatusPopups.quietHoursActive()') is False


def test_setters_refuse_bad_values_and_shifts_wrap_round_midnight():
    lua = make_lua()
    lua.execute('''
        local P = WoWStatusPopups
        assert(not P.setQuietHours("start", 1440) and not P.setQuietHours("start", "x") and not P.setQuietHours("other", 1))
        assert(P.quietHours().start == 22 * 60)
        P.setQuietHours("start", 23 * 60 + 30)
        P.shiftQuietHours("start", 1)
        assert(P.quietHours().start == 0, P.quietHours().start)
        P.shiftQuietHours("start", -1)
        assert(P.quietHours().start == 23 * 60 + 30)
        assert(P.clockText(7 * 60 + 5) == "07:05")
        assert(P.parseClock("7:05") == 425 and P.parseClock("23:59") == 1439)
        assert(P.parseClock("24:00") == nil and P.parseClock("7:60") == nil and P.parseClock("x") == nil)
    ''')


def test_the_local_clock_is_optional():
    lua = make_lua()
    lua.execute('''
        date = nil
        WoWStatusPopups.setQuietHours("start", 0)
        WoWStatusPopups.setQuietHours("stop", 23 * 60)
        WoWStatusPopups.setQuietHours("enabled", true)
        assert(not WoWStatusPopups.quietHoursActive())
    ''')


def test_slash_command_sets_and_reports_quiet_hours():
    lua = make_lua()
    lua.execute('''
        __said = {}
        local add = DEFAULT_CHAT_FRAME.AddMessage
        DEFAULT_CHAT_FRAME.AddMessage = function(self, text) table.insert(__said, text) end
        SlashCmdList.WOWSTATUS("quiethours 21:30-6:00")
        DEFAULT_CHAT_FRAME.AddMessage = add
    ''')
    hours = lua.eval('WoWStatusPopups.quietHours()')
    assert hours.enabled is True and (hours.start, hours.stop) == (21 * 60 + 30, 6 * 60)
    assert 'Quiet hours on (local time): 21:30-06:00' in lua.eval('__said[1]')
    lua.execute('SlashCmdList.WOWSTATUS("quiethours off")')
    assert lua.eval('WoWStatusPopups.quietHours().enabled') is False
    lua.execute('SlashCmdList.WOWSTATUS("quiethours 25:00-6:00")')
    assert lua.eval('WoWStatusPopups.quietHours().start') == 21 * 60 + 30
    lua.execute('SlashCmdList.WOWSTATUS("quiethours 21:00 - 6:30")')
    assert lua.eval('WoWStatusPopups.quietHours().start') == 21 * 60
    lua.execute('SlashCmdList.WOWSTATUS("quiethours 21:30-6:00")')
    assert lua.eval('WoWStatusPopups.quietHours().start') == 21 * 60 + 30
    lua.execute('SlashCmdList.WOWSTATUS("quiethours on  ")')
    assert lua.eval('WoWStatusPopups.quietHours().enabled') is True
    lua.execute('''
        __said = {}
        local add = DEFAULT_CHAT_FRAME.AddMessage
        DEFAULT_CHAT_FRAME.AddMessage = function(self, text) table.insert(__said, text) end
        SlashCmdList.WOWSTATUS("quiethours 8:00-8:00")
        DEFAULT_CHAT_FRAME.AddMessage = add
    ''')
    assert 'Same start and end: never quiet' in lua.eval('__said[2]')


def test_notifications_page_has_quiet_hours_controls_a_controller_can_reach():
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute('''
        WoWStatusPreviews.show()
        local panel = WoWStatusNotificationPreviews
        panel.settingsCategories:select("quiet")
        assert(not panel.quietHours:GetChecked())
        assert(panel.quietClock.start.text == "22:00" and panel.quietClock.stop.text == "07:00")
        panel.quietHours:SetChecked(true); panel.quietHours.OnClick(panel.quietHours)
        assert(WoWStatusPopups.quietHours().enabled)
        panel.quietClock.startLater.OnClick(panel.quietClock.startLater)
        assert(WoWStatusPopups.quietHours().start == 22 * 60 + 30 and panel.quietClock.start.text == "22:30")
        panel.quietClock.stopEarlier.OnClick(panel.quietClock.stopEarlier)
        assert(WoWStatusPopups.quietHours().stop == 6 * 60 + 30 and panel.quietClock.stop.text == "06:30")
        -- 07:33 is outside 22:30-06:30; a window covering it shows the indicator.
        assert(panel.quietState.text == "")
        WoWStatusPopups.setQuietHours("stop", 8 * 60); panel.refreshQuietHours()
        assert(panel.quietState.text == "Quiet hours until 08:00")
        -- The label follows the clock while the page stays open.
        __now = __now + 30 * 60
        panel.OnUpdate(panel, 1)
        assert(panel.quietState.text == "")
        -- Gamepad.lua reaches enabled Buttons/CheckButtons with an OnClick on the panel.
        local methods = getmetatable(panel).__index
        function methods:GetObjectType() return self.kind end
        function methods:GetScript(name) return self[name] end
        function methods:IsEnabled() return true end
        for _, control in ipairs({panel.quietHours, panel.quietClock.startEarlier, panel.quietClock.startLater,
                panel.quietClock.stopEarlier, panel.quietClock.stopLater}) do
            assert(control.parent == panel.settingsCategories.frames.quiet and WoWStatusGamepad.interactive(control))
        end
    ''')
