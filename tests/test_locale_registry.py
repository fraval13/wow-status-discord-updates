"""Display locale plug-ins: fresh defaults, saved choices, partial banks and menus."""
import importlib.util
from pathlib import Path

import pytest
from lupa import LuaRuntime
from test_addon import STUBS, make_lua
from test_client_compatibility import client_runtime
from test_gamepad import FRAMES, main_window

ROOT = Path(__file__).resolve().parents[1]
BANK = '''
    WoWStatusLocale.register("zz","Test language",{"zzZZ"},
        {["Activity"]="Test activity", ["Language:"]="Test language:", ["Close"]="Test close", ["Empty"]=""},
        {{"^Reached level (%d+)!$","Test level %1!"}})
'''


def locale_runtime():
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute('WoWStatusDB={}')
    for name in ('Safe', 'Locale', 'LocaleNN'):
        lua.execute((ROOT / f'addon/shared/{name}.lua').read_text(encoding='utf-8'))
    return lua


def test_new_bank_registers_without_changing_locale_core_and_falls_back_per_string():
    lua = locale_runtime()
    lua.execute(BANK + '''
        assert(WoWStatusLocale.set("zz"))
        assert(WoWStatusLocale.T("Activity")=="Test activity")
        assert(WoWStatusLocale.T("Reached level 12!")=="Test level 12!")
        assert(WoWStatusLocale.T("Unknown text")=="Unknown text")
        assert(WoWStatusLocale.T("Empty")=="Empty")
        assert(WoWStatusLocale.T(12)==12 and WoWStatusLocale.T(nil)==nil)
        assert(not WoWStatusLocale.set("missing") and WoWStatusLocale.lang()=="zz")
        WoWStatusLocale.set("nn")
        assert(WoWStatusLocale.T("Activity")=="Aktivitet")
        WoWStatusLocale.set("en")
        assert(WoWStatusDB.language==nil and WoWStatusLocale.T("Activity")=="Activity")
    ''')


@pytest.mark.parametrize('client', ['enUS', 'enGB', 'frFR', None])
def test_unavailable_client_bank_falls_back_to_english(client):
    lua = locale_runtime()
    lua.globals().client = client
    lua.execute('function GetLocale() return client end')
    assert lua.eval('WoWStatusLocale.clientLanguage()') == 'en'


@pytest.mark.parametrize('saved', ['nil', '"nn"', '"en"'])
def test_old_accounts_keep_their_saved_choice_even_when_a_client_bank_is_available(saved):
    lua = make_lua(STUBS + f'''
        WoWStatusDB={{version=1,characters={{}},language={saved}}}
        function GetLocale() error("existing choices must not consult the client") end
    ''')
    assert lua.eval('WoWStatusLocale.lang()') == ('nn' if saved == '"nn"' else 'en')


@pytest.mark.parametrize('edition', ['vanilla', 'forever', 'tbc', 'retail'])
def test_fresh_account_uses_available_client_bank_and_explicit_choice_wins_afterward(edition):
    # A small bank registered before initialization, like a TOC-loaded locale file.
    extra = '''
        function GetLocale()
            if not WoWStatusLocale.banks.zz then
    ''' + BANK + '''
            end
            return "zzZZ"
        end
    '''
    lua = make_lua(STUBS + extra, join_announcements=True) if edition == 'vanilla' else client_runtime(edition, extra=extra)
    assert lua.eval('WoWStatusLocale.lang()') == 'zz'
    lua.execute('''
        SlashCmdList.WOWSTATUS("language en")
        assert(WoWStatusLocale.lang()=="en" and WoWStatusDB.language==nil)
        fire("PLAYER_ENTERING_WORLD")
        assert(WoWStatusLocale.lang()=="en")
        SlashCmdList.WOWSTATUS("language zz")
        assert(WoWStatusLocale.lang()=="zz")
    ''')


def test_options_and_language_help_include_new_banks_and_a_menu_selects_them():
    lua = make_lua()
    lua.execute(BANK + '''
        WoWStatusPreviews.show()
        local p=WoWStatusNotificationPreviews
        assert(p.languageSwitch.text=="Choose language")
        local menu=WoWStatusUI.menu
        WoWStatusUI.menu=function(anchor,items,choose)
            assert(anchor==p.languageSwitch)
            assert(#items==3 and items[1].value=="en")
            choose("zz")
        end
        p.languageSwitch.OnClick(p.languageSwitch)
        WoWStatusUI.menu=menu
        assert(WoWStatusLocale.lang()=="zz" and p.reload.visible)
        assert(p.language.text=="Test language: Test language")
        __messages={}
        DEFAULT_CHAT_FRAME={AddMessage=function(_,text) __messages[#__messages+1]=text end}
        SlashCmdList.WOWSTATUS("language unknown")
        assert(__messages[#__messages]:find("en|nn|zz",1,true))
    ''')


def test_registered_language_menu_is_reachable_by_gamepad():
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute('unpack=unpack or table.unpack')
    lua.execute(FRAMES)
    lua.execute((ROOT / 'addon/shared/Gamepad.lua').read_text(encoding='utf-8'))
    main_window(lua)
    lua.execute('''
        local m=getmetatable(CreateFrame("Frame")).__index
        function m:SetText(text) self.text=text end
        function m:SetScrollChild(child) self.child=child end
        function m:SetShown(value) self.visible=value end
        function m:CreateFontString() return CreateFrame("FontString",nil,self) end
        for _,n in ipairs({"SetSize","SetJustifyH","SetWordWrap","SetScale"}) do m[n]=function() end end
    ''')
    for name in ('Safe', 'Locale', 'LocaleNN', 'Theme'):
        lua.execute((ROOT / f'addon/shared/{name}.lua').read_text(encoding='utf-8'))
    lua.execute(BANK + '''
        local chosen
        WoWStatusUI.menu(a,WoWStatusLocale.options(),function(code) chosen=code end)
        local menu=WoWStatusMenu
        menu.rect={100,100,200,180}
        local reached={}
        for _,c in ipairs(WoWStatusGamepad.controls(menu,{menu})) do reached[c]=true end
        local found=false
        for _,c in ipairs(menu.rows) do
            if c.value=="zz" then assert(reached[c]);c:Click();found=true end
        end
        assert(found and chosen=="zz")
    ''')


def test_coverage_reports_missing_keys_for_every_registered_bank_and_keeps_fallbacks():
    spec = importlib.util.spec_from_file_location('check_locales', ROOT / 'scripts/check_locales.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    lua = locale_runtime()
    lua.execute(BANK)
    missing = module.coverage(lua, ['Activity', 'Close', 'Something untranslated'])
    assert set(missing) == {'nn', 'zz'}
    assert missing['zz'] == ['Something untranslated']
    assert missing['nn'] == ['Something untranslated']
    assert 'Activity' in module.source_keys(ROOT)
    # Exercise the actual TOC-loaded banks as well as a partial fixture.
    shipped = module.load_banks(ROOT, 'vanilla')
    assert set(module.coverage(shipped, ['Activity', 'Close'])) == {'nn'}


def test_one_new_file_and_toc_line_load_a_partial_bank(tmp_path):
    spec = importlib.util.spec_from_file_location('check_locales', ROOT / 'scripts/check_locales.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    folder = tmp_path / 'addon/vanilla/WoWStatus'
    folder.mkdir(parents=True)
    names = ['Safe.lua', 'Locale.lua', 'LocaleNN.lua', 'LocaleZZ.lua']
    for name in names[:-1]:
        (folder / name).write_text((ROOT / 'addon/shared' / name).read_text(encoding='utf-8'), encoding='utf-8')
    (folder / names[-1]).write_text(BANK, encoding='utf-8')
    (folder / 'WoWStatus.toc').write_text('\n'.join(names), encoding='utf-8')
    lua = module.load_banks(tmp_path, 'vanilla')
    lua.execute('function GetLocale() return "zzZZ" end; WoWStatusLocale.set(WoWStatusLocale.clientLanguage())')
    assert lua.eval('WoWStatusLocale.T("Activity")') == 'Test activity'
    assert lua.eval('WoWStatusLocale.T("Untranslated")') == 'Untranslated'
