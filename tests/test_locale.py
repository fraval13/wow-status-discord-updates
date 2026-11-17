"""Optional Nynorsk: display-only translation, captions and completeness."""
import re
from pathlib import Path

from test_addon import make_lua
from test_journal import actor

ROOT = Path(__file__).parents[1]
# Words that are the same in Nynorsk.
SAME = {"Paladin", "Mine", "Troll", "Tauren", "Draenei", "Goblin", "Pandaren", "Dracthyr", "WoW Status", "X",
        "%", "-", "+", "Type:", "Person:", "PvP", "<", ">", "Mana"}


def test_english_is_the_default_and_unchanged():
    lua = make_lua()
    assert lua.eval('WoWStatusLocale.lang()') == 'en'
    assert lua.eval('WoWStatusLocale.T("Reached level 12!")') == 'Reached level 12!'


def test_nynorsk_translates_facts_recaps_and_titles():
    lua = make_lua()
    lua.execute('WoWStatusLocale.set("nn")')
    t = lua.eval('WoWStatusLocale.T')
    assert t('Reached level 12!') == 'Nådde nivå 12!'
    assert t('Entered Westfall') == 'Kom til Westfall'
    assert t('Total deaths: 22') == 'Dødsfall totalt: 22'
    assert t('Learned Blacksmithing (Expert)') == 'Lærte Blacksmithing (Ekspert)'
    assert t('Tailoring: Artisan (300 max)') == 'Tailoring: Kunstnar (maks 300)'
    assert t('Session recap: 2 level ups, 1 death.') == 'Øktsamandrag: 2 nivå, 1 dødsfall.'
    assert t('Tonight: Edith went from 5 to 7, died twice.') == 'I kveld: Edith gjekk frå 5 til 7, døydde to gonger.'
    assert t('First to reach level 10') == 'Først til nivå 10'
    assert t('LEVEL UP!') == 'NYTT NIVÅ!'
    assert t('Enjoy Westfall!') == 'Kos deg i Westfall!'
    lua.execute('WoWStatusLocale.set("en")')
    assert t('Reached level 12!') == 'Reached level 12!'


def test_captions_follow_the_language_and_keep_their_line():
    lua = make_lua()
    lua.execute('''
        WoWStatusPersonalities.set("classic")  -- these check the Classic banks; Random is the default
        local item = {id = "x:1", kind = "death", text = "Died", sender = "Mira-TestRealm"}
        local english = WoWStatusFlavour.text(item)
        assert(item.flavour_kind == "death" and item.flavour == english)
        WoWStatusLocale.set("nn")
        local nynorsk = WoWStatusFlavour.text(item)
        local expected = WoWStatusFlavourNN.death[item.flavour_pos]:gsub("^%[[A-Z]+%] ", "")
        assert(nynorsk == expected and nynorsk ~= english)
        -- A caption saved by an older version (English text only) is found and translated.
        local old = {flavour = english}
        assert(WoWStatusFlavour.text(old) == nynorsk)
    ''')
    for kind in ('level', 'introduction', 'loot', 'death', 'zone', 'quest', 'profession_learned', 'profession',
                 'dungeon', 'mount', 'reputation', 'unlock', 'pvp'):
        assert lua.eval(f'#WoWStatusFlavourNN.{kind}') == 100, kind


def test_pages_and_notifications_show_nynorsk():
    lua = actor('Thora')
    lua.execute('''
        WoWStatusLocale.set("nn")
        WoWStatusMainWindow.show("characters")
        assert(WoWStatusCharactersPage.sections[1].text.text == "Figurane dine")
        WoWStatusMainWindow.show("records")
        assert(WoWStatusRecordsPage.heading.text:find("Rekordar i", 1, true))
        WoWStatusPopups.preview("level"); WoWStatusPopups.tick()
        assert(WoWStatusLevelPopup.heading.text == "NYTT NIVÅ!")
        assert(WoWStatusLevelPopup.message.text:find("nådde nivå", 1, true))
    ''')


def shown_texts():
    """Every English text the addon shows, as the source spells it."""
    texts = []
    for path in sorted((ROOT / 'addon/shared').glob('*.lua')):
        if path.name.startswith(('Locale', 'Flavour')):
            continue
        source = path.read_text(encoding='utf-8')
        found = re.findall(r'\bT\("((?:[^"\\]|\\.)*)"\)', source)
        # Texts reaching T() through the windows' helpers and chat messages.
        found += re.findall(r'\b(?:label|button|text|check|checkbox|section|say|notify|report|refuse)\(\s*'
                            r'(?:[\w.]+\s*,\s*)?(?:"[a-z_]+"\s*,\s*)?"((?:[^"\\]|\\.)*)"\s*[,)]', source)
        # Lists of labels: guide steps, preview buttons, settings checkboxes.
        found += re.findall(r'\{title="([^"]*)"', source)
        found += re.findall(r'\{"[a-z_]+", ?"([A-Z][^"]*)"\}', source)
        for listed in re.findall(r'local (?:titles|names)=\{(.*?)\}', source, re.S):
            found += re.findall(r'[a-z_]+="([^"]*)"', listed)
        found = [t for t in found if t and not t.endswith(" ") and not t.startswith(("GameFont", "Interface", "Minimap"))
                 and "Discord" not in t and "Previewlock" not in t]
        for text in found:
            texts.append((path.name, text.replace('\\n', '\n')))
    return texts


def test_every_language_bank_covers_the_texts_the_windows_show():
    """Each registered bank, not Nynorsk by name: a new one is held to the same bar (#154)."""
    lua = make_lua()
    banks = lua.eval('WoWStatusLocale.BANKS')
    codes = sorted(banks.keys())
    assert codes == ['nn'], f'a new bank needs no code change, but this test should list it: {codes}'
    for code in codes:
        lua.eval('WoWStatusLocale.set')(code)
        t = lua.eval('WoWStatusLocale.T')
        missing = [f'{name}: {text}' for name, text in shown_texts()
                   if text not in SAME and t(text) == text]
        assert missing == [], f'{code} is missing:\n' + '\n'.join(missing)



def test_the_language_switch_is_labelled_when_the_settings_open():
    # Live report: the switch was an empty button until clicked.
    lua = make_lua()
    lua.execute('''
        WoWStatusPreviews.show()
        local panel = WoWStatusNotificationPreviews
        assert(panel.languageSwitch.text == "Bytt til nynorsk" and panel.language.text == "Language: English")
        assert(not panel.reload.visible)
        panel.languageSwitch.OnClick(panel.languageSwitch)
        assert(WoWStatusLocale.lang() == "nn" and panel.languageSwitch.text == "Switch to English")
        assert(panel.language.text == "Språk: Nynorsk" and panel.reload.visible and panel.reload.text == "Last på nytt")
    ''')


GERMAN = '''
    local add = WoWStatusLocale.language("deDE", "Deutsch", "Auf Deutsch umstellen")
    add({["Close"] = "Schlie\\195\\159en", ["Reactions"] = "Reaktionen"})
'''


def test_a_new_language_is_one_file_and_no_change_to_locale_lua():
    """What a LocaleDE.lua would do: register a bank, add texts, and be picked up (#154)."""
    lua = make_lua()
    lua.execute(GERMAN)
    assert lua.eval('WoWStatusLocale.set')('deDE') is True
    assert lua.eval('WoWStatusLocale.lang()') == 'deDE'
    assert lua.eval('WoWStatusLocale.T("Reactions")') == 'Reaktionen'
    # Per string, not per language: an untranslated text stays English.
    assert lua.eval('WoWStatusLocale.T("Records")') == 'Records'
    names = lua.eval('WoWStatusLocale.languages()')
    assert [names[i]['code'] for i in range(1, len(names) + 1)] == ['en', 'deDE', 'nn']


def test_the_client_locale_picks_the_language_until_the_player_chooses():
    lua = make_lua()
    lua.execute(GERMAN)
    lua.execute('WoWStatusDB.language = nil; __locale = "deDE"')
    assert lua.eval('WoWStatusLocale.lang()') == 'deDE'
    # A client with no bank, and an unreadable one, both stay English.
    lua.execute('__locale = "frFR"')
    assert lua.eval('WoWStatusLocale.lang()') == 'en'
    lua.execute('__locale = nil; local saved = GetLocale; GetLocale = nil')
    assert lua.eval('WoWStatusLocale.lang()') == 'en'


def test_a_saved_choice_wins_over_the_client_including_english():
    lua = make_lua()
    lua.execute(GERMAN)
    lua.execute('__locale = "deDE"')
    assert lua.eval('WoWStatusLocale.set')('en') is True
    assert lua.eval('WoWStatusDB.language') == 'en'
    assert lua.eval('WoWStatusLocale.lang()') == 'en'
    assert lua.eval('WoWStatusLocale.T("Reactions")') == 'Reactions'
    assert lua.eval('WoWStatusLocale.set')('nn') is True
    assert lua.eval('WoWStatusLocale.lang()') == 'nn'
    # An unknown code changes nothing.
    assert lua.eval('WoWStatusLocale.set')('xxXX') is False
    assert lua.eval('WoWStatusLocale.lang()') == 'nn'


def test_nynorsk_still_switches_both_ways_from_the_options_panel():
    lua = make_lua()
    assert lua.eval('WoWStatusLocale.nextLanguage()') == 'nn'
    lua.eval('WoWStatusLocale.set')('nn')
    assert lua.eval('WoWStatusLocale.nextLanguage()') == 'en'
    assert lua.eval('WoWStatusLocale.SWITCH.nn') == 'Bytt til nynorsk'
    assert lua.eval('WoWStatusLocale.SWITCH.en') == 'Switch to English'
