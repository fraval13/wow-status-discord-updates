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
