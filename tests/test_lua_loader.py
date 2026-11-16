"""The client harness follows the shipped TOC, including newly added Lua files."""
import lua_loader
import pytest
from test_addon import lupa


@pytest.fixture
def addon(tmp_path, monkeypatch):
    monkeypatch.setattr(lua_loader, 'ADDON_ROOT', tmp_path)
    folder = tmp_path / 'vanilla/WoWStatus'
    folder.mkdir(parents=True)
    (folder / 'First.lua').write_text('__order = {"fyrst"}', encoding='utf-8')
    (folder / 'Second.lua').write_text('table.insert(__order, "andre")', encoding='utf-8')
    (folder / 'WoWStatus.toc').write_text(
        '## Title: Prøve\n  # comment\n\n First.lua \nSecond.lua\n', encoding='utf-8')
    return folder


def order(runtime):
    return runtime.eval('table.concat(__order, ",")')


def test_adding_a_file_to_the_toc_loads_it_without_a_test_list_change(addon):
    lua = lupa.LuaRuntime()
    lua_loader.load_edition(lua, 'vanilla')
    assert order(lua) == 'fyrst,andre'
    (addon / 'nested').mkdir()
    (addon / 'nested/New.lua').write_text('table.insert(__order, "ny")', encoding='utf-8')
    toc = addon / 'WoWStatus.toc'
    toc.write_text(toc.read_text(encoding='utf-8').replace(
        'Second.lua', 'nested\\New.lua\nSecond.lua'), encoding='utf-8')
    lua_loader.load_edition(lua, 'vanilla')
    assert order(lua) == 'fyrst,ny,andre'


def test_selected_files_keep_toc_order_and_hooks_run_before_the_next_file(addon):
    lua = lupa.LuaRuntime()
    (addon / 'Second.lua').write_text('assert(__flag); table.insert(__order, "andre")', encoding='utf-8')

    def override(name):
        if name == 'First.lua':
            lua.globals().__flag = True

    lua_loader.load_edition(lua, 'vanilla', only=('Second.lua', 'First.lua'), after_file=override)
    assert order(lua) == 'fyrst,andre'
    lua_loader.load_edition(lua, 'vanilla', only=('First.lua',))
    assert order(lua) == 'fyrst'


def test_an_unlisted_selected_file_fails_instead_of_silently_skipping_it(addon):
    with pytest.raises(ValueError, match='TOC does not list: Missing.lua'):
        lua_loader.load_edition(lupa.LuaRuntime(), 'vanilla', only=('Missing.lua',))


def test_non_lua_entries_fail_instead_of_silently_missing_their_scripts(addon):
    (addon / 'WoWStatus.toc').write_text('Window.xml\n', encoding='utf-8')
    with pytest.raises(ValueError, match='cannot execute TOC entry: Window.xml'):
        lua_loader.load_edition(lupa.LuaRuntime(), 'vanilla')


def test_changed_source_is_recompiled_even_in_an_existing_runtime(addon):
    lua = lupa.LuaRuntime()
    lua_loader.load_edition(lua, 'vanilla')
    (addon / 'Second.lua').write_text('table.insert(__order, "endra")', encoding='utf-8')
    lua_loader.load_edition(lua, 'vanilla')
    assert order(lua) == 'fyrst,endra'
