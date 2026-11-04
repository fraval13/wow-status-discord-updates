import copy
import sys
import time
import types

import pytest

from wow_status.store import Store

# Every WoW client runs Lua 5.1, but lupa's default ``LuaRuntime`` is a newer Lua
# (5.5 in lupa 2.8). ``--lua=5.1`` makes ``import lupa`` give Lua 5.1 before any test
# module imports it, so the same suite exercises the game's Lua (issue #24).
_lua_tests = set()
_runtimes_outside_tests = 0
_current_test = None
_no_lua_ran = False


def pytest_addoption(parser):
    parser.addoption(
        '--lua', choices=('default', '5.1'), default='default',
        help="Lua for the addon tests: lupa's default runtime, or 5.1 as in every WoW client.")


def pytest_configure(config):
    if config.getoption('lua') != '5.1':
        return
    # Not importorskip: a missing runtime must fail the run rather than silently
    # skip every Lua-backed test.
    try:
        import lupa
        from lupa import lua51
    except ImportError as error:
        raise pytest.UsageError(f'--lua=5.1 needs lupa with its lua51 module ({error})') from None
    version = lua51.LuaRuntime().eval('_VERSION')
    if version != 'Lua 5.1':
        raise pytest.UsageError(f'--lua=5.1 needs lupa.lua51, which reports {version!r}')

    def LuaRuntime(*args, **kwargs):
        """Records which tests start Lua, so the run can prove it reached them."""
        global _runtimes_outside_tests
        if _current_test is None:
            _runtimes_outside_tests += 1
        else:
            _lua_tests.add(_current_test)
        return lua51.LuaRuntime(*args, **kwargs)

    # A copy of the lupa package (``lupa.version`` and ``import lupa.lua54`` keep
    # working) whose runtime names are all Lua 5.1's. Its lazy ``__getattr__`` is
    # left out so that no name silently falls through to the newest Lua.
    swapped = types.ModuleType('lupa')
    swapped.__dict__.update({k: v for k, v in vars(lupa).items() if k != '__getattr__'})
    swapped.__dict__.update({k: v for k, v in vars(lua51).items() if not k.startswith('_')})
    swapped.LuaRuntime = LuaRuntime
    sys.modules['lupa'] = swapped


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


def pytest_sessionfinish(session):
    global _no_lua_ran
    if (session.config.getoption('lua') == '5.1' and session.exitstatus == 0
            and not _lua_tests and not _runtimes_outside_tests):
        # Guards against the Lua tests being skipped or deselected unnoticed.
        _no_lua_ran = True
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(terminalreporter, config):
    if config.getoption('lua') != '5.1':
        return
    outside = f' (plus {_runtimes_outside_tests} runtimes started outside a test)' * bool(
        _runtimes_outside_tests)
    terminalreporter.write_line(f'{len(_lua_tests)} tests started a Lua 5.1 runtime{outside}')
    if _no_lua_ran:
        terminalreporter.write_line(
            'ERROR: --lua=5.1 ran no Lua code, so nothing was checked under Lua 5.1. '
            'Select at least one Lua-backed test.', red=True, bold=True)


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
