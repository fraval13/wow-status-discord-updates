"""Main window with tabbed pages (#57)."""
from test_addon import STUBS, make_lua

WINDOW = STUBS + '''
function methods:SetEnabled(value) self.enabled=value end
function methods:GetPoint() return self.point or "CENTER", UIParent, self.relative or "CENTER", self.x or 0, self.y or 0 end
function methods:SetPoint(point, a, b, c, d)
    if type(a) == "table" then self.point, self.relative, self.x, self.y = point, b, c, d end
end
'''


def tab(lua, title):
    return lua.eval(f'''(function()
        for _, f in ipairs(__frames) do
            if f.parent == WoWStatusMainFrame and f.text == "{title}" then return f end
        end
    end)()''')


def test_activity_log_lives_in_the_activity_tab():
    lua = make_lua(WINDOW)
    lua.execute('''
        SlashCmdList.WOWSTATUS("activity")
        assert(WoWStatusMainFrame:IsShown())
        assert(WoWStatusActivityLog:IsShown() and WoWStatusActivityLog:GetParent() == WoWStatusMainFrame.content)
        assert(WoWStatusMainWindow.active() == "activity")
        assert(#WoWStatusActivityLog.rows == 6)
    ''')
    assert tab(lua, 'Activity') is not None
    assert tab(lua, 'Activity').enabled is False


def test_new_pages_register_without_changing_the_frame_code():
    lua = make_lua(WINDOW)
    lua.execute('''
        __built, __refreshed = 0, 0
        assert(WoWStatusMainWindow.register("records", "Records",
            function(parent) __built = __built + 1; local f = CreateFrame("Frame", nil, parent); return f end,
            function(frame) __refreshed = __refreshed + 1 end))
        assert(not WoWStatusMainWindow.register("records", "Again"))
        SlashCmdList.WOWSTATUS("records")
        assert(WoWStatusMainWindow.active() == "records" and __built == 1 and __refreshed == 1)
        assert(not WoWStatusActivityLog or not WoWStatusActivityLog:IsShown())
        SlashCmdList.WOWSTATUS("activity")
        SlashCmdList.WOWSTATUS("records")
        assert(__built == 1 and __refreshed == 2)
        WoWStatusMainWindow.refresh("records")
        assert(__refreshed == 3)
        WoWStatusMainWindow.refresh("activity")
        assert(__refreshed == 3)
    ''')
    assert tab(lua, 'Records') is not None


def test_tabs_switch_pages_and_the_last_page_is_remembered():
    lua = make_lua(WINDOW)
    lua.execute('''
        WoWStatusMainWindow.register("records", "Records", function(parent) return CreateFrame("Frame", nil, parent) end)
        WoWStatusJournal.show()
    ''')
    records = tab(lua, 'Records')
    records.OnClick(records)
    assert lua.eval('WoWStatusMainWindow.active()') == 'records'
    assert lua.eval('WoWStatusActivityLog:IsShown()') is False
    assert lua.eval('WoWStatusDB.main_window.page') == 'records'
    lua.execute('WoWStatusMainWindow.hide(); WoWStatusMainWindow.show()')
    assert lua.eval('WoWStatusMainWindow.active()') == 'records'


def test_window_position_is_saved_and_restored():
    lua = make_lua(WINDOW)
    lua.execute('''
        WoWStatusJournal.show()
        local w = WoWStatusMainFrame
        w.point, w.relative, w.x, w.y = "TOPLEFT", "TOPLEFT", 120, -80
        w.OnDragStop(w)
        local p = WoWStatusDB.main_window.position
        assert(p.point == "TOPLEFT" and p.x == 120 and p.y == -80)
    ''')
    other = make_lua(WINDOW + 'WoWStatusDB = nil\n')
    other.globals().WoWStatusDB.main_window = other.table_from({'position': other.table_from(
        {'point': 'TOPLEFT', 'relative': 'TOPLEFT', 'x': 120, 'y': -80})})
    other.execute('WoWStatusJournal.show()')
    assert other.eval('WoWStatusMainFrame.x') == 120


def test_unknown_page_command_still_opens_options():
    lua = make_lua(WINDOW)
    lua.execute('SlashCmdList.WOWSTATUS("nonsense")')
    assert lua.eval('WoWStatusMainFrame') is None
