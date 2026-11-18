"""Two characters side by side (#160): read from the roster, never from the wire."""
from test_roster import pair, pump


def rows_of(lua, one, two):
    """The data rows as {label: Lua table of left, right, gap, winner (1-indexed)}."""
    return lua.eval(f'''(function()
        local out = {{}}
        for _, row in ipairs(WoWStatusCompare.data({one!r}, {two!r}).rows) do
            out[row.label] = {{row.left or "-", row.right or "-", row.gap or "", row.winner or 0}}
        end
        return out
    end)()''')


def crafted(lua, extra=''):
    """Two characters with numbers of our choosing, set through the one seam the
    module reads: WoWStatusRoster.groups()."""
    lua.execute('''
        __rows = {
            {name="Mira-TestRealm", class="WARRIOR", status="online",
             level=40, xp=500, deaths=9, quests=300, played=36000, dungeons=3, kills=1200},
            {name="Thora-TestRealm", class="PALADIN", status="last seen 2h ago",
             level=30, xp=200, deaths=2, quests=100, played=72000},
        }
        ''' + extra + '''
        WoWStatusRoster.groups = function() return {{title="Group", rows=__rows}} end
    ''')


def test_the_numbers_sit_side_by_side_with_the_gap_and_the_better_side():
    _, thora = pair()
    crafted(thora)
    rows = rows_of(thora, 'Mira-TestRealm', 'Thora-TestRealm')
    # Higher is better for a level, and the gap is the difference.
    assert rows['Level'][1] == '40' and rows['Level'][2] == '30'
    assert rows['Level'][3] == '10' and rows['Level'][4] == 1
    # Fewer deaths is better, so the other side wins that row.
    assert rows['Deaths'][3] == '7' and rows['Deaths'][4] == 2
    # More playing is not better than less: nobody wins, and no gap is claimed.
    assert rows['Played'][4] == 0 and rows['Played'][3] == ''
    # The interesting row: Thora played twice as long for ten levels fewer.
    assert rows['Played per level'][4] == 1, 'the faster leveller should win'
    assert rows['XP into the level'][1] == '50%'


def test_a_shared_zero_is_a_number_and_an_unshared_value_says_so():
    _, thora = pair()
    crafted(thora, extra='__rows[1].dungeons = 0; __rows[2].dungeons = nil')
    rows = rows_of(thora, 'Mira-TestRealm', 'Thora-TestRealm')
    # A zero somebody shared is information, not a blank.
    assert rows['Dungeons cleared'][1] == '0'
    assert rows['Dungeons cleared'][2] == '-'      # never shared
    assert rows['Dungeons cleared'][4] == 0        # no winner against an unknown
    # A measure neither side shared is left out instead of an empty line.
    assert 'Gold' not in rows
    # Only one side has it, so the row is shown without a winner.
    assert rows['Monsters killed'][1] == '1200' and rows['Monsters killed'][2] == '-'
    assert rows['Monsters killed'][4] == 0


def test_the_page_says_so_when_there_is_nothing_to_compare():
    _, thora = pair()
    thora.execute('''
        WoWStatusRoster.groups = function() return {{title="Group", rows={
            {name="Mira-TestRealm", status="online"}, {name="Thora-TestRealm", status="online"},
        }}} end
    ''')
    thora.eval('WoWStatusCompare.show')('Mira-TestRealm')
    assert thora.eval('WoWStatusComparePage.empty:IsShown()') is True
    assert thora.eval('WoWStatusComparePage.empty:GetText()') == 'Neither of them has shared any numbers yet.'


def names_offered(lua):
    return lua.eval('''(function()
        local out = {}
        for _, item in ipairs(WoWStatusCompare.candidates()) do out[#out+1] = item.name end
        return table.concat(out, ",")
    end)()''')


def test_only_characters_the_viewer_may_see_can_be_picked():
    mira, thora = pair()
    pump(mira, thora)
    offered = names_offered(thora)
    assert 'Thora-TestRealm' in offered and 'Mira-TestRealm' in offered
    # A character its owner hid is not offered: R.groups() leaves it out already.
    thora.execute('WoWStatusRoster.hiddenNames = function() return {["mira-testrealm"] = true} end')
    assert 'Mira-TestRealm' not in names_offered(thora)


def test_the_page_opens_with_you_on_the_left_and_the_clicked_friend_on_the_right():
    mira, thora = pair()
    pump(mira, thora)
    thora.eval('WoWStatusCompare.show')('Mira-TestRealm')
    assert thora.eval('WoWStatusMainWindow.active()') == 'compare'
    assert 'Thora' in thora.eval('WoWStatusComparePage.leftPick:GetText()')
    assert 'Mira' in thora.eval('WoWStatusComparePage.rightPick:GetText()')
    # Both columns say how fresh they are, as the profile does.
    assert thora.eval('WoWStatusComparePage.leftWhen:GetText()') != ''
    assert thora.eval('WoWStatusComparePage.rightWhen:GetText()') != ''


def test_swapping_sides_swaps_the_columns():
    mira, thora = pair()
    pump(mira, thora)
    thora.eval('WoWStatusCompare.show')('Mira-TestRealm')
    before = (thora.eval('WoWStatusComparePage.leftPick:GetText()'),
              thora.eval('WoWStatusComparePage.rightPick:GetText()'))
    thora.execute('WoWStatusComparePage.swap.OnClick()')
    after = (thora.eval('WoWStatusComparePage.leftPick:GetText()'),
             thora.eval('WoWStatusComparePage.rightPick:GetText()'))
    assert after == (before[1], before[0])


def test_the_slash_command_and_the_leaderboard_button_open_the_page():
    mira, thora = pair()
    pump(mira, thora)
    thora.eval('SlashCmdList.WOWSTATUS')('compare Mira-TestRealm')
    assert thora.eval('WoWStatusMainWindow.active()') == 'compare'
    assert 'Mira' in thora.eval('WoWStatusComparePage.rightPick:GetText()')
    thora.eval('SlashCmdList.WOWSTATUS')('leaderboard')
    thora.execute('WoWStatusLeaderboardPage.compare.OnClick()')
    assert thora.eval('WoWStatusMainWindow.active()') == 'compare'


def test_the_pickers_and_the_swap_button_are_controller_controls():
    mira, thora = pair()
    pump(mira, thora)
    thora.eval('WoWStatusCompare.show')('Mira-TestRealm')
    for name in ('leftPick', 'rightPick', 'swap'):
        assert thora.eval(f'WoWStatusComparePage.{name}.kind') == 'Button', name
        assert thora.eval(f'WoWStatusComparePage.{name}.OnClick') is not None, name
