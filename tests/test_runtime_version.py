"""`/wstatus popup status` reports the version from each edition's TOC (mocked API only)."""
import re
from pathlib import Path

import pytest
from test_addon import STUBS, make_lua
from test_forever import forever_runtime
from test_retail import retail_runtime
from test_tbc import tbc_runtime

ROOT = Path(__file__).parents[1]
EDITIONS = {
    'vanilla': lambda extra: make_lua(STUBS + extra),
    'forever': lambda extra: _login(forever_runtime(extra=extra)),
    'tbc': lambda extra: tbc_runtime(extra=extra),
    'retail': lambda extra: retail_runtime(extra=extra),
}


def _login(lua):
    lua.eval('fire')('PLAYER_LOGIN')
    lua.execute('WoWStatusGroups.announce=nil')
    return lua


def toc_metadata(edition):
    toc = (ROOT / 'addon' / edition / 'WoWStatus/WoWStatus.toc').read_text(encoding='utf-8')
    return dict(re.findall(r'^## ([^:]+): (.*)$', toc, re.MULTILINE))


def metadata_api(edition, *, legacy_only=False):
    """Mock the client lookup with this edition's real TOC fields, keyed by addon folder."""
    fields = ''.join(f'[ [==[{key}]==] ]=[==[{value}]==],' for key, value in toc_metadata(edition).items())
    lookup = f'''
        __metadataCalls = {{}}
        local fields = {{{fields}}}
        local function lookup(addon, field)
            table.insert(__metadataCalls, addon .. ":" .. field)
            if addon == "WoWStatus" then return fields[field] end
        end
    '''
    if legacy_only:
        return lookup + 'C_AddOns=nil; GetAddOnMetadata=lookup\n'
    return lookup + 'C_AddOns={GetAddOnMetadata=lookup}; GetAddOnMetadata=nil\n'


def status_lines(lua):
    lua.execute('__chat={}; DEFAULT_CHAT_FRAME={AddMessage=function(_, text) table.insert(__chat, text) end}')
    lua.eval('SlashCmdList.WOWSTATUS')('popup status')
    return [lua.eval(f'__chat[{index}]') for index in range(1, lua.eval('#__chat') + 1)]


@pytest.mark.parametrize('edition', EDITIONS)
def test_runtime_version_matches_toc_version_in_every_edition(edition):
    version = toc_metadata(edition)['Version']
    lua = EDITIONS[edition](metadata_api(edition))
    assert lua.eval('WoWStatusPopups.runtimeVersion') == version
    assert lua.eval('__metadataCalls[1]') == 'WoWStatus:Version'
    assert any(f'Runtime {version} ' in line for line in status_lines(lua))


@pytest.mark.parametrize('edition', EDITIONS)
def test_runtime_version_uses_legacy_global_when_c_addons_is_missing(edition):
    lua = EDITIONS[edition](metadata_api(edition, legacy_only=True))
    assert lua.eval('WoWStatusPopups.runtimeVersion') == toc_metadata(edition)['Version']


@pytest.mark.parametrize('extra', [
    'C_AddOns=nil; GetAddOnMetadata=nil',
    'C_AddOns={GetAddOnMetadata=function() error("unavailable") end}; GetAddOnMetadata=nil',
    'C_AddOns={GetAddOnMetadata=function() return "" end}; GetAddOnMetadata=nil',
    'C_AddOns={GetAddOnMetadata=function() return "1.0|cffff0000x" end}; GetAddOnMetadata=nil',
    'C_AddOns={GetAddOnMetadata=function() return string.rep("9", 33) end}; GetAddOnMetadata=nil',
    '__secret={}; function issecretvalue(v) return v==__secret end;'
    ' C_AddOns={GetAddOnMetadata=function() return __secret end}; GetAddOnMetadata=nil',
])
def test_runtime_version_falls_back_to_unknown_without_usable_metadata(extra):
    lua = make_lua(STUBS + extra)
    assert lua.eval('WoWStatusPopups.runtimeVersion') == 'unknown'
    assert any('Runtime unknown ' in line for line in status_lines(lua))


def test_runtime_version_tries_legacy_global_when_c_addons_returns_nothing():
    lua = make_lua(STUBS + '''
        C_AddOns={GetAddOnMetadata=function() return nil end}
        function GetAddOnMetadata(addon, field) return addon == "WoWStatus" and field == "Version" and "9.8.7" end
    ''')
    assert lua.eval('WoWStatusPopups.runtimeVersion') == '9.8.7'


def test_popups_source_has_no_hard_coded_runtime_version():
    for edition in ('shared', *EDITIONS):
        folder = ROOT / 'addon' / edition / ('' if edition == 'shared' else 'WoWStatus')
        source = (folder / 'Popups.lua').read_text(encoding='utf-8')
        assert not re.search(r'runtimeVersion\s*=\s*"', source), edition
