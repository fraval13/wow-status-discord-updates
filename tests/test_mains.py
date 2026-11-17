"""A player's main character and the Players ranking on the Leaderboard (#200)."""
import pytest
from test_client_compatibility import client_runtime
from test_roster import pair, pump

ALT = '''
    local original=character()
    WoWStatusDB.characters.alt={identity={name="Bank Person",realm="TestRealm",client=WoWStatusAdapter.client_id},
        settings=original.settings,events={},
        roster_info={race="Dwarf",sex=3,class="WARRIOR",level=WoWStatusAdapter.max_level or 60,at=1}}
    -- The harness's character() returns any saved character; keep it the played one.
    function character() return original end
'''


def owner_with_alt():
    mira, thora = pair()
    mira.execute(ALT)
    pump(mira, thora)
    return mira, thora


def group(lua):
    return lua.eval('next(character().group_ids)')[0]


def frank(lua):
    """Frank's entry in the Players ranking of the receiver's group, as a dict."""
    lua.execute('''
        __frank=nil
        for _, entry in ipairs(WoWStatusRoster.players(next(character().group_ids))) do
            if entry.name=="Frank" then __frank=entry end
        end
    ''')
    main = lua.eval('__frank and __frank.main.name')
    return {'main': main, 'chosen': lua.eval('__frank and __frank.chosen'),
            'alts': [lua.eval(f'__frank.alts[{i}].name') for i in range(1, (lua.eval('__frank and #__frank.alts') or 0) + 1)]}


def test_players_ranking_has_one_row_per_player_with_a_highest_level_default():
    _, thora = owner_with_alt()
    entry = frank(thora)
    assert entry == {'main': 'Bank Person-TestRealm', 'chosen': False, 'alts': ['Mira-TestRealm']}
    # The character ranking is unchanged: both of Frank's characters, and Thora's own.
    names = thora.eval('(function() local t={} for _, row in ipairs(WoWStatusRoster.leaderboard(next(character().group_ids))) '
                       'do t[#t+1]=row.name end table.sort(t) return table.concat(t,",") end)()')
    assert names == 'Bank Person-TestRealm,Mira-TestRealm,Thora-TestRealm'
    assert thora.eval('#WoWStatusRoster.players(next(character().group_ids))') == 2


def test_a_chosen_main_reaches_friends_and_a_second_claim_replaces_the_first():
    mira, thora = owner_with_alt()
    g = group(mira)
    assert mira.eval(f'WoWStatusRoster.setMain("{g}", "Mira-TestRealm")') is True
    packets = pump(mira, thora, start=300)
    # Only the main travels again, not the whole list.
    assert packets == [f'W {g} {mira.eval("WoWStatusDB.roster.id")} Mira-TestRealm']
    assert frank(thora) == {'main': 'Mira-TestRealm', 'chosen': True, 'alts': ['Bank Person-TestRealm']}
    assert mira.eval(f'WoWStatusRoster.setMain("{g}", "Bank Person-TestRealm")') is True
    pump(mira, thora, start=600)
    assert frank(thora)['main'] == 'Bank Person-TestRealm' and frank(thora)['chosen'] is True
    assert thora.eval(f'(function() local n=0 for _ in pairs(WoWStatusDB.roster.players["{mira.eval("WoWStatusDB.roster.id")}"].mains) '
                      'do n=n+1 end return n end)()') == 1
    # Back to Automatic: "-" clears it, and the default reads as a default again.
    assert mira.eval(f'WoWStatusRoster.setMain("{g}", nil)') is True
    assert f'W {g} {mira.eval("WoWStatusDB.roster.id")} -' in pump(mira, thora, start=900)
    assert frank(thora)['chosen'] is False


def test_a_forged_claim_or_one_from_outside_the_group_is_dropped():
    mira, thora = owner_with_alt()
    g, pid = group(mira), mira.eval('WoWStatusDB.roster.id')
    receive = thora.eval('WoWStatusRoster.receive')
    assert receive(f'W {g} {pid} Stranger-TestRealm', 'Mira-TestRealm', 'WHISPER') is False
    assert receive(f'W {g} {pid} Bad|cff-TestRealm', 'Mira-TestRealm', 'WHISPER') is False
    assert receive(f'W {g} 0123456789abcdef Mira-TestRealm', 'Mira-TestRealm', 'WHISPER') is False
    assert receive(f'W {g} {pid} Mira-TestRealm', 'Outsider-TestRealm', 'WHISPER') is False
    assert receive(f'W {g} {pid} Mira-TestRealm', 'Mira-TestRealm', 'GUILD') is False
    assert frank(thora)['chosen'] is False
    assert receive(f'W {g} {pid} Mira-TestRealm', 'Mira-TestRealm', 'WHISPER') is True
    assert frank(thora)['main'] == 'Mira-TestRealm'


def test_a_hidden_main_is_ignored_and_never_becomes_the_default():
    mira, thora = owner_with_alt()
    g, pid = group(mira), mira.eval('WoWStatusDB.roster.id')
    assert mira.eval(f'WoWStatusRoster.setMain("{g}", "Bank Person-TestRealm")') is True
    pump(mira, thora, start=300)
    assert frank(thora)['main'] == 'Bank Person-TestRealm'
    # Hiding the main: it is not shared as a main, and the friend's stale claim is ignored.
    mira.execute('assert(WoWStatusRoster.setHidden(WoWStatusDB.characters.alt,true))')
    assert mira.eval(f'WoWStatusRoster.ownMain("{g}")') is None
    packets = pump(mira, thora, start=600)
    assert f'W {g} {pid} -' in packets
    assert frank(thora) == {'main': 'Mira-TestRealm', 'chosen': False, 'alts': []}
    # A replayed claim for the hidden character changes nothing.
    receive = thora.eval('WoWStatusRoster.receive')
    receive(f'W {g} {pid} Bank Person-TestRealm', 'Mira-TestRealm', 'WHISPER')
    assert frank(thora) == {'main': 'Mira-TestRealm', 'chosen': False, 'alts': []}
    # A hidden character cannot be chosen either.
    assert mira.eval(f'WoWStatusRoster.setMain("{g}", "Bank Person-TestRealm")') is False
    assert mira.eval('WoWStatusRoster.setMain("not-a-group", "Mira-TestRealm")') is False


def test_an_old_player_id_claim_does_not_outlive_a_reinstall():
    mira, thora = owner_with_alt()
    g = group(mira)
    assert mira.eval(f'WoWStatusRoster.setMain("{g}", "Bank Person-TestRealm")') is True
    pump(mira, thora, start=300)
    assert frank(thora)['chosen'] is True
    # A reinstall: a new player ID with no main chosen, under the same player name.
    mira.execute('WoWStatusDB.roster.id="abcdefabcdef0123"; WoWStatusDB.roster.mains=nil; WoWStatusRoster.changed()')
    thora.execute('__mono=(__mono or 0)+5; local t=time; function time() return t()+60 end')
    pump(mira, thora, start=600)
    assert thora.eval('(function() local n=0 for _ in pairs(WoWStatusDB.roster.players) do n=n+1 end return n end)()') == 2
    assert frank(thora)['chosen'] is False


def test_cycling_the_main_queues_one_line_per_member():
    mira, thora = owner_with_alt()
    g = group(mira)
    for name in ('"Bank Person-TestRealm"', '"Mira-TestRealm"', 'nil', '"Mira-TestRealm"'):
        assert mira.eval(f'WoWStatusRoster.setMain("{g}", {name})') is True
    packets = pump(mira, thora, start=300)
    assert packets == [f'W {g} {mira.eval("WoWStatusDB.roster.id")} Mira-TestRealm']


def test_no_main_line_is_sent_until_a_main_was_ever_chosen():
    mira, thora = pair()
    assert not any(line.startswith('W ') for line in pump(mira, thora))


@pytest.mark.parametrize('edition', ['vanilla', 'forever', 'tbc', 'retail'])
@pytest.mark.parametrize('language', ['en', 'nn'])
def test_players_view_and_main_choice_on_the_leaderboard(edition, language):
    lua = client_runtime(edition)
    lua.execute(f'WoWStatusLocale.set("{language}")')
    lua.execute(ALT)
    lua.execute('''
        WoWStatusGroups.update("Example Crew", "")
        local id=next(character().group_ids)
        SlashCmdList.WOWSTATUS("leaderboard")
        local page, T=WoWStatusLeaderboardPage, WoWStatusLocale.T
        assert(page.mode.kind=="Button" and page.main.kind=="Button")
        assert(page.mode.text==T("View:").." "..T("Characters"))
        assert(page.main.text==T("Main:").." "..T("Automatic"))
        -- Characters view: short, class-coloured names as before.
        for _, row in ipairs(page.board) do
            if row:IsShown() then assert(not row.name.text:find("-TestRealm",1,true), row.name.text) end
        end
        page.mode.OnClick(page.mode)
        assert(WoWStatusDB.leaderboard.mode=="players")
        assert(page.mode.text==T("View:").." "..T("Players"))
        assert(page.nameHeader.text==T("Player"))
        -- One row for this account, its default main the higher-level alt.
        local function own()
            local found
            for _, row in ipairs(page.board) do
                if row:IsShown() and row.alts.text:find("Bank",1,true) then assert(not found); found=row end
            end
            return found
        end
        assert(own().alts.text:find("Bank Person · "..T("highest level, no main chosen"),1,true))
        assert(own().alts.text:find(T("Alts:"),1,true))
        -- Cycle: Automatic -> Bank Person (highest level) -> each other listed character -> Automatic.
        local choices=WoWStatusRoster.mainChoices()
        assert(choices[1].name=="Bank Person-TestRealm")
        for _, choice in ipairs(choices) do
            page.main.OnClick(page.main)
            assert(WoWStatusRoster.ownMain(id)==choice.name)
            assert(page.main.text==T("Main:").." "..choice.name:match("^[^-]+"))
        end
        assert(own().alts.text:find(" · "..T("main"),1,true))
        page.main.OnClick(page.main)
        assert(WoWStatusRoster.ownMain(id)==nil and page.main.text==T("Main:").." "..T("Automatic"))
        -- Controller reach of both buttons: tests/test_gamepad.py.
        page.mode.OnClick(page.mode)
        assert(WoWStatusDB.leaderboard.mode=="characters" and page.nameHeader.text==T("Character"))
    ''')
