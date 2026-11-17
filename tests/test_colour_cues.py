"""Never colour alone (#185): every state that was told apart only by colour
now carries a shape or text cue too, and secondary grey text stays readable."""
import re
import struct
from pathlib import Path

import lupa
import pytest
from test_addon import make_lua
from test_gamepad import FRAMES, main_window
from test_main_window import WINDOW
from test_themes import THEMES, contrast

ROOT = Path(__file__).resolve().parents[1]
EDITIONS = ('vanilla', 'forever', 'tbc', 'retail')
OFFLINE = 'Interface\\AddOns\\WoWStatus\\Textures\\Offline'
ONLINE = 'Interface\\FriendsFrame\\StatusIcon-Online'


def cues(lua):
    table = lua.eval('WoWStatusUI.CUES')
    return {row['state']: row['cue'] for row in table.values()}


def test_every_colour_led_state_is_listed_with_a_cue_that_is_not_a_colour():
    lua = make_lua(THEMES)
    listed = cues(lua)
    assert set(listed) == {'online', 'offline', 'controller focus', 'calendar today',
                           'calendar day with entries'}
    colours = re.compile(r'\b(green|grey|gray|gold|red|blue|white|yellow)\b', re.IGNORECASE)
    for state, cue in listed.items():
        # Each cue names a shape or text; a colour word may only describe it alongside one.
        assert cue and colours.sub('', cue).strip(), state
    # Online and offline differ by shape, not by tint alone.
    assert listed['online'] != listed['offline']


def read_tga(path):
    data = path.read_bytes()
    _, _, kind, _, _, _, _, _, width, height, depth, _ = struct.unpack('<BBBHHBHHHHBB', data[:18])
    assert kind == 2 and depth == 32
    pixels = data[18:]
    return width, height, lambda x, y: pixels[(y * width + x) * 4 + 3]


@pytest.mark.parametrize('edition', EDITIONS)
def test_the_offline_marker_is_a_hollow_ring_in_every_edition(edition):
    path = ROOT / 'addon' / edition / 'WoWStatus' / 'Textures' / 'Offline.tga'
    assert path.read_bytes() == (ROOT / 'addon/shared/Textures/Offline.tga').read_bytes()
    width, height, alpha = read_tga(path)
    assert (width, height) == (32, 32)  # a power of two, as every client needs
    assert alpha(16, 16) == 0           # hollow in the middle
    assert alpha(16, 4) > 200 and alpha(4, 16) > 200  # a solid ring around it
    assert alpha(0, 0) == 0             # nothing in the corners


def test_presence_markers_are_a_filled_dot_and_a_hollow_ring():
    lua = make_lua(THEMES)
    assert lua.eval('WoWStatusUI.presence(true)') == f'|T{ONLINE}:12:12|t'
    assert lua.eval('WoWStatusUI.presence(false, 14)') == f'|T{OFFLINE}:14:14|t'


def test_the_leaderboard_marks_offline_friends_too_not_only_online_ones_in_green():
    lua = make_lua(WINDOW)
    lua.execute('''
        WoWStatusGroups.update("Example Crew", "")
        WoWStatusRoster.leaderboard=function() return {
            {name="Online-Realm",level=20,online=true},{name="Offline-Realm",level=10}} end
        SlashCmdList.WOWSTATUS("leaderboard")
    ''')
    first = lua.eval('WoWStatusLeaderboardPage.board[1].name.text')
    second = lua.eval('WoWStatusLeaderboardPage.board[2].name.text')
    assert first.startswith(f'|T{ONLINE}:') and 'Online' in first
    assert second.startswith(f'|T{OFFLINE}:') and 'Offline' in second
    assert '|cff40ff40' not in first + second


def test_character_cards_use_the_ring_for_offline_characters():
    source = (ROOT / 'addon/shared/Roster.lua').read_text(encoding='utf-8')
    assert 'c.dot:SetTexture(online and UI.ONLINE_ICON or UI.OFFLINE_ICON)' in source
    assert 'StatusIcon-Offline' not in source


def test_the_controller_highlight_has_a_dark_outline_inside_the_gold():
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute('unpack = unpack or table.unpack')
    lua.execute(FRAMES)
    # Record what the highlight draws; it is built when Gamepad.lua loads.
    lua.execute('''
        local methods = getmetatable(CreateFrame("Frame")).__index
        methods.SetColorTexture = function(self, r, g, b, a) self.colour = {r, g, b, a} end
        methods.SetPoint = function(self, point, x, y)
            self.points = self.points or {}; table.insert(self.points, {point, x or 0, y or 0})
        end
    ''')
    lua.execute((ROOT / 'addon/shared/Gamepad.lua').read_text(encoding='utf-8'))
    main_window(lua)
    lua.execute('WoWStatusGamepad.update(); press("PADDRIGHT")')
    assert lua.eval('WoWStatusGamepadFocus.visible') is True
    assert lua.eval('#WoWStatusGamepadFocus.outline') == 4
    assert lua.eval('#WoWStatusGamepadFocus.inner') == 4
    for i in range(1, 5):
        gold = lua.eval(f'WoWStatusGamepadFocus.outline[{i}].colour')
        dark = lua.eval(f'WoWStatusGamepadFocus.inner[{i}].colour')
        assert (gold[1], gold[2], gold[3]) == (1, .82, 0)
        assert (dark[1], dark[2], dark[3]) == (0, 0, 0) and dark[4] >= .8
        # Gold against black: a brightness step a colour-blind eye sees as well.
        assert contrast((1, .82, 0), (0, 0, 0)) >= 7
        # The dark line sits 2 units inside the 2-unit gold one.
        for point, x, y in (p.values() for p in lua.eval(f'WoWStatusGamepadFocus.inner[{i}].points').values()):
            assert x == (2 if 'LEFT' in point else -2)
            assert y == (-2 if 'TOP' in point else 2)


def test_the_calendar_marks_today_and_busy_days_by_shape_as_well_as_colour():
    lua = make_lua(THEMES)
    lua.execute('''
        local owner = CreateFrame("Button")
        WoWStatusUI.calendar(owner, nil, "2026-11-17", {["2026-11-17"]=1, ["2026-11-05"]=2}, function() end)
        __cells = {}
        for _, cell in ipairs(WoWStatusCalendar.cells) do if cell.key then __cells[cell.key] = cell.text.text end end
    ''')
    cells = lua.eval('__cells')
    assert '[17]' in cells['2026-11-17'] and '•' in cells['2026-11-17']
    assert '5•' in cells['2026-11-05'] and '[' not in cells['2026-11-05']
    plain = cells['2026-11-06']
    assert plain == '|cff9d9d9d6|r'


def test_muted_grey_reads_at_least_aa_on_every_theme():
    lua = make_lua(THEMES + 'WoWStatusDB = {version=1, characters={}, theme={name="achievement"}}\n')
    grey = lua.eval('WoWStatusUI.MUTED')
    assert lua.eval('WoWStatusUI.MUTED_CODE') == '|cff%02x%02x%02x' % ((round(grey * 255),) * 3)
    for faction in ('Alliance', 'Horde'):
        for name in ('achievement', 'night', 'journal', 'faction', 'contrast'):
            lua.execute(f'__faction = "{faction}"; WoWStatusDB.theme.name = "{name}"')
            window = lua.eval('{WoWStatusTheme.colour()}')
            assert contrast((grey, grey, grey), (window[1], window[2], window[3])) >= 5, (name, faction)


def test_disabled_fonts_made_through_the_ui_take_the_muted_grey():
    lua = make_lua(THEMES)
    lua.execute('''
        local methods = getmetatable(CreateFrame("Frame")).__index
        methods.SetTextColor = function(self, r, g, b) self.textColour = {r, g, b} end
        local parent = CreateFrame("Frame")
        __dim = WoWStatusUI.text(parent, "GameFontDisableSmall")
        __plain = WoWStatusUI.text(parent, "GameFontHighlight")
    ''')
    assert lua.eval('__dim.textColour[1]') == lua.eval('WoWStatusUI.MUTED')
    assert lua.eval('__plain.textColour') is None


def test_no_dim_greys_remain_in_the_addon_source():
    for path in sorted((ROOT / 'addon/shared').glob('*.lua')):
        if path.name.startswith('Flavour'):
            continue
        code = path.read_text(encoding='utf-8')
        assert '|cff808080' not in code, path.name
        assert not re.search(r'SetTextColor\(\s*\.5\s*,\s*\.5\s*,\s*\.5', code), path.name
        assert not re.search(r'AddLine\([^)]*,\s*\.6\s*,\s*\.6\s*,\s*\.6', code), path.name
