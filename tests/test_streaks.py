"""Deathless streaks (#164): who has NOT died lately, from a crafted log."""
from test_addon import STUBS, make_lua
from test_journal import actor, clock
from test_week import plain, with_entries

DAY = 86400

# Mira: level 10, a death 15 days ago, then 12 levels, a death in Stranglethorn a
# little earlier today and one level since. Bob: no death in the log, 7 levels in 10 days.
LOG = [
    ('Mira-TestRealm', '1-1-a', 'level', 20 * DAY, '{level=10}'),
    ('Mira-TestRealm', '1-2-b', 'death', 15 * DAY, None),
    *[('Mira-TestRealm', f'1-3-{level}', 'level', (14 - (level - 11)) * DAY, f'{{level={level}}}')
      for level in range(11, 23)],
    ('Mira-TestRealm', '1-4-c', 'death', 2 * 3600, '{text="Total deaths: 2"}'),
    ('Mira-TestRealm', '1-5-d', 'level', 3600, '{level=23}'),
    *[('Bob-TestRealm', f'2-1-{level}', 'level', (10 - (level - 5)) * DAY, f'{{level={level}}}')
      for level in range(5, 12)],
]


def board(lua, rows):
    """The roster's shared death totals: {name: deaths or None}."""
    body = ','.join(f'{{name="{name}", deaths={"nil" if deaths is None else deaths}}}' for name, deaths in rows.items())
    lua.execute(f'WoWStatusRoster.leaderboard = function() return {{{body}}} end; WoWStatusStreaks.reset()')


def crafted(rows=None):
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute('''
        local details = WoWStatusJournal.details
        function WoWStatusJournal.details(e)
            if e.kind == "death" and e.sender == "Mira-TestRealm" and e.text == "Total deaths: 2" then
                return {zone="Stranglethorn Vale"}
            end
            return details(e)
        end
    ''')
    with_entries(lua, LOG)
    board(lua, rows or {'Mira-TestRealm': 2, 'Bob-TestRealm': 0})
    return lua, lua.eval('__group')


def ended(lua):
    return lua.eval('''(function()
        for _, e in ipairs(WoWStatusJournal.entries()) do
            if e.kind == "death" and e.text == "Total deaths: 2" then return WoWStatusStreaks.endedText(e) end
        end
    end)()''')


def test_streaks_are_counted_from_the_log_and_bounded_by_it():
    lua, group = crafted()
    lua.execute(f'''
        local data = WoWStatusStreaks.compute("{group}")
        local mira = WoWStatusPopups.senderKey("Mira-TestRealm")
        local bob = WoWStatusPopups.senderKey("Bob-TestRealm")
        -- Mira's longest run: 12 levels in the 14 days between her deaths, exact.
        local best = data.best[mira]
        assert(best.levels == 12 and best.exact and best.seconds == 15 * {DAY} - 7200, best.levels)
        -- Since the last death: one level, under a day.
        assert(data.current[mira].levels == 1 and data.current[mira].exact)
        -- Bob never died in the log: his streak is at least what the log holds.
        assert(data.current[bob].levels == 7 and not data.current[bob].exact)
        assert(WoWStatusStreaks.describe(data.current[bob]) == "at least 7 levels · 10 days")
        assert(WoWStatusStreaks.describe(best) == "12 levels · 14 days")
    ''')


def test_records_show_the_longest_current_and_longest_ever_streak():
    lua, group = crafted()
    text = plain(lua.eval(f'WoWStatusFirsts.funRecords("{group}")'))
    assert 'Longest deathless streak now: Bob — at least 7 levels · 10 days' in text, text
    assert 'Longest deathless streak ever: Mira — 12 levels · 14 days' in text, text
    lua.execute('WoWStatusLocale.set("nn")')
    text = plain(lua.eval(f'WoWStatusFirsts.funRecords("{group}")'))
    assert 'Lengst utan å døy no: Bob — minst 7 nivå · 10 dagar' in text, text
    assert 'Lengst utan å døy nokon gong: Mira — 12 nivå · 14 dagar' in text, text


def test_short_streaks_hold_no_record():
    lua = actor('Thora')
    clock(lua, 10)
    with_entries(lua, [('Mira-TestRealm', '1-1-a', 'level', 2 * DAY, '{level=10}'),
                       ('Mira-TestRealm', '1-2-b', 'level', DAY, '{level=11}')])
    board(lua, {'Mira-TestRealm': 0})
    text = plain(lua.eval(f'WoWStatusFirsts.funRecords("{lua.eval("__group")}")'))
    assert 'deathless' not in text, text


def test_the_death_that_ends_a_long_streak_says_so_in_the_log():
    lua, _ = crafted()
    assert ended(lua) == '12 levels without a death ends in Stranglethorn Vale.'
    lua.execute('WoWStatusLocale.set("nn")')
    assert ended(lua) == '12 nivå utan å døy endar i Stranglethorn Vale.'
    # The first death ended a run that started before the log: "at least", one level.
    first = lua.eval('''(function()
        for _, e in ipairs(WoWStatusJournal.entries()) do
            if e.kind == "death" and e.text == "Total deaths: 1" then return WoWStatusStreaks.endedText(e) end
        end
    end)()''')
    assert first is None  # one level and five days is not a long streak
    # The log row shows the line before the death caption.
    lua.execute('''
        WoWStatusLocale.set("en")
        WoWStatusJournal.show()
        local found
        for _, row in ipairs(WoWStatusActivityLog.rows) do
            local text = row.flavour.text or ""
            if text:find("without a death ends in Stranglethorn Vale.", 1, true) then found = text end
        end
        assert(found and found:find("^|cffffd100"), tostring(found))
    ''')


def test_a_character_without_shared_death_total_shows_no_streak():
    lua, group = crafted({'Mira-TestRealm': None, 'Bob-TestRealm': None})
    text = plain(lua.eval(f'WoWStatusFirsts.funRecords("{group}")'))
    assert 'deathless' not in text, text
    assert ended(lua) is None
    assert lua.eval('WoWStatusStreaks.forRow({name="Bob-TestRealm"})') is None
    # A death total higher than the log's last death: a death the log never saw.
    board(lua, {'Mira-TestRealm': 3, 'Bob-TestRealm': 0})
    text = plain(lua.eval(f'WoWStatusFirsts.funRecords("{group}")'))
    assert 'Mira' not in text and 'Bob' in text, text
    assert ended(lua) is None


def test_profile_shows_the_current_streak():
    lua, _ = crafted()
    lua.execute('''
        local facts = WoWStatusProfile.data({name="Bob-TestRealm", deaths=0}).facts
        local found
        for _, f in ipairs(facts) do if f[1] == "Deathless streak" then found = f[2] end end
        assert(found == "at least 7 levels · 10 days", tostring(found))
        facts = WoWStatusProfile.data({name="Bob-TestRealm"}).facts
        for _, f in ipairs(facts) do assert(f[1] ~= "Deathless streak") end
    ''')


def test_a_hardcore_death_ends_the_run_for_good_without_a_line():
    lua = actor('Thora')
    clock(lua, 10)
    with_entries(lua, [
        *[('Mira-TestRealm', f'1-1-{level}', 'level', (20 - level) * DAY, f'{{level={level}}}') for level in range(2, 12)],
        ('Mira-TestRealm', '1-2-a', 'death', DAY, '{text="Died in Hardcore"}'),
    ])
    board(lua, {'Mira-TestRealm': 0})
    group = lua.eval('__group')
    lua.execute(f'''
        local data = WoWStatusStreaks.compute("{group}")
        local mira = WoWStatusPopups.senderKey("Mira-TestRealm")
        assert(data.current[mira] == nil)
        assert(data.best[mira].levels == 10)
        for _, e in ipairs(WoWStatusJournal.entries()) do
            if e.kind == "death" then assert(WoWStatusStreaks.endedText(e) == nil) end
        end
    ''')
    text = plain(lua.eval(f'WoWStatusFirsts.funRecords("{group}")'))
    assert 'now:' not in text and 'Longest deathless streak ever: Mira — at least 10 levels' in text, text


def notices(lua):
    """Collect streak notices; medal notices for new Firsts are left out."""
    lua.execute('''
        __notices = {}
        WoWStatusPopups.notice = function(item)
            if item.flavour == "Deathless streak" then table.insert(__notices, item) end
            return true
        end
    ''')


def test_milestones_are_off_by_default_and_announce_every_five_levels():
    lua = actor('Thora')
    clock(lua, 10)
    notices(lua)
    board(lua, {'Mira-TestRealm': 1})
    group = lua.eval('__group')
    with_entries(lua, [('Mira-TestRealm', '1-0-a', 'death', 3 * 3600, None)])
    with_entries(lua, [('Mira-TestRealm', f'1-1-{level}', 'level', 3000 - level, f'{{level={level}}}') for level in range(2, 7)])
    assert lua.eval('#__notices') == 0
    assert lua.eval('WoWStatusStreaks.milestones()') is False
    lua.execute('WoWStatusStreaks.setMilestones(true)')
    with_entries(lua, [('Mira-TestRealm', f'1-2-{level}', 'level', 100 - level, f'{{level={level}}}') for level in range(7, 12)])
    assert lua.eval('#__notices') == 1
    assert lua.eval('__notices[1].text') == '10 levels without a death!'
    assert lua.eval('__notices[1].sender') == 'Mira-TestRealm'
    lua.execute('WoWStatusLocale.set("nn")')
    assert lua.eval('WoWStatusLocale.T(__notices[1].text)') == '10 nivå utan å døy!'
    # Death sharing off: no milestone.
    board(lua, {'Mira-TestRealm': None})
    with_entries(lua, [('Mira-TestRealm', f'1-3-{level}', 'level', 50 - level, f'{{level={level}}}') for level in range(12, 17)])
    assert lua.eval('#__notices') == 1
    del group


def test_a_week_is_announced_once_per_streak():
    lua = actor('Thora')
    clock(lua, 10)
    notices(lua)
    lua.execute('WoWStatusStreaks.setMilestones(true)')
    board(lua, {'Mira-TestRealm': 1})
    with_entries(lua, [('Mira-TestRealm', '1-0-a', 'death', 8 * DAY, None)])
    with_entries(lua, [('Mira-TestRealm', '1-1-a', 'zone', 60, '{text="Entered Duskwood"}')])
    assert lua.eval('__notices[1] and __notices[1].text') == 'A week without a death!'
    with_entries(lua, [('Mira-TestRealm', '1-1-b', 'zone', 30, '{text="Entered Westfall"}')])
    assert lua.eval('#__notices') == 1
    lua.execute('WoWStatusLocale.set("nn")')
    assert lua.eval('WoWStatusLocale.T("2 weeks without a death!")') == '2 veker utan å døy!'


def test_malformed_saved_streak_state_is_ignored():
    lua = make_lua(STUBS)
    lua.execute('''
        WoWStatusDB.streaks = "broken"
        assert(WoWStatusStreaks.milestones() == false)
        WoWStatusDB.streaks = {milestones="yes", weeks=5}
        assert(WoWStatusStreaks.milestones() == false)
        WoWStatusStreaks.setMilestones(true)
        assert(WoWStatusStreaks.milestones() == true and type(WoWStatusDB.streaks.weeks) == "table")
    ''')


def test_the_milestone_option_is_a_checkbox_with_the_settings():
    lua = make_lua(STUBS + '''
        local methods = getmetatable(CreateFrame("Frame")).__index
        function methods:SetPoint(_, _, y) self.y = y end
    ''')
    lua.eval('SlashCmdList.WOWSTATUS')('previews')
    lua.execute('''
        local panel = WoWStatusNotificationPreviews
        local box = panel.streaks
        assert(box.y > panel.divider.y and box.y < panel.big.y and box.y > panel.line.enabled.y)
        assert(box:GetChecked() == false)
        box:SetChecked(true); box.OnClick(box)
        assert(WoWStatusStreaks.milestones() == true)
    ''')
