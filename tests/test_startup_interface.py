"""Account UI remains reachable when public character identity is not ready."""
import pytest
from test_addon import STUBS, make_lua
from test_client_compatibility import client_runtime

UI = '''
    local methods=getmetatable(CreateFrame("Frame")).__index
    function methods:RegisterForClicks() end
    function methods:GetHeight() return self.height end
    function methods:HookScript() end
    Minimap=CreateFrame("Frame","Minimap",UIParent);Minimap:SetSize(198,198)
    __ready=false;__identityCalls=0
    __secret={};function issecretvalue(value) return value==__secret end
'''


def runtime(edition, extra=''):
    if edition == 'vanilla':
        return make_lua(stubs=STUBS+UI+extra)
    return client_runtime(edition, extra=UI+extra)


@pytest.mark.parametrize('edition', ['vanilla', 'tbc', 'forever', 'retail'])
@pytest.mark.parametrize('api', ['UnitGUID', 'UnitName', 'GetRealmName'])
def test_delayed_identity_keeps_settings_and_icon_and_recovers_without_an_event(edition, api):
    lua = runtime(edition, f'''
        local original={api}
        function {api}(...)
            __identityCalls=__identityCalls+1
            if __ready then return original(...) end
        end
    ''')
    lua.execute('''
        assert(WoWStatusPopups.character()==nil and next(WoWStatusDB.characters)==nil)
        assert(WoWStatusMinimapButton:IsShown() and not WoWStatusDB.minimap_hidden)
        local page=__categories["WoW Status"].page
        assert(__categories.Groups and __categories.Notifications)
        SlashCmdList.WOWSTATUS("")
        page:Show();page.OnShow()
        assert(__opened=="WoW Status" and page.waiting:IsShown())
        for _,name in ipairs({"Groups","Notifications"}) do
            local sub=__categories[name].page
            sub.OnShow();assert(sub.waiting:IsShown())
        end
        WoWStatusMinimapButton.OnClick(WoWStatusMinimapButton,"LeftButton")
        assert(__opened=="WoW Status")
        for _,open in ipairs({WoWStatusGamepad.toggle,WoWStatusGamepad.activity,WoWStatusGamepad.mapFriends}) do
            __opened=nil;open();assert(__opened=="WoW Status")
        end
        __opened=nil;WoWStatusGamepad.togglePage("characters");assert(__opened=="WoW Status")
        local core=__events.PLAYER_LOGIN[#__events.PLAYER_LOGIN]
        assert(core.OnUpdate)
        local calls=__identityCalls
        core.OnUpdate(core,.5)
        assert(__identityCalls==calls and WoWStatusPopups.character()==nil)
        __ready=true
        core.OnUpdate(core,.6)
        assert(WoWStatusPopups.character() and core.OnUpdate==nil)
        assert(page.waiting:IsShown()==false and WoWStatusSetup)
        assert(__categories["WoW Status"].registrations==1)
        assert(WoWStatusMinimapButton:IsShown())
    ''')


@pytest.mark.parametrize('edition', ['forever', 'retail'])
def test_secret_identity_stays_unshared_while_the_basic_ui_is_available(edition):
    lua = runtime(edition, 'function UnitGUID() return __secret end')
    lua.execute('''
        assert(WoWStatusPopups.character()==nil and next(WoWStatusDB.characters)==nil)
        assert(WoWStatusMinimapButton:IsShown() and __categories["WoW Status"])
        local core=__events.PLAYER_LOGIN[#__events.PLAYER_LOGIN]
        for i=1,5 do core.OnUpdate(core,1) end
        assert(WoWStatusPopups.character()==nil and next(WoWStatusDB.characters)==nil)
        assert(#__sent==0)
        __tip={}
        GameTooltip={SetOwner=function() end,SetText=function() end,
            AddLine=function(_,text) __tip[#__tip+1]=text end,Show=function() end}
        WoWStatusMinimapButton.OnEnter(WoWStatusMinimapButton)
        assert(__tip[1]=="Waiting for character information…" and __tip[2]=="Left-click: Options")
    ''')


@pytest.mark.parametrize('edition', ['vanilla', 'tbc', 'forever', 'retail'])
def test_a_deliberately_hidden_icon_stays_hidden_during_delayed_startup(edition):
    lua = runtime(edition, '''
        WoWStatusDB={version=1,characters={},minimap_hidden=true}
        function UnitGUID() return nil end
    ''')
    lua.execute('''
        assert(not WoWStatusMinimapButton:IsShown() and __categories["WoW Status"])
        SlashCmdList.WOWSTATUS("minimap show")
        assert(WoWStatusMinimapButton:IsShown())
        SlashCmdList.WOWSTATUS("minimap hide")
        assert(not WoWStatusMinimapButton:IsShown())
    ''')


def test_settings_registered_after_the_settings_addon_loads_while_identity_waits():
    lua=runtime('forever', """
        __savedSettings=Settings;Settings=nil
        function UnitGUID() return nil end
    """)
    lua.execute("""
        assert(not __categories["WoW Status"] and WoWStatusMinimapButton:IsShown())
        Settings=__savedSettings
        fire("ADDON_LOADED","Blizzard_Settings")
        assert(__categories["WoW Status"] and __categories.Groups)
        SlashCmdList.WOWSTATUS("")
        assert(__categories["WoW Status"].page.waiting:IsShown())
    """)
