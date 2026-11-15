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
                 'Knights of the Silver Hand', 'knights-of-the-silver-hand', 'BLOODSAIL BUCCANEERS',
                 '1234567890123456', '8104-2275-3391-60', 'password password1', 'abcdefghijklmnop1',
                 'qwertyuiop asdfgh', 'Thora and the gang 2026', 'the knights of the silver hand!',
                 'dragonslayer2026', 'Ærlegegjengenfråvoss', 'Dragonslayer2026!', '2026dragonslayer',
                 'supercalifragilistic!'):
        assert weak(name), name
    for name in ('the weekend crew meets at nine', 'k7qm-4xfz-pr2d-9hwt-cn3b', 'Ærlege gjengen frå Voss 1999',
                 'the cat and the hat sat on a mat'):
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
        -- Replacing a name the player may have sent asks first.
        p.create.OnClick()
        assert(p.created:GetText() == name and p.status:GetText():find("different group", 1, true))
        p.create.OnClick()
        assert(p.created:GetText() ~= name)
        name = p.created:GetText()
        -- Closing and reopening keeps a name the player may already have sent.
        WoWStatusGroups.show()
        assert(p.created:GetText() == name and p.join:IsShown())
        p.input:SetText("half typed"); p.input.focused = false
        p.join.OnClick()
        assert(WoWStatusGroups.contains(character(), WoWStatusGroups.key(name)))
        assert(p.input:GetText() == "half typed" and not p.input.focused)  -- the Group ID box is left alone
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


def test_created_names_are_never_flagged_as_weak():
    lua = make_lua()
    lua.execute('''
        for _ = 1, 3000 do assert(not WoWStatusGroups.weak(WoWStatusGroups.generate())) end
    ''')


def test_pasting_the_created_name_or_joining_clears_what_it_replaces():
    lua = make_lua()
    lua.eval('SlashCmdList.WOWSTATUS')('groups')
    lua.execute('''
        local p = WoWStatusGroupWindow
        -- A pending "Add anyway" is taken back when another add replaces its warning.
        p.input:SetText("dawnwatch"); p.add.OnClick()
        assert(p.add:GetText() == "Add anyway")
        p.create.OnClick(); p.join.OnClick()
        assert(p.add:GetText() == "Add" and p.status:GetText() == "Groups saved for all characters.")
        p.add.OnClick()
        assert(not WoWStatusGroups.contains(character(), WoWStatusGroups.key("dawnwatch")))
        -- The created name pasted into Group ID: the box and Join it go away.
        p.create.OnClick()
        local name = p.created:GetText()
        p.input:SetText(name); p.add.OnClick()
        assert(WoWStatusGroups.contains(character(), WoWStatusGroups.key(name)))
        assert(p.created.value == nil and not p.join:IsShown())
    ''')


def test_create_is_disabled_with_eight_groups_and_names_the_mac_key():
    lua = make_lua(STUBS + 'function IsMacClient() return true end\n')
    lua.eval('SlashCmdList.WOWSTATUS')('groups')
    lua.execute('''
        local p = WoWStatusGroupWindow
        function p.create:SetEnabled(value) self.enabled = value end
        p.create.OnClick()
        assert(p.createHint:GetText():find("Cmd+C", 1, true))
        local names = {}
        for i = 1, 8 do names[i] = "group number " .. i .. " of eight" end
        WoWStatusGroups.update(table.concat(names, "\\n"), "")
        WoWStatusGroups.show()
        assert(p.create.enabled == false)
        p.rows[1].remove.OnClick()
        assert(p.create.enabled == true)
    ''')


def test_a_created_name_survives_a_reload_and_a_stale_replace_click_asks_again():
    lua = make_lua()
    lua.eval('SlashCmdList.WOWSTATUS')('groups')
    lua.execute('''
        local p = WoWStatusGroupWindow
        p.create.OnClick()
        local name = p.created:GetText()
        assert(WoWStatusDB.created_group == name)
        -- A /reload builds the window again: the saved name comes back.
        p.created.value = nil; p.created:SetText("")
        WoWStatusGroups.show()
        assert(p.created:GetText() == name and p.join:IsShown())
        -- The replace warning is disarmed by any later message or by reopening.
        p.create.OnClick()
        p.input:SetText("dawnwatch"); p.add.OnClick()
        p.create.OnClick()
        assert(p.created:GetText() == name)
        WoWStatusGroups.show(); p.create.OnClick()  -- armed by the click above, disarmed by reopening
        assert(p.created:GetText() == name)
        p.join.OnClick()
        assert(WoWStatusDB.created_group == nil and not p.join:IsShown())
    ''')
