"""Character profiles (click a card) and invitations to a group."""
from test_roster import pair, pump


def open_profile(lua, name):
    lua.eval('SlashCmdList.WOWSTATUS')('characters')
    count = lua.eval('WoWStatusCharactersPage.count')
    card = next(lua.eval(f'WoWStatusCharactersPage.lines[{i}]') for i in range(1, count + 1)
                if name in lua.eval(f'WoWStatusCharactersPage.lines[{i}]').name.text)
    card.OnClick(card)
    return lua.eval('WoWStatusProfileView')


def test_clicking_a_card_opens_the_profile_with_stats_and_history():
    mira, thora = pair()
    mira.execute('''
        function GetMoney() return 123456 end
        WoWStatusRoster.observe(character())
    ''')
    pump(mira, thora)
    thora.execute('''
        local group = next(character().group_ids)
        local r = WoWStatusJournal.received
        r({sender="Mira-TestRealm",nonce="1-1-a",kind="level",level=2,at=time()-60,group_id=group})
        r({sender="Mira-TestRealm",nonce="1-2-b",kind="death",text="Total deaths: 1",at=time(),group_id=group})
    ''')
    view = open_profile(thora, 'Mira')
    assert view.IsShown(view)
    assert 'Mira' in view.head.name.text
    cells = ' '.join(c.text for c in view.stats.cells.values())
    assert 'Gold:' in cells and '12' in cells
    assert 'Level 2' in view.levels.text.text
    assert 'Total deaths: 1' in view.recent.text.text
    view.back.OnClick(view.back)
    assert not view.IsShown(view)


def test_show_activity_from_the_profile():
    mira, thora = pair()
    pump(mira, thora)
    view = open_profile(thora, 'Mira')
    view.activity.OnClick(view.activity)
    assert thora.eval('WoWStatusMainWindow.active()') == 'activity'
    assert thora.eval('WoWStatusActivityLog.character') == 'mira-testrealm'


def test_inviting_a_friend_to_another_group():
    mira, thora = pair()
    thora.execute('''
        WoWStatusGroups.update("dawnwatch\\nSecret Garden", "Ada")
        -- In the game each group has its own member list; Mira is not in Secret Garden.
        local garden, peers = WoWStatusGroups.key("Secret Garden"), WoWStatusPopups.peers
        WoWStatusPopups.peers = function(group) if group == garden then return {"Thora-TestRealm"} end return peers(group) end
    ''')
    pump(mira, thora)
    view = open_profile(thora, 'Mira')
    assert view.invite.IsShown(view.invite)
    view.invite.OnClick(view.invite)
    pick = next(r for r in thora.eval('WoWStatusMenu.rows').values() if r.IsShown(r) and r.text.text == 'Secret Garden')
    pick.OnClick(pick)
    assert view.message.text == 'Invite sent.'
    sent = pump(thora, mira, start=300)
    assert any(line.startswith('N ') for line in sent)
    garden = mira.eval('(WoWStatusGroups.key("Secret Garden"))')
    mira.execute(f'''
        local popup = WoWStatusInvite
        assert(popup:IsShown() and popup.text.text:find("Secret Garden", 1, true))
        assert(popup.text.text:find("Ada", 1, true) or popup.text.text:find("Thora", 1, true))
        popup.join.OnClick(popup.join)
        assert(WoWStatusGroups.contains(character(), "{garden}"))
    ''')


def test_an_invite_from_outside_your_groups_is_refused():
    _, thora = pair()
    hexname = 'Secret Garden'.encode().hex()
    group = thora.eval('(next(character().group_ids))')
    assert not thora.eval('WoWStatusRoster.receive')(f'N {group} 0123456789abcdef {hexname}', 'Stranger-TestRealm', 'WHISPER')
    assert thora.eval('WoWStatusInvite') is None
