"""Diagnostics page (#153): the addon's own Lua errors, kept for bug reports.

The game's error handler, debugstack and BugGrabber are modelled here; how a live
client formats its paths and stacks needs a game client to confirm.
"""
from pathlib import Path

from test_addon import STUBS, lupa, make_lua, run_addon_file

ROOT = Path(__file__).parents[1]

HANDLER = '''
function methods:SetEnabled(value) self.enabled = value end
__shown = {}
__stack = ""
local function display(message) table.insert(__shown, message) end
local current = display
function geterrorhandler() return current end
function seterrorhandler(fn) current = fn end
function debugstack() return __stack end
-- Raise an error the way the game reports one: through the current handler.
function raise(message, stack) __stack = stack or ""; return geterrorhandler()(message) end
'''
OWN = 'Interface/AddOns/WoWStatus/Journal.lua:120: attempt to index field "entries" (a nil value)'
OWN_STACK = ('[string "@Interface/AddOns/WoWStatus/Diagnostics.lua"]:300: in function <...>\n'
             '[string "@Interface/AddOns/WoWStatus/Journal.lua"]:120: in function "insert"\n'
             '[string "@Interface/AddOns/WoWStatus/Popups.lua"]:900: in function "receive"\n'
             '[C]: in ?')
OTHER = 'Interface/AddOns/OtherAddon/Core.lua:5: attempt to call a nil value'


def diagnostics(stubs=STUBS + HANDLER):
    return make_lua(stubs)


def test_own_error_is_recorded_with_its_stack_and_still_reaches_the_display():
    lua = diagnostics()
    lua.execute(f'''
        WoWStatusMainWindow.show("activity")
        raise({OWN!r}, {OWN_STACK!r})
        assert(#__shown == 1 and __shown[1] == {OWN!r}) -- handed on unchanged
        local list = WoWStatusDB.diagnostics.errors
        assert(#list == 1)
        local e = list[1]
        assert(e.message == {OWN!r} and e.count == 1 and e.unseen)
        assert(e.stack:find("Journal.lua\\"]:120", 1, true) and e.stack:find("Popups.lua", 1, true))
        assert(not e.stack:find("Diagnostics.lua", 1, true)) -- the handler's own frames are left out
        assert(e.page == "activity" and e.edition == "Vanilla Classic (classic-era)")
        assert(e.build == "test build 12345 (interface 11507)" and e.at == 1793000000)
    ''')


def test_errors_from_other_addons_are_ignored_but_not_swallowed():
    lua = diagnostics()
    lua.execute(f'''
        raise({OTHER!r}, "Interface/AddOns/OtherAddon/Core.lua:5: in function <...>")
        assert(#__shown == 1 and __shown[1] == {OTHER!r})
        assert(#WoWStatusDiagnostics.errors() == 0)
        -- A game function failing on what we passed it: the first addon frame is ours.
        raise("Interface/AddOns/Blizzard_SharedXML/Util.lua:10: bad argument #1",
            "Interface/AddOns/Blizzard_SharedXML/Util.lua:10: in function\\n"
            .. "Interface/AddOns/WoWStatus/Theme.lua:44: in function <...>")
        assert(#WoWStatusDB.diagnostics.errors == 1)
        -- The same game function failing for another addon is not ours.
        raise("Interface/AddOns/Blizzard_SharedXML/Util.lua:11: bad argument #2",
            "Interface/AddOns/Blizzard_SharedXML/Util.lua:11: in function\\n"
            .. "Interface/AddOns/OtherAddon/Core.lua:5: in function <...>")
        assert(#WoWStatusDB.diagnostics.errors == 1 and #__shown == 3)
    ''')
    assert lua.eval('WoWStatusDiagnostics.ours("WoWStatus/Popups.lua:3: oops")') is True  # BugGrabber's short path
    assert lua.eval('WoWStatusDiagnostics.ours("WoWStatus_Voices/VoiceData.lua:3: oops")') is True
    assert lua.eval('WoWStatusDiagnostics.ours("Interface/AddOns/NotWoWStatus/X.lua:3: oops")') is False


def test_repeats_are_counted_and_only_the_last_ten_are_kept():
    lua = diagnostics()
    lua.execute(f'''
        for _ = 1, 50 do raise({OWN!r}, {OWN_STACK!r}) end -- an OnUpdate error, every frame
        assert(#WoWStatusDB.diagnostics.errors == 1 and WoWStatusDB.diagnostics.errors[1].count == 50)
        for i = 1, 12 do raise("Interface/AddOns/WoWStatus/Popups.lua:" .. i .. ": boom") end
        local list = WoWStatusDB.diagnostics.errors
        assert(#list == 10 and list[1].message:find("Popups.lua:12:", 1, true))
        -- An older error coming back moves to the top and keeps its count.
        raise("Interface/AddOns/WoWStatus/Popups.lua:5: boom")
        assert(list[1].message:find("Popups.lua:5:", 1, true) and list[1].count == 2 and #list == 10)
        assert(#__shown == 63)
    ''')


SERIALIZE = '''
function serialize(value)
    if type(value) == "table" then
        local parts = {}
        for k, v in pairs(value) do parts[#parts + 1] = "[" .. serialize(k) .. "]=" .. serialize(v) end
        return "{" .. table.concat(parts, ",") .. "}"
    elseif type(value) == "string" then return string.format("%q", value)
    else return tostring(value) end
end
'''


def test_errors_survive_a_reload():
    lua = diagnostics()
    lua.execute(SERIALIZE)
    lua.execute(f'raise({OWN!r}, {OWN_STACK!r})')
    saved = lua.eval('serialize(WoWStatusDB)')
    after = diagnostics((STUBS + HANDLER).replace('WoWStatusDB = nil', f'WoWStatusDB = {saved}'))
    after.execute(f'''
        local list = WoWStatusDiagnostics.errors()
        assert(#list == 1 and list[1].message == {OWN!r} and list[1].stack:find("Popups.lua", 1, true))
        assert(WoWStatusDiagnostics.report():find("attempt to index field", 1, true))
    ''')


def test_errors_before_saved_variables_load_are_kept():
    # In game an addon's files run before its SavedVariables are loaded.
    runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
    runtime.execute(STUBS + HANDLER)
    run_addon_file(runtime, ROOT / 'addon/vanilla/WoWStatus/Diagnostics.lua')
    runtime.execute('''
        raise("Interface/AddOns/WoWStatus/Locale.lua:3: early", "")
        assert(WoWStatusDB == nil and #WoWStatusDiagnostics.errors() == 1)
        WoWStatusDB = {version = 1, characters = {}}
        fire("ADDON_LOADED", "OtherAddon")
        assert(WoWStatusDB.diagnostics == nil)
        fire("ADDON_LOADED", "WoWStatus")
        assert(#WoWStatusDB.diagnostics.errors == 1)
        assert(WoWStatusDB.diagnostics.errors[1].message:find("early", 1, true))
    ''')


def test_bugGrabber_errors_arrive_through_its_callback():
    # BugGrabber keeps its own handler and makes seterrorhandler do nothing.
    stubs = STUBS + HANDLER + '''
        local grabbed = function(message) table.insert(__shown, message) end
        seterrorhandler(grabbed)
        seterrorhandler = function() end
        BugGrabber = {RegisterCallback = function(owner, event, fn) __grabber = {event = event, fn = fn} end}
        function grab(message, stack)
            grabbed(message)
            __grabber.fn("BugGrabber_BugGrabbed", {message = message, stack = stack, locals = "secret locals"})
        end
    '''
    lua = make_lua(stubs)
    lua.execute('fire("ADDON_LOADED", "WoWStatus")')
    assert lua.eval('__grabber.event') == 'BugGrabber_BugGrabbed'
    assert lua.eval('WoWStatusDiagnostics.chained()') is False
    lua.execute(f'''
        grab("WoWStatus/Journal.lua:120: attempt to index a nil value", "WoWStatus/Journal.lua:120: in function")
        grab({OTHER!r}, "")
        local list = WoWStatusDB.diagnostics.errors
        assert(#list == 1 and #__shown == 2 and not list[1].stack:find("locals", 1, true))
        assert(WoWStatusDiagnostics.report():find("Error capture: via BugGrabber", 1, true))
    ''')


def test_report_never_contains_group_or_other_players_names():
    lua = diagnostics()
    lua.eval('WoWStatusGroups.update')('Moonwell Secret\nsecond', '')
    lua.execute('''
        for id, label in pairs(WoWStatusDB.account_groups) do
            if label == "Moonwell Secret" then __id = id end
        end
        table.insert(WoWStatusDB.journal.entries, {id = "x:1", sender = "Eldrin-TestRealm", kind = "level",
            at = 1793000000, text = "Reached level 2!", groups = {}})
        local players = WoWStatusDB.roster.players
        players["0123456789abcdef"] = {characters = {["åsa"] = {name = "Åsa-TestRealm"}}}
    ''')
    group_id = lua.eval('__id')
    message = (f'Interface/AddOns/WoWStatus/Groups.lua:9: bad group "Moonwell Secret" moonwell secret '
               f'WStatus{group_id} {group_id} from Eldrin-TestRealm and Eldrin, Åsa, Thora')
    lua.execute(f'raise({message!r}, {OWN_STACK!r}); WoWStatusDiagnostics.show()')
    report = lua.eval('WoWStatusDiagnostics.report()')
    stored = lua.eval('WoWStatusDB.diagnostics.errors[1].message')
    shown = lua.eval('WoWStatusDiagnosticsPage.box.text')
    for text in (report, stored, shown):
        for secret in ('Moonwell', 'moonwell', group_id, 'Eldrin', 'Åsa', 'Thora', 'second'):
            assert secret not in text, (secret, text)
    assert 'bad group "<group>" <group> <group channel> <group> from <name> and <name>, <name>, <name>' in stored
    assert 'Groups joined: 2 - group channel joined: yes' in report
    # Group names joined after an error was stored are hidden in the report too.
    lua.execute('raise("Interface/AddOns/WoWStatus/Groups.lua:10: Later Crew", "")')
    lua.eval('WoWStatusGroups.update')('Later Crew', '')
    assert 'Later Crew' not in lua.eval('WoWStatusDiagnostics.report()')


def test_report_lists_the_numbers_bug_reports_ask_for():
    stubs = STUBS + HANDLER + '''
        function UpdateAddOnMemoryUsage() __updated = true end
        function GetAddOnMemoryUsage(name) assert(name == "WoWStatus"); return 2345.6 end
        C_AddOns = {GetAddOnMetadata = function(name, field) return "1.52.0" end}
    '''
    lua = make_lua(stubs)
    lua.execute('''
        table.insert(WoWStatusDB.journal.entries, {id = "x:1", sender = "Eldrin-TestRealm", kind = "level",
            at = 1793000000, text = "Reached level 2!", groups = {}})
        table.insert(WoWStatusDB.journal.entries, {id = "y:1", owner = "Player-123-0001", kind = "level",
            at = 1793000000, text = "Reached level 2!", groups = {}})
        WoWStatusDB.roster.equipment_cache = {a = {snapshot = {}}, b = {snapshot = {}}, c = {}}
    ''')
    report = lua.eval('WoWStatusDiagnostics.report()')
    assert report.startswith('WoW Status diagnostics\nAddon: 1.52.0 - Vanilla Classic (classic-era)\n')
    assert 'Memory: 2346 KB' in report
    assert 'Saved log: 1 own entries, 1 received' in report
    assert 'Cached gear snapshots: 2' in report
    assert 'Groups joined: 0 - group channel joined: no' in report
    assert 'Error capture: chained' in report
    assert 'Generated: 2026-10-26' in report
    assert report.endswith('No errors recorded.')


def test_page_opens_by_command_without_a_tab_and_clears():
    lua = diagnostics()
    lua.execute(f'''
        raise({OWN!r}, "Interface/AddOns/WoWStatus/Journal.lua:120: in function <x|y>")
        SlashCmdList.WOWSTATUS("errors")
        assert(WoWStatusMainWindow.active() == "diagnostics")
        local page = WoWStatusDiagnosticsPage
        assert(page:IsShown() and page:GetParent() == WoWStatusMainFrame.content)
        assert(page.status.text == "1 error recorded since you last looked.")
        assert(page.box.text:find("attempt to index field", 1, true))
        assert(page.box.text:find("<x||y>", 1, true)) -- escapes shown as text
        assert(page.box.multiline and page.clear.enabled ~= false)
        -- Typing does not change the report.
        page.box:SetText("typed"); page.box.OnTextChanged(page.box, true)
        assert(page.box.text:find("attempt to index field", 1, true))
        -- No tab, not remembered as the last page, not in the LB/RB cycle.
        for _, f in ipairs(__frames) do assert(not (f.parent == WoWStatusMainFrame and f.text == "Diagnostics")) end
        for _, key in ipairs(WoWStatusMainWindow.pages()) do assert(key ~= "diagnostics") end
        assert(WoWStatusDB.main_window.page ~= "diagnostics")
        SlashCmdList.WOWSTATUS("diagnostics")
        assert(page.status.text == "No new errors since you last looked.")
        page.clear.OnClick(page.clear)
        assert(#WoWStatusDB.diagnostics.errors == 0 and page.box.text:find("No errors recorded.", 1, true))
        assert(page.clear.enabled == false)
        WoWStatusMainWindow.show("activity")
        assert(not page:IsShown())
        -- Back returns to the diagnostics page.
        WoWStatusMainWindow.back()
        assert(WoWStatusMainWindow.active() == "diagnostics")
    ''')


def test_page_opens_from_the_options_and_before_the_character_is_ready():
    lua = diagnostics()
    lua.execute('''
        for _, f in ipairs(__frames) do
            if f.parent == WoWStatusSetup and f.text == "Diagnostics" then f.OnClick(f) end
        end
        assert(WoWStatusMainWindow.active() == "diagnostics")
    ''')
    waiting = STUBS.replace('function UnitGUID() return "Player-123-0001" end', 'function UnitGUID() return nil end')
    lua = make_lua(waiting + HANDLER)
    lua.execute('''
        SlashCmdList.WOWSTATUS("errors")
        assert(WoWStatusMainWindow.active() == "diagnostics" and WoWStatusDiagnosticsPage:IsShown())
    ''')


def test_page_shows_nynorsk_but_the_report_stays_english():
    lua = diagnostics()
    lua.execute(f'''
        WoWStatusLocale.set("nn")
        raise({OWN!r}, "")
        raise("Interface/AddOns/WoWStatus/Popups.lua:1: two", "")
        WoWStatusDiagnostics.show()
        local page = WoWStatusDiagnosticsPage
        assert(page.heading.text == "Diagnostikk" and page.select.text == "Merk alt")
        assert(page.status.text == "2 feil registrerte sidan du sist såg.")
        assert(page.box.text:find("WoW Status diagnostics", 1, true))
    ''')


def test_a_failing_capture_never_blocks_the_error_display():
    lua = diagnostics()
    lua.execute(f'''
        WoWStatusDiagnostics.capture = function() error("broken") end
        raise({OWN!r}, "")
        assert(#__shown == 1 and __shown[1] == {OWN!r})
    ''')


def test_early_errors_are_redacted_before_they_are_stored():
    runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
    runtime.execute(STUBS + HANDLER)
    run_addon_file(runtime, ROOT / 'addon/vanilla/WoWStatus/Diagnostics.lua')
    run_addon_file(runtime, ROOT / 'addon/vanilla/WoWStatus/Safe.lua')
    runtime.execute('''
        raise("Interface/AddOns/WoWStatus/Locale.lua:3: early from Eldrin-TestRealm", "")
        WoWStatusDB = {version = 1, characters = {}, account_groups = {abc = "Moonwell Secret"},
            journal = {entries = {{sender = "Eldrin-TestRealm"}}}}
        fire("ADDON_LOADED", "WoWStatus")
        raise("Interface/AddOns/WoWStatus/Locale.lua:3: early from Eldrin-TestRealm", "")
    ''')
    assert runtime.eval('#WoWStatusDB.diagnostics.errors') == 1
    assert runtime.eval('WoWStatusDB.diagnostics.errors[1].message') == \
        'Interface/AddOns/WoWStatus/Locale.lua:3: early from <name>'
    assert runtime.eval('WoWStatusDB.diagnostics.errors[1].count') == 2


def test_names_are_hidden_before_long_messages_are_cut():
    lua = diagnostics()
    lua.execute('''
        table.insert(WoWStatusDB.journal.entries, {id = "x:1", sender = "Aronsson-TestRealm", kind = "level",
            at = 1793000000, text = "Reached level 2!", groups = {}})
        raise("Interface/AddOns/WoWStatus/X.lua:1: " .. string.rep("x ", 290) .. "Aronsson", "")
    ''')
    assert 'Aro' not in lua.eval('WoWStatusDB.diagnostics.errors[1].message')


def test_names_that_are_words_or_file_names_keep_errors_readable():
    lua = diagnostics()
    lua.execute('''
        for _, sender in ipairs({"Value-TestRealm", "Groups-TestRealm"}) do
            table.insert(WoWStatusDB.journal.entries, {id = sender, sender = sender, kind = "level",
                at = 1793000000, text = "Reached level 2!", groups = {}})
        end
        raise("Interface/AddOns/WoWStatus/Groups.lua:12: attempt to index a nil value, Value said", "")
    ''')
    assert lua.eval('WoWStatusDB.diagnostics.errors[1].message') == \
        'Interface/AddOns/WoWStatus/Groups.lua:12: attempt to index a nil value, <name> said'


def test_bracketed_stack_frames_and_this_files_own_frames_count():
    lua = diagnostics()
    lua.execute('''
        raise("Interface/AddOns/Blizzard_SharedXML/Util.lua:10: bad argument #1",
            '[string "@Interface/AddOns/Blizzard_SharedXML/Util.lua"]:10: in function\\n'
            .. '[string "@Interface/AddOns/WoWStatus/Theme.lua"]:44: in function <...>')
        raise("Interface/AddOns/Blizzard_SharedXML/Util.lua:11: bad argument #1",
            '[Interface/AddOns/Blizzard_SharedXML/Util.lua]:11: in function\\n'
            .. '[Interface/AddOns/WoWStatus/Diagnostics.lua]:400: in function "render"')
        assert(#WoWStatusDB.diagnostics.errors == 2)
        assert(WoWStatusDB.diagnostics.errors[1].stack:find("Diagnostics.lua", 1, true))
    ''')


def test_errors_taking_turns_are_counted():
    lua = diagnostics()
    lua.execute('''
        for _ = 1, 20 do
            raise("Interface/AddOns/WoWStatus/A.lua:1: a", "")
            raise("Interface/AddOns/WoWStatus/B.lua:1: b", "")
        end
        local list = WoWStatusDB.diagnostics.errors
        assert(#list == 2 and list[1].count == 20 and list[2].count == 20)
        WoWStatusDiagnostics.clear()
        raise("Interface/AddOns/WoWStatus/A.lua:1: a", "")
        assert(#WoWStatusDB.diagnostics.errors == 1 and WoWStatusDB.diagnostics.errors[1].count == 1)
    ''')


def test_bugGrabber_listens_from_load_and_a_handler_on_top_is_reported():
    stubs = STUBS + HANDLER + '''
        seterrorhandler = function() end
        BugGrabber = {RegisterCallback = function(owner, event, fn) __grabber = fn end}
    '''
    runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
    runtime.execute(stubs)
    run_addon_file(runtime, ROOT / 'addon/vanilla/WoWStatus/Diagnostics.lua')
    runtime.execute('''
        __grabber("BugGrabber_BugGrabbed", {message = "WoWStatus/Popups.lua:1: during load", stack = ""})
        assert(#WoWStatusDiagnostics.errors() == 1)
    ''')
    lua = diagnostics()
    lua.execute('local ours = geterrorhandler(); seterrorhandler(function(...) return ours(...) end)')
    assert "Error capture: another addon's handler is on top" in lua.eval('WoWStatusDiagnostics.report()')
