import copy
import hashlib
import importlib
import os
import shutil
import subprocess
import sys
import time
import types
from pathlib import Path

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
    if config.pluginmanager.hasplugin('xdist') and not hasattr(config, 'workerinput'):
        config.pluginmanager.register(_WorkerLuaCounts(), 'wow-status-worker-lua-counts')
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
    """False for runs that start no test bodies here: collection, setup plans, xdist workers.

    Under pytest-xdist the workers run the tests and send their Lua counts to the
    main process (``_WorkerLuaCounts``), which checks and reports the total.
    """
    option = config.option
    return config.getoption('lua') == '5.1' and not (
        option.collectonly or getattr(option, 'setuponly', False)
        or getattr(option, 'setupplan', False) or hasattr(config, 'workerinput'))


class _WorkerLuaCounts:
    """Adds each pytest-xdist worker's Lua 5.1 counts to the main process's."""

    @pytest.hookimpl
    def pytest_testnodedown(self, node, error):
        global _runtimes_outside_tests
        output = getattr(node, 'workeroutput', {})
        _lua_tests.update(output.get('lua_tests', ()))
        _runtimes_outside_tests += output.get('lua_runtimes_outside_tests', 0)


def pytest_sessionfinish(session):
    global _no_lua_ran
    config = session.config
    if hasattr(config, 'workerinput'):  # an xdist worker: report to the main process
        config.workeroutput['lua_tests'] = sorted(_lua_tests)
        config.workeroutput['lua_runtimes_outside_tests'] = _runtimes_outside_tests
        return
    if _guarded(config) and session.exitstatus == 0 and not _lua_tests:
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


@pytest.fixture(scope='session')
def shared_once(tmp_path_factory):
    """Make a folder once per run and share it, across pytest-xdist workers too.

    ``shared_once(name, make)`` calls ``make(folder)`` for the first caller only and
    returns the finished folder to everyone. Callers must not change it.
    """
    base = tmp_path_factory.getbasetemp()
    if os.environ.get('PYTEST_XDIST_WORKER'):
        base = base.parent  # the run's folder, which holds every worker's own folder

    def once(name, make):
        final = base / f'shared-{name}'
        if final.is_dir():
            return final
        lock = base / f'shared-{name}.lock'
        deadline = time.monotonic() + 600
        while True:
            try:
                handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except FileExistsError:
                if final.is_dir():
                    return final
                if time.monotonic() > deadline:
                    raise TimeoutError(f'Another test worker still holds {lock}') from None
                time.sleep(0.02)
        try:
            if not final.is_dir():
                partial = base / f'shared-{name}.partial'
                shutil.rmtree(partial, ignore_errors=True)  # from a worker that failed
                partial.mkdir()
                make(partial)
                partial.rename(final)
        finally:
            os.close(handle)
            os.unlink(lock)
        return final

    return once


@pytest.fixture
def reuse_homepage_packages(shared_once, monkeypatch):
    """Make a homepage builder module reuse each addon ZIP it wrote earlier in this run.

    ``write_package`` compresses an edition's committed files, and its ZIP is fixed by
    the builder's code, the Git tree of that addon folder and the file list.
    Compressing the same files again for every build was most of these tests' time.
    The rest of a build still runs every time, and changed addon files are a real
    build. ``test_a_rebuild_leaves_no_file_of_the_earlier_build`` compares a fresh
    compression with a reused one, so the builder's repeatable output stays checked.
    """
    def reuse(module):
        write_package = module.write_package
        code = hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()

        def write(root, revision, folder, files, archive):
            tree = module.git(root, 'rev-parse', '--verify', f'{revision}:{folder.rstrip("/")}').decode().strip()
            key = repr((code, tree, folder, files))
            made = shared_once('zip-' + hashlib.sha256(key.encode('utf-8')).hexdigest()[:32],
                               lambda made: write_package(root, revision, folder, files, made / archive.name))
            shutil.copyfile(made / archive.name, archive)

        monkeypatch.setattr(module, 'write_package', write)
        return module

    return reuse


@pytest.fixture(scope='session')
def clone_repository():
    """Clone a template repository, checking out only the folders a test reads and edits.

    Sharing the template's Git objects is much faster than writing and committing
    every file again, and objects are never rewritten, so a test's commits can't reach
    the template. Pack the template first (``git repack -ad``) so a clone links a few
    pack files instead of hundreds of loose objects. Other paths stay committed but out of the working tree: Git then
    never has to reread hundreds of just-written files to trust its index.
    """
    def clone(template, destination, folders):
        # Stored in the clone's config: exact bytes on Windows too, and no developer hooks.
        # expectFilesOutsideOfPatterns: Git otherwise clears a skip-worktree mark a test sets.
        # --template=: no sample hooks or other template files, which this would otherwise copy each time.
        subprocess.run(['git', 'clone', '-q', '--local', '--no-checkout', '--template=', '-c', 'core.autocrlf=false',
                        '-c', 'core.hooksPath=no-hooks', '-c', 'sparse.expectFilesOutsideOfPatterns=true',
                        str(template), str(destination)],
                       check=True, capture_output=True)
        subprocess.run(['git', '-C', str(destination), 'sparse-checkout', 'set', '--cone', *folders],
                       check=True, capture_output=True)
        subprocess.run(['git', '-C', str(destination), 'checkout', '-q'], check=True, capture_output=True)
        return destination

    return clone
