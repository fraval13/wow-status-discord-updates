"""WoW Forever: membership by name alone, whatever internal realm a name carries."""
from test_roster import pair


def test_a_bare_sender_name_matches_a_member_listed_with_another_realm():
    mira, thora = pair()
    thora.execute('''
        WoWStatusAdapter.full_names = true
        __peers = {"Thora-TestRealm", "Mira Stone-CAMWOWEU5Realm7PvE"}
        for id in pairs(character().group_ids) do WoWStatusPopups.peers(id) end
    ''')
    group = thora.eval('(next(character().group_ids))')
    # The game gives the sender without a realm; the roster lists another one.
    assert thora.eval(f'WoWStatusPopups.isPeer("{group}", WoWStatusPopups.senderKey("Mira Stone"))')
    assert not thora.eval(f'WoWStatusPopups.isPeer("{group}", WoWStatusPopups.senderKey("Bob Other"))')


def test_other_editions_still_compare_the_realm():
    _, thora = pair()
    thora.execute('__peers = {"Thora-TestRealm", "Mira-OtherRealm"}; for id in pairs(character().group_ids) do WoWStatusPopups.peers(id) end')
    group = thora.eval('(next(character().group_ids))')
    assert not thora.eval(f'WoWStatusPopups.isPeer("{group}", WoWStatusPopups.senderKey("Mira"))')


def test_lists_from_bare_names_are_accepted_on_forever():
    mira, thora = pair()
    mira.execute('character().chat_name = "Mira Stone"')
    thora.execute('''
        WoWStatusAdapter.full_names = true
        __peers = {"Thora-TestRealm", "Mira Stone-CAMWOWEU5Realm7PvE"}
        for id in pairs(character().group_ids) do WoWStatusPopups.peers(id) end
    ''')
    before = mira.eval('#__sent')
    for step in range(20):
        mira.execute(f'__mono = {100 + step}')
        mira.eval('WoWStatusRoster.tick')()
    for i in range(before + 1, mira.eval('#__sent') + 1):
        packet = mira.eval(f'__sent[{i}]')
        if packet['prefix'] == 'WoWStatusChr':
            thora.eval('fire')('CHAT_MSG_ADDON', 'WoWStatusChr', packet['text'], 'WHISPER', 'Mira Stone')
    names = [r.name for g in thora.eval('WoWStatusRoster.groups()').values() for r in g.rows.values()]
    assert any(n.startswith('Mira Stone') for n in names)
