"""Controller navigation with simulated frames and buttons.

Positions, visibility and gamepad events are modelled here; whether a client
delivers its controller's buttons this way needs a game client to confirm.
"""
from pathlib import Path

import pytest
from test_addon import lupa

ROOT = Path(__file__).parents[1]

FRAMES = r'''
UIParent = {visible=true, children={}}
UISpecialFrames = {}
WoWStatusDB = {}
__combat = false
__pad = true
__focusEdit = nil
function InCombatLockdown() return __combat end
function GetCurrentKeyBoardFocus() return __focusEdit end
C_GamePad = {IsEnabled=function() return __pad end}
local methods = {}
local meta = {__index=methods}
function CreateFrame(kind, name, parent, template)
    parent = parent or UIParent
    local f = setmetatable({kind=kind, parent=parent, children={}, visible=true, scripts={},
        rect={0, 0, 10, 10}, strata="MEDIUM", level=1, scroll=0}, meta)
    if parent.children then table.insert(parent.children, f) end
    if name then _G[name] = f end
    return f
end
function methods:GetObjectType() return self.kind end
function methods:GetParent() return self.parent end
function methods:GetChildren() return unpack(self.children) end
function methods:IsVisible()
    local frame = self
    while frame do
        if not frame.visible then return false end
        if frame == UIParent then return true end
        frame = frame.parent
    end
    return true
end
function methods:IsShown() return self.visible end
function methods:Show() self.visible = true end
function methods:Hide()
    self.visible = false
    if self.scripts.OnHide then self.scripts.OnHide(self) end
end
function methods:SetScript(name, fn) self.scripts[name] = fn end
function methods:GetScript(name) return self.scripts[name] end
function methods:IsEnabled() return self.enabled ~= false end
function methods:SetEnabled(value) self.enabled = value end
function methods:IsMouseEnabled() return self.mouse == true end
function methods:EnableMouse(value) self.mouse = value end
function methods:Click(button)
    if self.enabled ~= false and self.scripts.OnClick then self.scripts.OnClick(self, button) end
end
function methods:GetFrameStrata() return self.strata end
function methods:SetFrameStrata(value) self.strata = value end
function methods:GetFrameLevel() return self.level end
function methods:SetFrameLevel(value) self.level = value end
function methods:GetEffectiveScale() return 1 end
-- Rectangles are absolute; a list's rows move up as it scrolls down.
function methods:GetRect()
    local l, b, w, h = unpack(self.rect)
    local frame = self.parent
    while frame and frame ~= UIParent do
        if frame.kind == "ScrollFrame" then b = b + frame.scroll end
        frame = frame.parent
    end
    return l, b, w, h
end
function methods:GetVerticalScroll() return self.scroll end
function methods:SetVerticalScroll(value) self.scroll = value end
function methods:GetVerticalScrollRange() return self.range or 0 end
function methods:EnableGamePadButton(value) self.padButtons = value end
function methods:EnableGamePadStick(value) self.padStick = value end
function methods:SetPropagateKeyboardInput(value) self.propagate = value end
function methods:RegisterEvent(name) self.events = self.events or {}; self.events[name] = true end
function methods:SetFocus() self.typing = true; __focusEdit = self end
function methods:ClearFocus() self.typing = false; __focusEdit = nil end
function methods:CreateTexture() return setmetatable({children={}, scripts={}}, meta) end
for _, name in ipairs({"SetPoint", "ClearAllPoints", "SetAllPoints", "SetColorTexture", "SetWidth", "SetHeight"}) do
    methods[name] = function() end
end

function window(name, l, b, w, h, strata)
    local f = CreateFrame("Frame", name, UIParent)
    f.rect = {l, b, w, h}; f.strata = strata or "FULLSCREEN_DIALOG"
    table.insert(UISpecialFrames, name)
    return f
end
__clicks = {}
function button(parent, label, l, b, w, h)
    local f = CreateFrame("Button", nil, parent)
    f.rect = {l, b, w or 80, h or 24}; f.label = label
    f:SetScript("OnClick", function(self, which) table.insert(__clicks, label .. ":" .. (which or "?")) end)
    return f
end
function press(name)
    local driver = WoWStatusGamepadDriver
    driver.scripts.OnGamePadButtonDown(driver, name)
    return driver.propagate
end
function focused() local f = WoWStatusGamepad.focus(); return f and f.label end
function fire(event, ...) WoWStatusGamepadDriver.scripts.OnEvent(WoWStatusGamepadDriver, event, ...) end
'''


@pytest.fixture
def lua():
    runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
    runtime.execute('unpack = unpack or table.unpack')
    runtime.execute(FRAMES)
    runtime.execute((ROOT / 'addon/shared/Gamepad.lua').read_text(encoding='utf-8'))
    return runtime


def main_window(lua):
    """A main window with two rows of two buttons, and a stub page/back API."""
    lua.execute('''
        main = window("WoWStatusMainFrame", 100, 100, 600, 400)
        a = button(main, "a", 120, 440); b = button(main, "b", 300, 440)
        c = button(main, "c", 120, 380); d = button(main, "d", 300, 380)
        __back = false
        __pages = {"overview", "activity", "characters"}
        __active = "activity"
        WoWStatusMainWindow = {
            pages=function() return __pages end,
            active=function() return main:IsVisible() and __active or nil end,
            show=function(key) __active = key or __active; main:Show() end,
            hide=function() main:Hide() end,
            back=function() return __back end,
        }
    ''')


def test_takes_buttons_only_while_a_window_is_open_with_gamepad_enabled(lua):
    lua.execute('WoWStatusGamepad.update()')
    assert not lua.eval('WoWStatusGamepadDriver.padButtons')
    main_window(lua)
    lua.execute('WoWStatusGamepad.update()')
    assert lua.eval('WoWStatusGamepadDriver.padButtons') is True
    assert lua.eval('WoWStatusGamepadDriver.padStick') is True
    lua.execute('main:Hide(); WoWStatusGamepad.update()')
    assert lua.eval('WoWStatusGamepadDriver.padButtons') is False
    # Gamepad support switched off in the game's options: never taken.
    lua.execute('__pad = false; main:Show(); WoWStatusGamepad.update()')
    assert lua.eval('WoWStatusGamepadDriver.padButtons') is False


@pytest.mark.parametrize('setup', ['ConsolePort = {}', 'WoWStatusDB.controller = false'])
def test_steps_aside_for_consoleport_and_the_opt_out(lua, setup):
    main_window(lua)
    lua.execute(setup + '; WoWStatusGamepad.update()')
    assert not lua.eval('WoWStatusGamepadDriver.padButtons')
    assert lua.eval('WoWStatusGamepad.root()') is None


def test_dpad_moves_spatially_and_a_presses(lua):
    main_window(lua)
    lua.execute('WoWStatusGamepad.update()')
    # The first press only shows the highlight, on the first control in reading order.
    assert lua.eval('press("PADDRIGHT")') is False
    assert lua.eval('focused()') == 'a'
    assert lua.eval('WoWStatusGamepadFocus.visible') is True
    lua.execute('press("PADDRIGHT")')
    assert lua.eval('focused()') == 'b'
    lua.execute('press("PADDDOWN")')
    assert lua.eval('focused()') == 'd'
    lua.execute('press("PADDLEFT")')
    assert lua.eval('focused()') == 'c'
    lua.execute('press("PADDLEFT")')  # Nothing further left: stays.
    assert lua.eval('focused()') == 'c'
    lua.execute('press("PAD1"); press("PAD3")')
    assert list(lua.eval('__clicks').values()) == ['c:LeftButton', 'c:RightButton']


def test_unused_buttons_reach_the_game(lua):
    main_window(lua)
    lua.execute('WoWStatusGamepad.update()')
    assert lua.eval('press("PADDDOWN")') is False
    assert lua.eval('press("PADFORWARD")') is True
    assert lua.eval('press("PAD5")') is True


def test_skips_disabled_scroll_bars_and_covered_controls(lua):
    main_window(lua)
    lua.execute('''
        b:SetEnabled(false)
        list = CreateFrame("ScrollFrame", nil, main); list.rect = {120, 150, 400, 200}
        bar = CreateFrame("Slider", nil, list); bar.rect = {520, 150, 16, 200}
        bar:SetScript("OnClick", function() end)
        up = button(bar, "up", 520, 330, 16, 16)
        -- A profile inside the main window covering the lower half.
        profile = window("WoWStatusProfileView", 100, 100, 600, 300)
        profile.parent = main; table.insert(main.children, profile)
        profileBack = button(profile, "profileBack", 500, 360)
        WoWStatusGamepad.update()
    ''')
    labels = lua.eval('''(function()
        local _, open = WoWStatusGamepad.top()
        local names = {}
        for _, f in ipairs(WoWStatusGamepad.controls(main, open)) do names[#names + 1] = f.label end
        table.sort(names)
        return table.concat(names, ",")
    end)()''')
    # c and d sit under the profile; b is disabled; the scroll bar is left out.
    assert labels == 'a,profileBack'
    assert lua.eval('WoWStatusGamepad.root() == main') is True


def test_a_menu_above_the_window_takes_the_controller_and_b_closes_it(lua):
    main_window(lua)
    lua.execute('''
        WoWStatusGamepad.update()
        menu = window("WoWStatusMenu", 200, 200, 150, 120, "TOOLTIP")
        first = button(menu, "first", 210, 280)
        WoWStatusGamepad.update()
    ''')
    assert lua.eval('WoWStatusGamepad.root() == menu') is True
    lua.execute('press("PADDDOWN")')
    assert lua.eval('focused()') == 'first'
    lua.execute('press("PAD2")')
    assert lua.eval('menu.visible') is False
    assert lua.eval('WoWStatusGamepad.root() == main') is True
    assert lua.eval('main.visible') is True


def test_b_goes_back_first_then_closes_and_leaves_text_fields(lua):
    main_window(lua)
    lua.execute('''
        field = CreateFrame("EditBox", nil, main); field.rect = {120, 300, 200, 24}; field.label = "field"
        WoWStatusGamepad.update()
        __back = true
    ''')
    lua.execute('press("PAD2")')
    assert lua.eval('main.visible') is True  # Stepped back instead.
    lua.execute('WoWStatusGamepad.setFocus(field); press("PADDDOWN"); WoWStatusGamepad.setFocus(field); press("PAD1")')
    assert lua.eval('field.typing') is True
    lua.execute('press("PAD2")')
    assert lua.eval('field.typing') is False
    assert lua.eval('main.visible') is True
    lua.execute('__back = false; press("PAD2")')
    assert lua.eval('main.visible') is False
    lua.execute('WoWStatusGamepad.update()')
    assert lua.eval('WoWStatusGamepadDriver.padButtons') is False


def test_shoulders_change_main_window_pages_and_wrap(lua):
    main_window(lua)
    lua.execute('WoWStatusGamepad.update(); press("PADRSHOULDER")')
    assert lua.eval('__active') == 'characters'
    lua.execute('press("PADRSHOULDER")')
    assert lua.eval('__active') == 'overview'
    lua.execute('press("PADLSHOULDER")')
    assert lua.eval('__active') == 'characters'


def test_moving_past_a_lists_edge_scrolls_it_into_view(lua):
    main_window(lua)
    lua.execute('''
        list = CreateFrame("ScrollFrame", nil, main); list.rect = {120, 150, 400, 200}; list.range = 400
        child = CreateFrame("Frame", nil, list); child.rect = {120, -250, 400, 600}
        for i = 1, 8 do button(child, "row" .. i, 130, 350 - i * 60, 300, 40) end
        WoWStatusGamepad.update()
        WoWStatusGamepad.setFocus(c); press("PADDDOWN")
    ''')
    assert lua.eval('focused()') == 'c'  # Shown first.
    steps = []
    for _ in range(5):
        lua.execute('press("PADDDOWN")')
        steps.append((lua.eval('focused()'), lua.eval('list.scroll')))
    assert [label for label, _ in steps] == ['row1', 'row2', 'row3', 'row4', 'row5']
    assert steps[2][1] == 0  # row3 (bottom 170) is still in view.
    assert steps[3][1] > 0 and steps[4][1] > steps[3][1]
    assert lua.eval('WoWStatusGamepad.inView(WoWStatusGamepad.focus(), list)') is True


def test_right_stick_scrolls_the_list_under_the_highlight(lua):
    main_window(lua)
    lua.execute('''
        list = CreateFrame("ScrollFrame", nil, main); list.rect = {120, 150, 400, 200}; list.range = 300
        WoWStatusGamepad.update()
        local driver = WoWStatusGamepadDriver
        driver.scripts.OnGamePadStick(driver, "Right", 0, -1, 1)
        WoWStatusGamepad.tick(.1)
    ''')
    assert lua.eval('list.scroll') == pytest.approx(90)
    lua.execute('''
        local driver = WoWStatusGamepadDriver
        driver.scripts.OnGamePadStick(driver, "Right", 0, .1, .1) -- Inside the dead zone.
        WoWStatusGamepad.tick(.1)
    ''')
    assert lua.eval('list.scroll') == pytest.approx(90)


def test_combat_lets_go_and_takes_back_after(lua):
    main_window(lua)
    lua.execute('WoWStatusGamepad.update(); fire("PLAYER_REGEN_DISABLED"); __combat = true; WoWStatusGamepad.update()')
    assert lua.eval('WoWStatusGamepadDriver.padButtons') is False
    lua.execute('__combat = false; fire("PLAYER_REGEN_ENABLED")')
    assert lua.eval('WoWStatusGamepadDriver.padButtons') is True


def test_mouse_use_hides_the_highlight_until_the_next_controller_press(lua):
    main_window(lua)
    lua.execute('WoWStatusGamepad.update(); press("PADDDOWN"); fire("GAME_PAD_ACTIVE_CHANGED", false)')
    assert lua.eval('WoWStatusGamepadFocus.visible') is False
    lua.execute('press("PAD1")')  # Shows where it is; does not press.
    assert lua.eval('#__clicks') == 0
    assert lua.eval('WoWStatusGamepadFocus.visible') is True


def test_key_bindings_have_names_and_call_their_actions(lua):
    main_window(lua)
    assert lua.eval('BINDING_HEADER_WOWSTATUS') == 'WoW Status'
    assert lua.eval('BINDING_NAME_WOWSTATUS_DISMISS') == 'Dismiss the notification'
    lua.execute('''
        __dismissed, __activity = 0, 0
        WoWStatusPopups = {dismiss=function() __dismissed = __dismissed + 1; return true end,
            showActivity=function() __activity = __activity + 1 end}
        WoWStatusGamepad.dismiss(); WoWStatusGamepad.activity()
        WoWStatusGamepad.toggle()
    ''')
    assert lua.eval('__dismissed') == 1 and lua.eval('__activity') == 1
    assert lua.eval('main.visible') is False
    lua.execute('WoWStatusGamepad.toggle()')
    assert lua.eval('main.visible') is True


def test_bindings_xml_calls_existing_functions():
    text = (ROOT / 'addon/shared/Bindings.xml').read_text(encoding='utf-8')
    lua_source = (ROOT / 'addon/shared/Gamepad.lua').read_text(encoding='utf-8')
    for name in ('toggle', 'activity', 'dismiss'):
        assert f'WoWStatusGamepad.{name}()' in text
        assert f'function G.{name}()' in lua_source
    for binding in ('WOWSTATUS_TOGGLE', 'WOWSTATUS_ACTIVITY', 'WOWSTATUS_DISMISS'):
        assert f'name="{binding}"' in text
        assert f'BINDING_NAME_{binding}' in lua_source
