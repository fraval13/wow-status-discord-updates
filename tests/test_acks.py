"""Delivery confirmations for live updates (WSACK), retries and "not reached"."""
from test_journal import actor, clock, deliver_popup


def level_up_sent():
    mira, thora = actor('Mira'), actor('Thora')
    clock(mira, 10)
    clock(thora, 10)
    mira.eval('fire')('PLAYER_LEVEL_UP', 42)
    return mira, thora


def acks(lua):
    return [p['text'] for p in lua.eval('__sent').values() if ' WSACK ' in p['text']]


def test_a_member_confirms_a_live_update_and_the_sender_stops_waiting():
    mira, thora = level_up_sent()
    assert mira.eval('#WoWStatusPopups.pendingDeliveries()') >= 1
    deliver_popup(mira, thora)
    reply = acks(thora)
    assert len(reply) == 1
    mira.eval('fire')('CHAT_MSG_ADDON', 'WoWStatus', reply[0], 'WHISPER', 'Thora-TestRealm')
    assert mira.eval('''(function()
        for _, p in ipairs(WoWStatusPopups.pendingDeliveries()) do if p.key == "thora-testrealm" then return false end end
        return true
    end)()''')


def test_an_unconfirmed_update_is_sent_again_then_marked_not_reached():
    mira, _ = level_up_sent()
    mira.execute('function WoWStatusRoster.versionOf() return "1.25.0" end')
    target = mira.eval('WoWStatusPopups.pendingDeliveries()[1].target')
    before = mira.eval('#__sent')
    clock(mira, 31)
    mira.eval('WoWStatusPopups.tick')()
    resent = [mira.eval(f'__sent[{i}]') for i in range(before + 1, mira.eval('#__sent') + 1)]
    assert any(p['target'] == target and 'WSTATUS2' in p['text'] for p in resent)
    assert not mira.eval(f'WoWStatusRoster.isUnreachable("{target}")')
    clock(mira, 52)
    mira.eval('WoWStatusPopups.tick')()
    assert mira.eval(f'WoWStatusRoster.isUnreachable("{target}")')
    # A later confirmation clears it.
    group = mira.eval('(next(character().group_ids))')
    mira.eval('fire')('CHAT_MSG_ADDON', 'WoWStatus', f'{group} WSACK 1-2-abc', 'WHISPER', target)
    assert not mira.eval(f'WoWStatusRoster.isUnreachable("{target}")')


def test_members_on_older_versions_are_never_marked_not_reached():
    mira, _ = level_up_sent()
    mira.execute('function WoWStatusRoster.versionOf() return "1.24.0" end')
    target = mira.eval('WoWStatusPopups.pendingDeliveries()[1].target')
    for t in (31, 52, 80):
        clock(mira, t)
        mira.eval('WoWStatusPopups.tick')()
    assert not mira.eval(f'WoWStatusRoster.isUnreachable("{target}")')
    assert mira.eval('#WoWStatusPopups.pendingDeliveries()') == 0


def test_the_card_says_not_reached():
    from test_roster import pair, pump
    mira, thora = pair()
    pump(mira, thora)
    thora.execute('WoWStatusRoster.unreached("Mira-TestRealm")')
    thora.eval('SlashCmdList.WOWSTATUS')('characters')
    cards = [thora.eval(f'WoWStatusCharactersPage.lines[{i}]') for i in range(1, thora.eval('WoWStatusCharactersPage.count') + 1)]
    card = next(c for c in cards if 'Mira' in c.name.text)
    assert 'not reached' in card.status.text
