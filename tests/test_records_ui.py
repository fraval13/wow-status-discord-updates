"""Records selectors and wrapped layouts, with synthetic names and mocked fonts."""
import pytest
from test_client_compatibility import client_runtime
from test_week import with_entries


@pytest.mark.parametrize('edition', ['vanilla', 'forever', 'tbc', 'retail'])
@pytest.mark.parametrize('language', ['en', 'nn'])
def test_records_dropdowns_keep_group_view_dates_and_export_together(edition, language):
    lua = client_runtime(edition)
    lua.eval('WoWStatusGroups.update')('Example Alpha\nExample Beta', '')
    lua.eval('WoWStatusLocale.set')(language)
    lua.execute('''
        WoWStatusMainWindow.show("records")
        local p = WoWStatusRecordsPage
        local sent = #__sent
        assert(p.tabs == nil and p.viewWeek == nil and p.viewFun == nil)
        p.pick.OnClick(p.pick)
        local menu = WoWStatusMenu
        assert(#menu.items == 2)
        local second = menu.rows[2].value
        menu.rows[2].OnClick(menu.rows[2])
        assert(p.group == second and WoWStatusDB.firsts.tab == second)
        p.view.OnClick(p.view)
        assert(#menu.items == 3 and menu.items[2].value == "week")
        menu.rows[2].OnClick(menu.rows[2])
        assert(WoWStatusDB.firsts.view == "week" and p.weekly:IsShown())
        assert(p.dates:GetText():find("%d%d%d%d%-%d%d%-%d%d"))
        assert(not p.weekNext:IsEnabled() and p.weekBack:IsShown())
        p.weekBack.OnClick(p.weekBack)
        assert(p.weekOffset == 1 and p.weekNext:IsEnabled())
        local expected = p.dates:GetText()
        local exported
        WoWStatusExport.records = function(group, view, offset) exported={group,view,offset} end
        p.export.OnClick(p.export)
        assert(exported[1] == second and exported[2] == "week" and exported[3] == 1)
        assert(#__sent == sent)
        WoWStatusFirsts.render()
        assert(p.dates:GetText() == expected)
        p.view.OnClick(p.view); menu.rows[3].OnClick(menu.rows[3])
        assert(not p.weekly:IsShown() and not p.weekBack:IsShown() and p.dates:GetText() == "")
        assert(p.textRows[1]:IsShown())
        WoWStatusGroups.update("", "")
        WoWStatusFirsts.render()
        assert(not p.pick:IsEnabled() and not p.view:IsEnabled() and not p.export:IsEnabled())
        for _,row in ipairs(p.textRows) do assert(not row:IsShown()) end
    ''')


def test_weekly_table_counts_milestones_and_leaves_out_empty_people():
    lua = client_runtime('vanilla')
    lua.eval('WoWStatusGroups.update')('Example weekly table', '')
    with_entries(lua, [
        ('Mira-TestRealm', 'level-one', 'level', 50, '{level=20}'),
        ('Mira-TestRealm', 'quest-one', 'quest', 40, '{text="Completed 100 quests!"}'),
        ('Bob-TestRealm', 'death-one', 'death', 30, None),
        ('Blank-TestRealm', 'intro-only', 'introduction', 20, '{text="Joined the WoW Status group"}'),
    ])
    lua.execute('''
        local group = next(character().group_ids)
        local report = WoWStatusFirsts.weekData(group, 0)
        assert(#report.people == 2 and #report.highlights == 2)
        assert(report.people[1].name == "Mira" and report.people[1].quest == 1)
        WoWStatusDB.firsts.view = "week"
        WoWStatusMainWindow.show("records")
        local p = WoWStatusRecordsPage
        assert(p.weekly.rows[1].cells[1]:GetText() == "Mira")
        assert(p.weekly.rows[1].cells[2]:GetText() == "+1")
        assert(p.weekly.rows[1].cells[6]:GetText() == "100")
        assert(p.weekly.rows[2].cells[1]:GetText() == "Bob")
        assert(p.weekly.rows[2].cells[3]:GetText() == "1")
        assert(p.weekly.headers[6]:GetText() == "Quests")
        local lines = WoWStatusFirsts.week(group, 0)
        for _,line in ipairs(lines) do assert(not line:find("Blank", 1, true)) end
    ''')


def test_wrapped_names_and_fun_records_reserve_their_rendered_height():
    lua = client_runtime('vanilla')
    lua.eval('WoWStatusGroups.update')('Example wrapping', '')
    lua.execute('''
        local methods = getmetatable(CreateFrame("Frame")).__index
        function methods:SetPoint(...) self.point={...} end
        function methods:GetStringHeight() return self.text and self.text:find("Long", 1, true) and 60 or 14 end
        WoWStatusDB.firsts.view = "week"
        WoWStatusFirsts.weekData = function() return {
            first="2026-11-16", last="2026-11-22", highlights={}, extras={}, people={
                {name="Long Synthetic Character Name",level=1,death=0,zone=0,loot=0,quest=0},
                {name="Mira",level=0,death=1,zone=0,loot=0,quest=0}}} end
        WoWStatusMainWindow.show("records")
        local p = WoWStatusRecordsPage
        local first, second = p.weekly.rows[1], p.weekly.rows[2]
        assert(first.height >= 76 and first.point[3] - second.point[3] >= first.height)
        WoWStatusFirsts.funRecords = function() return {"Long wrapped record", "Next record"} end
        p.view.OnClick(p.view); WoWStatusMenu.rows[3].OnClick(WoWStatusMenu.rows[3])
        assert(p.textRows[1].point[3] - p.textRows[2].point[3] >= 60)
        assert(p.list.height >= 94)
    ''')


def test_native_button_label_is_bounded_for_long_localized_text():
    lua = client_runtime('vanilla')
    lua.execute('''
        local methods = getmetatable(CreateFrame("Frame")).__index
        function methods:GetFontString() return self.label end
        function methods:SetWordWrap(value) self.wrap=value end
        function methods:SetMaxLines(value) self.lines=value end
        function methods:GetHeight() return self.height end
        local b = CreateFrame("Button")
        b:SetSize(256, 28); b.label=b:CreateFontString()
        WoWStatusUI.buttonLabel(b, "Vis: Morosame rekordar")
        assert(b.label.width <= 232 and b.label.height <= 22)
        assert(b.label.wrap == false and b.label.lines == 1)
        assert(b.fullLabel == "Vis: Morosame rekordar")
    ''')
