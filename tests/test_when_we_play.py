"""When we play (#158): the group's weekly pattern, read from the log only.

The counts and the page's state are modelled here; how the shaded cells look and
how a real controller moves over them still needs the owner's live check.
"""
import time
from pathlib import Path

import pytest
from test_addon import lupa
from test_gamepad import FRAMES, main_window
from test_journal import actor, clock

ROOT = Path(__file__).parents[1]
# A Wednesday 20:00 UTC; the page reads local time, so the tests ask the client
# which weekday and block each timestamp falls in rather than assuming one.
BASE = 1793000000


def add_entries(lua, sender, times, owner=False):
    """Put entries straight into the log, as a sync would have."""
    lua.execute('''
        __add = function(sender, at, index, owner)
            local entries = WoWStatusJournal.entries()
            entries[#entries + 1] = {id="when:" .. sender .. ":" .. index, sender=sender,
                owner=owner and "guid" or nil, kind="level", level=2, at=at,
                text="Reached level 2!", groups={dawnwatch=true}, origin=owner and "mine" or "peer"}
        end
    ''')
    for index, at in enumerate(times):
        lua.eval('__add')(sender, at, index, owner)


@pytest.fixture
def lua():
    return actor('Thora')


def week(lua, at):
    """The weekday (1 = Monday) and block the client puts a timestamp in."""
    t = lua.eval('WoWStatusWhenWePlay.when')(at)
    return t['day'], t['block']


def rows(lua):
    result = lua.eval('WoWStatusWhenWePlay.data')()[0]
    return [result[i] for i in range(1, len(result) + 1)]


def test_a_steady_wednesday_evening_becomes_a_summary(lua):
    # Eight weeks of the same slot, at whatever weekday and block that is locally.
    at = BASE
    times = [at - 7 * 86400 * n for n in range(8)]
    add_entries(lua, 'Mira-TestRealm', times)
    clock(lua, 0)
    lua.execute(f'__now = {BASE}')
    day, block = week(lua, BASE)
    mira = [row for row in rows(lua) if 'Mira' in row['name']]
    assert len(mira) == 1
    row = mira[0]
    assert row['total'] == 8 and row['days'] == 8
    assert row['byDay'][day] == 8
    assert row['byBlock'][block] == 8
    summary = lua.eval('WoWStatusWhenWePlay.summary')(row)
    expected_day = lua.eval('WoWStatusWhenWePlay.DAYS')[day]
    assert summary.startswith(expected_day)
    assert lua.eval('WoWStatusWhenWePlay.blockText')(block) in summary


def test_a_sparse_row_says_not_enough_rather_than_never(lua):
    add_entries(lua, 'Kael-TestRealm', [BASE, BASE - 86400])
    lua.execute(f'__now = {BASE}')
    kael = [row for row in rows(lua) if 'Kael' in row['name']][0]
    assert lua.eval('WoWStatusWhenWePlay.enough')(kael) is False
    assert lua.eval('WoWStatusWhenWePlay.summary')(kael) is None


def test_the_detail_counts_the_weekdays_that_happened(lua):
    times = [BASE - 7 * 86400 * n for n in range(6)]
    add_entries(lua, 'Mira-TestRealm', times)
    lua.execute(f'__now = {BASE}')
    day, _ = week(lua, BASE)
    row = [r for r in rows(lua) if 'Mira' in r['name']][0]
    detail = lua.eval('WoWStatusWhenWePlay.dayDetail')(row, day)
    # Six of that weekday were seen, out of the weekdays the window covers.
    assert ': seen on 6 of the last ' in detail
    assert detail.startswith(lua.eval('WoWStatusWhenWePlay.DAY_PLURAL')[day])
    assert row['weekdays'][day] >= 6


def test_hidden_characters_and_muted_friends_are_left_out(lua):
    add_entries(lua, 'Mira-TestRealm', [BASE - 86400 * n for n in range(8)])
    add_entries(lua, 'Kael-TestRealm', [BASE - 86400 * n for n in range(8)])
    lua.execute(f'__now = {BASE}')
    # No shared player list here, so a row falls back to the character's own name.
    assert {r['name'] for r in rows(lua)} >= {'Mira', 'Kael'}
    assert lua.eval('WoWStatusMutes.setCharacter')('Kael-TestRealm', 'hide') is True
    names = {r['name'] for r in rows(lua)}
    assert 'Mira' in names and 'Kael' not in names


def test_opening_the_page_sends_nothing(lua):
    add_entries(lua, 'Mira-TestRealm', [BASE - 86400 * n for n in range(8)])
    lua.execute(f'__now = {BASE}')
    before = lua.eval('#__sent')
    lua.eval('WoWStatusWhenWePlay.show')()
    lua.eval('WoWStatusWhenWePlay.render')()
    assert lua.eval('#__sent') == before
    assert lua.eval('WoWStatusMainWindow.active()') == 'whenweplay'


def test_the_page_has_no_tab_of_its_own(lua):
    pages = lua.eval('WoWStatusMainWindow.pages()')
    assert 'whenweplay' not in [pages[i] for i in range(1, len(pages) + 1)]


def test_the_rows_are_reachable_with_a_controller():
    runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
    runtime.execute('unpack = unpack or table.unpack')
    runtime.execute(FRAMES)
    runtime.execute((ROOT / 'addon/shared/Gamepad.lua').read_text(encoding='utf-8'))
    main_window(runtime)
    runtime.execute('''
        local methods=getmetatable(CreateFrame("Frame")).__index
        function methods:SetSize(w,h) self.rect[3],self.rect[4]=w,h end
        function methods:SetText(text) self.text=text end
        function methods:CreateTexture() return {SetPoint=function() end, SetSize=function() end,
            SetColorTexture=function() end} end
        function methods:SetScrollChild(child) self.child=child end
        function methods:SetAllPoints() end
        function methods:SetShown(value) self.visible=value end
        function date(fmt, at)
            local day = math.floor(at / 86400)
            return string.format("%d %02d %04d-%02d-%02d", day % 7,
                math.floor((at % 86400) / 3600), 2026, 1 + day % 12, 1 + day % 28)
        end
        WoWStatusLocale={T=function(text) return text end,F=string.format}
        WoWStatusSafe={string=function(v) return type(v)=="string" and v~="" and v or nil end,
            number=function(v) return type(v)=="number" and v or nil end,
            now=function() return 1793000000 end}
        WoWStatusHistory={oslo=function() return "2026-11-18 20:14:00 +01:00" end}
        WoWStatusRoster={playerOf=function() return nil end, key=string.lower, hiddenNames=function() return {} end}
        WoWStatusJournal={visible=function() return true end, entries=function()
            local list={}
            for i=1,10 do list[i]={id="e"..i, sender="Mira-TestRealm", at=1793000000-i*86400, kind="level"} end
            return list
        end}
        WoWStatusUI={text=function(parent) return CreateFrame("FontString",nil,parent) end,
            MUTED_CODE="|cff9d9d9d"}
        __registered=nil
        WoWStatusMainWindow.register=function(key,title,build,refresh,options)
            __registered={key=key,title=title,build=build,refresh=refresh,options=options}
            return true
        end
    ''')
    runtime.execute((ROOT / 'addon/shared/WhenWePlay.lua').read_text(encoding='utf-8'))
    runtime.execute('''
        assert(__registered.options.tab == false, "the page must not take a tab")
        local page = __registered.build(main)
        page.rect = {100, 100, 780, 540}
        WoWStatusWhenWePlay.render()
        local row = page.rows[1]
        assert(row, "no player row was drawn")
        row.rect = {120, 400, 680, 46}
        local reached = false
        for _, control in ipairs(WoWStatusGamepad.controls(page, {page})) do
            if control == row then reached = true end
        end
        assert(reached, "the player row is out of the controller's reach")
        row:GetScript("OnClick")(row)
        assert(page.open == row.id, "clicking a row does not open its hours")
        row:GetScript("OnClick")(row)
        assert(page.open == nil, "clicking again does not close it")
    ''')


def test_the_page_is_translated_to_nynorsk(lua):
    add_entries(lua, 'Mira-TestRealm', [BASE - 86400 * n for n in range(8)])
    lua.execute(f'__now = {BASE}')
    lua.execute('WoWStatusLocale.set("nn")')
    lua.eval('WoWStatusWhenWePlay.show')()
    assert lua.eval('WoWStatusWhenWePlayPage.heading:GetText()') == 'Når vi spelar'
    assert lua.eval('WoWStatusWhenWePlayPage.note:GetText()').startswith('Bygd berre')
    row = [r for r in rows(lua) if 'Mira' in r['name']][0]
    day = next(d for d in range(1, 8) if row['byDay'][d] > 0)
    assert ': sedd ' in lua.eval('WoWStatusWhenWePlay.dayDetail')(row, day)


def test_the_window_covers_only_as_far_back_as_the_log(lua):
    # An entry a year old still gives a bounded calendar, not a year-long loop.
    add_entries(lua, 'Mira-TestRealm', [BASE - 500 * 86400, BASE])
    lua.execute(f'__now = {BASE}')
    started = time.monotonic()
    row = [r for r in rows(lua) if 'Mira' in r['name']][0]
    assert time.monotonic() - started < 2
    total = sum(row['weekdays'][d] for d in range(1, 8))
    assert total <= lua.eval('WoWStatusWhenWePlay.MAX_WINDOW_DAYS')
