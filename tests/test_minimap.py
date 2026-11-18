"""Minimap geometry with simulated frames; rendering requires a game client."""
from pathlib import Path

import pytest
from test_addon import STUBS, lupa

ROOT = Path(__file__).parents[1]


def minimap_runtime(client, source=ROOT / 'addon/shared/Minimap.lua', saved='minimap_angle=0'):
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(STUBS + '''
        function methods:RegisterForClicks() end
        function methods:GetHeight() return self.height end
        function methods:HookScript(event, fn) self[event]=fn end
        function methods:SetPoint(...) self.point={...} end
        Minimap=CreateFrame("Frame","Minimap",UIParent)
        Minimap:SetSize(198,198)
        function Minimap:GetCenter() return 20,30 end
        function Minimap:GetEffectiveScale() return .75 end
        function GetCursorPosition() return 150,22.5 end
        WoWStatusDB={%s}
    ''' % saved)
    lua.execute((ROOT / 'addon/shared/Safe.lua').read_text(encoding='utf-8'))
    lua.globals().WoWStatusAdapter = lua.table_from({'client_id': client})
    lua.execute(source.read_text(encoding='utf-8'))
    lua.execute('WoWStatusMinimap.init(WoWStatusDB)')
    return lua


@pytest.mark.parametrize('client', ['retail', 'forever', 'classic-era', 'tbc-anniversary'])
def test_button_follows_modern_map_rim_and_preserves_classic_distance(client):
    lua = minimap_runtime(client)
    modern = client in ('retail', 'forever')
    assert lua.eval('WoWStatusMinimapButton.point[4]') == (109 if modern else 80)
    lua.execute('''
        assert(WoWStatusDB.minimap_angle==0)
        Minimap:SetSize(280,240)
        Minimap.OnSizeChanged()
    ''')
    assert lua.eval('WoWStatusMinimapButton.point[4]') == (150 if modern else 80)
    lua.execute('WoWStatusDB.minimap_angle=90;Minimap.OnShow()')
    assert lua.eval('WoWStatusMinimapButton.point[4]') == pytest.approx(0, abs=1e-10)
    assert lua.eval('WoWStatusMinimapButton.point[5]') == (130 if modern else 80)
    lua.execute('''
        local button=WoWStatusMinimapButton
        button.OnDragStart(button);button.OnUpdate(button,.1);button.OnDragStop(button)
        assert(WoWStatusDB.minimap_angle==0)
        assert(button.OnUpdate==nil)
    ''')
    assert lua.eval('WoWStatusMinimapButton.point[4]') == (150 if modern else 80)


@pytest.mark.parametrize('client', ['retail', 'forever'])
def test_unavailable_map_dimensions_are_safe_and_later_layout_recovers(client):
    lua = minimap_runtime(client)
    lua.execute('''
        Minimap:SetSize(0,0);Minimap.OnSizeChanged()
        assert(WoWStatusMinimapButton.point[4]==80)
        __secret={}
        function issecretvalue(value) return value==__secret end
        Minimap:SetSize(__secret,198);Minimap.OnSizeChanged()
        assert(WoWStatusMinimapButton.point[4]==80)
        Minimap:SetSize(198,198);Minimap.OnShow()
        assert(WoWStatusMinimapButton.point[4]==109)
    ''')


@pytest.mark.parametrize('client', ['forever', 'classic-era'])
def test_distance_can_be_adjusted_reset_and_reported(client):
    lua = minimap_runtime(client)
    base = lua.eval('WoWStatusMinimapButton.point[4]')
    assert lua.eval('WoWStatusMinimap.setOffset(40)') is True
    assert lua.eval('WoWStatusMinimapButton.point[4]') == base + 30
    for bad in ('81', '-41', '2.5', '"x"'):
        assert lua.eval(f'WoWStatusMinimap.setOffset({bad})') is False
    assert lua.eval('WoWStatusDB.minimap_offset') == 40
    report = lua.eval('WoWStatusMinimap.report()')
    assert report.startswith(client) and 'Minimap=198x198@0.75' in report and 'offset=40' in report
    assert 'MinimapCluster=missing' in report
    lua.execute('WoWStatusMinimap.setOffset(nil)')
    assert lua.eval('WoWStatusMinimapButton.point[4]') == base
    # A corrupt saved value falls back to the default distance.
    lua.execute('WoWStatusDB.minimap_offset=1000; Minimap.OnShow()')
    assert lua.eval('WoWStatusMinimapButton.point[4]') == base


def test_tooltip_shows_who_is_online_and_the_latest_friend_entry():
    from test_roster import pair, pump
    mira, thora = pair()
    pump(mira, thora)
    thora.execute('''
        local methods = getmetatable(CreateFrame("Frame")).__index
        function methods:RegisterForClicks() end
        function methods:HookScript(event, fn) self[event] = fn end
        Minimap=CreateFrame("Frame","Minimap",UIParent)
        function Minimap:GetCenter() return 0,0 end
        function Minimap:GetEffectiveScale() return 1 end
        WoWStatusMinimap.init(WoWStatusDB)
        __tip = {}
        GameTooltip = {SetOwner=function() __tip = {} end, SetText=function() end,
            AddLine=function(_, t) table.insert(__tip, t) end, Show=function() end, Hide=function() end}
        local group = next(character().group_ids)
        WoWStatusJournal.received({sender="Mira-TestRealm",nonce="1-1-a",kind="level",level=30,at=time()-300,group_id=group})
        local button = WoWStatusMinimapButton
        button.OnEnter(button)
        local all = table.concat(__tip, "\\n")
        assert(all:find("Online now: Mira", 1, true), all)
        assert(all:find("Latest: Mira — Reached level 30! · 5 min", 1, true), all)
        assert(all:find("Left-click: Activity log", 1, true))
        assert(all:find("Drag to move", 1, true))
        -- The Retail AddOn Compartment entry shows the same tooltip, minus dragging (#161).
        local owner = CreateFrame("Button")
        WoWStatus_OnAddonCompartmentEnter("WoWStatus", owner)
        local entry = table.concat(__tip, "\\n")
        assert(entry:find("Latest: Mira — Reached level 30! · 5 min", 1, true), entry)
        assert(entry:find("Right-click: Options", 1, true), entry)
        assert(not entry:find("Drag to move", 1, true), entry)
        WoWStatus_OnAddonCompartmentLeave("WoWStatus", owner)
    ''')


def test_retail_compartment_entry_opens_log_and_options():
    lua = minimap_runtime('retail')
    lua.execute('''
        __opened = {}
        WoWStatusJournal = {show=function() table.insert(__opened, "log") end}
        SlashCmdList = {WOWSTATUS=function(msg) table.insert(__opened, "options:"..msg) end}
        -- Before 11.0 the menu passes the mouse button; since 11.0 a table with buttonName.
        WoWStatus_OnAddonCompartmentClick("WoWStatus", "LeftButton")
        WoWStatus_OnAddonCompartmentClick("WoWStatus", "RightButton")
        WoWStatus_OnAddonCompartmentClick("WoWStatus", {buttonName="LeftButton"})
        WoWStatus_OnAddonCompartmentClick("WoWStatus", {buttonName="RightButton"})
        -- Other mouse buttons do nothing, as on the minimap button.
        WoWStatus_OnAddonCompartmentClick("WoWStatus", "MiddleButton")
        WoWStatus_OnAddonCompartmentClick("WoWStatus", {buttonName="Button4"})
        -- The minimap button keeps doing the same two things.
        local button = WoWStatusMinimapButton
        button.OnClick(button, "LeftButton")
        button.OnClick(button, "RightButton")
    ''')
    assert list(lua.eval('__opened').values()) == ['log', 'options:'] * 3


def test_compartment_click_before_setup_reports_instead_of_doing_nothing():
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(STUBS)
    lua.execute((ROOT / 'addon/shared/Safe.lua').read_text(encoding='utf-8'))
    lua.execute((ROOT / 'addon/shared/Minimap.lua').read_text(encoding='utf-8'))
    lua.execute('''
        __opened = {}
        WoWStatusJournal = {show=function() table.insert(__opened, "log") end}
        SlashCmdList = {WOWSTATUS=function(msg) table.insert(__opened, "options:"..msg) end}
        WoWStatus_OnAddonCompartmentClick("WoWStatus", {buttonName="LeftButton"})
    ''')
    assert list(lua.eval('__opened').values()) == ['options:']


def test_compartment_tooltip_hides_only_its_own_and_tolerates_missing_frames():
    lua = minimap_runtime('retail')
    lua.execute('''
        WoWStatusLocale = {T=function(text) return text end}
        __owner, __shown = nil, false
        GameTooltip = {SetOwner=function(_, owner) __owner = owner end, SetText=function() end,
            AddLine=function() end, Show=function() __shown = true end, Hide=function() __shown = false end,
            GetOwner=function() return __owner end}
        local ours, theirs = CreateFrame("Button"), CreateFrame("Button")
        WoWStatus_OnAddonCompartmentEnter("WoWStatus", nil)
        assert(__owner == nil and not __shown)
        WoWStatus_OnAddonCompartmentEnter("WoWStatus", ours)
        assert(__owner == ours and __shown)
        -- The next entry took the tooltip first: leaving ours must not hide it.
        __owner = theirs
        WoWStatus_OnAddonCompartmentLeave("WoWStatus", ours)
        assert(__shown)
        WoWStatus_OnAddonCompartmentEnter("WoWStatus", ours)
        WoWStatus_OnAddonCompartmentLeave("WoWStatus", ours)
        assert(not __shown)
        -- A leave that passes no frame still hides our tooltip, and only ours.
        WoWStatus_OnAddonCompartmentEnter("WoWStatus", ours)
        WoWStatus_OnAddonCompartmentLeave("WoWStatus", nil)
        assert(not __shown)
        WoWStatus_OnAddonCompartmentEnter("WoWStatus", ours)
        __owner = theirs
        WoWStatus_OnAddonCompartmentLeave("WoWStatus", nil)
        assert(__shown)
        -- The minimap button uses the same ownership check.
        local button = WoWStatusMinimapButton
        button.OnEnter(button)
        assert(__owner == button and __shown)
        button.OnLeave(button)
        assert(not __shown)
        GameTooltip = nil
        WoWStatus_OnAddonCompartmentEnter("WoWStatus", ours)
        WoWStatus_OnAddonCompartmentLeave("WoWStatus", ours)
    ''')


@pytest.mark.parametrize('edition', ['retail', 'forever'])
def test_toc_names_compartment_handlers_that_ship_in_that_edition(edition):
    folder = ROOT / 'addon' / edition / 'WoWStatus'
    toc = (folder / 'WoWStatus.toc').read_text(encoding='utf-8').splitlines()
    fields = dict(line[3:].split(': ', 1) for line in toc if line.startswith('## '))
    assert fields['IconTexture'] == 'Interface\\AddOns\\WoWStatus\\Textures\\Logo'
    assert (folder / 'Textures/Logo.tga').is_file()
    assert 'Minimap.lua' in toc
    lua = minimap_runtime(edition, folder / 'Minimap.lua')
    for key in ('AddonCompartmentFunc', 'AddonCompartmentFuncOnEnter', 'AddonCompartmentFuncOnLeave'):
        assert lua.eval(f'type({fields[key]})') == 'function', key


def test_the_button_can_be_hidden_and_shown_again_without_a_reload():
    lua = minimap_runtime('retail')
    assert lua.eval('WoWStatusMinimap.visible()') is True
    assert lua.eval('WoWStatusMinimapButton.visible') is not False
    lua.execute('assert(WoWStatusMinimap.setVisible(false))')
    assert lua.eval('WoWStatusMinimapButton.visible') is False
    assert lua.eval('WoWStatusMinimap.visible()') is False
    assert lua.eval('WoWStatusDB.minimap_hidden') is True
    lua.execute('assert(WoWStatusMinimap.setVisible(true))')
    assert lua.eval('WoWStatusMinimap.visible()') is True
    assert lua.eval('WoWStatusMinimapButton.visible') is True
    # Nothing is left behind in the saved variables once it is shown again.
    assert lua.eval('WoWStatusDB.minimap_hidden') is None


def test_a_login_with_the_button_switched_off_never_shows_it():
    lua = minimap_runtime('retail', saved='minimap_angle=0,minimap_hidden=true')
    assert lua.eval('WoWStatusMinimap.visible()') is False
    assert lua.eval('WoWStatusMinimapButton.visible') is False


def test_the_slash_command_and_the_tick_hide_the_button_and_name_a_way_in():
    from test_addon import make_lua
    lua = make_lua()
    lua.execute("""
        local methods = getmetatable(CreateFrame("Frame")).__index
        function methods:RegisterForClicks() end
        function methods:HookScript(event, fn) self[event] = fn end
        Minimap=CreateFrame("Frame","Minimap",UIParent)
        function Minimap:GetCenter() return 0,0 end
        function Minimap:GetEffectiveScale() return 1 end
        WoWStatusMinimap.init(WoWStatusDB)
        local said, addMessage = {}, DEFAULT_CHAT_FRAME.AddMessage
        DEFAULT_CHAT_FRAME.AddMessage = function(_, message) table.insert(said, message) end
        SlashCmdList.WOWSTATUS("minimap hide")
        SlashCmdList.WOWSTATUS("minimap wobble")
        SlashCmdList.WOWSTATUS("minimap show")
        DEFAULT_CHAT_FRAME.AddMessage = addMessage
        assert(said[1]:find("Minimap button hidden.", 1, true), said[1])
        -- Nobody may hide the button and lose the addon with it.
        assert(said[1]:find("/wstatus", 1, true), said[1])
        assert(said[2]:find("hide | show", 1, true), said[2])
        assert(said[3]:find("Minimap button shown.", 1, true), said[3])
        assert(WoWStatusMinimap.visible())

        -- The tick on the Notifications page does the same, and says so too.
        WoWStatusPreviews.show()
        local tick = WoWStatusNotificationPreviews.minimap
        assert(tick:GetChecked())
        said, addMessage = {}, DEFAULT_CHAT_FRAME.AddMessage
        DEFAULT_CHAT_FRAME.AddMessage = function(_, message) table.insert(said, message) end
        tick:SetChecked(false); tick.OnClick(tick)
        DEFAULT_CHAT_FRAME.AddMessage = addMessage
        assert(not WoWStatusMinimap.visible())
        assert(WoWStatusMinimapButton.visible == false)
        assert(said[1] and said[1]:find("/wstatus", 1, true), said[1] or "nothing said")
        WoWStatusPreviews.show()
        assert(not WoWStatusNotificationPreviews.minimap:GetChecked())
    """)
