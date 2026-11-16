"""How long a notification stays: a setting, a command and a Hold binding (#159)."""
from pathlib import Path

from test_addon import run_addon_file
from test_journal import actor, clock

ROOT = Path(__file__).resolve().parents[1]

PICK = '''
    function __pick(button, label)
        button.OnClick(button)
        local names, found = {}, nil
        for _, row in ipairs(WoWStatusMenu.rows) do
            if row:IsShown() then
                names[#names + 1] = row.text.text
                if row.text.text == label then found = row end
            end
        end
        if not found then error("no " .. label .. " in " .. table.concat(names, ", ")) end
        found.OnClick(found)
        return names
    end
'''


def shown(lua):
    return lua.eval('WoWStatusLevelPopup ~= nil and WoWStatusLevelPopup:IsShown()') is True


def test_lifetime_and_fade_follow_the_duration_with_six_seconds_as_default():
    lua = actor('Thora')
    lua.execute('''
        local P = WoWStatusPopups
        assert(P.duration() == 6)
        local life, tail = P.lifetime()
        assert(life == 6 and tail == .5) -- The old fixed length and half-second fade.
        life, tail = P.lifetime(20)
        assert(life == 20 and math.abs(tail - 20 / 12) < 1e-9)
        life, tail = P.lifetime(3)
        assert(life == 3 and tail == .25)
        life, tail = P.lifetime(0)
        assert(life == math.huge and tail == 0)
    ''')


def test_duration_setting_is_kept_in_range_and_saved_account_wide():
    lua = actor('Thora')
    lua.execute('''
        local P = WoWStatusPopups
        assert(P.setDuration(12) and P.duration() == 12 and WoWStatusDB.popups.popup_duration == 12)
        assert(not P.setDuration(2) and not P.setDuration(21) and not P.setDuration("long"))
        assert(not P.setDuration(0/0) and P.duration() == 12)
        assert(P.setDuration(" 8 ") and P.duration() == 8)
        assert(P.setDuration(0) and P.duration() == 0 and P.durationLabel() == "Until dismissed")
        -- The default is not stored, so a later default change reaches everyone.
        assert(P.setDuration(6) and WoWStatusDB.popups.popup_duration == nil)
        -- A broken saved value falls back to the default.
        WoWStatusDB.popups.popup_duration = 999
        assert(P.duration() == 6)
        assert(P.durationLabel(15) == "15 seconds")
    ''')


def test_a_longer_duration_keeps_the_notification_and_delays_the_next_one():
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute('''
        WoWStatusPopups.setDuration(12)
        WoWStatusPopups.preview("level"); WoWStatusPopups.preview("zone")
    ''')
    assert shown(lua)
    lua.execute('''
        local toast = WoWStatusLevelPopup
        assert(toast.item.kind == "level" and toast.life == 12 and toast.tail == 1)
        toast.OnUpdate(toast, 6) -- Past the old six seconds: still fully visible.
        assert(toast:IsShown() and toast.alpha == 1)
        toast.OnUpdate(toast, 5.5) -- Halfway through its one-second fade.
        assert(math.abs(toast.alpha - .5) < 1e-9)
    ''')
    clock(lua, 21)
    lua.eval('WoWStatusPopups.tick')()
    assert lua.eval('WoWStatusLevelPopup.item.kind') == 'level'
    # While its own countdown runs, tick() leaves it alone (time() is whole seconds).
    clock(lua, 22)
    lua.eval('WoWStatusPopups.tick')()
    assert shown(lua) and lua.eval('WoWStatusLevelPopup.item.kind') == 'level'
    lua.execute('WoWStatusLevelPopup.OnUpdate(WoWStatusLevelPopup, .5)')
    lua.eval('WoWStatusPopups.tick')()
    assert not shown(lua)  # A second's pause between notifications, as before.
    clock(lua, 23)
    lua.eval('WoWStatusPopups.tick')()
    assert shown(lua) and lua.eval('WoWStatusLevelPopup.item.kind') == 'zone'


def test_the_default_still_hides_after_six_seconds():
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute('WoWStatusPopups.preview("level"); WoWStatusPopups.preview("zone"); WoWStatusPopups.tick()')
    lua.execute('''
        local toast = WoWStatusLevelPopup
        toast.OnUpdate(toast, 5.75)
        assert(toast:IsShown() and math.abs(toast.alpha - .5) < 1e-9)
        toast.OnUpdate(toast, .25)
    ''')
    clock(lua, 16)
    lua.eval('WoWStatusPopups.tick')()
    assert not shown(lua)
    clock(lua, 17)
    lua.eval('WoWStatusPopups.tick')()
    assert lua.eval('WoWStatusLevelPopup.item.kind') == 'zone'


def test_until_dismissed_stays_until_clicked_away_and_then_the_next_follows():
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute('''
        WoWStatusPopups.setDuration(0)
        WoWStatusPopups.preview("level"); WoWStatusPopups.preview("zone"); WoWStatusPopups.tick()
        local toast = WoWStatusLevelPopup
        toast.OnUpdate(toast, 1000)
        assert(toast:IsShown() and toast.alpha == 1)
    ''')
    clock(lua, 2000)
    lua.eval('WoWStatusPopups.tick')()
    assert lua.eval('WoWStatusLevelPopup.item.kind') == 'level'
    assert lua.eval('WoWStatusPopups.dismiss()') is True
    lua.eval('WoWStatusPopups.tick')()
    assert shown(lua) and lua.eval('WoWStatusLevelPopup.item.kind') == 'zone'


def test_dismissing_a_long_notification_shows_the_next_one_at_once():
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute('''
        WoWStatusPopups.setDuration(20)
        WoWStatusPopups.preview("level"); WoWStatusPopups.preview("zone"); WoWStatusPopups.tick()
    ''')
    clock(lua, 12)
    assert lua.eval('WoWStatusPopups.dismiss()') is True
    lua.eval('WoWStatusPopups.tick')()
    assert lua.eval('WoWStatusLevelPopup.item.kind') == 'zone'


def test_the_hold_binding_pauses_the_countdown_like_hovering():
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute('WoWStatusPopups.preview("level"); WoWStatusPopups.tick()')
    lua.execute('''
        local toast = WoWStatusLevelPopup
        toast.OnUpdate(toast, .3)
        WoWStatusGamepad.hold("down")
        toast.OnUpdate(toast, 30)
        assert(toast:IsShown() and toast.alpha == 1)
    ''')
    clock(lua, 40)
    lua.eval('WoWStatusPopups.tick')()
    assert shown(lua)
    lua.execute('''
        WoWStatusGamepad.hold("up")
        local toast = WoWStatusLevelPopup
        toast.OnUpdate(toast, 3) -- Counting down again from a second.
    ''')
    # Released: the countdown and fade run their course; tick() does not cut it off.
    clock(lua, 43)
    lua.eval('WoWStatusPopups.tick')()
    assert shown(lua)
    lua.execute('WoWStatusLevelPopup.OnUpdate(WoWStatusLevelPopup, 3)')
    assert not shown(lua)


def test_a_hold_does_not_carry_over_to_the_next_notification():
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute('''
        WoWStatusPopups.preview("level"); WoWStatusPopups.preview("zone"); WoWStatusPopups.tick()
        WoWStatusGamepad.hold("down")
        assert(WoWStatusPopups.held())
        WoWStatusPopups.dismiss()
        assert(not WoWStatusPopups.held())
    ''')


def test_options_dropdown_sets_the_duration_and_shows_a_sample():
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute(PICK)
    lua.execute('''
        WoWStatusPreviews.show()
        local panel = WoWStatusNotificationPreviews
        local pick = panel.popupDuration
        assert(pick.kind == "Button" and pick.OnClick and pick.text == "6 seconds")
        local names = __pick(pick, "12 seconds")
        assert(names[1] == "3 seconds" and names[#names] == "Until dismissed" and #names == 10)
        assert(WoWStatusPopups.duration() == 12 and pick.text == "12 seconds")
        WoWStatusPopups.tick()
        assert(WoWStatusLevelPopup:IsShown() and WoWStatusLevelPopup.life == 12)
        __pick(pick, "Until dismissed")
        assert(WoWStatusPopups.duration() == 0 and pick.text == "Until dismissed")
    ''')


def test_popuptime_command_sets_and_reports_the_duration():
    lua = actor('Thora')
    lua.execute('''
        __said = {}
        local frame = DEFAULT_CHAT_FRAME
        local add = frame.AddMessage
        function frame:AddMessage(text) table.insert(__said, text); if add then add(self, text) end end
        SlashCmdList.WOWSTATUS("popuptime 10")
        assert(WoWStatusPopups.duration() == 10 and __said[#__said]:find("stay for 10 seconds", 1, true))
        SlashCmdList.WOWSTATUS("popuptime 25")
        assert(WoWStatusPopups.duration() == 10 and __said[#__said]:find("popuptime 3-20", 1, true))
        SlashCmdList.WOWSTATUS("popuptime")
        assert(WoWStatusPopups.duration() == 10 and __said[#__said - 1]:find("stay for 10 seconds", 1, true))
        SlashCmdList.WOWSTATUS("popuptime 0")
        assert(WoWStatusPopups.duration() == 0 and __said[#__said]:find("until dismissed", 1, true))
    ''')


def test_duration_texts_are_in_nynorsk():
    lua = actor('Thora')
    lua.execute('''
        WoWStatusLocale.set("nn")
        assert(WoWStatusPopups.durationLabel(8) == "8 sekund")
        assert(WoWStatusPopups.durationLabel(0) == "Til du lukkar dei")
        WoWStatusGamepad.bindingNames()
        assert(BINDING_NAME_WOWSTATUS_HOLD == "Hald varselet framme (medan tasten er nede)")
    ''')


def test_tick_hides_on_time_while_the_ui_is_hidden():
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute('''
        WoWStatusPopups.preview("level"); WoWStatusPopups.tick()
        local toast = WoWStatusLevelPopup
        toast.OnUpdate(toast, 2)
        toast.parent = {IsVisible=function() return false end} -- Alt+Z: OnUpdate stops.
    ''')
    clock(lua, 16)
    lua.eval('WoWStatusPopups.tick')()
    assert not shown(lua)


def test_after_combat_the_next_waits_one_second_not_the_full_duration():
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute('''
        WoWStatusPopups.setDuration(20)
        WoWStatusPopups.preview("level"); WoWStatusPopups.tick()
        WoWStatusLevelPopup.OnUpdate(WoWStatusLevelPopup, 2)
    ''')
    clock(lua, 12)
    lua.execute('__combat = true; function UnitAffectingCombat() return true end')
    lua.eval('WoWStatusPopups.tick')()
    assert not shown(lua)
    clock(lua, 15)
    lua.execute('__combat = false; function UnitAffectingCombat() return false end')
    lua.eval('WoWStatusPopups.tick')()
    assert not shown(lua)  # A second's pause after combat ...
    clock(lua, 16)
    lua.eval('WoWStatusPopups.tick')()
    assert shown(lua)  # ... not until 20 seconds after it first showed.


def test_a_hold_without_a_key_state_switches_on_and_off():
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute('''
        WoWStatusPopups.preview("level"); WoWStatusPopups.tick()
        WoWStatusGamepad.hold()
        assert(WoWStatusPopups.held())
        WoWStatusGamepad.hold()
        assert(not WoWStatusPopups.held())
    ''')


def test_changing_the_duration_replaces_the_sample_instead_of_queueing_more():
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute(PICK)
    lua.execute('''
        WoWStatusPreviews.show()
        local pick = WoWStatusNotificationPreviews.popupDuration
        __pick(pick, "12 seconds"); WoWStatusPopups.tick()
        __pick(pick, "20 seconds"); __pick(pick, "Until dismissed")
        SlashCmdList.WOWSTATUS("popuptime 8")
        WoWStatusPopups.tick()
        local toast = WoWStatusLevelPopup
        assert(toast:IsShown() and toast.life == 8)
        assert(WoWStatusPopups.dismiss())
        WoWStatusPopups.tick()
        assert(not toast:IsShown()) -- No older samples were left waiting.
    ''')


def test_the_duration_dropdown_is_a_controller_control_and_does_not_overlap():
    lua = actor('Thora')
    lua.execute('''
        local methods = getmetatable(CreateFrame("Frame")).__index
        local setPoint = methods.SetPoint
        function methods:SetPoint(...) self.__point = {...}; if setPoint then return setPoint(self, ...) end end
        methods.GetObjectType = methods.GetObjectType or function(self) return self.kind end
        methods.GetScript = methods.GetScript or function(self, name) return self[name] end
        methods.IsEnabled = methods.IsEnabled or function() return true end
    ''')
    run_addon_file(lua, ROOT / 'addon/vanilla/WoWStatus/Previews.lua')  # Built again with the hooks.
    lua.execute('''
        WoWStatusPreviews.show()
        local panel = WoWStatusNotificationPreviews
        local pick = panel.popupDuration
        assert(pick.parent == panel and WoWStatusGamepad.interactive(pick))
        local function top(widget) return widget.__point[3] end
        -- Its row sits between the size row and the language row, 30 px buttons apart.
        assert(top(panel.popupSize) - top(pick) >= 34 and top(pick) - top(panel.languageSwitch) >= 34)
    ''')


def test_a_lost_key_up_stops_holding_after_a_minute():
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute('''
        WoWStatusPopups.preview("level"); WoWStatusPopups.tick()
        WoWStatusGamepad.hold("down")
        assert(WoWStatusPopups.held())
    ''')
    clock(lua, 71)
    assert lua.eval('WoWStatusPopups.held()') is False


def test_a_hold_with_nothing_shown_does_nothing():
    lua = actor('Thora')
    lua.execute('''
        WoWStatusGamepad.hold()
        assert(not WoWStatusPopups.holding())
    ''')


def test_a_stopped_countdown_still_hides_two_seconds_late_at_most():
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute('WoWStatusPopups.preview("level"); WoWStatusPopups.tick()')
    lua.execute('WoWStatusLevelPopup.OnUpdate(WoWStatusLevelPopup, 1)')  # ... and then never again.
    clock(lua, 17)
    lua.eval('WoWStatusPopups.tick')()
    assert shown(lua)
    clock(lua, 18)
    lua.eval('WoWStatusPopups.tick')()
    assert not shown(lua)


def test_a_new_sample_keeps_the_previews_the_player_asked_for():
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute('''
        WoWStatusPopups.preview("death"); WoWStatusPopups.preview("zone")
        SlashCmdList.WOWSTATUS("popuptime 8")
        local toast = WoWStatusLevelPopup
        assert(toast.item.kind == "death")
        assert(WoWStatusPopups.dismiss()); WoWStatusPopups.tick()
        assert(toast.item.kind == "zone")
        assert(WoWStatusPopups.dismiss()); WoWStatusPopups.tick()
        assert(toast.item.kind == "level" and toast.item.sample)
    ''')
