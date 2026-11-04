"""Addon text validation must not depend on the C library's locale (issue #23).

Lua's built-in control class follows ``iscntrl``. Under the macOS default
``LC_CTYPE=UTF-8`` it also matches bytes 0x80-0x9F, which are the second byte of
Æ, Ø and Å. The addon uses explicit byte classes from ``Safe.lua`` instead.
"""
import re
from pathlib import Path

import pytest
from test_addon import make_lua

ADDON = Path(__file__).parents[1] / 'addon'
LOCALE_CLASS = re.compile(r'(?<!%)%[cC]')
NORDIC = ['Ærlig', 'Øystein', 'Åse']


def addon_lua_files():
    shared = sorted((ADDON / 'shared').glob('*.lua'))
    editions = sorted(ADDON.glob('*/WoWStatus/*.lua'))
    return shared + editions


def test_addon_lua_never_uses_the_locale_dependent_control_class():
    files = addon_lua_files()
    assert files
    offenders = []
    for path in files:
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if LOCALE_CLASS.search(line):
                offenders.append(f'{path.relative_to(ADDON)}:{number}: {line.strip()}')
    assert offenders == [], 'use WoWStatusSafe.CONTROL instead:\n' + '\n'.join(offenders)


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


def test_control_classes_replace_embedded_nul_and_delete(lua):
    cleaned = lua.execute(r'''
        return (("a\0b\127c\31d|e"):gsub(WoWStatusSafe.CONTROL_OR_PIPE, " "))
    ''')
    assert cleaned == 'a b c d e'


@pytest.mark.parametrize('name', NORDIC)
def test_nordic_letters_are_accepted_in_sender_group_and_player_names(lua, name):
    from wow_status.group_routing import group_key
    assert lua.eval('WoWStatusPopups.senderKey')(f'{name}-TestRealm') == f'{name}-testrealm'
    label = f'{name} gjeng — {name}'
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


def test_control_bytes_are_still_rejected(lua):
    assert lua.eval('WoWStatusPopups.senderKey')('Bad\tName-TestRealm') is None
    assert lua.eval('WoWStatusPopups.senderKey')('Bad|Name-TestRealm') is None
    assert lua.eval('WoWStatusGroups.key')('Bad\x7fGroup') is None
    ok, _ = lua.eval('WoWStatusGroups.update')('Weekend Crew', 'Bad\x01Name')
    assert ok is False
