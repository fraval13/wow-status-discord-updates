"""Addon text validation must not depend on the C library's locale (issue #23).

Lua's built-in control and space classes and ``string.lower`` follow the C
library's locale. Under the macOS default ``LC_CTYPE=UTF-8`` they treat bytes
0x80-0xFF as Latin-1: 0x80-0x9F (the second byte of Æ, Ø and Å) are control
bytes, 0x85 is a space, and the lead byte 0xC3 lowercases to 0xE3. The addon uses
explicit byte classes and helpers from ``Safe.lua`` instead.
"""
import re
from pathlib import Path

import pytest
from test_addon import make_lua

ADDON = Path(__file__).parents[1] / 'addon'
# A class escape preceded by an even number of percent signs (zero included).
CONTROL_CLASS = re.compile(r'(?<!%)(?:%%)*%[cC]')
SPACE_CLASS = re.compile(r'(?<!%)(?:%%)*%[sS]')
# Format strings, not patterns: %s and %S mean "string" and "seconds" there.
FORMAT_LITERAL = re.compile(r'\b(?:format|date)\(\s*"[^"]*"')


def locale_dependent(line):
    line = FORMAT_LITERAL.sub('', line)
    return bool(CONTROL_CLASS.search(line) or SPACE_CLASS.search(line))
NORDIC = ['Ærlig', 'Øystein', 'Åse']


def addon_lua_files():
    shared = sorted((ADDON / 'shared').glob('*.lua'))
    editions = sorted(ADDON.glob('*/WoWStatus/*.lua'))
    return shared + editions


def test_addon_lua_never_uses_locale_dependent_control_or_space_classes():
    files = addon_lua_files()
    assert files
    offenders = []
    for path in files:
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if locale_dependent(line):
                offenders.append(f'{path.relative_to(ADDON)}:{number}: {line.strip()}')
    assert offenders == [], 'use WoWStatusSafe classes instead:\n' + '\n'.join(offenders)


@pytest.mark.parametrize('line, flagged', [
    ('x:find("[%c|]")', True),
    ('x:find("%%%c")', True),
    ('x:match("^%s*(.-)$")', True),
    ('x:find("%%c")', False),
    ('x:gsub("%%s", "")', False),
    ('string.format("%s", value)', False),
    ('date("!%H:%M:%S", at)', False),
    ('string.format("%s", x):match("^%s*(.-)$")', True),
])
def test_guard_counts_escaped_percent_signs(line, flagged):
    assert locale_dependent(line) is flagged


def test_safe_lua_loads_before_every_consumer():
    for toc in sorted(ADDON.glob('*/WoWStatus/*.toc')):
        files = [line.strip() for line in toc.read_text(encoding='utf-8').splitlines()
                 if line.strip().endswith('.lua')]
        assert files[0] == 'Safe.lua', toc


@pytest.fixture
def lua():
    return make_lua()


def test_control_classes_match_exactly_ascii_control_bytes(lua):
    matched = lua.execute('''
        local found = {}
        for byte = 0, 255 do
            local char = string.char(byte)
            found[#found + 1] = (char:find(WoWStatusSafe.CONTROL) and "c" or "-")
                .. (char:find(WoWStatusSafe.CONTROL_OR_PIPE) and "p" or "-")
        end
        return table.concat(found, ",")
    ''').split(',')
    for byte, flags in enumerate(matched):
        control = byte < 32 or byte == 127
        assert flags == ('c' if control else '-') + ('p' if control or byte == 124 else '-'), byte


def test_space_class_and_helpers_are_ascii_only(lua):
    matched = lua.execute('''
        local found = {}
        for byte = 0, 255 do
            local char = string.char(byte)
            found[#found + 1] = (char:find(WoWStatusSafe.SPACE) and "s" or "-")
                .. (char:find(WoWStatusSafe.NONSPACE) and "n" or "-")
                .. WoWStatusSafe.lowerASCII(char):byte()
        end
        return table.concat(found, ",")
    ''').split(',')
    for byte, flags in enumerate(matched):
        space = byte in (9, 10, 11, 12, 13, 32)
        lowered = byte + 32 if 65 <= byte <= 90 else byte
        assert flags == ('s-' if space else '-n') + str(lowered), byte
    trim = lua.eval('WoWStatusSafe.trim')
    assert trim(' \t Gjengen PÅ \r\n') == 'Gjengen PÅ'
    assert lua.eval('WoWStatusSafe.stripSpace')(' Argent  Dawn ') == 'ArgentDawn'
    assert lua.eval('WoWStatusSafe.lowerASCII')('ÆRLIG-Realm') == 'Ærlig-realm'


def test_control_classes_replace_embedded_nul_and_delete(lua):
    cleaned = lua.execute(r'''
        return (("a\0b\127c\31d|e"):gsub(WoWStatusSafe.CONTROL_OR_PIPE, " "))
    ''')
    assert cleaned == 'a b c d e'


@pytest.mark.parametrize('name', NORDIC)
def test_nordic_letters_are_accepted_in_sender_group_and_player_names(lua, name):
    from wow_status.group_routing import group_key
    assert lua.eval('WoWStatusPopups.senderKey')(f'{name}-TestRealm') == f'{name}-testrealm'
    label = f'{name} gjeng — PÅ {name}'
    key, cleaned = lua.eval('WoWStatusGroups.key')(label)
    assert (key, cleaned) == (group_key(label), label)
    ok, _ = lua.eval('WoWStatusGroups.update')(label, name)
    assert ok is True
    assert lua.eval('WoWStatusDB.player_name') == name


@pytest.mark.parametrize('name', NORDIC)
def test_popup_from_nordic_sender_is_received(lua, name):
    command = lua.eval('SlashCmdList.WOWSTATUS')
    command('popup channel WStatusFriends')
    command('popup on')
    command(f'popup trust {name}-TestRealm Ølvenn')
    receive = lua.eval('WoWStatusPopups.receive')
    assert receive('WSTATUS1 LEVEL 25 1793000000 event-1', f'{name}-TestRealm',
                   'WStatusFriends') is True
    assert lua.eval('WoWStatusLevelPopup.message.text') == f'Ølvenn’s {name} reached level 25!'


@pytest.mark.parametrize('detail, sent', [
    ('Won |cffff0000a duel|r\\tin Ærlig', 'Won a duel in Ærlig'),
    ('Won |Hitem:1|h[Ærlig Blade]|h |TInterface\\\\Icon:0|t', 'Won [Ærlig Blade] '),
    ('Odd | pipe', 'Odd   pipe'),
])
def test_outgoing_detail_strips_escapes_and_pipes_the_receiver_would_reject(lua, detail, sent):
    lua.eval('WoWStatusGroups.update')('navsquad', '')
    text = lua.execute(f'''
        local ids = {{}}
        for id in pairs(character().group_ids) do ids[id] = true end
        WoWStatusPopups.broadcast(character(), {{id = "pvp-1", kind = "pvp", at = time(),
            group_ids = ids, data = {{text = "{detail}"}}}})
        return __sent[1].text
    ''')
    assert text.split(' ', 6)[6] == sent


@pytest.mark.parametrize('text, stripped', [
    ('|cnIQ4:Epic Mount|r', 'Epic Mount'),
    ('a||rb', 'a|rb'),
    ('||cffffffffX', '|cffffffffX'),
    ('|KTb12|k friend', ' friend'),
    ('|TInterface\\\\Icons\\\\X:0|t', ''),
])
def test_strip_escapes_handles_named_colours_protected_text_and_literal_pipes(
        lua, text, stripped):
    assert lua.execute(f'return WoWStatusSafe.stripEscapes("{text}")') == stripped


def test_detail_that_is_only_escapes_is_not_sent(lua):
    lua.eval('WoWStatusGroups.update')('navsquad', '')
    sent = lua.execute('''
        local ids = {}
        for id in pairs(character().group_ids) do ids[id] = true end
        WoWStatusPopups.broadcast(character(), {id = "pvp-1", kind = "pvp", at = time(),
            group_ids = ids, data = {text = "|TInterface\\\\Icons\\\\X:0|t"}})
        return #__sent
    ''')
    assert sent == 0


def test_sender_keys_never_call_locale_dependent_string_lower(lua):
    lua.execute('string.lower = function() error("locale-dependent lower") end')
    assert lua.eval('WoWStatusPopups.senderKey')('ÅSE-TestRealm') == 'Åse-testrealm'


def test_trust_command_splits_nordic_names_and_aliases(lua):
    lua.eval('SlashCmdList.WOWSTATUS')('popup trust Åse-TestRealm Gamle Ølvenn')
    assert lua.eval('WoWStatusDB.popups.trusted["Åse-testrealm"]') == 'Gamle Ølvenn'


def test_control_bytes_are_still_rejected(lua):
    assert lua.eval('WoWStatusPopups.senderKey')('Bad\tName-TestRealm') is None
    assert lua.eval('WoWStatusPopups.senderKey')('Bad|Name-TestRealm') is None
    assert lua.eval('WoWStatusGroups.key')('Bad\x7fGroup') is None
    ok, _ = lua.eval('WoWStatusGroups.update')('Weekend Crew', 'Bad\x01Name')
    assert ok is False
