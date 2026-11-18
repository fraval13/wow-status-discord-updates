"""Reduce motion: notifications that do not slide, fade or pulse (#184)."""
from pathlib import Path

import pytest
from test_addon import run_addon_file
from test_client_compatibility import client_runtime
from test_journal import actor, clock

ROOT = Path(__file__).resolve().parents[1]

# Records the toast's vertical offset each time it is anchored.
TRACK_POINTS = '''
    local methods = getmetatable(CreateFrame("Frame")).__index
    local setPoint = methods.SetPoint
    function methods:SetPoint(...)
        self.__point = {...}
        if setPoint then return setPoint(self, ...) end
    end
'''


def offset(lua):
    return lua.eval('WoWStatusLevelPopup.__point[#WoWStatusLevelPopup.__point]')


@pytest.mark.parametrize('edition', ['vanilla', 'forever', 'tbc', 'retail'])
def test_alpha_position_and_glow_stay_still_across_ticks(edition):
    lua = client_runtime(edition)
    lua.execute(TRACK_POINTS)
    lua.execute('''
        WoWStatusPopups.setReduceMotion(true)
        WoWStatusPopups.preview("level"); WoWStatusPopups.tick()
        local toast = WoWStatusLevelPopup
        assert(toast:IsShown() and toast.alpha == 1 and toast.glow.alpha == WoWStatusPopups.STEADY_GLOW)
        __seen = {}
        for _, step in ipairs({0, .05, .1, .2, .5, 1.3, 2, 1.5}) do -- Entrance, middle and the old fade.
            toast.OnUpdate(toast, step)
            assert(toast:IsShown(), "hid early")
            __seen[#__seen + 1] = {toast.alpha, toast.glow.alpha}
        end
    ''')
    seen = lua.eval('__seen')
    assert {(row[1], row[2]) for row in seen.values()} == {(1, 0.5)}
    assert offset(lua) == -170  # Never dropped for a slide-in.
    # At the end it simply goes, without fading.
    lua.execute('WoWStatusLevelPopup.OnUpdate(WoWStatusLevelPopup, .5)')
    assert lua.eval('WoWStatusLevelPopup:IsShown()') is False


def test_default_still_slides_fades_and_pulses():
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute(TRACK_POINTS)
    lua.execute('''
        assert(not WoWStatusPopups.reduceMotion())
        WoWStatusPopups.preview("level"); WoWStatusPopups.tick()
        local toast = WoWStatusLevelPopup
        assert(toast.alpha == 0)
        toast.OnUpdate(toast, .11)
        assert(math.abs(toast.alpha - .5) < 1e-9)
        assert(toast.__point[#toast.__point] < -170) -- Still sliding in.
        __glow = toast.glow.alpha
        toast.OnUpdate(toast, .2)
        assert(toast.glow.alpha ~= __glow)
    ''')
    assert offset(lua) == -170  # Settled once the entrance is over.


def test_big_banners_and_custom_durations_stay_still_too():
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute('''
        WoWStatusPopups.setReduceMotion(true)
        WoWStatusPopups.setDuration(12)
        WoWStatusPopups.preview("level")
        WoWStatusPopups.tick()
        local toast = WoWStatusLevelPopup
        local scale = toast.scale
        for _ = 1, 10 do
            toast.OnUpdate(toast, 1.15)
            assert(toast.alpha == 1 and toast.glow.alpha == WoWStatusPopups.STEADY_GLOW and toast.scale == scale)
        end
        toast.OnUpdate(toast, .5)
        assert(not toast:IsShown())
    ''')


def test_turning_it_on_settles_a_toast_already_on_screen():
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute(TRACK_POINTS)
    lua.execute('''
        WoWStatusPopups.preview("level"); WoWStatusPopups.tick()
        local toast = WoWStatusLevelPopup
        toast.OnUpdate(toast, .05) -- Mid-slide, half transparent.
        assert(toast.alpha < 1)
        WoWStatusPopups.setReduceMotion(true)
        toast.OnUpdate(toast, .05) -- Settled on the next frame.
        assert(toast.alpha == 1 and toast.glow.alpha == WoWStatusPopups.STEADY_GLOW)
    ''')
    assert offset(lua) == -170


def test_setting_is_saved_account_wide_and_only_true_counts():
    lua = actor('Thora')
    lua.execute('''
        local P = WoWStatusPopups
        P.setReduceMotion(true)
        assert(P.reduceMotion() and WoWStatusDB.popups.reduce_motion == true and P.options().reduce_motion)
        P.setReduceMotion(false)
        assert(not P.reduceMotion() and WoWStatusDB.popups.reduce_motion == nil)
        -- A broken saved value means off.
        for _, value in ipairs({"yes", 1, {}}) do
            WoWStatusDB.popups.reduce_motion = value
            assert(not P.reduceMotion())
        end
    ''')


def test_options_tick_switches_it_and_shows_a_still_sample():
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute('''
        WoWStatusPreviews.show()
        local panel = WoWStatusNotificationPreviews
        local tick = panel.reduceMotion
        assert(tick.kind == "CheckButton" and tick.OnClick and not tick.checked)
        tick:SetChecked(true); tick.OnClick(tick)
        assert(WoWStatusPopups.reduceMotion())
        WoWStatusPopups.tick()
        local toast = WoWStatusLevelPopup
        assert(toast:IsShown() and toast.item.sample and toast.alpha == 1)
        tick:SetChecked(false); tick.OnClick(tick)
        assert(not WoWStatusPopups.reduceMotion())
        -- Reopening shows the saved state.
        WoWStatusPopups.setReduceMotion(true)
        panel:Hide(); WoWStatusPreviews.show()
        assert(tick.checked == true)
    ''')


def test_the_tick_is_a_controller_control_beside_big_banners():
    lua = actor('Thora')
    lua.execute(TRACK_POINTS + '''
        local methods = getmetatable(CreateFrame("Frame")).__index
        methods.GetObjectType = methods.GetObjectType or function(self) return self.kind end
        methods.GetScript = methods.GetScript or function(self, name) return self[name] end
        methods.IsEnabled = methods.IsEnabled or function() return true end
        -- Enough geometry for WoWStatusGamepad.controls: children, visibility and a
        -- 32 px rect from each TOPLEFT point (top-down, as the panel lays them out).
        local create = CreateFrame
        function CreateFrame(kind, name, parent, ...)
            local frame = create(kind, name, parent, ...)
            if type(parent) == "table" then parent.__kids = parent.__kids or {}; table.insert(parent.__kids, frame) end
            return frame
        end
        methods.GetChildren = function(self) return (unpack or table.unpack)(self.__kids or {}) end
        methods.IsVisible = function(self) return self.visible ~= false end -- Shown unless hidden, as in the game.
        methods.GetRect = function(self)
            local point = self.__point
            if not point or type(point[2]) ~= "number" then return 0, 0, 1000, 1000 end
            return point[2], 2000 + point[3] - 32, 32, 32
        end
    ''')
    run_addon_file(lua, ROOT / 'addon/vanilla/WoWStatus/Previews.lua')  # Built again with the hooks.
    lua.execute('''
        WoWStatusPreviews.show()
        local panel = WoWStatusNotificationPreviews
        local tick = panel.reduceMotion
        assert(tick.parent == panel.settingsCategories.frames.popups and WoWStatusGamepad.interactive(tick))
        local found = false
        for _, control in ipairs(WoWStatusGamepad.controls(panel, {panel})) do found = found or control == tick end
        assert(found, "the pad does not reach the tick")
        -- Same row as Big banners, to its right, inside the page's 564 px right margin.
        assert(tick.__point[3] == panel.big.__point[3])
        assert(tick.__point[2] == 400 and panel.big.__point[2] == 24)
        -- The Big banners label (from x 62) ends before the tick begins.
        assert(24 + 38 + panel.big.label.width <= 400 and 400 + 38 + tick.label.width <= 564)
    ''')


def test_reduce_motion_label_is_in_nynorsk():
    lua = actor('Thora')
    lua.execute('''
        WoWStatusLocale.set("nn")
        assert(WoWStatusLocale.T("Reduce motion") == "Mindre rørsle")
    ''')


def test_a_toast_dragged_while_it_is_switched_on_settles_after_the_drag():
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute('''
        WoWStatusPopups.preview("level"); WoWStatusPopups.tick()
        local toast = WoWStatusLevelPopup
        toast.OnUpdate(toast, .05)
        toast.dragging = true
        WoWStatusPopups.setReduceMotion(true)
        toast.OnUpdate(toast, .05)
        assert(toast.alpha < 1) -- Left alone while it is moved.
        toast.dragging = false
        toast.OnUpdate(toast, .05)
        assert(toast.alpha == 1 and toast.glow.alpha == WoWStatusPopups.STEADY_GLOW)
    ''')


def test_hover_pauses_the_countdown_at_once_without_an_entrance():
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute('''
        WoWStatusPopups.setReduceMotion(true)
        WoWStatusPopups.preview("level"); WoWStatusPopups.tick()
        local toast = WoWStatusLevelPopup
        WoWStatusGamepad.hold("down")
        toast.OnUpdate(toast, .1)
        assert(toast.age == 0 and toast.alpha == 1 and toast.glow.alpha == WoWStatusPopups.STEADY_GLOW)
        toast.OnUpdate(toast, 30)
        assert(toast:IsShown() and toast.age == 0)
    ''')


def test_turning_it_off_mid_toast_does_not_replay_the_entrance():
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute(TRACK_POINTS)
    lua.execute('''
        WoWStatusPopups.setReduceMotion(true)
        WoWStatusPopups.preview("level"); WoWStatusPopups.tick()
        local toast = WoWStatusLevelPopup
        toast.OnUpdate(toast, .05)
        WoWStatusPopups.setReduceMotion(false)
        toast.OnUpdate(toast, .01)
        assert(toast.alpha == 1)
    ''')
    assert offset(lua) == -170
