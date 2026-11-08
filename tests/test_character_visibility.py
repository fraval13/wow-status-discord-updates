"""Owner-controlled character visibility, shared quietly with group peers."""
import pytest
from test_client_compatibility import client_runtime
from test_roster import pair, pump


def test_hidden_character_stays_out_of_cached_lists_log_fallback_and_ranking():
    owner, friend = pair()
    pump(owner, friend)
    friend.execute('''
        WoWStatusJournal.received({sender="Mira-TestRealm",nonce="old-level",kind="level",level=8})
        __history=#WoWStatusJournal.entries()
    ''')
    owner.execute('assert(WoWStatusRoster.setHidden(character(),true))')
    packets = pump(owner, friend, start=300)
    hidden = next(packet for packet in packets if packet.startswith('Z '))
    friend.execute('''
        assert(WoWStatusRoster.isHidden("Mira-TestRealm"))
        for _, group in ipairs(WoWStatusRoster.groups()) do
            for _, row in ipairs(group.rows) do assert(row.name~="Mira-TestRealm") end
        end
        local id=next(character().group_ids)
        for _, row in ipairs(WoWStatusRoster.leaderboard(id)) do assert(row.name~="Mira-TestRealm") end
        assert(#WoWStatusJournal.entries()==__history)
        assert(#WoWStatusRoster.onlineNames()==0)
        local snapshot,hidden,known=WoWStatusEquipmentSync.get("Mira-TestRealm")
        assert(snapshot==nil and hidden and known)
    ''')
    # An old list packet and a delayed visibility packet cannot restore a hidden alt.
    pid = owner.eval('WoWStatusDB.roster.id')
    group = owner.eval('next(character().group_ids)')[0]
    receive = friend.eval('WoWStatusRoster.receive')
    assert receive(f'C {group} {pid} Frank Mira-TestRealm Dwarf 3 WARRIOR 1', 'Mira-TestRealm', 'WHISPER') is True
    assert friend.eval('WoWStatusRoster.isHidden("Mira-TestRealm")') is True
    owner.execute('assert(WoWStatusRoster.setHidden(character(),false))')
    pump(owner, friend, start=600)
    assert friend.eval('WoWStatusRoster.isHidden("Mira-TestRealm")') is False
    assert receive(hidden, 'Mira-TestRealm', 'WHISPER') is False
    assert friend.eval('#WoWStatusRoster.onlineNames()') == 1


@pytest.mark.parametrize('edition', ['vanilla', 'forever', 'tbc', 'retail'])
def test_settings_can_hide_and_restore_an_owned_offline_alt(edition):
    lua = client_runtime(edition)
    lua.execute('''
        local original=character()
        __alt={identity={name="Bank Person",realm="TestRealm",client=WoWStatusAdapter.client_id},
            settings=original.settings,events={{kind="level",level=1}},roster_info=original.roster_info}
        WoWStatusDB.characters.bank=__alt
        SlashCmdList.WOWSTATUS("")
        local list=WoWStatusSetup.visibility
        assert(list and list.kind=="ScrollFrame")
        local row
        for _, candidate in ipairs(list.rows) do if candidate.character==__alt then row=candidate end end
        assert(row and row.kind=="CheckButton" and row:GetChecked())
        row:SetChecked(false);row.OnClick(row)
        assert(__alt.hide_from_list and __alt.visibility_revision==1)
        assert(# __alt.events==1 and not original.hide_from_list)
        row:SetChecked(true);row.OnClick(row)
        assert(not __alt.hide_from_list and __alt.visibility_revision==2)
        assert(not WoWStatusRoster.setHidden({identity=__alt.identity},true))
    ''')


def test_hidden_alt_is_advertised_to_a_new_peer_without_sending_its_stats():
    owner, friend = pair()
    owner.execute('WoWStatusRoster.setHidden(character(),true)')
    packets = pump(owner, friend)
    assert any(packet.startswith('Z ') for packet in packets)
    assert not any(packet.startswith(('C ', 'O ', 'P ', 'S ', 'Q ')) for packet in packets)
    assert friend.eval('WoWStatusRoster.isHidden("Mira-TestRealm")') is True
    # Visibility remains in saved state when roster initialization is repeated.
    friend.execute('WoWStatusRoster.init(WoWStatusDB,character(),function() end)')
    assert friend.eval('WoWStatusRoster.isHidden("Mira-TestRealm")') is True


def test_bad_visibility_updates_cannot_change_the_list():
    owner, friend = pair()
    pump(owner, friend)
    pid = owner.eval('WoWStatusDB.roster.id')
    group = owner.eval('next(character().group_ids)')[0]
    receive = friend.eval('WoWStatusRoster.receive')
    good = f'Z {group} {pid} Mira-TestRealm 1 1'
    for bad in (good.replace(' 1 1',' -1 1'),good.replace(' 1 1',' 1.5 1'),
                good.replace(' 1 1',' 1 2'),good.replace('Mira-TestRealm','Mira|bad'),good+' extra'):
        assert receive(bad,'Mira-TestRealm','WHISPER') is False
    assert receive(good,'Stranger-TestRealm','WHISPER') is False
    assert receive(good,'Mira-TestRealm','CHANNEL') is False
    assert friend.eval('WoWStatusRoster.isHidden("Mira-TestRealm")') is False


def test_visibility_updates_are_bounded_and_idempotent():
    owner, friend = pair()
    pid = owner.eval('WoWStatusDB.roster.id')
    group = owner.eval('next(character().group_ids)')[0]
    receive = friend.eval('WoWStatusRoster.receive')
    for i in range(200):
        packet = f'Z {group} {pid} Bank{i}-TestRealm 1 1'
        assert receive(packet, 'Mira-TestRealm', 'WHISPER') is True
        assert receive(packet, 'Mira-TestRealm', 'WHISPER') is True
    assert receive(f'Z {group} {pid} Overflow-TestRealm 1 1', 'Mira-TestRealm', 'WHISPER') is False
    assert receive(f'Z {group} {pid} Bank0-TestRealm 2 0', 'Mira-TestRealm', 'WHISPER') is True
    assert friend.eval('WoWStatusRoster.isHidden("Bank0-TestRealm")') is False


def test_hiding_still_reaches_friends_with_account_list_sharing_off():
    owner, friend = pair()
    pump(owner, friend)
    owner.execute('WoWStatusRoster.setSharing(false);WoWStatusRoster.setHidden(character(),true)')
    packets = pump(owner, friend, start=300)
    assert any(packet.startswith('X ') for packet in packets)
    assert any(packet.startswith('Z ') for packet in packets)
    assert not any(packet.startswith('C ') for packet in packets)
    assert friend.eval('WoWStatusRoster.isHidden("Mira-TestRealm")') is True
    # Later stop-sharing notifications must not discard the hidden state.
    owner.execute('WoWStatusRoster.changed()')
    pump(owner, friend, start=500)
    assert friend.eval('WoWStatusRoster.isHidden("Mira-TestRealm")') is True
    owner.execute('WoWStatusRoster.setHidden(character(),false)')
    pump(owner, friend, start=700)
    assert friend.eval('WoWStatusRoster.isHidden("Mira-TestRealm")') is False
