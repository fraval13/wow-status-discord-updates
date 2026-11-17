"""One clock (issue #229).

Only Safe.lua reads time(), this PC's clock. Everything stored or shared uses
realm time (S.now()), short in-memory timers use game uptime (S.uptime()), and
the player's local wall clock is read through S.localNow(). Mocked API only.
"""
import re
from pathlib import Path

from test_clock_skew import REALM, pc

ROOT = Path(__file__).resolve().parents[1]
# The global `time` as a call or a value (pcall(time), local t = time), but not
# a field (x.time, x:time()), a key (time=) or a longer name (playtime).
BARE_TIME = re.compile(r'(?<![\w.:])time\b(?!\s*=[^=])')
LONG = re.compile(r'(?:--)?\[(=*)\[.*?\]\1\]', re.S)


def code_lines(path):
    """Lines of Lua with comments and string literals blanked out. Long
    comments and long strings keep their newlines, so line numbers hold."""
    text = path.read_text(encoding='utf-8')
    text = LONG.sub(lambda m: '\n' * m.group(0).count('\n'), text)
    for number, line in enumerate(text.splitlines(), 1):
        line = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', '""', line)
        yield number, line.split('--', 1)[0]


def addon_lua():
    yield from (ROOT / 'addon/shared').glob('*.lua')
    for edition in ('vanilla', 'forever', 'tbc', 'retail'):
        for path in (ROOT / 'addon' / edition / 'WoWStatus').glob('*.lua'):
            if not (ROOT / 'addon/shared' / path.name).exists():
                yield path


def test_only_safe_lua_reads_the_pc_clock():
    found = [f'{path.relative_to(ROOT)}:{number}: {line.strip()}'
             for path in addon_lua() if path.name != 'Safe.lua'
             for number, line in code_lines(path) if BARE_TIME.search(line)]
    assert not found, 'use S.now(), S.uptime(), S.localNow() or S.timeOf() instead of time:\n' + '\n'.join(found)


def test_guard_sees_a_bare_call_but_not_lookalikes(tmp_path):
    sample = tmp_path / 'Sample.lua'
    sample.write_text('local a = S.now()\nlocal b = A.requestPlaytime()\n'
                      '-- time() in a comment\nlocal c = "time()"\nlocal d = time()\n'
                      '--[[ time()\n time() ]]\nlocal e = [[\ntime()]]\nlocal f = {time = 1}\n'
                      'local g = pcall(time)\nlocal h = x.time\n', encoding='utf-8')
    assert [n for n, line in code_lines(sample) if BARE_TIME.search(line)] == [5, 11]


def test_clocks_follow_realm_time_uptime_and_the_pc():
    lua = pc('Thora', skew=600)
    lua.execute('__mono=42.5')
    assert lua.eval('WoWStatusSafe.now()') == REALM
    assert lua.eval('WoWStatusSafe.uptime()') == 42.5
    assert lua.eval('WoWStatusSafe.localNow()') == REALM + 600
    lua.execute('function time(t) assert(type(t) == "table"); return t.day * 86400 end')
    assert lua.eval('WoWStatusSafe.timeOf({year=2026, month=11, day=17})') == 17 * 86400
    assert lua.eval('WoWStatusSafe.timeOf("nonsense")') is None


def test_minimap_latest_age_uses_realm_time_on_a_fast_pc():
    """Journal entries carry realm time; a PC clock ten minutes fast used to
    add those ten minutes to "Latest: ... · 5 min"."""
    thora = pc('Thora', skew=600)
    thora.execute('''
        local methods = getmetatable(CreateFrame("Frame")).__index
        function methods:RegisterForClicks() end
        function methods:HookScript(event, fn) self[event] = fn end
        Minimap=CreateFrame("Frame","Minimap",UIParent)
        function Minimap:GetCenter() return 0,0 end
        function Minimap:GetEffectiveScale() return 1 end
        WoWStatusMinimap.init(WoWStatusDB)
        __tip = {}
        GameTooltip = {SetOwner=function() __tip = {} end, SetText=function() end,
            AddLine=function(_, t) table.insert(__tip, t) end, Show=function() end, Hide=function() end}
        local group = next(character().group_ids)
        WoWStatusJournal.received({sender="Mira-TestRealm",nonce="1-1-a",kind="level",level=30,
            at=GetServerTime()-300,group_id=group})
        WoWStatusMinimapButton.OnEnter(WoWStatusMinimapButton)
    ''')
    tip = '\n'.join(thora.eval('__tip').values())
    assert 'Reached level 30! · 5 min' in tip, tip
