"""Shared group goals with a progress bar (#157)."""
import pytest
from test_journal import clock
from test_roster import pair, person, pump

NOW = 1793000000
# The plain test frames have no SetEnabled; record it like the main window tests do.
ENABLED = 'getmetatable(CreateFrame("Frame")).__index.SetEnabled = function(self, value) self.enabled = value end'


def group_of(lua):
    return lua.eval('(next(character().group_ids))')


def goal_lines(lines):
    return [line for line in lines if line.startswith('A ')]


def receive(lua, text, sender='Mira-TestRealm'):
    return lua.eval('WoWStatusRoster.receive')(text, sender, 'WHISPER')


def stored(lua):
    return lua.eval(f'WoWStatusDB.goals and WoWStatusDB.goals["{group_of(lua)}"]')


def introduced():
    """Mira and Thora in one group, each holding the other's character list."""
    mira, thora = pair()
    pump(mira, thora)
    pump(thora, mira)
    return mira, thora


def test_a_goal_travels_to_members_and_shows_on_overview_and_leaderboard():
    mira, thora = introduced()
    group = group_of(mira)
    assert mira.eval(f'WoWStatusGoals.set("{group}", "level", "all", 10, 14)') is True
    lines = goal_lines(pump(mira, thora, start=300))
    assert len(lines) == 1
    words = lines[0].split(' ')
    assert words[0] == 'A' and words[2] == mira.eval('WoWStatusDB.roster.id')
    assert words[4:7] == ['level', 'all', '10'] and int(words[7]) == int(words[3]) + 14 * 86400
    assert len(lines[0]) < 80  # a bounded, compact record
    goal = stored(thora)
    assert goal.measure == 'level' and goal.target == 10
    assert thora.eval(f'WoWStatusGoals.setBy(WoWStatusGoals.get("{group}"))') == 'Frank'
    thora.execute(f'''
        local goal = WoWStatusGoals.get("{group}")
        assert(WoWStatusGoals.title(goal) == "Everybody reaches level 10")
        local progress = WoWStatusGoals.progress("{group}", goal)
        assert(progress.known == 2 and progress.reached == 0, progress.known)
        assert(WoWStatusGoals.status(goal, progress) == "0 of 2 there · 14 days left")
        SlashCmdList.WOWSTATUS("leaderboard")
        local row = WoWStatusLeaderboardPage.goalRow
        assert(row:IsShown() and row.title.text:find("Everybody reaches level 10", 1, true))
        WoWStatusMainWindow.show("overview")
        local band = WoWStatusOverviewPage.goal
        assert(band.title.text:find("Everybody reaches level 10", 1, true))
        assert(band.status.text == "0 of 2 there · 14 days left")
    ''')
    # Sent once a session at first contact, like the list, and not repeated.
    assert goal_lines(pump(mira, thora, start=400)) == []


def test_a_goal_is_sent_again_at_the_next_first_contact():
    mira, thora = introduced()
    group = group_of(mira)
    mira.execute(f'WoWStatusGoals.set("{group}", "quests", "sum", 1000, 0)')
    third = person('Bob', 'Kari')
    third.execute('__peers={"Bob-TestRealm","Mira-TestRealm"}')
    mira.execute('__peers={"Thora-TestRealm","Mira-TestRealm","Bob-TestRealm"}')
    lines = pump(mira, third, start=300)
    assert [line[0] for line in lines].index('A') > [line[0] for line in lines].index('C')
    assert third.eval(f'WoWStatusGoals.title(WoWStatusGoals.get("{group}"))') == '1000 completed quests together'


@pytest.mark.parametrize('change', [
    lambda w: w[:4] + ['mood', 'all', '10', '0'],             # unknown measure
    lambda w: w[:4] + ['level', 'sum', '10', '0'],            # "together" makes no sense for level
    lambda w: w[:4] + ['level', 'all', '999', '0'],           # above the level cap
    lambda w: w[:4] + ['level', 'all', '1', '0'],             # below the smallest target
    lambda w: w[:4] + ['quests', 'all', '1e3', '0'],          # not a plain number
    lambda w: w[:4] + ['quests', 'all', '-50', '0'],
    lambda w: w[:4] + ['deaths', 'sum', '5', '0'],            # "fewer than" needs a deadline
    lambda w: w[:4] + ['level', 'all', '10', str(int(w[3]) + 400 * 86400)],  # deadline too far away
    lambda w: w[:4] + ['level', 'all', '10', str(int(w[3]) - 1)],            # deadline before it was set
    lambda w: w[:3] + [str(NOW + 100000)] + w[4:],            # set in the future
    lambda w: w[:3] + ['12x'] + w[4:],
    lambda w: w + ['extra'],
    lambda w: w[:7],
    lambda w: w[:4] + ['none', 'all', '0', '0'],              # a malformed clear
    lambda w: w[:4] + ['level', 'all', '1' + '0' * 300, '0'],  # oversized
])
def test_malformed_or_oversized_goals_are_rejected_silently(change):
    mira, thora = introduced()
    group = group_of(thora)
    pid = mira.eval('WoWStatusDB.roster.id')
    words = ['A', group, pid, str(NOW), 'level', 'all', '10', '0']
    assert receive(thora, ' '.join(words)) is True
    thora.execute('WoWStatusDB.goals = {}')
    popups = thora.eval('#__sent')
    assert receive(thora, ' '.join(change(list(words)))) is False
    assert stored(thora) is None
    assert thora.eval('#__sent') == popups  # silent: nothing reported to anyone


def test_only_the_setter_can_change_or_clear_the_goal():
    mira, thora = introduced()
    bob = person('Bob', 'Kari')
    for lua in (mira, thora, bob):
        lua.execute('__peers={"Thora-TestRealm","Mira-TestRealm","Bob-TestRealm"}')
    pump(bob, thora)
    group = group_of(thora)
    mira_id, bob_id = mira.eval('WoWStatusDB.roster.id'), bob.eval('WoWStatusDB.roster.id')
    goal = f'A {group} {mira_id} {NOW} level all 10 0'
    # A record claiming Mira as its setter, sent by Bob, is refused.
    assert receive(thora, goal, 'Bob-TestRealm') is False
    assert receive(thora, goal) is True
    # Bob cannot replace or clear Mira's goal, under his own ID or hers.
    assert receive(thora, f'A {group} {bob_id} {NOW + 10} quests sum 500 0', 'Bob-TestRealm') is False
    assert receive(thora, f'A {group} {mira_id} {NOW + 10} none - 0 0', 'Bob-TestRealm') is False
    assert stored(thora).pid == mira_id and stored(thora).measure == 'level'
    # Mira can: an older record is refused, a newer one replaces it, and she can clear it.
    assert receive(thora, f'A {group} {mira_id} {NOW - 10} dungeons all 5 0') is False
    assert receive(thora, f'A {group} {mira_id} {NOW} dungeons all 5 0') is False  # changed without a new time
    assert receive(thora, f'A {group} {mira_id} {NOW + 20} dungeons all 5 0') is True
    assert stored(thora).measure == 'dungeons'
    assert receive(thora, f'A {group} {mira_id} {NOW + 30} none - 0 0') is True
    assert thora.eval(f'WoWStatusGoals.get("{group}")') is None
    # Once cleared, anyone in the group may set the next one.
    assert receive(thora, f'A {group} {bob_id} {NOW + 40} quests sum 500 0', 'Bob-TestRealm') is True
    # The editor refuses to overwrite another member's goal too.
    assert thora.eval(f'WoWStatusGoals.blocked("{group}")') == 'Only the member who set this goal can change it.'
    assert thora.eval(f'WoWStatusGoals.set("{group}", "level", "all", 20, 0)') is False
    assert thora.eval(f'WoWStatusGoals.clear("{group}")') is False


def test_a_finished_or_long_silent_goal_no_longer_blocks_a_new_one():
    mira, thora = introduced()
    bob = person('Bob', 'Kari')
    for lua in (thora, bob):
        lua.execute('__peers={"Thora-TestRealm","Mira-TestRealm","Bob-TestRealm"}')
    pump(bob, thora)
    group = group_of(thora)
    mira_id, bob_id = mira.eval('WoWStatusDB.roster.id'), bob.eval('WoWStatusDB.roster.id')
    assert receive(thora, f'A {group} {mira_id} {NOW} quests sum 100000 {NOW + 3 * 86400}') is True
    clock(thora, 4 * 86400)  # past its deadline
    thora.eval('WoWStatusGoals.check')()
    assert thora.eval(f'WoWStatusGoals.outcome(WoWStatusGoals.get("{group}"))') == 'missed'
    assert receive(thora, f'A {group} {bob_id} {NOW + 4 * 86400} level all 20 0', 'Bob-TestRealm') is True
    # Bob's goal, never heard of again for over 30 days, stops blocking Mira.
    clock(thora, 40 * 86400)
    assert receive(thora, f'A {group} {mira_id} {NOW + 40 * 86400} level all 30 0') is True


def test_progress_leaves_out_hidden_characters_and_hidden_friends():
    mira, thora = introduced()
    group = group_of(thora)
    # Thora's level-60 bank alt is hidden from lists; Mira's alt is hidden by Mira.
    thora.execute('''
        WoWStatusDB.characters["Bank"] = {identity={client=WoWStatusAdapter.client_id, guid="Player-123-Bank", name="Bankalt",
            realm="TestRealm"}, roster_info={race="Dwarf", sex=3, class="WARRIOR", level=60, at=1}, hide_from_list=true,
            settings=character().settings}
    ''')
    pid = mira.eval('WoWStatusDB.roster.id')
    assert receive(thora, f'C {group} {pid} Frank Mirabank-TestRealm Dwarf 3 WARRIOR 60') is True
    assert receive(thora, f'Z {group} {pid} Mirabank-TestRealm 1 1') is True
    assert receive(thora, f'A {group} {pid} {NOW} level all 50 0') is True
    progress = thora.eval(f'WoWStatusGoals.progress("{group}")')
    assert (progress.known, progress.reached) == (2, 0)
    names = thora.eval('''(function()
        local seen = {}
        for _, section in ipairs(WoWStatusRoster.sections()) do
            for _, entry in ipairs(section.entries) do
                for _, row in ipairs(entry.rows) do seen[#seen + 1] = row.name end
            end
        end
        return table.concat(seen, ",")
    end)()''')
    assert 'Mirabank' not in names and 'Bankalt' not in names
    # A friend at the target counts; a friend hidden completely (#169) is left out.
    assert receive(thora, f'C {group} {pid} Frank Mira-TestRealm Dwarf 3 WARRIOR 55') is True
    assert thora.eval(f'WoWStatusGoals.progress("{group}").reached') == 1
    thora.execute('WoWStatusMutes.hidden = function(name) return name:find("^Mira") ~= nil end')
    progress = thora.eval(f'WoWStatusGoals.progress("{group}")')
    assert (progress.known, progress.reached) == (1, 0)


def test_deaths_since_the_goal_count_and_a_kept_limit_is_reached_at_the_deadline():
    mira, thora = introduced()
    group = group_of(thora)
    pid = mira.eval('WoWStatusDB.roster.id')
    deadline = NOW + 7 * 86400
    assert receive(thora, f'A {group} {pid} {NOW + 50} deaths sum 3 {deadline}') is True
    thora.execute('''
        WoWStatusJournal.received({sender="Mira-TestRealm", nonce="d0", kind="death", text="Died", at=1793000010})
        WoWStatusJournal.received({sender="Mira-TestRealm", nonce="d1", kind="death", text="Died", at=1793000100})
    ''')
    clock(thora, 200)
    goal = f'WoWStatusGoals.get("{group}")'
    assert thora.eval(f'WoWStatusGoals.status({goal}, WoWStatusGoals.progress("{group}"))') == '1 of 3 deaths · 7 days left'
    thora.eval('WoWStatusGoals.check')()
    assert thora.eval(f'WoWStatusGoals.outcome({goal})') == 'open'
    clock(thora, 8 * 86400)
    thora.eval('WoWStatusGoals.check')()
    assert thora.eval(f'WoWStatusGoals.outcome({goal})') == 'reached'


def test_reaching_a_goal_gets_a_big_banner_and_the_goal_medal():
    mira, thora = introduced()
    group = group_of(thora)
    pid = mira.eval('WoWStatusDB.roster.id')
    assert receive(thora, f'A {group} {pid} {NOW} level all 2 0') is True
    assert thora.eval(f'WoWStatusGoals.outcome(WoWStatusGoals.get("{group}"))') == 'open'
    assert receive(thora, f'C {group} {pid} Frank Mira-TestRealm Dwarf 3 WARRIOR 2') is True
    thora.execute('''
        WoWStatusAdapter.max_level = WoWStatusAdapter.max_level
        __levels = {player=2}
        local info = character().roster_info; info.level = 2
    ''')
    thora.eval('WoWStatusGoals.check')()
    goal = f'WoWStatusGoals.get("{group}")'
    assert thora.eval(f'WoWStatusGoals.outcome({goal})') == 'reached'
    thora.execute('''
        local found
        for i = 1, 20 do
            WoWStatusPopups.tick()
            if __toast and __toast.item and __toast.item.kind == "goal" then found = __toast.item end
        end
    ''')
    item = thora.eval('''(function()
        local P = WoWStatusPopups
        for _, frame in ipairs(__frames) do
            if frame.item and frame.item.kind == "goal" then return frame.item end
        end
    end)()''')
    assert item is not None and item.text == 'Goal reached: Everybody reaches level 2'
    assert thora.eval('WoWStatusPopups.bigMoment')(item) is True
    medal = thora.eval(f'WoWStatusFirsts.compute(WoWStatusJournal.entries(), "{group}").goal')
    assert medal is not None and medal.text == 'Everybody reaches level 2'
    thora.execute('SlashCmdList.WOWSTATUS("records")')
    holders = [thora.eval(f'WoWStatusRecordsPage.rows[{i}].text') for i in range(1, thora.eval('#WoWStatusRecordsPage.rows') + 1)]
    assert any(text.startswith('Group goal reached — Everybody reaches level 2') for text in holders)
    # One banner only, however often it is checked again.
    count = thora.eval('#__frames')
    thora.eval('WoWStatusGoals.check')()
    assert stored(thora).done_at is not None and thora.eval('#__frames') == count


def test_the_editor_sets_and_clears_a_goal_with_buttons_only():
    mira, thora = introduced()
    group = group_of(mira)
    mira.execute(ENABLED)
    mira.execute('SlashCmdList.WOWSTATUS("goal")')
    assert mira.eval('WoWStatusMainWindow.active()') == 'goal'
    mira.execute('''
        local page = WoWStatusGoalPage
        for _, name in ipairs({"measureNext", "measureBack", "everybody", "together", "less", "more",
            "muchLess", "muchMore", "deadlineBack", "deadlineNext", "save", "clear", "nextGroup"}) do
            assert(page[name].kind == "Button" and page[name].OnClick, name)
        end
        assert(page.preview.text:find("Everybody reaches level", 1, true))
        assert(page.together.enabled == false) -- not for level
        page.measureNext.OnClick(page.measureNext)
        assert(page.preview.text:find("Everybody completes 500 quests", 1, true))
        page.together.OnClick(page.together)
        page.more.OnClick(page.more)
        assert(page.preview.text:find("550 completed quests together", 1, true))
        page.deadlineNext.OnClick(page.deadlineNext)
        assert(page.deadline.text == "Deadline: 3 days")
        assert(page.clear.enabled == false)
        page.save.OnClick(page.save)
        assert(WoWStatusGoals.get(next(character().group_ids)).target == 550)
        assert(page.clear.enabled ~= false)
        page.clear.OnClick(page.clear)
        assert(WoWStatusGoals.get(next(character().group_ids)) == nil)
    ''')
    lines = goal_lines(pump(mira, thora, start=300))
    assert [line.split(' ')[4] for line in lines] == ['quests', 'none']
    assert thora.eval(f'WoWStatusGoals.get("{group}")') is None
    # The Overview's "Goal…" button opens the editor for the band's group.
    thora.execute('''
        WoWStatusMainWindow.show("overview")
        local edit = WoWStatusOverviewPage.goal.edit
        assert(edit.kind == "Button")
        edit.OnClick(edit)
        assert(WoWStatusMainWindow.active() == "goal")
    ''')


def test_goal_texts_are_in_nynorsk():
    mira, thora = introduced()
    group = group_of(thora)
    pid = mira.eval('WoWStatusDB.roster.id')
    assert receive(thora, f'A {group} {pid} {NOW} dungeons sum 20 {NOW + 3 * 86400}') is True
    thora.execute('WoWStatusLocale.set("nn")')
    goal = f'WoWStatusGoals.get("{group}")'
    assert thora.eval(f'WoWStatusGoals.title({goal})') == '20 fangehol rydda saman'
    assert thora.eval(f'WoWStatusGoals.status({goal}, WoWStatusGoals.progress("{group}"))') == '0 av 20 · 3 dagar att'


def test_saved_goals_that_are_not_valid_are_dropped():
    lua = person('Thora', 'Ada')
    group = group_of(lua)
    lua.execute(f'''
        WoWStatusDB.goals = {{["{group}"] = {{pid="x", at=1793000000, measure="level", shape="sum", target=10, deadline=0}},
            other = "junk"}}
        assert(WoWStatusGoals.get("{group}") == nil and next(WoWStatusDB.goals) == nil)
        WoWStatusDB.goals = "junk"
        assert(WoWStatusGoals.get("{group}") == nil)
        WoWStatusMainWindow.show("overview")
    ''')


def test_a_member_claiming_the_setters_player_id_still_cannot_change_an_open_goal():
    mira, thora = introduced()
    bob = person('Bob', 'Kari')
    thora.execute('__peers={"Thora-TestRealm","Mira-TestRealm","Bob-TestRealm"}')
    group = group_of(thora)
    mira_id = mira.eval('WoWStatusDB.roster.id')
    assert receive(thora, f'A {group} {mira_id} {NOW} level all 10 0') is True
    # Bob lists his own character under Mira's player ID, then tries to clear her goal.
    assert receive(thora, f'C {group} {mira_id} Frank Bob-TestRealm Dwarf 3 WARRIOR 5', 'Bob-TestRealm') is True
    assert receive(thora, f'A {group} {mira_id} {NOW + 10} none - 0 0', 'Bob-TestRealm') is False
    assert receive(thora, f'A {group} {mira_id} {NOW + 10} quests sum 500 0', 'Bob-TestRealm') is False
    assert stored(thora).measure == 'level' and not stored(thora).cleared
    del bob


def test_an_older_goal_sent_again_never_replaces_a_newer_one():
    mira, thora = introduced()
    bob = person('Bob', 'Kari')
    for lua in (thora, bob):
        lua.execute('__peers={"Thora-TestRealm","Mira-TestRealm","Bob-TestRealm"}')
    pump(bob, thora)
    group = group_of(thora)
    mira_id, bob_id = mira.eval('WoWStatusDB.roster.id'), bob.eval('WoWStatusDB.roster.id')
    first = f'A {group} {bob_id} {NOW} quests sum 100000 {NOW + 86400}'
    assert receive(thora, first, 'Bob-TestRealm') is True
    clock(thora, 2 * 86400)
    thora.eval('WoWStatusGoals.check')()  # Bob's goal is missed: the group is free again
    assert receive(thora, f'A {group} {mira_id} {NOW + 2 * 86400} level all 10 0') is True
    # Bob's next session sends his old goal and its clear again: both are older.
    assert receive(thora, first, 'Bob-TestRealm') is False
    assert receive(thora, f'A {group} {bob_id} {NOW + 3600} none - 0 0', 'Bob-TestRealm') is False
    assert stored(thora).pid == mira_id and stored(thora).measure == 'level'


def test_the_setter_changes_the_goal_only_from_the_character_that_set_it():
    mira, thora = introduced()
    group = group_of(mira)
    assert mira.eval(f'WoWStatusGoals.set("{group}", "level", "all", 10, 0)') is True
    assert mira.eval(f'WoWStatusGoals.line("{group}")') is not None
    mira.execute('WoWStatusPopups.characterName = function() return "Miraalt-TestRealm" end')
    assert mira.eval(f'WoWStatusGoals.blocked("{group}")') == 'Change this goal from the character that set it.'
    assert mira.eval(f'WoWStatusGoals.clear("{group}")') is False
    assert mira.eval(f'WoWStatusGoals.line("{group}")') is None  # members would refuse it from this one


def test_deaths_after_the_deadline_do_not_count():
    mira, thora = introduced()
    group = group_of(thora)
    pid = mira.eval('WoWStatusDB.roster.id')
    deadline = NOW + 86400
    assert receive(thora, f'A {group} {pid} {NOW} deaths sum 2 {deadline}') is True
    thora.execute(f'''
        WoWStatusJournal.received({{sender="Mira-TestRealm", nonce="d1", kind="death", text="Died", at={NOW + 10}}})
        WoWStatusJournal.received({{sender="Mira-TestRealm", nonce="d2", kind="death", text="Died", at={deadline + 10}}})
    ''')
    clock(thora, 2 * 86400)
    thora.eval('WoWStatusGoals.check')()
    assert thora.eval(f'WoWStatusGoals.outcome(WoWStatusGoals.get("{group}"))') == 'reached'


def test_everybody_needs_more_than_one_known_player_and_unnamed_players_count_apart():
    lua = person('Thora', 'Ada')
    lua.execute('__peers={"Thora-TestRealm","Ann-TestRealm","Bea-TestRealm"}')
    group = group_of(lua)
    lua.execute('character().roster_info.level = 40')
    assert lua.eval(f'WoWStatusGoals.set("{group}", "level", "all", 40, 0)') is True
    # Only this account's numbers are known: not reached yet.
    assert lua.eval(f'WoWStatusGoals.outcome(WoWStatusGoals.get("{group}"))') == 'open'
    # Two friends without a chosen name, at 40 and 12: two players, not one at 40.
    for name, pid, level in (('Ann', 'aaaaaaaaaaaaaaaa', 40), ('Bea', 'bbbbbbbbbbbbbbbb', 12)):
        assert receive(lua, f'C {group} {pid} - {name}-TestRealm Dwarf 3 WARRIOR {level}', f'{name}-TestRealm') is True
    progress = lua.eval(f'WoWStatusGoals.progress("{group}")')
    assert (progress.known, progress.reached) == (3, 2)
    lua.eval('WoWStatusGoals.check')()
    assert lua.eval(f'WoWStatusGoals.outcome(WoWStatusGoals.get("{group}"))') == 'open'


def test_the_goal_medal_stays_after_the_goal_is_cleared():
    mira, thora = introduced()
    group = group_of(mira)
    mira.execute('character().roster_info.level = 2')
    assert receive(mira, f'C {group} {thora.eval("WoWStatusDB.roster.id")} Ada Thora-TestRealm Dwarf 3 WARRIOR 2',
                   'Thora-TestRealm') is True
    assert mira.eval(f'WoWStatusGoals.set("{group}", "level", "all", 2, 0)') is True
    assert mira.eval(f'WoWStatusGoals.outcome(WoWStatusGoals.get("{group}"))') == 'reached'
    assert mira.eval(f'WoWStatusGoals.clear("{group}")') is True
    medal = mira.eval(f'WoWStatusFirsts.compute(WoWStatusJournal.entries(), "{group}").goal')
    assert medal is not None and medal.text == 'Everybody reaches level 2'


def test_goals_are_checked_only_after_news_or_every_few_minutes():
    mira, thora = introduced()
    group = group_of(thora)
    pid = mira.eval('WoWStatusDB.roster.id')
    assert receive(thora, f'A {group} {pid} {NOW} level all 10 0') is True
    thora.execute('''
        __checks = 0
        local check = WoWStatusGoals.check
        WoWStatusGoals.check = function() __checks = __checks + 1; return check() end
        WoWStatusGoals.tick(1000)  -- the receive above was news
        assert(__checks == 1, __checks)
        WoWStatusGoals.tick(1004); WoWStatusGoals.tick(1200)
        assert(__checks == 1, __checks)
        WoWStatusGoals.tick(1000 + WoWStatusGoals.CHECK_INTERVAL)
        assert(__checks == 2, __checks)
        -- A burst of news is checked once, a few seconds later.
        WoWStatusGoals.touch(); WoWStatusGoals.touch(); WoWStatusGoals.tick(1302)
        assert(__checks == 2, __checks)
        WoWStatusGoals.tick(1300 + WoWStatusGoals.NEWS_DELAY)
        assert(__checks == 3, __checks)
    ''')


def test_the_leaderboard_goal_row_sits_between_the_heading_and_the_ranking():
    mira, thora = introduced()
    group = group_of(thora)
    pid = mira.eval('WoWStatusDB.roster.id')
    assert receive(thora, f'A {group} {pid} {NOW} level all 10 0') is True
    thora.execute('''
        local methods = getmetatable(CreateFrame("Frame")).__index
        function methods:SetPoint(point, a, b, c) if type(a) == "number" then self.y = b end end
        SlashCmdList.WOWSTATUS("leaderboard")
        local page = WoWStatusLeaderboardPage
        -- The heading line (about 20 high) ends above the row; the 26-high row ends above the column titles.
        assert(page.heading.y - 20 >= page.goalRow.y, page.heading.y)
        assert(page.sort.y == nil or page.sort.y - 24 >= page.goalRow.y)
        -- View, Main and Pinned first (#200) sit on their own line above the row.
        for _, button in ipairs({page.mode, page.main, page.pinnedFirst}) do
            assert(button.y - 24 >= page.goalRow.y, button.y)
        end
        assert(page.goalRow.y - 26 >= page.boardHeader.y, page.boardHeader.y)
    ''')


def test_a_goal_set_on_a_character_no_longer_played_frees_the_group_after_a_while():
    mira, thora = introduced()
    group = group_of(mira)
    assert mira.eval(f'WoWStatusGoals.set("{group}", "level", "all", 10, 0)') is True
    mira.execute('WoWStatusPopups.characterName = function() return "Miraalt-TestRealm" end')
    assert mira.eval(f'WoWStatusGoals.blocked("{group}")') is not None
    clock(mira, 31 * 86400)
    assert mira.eval(f'WoWStatusGoals.blocked("{group}")') is None
    assert mira.eval(f'WoWStatusGoals.set("{group}", "quests", "sum", 500, 0)') is True


def test_a_deadline_passed_while_away_waits_for_the_login_sync():
    mira, thora = introduced()
    group = group_of(thora)
    pid = mira.eval('WoWStatusDB.roster.id')
    assert receive(thora, f'A {group} {pid} {NOW} deaths sum 2 {NOW + 86400}') is True
    clock(thora, 2 * 86400)
    thora.execute(f'''
        local settle = WoWStatusGoals.SETTLE
        WoWStatusGoals.SETTLE = 1e9  -- this session has only just started
        WoWStatusGoals.touch(); WoWStatusGoals.tick(5000)
        assert(WoWStatusGoals.outcome(WoWStatusGoals.get("{group}")) == "open")
        WoWStatusGoals.SETTLE = settle
        WoWStatusJournal.received({{sender="Mira-TestRealm", nonce="d1", kind="death", text="Died", at={NOW + 10}}})
        WoWStatusJournal.received({{sender="Mira-TestRealm", nonce="d2", kind="death", text="Died", at={NOW + 20}}})
        WoWStatusGoals.touch(); WoWStatusGoals.tick(5000 + WoWStatusGoals.NEWS_DELAY)
        assert(WoWStatusGoals.outcome(WoWStatusGoals.get("{group}")) == "missed")
    ''')


def test_bars_empty_as_deaths_come_and_one_known_player_is_never_full():
    mira, thora = introduced()
    group = group_of(thora)
    pid = mira.eval('WoWStatusDB.roster.id')
    assert receive(thora, f'A {group} {pid} {NOW} deaths sum 4 {NOW + 86400}') is True
    thora.execute(f'WoWStatusJournal.received({{sender="Mira-TestRealm", nonce="d1", kind="death", text="Died", at={NOW + 10}}})')
    goal = f'WoWStatusGoals.get("{group}")'
    assert thora.eval(f'WoWStatusGoals.fraction({goal}, WoWStatusGoals.progress("{group}"))') == 0.75
    thora.execute(f'{goal}.missed_at = {NOW}')
    assert thora.eval(f'WoWStatusGoals.fraction({goal}, WoWStatusGoals.progress("{group}"))') == 0
    lua = person('Bea', 'Bea')
    own = group_of(lua)
    lua.execute('character().roster_info.level = 10')
    assert lua.eval(f'WoWStatusGoals.set("{own}", "level", "all", 10, 0)') is True
    assert lua.eval(f'WoWStatusGoals.progress("{own}").fraction') == 0.5


def test_a_new_goal_is_always_stamped_after_the_kept_one():
    mira, thora = introduced()
    group = group_of(thora)
    pid = mira.eval('WoWStatusDB.roster.id')
    ahead = NOW + 200  # the other realm's clock runs ahead
    assert receive(thora, f'A {group} {pid} {ahead} quests sum 10 {ahead + 3600}') is True
    thora.execute(f'WoWStatusGoals.get("{group}").missed_at = {NOW}')
    assert thora.eval(f'WoWStatusGoals.set("{group}", "level", "all", 10, 0)') is True
    assert stored(thora).at == ahead + 1


def test_quest_goals_count_an_older_versions_logged_quest_milestone():
    mira, thora = introduced()
    group = group_of(thora)
    pid = mira.eval('WoWStatusDB.roster.id')
    assert receive(thora, f'C {group} {pid} Frank Mirabeta-TestRealm Dwarf 3 WARRIOR 30') is True
    thora.execute('''
        WoWStatusJournal.received({sender="Mirabeta-TestRealm", nonce="q1", kind="quest", text="Completed 300 quests!", at=1793000010})
    ''')
    assert receive(thora, f'A {group} {pid} {NOW + 20} quests sum 1000 0') is True
    assert thora.eval(f'WoWStatusGoals.progress("{group}").total') >= 300


def test_pages_reuse_the_last_progress_until_news_arrives():
    mira, thora = introduced()
    group = group_of(thora)
    pid = mira.eval('WoWStatusDB.roster.id')
    assert receive(thora, f'A {group} {pid} {NOW} level all 10 0') is True
    thora.execute(f'''
        local first = WoWStatusGoals.view("{group}")
        assert(WoWStatusGoals.view("{group}") == first)
        WoWStatusGoals.touch()
        assert(WoWStatusGoals.view("{group}") == first)  -- until the coming check
        WoWStatusGoals.tick(1e6)
        assert(WoWStatusGoals.view("{group}") ~= first)
    ''')


def test_round_three_fixes_hidden_setter_sharing_and_lone_deaths_goals():
    mira, thora = introduced()
    group = group_of(thora)
    pid = mira.eval('WoWStatusDB.roster.id')
    assert receive(thora, f'A {group} {pid} {NOW} level all 10 0') is True
    # The setter's character, hidden after the goal arrived, is no longer named.
    assert receive(thora, f'Z {group} {pid} Mira-TestRealm 1 1') is True
    thora.execute('WoWStatusDB.roster.players = {}')
    assert thora.eval(f'WoWStatusGoals.setBy(WoWStatusGoals.get("{group}"))') == 'a group member'
    # With list sharing off, no goal is set or sent.
    own = group_of(mira)
    mira.execute('WoWStatusRoster.setSharing(false)')
    assert mira.eval(f'WoWStatusGoals.blocked("{own}")') == 'Turn on sharing your character list to set a goal.'
    assert mira.eval(f'WoWStatusGoals.set("{own}", "level", "all", 10, 0)') is False
    # A deaths goal kept with only one player's numbers known is not reached.
    lua = person('Bea', 'Bea')
    alone = group_of(lua)
    assert lua.eval(f'WoWStatusGoals.set("{alone}", "deaths", "all", 3, 3)') is True
    clock(lua, 4 * 86400)
    lua.eval('WoWStatusGoals.check')()
    goal = f'WoWStatusGoals.get("{alone}")'
    assert lua.eval(f'WoWStatusGoals.outcome({goal})') == 'missed'
    assert lua.eval(f'WoWStatusGoals.status({goal})') == 'Not reached in time.'
