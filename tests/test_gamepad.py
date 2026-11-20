"""Controller navigation with simulated frames and buttons.

Positions, visibility, override bindings and the controller's mapped state are
modelled here; whether a client delivers its controller's buttons this way needs
a game client to confirm.
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
__stick = {x=0, y=0, len=0}
C_GamePad = {
    IsEnabled=function() return __pad end,
    GetActiveDeviceID=function() return 3 end,
    GetDeviceMappedState=function(id)
        if id ~= 3 then return nil end
        return {sticks={{x=0, y=0, len=0}, __stick}}
    end,
    StickIndexToConfigName=function(i) return ({"Left", "Right"})[i] end,
}
-- Override bindings: {[key] = {button name, mouse button}}.
__bindings = {}
function SetOverrideBindingClick(owner, priority, key, name, mouse)
    assert(not __combat, "override bindings cannot change in combat")
    assert(priority == true)
    __bindings[key] = {name, mouse}
end
function ClearOverrideBindings(owner)
    assert(not __combat, "override bindings cannot change in combat")
    __bindings = {}
end
function bound(key) return __bindings[key] ~= nil end
function anyBound() return next(__bindings) ~= nil end
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
function methods:Click(button, down)
    if self.enabled ~= false and self.scripts.OnClick then self.scripts.OnClick(self, button, down) end
end
function methods:RegisterForClicks(...) self.clicks = {...} end
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
-- Protected for addons: calling them raised the game's "blocked action" dialog.
function methods:EnableGamePadButton() error("EnableGamePadButton is protected") end
function methods:EnableGamePadStick() error("EnableGamePadStick is protected") end
function methods:SetPropagateKeyboardInput() error("SetPropagateKeyboardInput is restricted") end
function methods:RegisterEvent(name) self.events = self.events or {}; self.events[name] = true end
function methods:SetFocus() self.typing = true; __focusEdit = self end
function methods:ClearFocus() self.typing = false; __focusEdit = nil end
function methods:CreateTexture() return setmetatable({children={}, scripts={}, rect={0,0,10,10}}, meta) end
function methods:SetTexture(path) self.texture=path end
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
-- A controller button: a claimed one clicks its button (press, then release) and
-- returns false; any other returns true, as it reaches the game's own binding.
function press(name)
    local binding = __bindings[name]
    if not binding then return true end
    local target = _G[binding[1]]
    target:Click(binding[2], true)
    target:Click(binding[2], false)
    return false
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
    assert not lua.eval('anyBound()')
    main_window(lua)
    lua.execute('WoWStatusGamepad.update()')
    for key in ('PADDUP', 'PADDDOWN', 'PADDLEFT', 'PADDRIGHT', 'PAD1', 'PAD2', 'PAD3',
                'PADLSHOULDER', 'PADRSHOULDER'):
        assert lua.eval(f'__bindings.{key}[1]') == 'WoWStatusGamepadInput'
        assert lua.eval(f'__bindings.{key}[2]') == key
    assert not lua.eval('bound("PAD5")')
    lua.execute('main:Hide(); WoWStatusGamepad.update()')
    assert not lua.eval('anyBound()')
    # Gamepad support switched off in the game's options: never taken.
    lua.execute('__pad = false; main:Show(); WoWStatusGamepad.update()')
    assert not lua.eval('anyBound()')


def test_never_calls_protected_frame_input_functions():
    source = (ROOT / 'addon/shared/Gamepad.lua').read_text(encoding='utf-8')
    code = '\n'.join(line.split('--')[0] for line in source.splitlines())
    for name in ('EnableGamePadButton', 'EnableGamePadStick', 'SetPropagateKeyboardInput',
                 'OnGamePadButtonDown', 'OnGamePadStick'):
        assert name not in code


def test_shoulders_are_claimed_only_for_the_main_window(lua):
    lua.execute('''
        menu = window("WoWStatusMenu", 200, 200, 150, 120, "TOOLTIP")
        first = button(menu, "first", 210, 280)
        WoWStatusGamepad.update()
    ''')
    assert lua.eval('bound("PAD1")') is True
    assert lua.eval('bound("PADLSHOULDER")') is False
    assert lua.eval('press("PADRSHOULDER")') is True


@pytest.mark.parametrize('setup', ['ConsolePort = {}', 'WoWStatusDB.controller = false'])
def test_steps_aside_for_consoleport_and_the_opt_out(lua, setup):
    main_window(lua)
    lua.execute(setup + '; WoWStatusGamepad.update()')
    assert not lua.eval('anyBound()')
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
    assert not lua.eval('anyBound()')


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
        __stick = {x=0, y=-1, len=1}
        WoWStatusGamepad.tick(.1)
    ''')
    assert lua.eval('list.scroll') == pytest.approx(90)
    lua.execute('''
        __stick = {x=0, y=.1, len=.1} -- Inside the dead zone.
        WoWStatusGamepad.tick(.1)
    ''')
    assert lua.eval('list.scroll') == pytest.approx(90)
    # Only the right stick scrolls; the left one moves the character.
    lua.execute('''
        C_GamePad.StickIndexToConfigName = function(i) return ({"Right", "Left"})[i] end
        __stick = {x=0, y=-1, len=1}
        WoWStatusGamepad.tick(.1)
    ''')
    assert lua.eval('list.scroll') == pytest.approx(90)


def test_combat_lets_go_and_takes_back_after(lua):
    main_window(lua)
    lua.execute('WoWStatusGamepad.update(); fire("PLAYER_REGEN_DISABLED"); __combat = true; WoWStatusGamepad.update()')
    assert not lua.eval('anyBound()')
    assert lua.eval('press("PAD1")') is True
    lua.execute('__combat = false; fire("PLAYER_REGEN_ENABLED")')
    assert lua.eval('bound("PAD1")') is True


def test_leaderboard_controls_are_reachable_and_shoulders_visit_its_page(lua):
    main_window(lua)
    lua.execute('''
        local methods=getmetatable(CreateFrame("Frame")).__index
        function methods:SetText(text) self.text=text end
        function methods:SetWordWrap() end
        function methods:CreateFontString() return CreateFrame("FontString",nil,self) end
        function methods:SetChecked(value) self.checked=value end
        function methods:GetChecked() return self.checked end
        function methods:SetSize(w,h) self.rect[3],self.rect[4]=w,h end
        function methods:SetScrollChild(child) self.child=child end
        function methods:SetShown(value) self.visible=value end
        WoWStatusLocale={T=function(text) return text end,F=string.format}
        WoWStatusSafe={}
        WoWStatusUI={
            text=function(parent) return CreateFrame("FontString",nil,parent) end,
            call=function(frame,method,...) if frame[method] then return frame[method](frame,...) end end,
            classColour=function() end,
            stripe=function() end,
            presence=function(online) return online and "(on) " or "(off) " end,
            xpBar=function(parent) local bar=CreateFrame("Frame",nil,parent); bar.SetProgress=function() end; return bar end,
        }
        WoWStatusFirsts={groups=function() return {{id="one",label="One"},{id="two",label="Two"}} end}
        WoWStatusRoster={leaderboard=function() return {{name="Mira-Realm",level=20,deaths=1,quests=247}} end,
            players=function() return {{name="Frank",main={name="Mira-Realm",level=20},rows={{name="Mira-Realm"}},alts={}}} end,
            mainChoices=function() return {{name="Mira-Realm"}} end,
            ownMain=function() return __main end,
            setMain=function(group,name) __main=name; return true end}
        WoWStatusMainWindow.register=function(key,title,build,refresh)
            assert(key=="leaderboard")
            __boardBuild,__boardRefresh=build,refresh
            __pages={"overview","activity","records","leaderboard","characters"}
        end
    ''')
    lua.execute((ROOT / 'addon/shared/Safe.lua').read_text(encoding='utf-8'))
    lua.execute((ROOT / 'addon/shared/Leaderboard.lua').read_text(encoding='utf-8'))
    lua.execute('''
        local show=WoWStatusMainWindow.show
        WoWStatusMainWindow.show=function(key)
            show(key)
            if key=="leaderboard" then
                __board=__board or __boardBuild(main)
                __board:Show();__boardRefresh()
                __board.sort.rect={500,380,140,24}
                __board.pinnedFirst.rect={300,380,32,32}
                __board.mode.rect={370,380,120,24}
                __board.main.rect={190,380,170,24}
                for i,tab in ipairs(__board.tabs) do tab.rect={120+(i-1)*140,440,128,24} end
            elseif __board then __board:Hide() end
        end
        WoWStatusGamepad.update()
        press("PADRSHOULDER")
        assert(__active=="records")
        press("PADRSHOULDER")
        assert(__active=="leaderboard")
        local controls=WoWStatusGamepad.controls(main,{main})
        local sort,group,pinned,mode,mainButton=false,false,false,false,false
        for _,control in ipairs(controls) do
            if control==__board.sort then sort=true end
            if control==__board.pinnedFirst then pinned=true end
            if control==__board.mode then mode=true end
            if control==__board.main then mainButton=true end
            if control==__board.tabs[2] then group=true end
            assert(control~=__board.tabs[1]) -- the selected group is disabled
        end
        assert(sort and group and pinned and mode and mainButton)
        press("PADDDOWN")
        WoWStatusGamepad.setFocus(__board.sort);press("PAD1")
        assert(WoWStatusDB.leaderboard.sort=="deaths")
        WoWStatusGamepad.setFocus(__board.tabs[2]);press("PAD1")
        assert(WoWStatusDB.leaderboard.tab=="two")
        WoWStatusGamepad.setFocus(__board.mode);press("PAD1")
        assert(WoWStatusDB.leaderboard.mode=="players")
        WoWStatusGamepad.setFocus(__board.main);press("PAD1")
        assert(__main=="Mira-Realm")
        press("PADRSHOULDER")
        assert(__active=="characters")
        press("PADLSHOULDER")
        assert(__active=="leaderboard")
        press("PAD2")
        assert(not main:IsShown())
    ''')


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
    lua.execute('''
        __holds = {}
        WoWStatusPopups.hold = function(down) table.insert(__holds, down) end
        WoWStatusGamepad.hold("down"); WoWStatusGamepad.hold("up")
    ''')
    assert lua.eval('__holds[1]') is True and lua.eval('__holds[2]') is False
    assert lua.eval('main.visible') is False
    lua.execute('WoWStatusGamepad.toggle()')
    assert lua.eval('main.visible') is True


def test_bindings_xml_calls_existing_functions():
    text = (ROOT / 'addon/shared/Bindings.xml').read_text(encoding='utf-8')
    lua_source = (ROOT / 'addon/shared/Gamepad.lua').read_text(encoding='utf-8')
    for name in ('toggle', 'activity', 'dismiss'):
        assert f'WoWStatusGamepad.{name}()' in text
        assert f'function G.{name}()' in lua_source
    # Hold runs on press and release, and is told which.
    assert '<Binding name="WOWSTATUS_HOLD" runOnUp="true">WoWStatusGamepad.hold(keystate)</Binding>' in text
    assert 'function G.hold(keystate)' in lua_source
    for binding in ('WOWSTATUS_TOGGLE', 'WOWSTATUS_ACTIVITY', 'WOWSTATUS_DISMISS', 'WOWSTATUS_HOLD'):
        assert f'name="{binding}"' in text
        assert f'BINDING_NAME_{binding}' in lua_source


PAGE_BINDINGS = {'overview': 'WOWSTATUS_OVERVIEW', 'characters': 'WOWSTATUS_CHARACTERS',
                 'leaderboard': 'WOWSTATUS_LEADERBOARD', 'records': 'WOWSTATUS_RECORDS'}


def page_window(lua):
    """main_window with the page API the page bindings use: has, state, show(key)."""
    main_window(lua)
    lua.execute('''
        __pages = {"overview", "activity", "characters", "leaderboard", "records"}
        __state = nil
        __shown = {}
        local M = WoWStatusMainWindow
        M.has = function(key) for _, k in ipairs(__pages) do if k == key then return true end end return false end
        M.state = function() return __state end
        M.show = function(key) __active = key; __state = {page=key}; table.insert(__shown, key); main:Show() end
        main:Hide()
    ''')


def test_page_bindings_are_in_bindings_xml_with_labels_and_no_default_key():
    text = (ROOT / 'addon/shared/Bindings.xml').read_text(encoding='utf-8')
    for key, binding in PAGE_BINDINGS.items():
        line = next(row for row in text.splitlines() if f'name="{binding}"' in row)
        assert f'>WoWStatusGamepad.togglePage("{key}")</Binding>' in line
        # Unbound by default: no default key attribute.
        assert 'default=' not in line


def test_page_shortcuts_table_matches_bindings_xml(lua):
    text = (ROOT / 'addon/shared/Bindings.xml').read_text(encoding='utf-8')
    shortcuts = lua.eval('WoWStatusGamepad.PAGE_SHORTCUTS')
    pairs = {row['key']: row['binding'] for row in shortcuts.values()}
    assert pairs == PAGE_BINDINGS
    for key, binding in pairs.items():
        assert f'<Binding name="{binding}">WoWStatusGamepad.togglePage("{key}")</Binding>' in text


def test_page_binding_closes_a_menu_left_open_by_the_old_page(lua):
    page_window(lua)
    lua.execute('''
        WoWStatusGamepad.togglePage("leaderboard")
        menu = window("WoWStatusMenu", 150, 150, 180, 200, "TOOLTIP")
        m1 = button(menu, "m1", 160, 300)
        WoWStatusGamepad.update()
        WoWStatusGamepad.togglePage("records")
    ''')
    assert lua.eval('menu.visible') is False and lua.eval('__active') == 'records'
    # And when the binding closes the window, the menu goes with it.
    lua.execute('menu:Show(); WoWStatusGamepad.update(); WoWStatusGamepad.togglePage("records")')
    assert lua.eval('menu.visible') is False and lua.eval('main.visible') is False
    lua.execute('WoWStatusGamepad.update()')
    assert not lua.eval('anyBound()')


def test_page_binding_keeps_the_place_in_another_window_on_top(lua):
    page_window(lua)
    lua.execute('''
        WoWStatusGamepad.togglePage("overview")
        news = window("WoWStatusWhatsNewFrame", 150, 150, 300, 300, "DIALOG")
        news:SetFrameStrata("FULLSCREEN_DIALOG")
        n1 = button(news, "n1", 160, 400); n2 = button(news, "n2", 160, 300)
        WoWStatusGamepad.update(); press("PADDDOWN"); press("PADDDOWN")
        __left = 0
        n1:SetScript("OnLeave", function() __left = __left + 1 end)
        n2:SetScript("OnLeave", function() __left = __left + 1 end)
        WoWStatusGamepad.togglePage("records")
        __clicks = {}
        press("PAD1")
    ''')
    assert lua.eval('__left') == 0
    assert lua.eval('__clicks[1]') == 'n2:LeftButton'


def test_closing_with_a_page_binding_lets_go_of_the_highlighted_control(lua):
    page_window(lua)
    lua.execute('''
        WoWStatusGamepad.togglePage("overview"); WoWStatusGamepad.update(); press("PADDDOWN")
        __left = 0
        for _, f in ipairs({a, b, c, d}) do f:SetScript("OnLeave", function() __left = __left + 1 end) end
        WoWStatusGamepad.togglePage("overview")
    ''')
    assert lua.eval('main.visible') is False
    assert lua.eval('__left') == 1 and not lua.eval('anyBound()')


def test_page_binding_labels_in_english_and_nynorsk(lua):
    labels = {key: lua.eval(f'BINDING_NAME_{binding}') for key, binding in PAGE_BINDINGS.items()}
    assert labels == {key: f'Open or close the {key.capitalize()} page' for key in PAGE_BINDINGS}
    nynorsk = (ROOT / 'addon/shared/LocaleNN.lua').read_text(encoding='utf-8')
    titles = {'overview': 'Oversikt', 'characters': 'Figurar', 'leaderboard': 'Toppliste', 'records': 'Rekordar'}
    for key, label in labels.items():
        assert f'["{label}"] = "Opne eller lukk sida {titles[key]}"' in nynorsk
        # The same Nynorsk name as the page's own tab.
        assert f'["{key.capitalize()}"] = "{titles[key]}"' in nynorsk


@pytest.mark.parametrize('key', sorted(PAGE_BINDINGS))
def test_page_binding_opens_its_page_and_closes_it_on_a_second_press(lua, key):
    page_window(lua)
    assert lua.eval(f'WoWStatusGamepad.togglePage("{key}")') is True
    assert lua.eval('main.visible') is True and lua.eval('__active') == key
    # Same page on screen: the second press closes the window.
    lua.execute(f'WoWStatusGamepad.togglePage("{key}")')
    assert lua.eval('main.visible') is False


def test_page_binding_switches_page_when_another_page_is_open(lua):
    page_window(lua)
    lua.execute('WoWStatusGamepad.togglePage("overview"); WoWStatusGamepad.togglePage("records")')
    assert lua.eval('main.visible') is True and lua.eval('__active') == 'records'


def test_page_binding_moves_the_highlight_off_the_page_it_left(lua):
    page_window(lua)
    lua.execute('''
        WoWStatusGamepad.togglePage("overview"); WoWStatusGamepad.update(); press("PADDDOWN")
        __left = {}
        for _, f in ipairs({a, b, c, d}) do
            f:SetScript("OnLeave", function(self) table.insert(__left, self) end)
        end
        -- The Overview's controls go away with the page; Records shows its own.
        local show = WoWStatusMainWindow.show
        WoWStatusMainWindow.show = function(key)
            a.visible, b.visible, c.visible, d.visible = false, false, false, false
            e = e or button(main, "e", 200, 300)
            show(key)
        end
        WoWStatusGamepad.togglePage("records")
        __clicks = {}
        press("PAD1")
    ''')
    assert lua.eval('__clicks[1]') == 'e:LeftButton'
    # The control it left hears OnLeave (tooltips and tints go away).
    assert lua.eval('#__left') == 1


def test_page_binding_returns_to_the_page_from_a_profile_instead_of_closing(lua):
    page_window(lua)
    lua.execute('WoWStatusGamepad.togglePage("characters"); __state = {page="characters", profile="Someone"}')
    lua.execute('WoWStatusGamepad.togglePage("characters")')
    assert lua.eval('main.visible') is True
    assert lua.eval('__state.profile') is None and lua.eval('#__shown') == 2


def test_page_bindings_do_nothing_in_combat(lua):
    page_window(lua)
    lua.execute('__combat = true')
    for key in PAGE_BINDINGS:
        assert lua.eval(f'WoWStatusGamepad.togglePage("{key}")') is False
    assert lua.eval('main.visible') is False and lua.eval('#__shown') == 0
    # Open before combat: a press in combat does not close it either.
    lua.execute('__combat = false; WoWStatusGamepad.togglePage("overview"); __combat = true; WoWStatusGamepad.togglePage("overview")')
    assert lua.eval('main.visible') is True


def test_page_binding_ignores_a_page_that_is_not_registered(lua):
    page_window(lua)
    lua.execute('__pages = {"overview", "activity"}')
    assert lua.eval('WoWStatusGamepad.togglePage("records")') is False
    assert lua.eval('main.visible') is False


def test_settings_character_visibility_checkboxes_are_reachable(lua):
    main_window(lua)
    lua.execute('''
        local methods=getmetatable(CreateFrame("Frame")).__index
        function methods:SetSize(w,h) self.rect[3],self.rect[4]=w,h end
        function methods:SetText(text) self.text=text end
        function methods:CreateFontString() return CreateFrame("FontString",nil,self) end
        function methods:SetChecked(value) self.checked=value end
        function methods:GetChecked() return self.checked end
        local click=methods.Click
        function methods:Click(button,down)
            if self.kind=="CheckButton" then self.checked=not self.checked end
            click(self,button,down)
        end
        function methods:SetJustifyH() end
        function methods:SetScrollChild(child) self.child=child end
        WoWStatusLocale={T=function(text) return text end,F=string.format}
        WoWStatusSafe={}
        WoWStatusMainWindow.register=function() end
    ''')
    lua.execute((ROOT / 'addon/shared/Roster.lua').read_text(encoding='utf-8'))
    lua.execute('''
        local bank={hide_from_list=true}
        local active={}
        WoWStatusRoster.ownedCharacters=function() return {
            {name="Bank-Realm",character=bank},{name="Active-Realm",character=active}} end
        WoWStatusRoster.setHidden=function(character,hidden) character.hide_from_list=hidden end
        local scroll=WoWStatusRoster.buildVisibilitySettings(main,-40)
        scroll:refresh()
        local controls=WoWStatusGamepad.controls(main,{main})
        local reached={}
        for _,control in ipairs(controls) do reached[control]=true end
        assert(reached[scroll.rows[1]] and reached[scroll.rows[2]])
        assert(not scroll.rows[1]:GetChecked() and scroll.rows[2]:GetChecked())
        scroll.rows[1].rect={120,400,32,32}
        WoWStatusGamepad.update()
        press("PADDDOWN")
        WoWStatusGamepad.setFocus(scroll.rows[1]);press("PAD1")
        assert(not bank.hide_from_list)
    ''')


def test_diagnostics_controls_are_reachable(lua):
    main_window(lua)
    lua.execute('''
        local methods=getmetatable(CreateFrame("Frame")).__index
        function methods:SetText(text) self.text=text end
        function methods:CreateFontString() return CreateFrame("FontString",nil,self) end
        for _, name in ipairs({"SetJustifyH","SetSize","SetMultiLine","SetAutoFocus","SetFontObject",
            "SetScrollChild","SetCursorPosition","HighlightText"}) do methods[name]=function() end end
        WoWStatusLocale={T=function(text) return text end,F=string.format}
        WoWStatusUI={text=function(parent) return CreateFrame("FontString",nil,parent) end}
        WoWStatusMainWindow.register=function(key,title,build,refresh,options)
            assert(key=="diagnostics" and options.tab==false)
            __diagBuild,__diagRefresh=build,refresh
            return true
        end
    ''')
    lua.execute((ROOT / 'addon/shared/Diagnostics.lua').read_text(encoding='utf-8'))
    lua.execute('''
        WoWStatusDB={diagnostics={errors={{message="Interface/AddOns/WoWStatus/X.lua:1: boom",count=1}}}}
        local show=WoWStatusMainWindow.show
        WoWStatusMainWindow.show=function(key)
            show(key)
            __page=__page or __diagBuild(main)
            __page:Show();__diagRefresh()
            __page.box.rect={124,200,690,200}
            __page.select.rect={124,150,160,26}
            __page.clear.rect={300,150,160,26}
            return __page
        end
        WoWStatusDiagnostics.show()
        WoWStatusGamepad.update()
        local controls=WoWStatusGamepad.controls(main,{main})
        local box,select,clear=false,false,false
        for _,control in ipairs(controls) do
            if control==__page.box then box=true end
            if control==__page.select then select=true end
            if control==__page.clear then clear=true end
        end
        assert(box and select and clear)
        press("PADDDOWN") -- the first press shows the highlight
        WoWStatusGamepad.setFocus(__page.clear);press("PAD1")
        assert(#WoWStatusDB.diagnostics.errors==0)
        assert(__page.clear.enabled==false)
        -- From the tabless page RB goes to the first tab, LB to the last.
        press("PADRSHOULDER")
        assert(__active=="overview")
        WoWStatusDiagnostics.show();press("PADLSHOULDER")
        assert(__active=="characters")
    ''')


def test_group_goal_editor_controls_are_reachable(lua):
    main_window(lua)
    lua.execute('''
        local methods=getmetatable(CreateFrame("Frame")).__index
        function methods:SetText(text) self.text=text end
        function methods:ClearAllPoints() self.anchor=nil end
        function methods:SetPoint(point, relative, relativePoint, x, y)
            if x then self.anchor={point,relative,relativePoint,x,y} end
        end
        function methods:CreateFontString() return CreateFrame("FontString",nil,self) end
        for _, name in ipairs({"SetJustifyH","SetSize","SetWordWrap"}) do methods[name]=function() end end
        WoWStatusLocale={T=function(text) return text end,F=string.format}
        WoWStatusSafe={now=function() return 1793000000 end, number=function(v) return type(v)=="number" and v or nil end}
        WoWStatusAdapter={max_level=60}
        WoWStatusGroups={contains=function(_, id) return id=="one" or id=="two" end,
            selected=function() return {one={label="One"},two={label="Two"}} end}
        WoWStatusPopups={character=function() return {} end, peers=function() return {} end,
            characterName=function() return "Ada-Realm" end}
        WoWStatusFirsts={groups=function() return {{id="one",label="One"},{id="two",label="Two"}} end}
        WoWStatusRoster={id=function() return "0123456789abcdef" end, ownName=function() return "Ada" end,
            key=function(name) return name and name:lower() end,
            sections=function() return {} end, queue=function() end}
        WoWStatusMainWindow.register=function(key,title,build,refresh,options)
            assert(key=="goal" and options.tab==false)
            __goalBuild,__goalRefresh=build,refresh
            return true
        end
        WoWStatusMainWindow.refresh=function() end
    ''')
    lua.execute((ROOT / 'addon/shared/Theme.lua').read_text(encoding='utf-8'))
    lua.execute((ROOT / 'addon/shared/Goals.lua').read_text(encoding='utf-8'))
    lua.execute('''
        local show=WoWStatusMainWindow.show
        WoWStatusMainWindow.show=function(key)
            show(key)
            __page=__page or __goalBuild(main)
            __page:Show();__goalRefresh()
            local positions={
                heading={24,-8}, nextGroup={600,-6},
                measure={24,-50}, measureBack={330,-44}, measureNext={376,-44},
                shape={24,-86}, everybody={330,-80}, together={446,-80},
                target={24,-122}, muchLess={330,-116}, less={386,-116},
                more={432,-116}, muchMore={478,-116},
                deadline={24,-158}, deadlineBack={330,-152}, deadlineNext={376,-152},
                preview={24,-196}, save={24,-228}, clear={172,-228},
                current={24,-272}, note={24,-320},
            }
            for key, position in pairs(positions) do
                local point, relative, relativePoint, x, y=unpack(__page[key].anchor)
                assert(point=="TOPLEFT" and relative==__page and relativePoint=="TOPLEFT", key)
                assert(x==position[1] and y==position[2], key)
            end
            __page.measureNext.rect={500,500,40,24}
            __page.together.rect={500,460,110,24}
            __page.nextGroup.rect={650,540,120,24}
            __page.save.rect={124,380,140,24}
            return __page
        end
        WoWStatusGoals.show()
        WoWStatusGamepad.update()
        local reached={}
        for _,control in ipairs(WoWStatusGamepad.controls(main,{main})) do reached[control]=true end
        assert(reached[__page.measureNext] and reached[__page.nextGroup] and reached[__page.save])
        assert(not reached[__page.together]) -- "Together" means nothing for a level goal
        press("PADDDOWN") -- the first press shows the highlight
        WoWStatusGamepad.setFocus(__page.measureNext);press("PAD1")
        assert(WoWStatusDB.goal_editor.measure=="quests")
        WoWStatusGamepad.setFocus(__page.save);press("PAD1")
        assert(WoWStatusDB.goals.one.measure=="quests" and WoWStatusDB.goals.one.target==500)
        WoWStatusGamepad.setFocus(__page.nextGroup);press("PAD1")
        assert(WoWStatusDB.goal_editor.group=="two")
    ''')


def test_labs_rows_and_the_all_off_button_are_reachable(lua):
    # #222: every toggle on the Labs page must be reachable with a controller.
    main_window(lua)
    lua.execute('''
        local methods=getmetatable(CreateFrame("Frame")).__index
        function methods:SetText(text) self.text=text end
        function methods:CreateFontString() return CreateFrame("FontString",nil,self) end
        function methods:SetChecked(value) self.checked=value and true or false end
        function methods:GetChecked() return self.checked end
        function methods:SetEnabled(value) self.enabled=value and true or false end
        local click=methods.Click
        function methods:Click(button,down)
            -- A real CheckButton flips before OnClick runs; A on a pad goes through Click.
            if self.kind=="CheckButton" and self.enabled~=false then self.checked=not self.checked end
            click(self,button,down)
        end
        for _, name in ipairs({"SetJustifyH","SetSize","SetScrollChild","SetHeight","SetShown"}) do methods[name]=function() end end
        WoWStatusLocale={T=function(text) return text end,F=string.format}
        WoWStatusUI={call=function(frame,name,...) if frame[name] then frame[name](frame,...) end end}
        WoWStatusMainWindow.register=function(key,title,build,refresh,options)
            assert(key=="labs" and options.tab==false)
            __labsBuild,__labsRefresh=build,refresh
            return true
        end
    ''')
    lua.execute((ROOT / 'addon/shared/Features.lua').read_text(encoding='utf-8'))
    lua.execute((ROOT / 'addon/shared/Labs.lua').read_text(encoding='utf-8'))
    lua.execute('''
        WoWStatusDB={}
        WoWStatusFeatures.init(WoWStatusDB)
        WoWStatusFeatures.register("combo","Hype combo banner","A banner for milestones together")
        WoWStatusFeatures.register("bingo","Weekly group bingo card")
        local show=WoWStatusMainWindow.show
        WoWStatusMainWindow.show=function(key)
            show(key)
            __page=__page or __labsBuild(main)
            __page:Show();__labsRefresh()
            __page.rows[1].rect={124,400,32,32}
            __page.rows[2].rect={124,330,32,32}
            __page.allOff.rect={124,150,260,26}
            return __page
        end
        WoWStatusLabs.show()
        WoWStatusGamepad.update()
        local controls=WoWStatusGamepad.controls(main,{main})
        local first,second,off=false,false,false
        for _,control in ipairs(controls) do
            if control==__page.rows[1] then first=true end
            if control==__page.rows[2] then second=true end
            if control==__page.allOff then off=true end
        end
        assert(first and second)
        -- Nothing is on yet, so Turn all off does nothing and is disabled.
        assert(not off and __page.allOff.enabled==false)
        press("PADDDOWN") -- the first press shows the highlight
        WoWStatusGamepad.setFocus(__page.rows[1]);press("PAD1")
        assert(WoWStatusFeatures.enabled("combo"))
        assert(__page.allOff.enabled==true)
        -- Now it does something, so the pad can reach it.
        local reached=false
        for _,control in ipairs(WoWStatusGamepad.controls(main,{main})) do
            if control==__page.allOff then reached=true end
        end
        assert(reached)
        WoWStatusGamepad.setFocus(__page.allOff);press("PAD1")
        assert(not WoWStatusFeatures.enabled("combo"))
    ''')


def test_group_listing_checkbox_and_confirmation_are_reachable(lua):
    lua.execute('''
        local methods=getmetatable(CreateFrame("Frame")).__index
        function methods:SetText(text) self.text=text end
        function methods:GetText() return self.text end
        function methods:CreateFontString() return CreateFrame("FontString",nil,self) end
        function methods:SetSize(w,h) self.rect[3],self.rect[4]=w,h end
        function methods:SetShown(shown) self.visible=shown end
        function methods:SetChecked(value) self.checked=value end
        function methods:GetChecked() return self.checked end
        function methods:SetParent(parent) self.parent=parent end
        function methods:SetScrollChild(child) self.child=child end
        for _,name in ipairs({"SetJustifyH","SetWordWrap","SetFontObject","SetAutoFocus",
            "SetMultiLine","SetMaxLetters","SetTextColor","SetScale","SetMovable","RegisterForDrag"}) do
            methods[name]=function() end
        end
        WoWStatusLocale={T=function(text) return text end,F=string.format}
        WoWStatusSafe={now=function() return 100 end,stampExport=function() end}
        WoWStatusPopups={peers=function() return {} end}
        WoWStatusDB={characters={},account_groups={demo="Example"}}
    ''')
    lua.execute((ROOT / 'addon/shared/Groups.lua').read_text(encoding='utf-8'))
    lua.execute('''
        WoWStatusGroups.init(WoWStatusDB,function() return {group_ids={demo={}}} end,function() end)
        WoWStatusGroups.show()
        local row=WoWStatusGroupWindow.rows[1]
        local controls=WoWStatusGamepad.controls(WoWStatusGroupWindow,{WoWStatusGroupWindow})
        local found=false
        for _,control in ipairs(controls) do if control==row.listed then found=true end end
        assert(found)
        row.listed:SetChecked(true);row.listed:GetScript("OnClick")(row.listed)
        local dialog=WoWStatusGroupListingConfirm
        local reached={}
        for _,control in ipairs(WoWStatusGamepad.controls(dialog,{dialog})) do reached[control]=true end
        assert(reached[dialog.cancel] and reached[dialog.accept])
        WoWStatusGamepad.update()
        assert(WoWStatusGamepad.top()==dialog)
        press("PAD2")
        assert(not dialog:IsShown() and not WoWStatusGroups.isListed("demo"))
        WoWStatusGroups.requestListing("demo",true)
        fire("PLAYER_REGEN_DISABLED");__combat=true;WoWStatusGamepad.update();assert(not anyBound())
        __combat=false
        WoWStatusGamepad.update()
        press("PADDDOWN")
        WoWStatusGamepad.setFocus(dialog.accept);press("PAD1")
        assert(WoWStatusGroups.isListed("demo") and not dialog:IsShown())
    ''')


def test_countdown_goal_buttons_are_reachable_and_set_the_target(lua):
    main_window(lua)
    lua.execute("""
        local methods=getmetatable(CreateFrame("Frame")).__index
        function methods:SetText(text) self.text=text end
        function methods:SetSize(w,h) self.rect[3],self.rect[4]=w,h end
        WoWStatusLocale={T=function(text) return text end,F=string.format}
        WoWStatusSafe={number=tonumber}
        WoWStatusAdapter={level=function() return 38 end,max_level=60,client_id="classic-era"}
        __character={}
        WoWStatusPopups={character=function() return __character end}
        WoWStatusUI={
            text=function(parent) return CreateFrame("FontString",nil,parent) end,
            call=function(frame,name,...) return frame[name](frame,...) end,
        }
        local window=WoWStatusMainWindow
        window.has=function() return __build~=nil end
        window.register=function(key, title, build, refresh, options)
            assert(key=="personal-countdown" and options.tab==false)
            __build,__refresh=build,refresh
        end
        local show=window.show
        window.show=function(key)
            show(key)
            __page=__build(main)
            __page:Show(); __refresh(__page)
            __page.less.rect={120,340,66,26}
            __page.more.rect={194,340,66,26}
            __page.riding.rect={120,300,160,26}
            __page.cap.rect={288,300,160,26}
            __page.clear.rect={456,300,160,26}
        end
    """)
    for name in ('Features', 'Settings', 'StatusLine'):
        lua.execute((ROOT / f'addon/shared/{name}.lua').read_text(encoding='utf-8'))
    lua.execute("""
        WoWStatusDB={}
        WoWStatusFeatures.init(WoWStatusDB)
        assert(WoWStatusFeatures.set("personalCountdown",true))
        for _, item in ipairs(WoWStatusFeatures.experiments()) do
            if item.id=="personalCountdown" then item.configure() end
        end
        WoWStatusGamepad.update()
        local function reachable()
            local controls={}
            for _,control in ipairs(WoWStatusGamepad.controls(main,{main})) do controls[control]=true end
            return controls
        end
        local controls=reachable()
        assert(controls[__page.more] and controls[__page.riding] and controls[__page.cap])
        assert(not controls[__page.less] and not controls[__page.clear])
        press("PADDDOWN")
        WoWStatusGamepad.setFocus(__page.riding); press("PAD1")
        assert(__character.personal_goal_level==40)
        controls=reachable()
        assert(controls[__page.less] and controls[__page.clear] and not controls[__page.riding])
        WoWStatusGamepad.setFocus(__page.clear); press("PAD1")
        assert(__character.personal_goal_level==nil)
    """)


def test_manual_hardcore_checkbox_is_reachable_when_needed():
    from test_addon import make_lua

    runtime = make_lua()
    runtime.execute("""
        local panel = WoWStatusMainWindow.show("overview")
        local check = panel.manualHardcore
        panel.GetChildren = function() return check end
        check.GetRect = function() return 310, 200, 32, 32 end
        check.GetObjectType = function() return "CheckButton" end
        check.SetEnabled = function(self, enabled) self.enabled = enabled end
        check.IsEnabled = function(self) return self.enabled end
        assert(WoWStatusGamepad.controls(panel)[1] == check)
        C_GameRules = {IsHardcoreActive=function() return false end}
        WoWStatusMainWindow.refresh("overview")
        assert(#WoWStatusGamepad.controls(panel) == 0)
        assert(check:IsEnabled() == false)
    """)


def test_bingo_board_cells_are_controller_controls():
    from test_journal import actor

    runtime = actor('Thora')
    runtime.execute("""
        local F = WoWStatusFeatures
        local unpack = unpack or table.unpack
        F.set("bingo", true)
        SlashCmdList.WOWSTATUS("labs")
        for _, row in ipairs(WoWStatusLabsPage.rows) do
            if row.id == "bingo" then row.configure.OnClick(row.configure) end
        end
        assert(WoWStatusMainWindow.active() == "bingo")
        local page = WoWStatusMainWindow.show("bingo")
        page.GetChildren = function() return unpack(page.cells) end
        for i, cell in ipairs(page.cells) do
            cell.GetRect = function() return (i-1)%5*142, 500-math.floor((i-1)/5)*78, 136, 72 end
            cell.GetObjectType = function() return "Button" end
            cell.GetScript = function(self, script) return self[script] end
        end
        assert(#WoWStatusGamepad.controls(page) == 25)
    """)


def test_settings_category_picker_reaches_only_the_visible_controls(lua):
    main_window(lua)
    lua.execute('''
        local m=getmetatable(CreateFrame("Frame")).__index
        function m:SetText(value) self.text=value end
        function m:CreateFontString() return CreateFrame("FontString",nil,self) end
        function m:SetShown(value) self.visible=value end
        function m:SetSize(w,h) self.rect[3],self.rect[4]=w,h end
        function m:SetHeight(h) self.rect[4]=h end
        function m:SetScrollChild(child) self.child=child end
        for _,name in ipairs({"SetJustifyH","SetScale"}) do m[name]=function() end end
    ''')
    for name in ('Safe', 'Locale', 'LocaleNN', 'Theme'):
        lua.execute((ROOT / f'addon/shared/{name}.lua').read_text(encoding='utf-8'))
    lua.execute('''
        local layout=WoWStatusUI.settingsCategories(main,{
            {value="one",label="One"},{value="two",label="Two"}},"one")
        layout:category("one",200)
        local a=button(layout:parent(),"A",120,400,80,24)
        layout:place(a,24,-200)
        layout:category("two",300)
        local b=button(layout:parent(),"B",120,400,80,24)
        layout:place(b,24,-300)
        layout:finish()
        layout.pick.rect={120,480,350,30}
        local function controls()
            local found={}
            for _,control in ipairs(WoWStatusGamepad.controls(main,{main})) do found[control]=true end
            return found
        end
        assert(controls()[layout.pick] and controls()[a] and not controls()[b])
        layout.pick:Click()
        local menu=WoWStatusMenu
        menu.rect={100,200,370,100}
        for i,row in ipairs(menu.rows) do row.rect={120,280-i*24,300,22} end
        local reached={}
        for _,control in ipairs(WoWStatusGamepad.controls(menu,{menu})) do reached[control]=true end
        for _,row in ipairs(menu.rows) do
            assert(reached[row])
            if row.value=="two" then row:Click() end
        end
        assert(layout.selected=="two" and not controls()[a] and controls()[b])
    ''')


def test_together_period_menu_options_are_reachable_by_controller(lua):
    main_window(lua)
    lua.execute('''
        local m=getmetatable(CreateFrame("Frame")).__index
        function m:SetText(value) self.text=value end
        function m:CreateFontString() return CreateFrame("FontString",nil,self) end
        function m:SetShown(value) self.visible=value end
        function m:SetSize(w,h) self.rect[3],self.rect[4]=w,h end
        function m:SetHeight(h) self.rect[4]=h end
        function m:SetScrollChild(child) self.child=child end
        for _,name in ipairs({"SetJustifyH","SetWordWrap","SetScale"}) do m[name]=function() end end
    ''')
    for name in ('Safe', 'Locale', 'LocaleNN', 'Theme'):
        lua.execute((ROOT / f'addon/shared/{name}.lua').read_text(encoding='utf-8'))
    lua.execute('''
        WoWStatusGroups={historySince=function() return nil end}
        WoWStatusJournal={entries=function() return {} end}
        WoWStatusRoster={groups=function() return {} end,hiddenNames=function() return {} end}
        WoWStatusFirsts={groups=function() return {{id="synthetic",label="Example"}} end,
            weekRange=function() return "2026-11-16","2026-11-22" end}
        WoWStatusMainWindow.register=function(_,_,build,refresh)
            __build,__refresh=build,refresh;return true
        end
        WoWStatusMainWindow.show=function()
            __page=__page or __build(main)
            __refresh()
        end
    ''')
    lua.execute((ROOT / 'addon/shared/Together.lua').read_text(encoding='utf-8'))
    lua.execute('''
        WoWStatusTogether.show()
        local p=__page
        p.period.rect={120,400,180,26}
        assert(p.period:GetScript("OnClick"))
        p.period:Click()
        local menu=WoWStatusMenu
        menu.rect={100,200,220,160}
        for i,row in ipairs(menu.rows) do row.rect={120,350-i*24,180,22} end
        local reached={}
        for _,control in ipairs(WoWStatusGamepad.controls(menu,{menu})) do reached[control]=true end
        local count=0
        for _,row in ipairs(menu.rows) do assert(reached[row]);count=count+1 end
        assert(count==5)
    ''')


def test_records_group_and_view_menus_are_reachable_by_controller(lua):
    main_window(lua)
    lua.execute('''
        local m=getmetatable(CreateFrame("Frame")).__index
        function m:SetText(value) self.text=value end
        function m:CreateFontString() return CreateFrame("FontString",nil,self) end
        function m:SetShown(value) self.visible=value end
        function m:SetSize(w,h) self.rect[3],self.rect[4]=w,h end
        function m:SetHeight(h) self.rect[4]=h end
        function m:SetScrollChild(child) self.child=child end
        function m:GetWidth() return self.rect[3] end
        for _,name in ipairs({"SetJustifyH","SetWordWrap","SetScale"}) do m[name]=function() end end
    ''')
    for name in ('Safe', 'Locale', 'LocaleNN', 'Theme'):
        lua.execute((ROOT / f'addon/shared/{name}.lua').read_text(encoding='utf-8'))
    lua.execute('''
        WoWStatusFeatures={register=function() end}
        WoWStatusMainWindow.register=function(_,_,build,refresh) __build,__refresh=build,refresh end
        WoWStatusDB.firsts={view="week"}
    ''')
    lua.execute((ROOT / 'addon/shared/Firsts.lua').read_text(encoding='utf-8'))
    lua.execute('''
        WoWStatusFirsts.groups=function() return {{id="one",label="Example One"},{id="two",label="Example Two"}} end
        WoWStatusFirsts.weekData=function() return {first="2026-11-16",last="2026-11-22",people={},highlights={},extras={}} end
        local p=__build(main); __refresh()
        p.pick.rect={120,440,290,28}; p.view.rect={420,440,256,28}; p.export.rect={690,440,118,28}
        p.weekBack.rect={650,400,56,28}; p.weekNext.rect={720,400,56,28}
        local reached={}
        for _,control in ipairs(WoWStatusGamepad.controls(main,{main})) do reached[control]=true end
        assert(reached[p.pick] and reached[p.view] and reached[p.export] and reached[p.weekBack])
        assert(not reached[p.weekNext]) -- there is no future week to open
        local function menuControls(count)
            local menu=WoWStatusMenu
            menu.rect={100,200,400,160}
            for i,row in ipairs(menu.rows) do row.rect={120,350-i*24,360,22} end
            local found={}
            for _,control in ipairs(WoWStatusGamepad.controls(menu,{menu})) do found[control]=true end
            for i=1,count do assert(found[menu.rows[i]]) end
            return menu
        end
        p.pick:Click(); local menu=menuControls(2)
        menu.rows[2]:Click()
        assert(WoWStatusDB.firsts.tab=="two")
        p.view:Click(); menu=menuControls(3)
        menu.rows[2]:Click()
        assert(WoWStatusDB.firsts.view=="week" and p.weekOffset==0)
        p.weekBack:Click();assert(p.weekOffset==1)
        assert(p.weekNext:IsEnabled())
    ''')
