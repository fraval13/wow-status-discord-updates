"""Leaderboard as a main page, separate from Records, in all four editions."""
import pytest
from test_addon import make_lua
from test_client_compatibility import client_runtime
from test_main_window import WINDOW, tab


@pytest.mark.parametrize('edition', ['vanilla', 'forever', 'tbc', 'retail'])
@pytest.mark.parametrize('language', ['en', 'nn'])
def test_leaderboard_has_its_own_main_tab_and_navigation(edition, language):
    lua = client_runtime(edition)
    lua.execute(f'WoWStatusLocale.set("{language}")')
    lua.execute('''
        WoWStatusGroups.update("Example Crew", "")
        SlashCmdList.WOWSTATUS("records")
        assert(WoWStatusRecordsPage.viewBoard == nil)
        __questEvents = #character().events
    ''')
    button = tab(lua, 'Toppliste' if language == 'nn' else 'Leaderboard')
    assert button is not None and button.kind == 'Button' and button.OnClick is not None
    button.OnClick(button)
    lua.execute('''
        assert(WoWStatusMainWindow.active() == "leaderboard")
        assert(WoWStatusDB.main_window.page == "leaderboard")
        assert(WoWStatusLeaderboardPage:GetParent() == WoWStatusMainFrame.content)
        assert(WoWStatusLeaderboardPage.scroll.kind == "ScrollFrame")
        assert(not WoWStatusRecordsPage:IsShown())
        local crumbs=WoWStatusMainWindow.crumbs()
        assert(crumbs[#crumbs].label==WoWStatusLocale.T("Leaderboard"))
        assert(WoWStatusMainWindow.back())
        assert(WoWStatusMainWindow.active()=="records")
        SlashCmdList.WOWSTATUS("leaderboard")
        WoWStatusMainWindow.hide()
        WoWStatusMainWindow.show()
        assert(WoWStatusMainWindow.active()=="leaderboard")
        assert(#character().events==__questEvents)
    ''')


def test_group_and_sort_choices_move_from_records_and_remain_independent():
    lua = make_lua(WINDOW)
    lua.execute('''
        WoWStatusGroups.update("Example One\\nExample Two", "")
        local second=WoWStatusGroups.key("Example Two")
        WoWStatusDB.firsts.sort="quests"
        WoWStatusDB.firsts.tab=second
        WoWStatusDB.firsts.view="leaderboard"
        SlashCmdList.WOWSTATUS("leaderboard")
        local page=WoWStatusLeaderboardPage
        assert(page.group==second and page.sort.text=="Sort: Quests")
        assert(WoWStatusDB.leaderboard.sort=="quests")
        page.sort.OnClick(page.sort)
        assert(WoWStatusDB.leaderboard.sort=="level")
        local another
        for _, tab in ipairs(page.tabs) do if tab.group~=second then another=tab end end
        another.OnClick(another)
        assert(page.group~=second)
        local selected=page.group
        assert(WoWStatusDB.leaderboard.tab==selected)
        SlashCmdList.WOWSTATUS("records")
        assert(WoWStatusDB.firsts.view=="firsts") -- old embedded view no longer exists
        WoWStatusRecordsPage.viewWeek.OnClick()
        SlashCmdList.WOWSTATUS("leaderboard")
        assert(page.group==selected and page.sort.text=="Sort: Level")
        assert(WoWStatusDB.firsts.tab==second and WoWStatusDB.firsts.view=="week")
    ''')


def test_empty_leaderboard_disables_sort_and_does_not_keep_removed_group_tabs():
    lua = make_lua(WINDOW)
    lua.execute('''
        SlashCmdList.WOWSTATUS("leaderboard")
        local page=WoWStatusLeaderboardPage
        assert(page.sort.enabled==false and page.boardEmpty:IsShown())
        WoWStatusGroups.update("Example One\\nExample Two", "")
        WoWStatusLeaderboard.render()
        assert(page.sort.enabled and #page.tabs==2)
        WoWStatusGroups.update("", "")
        WoWStatusLeaderboard.render()
        assert(page.sort.enabled==false and page.group==nil and page.boardEmpty:IsShown())
        for _, tab in ipairs(page.tabs) do assert(not tab:IsShown()) end
    ''')
