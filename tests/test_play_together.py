"""'Play together now' (#156): online friends near your level, with Whisper and Invite."""
from pathlib import Path

from test_addon import lupa
from test_gamepad import FRAMES
from test_roster import pair, pump

ROOT = Path(__file__).parents[1]


def friend(thora, words, name, level, race='Dwarf', klass='WARRIOR', pid=None):
    """Thora receives a list line from Mira announcing another character."""
    words = list(words)
    if pid:
        words[2] = pid
    words[4], words[5], words[7], words[8] = name, race, klass, str(level)
    thora.eval('WoWStatusRoster.receive')(' '.join(words), 'Mira-TestRealm', 'WHISPER')


def setup(level=20, peers=('Thora-TestRealm', 'Mira-TestRealm')):
    mira, thora = pair()
    words = next(line for line in pump(mira, thora) if line.startswith('C ')).split(' ')
    thora.execute(f'__level = {level}; __peers = {{{",".join(chr(34) + p + chr(34) for p in peers)}}}')
    # Buttons in this harness keep their enabled state, as the game's do.
    thora.execute('getmetatable(CreateFrame("Button")).__index.SetEnabled = function(self, on) self.enabled = on end')
    return mira, thora, words


def together(lua):
    data = lua.eval('WoWStatusRoster.together()')
    rows = [(r.name, r.level, r.diff) for r in data.rows.values()]
    return data, rows


def online(lua, *names):
    lua.execute('__peers = {' + ','.join(f'"{n}"' for n in ('Thora-TestRealm',) + names) + '}')


def test_lists_online_friends_within_the_window_closest_first():
    _, thora, words = setup()
    for name, level in (('Mira-TestRealm', 22), ('Bo-TestRealm', 19), ('Cy-TestRealm', 30), ('Di-TestRealm', 20)):
        friend(thora, words, name, level)
    friend(thora, words, 'Away-TestRealm', 20)          # listed, but not online
    online(thora, 'Mira-TestRealm', 'Bo-TestRealm', 'Cy-TestRealm', 'Di-TestRealm')
    data, rows = together(thora)
    assert data.level == 20 and data.range == 3
    assert rows == [('Di-TestRealm', 20, 0), ('Bo-TestRealm', 19, -1), ('Mira-TestRealm', 22, 2)]
    assert data.above is None and data.below is None


def test_with_nobody_in_range_the_nearest_above_and_below_are_offered():
    _, thora, words = setup()
    friend(thora, words, 'Mira-TestRealm', 26)
    friend(thora, words, 'Cy-TestRealm', 31)
    friend(thora, words, 'Bo-TestRealm', 12)
    online(thora, 'Mira-TestRealm', 'Cy-TestRealm', 'Bo-TestRealm')
    data, rows = together(thora)
    assert rows == []
    assert data.above.name == 'Mira-TestRealm' and data.above.diff == 6
    assert data.below.name == 'Bo-TestRealm' and data.below.diff == -8
    thora.eval('WoWStatusMainWindow.show')('characters')
    page = thora.eval('WoWStatusCharactersPage')
    assert page.togetherBar.note.text == 'Nobody that close. Nearest online:'
    assert page.together[1].level.text == 'Level 26 (+6)' and page.together[2].level.text == 'Level 12 (-8)'


def test_only_characters_from_a_shared_list_that_the_viewer_may_see():
    _, thora, words = setup(level=1)
    group, pid = words[1], words[2]
    # A log sender that never shared a list, with a level from the log.
    thora.execute('''WoWStatusJournal.received({sender="Eldrin-TestRealm", nonce="a1", kind="level", level=1,
        at=time(), group_id=next(character().group_ids)})''')
    online(thora, 'Mira-TestRealm', 'Eldrin-TestRealm')
    assert [r[0] for r in together(thora)[1]] == ['Mira-TestRealm']
    # Mira hides the character from the list: it leaves the band too.
    thora.eval('WoWStatusRoster.receive')(f'Z {group} {pid} Mira-TestRealm 1 1', 'Mira-TestRealm', 'WHISPER')
    assert together(thora)[1] == []
    # A player who stops sharing their list shows nothing.
    _, thora, words = setup(level=1)
    online(thora, 'Mira-TestRealm')
    assert len(together(thora)[1]) == 1
    thora.eval('WoWStatusRoster.receive')(f'X {words[1]} {words[2]}', 'Mira-TestRealm', 'WHISPER')
    assert together(thora)[1] == []


def test_the_window_is_adjustable_remembered_and_clamped():
    _, thora, words = setup()
    friend(thora, words, 'Mira-TestRealm', 26)
    online(thora, 'Mira-TestRealm')
    thora.eval('WoWStatusMainWindow.show')('characters')
    bar = thora.eval('WoWStatusCharactersPage.togetherBar')
    assert bar.label.text == 'Level range: ±3' and together(thora)[1] == []
    for _ in range(3):
        bar.more.OnClick(bar.more)
    assert thora.eval('WoWStatusDB.roster.together_range') == 6
    assert [r[0] for r in together(thora)[1]] == ['Mira-TestRealm']
    for _ in range(20):
        thora.eval('WoWStatusRoster.setTogetherRange')(thora.eval('WoWStatusRoster.togetherRange()') + 1)
    assert thora.eval('WoWStatusRoster.togetherRange()') == 10
    assert bar.more.enabled is False and bar.less.enabled is True
    thora.eval('WoWStatusRoster.setTogetherRange')(-4)
    assert thora.eval('WoWStatusRoster.togetherRange()') == 1 and bar.less.enabled is False
    for bad in ('"x"', '0', '11', '2.5', '0/0', '{}'):
        thora.execute(f'WoWStatusDB.roster.together_range = {bad}')
        assert thora.eval('WoWStatusRoster.togetherRange()') == 3, bad


def test_invite_is_disabled_where_the_game_would_refuse_it():
    _, thora, words = setup()
    friend(thora, words, 'Mira-TestRealm', 20)
    friend(thora, words, 'Grom-TestRealm', 20, race='Orc', klass='WARRIOR')
    friend(thora, words, 'Pan-TestRealm', 20, race='Pandaren', klass='MONK')
    friend(thora, words, 'Far-OtherRealm', 20)
    online(thora, 'Mira-TestRealm', 'Grom-TestRealm', 'Pan-TestRealm', 'Far-OtherRealm')
    blocked = {r.name: r.blocked for r in thora.eval('WoWStatusRoster.together()').rows.values()}
    # A friend on another realm is online only where the game groups across realms.
    assert blocked == {'Mira-TestRealm': None, 'Grom-TestRealm': 'Different faction',
                       'Pan-TestRealm': None, 'Far-OtherRealm': None}
    # Already in the party.
    thora.execute('function UnitName(unit) if unit == "party1" then return "Mira" end return "Thora" end')
    assert thora.eval('WoWStatusRoster.inviteBlocked({name="Mira-TestRealm", race="Dwarf"})') == 'Already in your group'
    thora.eval('WoWStatusMainWindow.show')('characters')
    rows = thora.eval('WoWStatusCharactersPage.together')
    by_name = {rows[i].whisper.target.name: rows[i] for i in range(1, len(rows) + 1) if rows[i].IsShown(rows[i])}
    assert by_name['Mira-TestRealm'].invite.enabled is False
    assert by_name['Mira-TestRealm'].info.text == '|cffff7777Already in your group|r'
    # The other faction can neither be invited nor whispered by name.
    assert by_name['Grom-TestRealm'].invite.enabled is False and by_name['Grom-TestRealm'].whisper.enabled is False
    assert by_name['Pan-TestRealm'].whisper.enabled is True
    assert by_name['Pan-TestRealm'].invite.enabled is True


def test_whisper_and_invite_use_the_games_own_actions_and_send_nothing_of_ours():
    mira, thora, words = setup()
    friend(thora, words, 'Mira-TestRealm', 21)
    online(thora, 'Mira-TestRealm')
    thora.execute('''
        __tells, __invites = {}, {}
        ChatFrameUtil = {SendTell=function(name) table.insert(__tells, name) end}
        C_PartyInfo = {InviteUnit=function(name) table.insert(__invites, name) end}
    ''')
    before = thora.eval('#__sent')
    thora.eval('WoWStatusMainWindow.show')('characters')
    row = thora.eval('WoWStatusCharactersPage.together[1]')
    row.whisper.OnClick(row.whisper)
    row.invite.OnClick(row.invite)
    bar = thora.eval('WoWStatusCharactersPage.togetherBar')
    bar.more.OnClick(bar.more)
    assert list(thora.eval('__tells').values()) == ['Mira']
    assert list(thora.eval('__invites').values()) == ['Mira']
    assert thora.eval('#__sent') == before
    # Invite rests while the invite waits, so a second click sends nothing.
    row = thora.eval('WoWStatusCharactersPage.together[1]')
    assert row.invite.enabled is False and row.info.text == '|cffff7777Invite sent|r'
    assert thora.eval('WoWStatusRoster.partyInvite')(row.invite.target) is False
    assert len(thora.eval('__invites')) == 1
    thora.execute('__mono = __mono + 61')
    assert thora.eval('WoWStatusRoster.together().rows[1].blocked') is None
    # Another realm keeps its realm in the name; a blocked invite never reaches the game.
    assert thora.eval('WoWStatusRoster.chatTarget("Far-OtherRealm")') == 'Far-OtherRealm'
    assert thora.eval('WoWStatusRoster.partyInvite({name="Orc-TestRealm", race="Orc"})') is False
    assert len(thora.eval('__invites')) == 1


def test_forever_whispers_and_invites_by_the_plain_name_on_any_internal_realm():
    _, thora, _ = setup()
    thora.execute('WoWStatusAdapter.full_names = true')
    assert thora.eval('WoWStatusRoster.chatTarget("Mira Stone-CAMWOWEU5Realm3PvE")') == 'Mira Stone'
    assert thora.eval('WoWStatusRoster.inviteBlocked({name="Mira Stone-CAMWOWEU5Realm3PvE", race="Dwarf"})') is None


def test_the_band_follows_a_friend_logging_out_without_a_sync():
    _, thora, words = setup()
    friend(thora, words, 'Mira-TestRealm', 20)
    online(thora, 'Mira-TestRealm')
    thora.eval('WoWStatusMainWindow.show')('characters')
    page = thora.eval('WoWStatusCharactersPage')
    assert page.together[1].IsShown(page.together[1])
    online(thora)
    # Recently heard friends count as online for a while (Popups.withKnown), as on the cards.
    thora.execute('__now = __now + 1900')
    for step in range(1, 30):
        thora.execute(f'__mono = 500 + {step}')
        thora.eval('WoWStatusRoster.tick')()
    assert not page.together[1].IsShown(page.together[1])
    assert page.togetherBar.note.text == 'No friends who share their list are online right now.'
    online(thora, 'Mira-TestRealm')
    for step in range(1, 30):
        thora.execute(f'__mono = 600 + {step}')
        thora.eval('WoWStatusRoster.tick')()
    assert page.together[1].IsShown(page.together[1])


def test_the_band_collapses_like_a_section_and_keeps_the_existing_sections():
    _, thora, words = setup()
    online(thora, 'Mira-TestRealm')
    thora.eval('WoWStatusMainWindow.show')('characters')
    page = thora.eval('WoWStatusCharactersPage')
    head = page.togetherHead
    assert head.text.text.startswith('Play together now')
    assert page.sections[1].text.text == 'Your characters'
    head.OnClick(head)
    assert thora.eval('WoWStatusRoster.collapsed("together")') is True
    assert not page.togetherBar.IsShown(page.togetherBar) and not page.together[1].IsShown(page.together[1])
    head.OnClick(head)
    assert page.together[1].IsShown(page.together[1])


def test_an_unknown_own_level_says_so():
    _, thora, _ = setup(level=0)
    thora.execute('character().roster_info.level = nil')
    online(thora, 'Mira-TestRealm')
    assert thora.eval('WoWStatusRoster.together().level') is None
    thora.eval('WoWStatusMainWindow.show')('characters')
    assert thora.eval('WoWStatusCharactersPage.togetherBar.note.text') == 'Your level is not known yet.'


def test_nynorsk_labels():
    _, thora, _ = setup(level=1)
    online(thora, 'Mira-TestRealm')
    thora.execute('WoWStatusLocale.set("nn")')
    thora.eval('WoWStatusMainWindow.show')('characters')
    page = thora.eval('WoWStatusCharactersPage')
    assert page.togetherHead.text.text.startswith('Spel saman no')
    assert page.together[1].whisper.text == 'Kviskre' and page.together[1].invite.text == 'Inviter'


def test_whisper_invite_and_range_buttons_are_reachable_with_a_controller():
    runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
    runtime.execute('unpack = unpack or table.unpack')
    runtime.execute(FRAMES)
    runtime.execute((ROOT / 'addon/shared/Gamepad.lua').read_text(encoding='utf-8'))
    runtime.execute('''
        main = window("WoWStatusMainFrame", 100, 100, 760, 560)
        WoWStatusMainWindow = {pages=function() return {"characters"} end, active=function() return "characters" end,
            show=function() main:Show() end, hide=function() main:Hide() end, back=function() return false end,
            refresh=function() end}
        local methods=getmetatable(CreateFrame("Frame")).__index
        function methods:SetSize(w,h) if self.rect then self.rect[3],self.rect[4]=w,h end end
        function methods:SetText(text) self.text=text end
        function methods:SetTexture(path) self.texture=path end
        function methods:CreateFontString() return CreateFrame("FontString",nil,self) end
        function methods:SetJustifyH() end
        function methods:SetScrollChild(child) self.child=child end
        function methods:SetShown(value) self.visible=value end
        WoWStatusLocale={T=function(text) return text end,F=string.format}
        WoWStatusSafe={}
        WoWStatusUI={text=function(parent) return CreateFrame("FontString",nil,parent) end,
            call=function() return false end, classColour=function() end}
        WoWStatusMainWindow.register=function(key,title,build) __build=build end
    ''')
    runtime.execute((ROOT / 'addon/shared/Roster.lua').read_text(encoding='utf-8'))
    runtime.execute('''
        local R=WoWStatusRoster
        R.collapsed=function() return false end
        R.onlineOnly=function() return false end
        R.groups=function() return {} end
        R.sections=function() return {} end
        R.together=function() return {level=20, range=3, online=1, inRange=1,
            rows={{name="Mira-Realm", class="WARRIOR", level=21, diff=1}}} end
        local page=__build(main); page.visible=true; page.list.visible=true
        R.render()
        local row, bar = page.together[1], page.togetherBar
        row.whisper.rect={600,500,88,22}; row.invite.rect={700,500,88,22}
        bar.less.rect={320,530,28,22}; bar.more.rect={352,530,28,22}
        local reached={}
        for _,control in ipairs(WoWStatusGamepad.controls(main,{main})) do reached[control]=true end
        assert(reached[row.whisper] and reached[row.invite] and reached[bar.less] and reached[bar.more])
        assert(row.whisper.kind=="Button" and row.whisper.scripts.OnClick and row.invite.scripts.OnClick)
    ''')


def test_the_heading_counts_everyone_in_range_beyond_the_rows_shown():
    _, thora, words = setup()
    names = [f'F{chr(97 + i)}-TestRealm' for i in range(10)]
    for name in names:
        friend(thora, words, name, 20)
    online(thora, *names)
    data, rows = together(thora)
    assert data.inRange == 10 and len(rows) == 8
    thora.eval('WoWStatusMainWindow.show')('characters')
    assert '10 within 3 levels' in thora.eval('WoWStatusCharactersPage.togetherHead.text.text')


def test_party_changes_redraw_once_on_the_next_tick():
    _, thora, words = setup()
    friend(thora, words, 'Mira-TestRealm', 20)
    online(thora, 'Mira-TestRealm')
    thora.eval('WoWStatusMainWindow.show')('characters')
    thora.execute('''
        __renders = 0
        local render = WoWStatusRoster.render
        WoWStatusRoster.render = function(...) __renders = __renders + 1; return render(...) end
        function UnitName(unit) if unit == "party1" then return "Mira" end return "Thora" end
        for _ = 1, 25 do fire("GROUP_ROSTER_UPDATE") end
    ''')
    assert thora.eval('__renders') == 0
    thora.eval('WoWStatusRoster.tick')()
    assert thora.eval('__renders') == 1
    assert thora.eval('WoWStatusCharactersPage.together[1].info.text') == '|cffff7777Already in your group|r'
