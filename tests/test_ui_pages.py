"""Main window pages: cards, level badges, XP bars, character filter and Forever names.

Mocked client APIs: these check behaviour and that every page draws, not the look
in a real client.
"""
import pytest
from test_client_compatibility import client_runtime
from test_roster import pair, pump


def test_friends_xp_arrives_and_shows_on_their_card():
    mira, thora = pair()
    mira.execute('function UnitXP() return 250 end function UnitXPMax() return 1000 end WoWStatusRoster.observe(character())')
    sent = pump(mira, thora)
    assert any(line.startswith('P ') and line.endswith(' 250') for line in sent)
    thora.eval('SlashCmdList.WOWSTATUS')('characters')
    cards = [thora.eval(f'WoWStatusCharactersPage.lines[{i}]') for i in range(1, thora.eval('WoWStatusCharactersPage.count') + 1)]
    mira_card = next(c for c in cards if 'Mira' in c.name.text)
    assert mira_card.xp.progress == 0.25 and mira_card.xp.label.text == 'XP 25%'


def test_clicking_a_character_shows_only_its_activity():
    mira, thora = pair()
    pump(mira, thora)
    thora.execute('''
        local group=next(character().group_ids)
        WoWStatusJournal.received({sender="Mira-TestRealm",nonce="1-1-aaaa",kind="level",level=5,at=time(),group_id=group})
        WoWStatusJournal.received({sender="Bob-TestRealm",nonce="1-2-bbbb",kind="level",level=6,at=time(),group_id=group})
        SlashCmdList.WOWSTATUS("characters")
        local card
        for i=1,WoWStatusCharactersPage.count do
            local c=WoWStatusCharactersPage.lines[i]
            if c.character and c.character.name=="Mira-TestRealm" then card=c end
        end
        card.OnClick(card)                   -- opens the profile
        WoWStatusProfileView.activity.OnClick(WoWStatusProfileView.activity)
        assert(WoWStatusMainWindow.active()=="activity")
        local list=WoWStatusActivityLog.entriesList
        assert(#list==1 and list[1].sender=="Mira-TestRealm")
        assert(WoWStatusActivityLog.showing.text:find("Mira",1,true) and WoWStatusActivityLog.showAll.visible)
        WoWStatusActivityLog.showAll.OnClick(WoWStatusActivityLog.showAll)
        assert(#WoWStatusActivityLog.entriesList==2)
    ''')


def test_cards_show_the_groups_you_share():
    mira, thora = pair()
    pump(mira, thora)
    rows = [r for g in thora.eval('WoWStatusRoster.groups()').values() for r in g.rows.values()]
    mira_row = next(r for r in rows if r.name == 'Mira-TestRealm')
    assert list(mira_row.groups.values()) == ['dawnwatch']


@pytest.mark.parametrize('edition', ['vanilla', 'forever', 'tbc', 'retail'])
def test_every_page_draws_on_every_edition(edition):
    lua = client_runtime(edition)
    lua.execute('''
        WoWStatusGroups.update("dawnwatch","")
        for _,key in ipairs({"overview","activity","records","characters"}) do
            assert(WoWStatusMainWindow.show(key))
        end
        assert(#WoWStatusRecordsPage.rows==#WoWStatusFirsts.medals())
        -- Nobody has died yet: that card is grey. (Level records can already be held:
        -- the simulated characters reached those levels before WoW Status.)
        local death
        for _, row in ipairs(WoWStatusRecordsPage.rows) do
            if row.text:find("to die", 1, true) then death = row end
        end
        assert(death.icon.path and death.icon.dimmed)
        assert(WoWStatusOverviewPage.you.badge.text.text~=nil)
        assert(WoWStatusOverviewPage.group.count.text:find("online",1,true))
        assert(WoWStatusOverviewPage.problem==nil, tostring(WoWStatusOverviewPage.problem))
    ''')


def test_overview_lists_everyone_online_and_fits_the_summary():
    from test_journal import actor
    lua = actor('Thora')
    lua.execute('''
        __peers={"Thora-TestRealm","Ann-TestRealm","Bob-TestRealm","Cid-TestRealm","Dee-TestRealm","Eve-TestRealm","Fay-TestRealm"}
        getmetatable(CreateFrame("Frame")).__index.SetHeight = function(self, h) self.height = h end
        WoWStatusDB.overview = {since = time() - 3600}
        local group = next(character().group_ids)
        WoWStatusJournal.received({sender="Ann-TestRealm",nonce="1-1-aaaa",kind="level",level=5,at=time(),group_id=group})
        WoWStatusMainWindow.show("overview")
        local page = WoWStatusOverviewPage
        local names = page.group.names.text
        for _, n in ipairs({"Ann","Bob","Cid","Dee","Eve","Fay"}) do assert(names:find(n, 1, true), n) end
        assert(not names:find("more", 1, true))
        -- Two summary lines: a compact box, not the full height.
        assert(#page.rows == 2 and page.since.height == 98, page.since.height)
        for i = 2, 30 do
            WoWStatusJournal.received({sender="Bob-TestRealm",nonce="2-"..i.."-bbbb",kind="death",text="Died",at=time(),group_id=group})
            WoWStatusJournal.received({sender="Cid"..i.."-TestRealm",nonce="3-"..i.."-cccc",kind="death",text="Died",at=time(),group_id=group})
        end
        WoWStatusMainWindow.show("overview")
        assert(page.since.height == 202)
    ''')


def test_activity_filters_by_type_and_person_combine():
    from test_journal import actor
    lua = actor('Thora')
    lua.execute('''
        local group = next(character().group_ids)
        local r = WoWStatusJournal.received
        r({sender="Mira-TestRealm",nonce="1-1-a",kind="level",level=5,at=time(),group_id=group})
        r({sender="Mira-TestRealm",nonce="1-2-b",kind="death",text="Died",at=time(),group_id=group})
        r({sender="Bob-TestRealm",nonce="1-3-c",kind="death",text="Died",at=time(),group_id=group})
        WoWStatusJournal.show()
        local log = WoWStatusActivityLog
        assert(#log.entriesList == 3)
        -- Type: Deaths
        log.typeButton.OnClick(log.typeButton)
        local menu = WoWStatusMenu
        local deaths
        for _, row in ipairs(menu.rows) do if row.text.text == "Deaths" then deaths = row end end
        deaths.OnClick(deaths)
        assert(#log.entriesList == 2 and log.typeButton.text == "Type: Deaths")
        -- Person: Mira, combined with the type
        log.personButton.OnClick(log.personButton)
        local mira
        for _, row in ipairs(menu.rows) do if row:IsShown() and row.text.text == "Mira" then mira = row end end
        mira.OnClick(mira)
        assert(#log.entriesList == 1 and log.entriesList[1].kind == "death" and log.entriesList[1].sender == "Mira-TestRealm")
        assert(log.showing.text:find("Deaths", 1, true) and log.showing.text:find("Mira", 1, true))
        log.showAll.OnClick(log.showAll)
        assert(#log.entriesList == 3 and log.typeButton.text == "Type: All")
    ''')


def test_calendar_dates_are_right():
    from test_journal import actor
    lua = actor('Thora')
    assert lua.eval('WoWStatusUI.weekday(2026, 11, 6)') == 5   # a Friday
    assert lua.eval('WoWStatusUI.weekday(2026, 11, 1)') == 7   # a Sunday
    assert lua.eval('WoWStatusUI.weekday(2024, 2, 29)') == 4   # leap day, a Thursday
    assert lua.eval('WoWStatusUI.daysIn(2024, 2)') == 29 and lua.eval('WoWStatusUI.daysIn(2100, 2)') == 28


def test_activity_log_opens_on_today_and_remembers_the_picked_day():
    from test_journal import actor
    lua = actor('Thora')
    lua.execute('''
        local group = next(character().group_ids)
        local r = WoWStatusJournal.received
        local now = S_now and S_now() or WoWStatusSafe.now()
        r({sender="Mira-TestRealm",nonce="1-1-a",kind="level",level=5,at=now,group_id=group})
        r({sender="Bob-TestRealm",nonce="1-2-b",kind="death",text="Died",at=now-2*86400,group_id=group})
        WoWStatusJournal.show()
        local log = WoWStatusActivityLog
        -- Today only, by default.
        assert(#log.entriesList == 1 and log.entriesList[1].sender == "Mira-TestRealm")
        assert(log.dayButton.text == "Today")
        -- The calendar marks both days in gold and picks the older one.
        log.dayButton.OnClick(log.dayButton)
        local cal = WoWStatusCalendar
        local older = WoWStatusHistory.oslo(now-2*86400):sub(1,10)
        local cell
        for _, c in ipairs(cal.cells) do if c.key == older then cell = c end end
        assert(cell.text.text:find("|cffffd100", 1, true))
        cell.OnClick(cell)
        assert(#log.entriesList == 1 and log.entriesList[1].sender == "Bob-TestRealm")
        assert(log.dayButton.text ~= "Today")
        -- Kept when the log is opened again (until /reload).
        WoWStatusJournal.show()
        assert(#log.entriesList == 1 and log.entriesList[1].sender == "Bob-TestRealm")
        -- All days.
        log.dayButton.OnClick(log.dayButton)
        cal.all.OnClick(cal.all)
        assert(#log.entriesList == 2 and log.dayButton.text == "All days")
        -- Back to today; a day without activity says so.
        log.dayButton.OnClick(log.dayButton)
        cal.today.OnClick(cal.today)
        assert(#log.entriesList == 1 and log.dayButton.text == "Today")
        -- A character's activity covers every day.
        WoWStatusJournal.showCharacter("Bob-TestRealm")
        assert(#log.entriesList == 1 and log.dayButton.text == "All days")
    ''')


def test_an_empty_today_says_so():
    from test_journal import actor
    lua = actor('Thora')
    lua.execute('''
        WoWStatusJournal.show()
        assert(WoWStatusActivityLog.empty.text == "Nothing yet today.")
    ''')


def test_groups_page_lists_and_browses_groups():
    from test_journal import actor
    lua = actor('Thora')
    lua.execute('''
        WoWStatusGroups.show()
        local panel = WoWStatusGroupWindow
        local row = panel.rows[1]
        assert(row:IsShown() and row.listed and not row.listed:GetChecked())
        row.listed:SetChecked(true); row.listed.OnClick(row.listed)
        assert(WoWStatusGroups.isListed(row.id))
        -- A friend's listing, joined from Browse groups.
        local id = WoWStatusGroups.key("Secret Garden")
        WoWStatusDB.roster.listings = {[id] = {name="Secret Garden", by={["0123456789abcdef"]={name="Frank", at=time()}}}}
        panel.browse.OnClick(panel.browse)
        local pick = WoWStatusMenu.rows[1]
        assert(pick.text.text:find("Secret Garden", 1, true) and pick.text.text:find("Frank", 1, true))
        pick.OnClick(pick)
        assert(WoWStatusGroups.contains(character(), id))
        assert(panel.rows[2]:IsShown())
    ''')


def test_settings_windows_opened_on_their_own_use_the_window_theme():
    from test_journal import actor
    lua = actor('Thora')
    lua.execute('''
        local methods = getmetatable(CreateFrame("Frame")).__index
        function methods:SetColorTexture(r, g, b, a) self.colour = {r, g, b, a} end
        local function same(texture)
            local r, g, b = WoWStatusTheme.colour()
            return texture.colour[1] == r and texture.colour[2] == g and texture.colour[3] == b
        end
        WoWStatusGroups.show()                    -- standalone, as in combat
        local groups = WoWStatusGroupWindow.background
        assert(groups:IsShown() ~= false and same(groups))
        WoWStatusPreviews.show()
        assert(same(WoWStatusNotificationPreviews.background))
        WoWStatusTheme.next()                     -- a theme change reaches them too
        assert(same(groups) and same(WoWStatusNotificationPreviews.background))
    ''')


def test_calendar_and_menus_draw_above_the_window():
    from test_journal import actor
    lua = actor('Thora')
    lua.execute('''
        local methods = getmetatable(CreateFrame("Frame")).__index
        function methods:SetFrameStrata(strata) self.strata = strata end
        WoWStatusJournal.show()
        local log = WoWStatusActivityLog
        log.dayButton.OnClick(log.dayButton)
        assert(WoWStatusCalendar.strata == "TOOLTIP")
        log.typeButton.OnClick(log.typeButton)
        assert(WoWStatusMenu.strata == "TOOLTIP")
    ''')


def test_day_button_names_the_day_in_either_language():
    from test_journal import actor
    lua = actor('Thora')
    lua.execute('''
        WoWStatusJournal.show()
        assert(WoWStatusActivityLog.dayButton.text == "Today")
        WoWStatusLocale.set("nn")
        WoWStatusJournal.show()
        assert(WoWStatusActivityLog.dayButton.text == "I dag")
    ''')


def test_log_card_lines_end_with_dots_instead_of_wrapping():
    from test_journal import actor
    lua = actor('Thora')
    lua.execute('''
        WoWStatusJournal.show()
        local row = WoWStatusActivityLog.rows[1]
        for _, key in ipairs({"heading", "message", "flavour", "detail"}) do assert(row[key].oneLine, key) end
    ''')


def test_hovering_a_log_card_shows_it_in_full_without_the_event_id():
    from test_journal import actor
    lua = actor('Thora')
    lua.execute('''
        __tip = {}
        GameTooltip = {SetOwner=function() __tip = {} end, SetText=function(_, t) __tip.title = t end,
            AddLine=function(_, t) table.insert(__tip, t) end, Show=function() end, Hide=function() end}
        local group = next(character().group_ids)
        WoWStatusJournal.received({sender="Mira-TestRealm",nonce="1-1-a",kind="death",text="Total deaths: 3",at=time(),group_id=group})
        WoWStatusJournal.show()
        local row = WoWStatusActivityLog.rows[1]
        row.OnEnter(row)
        assert(__tip.title == "Mira")
        local all = table.concat(__tip, "\\n")
        assert(all:find("Total deaths: 3", 1, true) and all:find(row.detail:GetText(), 1, true))
        assert(not all:find("Event ID", 1, true) and not all:find(row.entry.id, 1, true))
    ''')


def test_overview_names_current_gold_in_either_language():
    from test_journal import actor
    lua = actor('Thora')
    lua.execute('''
        function GetMoney() return 123456 end
        WoWStatusProgress.money(character())
        WoWStatusMainWindow.show("overview")
        local line = WoWStatusOverviewPage.you.stats2.text
        assert(line:find("^Current: 12"), line)
        WoWStatusLocale.set("nn")
        WoWStatusMainWindow.show("overview")
        line = WoWStatusOverviewPage.you.stats2.text
        assert(line:find("^Noverande: 12"), line)
    ''')


def test_an_overview_link_jumps_to_its_entry_through_any_filter():
    """A type or person filter left from earlier hid the wanted entry (#119)."""
    from test_journal import actor
    lua = actor('Thora')
    lua.execute('''
        local group = next(character().group_ids)
        local r = WoWStatusJournal.received
        r({sender="Mira-TestRealm",nonce="1-1-a",kind="level",level=5,at=time(),group_id=group})
        r({sender="Bob-TestRealm",nonce="1-3-c",kind="death",text="Died",at=time(),group_id=group})
        WoWStatusJournal.show()
        local log = WoWStatusActivityLog
        -- The player narrows the log to Type: Deaths and leaves it that way.
        log.typeButton.OnClick(log.typeButton)
        local deaths
        for _, row in ipairs(WoWStatusMenu.rows) do if row.text.text == "Deaths" then deaths = row end end
        deaths.OnClick(deaths)
        assert(#log.entriesList == 1, "the type filter is on")
        -- Then clicks the level-up line on the Overview.
        local target
        for _, e in ipairs(WoWStatusJournal.entries()) do if e.kind == "level" then target = e.id end end
        assert(WoWStatusJournal.focus(target), "focus found the entry")
        assert(#log.entriesList == 2, "every filter was cleared")
        assert(log.typeButton.text == "Type: All")
    ''')
