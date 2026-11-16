"""One-time What's New page (#63), generated from CHANGELOG.md."""
import importlib.util
import re
import sys
import tomllib
from pathlib import Path

import pytest
from test_addon import STUBS, make_lua

ROOT = Path(__file__).parents[1]


def load():
    spec = importlib.util.spec_from_file_location('whats_new', ROOT / 'scripts/whats_new.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


whats_new = load()

DATA = '''
WoWStatusWhatsNewData = {
    {version="1.2.0", notes={"Newest thing"}},
    {version="1.1.0", notes={"Middle thing"}},
    {version="1.0.0", notes={"Oldest thing"}},
}
'''


def test_generated_lua_is_up_to_date():
    assert whats_new.main(['--check']) == 0


def test_newest_changelog_section_is_the_project_version():
    version = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    assert whats_new.parse((ROOT / 'CHANGELOG.md').read_text(encoding='utf-8'))[0][0] == version


def test_parser_skips_unreleased_and_rejects_bad_notes():
    text = '# What\'s New\n\nintro\n\n## Unreleased\n\n- soon\n\n## 1.1.0\n\n- b\n\n## 1.0.0\n\n- a\n'
    assert whats_new.parse(text) == [('1.1.0', ['b']), ('1.0.0', ['a'])]
    for bad in ('## 1.0.0\n\n- a|cff\n', '## 1.0.0\n\n- ' + 'x' * 121 + '\n', '## v1\n\n- a\n',
                '## 1.0.0\n\n- a\n\n## 1.1.0\n\n- b\n', '## 1.0.0\n\n', '## 1.0.0\n\ntext\n',
                '## 1.0.0\n\n- Fixed __AFK__ status\n'):
        with pytest.raises(ValueError):
            whats_new.parse(bad)


def test_pending_note_files_in_the_repository_are_valid():
    # The release job promotes these on main; a bad note must fail in its own PR.
    whats_new.pending_notes(ROOT)


def test_changelog_has_no_unreleased_section():
    text = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    assert not re.search(r'^## Unreleased\s*$', text, re.MULTILINE), (
        'Put pending notes in a new changelog.d/<issue>-<short-name>.md file, not under '
        '## Unreleased in CHANGELOG.md; see changelog.d/README.md')


def test_pending_note_files_are_read_in_issue_number_order(tmp_path):
    assert whats_new.pending_notes(tmp_path) == []
    folder = tmp_path / 'changelog.d'
    folder.mkdir()
    (folder / 'README.md').write_text('Not a note\n', encoding='utf-8')
    (folder / '.DS_Store').write_text('finder junk', encoding='utf-8')
    (folder / '20-b.md').write_text('- b1\n\n- b2\n', encoding='utf-8')
    (folder / '100-a.md').write_text('\ufeff- a\r\n', encoding='utf-8')
    (folder / 'tidy-up.md').write_text('- c\n', encoding='utf-8')
    # Issue numbers sort numerically; names without one go last, alphabetically.
    assert whats_new.pending_notes(tmp_path) == [(folder / '20-b.md', ['b1', 'b2']),
                                                 (folder / '100-a.md', ['a']),
                                                 (folder / 'tidy-up.md', ['c'])]


@pytest.mark.parametrize('name, text, message', [
    ('1-a.md', '- a|cff\n', 'printable'),
    ('1-a.md', '- ' + 'x' * 121 + '\n', 'printable'),
    ('1-a.md', '- Type `/wstatus news`\n', 'markup'),
    ('1-a.md', '- A **bold** change\n', 'markup'),
    ('1-a.md', '## 1.0.0\n- a\n', 'only "- " notes'),
    ('1-a.md', 'text\n', 'only "- " notes'),
    ('1-a.md', '\n', 'has no notes'),
    ('1-A.md', '- a\n', 'named like'),
    ('1-a.txt', '- a\n', 'named like'),
    ('1 a.md', '- a\n', 'named like'),
    ('.1-a.md', '- a\n', 'named like'),
])
def test_invalid_pending_note_files_are_rejected(tmp_path, name, text, message):
    folder = tmp_path / 'changelog.d'
    folder.mkdir()
    (folder / name).write_text(text, encoding='utf-8')
    with pytest.raises(ValueError, match=message):
        whats_new.pending_notes(tmp_path)


def test_note_file_that_is_not_utf8_names_the_file(tmp_path):
    folder = tmp_path / 'changelog.d'
    folder.mkdir()
    (folder / '1-a.md').write_text('- a\n', encoding='utf-16')
    with pytest.raises(ValueError, match='1-a.md: save the note file as UTF-8'):
        whats_new.pending_notes(tmp_path)


def test_check_fails_on_an_invalid_pending_note_file(tmp_path, monkeypatch, capsys):
    folder = tmp_path / 'changelog.d'
    folder.mkdir()
    (folder / '1-a.md').write_text('oops\n', encoding='utf-8')
    monkeypatch.setattr(whats_new, 'ROOT', tmp_path)
    assert whats_new.main(['--check']) == 1
    assert 'changelog.d/1-a.md:1' in capsys.readouterr().out


def test_lua_strings_are_escaped():
    lua = make_lua()
    rendered = whats_new.render([('1.0.0', ['Say "hi" \\ bye'])])
    lua.execute(rendered)
    assert lua.eval('WoWStatusWhatsNewData[1].notes[1]') == 'Say "hi" \\ bye'


def make(version, saved=None):
    # Swap in fixed notes so the tests do not depend on the real changelog.
    stubs = STUBS + f'C_AddOns = {{GetAddOnMetadata=function() return "{version}" end}}\n'
    if saved is not None:
        stubs += f'WoWStatusDB = {saved}\n'
    original = Path.read_text

    def read_text(self, *args, **kwargs):
        if self.name == 'WhatsNewData.lua':
            return DATA
        return original(self, *args, **kwargs)

    Path.read_text = read_text
    try:
        return make_lua(stubs)
    finally:
        Path.read_text = original


def shown(lua):
    return lua.eval('WoWStatusWhatsNewFrame ~= nil and WoWStatusWhatsNewFrame:IsShown() == true')


def test_fresh_install_does_not_show_the_page():
    lua = make('1.2.0')
    assert not shown(lua)
    assert lua.eval('WoWStatusDB.whats_new_seen') == '1.2.0'


def test_update_shows_every_newer_section_once():
    lua = make('1.2.0', '{version=1, characters={}, whats_new_seen="1.0.0"}')
    assert shown(lua)
    text = lua.eval('WoWStatusWhatsNewFrame.body.text')
    assert 'Newest thing' in text and 'Middle thing' in text and 'Oldest thing' not in text
    assert lua.eval('WoWStatusDB.whats_new_seen') == '1.2.0'
    lua.execute('WoWStatusWhatsNewFrame:Hide()')
    assert lua.eval('WoWStatusWhatsNew.check(WoWStatusDB)') is False


def test_update_from_before_the_page_existed_shows_only_the_newest_section():
    lua = make('1.2.0', '{version=1, characters={}}')
    text = lua.eval('WoWStatusWhatsNewFrame.body.text')
    assert 'Newest thing' in text and 'Middle thing' not in text


def test_same_or_older_version_shows_nothing():
    assert not shown(make('1.2.0', '{version=1, characters={}, whats_new_seen="1.2.0"}'))
    lua = make('1.1.0', '{version=1, characters={}, whats_new_seen="1.2.0"}')
    assert not shown(lua)
    assert lua.eval('WoWStatusDB.whats_new_seen') == '1.2.0'


def test_news_command_reopens_the_page():
    lua = make('1.2.0')
    lua.eval('SlashCmdList.WOWSTATUS')('news')
    assert shown(lua)
    assert 'Newest thing' in lua.eval('WoWStatusWhatsNewFrame.body.text')


def test_version_comparison_is_numeric():
    lua = make('1.2.0')
    assert lua.eval('WoWStatusWhatsNew.newer("0.14.10", "0.14.9")') is True
    assert lua.eval('WoWStatusWhatsNew.newer("0.14.9", "0.14.10")') is False
    assert lua.eval('WoWStatusWhatsNew.newer("unknown", "0.1.0")') is False
