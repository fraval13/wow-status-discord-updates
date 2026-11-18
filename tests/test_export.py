"""Local CSV export: privacy, current filters, bounded work and actual page actions."""
import csv
import io

import pytest
from test_addon import run_addon_file
from test_client_compatibility import client_runtime
from test_gamepad import FRAMES, ROOT, lupa, main_window
from test_journal import actor

UI = '''
local m=getmetatable(CreateFrame("Frame")).__index
function m:SetMultiLine(value) self.multiline=value end
function m:SetFontObject() end
function m:SetFocus() self.focused=true end
function m:HighlightText() self.highlighted=true end
function finishExport()
    for i=1,200 do
        WoWStatusExportWindow.OnUpdate()
        if not WoWStatusExportWindow.status.text:find("Preparing export:",1,true) then return end
    end
    error("export never finished")
end
'''


def runtime():
    lua = actor('Thora')
    lua.execute(UI)
    lua.execute('''
        local group=next(character().group_ids)
        items={
            {id="a",sender="Mira-TestRealm",kind="level",level=20,at=time(),groups={[group]=true},text="Reached level 20!"},
            {id="b",sender="Bob-TestRealm",kind="death",at=time()-60,groups={[group]=true},text="Died"},
            {id="c",sender="Thora-TestRealm",owner=character().identity.guid,kind="level",level=10,
                at=time()-86400,groups={[group]=true},text="Reached level 10!"},
        }
        for _,e in ipairs(items) do e.client=WoWStatusAdapter.client_id end
        WoWStatusDB.journal.entries=items
    ''')
    return lua


def rows(lua):
    return list(csv.reader(io.StringIO(lua.eval('WoWStatusExportWindow.text'))))


def open_activity(lua):
    lua.execute('''
        SlashCmdList.WOWSTATUS("activity")
        WoWStatusActivityLog.day=nil
        WoWStatusMainWindow.refresh("activity")
        WoWStatusActivityLog.export.OnClick()
        finishExport()
    ''')


@pytest.mark.parametrize(('scope', 'kind', 'person', 'expected'), [
    ('all', None, None, ['Mira-TestRealm', 'Bob-TestRealm', 'Thora-TestRealm']),
    ('mine', None, None, ['Thora-TestRealm']),
    ('friends', None, None, ['Mira-TestRealm', 'Bob-TestRealm']),
    ('all', 1, None, ['Mira-TestRealm', 'Thora-TestRealm']),
    ('all', None, 'bob-testrealm', ['Bob-TestRealm']),
])
def test_activity_exports_the_current_combination_of_filters(scope, kind, person, expected):
    lua = runtime()
    lua.execute('SlashCmdList.WOWSTATUS("activity"); WoWStatusActivityLog.day=nil')
    page = lua.globals().WoWStatusActivityLog
    page.filter, page.typeFilter, page.character = scope, kind, person
    lua.execute('WoWStatusMainWindow.refresh("activity"); WoWStatusActivityLog.export.OnClick(); finishExport()')
    assert [r[1] for r in rows(lua)[1:]] == expected
    assert rows(lua)[1][0].endswith('Z')


def test_default_today_filter_and_unknown_player_name():
    lua = runtime()
    lua.execute('SlashCmdList.WOWSTATUS("activity"); WoWStatusActivityLog.export.OnClick(); finishExport()')
    assert [r[1] for r in rows(lua)[1:]] == ['Mira-TestRealm', 'Bob-TestRealm']
    assert rows(lua)[1][2] == ''


def test_full_log_is_built_over_frames_and_every_row_can_be_copied():
    lua = runtime()
    lua.execute('''
        items={}
        for i=1,4000 do items[i]={id="row"..i,sender="Friend"..i.."-Realm",kind="zone",
            text="Visited Elwynn Forest for the first time!",at=time(),groups={}} end
        __visibleCalls=0
        WoWStatusJournal.visible=function() __visibleCalls=__visibleCalls+1;return true end
        WoWStatusExport.activity(items)
        WoWStatusExportWindow.OnUpdate()
        assert(__visibleCalls==32)
        assert(WoWStatusExportWindow.text=="")
        finishExport()
    ''')
    collected = []
    sizes = []
    while True:
        page = rows(lua)
        sizes.append(len(page) - 1)
        collected.extend(r[1] for r in page[1:])
        assert len(lua.eval('WoWStatusExportWindow.text').encode()) <= 32768
        if not lua.eval('WoWStatusExportWindow.next.enabled'):
            break
        lua.execute('WoWStatusExportWindow.next.OnClick()')
    assert max(sizes) <= 256
    assert collected == [f'Friend{i}-Realm' for i in range(1, 4001)]
    lua.execute('WoWStatusExportWindow.previous.OnClick()')
    assert lua.eval('WoWStatusExportWindow.next.enabled')


def test_export_is_local_read_only_and_cancel_discards_the_job():
    lua = runtime()
    lua.execute('sentBefore=#__sent; entriesBefore=#WoWStatusJournal.entries()')
    open_activity(lua)
    expected = lua.eval('WoWStatusExportWindow.text')
    lua.execute('''
        local f=WoWStatusExportWindow
        f.box.text="typed text"
        f.box.OnTextChanged(f.box,true)
        f.select.OnClick()
        assert(f.box.highlighted and f.box.focused)
        assert(#__sent==sentBefore and #WoWStatusJournal.entries()==entriesBefore)
        WoWStatusExport.activity(items)
        f.OnHide()
        for _=1,10 do f.OnUpdate() end
        assert(f.text=="" and not f.select.enabled)
    ''')
    assert expected.startswith('"Timestamp (UTC)"')
    assert lua.eval('WoWStatusExportWindow.box.multiline')


def test_csv_escapes_quotes_and_blocks_formulas_and_wow_markup():
    lua = runtime()
    lua.execute('''
        items[1].sender="=SUM(1,2)"
        items[1].text='|cffff0000A "quote", |Hitem:1|h[Hat]|h|r\\nNext\\tline'
        WoWStatusJournal.visible=function() return true end
        WoWStatusExport.activity({items[1]});finishExport()
    ''')
    row = rows(lua)[1]
    assert row[1] == "'=SUM(1,2)"
    assert row[4] == 'A "quote", [Hat] Next line'


@pytest.mark.parametrize('location', ['account', 'alt', 'listing', 'channel'])
def test_group_names_and_routing_ids_never_appear_even_inside_other_fields(location):
    lua = runtime()
    lua.globals().location = location
    lua.execute('''
        local name="Hemmeleg ÆØÅ"
        local id=WoWStatusGroups.key(name)
        if location=="account" then WoWStatusDB.account_groups[id]=name
        elseif location=="alt" then character().group_ids[id]={label=name}
        elseif location=="listing" then WoWStatusDB.roster.listings={[id]={name=name}}
        else WoWStatusDB.popups.joined_channels={[WoWStatusGroups.channel(id)]=true} end
        items[1].sender="Before HEMMELEG æøå After"
        items[1].text="Secret: "..id.." and "..WoWStatusGroups.channel(id)
        WoWStatusJournal.visible=function() return true end
        WoWStatusExport.activity({items[1]});finishExport()
    ''')
    text = lua.eval('WoWStatusExportWindow.text')
    assert 'Secret:' not in text
    if location != 'channel':
        assert 'HEMMELEG' not in text


def test_header_collision_fails_closed():
    lua = runtime()
    lua.execute('WoWStatusGroups.update("Timestamp","")')
    open_activity(lua)
    assert lua.eval('WoWStatusExportWindow.text') == ''
    assert lua.eval('WoWStatusExportWindow.status.text') == 'Cannot export safely with the current group names.'


def test_samples_and_entries_hidden_during_preparation_are_omitted():
    lua = runtime()
    lua.execute('''
        items[1].sample=true
        items[2].owner=character().identity.guid
        character().settings.collection.death=false
        WoWStatusExport.activity(items);finishExport()
    ''')
    assert [r[1] for r in rows(lua)[1:]] == ['Thora-TestRealm']


@pytest.mark.parametrize('view', ['firsts', 'week', 'fun'])
def test_records_export_uses_the_selected_group_view_and_week(view):
    lua = runtime()
    lua.globals().view = view
    lua.execute('''
        local group=next(character().group_ids)
        WoWStatusDB.firsts.view=view
        WoWStatusFirsts.week=function(id,offset)
            assert(id==group); exportedWeek=offset
            return {"Mira: 2 levels"},"2026-10-05","2026-10-11"
        end
        WoWStatusFirsts.funRecords=function(id) assert(id==group);return {"Richest: Mira — 100g"} end
        SlashCmdList.WOWSTATUS("records")
        WoWStatusRecordsPage.weekOffset=2
        WoWStatusRecordsPage.export.OnClick();finishExport()
    ''')
    exported = rows(lua)[1:]
    assert exported
    if view == 'week':
        assert lua.eval('exportedWeek') == 2
        assert exported[0][4:] == ['Mira: 2 levels', '2026-10-05', '2026-10-11']
    elif view == 'fun':
        assert exported[0][4] == 'Richest: Mira — 100g'
    else:
        assert any(r[4] == 'First to reach level 20' and r[1] == 'Mira-TestRealm' for r in exported)
    assert 'dawnwatch' not in lua.eval('WoWStatusExportWindow.text')


def test_records_cancel_if_group_removed_while_preparing():
    lua = runtime()
    lua.execute('''
        WoWStatusExport.records(next(character().group_ids),"firsts",0)
        WoWStatusDB.account_groups={};character().group_ids={}
        WoWStatusExportWindow.OnUpdate()
        assert(WoWStatusExportWindow.text=="")
        assert(WoWStatusExportWindow.status.text=="Export is no longer available.")
    ''')


@pytest.mark.parametrize('edition', ['vanilla', 'forever', 'tbc', 'retail'])
def test_translated_export_buttons_and_dialog_ship_in_every_edition(edition):
    lua = client_runtime(edition)
    lua.execute(UI)
    lua.execute('''
        WoWStatusGroups.update("dawnwatch","")
        WoWStatusLocale.set("nn")
        SlashCmdList.WOWSTATUS("activity")
        WoWStatusActivityLog.export.OnClick();finishExport()
        assert(WoWStatusExportWindow.title.text=="Kopier eksport")
        assert(WoWStatusExportWindow.warning.text:find("spelarnamn",1,true))
        assert(WoWStatusExportWindow.next.text=="Neste side")
    ''')


def test_export_controls_are_reached_by_gamepad_and_b_closes_without_combat_override():
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute('unpack=unpack or table.unpack')
    lua.execute(FRAMES)
    run_addon_file(lua, ROOT / 'addon/shared/Gamepad.lua')
    main_window(lua)
    lua.execute('''
        local m=getmetatable(CreateFrame("Frame")).__index
        function m:SetSize(w,h) self.rect[3],self.rect[4]=w,h end
        function m:CreateFontString() return CreateFrame("FontString",nil,self) end
        function m:SetText(t) self.text=t end
        function m:SetScrollChild(c) self.child=c end
        for _,n in ipairs({"SetJustifyH","SetMultiLine","SetAutoFocus","SetFontObject","SetMaxLetters"}) do m[n]=function() end end
        WoWStatusLocale={T=function(t) return t end,F=string.format}
        WoWStatusJournal={}
    ''')
    for name in ('Safe', 'CaseFold', 'Export'):
        run_addon_file(lua, ROOT / f'addon/shared/{name}.lua')
    lua.execute('''
        main:Hide()
        local f=WoWStatusExport.activity({})
        f.OnUpdate=f.scripts.OnUpdate
        f.OnUpdate()
        f.rect={100,100,740,520};f.scroll.rect={124,160,668,314};f.box.rect={124,160,650,314}
        f.select.rect={124,120,150,28};f.previous.rect={288,120,150,28}
        f.next.rect={450,120,150,28};f.close.rect={660,120,150,28}
        f.select:SetEnabled(true);f.previous:SetEnabled(true);f.next:SetEnabled(true)
        local reached={}
        for _,c in ipairs(WoWStatusGamepad.controls(f,{f})) do reached[c]=true end
        assert(reached[f.box] and reached[f.select] and reached[f.previous] and reached[f.next] and reached[f.close])
        WoWStatusGamepad.update();press("PAD2");assert(not f:IsShown())
        __combat=true
        WoWStatusExport.activity({});WoWStatusGamepad.update()
        assert(not anyBound())
    ''')


def test_actual_activity_and_records_export_buttons_are_gamepad_controls():
    lua = runtime()
    lua.execute('''
        local m=getmetatable(CreateFrame("Frame")).__index
        function m:GetObjectType() return self.kind end
        function m:GetParent() return self.parent end
        function m:GetChildren()
            local found={}
            for _,f in ipairs(__frames) do if f.parent==self then found[#found+1]=f end end
            return (unpack or table.unpack)(found)
        end
        function m:IsEnabled() return self.enabled~=false end
        function m:GetRect() return 100,100,50,24 end
        function m:GetEffectiveScale() return 1 end
        for _,key in ipairs({"activity","records"}) do
            SlashCmdList.WOWSTATUS(key)
            local page=key=="activity" and WoWStatusActivityLog or WoWStatusRecordsPage
            local reached=false
            -- Activity has entries; Records has the selected joined group.
            assert(page.export.enabled)
            for _,c in ipairs(WoWStatusGamepad.controls(WoWStatusMainFrame,{WoWStatusMainFrame})) do
                if c==page.export then reached=true end
            end
            assert(reached,key.." Export button is unreachable")
        end
    ''')


def test_record_holder_that_contains_a_group_name_is_removed():
    lua = runtime()
    lua.execute('''
        local group=next(character().group_ids)
        WoWStatusFirsts.compute=function()
            return {goal={at=time(),holder="dawnwatch goal",kind="goal"}},{{key="goal",title="Group goal reached"}}
        end
        WoWStatusExport.records(group,"firsts",0);finishExport()
    ''')
    assert rows(lua)[1][1] == ''
    assert rows(lua)[1][4] == 'Group goal reached'


def test_a_new_group_secret_blocks_an_already_built_page():
    lua = runtime()
    lua.execute('''
        WoWStatusJournal.visible=function() return true end
        items={}
        for i=1,300 do items[i]={sender="Mira-TestRealm",kind="zone",text="Entered Elwynn",at=time()} end
        WoWStatusExport.activity(items);finishExport()
        WoWStatusGroups.update("Mira","")
        WoWStatusExportWindow.next.OnClick()
        assert(WoWStatusExportWindow.text=="")
        assert(not WoWStatusExportWindow.select.enabled)
    ''')
