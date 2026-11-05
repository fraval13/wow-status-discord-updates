import copy
import importlib
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
_lua_version = None
_original_lupa = None


def pytest_addoption(parser):
    parser.addoption(
        '--lua', choices=('default', '5.1'), default='default',
        help="Lua for the addon tests: lupa's default runtime, or 5.1 as in every WoW client.")


def pytest_configure(config):
    global _runtimes_outside_tests, _no_lua_ran, _lua_version, _original_lupa
    _lua_tests.clear()
    _runtimes_outside_tests = 0
    _no_lua_ran = False
    if config.getoption('lua') != '5.1':
        return
    # Not importorskip: a missing runtime must fail the run rather than silently
    # skip every Lua-backed test.
    try:
        import lupa
        from lupa import lua51
    except ImportError as error:
        raise pytest.UsageError(f'--lua=5.1 needs lupa with its lua51 module ({error})') from None
    _lua_version = lua51.LuaRuntime().eval('_VERSION')
    if _lua_version != 'Lua 5.1':
        raise pytest.UsageError(f'--lua=5.1 needs lupa.lua51, which reports {_lua_version!r}')

    class LuaRuntime(lua51.LuaRuntime):
        """Records which tests start Lua, so the run can prove it reached them."""

        def __new__(cls, *args, **kwargs):
            # Hooks __new__, not __init__: arguments still reach lupa unchanged.
            global _runtimes_outside_tests
            if _current_test is None:
                _runtimes_outside_tests += 1
            else:
                _lua_tests.add(_current_test)
            return super().__new__(cls, *args, **kwargs)

    # A copy of the lupa package (``lupa.version`` and ``import lupa.lua54`` keep
    # working) whose runtime names are all Lua 5.1's. Its lazy ``__getattr__``, which
    # serves the newest Lua, is replaced by one that only loads ``lupa.luaXY``
    # submodules, so that no name silently falls through to the newest Lua.
    def submodule(name):
        if name.startswith('lua') and name[3:].isdigit():
            return importlib.import_module(f'lupa.{name}')
        raise AttributeError(f"module 'lupa' has no attribute {name!r} under --lua=5.1")

    swapped = types.ModuleType('lupa')
    swapped.__dict__.update(vars(lupa))
    swapped.__dict__.update({k: v for k, v in vars(lua51).items() if not k.startswith('_')})
    swapped.__getattr__ = submodule
    swapped.LuaRuntime = LuaRuntime
    _original_lupa = sys.modules['lupa']
    sys.modules['lupa'] = swapped


def pytest_unconfigure(config):
    global _original_lupa
    if _original_lupa is not None:
        sys.modules['lupa'] = _original_lupa
        _original_lupa = None


def pytest_report_header(config):
    if config.getoption('lua') == '5.1':
        return f'lua: {_lua_version} (--lua=5.1)'
    try:
        import lupa
        version = lupa.LuaRuntime().eval('_VERSION')
    except Exception as error:  # lupa loads its binary modules lazily, on first use
        return f'lua: unavailable ({type(error).__name__}), Lua-backed tests are skipped or fail'
    return f"lua: {version} (lupa default; --lua=5.1 for the game's)"


@pytest.hookimpl(wrapper=True)
def pytest_runtest_protocol(item, nextitem):
    global _current_test
    _current_test = item.nodeid
    try:
        return (yield)
    finally:
        _current_test = None


def _guarded(config):
    """False for modes that run no test bodies here: collection, setup plans, xdist."""
    option = config.option
    return config.getoption('lua') == '5.1' and not (
        option.collectonly or getattr(option, 'setuponly', False)
        or getattr(option, 'setupplan', False) or getattr(option, 'numprocesses', None)
        or hasattr(config, 'workerinput'))


def pytest_sessionfinish(session):
    global _no_lua_ran
    if _guarded(session.config) and session.exitstatus == 0 and not _lua_tests:
        # Guards against the Lua tests being skipped or deselected unnoticed. Runtimes
        # started outside a test do not count: they show nothing was checked.
        _no_lua_ran = True
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(terminalreporter, config):
    if not _guarded(config):
        return
    count = len(_lua_tests)
    line = f"{count} test{'s' * (count != 1)} started a Lua 5.1 runtime"
    if _runtimes_outside_tests:
        line += f' (plus {_runtimes_outside_tests} started outside a test)'
    terminalreporter.write_line(line)
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


@pytest.fixture
def hold_lock():
    """Take the flock a deployment or homepage publish holds; whatever is still held is released after the test."""
    handles = []

    def hold(path):
        import fcntl  # Linux only, like the deploy tests that use this
        handle = open(path, 'ab')
        handles.append(handle)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return handle

    yield hold
    for handle in handles:
        handle.close()
