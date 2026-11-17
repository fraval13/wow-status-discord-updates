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
function UnitGUID(unit)
    if __units[unit] then return __units[unit].guid or ("Player-1-" .. __units[unit].name) end
    return "Player-123-Thora"
end
function hover() __tip = {}; WoWStatusUnitTooltip.add(GameTooltip); return __tip end
'''


def friends():
    """Mira (Frank's account) has listed her character to Thora, both in one group.

    The block shows level progress, quests and played time unless a test picks others.
    """
    mira, thora = pair()
    pump(mira, thora)
    thora.execute(TOOLTIP)
    thora.execute('WoWStatusDB.unit_tooltip = {shown={"level", "quests", "played"}}')
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
    thora.execute('WoWStatusDB.unit_tooltip = {shown={"level", "quests", "played"}}')
    before = thora.eval('#__sent')
    assert shown(thora) == [('WoW Status',), ('Level progress', '37%'), ('Quests (tracked)', '236'), ('Played', '1d 1h')]
    assert thora.eval('#__sent') == before  # nothing requested or sent
    assert thora.eval('GameTooltip.shown') is True
    # In the order picked.
    thora.execute('WoWStatusUnitTooltip.moveUp("played")')
    assert shown(thora)[2] == ('Played', '1d 1h')


def test_the_default_shows_item_level_deaths_and_professions_from_stored_data():
    _, thora = friends()
    thora.execute('''
        for _, player in pairs(WoWStatusDB.roster.players) do
            for _, ch in pairs(player.characters) do
                ch.played, ch.equipment_profile = 3600, {average_item_level=61.7}
                ch.professions = {{key="tailoring", skill=225, max_skill=300}, {key="mining", skill=150, max_skill=150}}
            end
        end
        table.insert(WoWStatusJournal.entries(), 1, {kind="death", sender="Mira-TestRealm", text="Total deaths: 4", at=2})
        WoWStatusDB.unit_tooltip = nil
    ''')
    before = thora.eval('#__sent')
    rows = shown(thora)
    assert rows[1] == ('Average item level', '61')
    assert rows[2] == ('Total deaths', '4')
    assert rows[3][0] == 'Professions' and rows[3][1].startswith('Tailoring 225, ') and 'Mining 150' in rows[3][1]
    assert len(rows) == 4  # played is not picked by default
    assert thora.eval('#__sent') == before  # no equipment request from a mouseover


def test_other_shared_statistics_can_be_picked():
    _, thora = friends()
    thora.execute('''
        for _, player in pairs(WoWStatusDB.roster.players) do
            for _, ch in pairs(player.characters) do ch.kills, ch.mounts, ch.dungeons, ch.honor_kills = 812, 3, 0, nil end
        end
        WoWStatusDB.unit_tooltip = {shown={"kills", "mounts", "dungeons", "honor_kills"}}
    ''')
    # Zero dungeons and no honor kills add nothing, like on the character card.
    assert shown(thora) == [('WoW Status',), ('Monsters killed', '812'), ('Mounts', '3')]


def test_unshared_values_are_absent_and_none_shared_means_no_block():
    _, thora = friends()
    thora.execute('''
        for _, player in pairs(WoWStatusDB.roster.players) do
            for _, ch in pairs(player.characters) do ch.xp, ch.quests, ch.quests_source, ch.played = nil, nil, "private", nil end
        end
        WoWStatusDB.unit_tooltip = {shown={"level", "quests", "played"}}
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
        WoWStatusDB.unit_tooltip = {shown={"deaths"}}
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
        WoWStatusDB.unit_tooltip = {shown={"level"}}
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
    thora.execute('__units.mouseover = {name="Thora", level=1, player=true, guid="Player-123-Thora"}')
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


def test_a_hook_firing_twice_adds_the_block_once():
    _, thora = friends()
    thora.execute('''
        __base = 3
        function GameTooltip:NumLines() return __base + #__tip end
        function rebuild() __tip = {}; WoWStatusUnitTooltip.add(GameTooltip) end
    ''')
    thora.execute('rebuild(); WoWStatusUnitTooltip.add(GameTooltip)')
    assert thora.eval('#__tip') == 2  # header and one value, not twice
    thora.execute('rebuild()')  # cleared and built again: added again
    assert thora.eval('#__tip') == 2


def test_a_level_up_in_the_log_makes_saved_progress_stale():
    _, thora = friends()
    thora.execute('''
        for _, player in pairs(WoWStatusDB.roster.players) do
            for _, ch in pairs(player.characters) do ch.xp = 850 end
        end
        WoWStatusDB.unit_tooltip = {shown={"level"}}
        __units.mouseover.level = nil
    ''')
    assert ('Level progress', '85%') in shown(thora)
    thora.execute('''
        table.insert(WoWStatusJournal.entries(), 1, {id="x", kind="level", level=2, sender="Mira-TestRealm", at=3})
    ''')
    assert all(row[0] != 'Level progress' for row in shown(thora))


def test_the_player_name_shows_when_you_also_know_their_alts():
    mira, thora = friends()
    assert shown(thora)[0] == ('WoW Status',)
    thora.execute('''
        for _, player in pairs(WoWStatusDB.roster.players) do
            player.characters["mirasalt-testrealm"] = {name="Mirasalt-TestRealm", level=5, race="Dwarf", sex=3, class="WARRIOR"}
        end
    ''')
    assert shown(thora)[0] == ('WoW Status · Frank',)


def test_off_switch_list_editing_and_malformed_saved_values():
    _, thora = friends()
    thora.execute('WoWStatusUnitTooltip.setEnabled(false)')
    assert shown(thora) == []
    thora.execute('WoWStatusUnitTooltip.setEnabled(true)')
    assert shown(thora) != []

    def picked(known=False):
        listed = thora.eval('WoWStatusUnitTooltip.picked()' if known else 'WoWStatusUnitTooltip.settings().shown')
        return [listed[i] for i in range(1, len(listed) + 1)]
    thora.execute('WoWStatusDB.unit_tooltip = nil')
    assert picked() == ['item_level', 'deaths', 'professions']
    thora.execute('WoWStatusUnitTooltip.addValue("played"); WoWStatusUnitTooltip.addValue("played")')
    thora.execute('WoWStatusUnitTooltip.addValue("nonsense"); WoWStatusUnitTooltip.removeValue("deaths")')
    thora.execute('WoWStatusUnitTooltip.moveUp("played"); WoWStatusUnitTooltip.moveUp("item_level")')
    assert picked() == ['item_level', 'played', 'professions']
    # Removing everything leaves no block, and stays removed.
    thora.execute('for _, k in ipairs({"item_level", "played", "professions"}) do WoWStatusUnitTooltip.removeValue(k) end')
    assert picked() == [] and shown(thora) == []
    for saved, expected in (('{shown={"deaths", "deaths", 7, "nope", "gold"}}', ['deaths', 'gold']),
                            ('{shown="deaths", size=3}', ['item_level', 'deaths', 'professions']),
                            ('"broken"', ['item_level', 'deaths', 'professions'])):
        thora.execute(f'WoWStatusDB.unit_tooltip = {saved}')
        assert picked(known=True) == expected
        assert thora.eval('WoWStatusUnitTooltip.settings().enabled') is True
        assert thora.eval('WoWStatusUnitTooltip.settings().size') is None
    # A pick this version does not know survives, so a newer version keeps it.
    thora.execute('WoWStatusDB.unit_tooltip = {shown={"deaths", "nope"}}')
    assert picked() == ['deaths', 'nope'] and picked(known=True) == ['deaths']


def test_options_list_adds_removes_reorders_and_translates():
    _, thora = friends()
    thora.eval('SlashCmdList.WOWSTATUS')('')
    box = thora.eval('WoWStatusSetup.unitTooltip')
    rows = box.rows

    def listed():
        return [(rows[i].label.text, rows[i].toggle.text) for i in range(1, len(rows) + 1)]
    assert box.check.checked is True and box.hint.text == 'Values shown, top first:'
    assert listed()[:4] == [('Level progress', 'Remove'), ('Quests', 'Remove'), ('Played', 'Remove'),
                            ('Average item level', 'Add')]
    assert len(rows) == thora.eval('#WoWStatusUnitTooltip.VALUES')
    # Add item level: it goes to the bottom of the picked values.
    rows[4].toggle.OnClick(rows[4].toggle)
    assert listed()[3] == ('Average item level', 'Remove')
    rows[4].up.OnClick(rows[4].up)
    assert [row[0] for row in listed()[:4]] == ['Level progress', 'Quests', 'Average item level', 'Played']
    rows[1].toggle.OnClick(rows[1].toggle)
    assert [row[0] for row in listed()[:3]] == ['Quests', 'Average item level', 'Played']
    assert ('Level progress', 'Add') in listed()
    assert shown(thora)[1] == ('Quests (tracked)', '0')
    box.check.checked = False
    box.check.OnClick(box.check)
    assert thora.eval('WoWStatusUnitTooltip.settings().enabled') is False
    assert shown(thora) == []
    thora.execute('WoWStatusLocale.set("nn")')
    box.refresh(box)
    assert box.hint.text == 'Verdiar som blir viste, den øvste først:'
    assert rows[1].up.text == 'Flytt opp' and rows[1].toggle.text == 'Fjern'
    assert rows[1].label.text == 'Oppdrag'


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


@pytest.mark.parametrize('kind', ['data', 'script', 'script-and-processor', 'neither'])
def test_each_client_gets_one_guarded_hook_and_never_errors(kind):
    lua = person('Thora', 'Ada')
    lua.execute(HOOKS)
    processor = '''
        Enum = {TooltipDataType={Unit=2}}
        TooltipDataProcessor = {AddTooltipPostCall=function(kind, fn) assert(kind == 2); __hooks.data = fn end}
    '''
    if kind == 'data':  # Retail and modern Classic: the script is gone.
        lua.execute('makeTooltip(false)' + processor)
    elif kind == 'script':  # Older clients: only the script.
        lua.execute('makeTooltip(true); TooltipDataProcessor = nil')
    elif kind == 'script-and-processor':  # The shared table exists, but units still fire the script.
        lua.execute('makeTooltip(true)' + processor)
    else:
        lua.execute('GameTooltip = nil; TooltipDataProcessor = nil')
    expected = {'data': 'data', 'script': 'script', 'script-and-processor': 'script'}.get(kind, False)
    assert lua.eval('WoWStatusUnitTooltip.hook()') == expected
    assert lua.eval('WoWStatusUnitTooltip.hook()') == expected  # installed once
    if kind == 'data':
        assert lua.eval('__hooks.script') is None
        lua.eval('__hooks.data')(lua.eval('GameTooltip'), {})  # a broken GetUnit does not raise
        lua.execute('__hooks.data({AddLine=GameTooltip.AddLine}, {})')  # other tooltips are ignored
        assert lua.eval('__added') is None
    elif kind != 'neither':
        assert lua.eval('__hooks.data') is None  # never both
        lua.eval('__hooks.script')(lua.eval('GameTooltip'))


def test_without_a_unit_token_mouseover_counts_only_with_the_tooltips_guid():
    _, thora = friends()
    thora.execute('''
        __tipUnit = nil
        function UnitGUID(unit) return unit == "mouseover" and "Player-1-MIRA" or "Player-123-Thora" end
    ''')
    assert thora.eval('#hover()') == 0  # no tooltip data: nothing is guessed
    thora.execute('__tip = {}; WoWStatusUnitTooltip.add(GameTooltip, {guid="Player-1-OTHER"})')
    assert thora.eval('#__tip') == 0  # the tooltip shows someone else
    thora.execute('__tip = {}; WoWStatusUnitTooltip.add(GameTooltip, {guid="Player-1-MIRA"})')
    assert thora.eval('#__tip') > 0


def test_your_own_character_in_a_stale_list_gets_no_block():
    _, thora = friends()
    thora.execute('''
        local _, player = next(WoWStatusDB.roster.players)
        player.characters["thora-testrealm"] = {name="Thora-TestRealm", level=1, played=60}
        __units.mouseover = {name="Thora", level=1, player=true, guid="Player-123-Thora"}
    ''')
    assert thora.eval('WoWStatusRoster.tooltipFacts("Thora-TestRealm")') is None
    assert shown(thora) == []


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
        function methods:SetShown(value) if value then self:Show() else self:Hide() end end
        function methods:SetTextColor() end
        local click=methods.Click
        function methods:Click(button,down)
            if self.kind=="CheckButton" then self.checked=not self.checked end
            click(self,button,down)
        end
        WoWStatusLocale={T=function(text) return text end,F=function(text, ...) return string.format(text, ...) end}
        WoWStatusSafe={number=function(v) return type(v)=="number" and v==v and v or nil end}
        WoWStatusDB={}
        WoWStatusUI={mute=function(text) text.muted=true end}
    ''')
    lua.execute((ROOT / 'addon/shared/UnitTooltip.lua').read_text(encoding='utf-8'))
    lua.execute('''
        local box=WoWStatusUnitTooltip.buildSettings(main,-40)
        local function reachable()
            local reached={}
            for _,control in ipairs(WoWStatusGamepad.controls(main,{main})) do reached[control]=true end
            return reached
        end
        local first,last=box.rows[1],box.rows[#box.rows]
        local reached=reachable()
        assert(reached[box.check] and reached[first.toggle] and reached[last.toggle])
        -- The top value cannot move up, and values not picked have no Move up.
        assert(not reached[first.up],"first up") assert(reached[box.rows[2].up],"second up") assert(not reached[last.up],"last up")
        box.check.rect={120,400,32,32}
        WoWStatusGamepad.update()
        press("PADDDOWN")
        WoWStatusGamepad.setFocus(last.toggle);press("PAD1")
        assert(WoWStatusDB.unit_tooltip.shown[4]==WoWStatusUnitTooltip.VALUES[#WoWStatusUnitTooltip.VALUES].key)
        WoWStatusGamepad.setFocus(box.check);press("PAD1")
        assert(WoWStatusDB.unit_tooltip.enabled==false)
        -- Off: the list buttons do nothing, so they are disabled and skipped.
        assert(first.toggle:IsEnabled()==false)
        reached=reachable()
        assert(not reached[first.toggle] and not reached[box.rows[2].up])
    ''')
