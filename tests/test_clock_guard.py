"""One clock (issue #229).

Only Safe.lua reads time(), this PC's clock. Everything stored or shared uses
realm time (S.now()), short in-memory timers use game uptime (S.uptime()), and
the player's local wall clock is read through S.localNow(). Mocked API only.
"""
import re
from pathlib import Path

from test_clock_skew import REALM, pc

ROOT = Path(__file__).resolve().parents[1]
LONG_OPEN = re.compile(r'\[(=*)\[')
NAME = re.compile(r'[A-Za-z_]\w*')


def bare_time(text):
    """Line numbers where Lua code uses the global `time`: a call, a value
    (pcall(time)) or an assignment (time = ...). Comments, strings, fields
    (x.time, x:time()) and table keys ({time = 1}) are skipped. A small
    tokenizer, so brackets inside strings and comments can't hide code."""
    found, i, n, prev = [], 0, len(text), ''
    while i < n:
        c = text[i]
        if text.startswith('--', i):
            long = LONG_OPEN.match(text, i + 2)
            if long:
                close = text.find(']' + long.group(1) + ']', long.end())
                i = n if close < 0 else close + len(long.group(0))
            else:
                close = text.find('\n', i)
                i = n if close < 0 else close
            continue
        long = LONG_OPEN.match(text, i)
        if long:
            close = text.find(']' + long.group(1) + ']', long.end())
            i, prev = (n if close < 0 else close + len(long.group(0))), 'string'
            continue
        if c in '"\'':
            i += 1
            while i < n and text[i] != c and text[i] != '\n':
                i += 2 if text[i] == '\\' else 1
            i, prev = i + 1, 'string'
            continue
        name = NAME.match(text, i)
        if name and not (i and (text[i - 1].isalnum() or text[i - 1] == '_')):
            word, i = name.group(0), name.end()
            if word == 'time' and not (prev in ('.', ':') and not text.startswith('..', i - 6)):
                rest = text[i:].lstrip(' \t')
                key = rest.startswith('=') and not rest.startswith('==') and prev in ('{', ',', ';')
                if not key:
                    found.append(text.count('\n', 0, i) + 1)
            prev = word
            continue
        if not c.isspace():
            prev = c
        i += 1
    return found


def addon_lua():
    yield from (ROOT / 'addon/shared').glob('*.lua')
    for edition in ('vanilla', 'forever', 'tbc', 'retail'):
        for path in (ROOT / 'addon' / edition / 'WoWStatus').glob('*.lua'):
            if not (ROOT / 'addon/shared' / path.name).exists():
                yield path


def test_only_safe_lua_reads_the_pc_clock():
    found = [f'{path.relative_to(ROOT)}:{number}'
             for path in addon_lua() if path.name != 'Safe.lua'
             for number in bare_time(path.read_text(encoding='utf-8'))]
    assert not found, 'use S.now(), S.uptime(), S.localNow() or S.timeOf() instead of time:\n' + '\n'.join(found)


def test_guard_sees_a_bare_use_but_not_lookalikes():
    sample = '\n'.join([
        'local a = S.now()',                      # 1
        'local b = A.requestPlaytime()',          # 2
        '-- time() in a comment',                 # 3
        'local c = "time()"',                     # 4
        'local d = time()',                       # 5  call
        '--[[ time()',                            # 6
        ' time() ]]',                             # 7
        'local e = [[',                           # 8
        'time()]]',                               # 9
        'local f = {time = 1, x = 2}',            # 10
        'local g = pcall(time)',                  # 11 value
        'local h = x.time + y:time()',            # 12
        'local p = s:gsub("^%[[A-Z]+%] ", "")',   # 13 bracket in a string
        'local i = time()',                       # 14 call after it
        'local j = t[k[1]]',                      # 15
        '---[[ not a long comment',               # 16
        'time = GetServerTime',                   # 17 assignment
        'local k = {time',                        # 18 value in a table
        '}',                                      # 19
        'local l = "a"..time()',                  # 20 after concatenation
    ])
    assert bare_time(sample) == [5, 11, 14, 17, 18, 20]


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
