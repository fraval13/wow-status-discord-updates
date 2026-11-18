"""Cross-feature regressions for the combined PR release; game APIs are mocked."""
from test_journal import actor, clock
from test_local_time import local_client
from test_streaks import board
from test_week import with_entries


def test_bingo_uses_one_week_and_card_across_viewer_timezones():
    # Monday in Oslo, still Sunday in Los Angeles: display calendars differ,
    # but a cooperative group's board and event membership must agree.
    now = "2026-11-16T00:30:00+00:00"
    cards = []
    for zone in ('Europe/Oslo', 'America/Los_Angeles', 'Asia/Tokyo'):
        lua = local_client(zone, now)
        lua.execute('WoWStatusFeatures.set("bingo", true)')
        group = lua.eval('(next(character().group_ids))')
        with_entries(lua, [('Mira-TestRealm', '1-1-a', 'level', 60, '{level=21}')])
        result, week = lua.eval('WoWStatusFirsts.bingo')(group, 0)
        cards.append((week, [(result[i]['text'], result[i]['by']) for i in range(1, 26)]))
    assert cards[0] == cards[1] == cards[2]
    assert cards[0][0] == '2026-11-16'


def test_missing_death_boundary_never_claims_a_deathless_streak():
    lua = actor('Thora')
    clock(lua, 10)
    with_entries(lua, [('Mira-TestRealm', '1-1-a', 'level', 86400 * 10, '{level=10}'),
                       ('Mira-TestRealm', '1-2-a', 'level', 60, '{level=20}')])
    board(lua, {'Mira-TestRealm': 1})
    assert lua.eval('WoWStatusStreaks.forRow({name="Mira-TestRealm",deaths=1})') is None
    board(lua, {'Mira-TestRealm': 0})
    assert lua.eval('WoWStatusStreaks.forRow({name="Mira-TestRealm",deaths=0})') is not None


def test_countdown_migration_preserves_valid_targets_and_removes_broken_values():
    lua = actor('Thora')
    lua.execute('''
        local step = WoWStatusMigrations.character[4]
        assert(step.version == 5)
        for _, value in ipairs({false, "broken", {}, -1, 1001, 40.5}) do
            local c = {personal_goal_level=value}
            step.run(c)
            assert(c.personal_goal_level == nil)
        end
        local c = {personal_goal_level=40}
        step.run(c)
        assert(c.personal_goal_level == 40)
    ''')


def test_race_configure_is_reachable_and_uses_the_same_saved_race():
    lua = actor('Thora')
    clock(lua, 10)
    with_entries(lua, [('Mira-TestRealm', '1-1-a', 'level', 60, '{level=10}')])
    lua.execute('''
        __level=11
        WoWStatusFeatures.set("race", true)
        SlashCmdList.WOWSTATUS("labs")
        for _, row in ipairs(WoWStatusLabsPage.rows) do
            if row.id == "race" then row.configure.OnClick(row.configure) end
        end
        assert(WoWStatusMainWindow.active() == "race")
        local page = WoWStatusMainWindow.show("race")
        local buttons = {page.less,page.more,page.start,page.cancel}
        page.GetChildren = function() return (unpack or table.unpack)(buttons) end
        for i, b in ipairs(buttons) do
            b.GetRect = function() return 24+i*70,200,66,26 end
            b.GetObjectType = function() return "Button" end
        end
        local found={}
        for _,b in ipairs(WoWStatusGamepad.controls(page)) do found[b]=true end
        assert(found[page.less] and found[page.more] and found[page.start] and not found[page.cancel])
        page.start.OnClick()
        assert(WoWStatusStatusLine.race().friend == "Mira-TestRealm")
        assert(WoWStatusStatusLine.race().target == 12)
        page.cancel.OnClick()
        assert(WoWStatusStatusLine.race() == nil)
    ''')


def test_an_alts_level_never_wins_the_current_characters_race():
    lua = actor('Thora')
    clock(lua, 10)
    with_entries(lua, [('Mira-TestRealm', '1-1-a', 'level', 60, '{level=10}')])
    lua.execute('''
        WoWStatusFeatures.set("race", true)
        local entries = WoWStatusJournal.entries()
        entries[#entries+1] = {id="alt:1",owner="OtherCharacterGUID",sender="Alt-TestRealm",
            kind="level",level=60,at=time()-30}
        assert(WoWStatusStatusLine.raceStart("Mira", 40))
        assert(WoWStatusStatusLine.race() ~= nil)
        assert(WoWStatusStatusLine.raceText() ~= nil)
    ''')
