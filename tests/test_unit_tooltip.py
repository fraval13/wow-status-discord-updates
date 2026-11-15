"""A WoW Status block in a group member's unit tooltip (#183).

The hooks and tooltip are stubs: whether each client fires them as modelled, and
how the block looks, needs a live client.
"""
from pathlib import Path

import pytest
from test_gamepad import lua as gamepad_lua  # noqa: F401
from test_gamepad import main_window
from test_roster import pair, person, pump

ROOT = Path(__file__).parents[1]

TOOLTIP = r'''
__tip = {}
__units = {mouseover={name="Mira", realm=nil, level=1, player=true}}
GameTooltip = {
    GetUnit=function(self) return "Mira", __tipUnit end,
    AddLine=function(self, text) table.insert(__tip, {text}) end,
    AddDoubleLine=function(self, left, right) table.insert(__tip, {left, right}) end,
    Show=function(self) self.shown = true end,
}
__tipUnit = "mouseover"
function UnitIsPlayer(unit) return __units[unit] and __units[unit].player end
function UnitExists(unit) return __units[unit] ~= nil end
function UnitName(unit)
    if __units[unit] then return __units[unit].name, __units[unit].realm end
    return "Thora"
end
function UnitLevel(unit) return __units[unit] and __units[unit].level or __level end
function hover() __tip = {}; WoWStatusUnitTooltip.add(GameTooltip); return __tip end
'''


def friends():
    """Mira (Frank's account) has listed her character to Thora, both in one group."""
    mira, thora = pair()
    pump(mira, thora)
    thora.execute(TOOLTIP)
    return mira, thora


def shown(thora):
    tip = thora.eval('hover()')
    return [tuple(tip[i].values()) for i in range(1, len(tip) + 1)]


def test_a_group_member_gets_a_short_block_from_stored_values():
    _, thora = friends()
    thora.execute('''
        local c = WoWStatusRoster.tooltipFacts("Mira-TestRealm")
        for _, player in pairs(WoWStatusDB.roster.players) do
            for _, ch in pairs(player.characters) do ch.xp, ch.quests, ch.played = 375, 236, 90000 end
        end
    ''')
    before = thora.eval('#__sent')
    assert shown(thora) == [('WoW Status',), ('Level progress', '37%'), ('Quests (tracked)', '236')]
    assert thora.eval('#__sent') == before  # nothing requested or sent
    assert thora.eval('GameTooltip.shown') is True
    # Larger: up to three values, so at most four lines.
    thora.execute('WoWStatusDB.unit_tooltip.size = 3')
    assert shown(thora)[-1] == ('Played', '1d 1h')
    assert len(shown(thora)) == 4


def test_unshared_values_are_absent_and_none_shared_means_no_block():
    _, thora = friends()
    thora.execute('''
        for _, player in pairs(WoWStatusDB.roster.players) do
            for _, ch in pairs(player.characters) do ch.xp, ch.quests, ch.quests_source, ch.played = nil, nil, "private", nil end
        end
    ''')
    assert shown(thora) == []
    thora.execute('''
        for _, player in pairs(WoWStatusDB.roster.players) do
            for _, ch in pairs(player.characters) do ch.played = 3600 end
        end
    ''')
    assert shown(thora) == [('WoW Status',), ('Played', '1h 0m')]


def test_deaths_come_from_the_newest_death_announcement():
    _, thora = friends()
    thora.execute('''
        local entries = WoWStatusJournal.entries()
        table.insert(entries, 1, {kind="death", sender="Mira-TestRealm", text="Total deaths: 7", at=2})
        table.insert(entries, 2, {kind="death", sender="Mira-TestRealm", text="Total deaths: 6", at=1})
    ''')
    assert ('Total deaths', '7') in shown(thora)


def test_saved_xp_is_dropped_once_the_live_level_moved_on():
    _, thora = friends()
    thora.execute('''
        for _, player in pairs(WoWStatusDB.roster.players) do
            for _, ch in pairs(player.characters) do ch.xp = 500 end
        end
    ''')
    assert ('Level progress', '50%') in shown(thora)
    thora.execute('__units.mouseover.level = 2')
    assert all(row[0] != 'Level progress' for row in shown(thora))


def test_non_members_hidden_characters_and_yourself_get_no_lines():
    mira, thora = friends()
    # A stranger with the same name on another realm, and a non-player unit.
    thora.execute('__units.mouseover.realm = "OtherRealm"')
    assert shown(thora) == []
    thora.execute('__units.mouseover = {name="Mira", level=1, player=false}')
    assert shown(thora) == []
    thora.execute('__units.mouseover = {name="Thora", level=1, player=true}')
    assert shown(thora) == []
    # Mira hides her character from friends: the block goes too.
    thora.execute('__units.mouseover = {name="Mira", level=1, player=true}')
    assert shown(thora) != []
    mira.execute('WoWStatusRoster.setHidden(character(), true)')
    pump(mira, thora, start=300)
    assert thora.eval('WoWStatusRoster.isHidden("Mira-TestRealm")') is True
    assert shown(thora) == []


def test_unit_names_match_list_keys_on_forever_and_hyphenated_realms():
    _, thora = friends()
    thora.execute('__units.mouseover = {name="Mira", realm="Azjol-Nerub", level=1, player=true}')
    assert thora.eval('WoWStatusRoster.unitName("mouseover")') == 'Mira-AzjolNerub'
    # WoW Forever: UnitName gives the first name only; the GUID lookup the full one.
    thora.execute('''
        WoWStatusAdapter.full_names = true
        __units.mouseover = {name="Edith", level=1, player=true}
        function UnitGUID(unit) return unit == "mouseover" and "Player-1-EDITH" or "Player-123-Thora" end
        function GetPlayerInfoByGUID(guid)
            if guid == "Player-1-EDITH" then return "Warrior", "WARRIOR", "Dwarf", "Dwarf", 3, "Edith Aateigen", "" end
        end
    ''')
    assert thora.eval('WoWStatusRoster.unitName("mouseover")') == 'Edith Aateigen-TestRealm'
    # Never someone else's name.
    thora.execute('''function GetPlayerInfoByGUID() return "Warrior", "WARRIOR", "Dwarf", "Dwarf", 3, "Bob Builder", "" end''')
    assert thora.eval('WoWStatusRoster.unitName("mouseover")') == 'Edith-TestRealm'


def test_the_newest_list_wins_when_two_player_ids_hold_a_character():
    _, thora = friends()
    thora.execute('''
        local players = WoWStatusDB.roster.players
        local id, player = next(players)
        local copy = {name="Old", at=(player.at or 0) - 100, groups=player.groups, characters={}}
        for k, ch in pairs(player.characters) do copy.characters[k] = {name=ch.name, level=1, played=60} end
        players["0123456789abcdef"] = copy
        for _, ch in pairs(player.characters) do ch.played = 7200 end
    ''')
    assert ('Played', '2h 0m') in shown(thora)


def test_leaving_the_group_removes_the_block():
    _, thora = friends()
    assert shown(thora) != []
    thora.execute('for id in pairs(character().group_ids) do character().group_ids[id] = nil end')
    assert shown(thora) == []


def test_the_player_name_shows_when_you_also_know_their_alts():
    mira, thora = friends()
    assert shown(thora)[0] == ('WoW Status',)
    thora.execute('''
        for _, player in pairs(WoWStatusDB.roster.players) do
            player.characters["mirasalt-testrealm"] = {name="Mirasalt-TestRealm", level=5, race="Dwarf", sex=3, class="WARRIOR"}
        end
    ''')
    assert shown(thora)[0] == ('WoW Status · Frank',)


def test_off_switch_size_setting_and_malformed_saved_values():
    _, thora = friends()
    thora.execute('WoWStatusUnitTooltip.setEnabled(false)')
    assert shown(thora) == []
    thora.execute('WoWStatusUnitTooltip.setEnabled(true)')
    assert shown(thora) != []
    for saved, size in (('"big"', 2), ('0', 1), ('9', 3), ('2.6', 3), ('0/0', 2)):
        thora.execute(f'WoWStatusDB.unit_tooltip = {{size={saved}, enabled="yes"}}')
        assert thora.eval('WoWStatusUnitTooltip.settings().size') == size
        assert thora.eval('WoWStatusUnitTooltip.settings().enabled') is True
    thora.execute('WoWStatusDB.unit_tooltip = "broken"')
    assert thora.eval('WoWStatusUnitTooltip.settings().size') == 2
    assert [thora.eval('WoWStatusUnitTooltip.nextSize()') for _ in range(3)] == [3, 1, 2]


def test_options_switch_and_size_button_work_and_translate():
    _, thora = friends()
    thora.eval('SlashCmdList.WOWSTATUS')('')
    box = thora.eval('WoWStatusSetup.unitTooltip')
    assert box.check.checked is True and box.size.text == 'Values shown: 2'
    box.size.OnClick(box.size)
    assert box.size.text == 'Values shown: 3'
    box.check.checked = False
    box.check.OnClick(box.check)
    assert thora.eval('WoWStatusUnitTooltip.settings().enabled') is False
    assert shown(thora) == []
    thora.execute('WoWStatusLocale.set("nn")')
    box.refresh(box)
    assert box.size.text == 'Verdiar som blir viste: 3'
    assert thora.eval('WoWStatusLocale.T("Level progress")') == 'Nivåframgang'


HOOKS = r'''
__hooks = {}
WoWStatusUnitTooltip.hooked = nil
function makeTooltip(script)
    GameTooltip = {
        HasScript=function(self, name) return script and name == "OnTooltipSetUnit" end,
        HookScript=function(self, name, fn)
            if not (script and name == "OnTooltipSetUnit") then error("no such script") end
            __hooks.script = fn
        end,
        GetUnit=function() error("broken tooltip") end,
        AddLine=function() __added = true end,
    }
end
'''


@pytest.mark.parametrize('kind', ['data', 'script', 'processor-without-tooltip-data', 'neither',
                                  'modern-without-script'])
def test_each_client_gets_one_guarded_hook_and_never_errors(kind):
    lua = person('Thora', 'Ada')
    lua.execute(HOOKS)
    if kind == 'data':
        lua.execute('''
            makeTooltip(true)
            Enum = {TooltipDataType={Unit=2}}
            C_TooltipInfo = {}
            TooltipDataProcessor = {AddTooltipPostCall=function(kind, fn) assert(kind == 2); __hooks.data = fn end}
        ''')
    elif kind == 'script':
        lua.execute('makeTooltip(true); TooltipDataProcessor = nil')
    elif kind == 'processor-without-tooltip-data':
        # The shared table exists, but unit tooltips are still built the old way.
        lua.execute('''
            makeTooltip(true); C_TooltipInfo = nil; Enum = {TooltipDataType={Unit=2}}
            TooltipDataProcessor = {AddTooltipPostCall=function() error("must not be used") end}
        ''')
    elif kind == 'modern-without-script':
        lua.execute('makeTooltip(false); TooltipDataProcessor = nil')
    else:
        lua.execute('GameTooltip = nil; TooltipDataProcessor = nil')
    expected = {'data': 'data', 'script': 'script', 'processor-without-tooltip-data': 'script'}.get(kind, False)
    assert lua.eval('WoWStatusUnitTooltip.hook()') == expected
    assert lua.eval('WoWStatusUnitTooltip.hook()') == expected  # installed once
    if kind == 'data':
        assert lua.eval('__hooks.script') is None  # never both
        lua.eval('__hooks.data')(lua.eval('GameTooltip'), {})
        lua.execute('__hooks.data({AddLine=GameTooltip.AddLine}, {})')  # other tooltips are ignored
        assert lua.eval('__added') is None
    elif kind in ('script', 'processor-without-tooltip-data'):
        lua.eval('__hooks.script')(lua.eval('GameTooltip'))


def test_the_settings_controls_are_reachable_with_a_controller(gamepad_lua):  # noqa: F811
    lua = gamepad_lua
    main_window(lua)
    lua.execute('''
        local methods=getmetatable(CreateFrame("Frame")).__index
        function methods:SetSize(w,h) self.rect[3],self.rect[4]=w,h end
        function methods:SetText(text) self.text=text end
        function methods:CreateFontString() return CreateFrame("FontString",nil,self) end
        function methods:SetChecked(value) self.checked=value end
        function methods:GetChecked() return self.checked end
        function methods:SetWidth() end
        function methods:SetJustifyH() end
        local click=methods.Click
        function methods:Click(button,down)
            if self.kind=="CheckButton" then self.checked=not self.checked end
            click(self,button,down)
        end
        WoWStatusLocale={T=function(text) return text end,F=function(text, ...) return string.format(text, ...) end}
        WoWStatusSafe={number=function(v) return type(v)=="number" and v==v and v or nil end}
        WoWStatusDB={}
    ''')
    lua.execute((ROOT / 'addon/shared/UnitTooltip.lua').read_text(encoding='utf-8'))
    lua.execute('''
        local box=WoWStatusUnitTooltip.buildSettings(main,-40)
        local reached={}
        for _,control in ipairs(WoWStatusGamepad.controls(main,{main})) do reached[control]=true end
        assert(reached[box.check] and reached[box.size])
        box.check.rect={120,400,32,32}
        WoWStatusGamepad.update()
        press("PADDDOWN")
        WoWStatusGamepad.setFocus(box.check);press("PAD1")
        assert(WoWStatusDB.unit_tooltip.enabled==false)
        -- Off: the size button does nothing, so it is disabled and skipped.
        assert(box.size:IsEnabled()==false)
        reached={}
        for _,control in ipairs(WoWStatusGamepad.controls(main,{main})) do reached[control]=true end
        assert(not reached[box.size])
    ''')
