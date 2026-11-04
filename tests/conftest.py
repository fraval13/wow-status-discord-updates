import copy
import sys
import time

import pytest

from wow_status.store import Store

# Every WoW client runs Lua 5.1, but lupa's default ``LuaRuntime`` is a newer Lua
# (5.5 in lupa 2.8). ``--lua=5.1`` swaps ``lupa`` for ``lupa.lua51`` before any
# test module imports it, so the same suite exercises the game's Lua (issue #24).
_lua_tests = set()
_current_test = None


def pytest_addoption(parser):
    parser.addoption(
        '--lua', choices=('default', '5.1'), default='default',
        help="Lua for the addon tests: lupa's default runtime, or 5.1 as in every WoW client.")


def pytest_configure(config):
    if config.getoption('lua') != '5.1':
        return
    # A plain import, not importorskip: a missing runtime must fail the run rather
    # than silently skip every Lua-backed test.
    from lupa import lua51
    version = lua51.LuaRuntime().eval('_VERSION')
    if version != 'Lua 5.1':
        raise pytest.UsageError(f'--lua=5.1 needs lupa.lua51, which reports {version!r}')

    class LuaRuntime(lua51.LuaRuntime):
        """Records which tests start Lua, so the run can prove it reached them."""

        def __init__(self, *args, **kwargs):
            # The Cython base takes its arguments in __cinit__; object.__init__ takes none.
            if _current_test is not None:
                _lua_tests.add(_current_test)

    lua51.LuaRuntime = LuaRuntime
    sys.modules['lupa'] = lua51


def pytest_report_header(config):
    try:
        import lupa
    except ImportError:
        return 'lua: lupa not installed, Lua-backed tests are skipped'
    return f"lua: {lupa.LuaRuntime().eval('_VERSION')} (--lua={config.getoption('lua')})"


@pytest.hookimpl(wrapper=True)
def pytest_runtest_protocol(item, nextitem):
    global _current_test
    _current_test = item.nodeid
    try:
        return (yield)
    finally:
        _current_test = None


def pytest_terminal_summary(terminalreporter, config):
    if config.getoption('lua') == '5.1':
        terminalreporter.write_line(f'{len(_lua_tests)} tests ran Lua 5.1 code')


def pytest_sessionfinish(session):
    if session.config.getoption('lua') == '5.1' and not _lua_tests and session.exitstatus == 0:
        # Guards against the Lua tests being skipped or deselected unnoticed.
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


@pytest.fixture
def payload():
    now = int(time.time())
    return {
        'version': 1,
        'identity': {'guid': 'Player-123-0001', 'name': 'Thora', 'realm': 'Test Realm',
                     'client': 'classic-era'},
        'settings': {'enabled': True, 'introduction_confirmed': True,
                     'fields': {'level': True, 'class': True, 'race': True},
                     'announcements': {'introduction': True, 'level': True, 'loot': True},
                     'loot_quality': 4, 'level_interval': 10},
        'snapshot': {'level': 10, 'class': 'Warrior', 'race': 'Dwarf', 'zone': 'PRIVATE'},
        'exported_at': now,
        'events': [{'id': 'intro-1', 'kind': 'introduction', 'at': now, 'data': {}},
                   {'id': 'level-10', 'kind': 'level', 'at': now, 'data': {'level': 10}}],
    }


@pytest.fixture
def store(tmp_path):
    value = Store(tmp_path / 'service.sqlite3')
    yield value
    value.close()


@pytest.fixture
def clone():
    return copy.deepcopy
