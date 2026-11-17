"""Overview page with a "Since you were last here" summary (#58)."""
from test_addon import STUBS, make_lua

OVERVIEW = STUBS + '''
__now = 1793000000
function time() return __now end
function UnitXP() return 250 end
function UnitXPMax() return 1000 end
function friend(sender, kind, at, fields)
    __serial = (__serial or 0) + 1
    local item = {sender=sender, nonce="n" .. __serial, kind=kind, at=at}
    for k, v in pairs(fields or {}) do item[k] = v end
    WoWStatusJournal.received(item)
end
function overviewLines()
    local found = {}
    for _, row in ipairs(WoWStatusOverviewPage.rows) do table.insert(found, row.text) end
    return table.concat(found, "\\n")
end
'''



def test_summary_groups_by_player_and_kind_since_the_last_logout():
    lua = make_lua(OVERVIEW)
    lua.execute('''
        WoWStatusDB.overview = {since = 1000}
        friend("Bob-TestRealm", "level", 1500, {level=40})
        friend("Bob-TestRealm", "level", 1600, {level=41})
        friend("Bob-TestRealm", "level", 1700, {level=42})
        friend("Alice-TestRealm", "dungeon", 1650, {text="First clear: The Deadmines"})
        friend("Alice-TestRealm", "profession", 1660, {text="Learned Mining"})
        friend("Alice-TestRealm", "profession", 1670, {text="Learned Herbalism"})
        friend("Alice-TestRealm", "death", 1680, {text="Died"})
        friend("Old-TestRealm", "level", 900, {level=9})
        local summary = WoWStatusOverview.summary(WoWStatusJournal.entries(), 1000)
        assert(#summary == 2)
        assert(WoWStatusOverview.sentence(summary[1]) == "Bob gained 3 levels (now 42)")
        assert(WoWStatusOverview.sentence(summary[2]) == "Alice cleared The Deadmines, died once, 2 profession milestones")
    ''')


def test_page_shows_own_status_and_links_each_fact_to_its_log_entry():
    lua = make_lua(OVERVIEW)
    lua.execute('''
        WoWStatusDB.overview = {since = 1000}
        friend("Bob-TestRealm", "level", 1500, {level=40})
        for i = 1, 12 do friend("Spam-TestRealm", "zone", 1000 + i, {text="Discovered zone " .. i}) end
        SlashCmdList.WOWSTATUS("overview")
        assert(WoWStatusMainWindow.active() == "overview")
        local text = overviewLines()
        assert(text:find("Bob", 1, true) and text:find("reached level 40", 1, true))
        assert(WoWStatusOverviewPage.status.text == "You are level 1 · 25% of the way to level 2.")
        local link
        for _, row in ipairs(WoWStatusOverviewPage.list.lines) do
            if row.text.text:find("reached level 40", 1, true) then link = row end
        end
        assert(link and link.id)
        link.OnClick(link)
        assert(WoWStatusMainWindow.active() == "activity")
        local index
        for i, e in ipairs(WoWStatusActivityLog.entriesList) do if e.id == link.id then index = i end end
        assert(WoWStatusActivityLog.scroll.scroll == (index - 1) * 132)
    ''')


def test_own_entries_are_not_part_of_the_summary():
    lua = make_lua(OVERVIEW)
    lua.execute('''
        WoWStatusDB.overview = {since = 1}
        clickSharing()
        fire("PLAYER_LEVEL_UP", 10)
        assert(#WoWStatusOverview.summary(WoWStatusJournal.entries(), 1) == 0)
    ''')


def test_clear_empty_states():
    lua = make_lua(OVERVIEW)
    lua.execute('''
        SlashCmdList.WOWSTATUS("overview")
        assert(WoWStatusOverviewPage.empty.visible and WoWStatusOverviewPage.empty.text:find("next logout", 1, true))
        WoWStatusDB.overview.since = __now
        WoWStatusOverview.render()
        assert(WoWStatusOverviewPage.empty.visible and WoWStatusOverviewPage.empty.text:find("Nothing new", 1, true))
    ''')


def test_cut_off_moves_at_login_but_not_at_reload_and_includes_synced_entries():
    lua = make_lua(OVERVIEW)
    lua.execute('''
        -- First session: logout recorded.
        __now = 5000; fire("PLAYER_LOGOUT")
        assert(WoWStatusDB.overview.last_logout == 5000)
    ''')
    saved = lua.eval('WoWStatusDB')
    # Next login: a fresh runtime with the same saved variables.
    again = make_lua(OVERVIEW)
    again.globals().WoWStatusDB.overview = again.table_from({'last_logout': saved.overview.last_logout})
    again.execute('''
        -- make_lua already fired PLAYER_LOGIN; the first world entry is the login.
        fire("PLAYER_ENTERING_WORLD", true, false)
        assert(WoWStatusDB.overview.since == 5000)
        -- A catch-up entry recovered by login sync with an original time after logout.
        friend("Bob-TestRealm", "level", 6000, {level=30, origin="catchup"})
        assert(#WoWStatusOverview.summary(WoWStatusJournal.entries(), WoWStatusDB.overview.since) == 1)
        __now = 7000; fire("PLAYER_LOGOUT")
        fire("PLAYER_ENTERING_WORLD", false, false) -- zone change later in the same load
        assert(WoWStatusDB.overview.since == 5000)
    ''')
    reload = make_lua(OVERVIEW)
    reload.globals().WoWStatusDB.overview = reload.table_from({'last_logout': 7000, 'since': 5000})
    reload.execute('''
        fire("PLAYER_ENTERING_WORLD", false, true)
        assert(WoWStatusDB.overview.since == 5000)
    ''')


def test_the_truncation_line_is_translated_and_counts_what_it_left_out():
    """It was built from bare literals and stayed English on a Nynorsk client (#120)."""
    for language, expected, wrong in (
            ('en', '…and 3 more lines in the Activity tab.', 'fleire linjer'),
            ('nn', '…og 3 fleire linjer i Aktivitet-fana.', 'more lines')):
        lua = make_lua(OVERVIEW)
        lua.execute(f'''
            WoWStatusLocale.set("{language}")
            WoWStatusDB.overview = {{since = 1000}}
            -- 21 people, a heading and one fact each: 42 rows against a cap of 40.
            for i = 1, 21 do
                friend("P" .. i .. "-TestRealm", "level", 1500 + i, {{level = 20 + i}})
            end
            WoWStatusMainWindow.show("overview")
            local rows = WoWStatusOverviewPage.rows
            assert(#rows == 40, "expected the 40-row cap, got " .. #rows)
            assert(rows[40].text == "{expected}", rows[40].text)
            assert(not rows[40].text:find("{wrong}", 1, true), rows[40].text)
            assert(rows[40].id == nil, "the summary line links nowhere")
        ''')


# "Not seen for a while" (#172) ------------------------------------------------

DAY = 86400


def quiet_pair():
    """Thora holds Mira's shared list; Mira then logs off."""
    from test_roster import pair, pump
    mira, thora = pair()
    pump(mira, thora)
    thora.execute('''
        __peers = {"Thora-TestRealm"}
        for id in pairs(character().group_ids) do WoWStatusPopups.peers(id) end
        for _ = 1, 3 do WoWStatusPopups.tick() end
    ''')
    return mira, thora


def test_not_seen_rule_counts_days_caps_at_the_log_and_skips_online_and_unlisted():
    lua = make_lua(OVERVIEW)
    lua.execute(f'''
        local now = 100 * {DAY}
        local function player(name, rows, extra)
            local entry = {{name=name, rows=rows}}
            for k, v in pairs(extra or {{}}) do entry[k] = v end
            return entry
        end
        local groups = {{
            player("Thora", {{{{listed=true, groupIds={{g=true}}, status="last seen 12d ago", seen=now - 12 * {DAY} - 5}}}}),
            -- One character online: around, whatever the others say.
            player("Online", {{{{listed=true, groupIds={{g=true}}, status="online"}}, {{listed=true, groupIds={{g=true}}, status="x", seen=1}}}}),
            -- Quiet for longer than the log reaches back.
            player("Bran", {{{{listed=true, groupIds={{g=true}}, status="x", seen=now - 80 * {DAY}}}}}),
            player("Recent", {{{{listed=true, groupIds={{g=true}}, status="x", seen=now - 2 * {DAY}}}}}),
            -- Shares no character list.
            player("Not announced", {{{{status="x", seen=now - 50 * {DAY}}}}}),
            player("You", {{{{listed=true, groupIds={{g=true}}, status="offline", seen=1}}}}, {{self=true}}),
        }}
        local oldest = now - 31 * {DAY} - 7
        local list = WoWStatusOverview.notSeen(groups, now, 7, oldest)
        assert(#list == 2, #list)
        assert(list[1].player == "Bran" and list[1].days == 31 and list[1].more)
        assert(list[2].player == "Thora" and list[2].days == 12 and not list[2].more)
        assert(WoWStatusOverview.notSeenLine(list) == "Not seen for a while: Bran (more than 31 days), Thora (12 days)",
            WoWStatusOverview.notSeenLine(list))
        -- A higher threshold drops Thora; off lists nobody.
        assert(#WoWStatusOverview.notSeen(groups, now, 14, oldest) == 1)
        assert(#WoWStatusOverview.notSeen(groups, now, 0, oldest) == 0)
        -- With a log reaching back far enough, Bran's absence is exact.
        assert(WoWStatusOverview.notSeen(groups, now, 30, now - 200 * {DAY})[1].days == 80)
        -- A short log does not hide him: under the threshold, his own days stand.
        local short = WoWStatusOverview.notSeen(groups, now, 14, now - 10 * {DAY})
        assert(short[1].player == "Bran" and short[1].days == 80 and not short[1].more)
        -- No longer sharing a group you are in: left out.
        groups[3].rows[1].groupIds = {{}}
        assert(#WoWStatusOverview.notSeen(groups, now, 7, oldest) == 1)
        -- Lists without a player name stand alone, one per character.
        local unnamed = {{player("Unnamed player", {{
            {{name="Ann-Realm", listed=true, groupIds={{g=true}}, status="online"}},
            {{name="Ivo-Realm", listed=true, groupIds={{g=true}}, status="x", seen=now - 9 * {DAY}}}}})}}
        local alone = WoWStatusOverview.notSeen(unnamed, now, 7)
        assert(#alone == 1 and alone[1].player == "Ivo" and alone[1].days == 9)
    ''')


def test_not_seen_threshold_is_account_wide_with_a_conservative_default():
    lua = make_lua(OVERVIEW)
    lua.execute('''
        assert(WoWStatusOverview.notSeenDays() == 14 and WoWStatusDB.overview.not_seen_days == nil)
        assert(WoWStatusOverview.cycleNotSeenDays() == 30 and WoWStatusDB.overview.not_seen_days == 30)
        assert(WoWStatusOverview.cycleNotSeenDays() == 0 and WoWStatusOverview.notSeenLabel() == "Off")
        assert(WoWStatusOverview.cycleNotSeenDays() == 7)
        assert(WoWStatusOverview.cycleNotSeenDays() == 14 and WoWStatusDB.overview.not_seen_days == nil)
        assert(not WoWStatusOverview.setNotSeenDays(9) and WoWStatusOverview.notSeenDays() == 14)
        WoWStatusDB.overview.not_seen_days = "junk"
        assert(WoWStatusOverview.notSeenDays() == 14)
    ''')


def test_overview_shows_a_quiet_friend_and_sends_nothing():
    _, thora = quiet_pair()
    thora.execute(f'''
        __now = __now + 20 * {DAY}
        local before = #__sent
        SlashCmdList.WOWSTATUS("overview")
        local line = WoWStatusOverviewPage.group.notSeen.text
        assert(line == "Not seen for a while: Frank (20 days)", line)
        WoWStatusOverview.render(); WoWStatusOverview.render()
        assert(#__sent == before, "the not-seen line must never send anything")
        -- Off hides the line.
        WoWStatusOverview.setNotSeenDays(0); WoWStatusOverview.render()
        assert(WoWStatusOverviewPage.group.notSeen.text == "")
        -- Not yet quiet enough.
        WoWStatusOverview.setNotSeenDays(30); WoWStatusOverview.render()
        assert(WoWStatusOverviewPage.group.notSeen.text == "")
    ''')


def test_hidden_friends_are_not_listed_as_not_seen():
    _, thora = quiet_pair()
    thora.execute(f'''
        __now = __now + 20 * {DAY}
        WoWStatusMutes.setCharacter("Mira-TestRealm", "hide")
        SlashCmdList.WOWSTATUS("overview")
        assert(WoWStatusOverviewPage.group.notSeen.text == "", WoWStatusOverviewPage.group.notSeen.text)
    ''')


def test_not_seen_line_is_translated():
    lua = make_lua(OVERVIEW)
    lua.execute('''
        WoWStatusDB.language = "nn"
        local line = WoWStatusOverview.notSeenLine({{player="Bran", days=31, more=true}, {player="Thora", days=12}})
        assert(line == "Ikkje sett på ei stund: Bran (meir enn 31 dagar), Thora (12 dagar)", line)
        assert(WoWStatusOverview.notSeenLabel(14) == "14 dagar" and WoWStatusOverview.notSeenLabel(0) == "Av")
    ''')


def test_options_button_cycles_the_threshold_and_a_controller_reaches_it():
    lua = make_lua(OVERVIEW)
    lua.execute('''
        SlashCmdList.WOWSTATUS("")
        local b = WoWStatusSetup.notSeen
        assert(b and b.text == "14 days", b and b.text)
        b.OnClick(b)
        assert(b.text == "30 days" and WoWStatusDB.overview.not_seen_days == 30)
        assert(b.kind == "Button")
        -- The controller walk needs what these stubs leave out.
        local methods = getmetatable(b).__index
        function methods:GetObjectType() return self.kind end
        function methods:GetScript(name) return self[name] end
        function methods:GetChildren()
            local found = {}
            for _, f in ipairs(__frames) do if f.parent == self then table.insert(found, f) end end
            return (unpack or table.unpack)(found)
        end
        local shown = WoWStatusSetup
        while shown do shown.visible = true; shown = shown.parent end
        b.GetRect = function() return 400, 400, 180, 26 end
        local reached = false
        for _, control in ipairs(WoWStatusGamepad.controls(WoWStatusSetup, {WoWStatusSetup})) do
            if control == b then reached = true end
        end
        assert(reached, "a controller must reach the threshold button")
    ''')
