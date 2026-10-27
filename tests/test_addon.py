"""Lua harness for home/CI only. Does not start WoW or contact any service."""
from pathlib import Path

import pytest

lupa = pytest.importorskip('lupa')

STUBS = r'''
__events = {}
__frames = {}
__slot = nil
__level = 1
__tick = nil
WoWStatusDB = nil
UIParent = {}
UISpecialFrames = {}
SlashCmdList = {}
WOW_PROJECT_ID = 2
WOW_PROJECT_CLASSIC = 2
DEFAULT_CHAT_FRAME = {AddMessage = function() end}
function GetBuildInfo() return "test", "12345", "today", 11507 end
function UnitGUID() return "Player-123-0001" end
function UnitName() return "Thora" end
function GetRealmName() return "Test Realm" end
function UnitLevel() return __level end
function UnitClass() return "Warrior", "WARRIOR" end
function UnitRace() return "Dwarf" end
function UnitFactionGroup() return "Alliance" end
function GetGuildInfo() return nil end
function GetRealZoneText() return "Dun Morogh" end
function GetInventoryItemLink() return __slot end
function GetMaxPlayerLevel() return 60 end
function RequestTimePlayed() end
function GetItemInfo(link) return "Sword", link, 4 end
function time() return 1793000000 end
LOOT_ITEM_SELF = "You receive loot: %s."
LOOT_ITEM_SELF_MULTIPLE = "You receive loot: %sx%d."
C_Timer = {NewTicker=function(_, fn) __tick=fn end}
local methods = {}
function methods:RegisterEvent(name) __events[name]=self end
function methods:SetScript(name, fn) self[name]=fn end
function methods:GetChecked() return self.checked end
function methods:SetChecked(value) self.checked=value end
function methods:SetText(value) self.text=value end
function methods:Show() self.visible=true end
function methods:Hide() self.visible=false end
function methods:CreateTexture() return setmetatable({}, {__index=methods}) end
function methods:CreateFontString() return setmetatable({}, {__index=methods}) end
for _, name in ipairs({"SetPoint","SetSize","SetWidth","SetJustifyH","SetFrameStrata",
    "EnableMouse","SetMovable","RegisterForDrag","SetAllPoints","SetColorTexture",
    "StartMoving","StopMovingOrSizing"}) do methods[name]=function() end end
function CreateFrame(_, name)
    local f=setmetatable({}, {__index=methods})
    table.insert(__frames,f)
    if name then _G[name]=f end
    return f
end
function fire(event, ...)
    local f=__events[event]
    if f then f.OnEvent(f,event,...) end
end
function character()
    for _, c in pairs(WoWStatusDB.characters) do return c end
end
function clickSharing()
    local c=WoWStatusSetup.checks[1].widget
    c:SetChecked(true)
    c.OnClick(c)
end
function confirmIntro()
    for _,f in ipairs(__frames) do
        if f.text=="Confirm introduction" then f.OnClick(f); return end
    end
end
'''


@pytest.fixture
def lua():
    runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
    runtime.execute(STUBS)
    root = Path(__file__).parents[1] / 'addon/WoWStatus'
    runtime.execute((root / 'Classic.lua').read_text())
    runtime.execute((root / 'WoWStatus.lua').read_text())
    runtime.eval('fire')('PLAYER_LOGIN')
    return runtime


def test_first_run_is_private_and_confirmation_is_required(lua):
    assert lua.eval('character().settings.enabled') is False
    assert lua.eval('#character().events') == 0
    lua.eval('confirmIntro')()
    assert lua.eval('#character().events') == 0
    lua.eval('clickSharing')()
    assert lua.eval('character().enrolled') is True
    assert lua.eval('#character().events') == 0
    lua.eval('confirmIntro')()
    lua.eval('confirmIntro')()
    assert lua.eval('#character().events') == 1
    assert lua.eval('character().events[1].kind') == 'introduction'


def test_real_level_and_pause_scrubs(lua):
    lua.eval('clickSharing')()
    lua.eval('fire')('PLAYER_LEVEL_UP', 10)
    assert lua.eval('character().events[1].data.level') == 10
    lua.eval('SlashCmdList.WOWSTATUS')('pause')
    assert lua.eval('#character().events') == 0
    assert lua.eval('next(character().snapshot)') is None
    lua.eval('fire')('PLAYER_LEVEL_UP', 20)
    assert lua.eval('#character().events') == 0


def test_party_loot_does_not_announce_as_self(lua):
    lua.eval('clickSharing')()
    lua.eval('fire')('CHAT_MSG_LOOT', 'Other receives loot: |Hitem:123|h[Sword]|h.')
    assert lua.eval('#character().events') == 0
    lua.eval('fire')('CHAT_MSG_LOOT', 'You receive loot: |Hitem:123|h[Sword]|h.')
    assert lua.eval('#character().events') == 1
    assert lua.eval('character().events[1].kind') == 'loot'


def test_no_level_event_when_level_profile_is_private(lua):
    lua.eval('clickSharing')()
    lua.execute('character().settings.fields.level=false')
    lua.eval('fire')('PLAYER_LEVEL_UP', 10)
    assert lua.eval('#character().events') == 0
