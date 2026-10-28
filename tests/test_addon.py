"""Lua harness for home/CI only. Does not start WoW or contact any service."""
from datetime import datetime, timezone
from pathlib import Path

import pytest

lupa = pytest.importorskip('lupa')

STUBS = r'''
__events = {}
__frames = {}
__slot = nil
__level = 1
__combat = false
__sent = {}
__joined = true
__restricted = false
__channelNames = {}
__peers = {"Eldrin-TestRealm"}
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
function GetNormalizedRealmName() return "TestRealm" end
function InCombatLockdown() return __combat end
function GetChannelName(name)
    __channelNames[1] = name
    if __joined then return 8,name end return 0,nil
end
function GetNumDisplayChannels() return #__channelNames end
function GetChannelDisplayInfo(index)
    return __channelNames[index],false,false,8,#__peers
end
C_ChatInfo = {
    InChatMessagingLockdown=function() return __restricted end,
    RegisterAddonMessagePrefix=function() return true end,
    GetChannelRosterInfo=function(_, index) return __peers[index] end,
    SendAddonMessage=function(prefix,text,kind,target)
        table.insert(__sent,{prefix=prefix,text=text,kind=kind,target=target})
        return true
    end,
    SendChatMessage=function(text,kind,language,target)
        table.insert(__sent,{text=text,kind=kind,target=target})
    end,
}
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
function methods:RegisterEvent(name)
    __events[name] = __events[name] or {}
    table.insert(__events[name],self)
end
function methods:GetFrameStrata() return "DIALOG" end
function methods:GetFrameLevel() return 5 end
function methods:SetParent(parent) self.parent=parent end
function methods:GetParent() return self.parent end
function methods:SetScale(value) self.scale=value end
function methods:SetAlpha(value) self.alpha=value end
function methods:SetTexture(value) self.texture=value end
function methods:GetWidth() return self.width or 700 end
function methods:SetWidth(width) self.width=width end
function methods:SetSize(width, height) self.width=width; self.height=height end
function methods:SetFontObject(font) self.font=font end
function methods:SetFocus() self.focused=true end
function methods:SetMultiLine(value) self.multiline=value end
function methods:GetVerticalScroll() return self.scroll or 0 end
function methods:SetShown(value) self.visible=value end
function methods:SetScript(name, fn) self[name]=fn end
function methods:GetChecked() return self.checked end
function methods:SetChecked(value) self.checked=value end
function methods:SetText(value) self.text=value end
function methods:GetText() return self.text or "" end
function methods:Insert(value) self.text=(self.text or "")..value end
function methods:Show() self.visible=true end
function methods:Hide() self.visible=false end
function methods:IsShown() return self.visible end
function methods:GetStringHeight() return #(self.text or "") / 2 end
function methods:SetScrollChild(child) self.child=child end
function methods:SetVerticalScroll(value) self.scroll=value end
function methods:CreateLine() return setmetatable({}, {__index=methods}) end
function methods:CreateTexture() return setmetatable({}, {__index=methods}) end
function methods:CreateFontString(_, _, font) return setmetatable({font=font}, {__index=methods}) end
for _, name in ipairs({"SetPoint","SetJustifyH","SetFrameStrata",
    "EnableMouse","SetMovable","RegisterForDrag","SetAllPoints","SetColorTexture",
    "StartMoving","StopMovingOrSizing","SetHeight","SetJustifyV","ClearAllPoints",
    "SetBlendMode","SetVertexColor","SetTextColor","SetWordWrap","SetFrameLevel","SetTextInsets","ClearFocus","SetThickness","SetStartPoint","SetEndPoint","SetAutoFocus","SetMaxLetters"}) do methods[name]=function() end end
function CreateFrame(kind, name, parent, template)
    local f=setmetatable({kind=kind,parent=parent,template=template}, {__index=methods})
    table.insert(__frames,f)
    if name then _G[name]=f end
    return f
end
function fire(event, ...)
    for _,f in ipairs(__events[event] or {}) do f.OnEvent(f,event,...) end
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
        if f.text=="Introduce character" then f.OnClick(f); return end
    end
end
'''


def make_lua(stubs=STUBS):
    runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
    runtime.execute(stubs)
    runtime.globals().date = lambda fmt, at: datetime.fromtimestamp(
        at, timezone.utc).strftime(fmt.lstrip('!'))
    root = Path(__file__).parents[1] / 'addon/vanilla/WoWStatus'
    runtime.execute((root / 'Safe.lua').read_text(encoding='utf-8'))
    runtime.execute((root / 'CaseFold.lua').read_text(encoding='utf-8'))
    runtime.execute((root / 'Vanilla.lua').read_text(encoding='utf-8'))
    runtime.execute((root / 'Progress.lua').read_text(encoding='utf-8'))
    runtime.execute((root / 'History.lua').read_text(encoding='utf-8'))
    runtime.execute((root / 'HistoryUI.lua').read_text(encoding='utf-8'))
    runtime.execute((root / 'Groups.lua').read_text(encoding='utf-8'))
    runtime.execute((root / 'Popups.lua').read_text(encoding='utf-8'))
    runtime.execute((root / 'Previews.lua').read_text(encoding='utf-8'))
    runtime.execute((root / 'Milestones.lua').read_text(encoding='utf-8'))
    runtime.execute((root / 'WoWStatus.lua').read_text(encoding='utf-8'))
    runtime.eval('fire')('PLAYER_LOGIN')
    return runtime


@pytest.fixture
def lua():
    return make_lua()


def test_first_run_sharing_defaults_on_and_introduction_requires_confirmation(lua):
    assert lua.eval('character().settings.enabled') is True
    assert lua.eval('#character().events') == 0
    assert lua.eval('character().settings.introduction_confirmed') is False
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


def test_persistent_history_outlives_recent_buffer(lua):
    lua.eval('clickSharing')()
    lua.execute('''for i=1,550 do SlashCmdList.WOWSTATUS("test") end''')
    assert lua.eval('#character().events') == 500
    assert lua.eval('#character().history.events') == 550
    lua.eval('SlashCmdList.WOWSTATUS')('pause')
    assert lua.eval('#character().history.events') == 0
    assert lua.eval('#character().history.tracking.points') == 0


def test_level_times_are_partial_then_complete_and_ignore_synthetic(lua):
    lua.eval('clickSharing')()
    lua.execute('''
        __at = 1793000000
        function time() return __at end
        __at = __at + 600
        __level = 2
        fire("PLAYER_LEVEL_UP",2)
        __at = __at + 900
        __level = 3
        fire("PLAYER_LEVEL_UP",3)
    ''')
    assert lua.eval('#WoWStatusHistory.timing(character())') == 2
    assert lua.eval('WoWStatusHistory.timing(character())[1].partial') is True
    assert lua.eval('WoWStatusHistory.timing(character())[2].partial') is False
    assert lua.eval('WoWStatusHistory.timing(character())[2].seconds') == 900
    lua.eval('SlashCmdList.WOWSTATUS')('test')
    assert lua.eval('#WoWStatusHistory.timing(character())') == 2


def test_missing_levels_break_the_line_without_fabricating_durations(lua):
    lua.eval('clickSharing')()
    lua.execute('''__level=10; fire("PLAYER_LEVEL_UP",10)''')
    assert lua.eval('#WoWStatusHistory.timing(character())') == 0
    assert lua.eval('character().history.tracking.points[1].segment') != lua.eval(
        'character().history.tracking.points[2].segment')


def test_history_and_line_graph_open_and_reuse_regions(lua):
    lua.eval('clickSharing')()
    lua.eval('SlashCmdList.WOWSTATUS')('logs')
    assert lua.eval('WoWStatusHistoryWindow:IsShown()') is True
    lua.eval('SlashCmdList.WOWSTATUS')('graph')
    lua.execute('''__level=2; fire("PLAYER_LEVEL_UP",2); WoWStatusHistoryUI.refresh()''')
    regions = lua.eval('#WoWStatusHistoryWindow.graphObjects')
    lua.eval('WoWStatusHistoryUI.refresh')()
    assert lua.eval('#WoWStatusHistoryWindow.graphObjects') == regions


def test_oslo_offsets_ignore_host_timezone(lua):
    assert lua.eval('WoWStatusHistory.oslo')(1793128500) == '2026-10-27 20:15:00 +01:00'
    summer = int(datetime(2026, 7, 1, 12, tzinfo=timezone.utc).timestamp())
    assert lua.eval('WoWStatusHistory.oslo')(summer) == '2026-07-01 14:00:00 +02:00'


def test_legacy_messages_require_explicit_channel_and_trusted_sender(lua):
    packet = 'WSTATUS1 LEVEL 25 1793000000 event-1'
    receive = lua.eval('WoWStatusPopups.receive')
    assert receive(packet, 'Eldrin-TestRealm', 'WStatusFriends') is False
    lua.eval('SlashCmdList.WOWSTATUS')('popup channel WStatusFriends')
    lua.eval('SlashCmdList.WOWSTATUS')('popup on')
    assert receive(packet, 'Eldrin-TestRealm', 'WStatusFriends') is False
    assert lua.eval('WoWStatusLevelPopup') is None


def test_trusted_friend_popup_uses_sender_and_suppresses_duplicates(lua):
    command = lua.eval('SlashCmdList.WOWSTATUS')
    command('popup channel WStatusFriends')
    command('popup on')
    command('popup trust Eldrin-TestRealm Frank')
    receive = lua.eval('WoWStatusPopups.receive')
    packet = 'WSTATUS1 LEVEL 25 1793000000 event-1'
    assert receive(packet, 'Eldrin-TestRealm', 'WStatusFriends') is True
    assert lua.eval('WoWStatusLevelPopup.message.text') == 'Frank’s Eldrin reached level 25!'
    assert receive(packet, 'Eldrin-TestRealm', 'WStatusFriends') is False
    # A different nonce does not replay the same sender/level.
    assert receive(packet.replace('event-1', 'event-2'), 'Eldrin-TestRealm', 'WStatusFriends') is False
    assert lua.eval('#character().events') == 0  # never upload peer events as our own


def test_popup_waits_for_combat_and_off_discards_it(lua):
    command = lua.eval('SlashCmdList.WOWSTATUS')
    command('popup channel WStatusFriends')
    command('popup on')
    command('popup trust Eldrin-TestRealm')
    lua.execute('__combat=true')
    receive = lua.eval('WoWStatusPopups.receive')
    assert receive('WSTATUS1 LEVEL 25 1793000000 event-1', 'Eldrin-TestRealm', 'WStatusFriends')
    assert lua.eval('WoWStatusLevelPopup') is None
    command('popup off')
    lua.execute('__combat=false; fire("PLAYER_REGEN_ENABLED")')
    assert lua.eval('WoWStatusLevelPopup') is None


def test_popup_appears_after_combat_when_still_enabled(lua):
    command = lua.eval('SlashCmdList.WOWSTATUS')
    command('popup channel WStatusFriends')
    command('popup on')
    command('popup trust Eldrin-TestRealm')
    lua.execute('__combat=true')
    lua.eval('WoWStatusPopups.receive')('WSTATUS1 LEVEL 25 1793000000 event-1',
                                       'Eldrin-TestRealm', 'WStatusFriends')
    lua.execute('__combat=false; fire("PLAYER_REGEN_ENABLED")')
    assert lua.eval('WoWStatusLevelPopup:IsShown()') is True


def test_bad_stale_other_channel_and_self_messages_are_rejected(lua):
    command = lua.eval('SlashCmdList.WOWSTATUS')
    command('popup channel WStatusFriends')
    command('popup on')
    command('popup trust Eldrin-TestRealm')
    command('popup trust Thora-TestRealm')
    receive = lua.eval('WoWStatusPopups.receive')
    assert receive('WSTATUS1 LEVEL 99 1793000000 e1', 'Eldrin-TestRealm', 'WStatusFriends') is False
    assert receive('WSTATUS1 LEVEL 25 1792000000 e1', 'Eldrin-TestRealm', 'WStatusFriends') is False
    assert receive('WSTATUS1 LEVEL 25 1793000000 e1', 'Eldrin-TestRealm', 'General') is False
    assert receive('WSTATUS1 LEVEL 25 1793000000 e1', 'Thora-TestRealm', 'WStatusFriends') is False
    assert receive('WSTATUS1 LEVEL 25 1793000000 |Tbad', 'Eldrin-TestRealm', 'WStatusFriends') is False


def test_real_levels_broadcast_only_after_explicit_opt_in_and_sharing(lua):
    command = lua.eval('SlashCmdList.WOWSTATUS')
    command('popup channel WStatusFriends')
    command('popup send on')
    command('pause')
    lua.eval('fire')('PLAYER_LEVEL_UP', 2)
    assert lua.eval('#__sent') == 0
    lua.eval('clickSharing')()
    command('test')  # synthetic events never broadcast
    assert lua.eval('#__sent') == 0
    lua.eval('fire')('PLAYER_LEVEL_UP', 2)
    assert lua.eval('#__sent') == 1
    assert lua.eval('__sent[1].kind') == 'CHANNEL'
    assert lua.eval('__sent[1].target') == '8'
    assert lua.eval('__sent[1].text').startswith('WSTATUS2 classic-era LEVEL 2 ')


def test_restrictions_hold_broadcast_and_privacy_pause_cancels(lua):
    command = lua.eval('SlashCmdList.WOWSTATUS')
    command('popup channel WStatusFriends')
    lua.eval('clickSharing')()
    command('popup send on')
    lua.execute('__restricted=true')
    lua.eval('fire')('PLAYER_LEVEL_UP', 2)
    assert lua.eval('#__sent') == 0
    assert lua.eval('WoWStatusDB.popups.last_send.state') == 'chat_restricted'
    command('pause')
    lua.execute('__restricted=false; WoWStatusPopups.tick()')
    assert lua.eval('#__sent') == 0


def test_local_popup_preview_never_broadcasts_or_changes_progress(lua):
    command = lua.eval('SlashCmdList.WOWSTATUS')
    command('popup channel WStatusFriends')
    command('popup on')
    points_before = lua.eval('#character().history.tracking.points')
    command('popup test')
    assert lua.eval('WoWStatusLevelPopup:IsShown()') is True
    assert lua.eval('#__sent') == 0
    assert lua.eval('#character().events') == 0
    assert lua.eval('#character().history.tracking.points') == points_before


def test_popup_preferences_never_enter_exported_character_snapshot(lua):
    command = lua.eval('SlashCmdList.WOWSTATUS')
    command('popup channel WStatusFriends')
    command('popup on')
    command('popup trust Eldrin-TestRealm PrivateLocalLabel')
    assert lua.eval('WoWStatusDB.popups.sound') is False
    assert lua.eval('character().snapshot.popups') is None
    assert lua.eval('character().settings.popups') is None


def test_no_auto_retry_after_send_raises(lua):
    command = lua.eval('SlashCmdList.WOWSTATUS')
    command('popup channel WStatusFriends')
    lua.eval('clickSharing')()
    command('popup send on')
    lua.execute('C_ChatInfo.SendChatMessage=function() error("restricted") end')
    lua.eval('fire')('PLAYER_LEVEL_UP', 2)
    assert lua.eval('WoWStatusDB.popups.last_send.state') == 'blocked_or_uncertain'
    lua.execute('''
        C_ChatInfo.SendChatMessage=function(text) table.insert(__sent,{text=text}) end
        WoWStatusPopups.tick()
    ''')
    assert lua.eval('#__sent') == 0


def test_free_text_groups_match_python_keys_and_support_two_destinations(lua):
    from wow_status.group_routing import group_key
    for label in ['Weekend Crew', 'Old friends #2', 'Ærlig gjeng! 🎮']:
        key, cleaned = lua.eval('WoWStatusGroups.key')(label)
        assert key == group_key(label)
        assert cleaned == label
    ok, _ = lua.eval('WoWStatusGroups.update')('Weekend Crew\nOld friends #2', 'Frank')
    assert ok is True
    assert lua.eval('WoWStatusDB.player_name') == 'Frank'
    assert lua.eval('WoWStatusGroups.text(character(),true)') == 'Old friends #2\nWeekend Crew'
    lua.eval('SlashCmdList.WOWSTATUS')('groups')
    assert lua.eval('WoWStatusGroupWindow:IsShown()') is True


def test_group_popups_do_not_require_character_trust_and_dedupe_between_groups(lua):
    from wow_status.group_routing import group_key
    first, second = group_key('Weekend Crew'), group_key('Old friends #2')
    lua.eval('WoWStatusGroups.update')('Weekend Crew\nOld friends #2', 'Frank')
    lua.eval('SlashCmdList.WOWSTATUS')('popup on')
    receive = lua.eval('WoWStatusPopups.receive')
    packet = 'WSTATUS1 LEVEL 25 1793000000 e1'
    assert receive(packet, 'Eldrin-TestRealm', 'WStatus' + first) is True
    assert receive(packet, 'Eldrin-TestRealm', 'WStatus' + second) is False
    assert receive(packet, 'Other-TestRealm', 'WStatusFriends') is False
    lua.eval('WoWStatusGroups.update')('Old friends #2', 'Frank')
    assert receive(packet.replace('25', '26'), 'Eldrin-TestRealm', 'WStatus' + first) is False


def test_empty_group_list_has_no_implicit_popup_destination(lua):
    lua.eval('clickSharing')()
    command = lua.eval('SlashCmdList.WOWSTATUS')
    command('popup send on')
    lua.eval('fire')('PLAYER_LEVEL_UP', 2)
    assert lua.eval('#__sent') == 0
    assert lua.eval('WoWStatusDB.popups.last_send.state') == 'no_group_selected'


def test_level_context_uses_client_played_boundaries_and_scrubs_privacy(lua):
    lua.eval('clickSharing')()
    lua.execute('''
        character().settings.fields.playtime=true
        character().settings.fields.zone=true
        fire("TIME_PLAYED_MSG", 1000, 200)
        __level=2; fire("PLAYER_LEVEL_UP", 2)
        fire("TIME_PLAYED_MSG", 1505, 5)
    ''')
    assert lua.eval('character().events[1].data.played_level_seconds') == 700
    assert lua.eval('character().history.events[1].data.played_level_seconds') == 700
    assert lua.eval('character().events[1].data.zone') == 'Dun Morogh'
    lua.execute('character().settings.fields.playtime=false; character().settings.fields.zone=false')
    lua.eval('fire')('PLAYER_LOGOUT')
    assert lua.eval('character().events[1].data.played_level_seconds') is None
    assert lua.eval('character().history.events[1].data.zone') is None
    assert lua.eval('character().played_boundary') is None


def test_missing_played_boundary_does_not_invent_level_duration(lua):
    lua.eval('clickSharing')()
    lua.execute('''
        character().settings.fields.playtime=true
        __level=10; fire("PLAYER_LEVEL_UP",10)
        fire("TIME_PLAYED_MSG", 9000, 5)
    ''')
    assert lua.eval('character().events[1].data.played_level_seconds') is None


def test_rapid_distinct_popup_levels_are_coalesced_and_replay_stays_blocked(lua):
    command = lua.eval('SlashCmdList.WOWSTATUS')
    command('popup channel WStatusFriends')
    command('popup on')
    command('popup trust Eldrin-TestRealm')
    receive = lua.eval('WoWStatusPopups.receive')
    assert receive('WSTATUS1 LEVEL 10 1793000000 a', 'Eldrin-TestRealm', 'WStatusFriends')
    assert receive('WSTATUS1 LEVEL 11 1793000000 b', 'Eldrin-TestRealm', 'WStatusFriends')
    assert receive('WSTATUS1 LEVEL 12 1793000000 c', 'Eldrin-TestRealm', 'WStatusFriends')
    lua.execute('function time() return 1793000700 end')
    assert receive('WSTATUS1 LEVEL 10 1793000700 d', 'Eldrin-TestRealm', 'WStatusFriends') is False


def test_unavailable_loading_level_is_omitted_instead_of_exporting_zero(lua):
    lua.eval('clickSharing')()
    lua.execute('__level=0; fire("PLAYER_ENTERING_WORLD")')
    assert lua.eval('character().snapshot.level') is None



def test_all_new_character_sharing_checkboxes_default_on(lua):
    assert lua.eval('character().settings.enabled') is True
    assert lua.eval('character().enrolled') is True
    for section in ['fields', 'collection', 'announcements']:
        assert lua.eval(f"function() for _, enabled in pairs(character().settings.{section}) "
                        "do if not enabled and _ ~= 'equipment' then return false end end return true end")()
    assert lua.eval('character().settings.introduction_confirmed') is False


def test_groups_apply_account_wide_without_changing_character_settings_or_history(lua):
    lua.execute('''
        active = character()
        other = WoWStatusHistory.copy(active)
        other.identity.guid = "Player-other"
        other.settings.enabled = false
        other.settings.fields.gear = false
        WoWStatusDB.characters.other = other
        clock = 1793000100
        function time() return clock end
    ''')
    update = lua.eval('WoWStatusGroups.update')
    assert update('Weekend Crew', 'Frank')[0]
    lua.eval('fire')('PLAYER_LEVEL_UP', 10)
    lua.execute('clock = clock + 100')
    assert update('Weekend Crew\nSecond group', 'Frank')[0]
    assert lua.eval('WoWStatusGroups.text(other,true)') == 'Second group\nWeekend Crew'
    assert lua.eval('other.player_name') == 'Frank'
    assert lua.eval('other.settings.enabled') is False
    assert lua.eval('other.settings.fields.gear') is False
    assert lua.eval('function() for _, m in pairs(other.group_ids) do '
                    'if m.label == "Weekend Crew" then return m.joined_at end end end')() == 1793000100
    assert lua.eval('function() for _, m in pairs(active.group_ids) do '
                    'if m.label == "Second group" then return m.joined_at end end end')() == 1793000200
    assert lua.eval('function() local n=0; for _ in pairs(active.events[1].group_ids) '
                    'do n=n+1 end return n end')() == 1
    assert update('', 'Frank')[0]
    assert lua.eval('next(other.group_ids)') is None
    assert lua.eval('next(active.group_ids)') is None
    assert lua.eval('next(WoWStatusDB.account_groups)') is None


def test_account_groups_migrate_and_new_characters_inherit_them(lua):
    lua.execute('''
        local key = WoWStatusGroups.key("Old crew")
        character().group_ids = {[key] = {label="Old crew", joined_at=1792000000}}
        WoWStatusDB.account_groups = nil
        WoWStatusGroups.init(WoWStatusDB, character, function() end)
        assert(WoWStatusDB.account_groups[key] == "Old crew")
        assert(character().group_ids[key].joined_at == 1792000000)
        newcomer = WoWStatusHistory.copy(character())
        newcomer.group_ids = {}
        WoWStatusDB.characters.newcomer = newcomer
        WoWStatusGroups.init(WoWStatusDB, function() return newcomer end, function() end)
        assert(newcomer.group_ids[key].joined_at == time())
        assert(newcomer.group_ids[key].baseline_level == 1)
    ''')


def test_group_editor_adds_and_removes_account_groups_immediately(lua):
    command = lua.eval('SlashCmdList.WOWSTATUS')
    command('groups')
    assert lua.eval('WoWStatusSetup:IsShown()') is False
    assert lua.eval('WoWStatusGroupWindow:IsShown()') is True
    assert lua.eval('WoWStatusGroupWindow.input.template') == 'InputBoxTemplate'
    assert lua.eval('WoWStatusGroupWindow.input.multiline') is False
    lua.execute('''
        local p = WoWStatusGroupWindow
        p.name:SetText("Frank")
        p.input:SetText("  navsquad  ")
        p.input.OnEnterPressed(p.input)
        assert(WoWStatusGroups.text(character(), true) == "navsquad")
        assert(p.input:GetText() == "")
        assert(p.input.focused)
        assert(p.rows[1].label:GetText() == "navsquad")
        assert(p.rows[1]:IsShown())
        assert(not p.rows[2]:IsShown())
        assert(not p.empty:IsShown())
        p.input:SetText("ronkalot")
        p.add.OnClick()
        assert(WoWStatusDB.player_name == "Frank")
        assert(p.rows[2].label:GetText() == "ronkalot")
        p.rows[2].remove.OnClick()
        assert(WoWStatusGroups.text(character(), true) == "navsquad")
        p.rows[1].remove.OnClick()
        assert(next(WoWStatusDB.account_groups) == nil)
        assert(next(character().group_ids) == nil)
        assert(p.empty:IsShown())
        p.name:SetText("New name")
        p.saveName.OnClick()
        assert(WoWStatusDB.player_name == "New name")
    ''')
    command('')
    assert lua.eval('WoWStatusSetup:IsShown()') is True
    assert lua.eval('WoWStatusGroupWindow:IsShown()') is False


def test_group_editor_rejects_invalid_duplicate_and_ninth_group(lua):
    lua.eval('SlashCmdList.WOWSTATUS')('groups')
    lua.execute('''
        local p = WoWStatusGroupWindow
        p.input:SetText(" ")
        p.add.OnClick()
        assert(next(WoWStatusDB.account_groups) == nil)
        p.input:SetText("one\\ntwo")
        p.add.OnClick()
        assert(next(WoWStatusDB.account_groups) == nil)
        for i=1,8 do
            p.input:SetText("Group " .. i)
            p.add.OnClick()
        end
        assert(p.count:GetText() == "Groups (8 / 8)")
        p.input:SetText("GROUP 1")
        p.add.OnClick()
        assert(p.status:GetText():find("already"))
        p.input:SetText("Group 9")
        p.add.OnClick()
        assert(p.status:GetText():find("up to 8"))
        p.rows[4].remove.OnClick()
        p.add.OnClick()
        assert(p.count:GetText() == "Groups (8 / 8)")
        assert(not WoWStatusGroups.contains(character(), WoWStatusGroups.key("Group 4")))
        assert(WoWStatusGroups.contains(character(), WoWStatusGroups.key("Group 9")))
    ''')


def test_native_settings_register_once_and_keep_groups_on_separate_page(lua):
    lua.execute('''
        __categories = {}
        Settings = {
            RegisterCanvasLayoutCategory = function(page, name)
                local c = {page=page,name=name,GetID=function(self) return self.name end}
                __categories[name] = c
                return c
            end,
            RegisterCanvasLayoutSubcategory = function(parent, page, name)
                local c = Settings.RegisterCanvasLayoutCategory(page, name)
                c.parent = parent
                return c
            end,
            RegisterAddOnCategory = function(category)
                category.registrations = (category.registrations or 0) + 1
            end,
            OpenToCategory = function(id)
                __opened = id
                __categories[id].page.OnShow()
            end,
        }
        WoWStatusGroups.update("ronkalot", "Frank")
        fire("ADDON_LOADED", "Blizzard_Settings")
        assert(__categories["WoW Status"] ~= nil)
        -- Sidebar first-open path: Blizzard can call OnRefresh without OnShow.
        -- The content must already exist and be populated before either callback.
        assert(not __categories.Groups.page:IsShown())
        assert(WoWStatusGroupWindow.rows[1].label:GetText() == "ronkalot")
        assert(WoWStatusGroupWindow.name:GetText() == "Frank")
        __categories.Groups.page.OnRefresh()
        assert(WoWStatusGroupWindow.rows[1].label:GetText() == "ronkalot")
        assert(WoWStatusGroupWindow:GetParent().child == WoWStatusGroupWindow)
        assert(WoWStatusGroupWindow.scale == 1)
        SlashCmdList.WOWSTATUS("")
        assert(__opened == "WoW Status")
        assert(WoWStatusSetup:GetParent() ~= UIParent)
        assert(not WoWStatusSetup.close:IsShown())
        assert(WoWStatusSetup.width >= 600)
        assert(WoWStatusSetup.scale == 1)
        assert(WoWStatusSetup.checks[1].widget.width == 32)
        local sharingScroll = WoWStatusSetup:GetParent()
        sharingScroll.width = 600
        __categories["WoW Status"].page.OnSizeChanged()
        assert(WoWStatusSetup.scale == 1)
        assert(WoWStatusSetup.width == 600)
        assert(WoWStatusSetup.preview.font == "GameFontHighlightLarge")
        SlashCmdList.WOWSTATUS("groups")
        assert(__opened == "Groups")
        assert(__categories.Groups.parent == __categories["WoW Status"])
        assert(WoWStatusGroupWindow:GetParent() ~= UIParent)
        assert(not WoWStatusGroupWindow.close:IsShown())
        WoWStatusGroupWindow.input:SetText("Unsaved edits")
        __categories.Groups.page.OnSizeChanged()
        __categories.Groups.page.OnRefresh()
        assert(WoWStatusGroupWindow.input:GetText() == "Unsaved edits")
        SlashCmdList.WOWSTATUS("")
        assert(__categories["WoW Status"].registrations == 1)
        assert(__categories.Groups.registrations == 1)
        for _, name in ipairs(UISpecialFrames) do
            assert(name ~= "WoWStatusSetup" and name ~= "WoWStatusGroupWindow")
        end
    ''')



def test_legacy_options_menu_registers_both_pages(lua):
    lua.execute('''
        __pages = {}
        function InterfaceOptions_AddCategory(page) __pages[page.name] = page end
        function InterfaceOptionsFrame_OpenToCategory(page)
            __opened = page.name
            page.OnShow()
        end
        SlashCmdList.WOWSTATUS("")
        assert(__opened == "WoW Status")
        SlashCmdList.WOWSTATUS("groups")
        assert(__opened == "Groups")
        assert(__pages.Groups.parent == "WoW Status")
        assert(WoWStatusGroupWindow:GetParent() ~= UIParent)
    ''')


def test_legacy_upload_choice_survives_account_group_initialization(lua):
    lua.execute('''
        WoWStatusGroups.update("Crew", "Frank")
        SlashCmdList.WOWSTATUS("groups legacy")
        WoWStatusGroups.init(WoWStatusDB, character, function() end)
        assert(character().legacy_upload)
        assert(next(character().group_ids) == nil)
        WoWStatusGroups.update("Crew", "Frank")
        assert(not character().legacy_upload)
        assert(next(character().group_ids) ~= nil)
    ''')



def test_snapshot_repairs_missing_enrollment_on_enabled_characters(lua):
    lua.execute('character().enrolled=nil')
    lua.eval('fire')('PLAYER_ENTERING_WORLD')
    assert lua.eval('character().enrolled') is True
    lua.execute('character().enrolled=nil; character().settings.enabled=false')
    lua.eval('fire')('PLAYER_ENTERING_WORLD')
    assert lua.eval('character().enrolled') is None



def test_ingame_default_does_not_enable_discord(lua):
    assert lua.eval('WoWStatusDB.popups.receive') is True
    assert lua.eval('WoWStatusDB.popups.broadcast') is True
    assert lua.eval('character().settings.discord_enabled') is False
    lua.eval('SlashCmdList.WOWSTATUS')('discord')
    assert lua.eval('WoWStatusDiscordSettings.checks[1].widget:GetChecked()') is False
    lua.execute('''
        local toggle = WoWStatusDiscordSettings.checks[1].widget
        toggle:SetChecked(true); toggle.OnClick(toggle)
        assert(character().settings.discord_enabled)
        assert(character().discord_enrolled)
        assert(character().discord_since == time())
        assert(character().settings.discord_delivery == "summary")
        toggle:SetChecked(false); toggle.OnClick(toggle)
        assert(not character().settings.discord_enabled)
        assert(WoWStatusDB.popups.broadcast)
    ''')


def test_two_clients_share_level_updates_without_companion_or_discord():
    sender = make_lua()
    receiver = make_lua(STUBS.replace('return "Thora" end', 'return "Eldrin" end'))
    for client in [sender, receiver]:
        client.eval('WoWStatusGroups.update')('navsquad', 'Friend')
    sender.eval('fire')('PLAYER_LEVEL_UP', 2)
    packet = sender.eval('__sent[1].text')
    assert sender.eval('__sent[1].kind') == 'WHISPER'
    assert sender.eval('__sent[1].target') == 'Eldrin-TestRealm'
    assert sender.eval('character().settings.discord_enabled') is False
    receiver.eval('fire')('CHAT_MSG_ADDON', 'WoWStatus', packet, 'WHISPER', 'Thora-TestRealm')
    assert receiver.eval('WoWStatusLevelPopup.message:GetText()') == 'Thora reached level 2!'
    assert receiver.eval('#WoWStatusDB.popups.activity') == 1
    assert receiver.eval('#character().events') == 0
    receiver.eval('fire')('CHAT_MSG_ADDON', 'WoWStatus', packet, 'WHISPER', 'Thora-TestRealm')
    assert receiver.eval('#WoWStatusDB.popups.activity') == 1
    receiver.eval('SlashCmdList.WOWSTATUS')('activity')
    assert 'Thora' in receiver.eval('WoWStatusActivity.text:GetText()')
    receiver.eval('WoWStatusGroups.update')('', 'Friend')
    assert receiver.eval('#WoWStatusDB.popups.activity') == 0
    assert 'Thora' not in receiver.eval('WoWStatusActivity.text:GetText()')


def test_generic_events_share_only_with_selected_groups_and_honor_privacy():
    sender = make_lua()
    receiver = make_lua(STUBS.replace('return "Thora" end', 'return "Eldrin" end'))
    for client in [sender, receiver]:
        client.eval('WoWStatusGroups.update')('navsquad', '')
    sender.eval('fire')('PLAYER_DEAD')
    packet = sender.eval('__sent[1].text')
    assert 'WSTATUS3 classic-era death' in packet
    assert len(packet.encode()) <= 243
    receiver.eval('fire')('CHAT_MSG_ADDON', 'WoWStatus', packet, 'WHISPER', 'Thora-TestRealm')
    assert 'Total deaths: 1' in receiver.eval('WoWStatusLevelPopup.message:GetText()')
    assert receiver.eval('#WoWStatusDB.popups.activity') == 1
    receiver.eval('fire')('CHAT_MSG_ADDON', 'OtherAddon', packet, 'WHISPER', 'Thora-TestRealm')
    assert receiver.eval('#WoWStatusDB.popups.activity') == 1
    sender.execute('character().settings.in_game.death=false')
    sender.eval('fire')('PLAYER_DEAD')
    assert sender.eval('#__sent') == 1
    receiver.eval('WoWStatusGroups.update')('', '')
    receiver.eval('fire')('CHAT_MSG_ADDON', 'WoWStatus', packet, 'WHISPER', 'Thora-TestRealm')
    assert receiver.eval('#WoWStatusDB.popups.activity') == 0


def test_discovery_waits_for_real_peers_and_never_sends_custom_channel_data(lua):
    lua.eval('WoWStatusGroups.update')('navsquad', '')
    lua.execute('__peers = {}')
    lua.eval('fire')('PLAYER_LEVEL_UP', 2)
    assert lua.eval('#__sent') == 0
    assert lua.eval('WoWStatusDB.popups.last_send.state') == 'waiting_for_group_peers'
    lua.execute('__peers={"Eldrin-TestRealm"}; fire("CHANNEL_ROSTER_UPDATE")')
    assert lua.eval('__sent[1].kind') == 'WHISPER'
    assert lua.eval('__sent[1].prefix') == 'WoWStatus'



def test_synchronous_roster_events_do_not_duplicate_outgoing_updates(lua):
    lua.eval('WoWStatusGroups.update')('navsquad', '')
    lua.execute('''
        function SetSelectedDisplayChannel(index) fire("CHANNEL_ROSTER_UPDATE",index,1) end
    ''')
    lua.eval('fire')('PLAYER_LEVEL_UP', 2)
    assert lua.eval('#__sent') == 1



def test_toast_has_event_icon_and_fades_without_recording_preview(lua):
    lua.eval('SlashCmdList.WOWSTATUS')('popup test')
    assert lua.eval('WoWStatusLevelPopup.icon.texture').endswith('Textures\\LevelUp')
    assert lua.eval('WoWStatusLevelPopup.heading:GetText()') == 'LEVEL UP!'
    assert lua.eval('WoWStatusLevelPopup.alpha') == 0
    lua.execute('WoWStatusLevelPopup.OnUpdate(WoWStatusLevelPopup, .11)')
    assert lua.eval('WoWStatusLevelPopup.alpha') == pytest.approx(.5)
    lua.execute('WoWStatusLevelPopup.OnUpdate(WoWStatusLevelPopup, 6)')
    assert lua.eval('WoWStatusLevelPopup:IsShown()') is False
    assert lua.eval('#WoWStatusDB.popups.activity') == 0
    assert lua.eval('#character().events') == 0



def test_combat_queue_keeps_general_updates_separate_from_coalesced_levels(lua):
    from wow_status.group_routing import group_key
    lua.eval('WoWStatusGroups.update')('navsquad', '')
    lua.execute('__combat=true')
    channel = 'WStatus' + group_key('navsquad')
    receive = lua.eval('WoWStatusPopups.receive')
    assert receive('WSTATUS3 classic-era death 1793000000 death1 44696564', 'Eldrin-TestRealm', channel)
    assert receive('WSTATUS2 classic-era LEVEL 2 1793000000 level1', 'Eldrin-TestRealm', channel)
    assert lua.eval('#WoWStatusDB.popups.activity') == 2
    lua.execute('__combat=false; WoWStatusPopups.tick()')
    assert lua.eval('WoWStatusLevelPopup.heading:GetText()') == 'A FRIEND HAS FALLEN'



def test_group_membership_ignores_stale_send_receive_flags_and_old_off_commands():
    sender = make_lua()
    receiver = make_lua(STUBS.replace('return "Thora" end', 'return "Eldrin" end'))
    for client in [sender, receiver]:
        client.eval('WoWStatusGroups.update')('navsquad', '')
        client.execute('''
            WoWStatusDB.popups.receive=false
            WoWStatusDB.popups.broadcast=false
            SlashCmdList.WOWSTATUS("popup off")
            SlashCmdList.WOWSTATUS("popup send off")
        ''')
    sender.eval('fire')('PLAYER_LEVEL_UP', 2)
    packet = sender.eval('__sent[1].text')
    receiver.eval('fire')('CHAT_MSG_ADDON', 'WoWStatus', packet, 'WHISPER', 'Thora-TestRealm')
    assert receiver.eval('WoWStatusLevelPopup.message:GetText()') == 'Thora reached level 2!'
    assert receiver.eval('#WoWStatusDB.popups.activity') == 1
    receiver.eval('SlashCmdList.WOWSTATUS')('activity')
    assert 'automatic' in receiver.eval('WoWStatusActivity.status:GetText()')
    receiver.eval('WoWStatusGroups.update')('', '')
    receiver.eval('fire')('CHAT_MSG_ADDON', 'WoWStatus', packet, 'WHISPER', 'Thora-TestRealm')
    assert receiver.eval('#WoWStatusDB.popups.activity') == 0


def test_settings_refresh_has_no_account_popup_checkboxes(lua):
    lua.execute('''
        WoWStatusDB.popups.receive=false
        WoWStatusDB.popups.broadcast=false
        SlashCmdList.WOWSTATUS("")
        for _, entry in ipairs(WoWStatusSetup.checks) do
            assert(entry.key ~= "receive" and entry.key ~= "broadcast")
            local target = entry.group and character().settings[entry.group] or character().settings
            assert(entry.widget:GetChecked() == target[entry.key])
        end
    ''')


def test_reload_and_unchanged_zone_do_not_generate_notifications(lua):
    lua.eval('WoWStatusGroups.update')('navsquad', '')
    lua.eval('fire')('PLAYER_ENTERING_WORLD')
    lua.eval('fire')('ZONE_CHANGED_NEW_AREA')
    lua.eval('fire')('PLAYER_LOGOUT')
    assert lua.eval('#character().events') == 0
    assert lua.eval('#__sent') == 0


def test_cumulative_deaths_xp_quests_and_profession_ranks(lua):
    lua.execute('''
        function UnitXP() return 375 end
        function UnitXPMax() return 1000 end
        __skill=75
        function GetNumSkillLines() return 2 end
        function GetSkillLineInfo(index)
            if index==1 then return "Professions",true,true,0,0,0,0 end
            return "Alchemy",nil,nil,__skill,0,0,150
        end
        fire("SKILL_LINES_CHANGED")
        fire("PLAYER_XP_UPDATE","player")
        assert(character().snapshot.xp_percent==37.5)
        assert(character().snapshot.professions[1].skill==75)
        assert(character().snapshot.professions[1].max_skill==150)
        assert(character().snapshot.professions[1].source=="game_api")
        fire("PLAYER_DEAD")
        fire("PLAYER_DEAD")
        assert(character().snapshot.deaths==1)
        fire("PLAYER_ALIVE")
        fire("PLAYER_DEAD")
        assert(character().snapshot.deaths==2)
        fire("QUEST_TURNED_IN",100)
        fire("QUEST_TURNED_IN",100)
        fire("QUEST_TURNED_IN",101)
        assert(character().snapshot.quests_completed==2)
        assert(character().snapshot.quests_source=="tracked_since")
        local before = #character().events
        __skill=76
        fire("SKILL_LINES_CHANGED")
        assert(character().snapshot.professions[1].skill==76)
        assert(#character().events==before)
    ''')


def test_game_reported_completed_quests_replaces_tracked_subset(lua):
    lua.execute('''
        function GetQuestsCompleted() return {[10]=true,[20]=true,[30]=true} end
        fire("QUEST_QUERY_COMPLETE")
        assert(character().snapshot.quests_completed==3)
        assert(character().snapshot.quests_source=="game_api")
    ''')


def test_every_notification_preview_is_local_and_has_icon(lua):
    lua.eval('SlashCmdList.WOWSTATUS')('previews')
    assert lua.eval('WoWStatusNotificationPreviews:IsShown()') is True
    for index, kind in enumerate(['level','introduction','loot','death','zone','quest','profession','lfg']):
        lua.execute(f'function time() return {1793000000 + index * 7} end')
        lua.execute(f'WoWStatusNotificationPreviews.buttons.{kind}.OnClick()')
        assert lua.eval('WoWStatusLevelPopup:IsShown()') is True
        lua.eval('WoWStatusPopups.tick')()
        texture = lua.eval('WoWStatusLevelPopup.icon.texture')
        assert texture.startswith('Interface\\Icons\\') or texture.endswith('Textures\\LevelUp')
    lua.eval('WoWStatusPreviews.statusCard')()
    assert 'Total deaths: 15' in lua.eval('WoWStatusStatusPreview.body:GetText()')
    assert lua.eval('#__sent') == 0
    assert lua.eval('#character().events') == 0
    assert lua.eval('#WoWStatusDB.popups.activity') == 0


def test_race_and_sex_are_collected_together_and_unknown_sex_is_omitted(lua):
    lua.execute('function UnitSex() return 3 end')
    assert lua.eval('WoWStatusAdapter.snapshot({race=true}).sex') == 'Female'
    assert lua.eval('WoWStatusAdapter.snapshot({race=true}).race') == 'Dwarf'
    assert lua.eval('WoWStatusAdapter.snapshot({race=false}).sex') is None
    lua.execute('function UnitSex() return 2 end')
    assert lua.eval('WoWStatusAdapter.snapshot({race=true}).sex') == 'Male'
    lua.execute('function UnitSex() return 1 end')
    assert lua.eval('WoWStatusAdapter.snapshot({race=true}).sex') is None


@pytest.mark.parametrize("has_event_validator", [False, True])
def test_removed_legacy_quest_event_does_not_abort_addon_startup(has_event_validator):
    stubs = STUBS.replace(
        'function methods:RegisterEvent(name)',
        'function methods:RegisterEvent(name)\n'
        '    if name == "QUEST_QUERY_COMPLETE" then error("Unknown event") end',
    )
    if has_event_validator:
        stubs += '\nC_EventUtils = {IsEventValid=function(name) return name ~= "QUEST_QUERY_COMPLETE" end}'
    runtime = make_lua(stubs)
    assert runtime.eval('character().identity.name') == 'Thora'
    assert runtime.eval('type(SlashCmdList.WOWSTATUS)') == 'function'
    runtime.execute('''
        __optionPages = {}
        InterfaceOptions_AddCategory = function(page) table.insert(__optionPages, page.name) end
        fire("ADDON_LOADED", "Blizzard_Settings")
        assert(__optionPages[1] == "WoW Status")
        SlashCmdList.WOWSTATUS("")
    ''')


def test_previews_wait_their_turn_in_fifo_order(lua):
    lua.execute('''
        WoWStatusPopups.preview("level")
        WoWStatusPopups.preview("introduction")
        WoWStatusPopups.preview("quest")
        assert(WoWStatusLevelPopup.heading:GetText()=="LEVEL UP!")
        function time() return 1793000003 end
        WoWStatusPopups.tick()
        assert(WoWStatusLevelPopup.heading:GetText()=="LEVEL UP!")
        function time() return 1793000007 end
        WoWStatusPopups.tick()
        assert(WoWStatusLevelPopup.heading:GetText()=="WELCOME, ADVENTURER!")
        assert(WoWStatusLevelPopup.icon.texture:find("Achievement_Character_Human_Male",1,true))
        function time() return 1793000014 end
        WoWStatusPopups.tick()
        assert(WoWStatusLevelPopup.heading:GetText()=="QUEST ACHIEVEMENT!")
        assert(WoWStatusLevelPopup.message:GetText():find("100 quests",1,true))
        assert(#character().events==0)
    ''')


def test_equipment_silent_quest_hundreds_and_profession_promotions(lua):
    lua.execute('''
        __slot="|Hitem:1|h[Test sword]|h"
        fire("PLAYER_EQUIPMENT_CHANGED",1)
        assert(#character().events==0)
        for id=1,99 do fire("QUEST_TURNED_IN",id) end
        assert(#character().events==0)
        fire("QUEST_TURNED_IN",100)
        assert(#character().events==1)
        assert(character().events[1].kind=="quest" and character().events[1].data.completed==100)
        fire("QUEST_TURNED_IN",100)
        fire("QUEST_LOG_UPDATE")
        assert(#character().events==1)
        for id=101,200 do fire("QUEST_TURNED_IN",id) end
        assert(#character().events==2 and character().events[2].data.completed==200)
        __maximum=150; __rank=100
        function GetNumSkillLines() return 1 end
        function GetSkillLineInfo() return "Alchemy",nil,nil,__rank,0,0,__maximum end
        fire("SKILL_LINES_CHANGED")
        assert(#character().events==2)
        __rank=101
        fire("SKILL_LINES_CHANGED")
        assert(#character().events==2)
        __maximum=225
        -- A snapshot can see the new cap before the skill event. Do not lose it.
        WoWStatusProgress.professions(true)
        fire("PLAYER_XP_UPDATE","player")
        fire("SKILL_LINES_CHANGED")
        assert(#character().events==3)
        assert(character().events[3].data.title=="Expert")
        fire("SKILL_LINES_CHANGED")
        assert(#character().events==3)
        WoWStatusProgress.questMilestone(character(),1000,"game_api")
        assert(WoWStatusProgress.questMilestone(character(),1000,"game_api")==nil)
    ''')


def test_rapid_friend_levelups_each_get_their_own_queued_notification(lua):
    lua.execute('''
        SlashCmdList.WOWSTATUS("popup channel WStatusFriends")
        SlashCmdList.WOWSTATUS("popup on")
        SlashCmdList.WOWSTATUS("popup trust Eldrin-TestRealm")
        for level=2,4 do
            assert(WoWStatusPopups.receive("WSTATUS2 classic-era LEVEL "..level.." 1793000000 n"..level,
                "Eldrin-TestRealm","WStatusFriends"))
        end
        assert(WoWStatusLevelPopup.message:GetText():find("level 2!",1,true))
        function time() return 1793000007 end
        WoWStatusPopups.tick()
        assert(WoWStatusLevelPopup.message:GetText():find("level 3!",1,true))
        function time() return 1793000014 end
        WoWStatusPopups.tick()
        assert(WoWStatusLevelPopup.message:GetText():find("level 4!",1,true))
    ''')
