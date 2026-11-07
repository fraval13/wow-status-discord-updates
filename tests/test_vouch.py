"""When the game shows you alone in a group channel, members who message you
with the group's ID are trusted (WoW Forever did this while friends were in it)."""
from test_journal import actor, clock

ALONE = '''
    __selected=1
    function GetNumDisplayChannels() return 1 end
    function GetChannelDisplayInfo(index)
        for id in pairs(character().group_ids) do return WoWStatusGroups.channel(id),false,false,1,__count or 1 end
    end
    function GetSelectedDisplayChannel() return __selected end
    function SetSelectedDisplayChannel(index) __selected=index end
    C_ChatInfo.GetChannelRosterInfo=function(index,member) if member==1 then return "Thora-TestRealm" end end
'''


def alone(count=1):
    lua = actor('Thora')
    lua.execute(f'__count={count}' + ALONE)
    group = lua.eval('(next(character().group_ids))')
    clock(lua, 1)
    lua.eval('WoWStatusPopups.peers')(group)
    clock(lua, 2)
    lua.eval('WoWStatusPopups.peers')(group)
    return lua, group


def test_a_member_messaging_us_is_trusted_while_the_game_shows_us_alone():
    lua, group = alone()
    assert not lua.eval(f'WoWStatusPopups.isPeer("{group}", WoWStatusPopups.senderKey("Mira-TestRealm"))')
    assert lua.eval('WoWStatusPopups.vouch')(group, 'Mira-TestRealm')
    assert lua.eval(f'WoWStatusPopups.isPeer("{group}", WoWStatusPopups.senderKey("Mira-TestRealm"))')
    # Our own updates go to her too.
    assert 'Mira-TestRealm' in list(lua.eval(f'WoWStatusPopups.peers("{group}")').values())


def test_trust_lasts_half_an_hour_after_the_last_message():
    lua, group = alone()
    lua.eval('WoWStatusPopups.vouch')(group, 'Mira-TestRealm')
    clock(lua, 1700)
    assert 'Mira-TestRealm' in list(lua.eval(f'WoWStatusPopups.peers("{group}")').values())
    clock(lua, 1900)
    assert 'Mira-TestRealm' not in list(lua.eval(f'WoWStatusPopups.peers("{group}")').values())


def test_with_a_normal_member_list_nobody_is_trusted_this_way():
    lua, group = alone(count=3)
    assert not lua.eval('WoWStatusPopups.vouch')(group, 'Mira-TestRealm')
    assert not lua.eval(f'WoWStatusPopups.isPeer("{group}", WoWStatusPopups.senderKey("Mira-TestRealm"))')


def test_messages_for_other_groups_vouch_nothing():
    lua, _ = alone()
    assert not lua.eval('WoWStatusPopups.vouch')('0123456789abcdef012345', 'Mira-TestRealm')


def test_a_friends_list_is_accepted_while_alone():
    lua, group = alone()
    ok = lua.eval('WoWStatusRoster.receive')(
        f'C {group} 4d6972614d697261 Frank Mira-TestRealm Dwarf 3 WARRIOR 12', 'Mira-TestRealm', 'WHISPER')
    assert ok
    names = [r.name for g in lua.eval('WoWStatusRoster.groups()').values() for r in g.rows.values()]
    assert 'Mira-TestRealm' in names
