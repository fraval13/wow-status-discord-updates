"""Group names nobody can guess (issue #151): generator and weak-name warning."""
import re

from test_addon import STUBS, make_lua

ALPHABET = '23456789abcdefghjkmnpqrstuvwxyz'
GENERATED = re.compile(rf'^[{ALPHABET}]{{4}}(-[{ALPHABET}]{{4}}){{4}}$')


def test_generated_names_are_long_unique_and_round_trip_through_key():
    lua = make_lua()
    generate, key, weak = (lua.eval(f'WoWStatusGroups.{name}') for name in ('generate', 'key', 'weak'))
    names = [generate() for _ in range(500)]
    assert len(set(names)) == len(names)
    for name in names:
        assert GENERATED.match(name), name
        group_id, cleaned = key(name)[:2]
        assert cleaned == name and lua.eval('WoWStatusGroups.valid')(group_id)
        assert key(name.upper())[0] == group_id  # friends may type it in capitals
        assert not weak(name)
    # Every symbol turns up: the draw covers the whole alphabet.
    assert set(''.join(names).replace('-', '')) == set(ALPHABET)


def test_a_new_session_does_not_repeat_the_last_sessions_names():
    first, second = make_lua(), make_lua(STUBS + 'function GetTime() return 4242.5 end\n')
    assert first.eval('WoWStatusGroups.generate()') != second.eval('WoWStatusGroups.generate()')


def test_weak_names_are_short_plain_repetitive_or_this_players_names():
    lua = make_lua(STUBS + '''
        function GetGuildInfo(unit) return "Knights of the Silver Hand", "Member", 3 end
        function GetRealmName() return "Bloodsail Buccaneers" end
    ''')
    weak = lua.eval('WoWStatusGroups.weak')
    for name in ('dawnwatch', 'Weekend Crew', 'supercalifragilistic', 'aaaa bbbb aaaa bbbb',
                 'Knights of the Silver Hand', 'knights-of-the-silver-hand', 'BLOODSAIL BUCCANEERS'):
        assert weak(name), name
    for name in ('the weekend crew meets at nine', 'k7qm-4xfz-pr2d-9hwt-cn3b', 'Ærlege gjengen frå Voss 1999'):
        assert not weak(name), name
    assert not weak('') and not weak(None)


def test_weak_names_still_save_and_saved_groups_still_join():
    lua = make_lua()
    lua.execute('''
        local ok = WoWStatusGroups.update("dawnwatch", "")
        assert(ok and WoWStatusGroups.contains(character(), WoWStatusGroups.key("dawnwatch")))
        WoWStatusGroups.init(WoWStatusDB, character, function() end)
        assert(WoWStatusGroups.contains(character(), WoWStatusGroups.key("dawnwatch")))
        ok = WoWStatusGroups.join("emberhold")
        assert(ok and WoWStatusGroups.contains(character(), WoWStatusGroups.key("emberhold")))
    ''')


def test_create_a_group_shows_a_copyable_name_and_joins_it():
    lua = make_lua()
    lua.eval('SlashCmdList.WOWSTATUS')('groups')
    lua.execute('''
        local p = WoWStatusGroupWindow
        assert(p.create:GetText() == "Create a group" and not p.created:IsShown() and not p.join:IsShown())
        assert(p.protection:GetText():find("never in public chat", 1, true))
        p.create.OnClick()
        local name = p.created:GetText()
        assert(name == p.created.value and p.created:IsShown() and p.join:IsShown() and not p.created.focused)
        assert(p.createHint:GetText():find("type exactly this name", 1, true))
        -- Read-only: typing puts the name back.
        p.created:SetText("changed"); p.created.OnTextChanged(p.created, true)
        assert(p.created:GetText() == name)
        p.create.OnClick()
        assert(p.created:GetText() ~= name)  -- each click makes a new one
        name = p.created:GetText()
        p.join.OnClick()
        assert(WoWStatusGroups.contains(character(), WoWStatusGroups.key(name)))
        assert(p.rows[1].label:GetText() == name and not p.created:IsShown() and not p.join:IsShown())
        assert(p.add:GetText() == "Add")  -- a strong name never asks
    ''')


def test_editing_a_warned_name_asks_again():
    lua = make_lua()
    lua.eval('SlashCmdList.WOWSTATUS')('groups')
    lua.execute('''
        local p = WoWStatusGroupWindow
        p.input:SetText("dawnwatch"); p.add.OnClick()
        assert(p.add:GetText() == "Add anyway")
        p.input:SetText("emberhold"); p.input.OnTextChanged(p.input, true)
        assert(p.add:GetText() == "Add")
        p.add.OnClick()
        assert(next(WoWStatusDB.account_groups) == nil and p.add:GetText() == "Add anyway")
        p.add.OnClick()
        assert(WoWStatusGroups.contains(character(), WoWStatusGroups.key("emberhold")))
        -- Reopening the window forgets a pending warning.
        p.input:SetText("dawnwatch"); p.add.OnClick()
        WoWStatusGroups.show()
        assert(p.add:GetText() == "Add")
    ''')


def test_the_guide_recommends_creating_a_group():
    lua = make_lua(guide=True)
    lua.execute('''
        local frame = WoWStatusGuideFrame
        frame.next.OnClick(frame.next)
        assert(frame.body.text:find("Create a group", 1, true) and frame.body.text:find("agreed on", 1, true))
        WoWStatusLocale.set("nn")
        frame.back.OnClick(frame.back); frame.next.OnClick(frame.next)
        assert(frame.body.text:find("Lag ei gruppe", 1, true))
    ''')
