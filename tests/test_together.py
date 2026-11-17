"""Together: the group's combined totals (#167). Local arithmetic, nothing sent."""
from test_roster import pair, pump


def crafted(lua, extra=''):
    """Three characters in one group, with numbers of our choosing. The one seam
    the module reads for per-character values is WoWStatusRoster.groups()."""
    lua.execute('''
        __group = next(character().group_ids)
        __rows = {
            {name="Mira-TestRealm", groupIds={[__group]=true}, level=40, played=36000, quests=300,
             deaths=9, kills=1200, dungeons=2, mounts=1, honor_kills=5},
            {name="Thora-TestRealm", groupIds={[__group]=true}, level=30, played=18000, quests=100,
             deaths=2, kills=400, dungeons=1},
            {name="Eldrin-TestRealm", groupIds={[__group]=true}, level=20},
        }
        ''' + extra + '''
        WoWStatusRoster.groups = function() return {{title="Group", rows=__rows}} end
    ''')
    return lua.eval('__group')


def totals(lua, group):
    return lua.eval(f'''(function()
        local out = {{}}
        for _, row in ipairs(WoWStatusTogether.totals({group!r}).rows) do
            out[row.caption] = {{row.total, row.shared, row.of}}
        end
        return out
    end)()''')


def test_the_group_adds_up_and_a_missing_member_is_said_out_loud():
    _, thora = pair()
    group = crafted(thora)
    rows = totals(thora, group)
    assert rows['Levels between us'][1] == '90'          # 40 + 30 + 20
    assert rows['Levels between us'][2] == 3 and rows['Levels between us'][3] == 3
    assert rows['Quests finished'][1] == '400'
    # Only two of the three shared played time, and the row knows it.
    assert rows['Hours played'][2] == 2 and rows['Hours played'][3] == 3
    # Gold is off by default, so the row is left out rather than shown as 0.
    assert 'Gold gathered' not in rows


def test_a_character_in_two_groups_is_counted_once():
    _, thora = pair()
    group = crafted(thora, extra='__rows[1].groupIds = {[__group]=true, ["other-group"]=true}')
    assert thora.eval(f'#WoWStatusTogether.members({group!r})') == 3
    rows = totals(thora, group)
    assert rows['Levels between us'][1] == '90'


def test_zones_are_counted_by_name_from_the_log():
    mira, thora = pair()
    pump(mira, thora)
    group = crafted(thora)
    thora.execute('''
        local group = __group
        for i, text in ipairs({"Entered Duskwood", "Entered Westfall", "Entered Duskwood"}) do
            WoWStatusJournal.received({sender="Mira-TestRealm", nonce="1-"..i, kind="zone",
                text=text, at=time(), group_id=group})
        end
    ''')
    rows = totals(thora, group)
    # Two friends in Duskwood are one zone discovered.
    assert rows['Zones discovered'][1] == '2'


def test_this_week_counts_only_this_week_and_says_so_when_it_is_quiet():
    mira, thora = pair()
    pump(mira, thora)
    group = crafted(thora)
    assert thora.eval(f'WoWStatusTogether.weekText(WoWStatusTogether.totals({group!r}).week)') is None
    thora.execute('''
        local group = __group
        WoWStatusJournal.received({sender="Mira-TestRealm", nonce="2-1", kind="level", level=41,
            text="Reached level 41!", at=time(), group_id=group})
        WoWStatusJournal.received({sender="Mira-TestRealm", nonce="2-2", kind="zone",
            text="Entered Stranglethorn Vale", at=time(), group_id=group})
        -- Three weeks ago: outside the window.
        WoWStatusJournal.received({sender="Mira-TestRealm", nonce="2-3", kind="level", level=39,
            text="Reached level 39!", at=time()-21*86400, group_id=group})
    ''')
    week = thora.eval(f'WoWStatusTogether.totals({group!r}).week')
    assert week.level == 1 and week.zone == 1
    text = thora.eval(f'WoWStatusTogether.weekText(WoWStatusTogether.totals({group!r}).week)')
    assert '1 level' in text and '1 new zone' in text


def test_a_hidden_character_never_reaches_the_totals():
    mira, thora = pair()
    pump(mira, thora)
    # R.groups() drops hidden characters, so Together never sees them. With the
    # real roster, hiding Mira must lower the member count.
    before = thora.eval('''(function()
        local group = next(character().group_ids)
        return #WoWStatusTogether.members(group)
    end)()''')
    thora.execute('WoWStatusRoster.hiddenNames = function() return {["mira-testrealm"] = true} end')
    after = thora.eval('''(function()
        local group = next(character().group_ids)
        return #WoWStatusTogether.members(group)
    end)()''')
    assert before >= 1 and after == before - 1


def test_the_page_opens_from_overview_and_the_slash_command():
    mira, thora = pair()
    pump(mira, thora)
    thora.eval('SlashCmdList.WOWSTATUS')('together')
    assert thora.eval('WoWStatusMainWindow.active()') == 'together'
    assert 'Together' in thora.eval('WoWStatusTogetherPage.heading:GetText()')
    assert thora.eval('WoWStatusTogetherPage.since:GetText()') != ''
    thora.eval('SlashCmdList.WOWSTATUS')('overview')
    thora.execute('WoWStatusOverviewPage.group.together.OnClick()')
    assert thora.eval('WoWStatusMainWindow.active()') == 'together'


def test_without_a_group_the_page_says_so_instead_of_showing_zeroes():
    _, thora = pair()
    # No group joined: the page reads the group list from Firsts.
    thora.execute('WoWStatusFirsts.groups = function() return {} end')
    thora.eval('WoWStatusTogether.show')()
    assert 'Join a group' in thora.eval('WoWStatusTogetherPage.heading:GetText()')
    assert thora.eval('WoWStatusTogetherPage.tiles[1]:IsShown()') is False


def test_the_group_picker_is_a_controller_control():
    mira, thora = pair()
    pump(mira, thora)
    thora.eval('WoWStatusTogether.show')()
    assert thora.eval('WoWStatusTogetherPage.pick.kind') == 'Button'
    assert thora.eval('WoWStatusTogetherPage.pick.OnClick') is not None
    # One group: nothing to choose, so the button is disabled rather than dead.
    assert thora.eval('WoWStatusTogetherPage.pick.enabled') is False
