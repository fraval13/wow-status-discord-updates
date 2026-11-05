"""First-time setup guide and 'Show me around' tour (#64)."""
from test_addon import STUBS, make_lua


def button(lua, text):
    return lua.eval(f'''(function()
        for _, f in ipairs(__frames) do
            if f.parent == WoWStatusGuideFrame and f.text == "{text}" and f.kind == "Button" then return f end
        end
    end)()''')


def test_guide_appears_once_on_a_new_account_and_can_be_skipped():
    lua = make_lua(guide=True)
    assert lua.eval('WoWStatusGuideFrame:IsShown()') is True
    assert lua.eval('WoWStatusSetup') is None  # The guide replaces the Options page.
    assert lua.eval('WoWStatusGuideFrame.progress.text') == 'Step 1 of 4'
    skip = button(lua, 'Skip')
    skip.OnClick(skip)
    assert lua.eval('WoWStatusGuideFrame:IsShown()') is False
    assert lua.eval('WoWStatusDB.guide_pending') is None
    assert lua.eval('WoWStatusGuide.check()') is False


def test_existing_accounts_never_see_the_guide():
    lua = make_lua(STUBS + 'WoWStatusDB = {version=1, characters={}}\n', guide=True)
    assert lua.eval('WoWStatusGuideFrame') is None


def test_steps_walk_through_groups_announcements_and_done():
    lua = make_lua(guide=True)
    lua.execute('''
        local frame = WoWStatusGuideFrame
        frame.next.OnClick(frame.next)
        assert(frame.title.text == "Choose or join a group" and frame.action.text == "Open Groups")
        frame.action.OnClick(frame.action)
        assert(WoWStatusGroupWindow:IsShown())
        frame.next.OnClick(frame.next)
        assert(frame.action.text == "Open announcement options")
        frame.next.OnClick(frame.next)
        assert(frame.next.text == "Done" and frame.action.text == "Show me around")
        frame.next.OnClick(frame.next)
        assert(not frame:IsShown() and WoWStatusDB.guide_pending == nil)
        SlashCmdList.WOWSTATUS("guide")
        assert(frame:IsShown() and frame.progress.text == "Step 1 of 4")
    ''')


def test_tour_shows_sample_data_that_is_never_saved_or_sent():
    lua = make_lua()
    lua.execute('''
        clickSharing()
        local sent, entries = #__sent, #WoWStatusDB.journal.entries
        WoWStatusGuide.tour()
        assert(WoWStatusMainWindow.active() == "overview")
        assert(WoWStatusMainFrame.title.text:find("sample tour", 1, true))
        local lines = {}
        for _, row in ipairs(WoWStatusOverviewPage.rows) do table.insert(lines, row.text) end
        local text = table.concat(lines, "\\n")
        assert(text:find("Brannic", 1, true) and text:find("gained 2 levels", 1, true))
        SlashCmdList.WOWSTATUS("activity")
        assert(#WoWStatusActivityLog.entriesList == 7)
        assert(WoWStatusActivityLog.rows[1].message.text:find("Brannic", 1, true))
        -- Nothing reaches the saved log or the network.
        assert(#WoWStatusDB.journal.entries == entries and #__sent == sent)
        for _, e in ipairs(WoWStatusJournal.entries()) do assert(not e.sample) end
        WoWStatusJournal.tick()
        assert(#__sent == sent)
        -- Closing the window ends the tour.
        WoWStatusMainFrame:Hide(); WoWStatusMainFrame.OnHide(WoWStatusMainFrame)
        assert(not WoWStatusGuide.touring())
        SlashCmdList.WOWSTATUS("activity")
        assert(#WoWStatusActivityLog.entriesList == 0)
        assert(not WoWStatusMainFrame.title.text:find("sample", 1, true))
    ''')


def test_options_page_reopens_the_guide_and_tour():
    lua = make_lua()
    lua.execute('''
        WoWStatusPreviews.show()
        local panel = WoWStatusNotificationPreviews
        panel.guide.OnClick(panel.guide)
        assert(WoWStatusGuideFrame:IsShown())
        panel.tour.OnClick(panel.tour)
        assert(WoWStatusGuide.touring() and not WoWStatusGuideFrame:IsShown())
    ''')
