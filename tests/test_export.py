"""Copyable export of the activity log and records (#176).

The text is built inside the client and never sent anywhere; what a live client
does with Ctrl-C, and how the box renders, still needs the owner's check.
"""
from pathlib import Path

import pytest
from test_addon import lupa
from test_gamepad import FRAMES, main_window
from test_journal import actor, clock

ROOT = Path(__file__).parents[1]
GROUP = 'dawnwatch'


@pytest.fixture
def thora():
    lua = actor('Thora')
    for level in range(11, 16):
        clock(lua, level)
        lua.eval('fire')('PLAYER_LEVEL_UP', level)
    return lua


def built(lua):
    return lua.eval('WoWStatusExport.frame().built')


def test_the_log_export_opens_on_what_the_page_shows_and_names_no_group(thora):
    thora.eval('WoWStatusExport.showLog')('all')
    text = built(thora)
    assert 'Reached level 15!' in text and 'Reached level 11!' in text
    assert GROUP not in text
    # An ISO date first on every entry line, so it sorts and a sheet reads it.
    entries = [line for line in text.split('\n') if 'Reached level' in line]
    assert len(entries) == 5
    for line in entries:
        assert line[:10] == thora.eval('WoWStatusHistory.oslo(1793000011)')[:10]
        assert 'Thora' in line


def test_the_csv_export_has_a_header_row_and_quotes_commas(thora):
    thora.eval('WoWStatusExport.showLog')('all')
    thora.execute('WoWStatusExport.frame().format="csv"; WoWStatusExport.rebuild()')
    lines = built(thora).split('\n')
    assert lines[0] == 'date,time,character,player,kind,entry'
    assert all(line.count(',') >= 5 for line in lines[1:] if line)
    assert GROUP not in built(thora)
    # A comma or a quote in the text is quoted, not left to split the row.
    assert thora.eval('WoWStatusExport.logLine')(
        {'at': 1793000000, 'sender': 'Mira-TestRealm', 'kind': 'zone', 'text': 'Elwynn, the "Forest"'},
        'csv').endswith('"Elwynn, the ""Forest"""')


def test_the_records_export_names_no_group_and_is_shaped_for_a_chat_message(thora):
    thora.eval('WoWStatusExport.showRecords')(GROUP)
    text = built(thora)
    assert GROUP not in text
    assert 'Firsts' in text and 'This week' in text and 'Fun records' in text
    assert all(line.startswith('- ') for line in text.split('\n')
               if line.startswith('-'))


def test_scopes_take_the_filters_the_log_already_has(thora):
    assert thora.eval('#WoWStatusJournal.exportEntries("all")') == 5
    assert thora.eval('#WoWStatusJournal.exportEntries("week")') == 5
    # With the page open, "shown" follows the filters it has on screen.
    thora.eval('WoWStatusJournal.show')()
    assert thora.eval('#WoWStatusJournal.exportEntries("shown")') == 5
    thora.execute('for i, t in ipairs(WoWStatusJournal.TYPES) do '
                  'if t[2].death then WoWStatusActivityLog.typeFilter = i end end')
    assert thora.eval('#WoWStatusJournal.exportEntries("shown")') == 0
    assert thora.eval('#WoWStatusJournal.exportEntries("all")') == 5
    thora.execute('WoWStatusActivityLog.typeFilter = nil')
    # A level-up eight days old is outside "the last seven days" but inside "all".
    thora.execute('''
        local e = WoWStatusJournal.entries()[1]
        e.at = e.at - 8 * 86400
    ''')
    assert thora.eval('#WoWStatusJournal.exportEntries("all")') == 5
    assert thora.eval('#WoWStatusJournal.exportEntries("week")') == 4


def test_a_four_thousand_entry_log_is_built_in_bounded_chunks(thora):
    entries = thora.eval('''(function()
        local list = {}
        for i = 1, 4000 do
            list[i] = {at=1793000000 + i, sender="Mira-TestRealm", kind="level", text="Reached level 2!"}
        end
        return list
    end)()''')
    job = thora.eval('WoWStatusExport.begin')('log', entries, 'text', 'all')
    steps, seen = 0, 0
    while not thora.eval('WoWStatusExport.step')(job) :
        steps += 1
        done, total = thora.eval('WoWStatusExport.progress')(job)
        assert done - seen <= thora.eval('WoWStatusExport.CHUNK')
        seen, _ = done, total
        assert steps < 200, 'the build never finished'
    assert steps >= 4000 // thora.eval('WoWStatusExport.CHUNK') - 1
    text = thora.eval('WoWStatusExport.text')(job)
    assert len([line for line in text.split('\n') if 'Reached level 2!' in line]) == 4000


def test_colour_codes_and_item_links_are_left_out_of_the_text(thora):
    plain = thora.eval('WoWStatusExport.plain')
    assert plain('|cffa335ee|Hitem:12345|h[Krol Blade]|h|r') == '[Krol Blade]'
    assert plain('Sword || Shield') == 'Sword | Shield'
    assert plain('one\ntwo') == 'one two'


def test_the_box_puts_back_anything_typed_into_it(thora):
    thora.eval('WoWStatusExport.showLog')('all')
    text = built(thora)
    thora.execute('''
        local box = WoWStatusExport.frame().box
        box:SetText("I typed over it")
        box:GetScript("OnTextChanged")(box, true)
    ''')
    assert thora.eval('WoWStatusExport.frame().box:GetText()') == text


def test_the_export_window_is_reachable_with_a_controller():
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute('unpack = unpack or table.unpack')
    lua.execute(FRAMES)
    lua.execute((ROOT / 'addon/shared/Gamepad.lua').read_text(encoding='utf-8'))
    main_window(lua)
    lua.execute('''
        local methods=getmetatable(CreateFrame("Frame")).__index
        function methods:SetSize(w,h) self.rect[3],self.rect[4]=w,h end
        function methods:SetText(text) self.text=text end
        function methods:GetText() return self.text end
        function methods:CreateFontString() return CreateFrame("FontString",nil,self) end
        function methods:SetJustifyH() end
        function methods:SetShown(value) self.visible=value end
        function methods:SetScrollChild(child) self.child=child end
        function methods:SetMultiLine() end
        function methods:SetAutoFocus() end
        function methods:SetWidth(w) self.rect[3]=w end
        function methods:SetFontObject() end
        WoWStatusLocale={T=function(text) return text end,F=string.format}
        WoWStatusSafe={string=function(v) return type(v)=="string" and v~="" and v or nil end,
            number=function(v) return type(v)=="number" and v or nil end, lowerASCII=string.lower,
            now=function() return 1793000000 end}
        WoWStatusHistory={oslo=function() return "2026-11-18 20:14:00 +01:00" end}
        WoWStatusJournal={exportEntries=function() return {} end, deathText=function(e) return e.text end,
            entries=function() return {} end}
        WoWStatusUI={text=function(parent) return CreateFrame("FontString",nil,parent) end,
            mute=function() end, menu=function() end,
            call=function(object,method,...) local fn=object and object[method]
                if type(fn)=="function" then return pcall(fn,object,...) end return false end}
    ''')
    lua.execute((ROOT / 'addon/shared/Export.lua').read_text(encoding='utf-8'))
    lua.execute('''
        main:Hide()
        local frame=WoWStatusExport.showLog("all")
        frame.rect={100,100,620,480}
        frame.scopeButton.rect={124,420,264,26}
        frame.formatButton.rect={396,420,180,26}
        frame.selectAll.rect={124,160,140,26}
        frame.close.rect={552,160,140,26}
        frame.box.rect={124,200,528,286}
        local reached={}
        for _,control in ipairs(WoWStatusGamepad.controls(frame,{frame})) do reached[control]=true end
        assert(reached[frame.scopeButton], "scope button out of reach")
        assert(reached[frame.selectAll], "select all out of reach")
        assert(reached[frame.close], "close out of reach")
        assert(reached[frame.box], "the text box out of reach")
        WoWStatusGamepad.update()
        press("PADDDOWN")
        WoWStatusGamepad.setFocus(frame.close);press("PAD1")
        assert(not frame:IsShown())
    ''')
    assert 'WoWStatusExportWindow' in [lua.eval(f'UISpecialFrames[{i}]')
                                       for i in range(1, lua.eval('#UISpecialFrames') + 1)]


def test_the_window_is_translated_to_nynorsk(thora):
    thora.execute('WoWStatusLocale.set("nn")')
    thora.eval('WoWStatusExport.showLog')('all')
    frame = thora.eval('WoWStatusExport.frame()')
    assert frame.title.GetText(frame.title) == 'Eksporter aktivitetsloggen'
    assert 'Omfang:' in frame.scopeButton.GetText(frame.scopeButton)
    assert thora.eval('WoWStatusExport.frame().warning:GetText()').startswith('Denne teksten')
