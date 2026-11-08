"""Versioned gear exchange, including cached relays, over in-memory whispers."""
import pytest
from test_equipment import GEAR, snapshot
from test_journal import clock
from test_roster import person


class Network:
    def __init__(self, *names):
        self.clients = {}
        self.offsets = {}
        self.packets = []
        self.now = 0
        for name in names:
            self.add(name)

    def add(self, name):
        lua = person(name, name + 'sPlayer')
        lua.execute(GEAR + '''
            function GetAverageItemLevel() return 999, 45.9375 end
            WoWStatusEquipment.capture(character())
        ''')
        self.clients[name] = lua
        self.offsets[name] = lua.eval('#__sent')
        return lua

    def advance(self, seconds=80, drop=None):
        for _ in range(int(seconds * 2)):
            self.now += .5
            peers = '{' + ','.join('"' + n + '-TestRealm"' for n in self.clients) + '}'
            for lua in self.clients.values():
                clock(lua, self.now)
                lua.execute('__peers=' + peers)
                lua.eval('WoWStatusRoster.tick')()
            delivery = []
            for name, lua in self.clients.items():
                total = lua.eval('#__sent')
                for i in range(self.offsets[name] + 1, total + 1):
                    p = lua.eval(f'__sent[{i}]')
                    if p['prefix'] == 'WoWStatusChr':
                        assert len(p['text'].encode()) <= 250
                        packet = (name, p['target'].split('-')[0], p['text'])
                        self.packets.append(packet)
                        delivery.append(packet)
                self.offsets[name] = total
            for source, target, text in delivery:
                if target in self.clients and not (drop and drop(source, target, text)):
                    self.clients[target].eval('WoWStatusRoster.receive')(text, source + '-TestRealm', 'WHISPER')


def test_login_fetches_gear_without_opening_a_profile_and_sync_refreshes_it():
    net = Network('Mira', 'Thora')
    net.advance()
    thora, mira = net.clients['Thora'], net.clients['Mira']
    assert snapshot(thora)['items'][1].startswith('item:16963:1503:')
    assert snapshot(thora)['average_item_level'] == 45.93
    assert thora.eval('WoWStatusProfileView') is None
    old_revision = snapshot(thora)['revision']
    mira.execute('__gear[1]="item:42:0:0:0:0:0:0:0"')
    # Deliberately don't fire a gear event: Sync must recapture the owner's gear.
    thora.eval('WoWStatusRoster.syncNow')()
    net.advance()
    assert snapshot(thora)['items'][1].startswith('item:42:')
    assert snapshot(thora)['revision'] > old_revision


def test_a_gear_change_pings_friends_and_keeps_the_open_menu_unnecessary():
    net = Network('Mira', 'Thora')
    net.advance()
    mira, thora = net.clients['Mira'], net.clients['Thora']
    before = len(net.packets)
    mira.execute('__gear[16]="item:77:0:0:0:0:0:0:0"; WoWStatusEquipment.capture(character())')
    net.advance(50)
    assert snapshot(thora)['items'][16].startswith('item:77:')
    assert any(p[2].startswith('H ') for p in net.packets[before:])
    assert thora.eval('WoWStatusProfileView') is None


def test_login_with_a_partial_game_member_list_uses_the_known_group_lists():
    net = Network('Mira', 'Thora')
    net.advance()
    for lua in net.clients.values():
        lua.execute('''
            WoWStatusPopups.peers=function() return {} end
            WoWStatusDB.roster.equipment_cache={}
            WoWStatusRoster.init(WoWStatusDB,character())
        ''')
    net.advance(100)
    assert snapshot(net.clients['Thora'])['items'][1].startswith('item:16963:1503:')


def test_a_friend_relays_the_newest_cached_snapshot_for_an_offline_owner():
    net = Network('Mira', 'Thora')
    net.advance()
    mira = net.clients.pop('Mira')
    old = snapshot(net.clients['Thora'])['revision']
    bob = net.add('Bob')
    net.advance(100)
    assert snapshot(bob)['items'][1].startswith('item:16963:1503:')
    assert snapshot(bob)['revision'] == old
    assert snapshot(bob)['at'] <= 1793000080  # Relay arrival didn't make it newer.
    rows = [row for entry in bob.eval('WoWStatusRoster.groups()').values() for row in entry.rows.values()]
    owner = next(row for row in rows if row.name == 'Mira-TestRealm')
    assert owner.status != 'online'
    # The old owner process was never ticked while the relay happened.
    assert mira.eval('WoWStatusProfileView') is None


def test_old_relay_metadata_cannot_replace_newer_owner_data_even_with_a_later_arrival():
    net = Network('Mira', 'Thora')
    net.advance()
    mira, thora = net.clients['Mira'], net.clients['Thora']
    old_h = next(p[2] for p in net.packets if p[0] == 'Mira' and p[2].startswith('H '))
    mira.execute('__gear[1]="item:81"; WoWStatusEquipment.capture(character())')
    net.advance(50)
    newer = snapshot(thora)['revision']
    fields = old_h.split()
    fields[6] = str(1793000000 + int(net.now))  # Claimed relay/arrival time must not win.
    assert not thora.eval('WoWStatusRoster.receive')(' '.join(fields), 'Mira-TestRealm', 'WHISPER')
    assert snapshot(thora)['revision'] == newer
    assert snapshot(thora)['items'][1] == 'item:81'


def test_an_incomplete_new_snapshot_keeps_the_previous_complete_one():
    net = Network('Mira', 'Thora')
    net.advance()
    old = snapshot(net.clients['Thora'])['revision']
    net.clients['Mira'].execute('__gear[1]="item:91"; WoWStatusEquipment.capture(character())')
    net.advance(50, drop=lambda a, b, text: a == 'Mira' and text.startswith('T ') and text.split()[4] == '1')
    assert snapshot(net.clients['Thora'])['revision'] == old
    net.advance(200)
    assert snapshot(net.clients['Thora'])['items'][1] == 'item:91'


@pytest.mark.parametrize('privacy', ['field', 'hidden', 'sharing'])
def test_newer_privacy_state_invalidates_cached_gear_and_is_relayed(privacy):
    net = Network('Mira', 'Thora')
    net.advance()
    mira, thora = net.clients['Mira'], net.clients['Thora']
    if privacy == 'field':
        mira.execute('character().settings.fields.gear=false; character().equipment_profile=nil; WoWStatusEquipmentSync.privacyChanged()')
    elif privacy == 'hidden':
        mira.eval('WoWStatusRoster.setHidden')(mira.eval('character()'), True)
    else:
        mira.eval('WoWStatusRoster.setSharing')(False)
    net.advance(40)
    assert snapshot(thora) is None
    net.clients.pop('Mira')
    bob = net.add('Bob')
    net.advance(100)
    assert snapshot(bob) is None


def test_cached_gear_from_one_group_is_not_relayed_to_another():
    net = Network('Mira', 'Thora')
    net.advance()
    thora = net.clients['Thora']
    thora.eval('WoWStatusGroups.update')('dawnwatch\nOther Example', '')
    bob = net.add('Bob')
    bob.eval('WoWStatusGroups.update')('Other Example', '')
    group_b = bob.eval('WoWStatusGroups.key("Other Example")')
    if isinstance(group_b, tuple):
        group_b = group_b[0]
    before = len(net.packets)
    net.advance(100)
    assert snapshot(bob) is None
    assert not any(p[2].startswith('H ' + group_b + ' ') and 'Mira-TestRealm' in p[2]
                   for p in net.packets[before:])


def test_average_is_the_equipped_game_value_and_unknown_or_secret_values_are_omitted():
    net = Network('Mira')
    lua = net.clients['Mira']
    assert lua.eval('character().equipment_profile.average_item_level') == 45.9375
    lua.execute('''
        __secret={}
        function issecretvalue(value) return value==__secret end
        function GetAverageItemLevel() return 999,__secret end
        assert(WoWStatusEquipment.capture(character()).average_item_level==nil)
        GetAverageItemLevel=nil
        assert(WoWStatusEquipment.capture(character()).average_item_level==nil)
    ''')


def test_cards_use_a_full_bottom_xp_bar_and_show_item_level_on_the_overview():
    net = Network('Thora')
    lua = net.clients['Thora']
    lua.execute('''
        local methods=getmetatable(CreateFrame("Frame")).__index
        function methods:SetPoint(...) self.point={...} end
        WoWStatusMainWindow.show("characters")
    ''')
    card = next(c for c in lua.eval('WoWStatusCharactersPage.lines').values() if c.IsShown(c))
    # The card is taller than its texts: the profession strip sits above the XP bar.
    assert card.height == 114 and card.xp.width == 660 and card.xp.height == 14
    assert card.xp.point[1] == 'BOTTOMLEFT'
    assert card.itemLevel.text.endswith('45')
    lua.eval('WoWStatusMainWindow.show')('overview')
    assert lua.eval('WoWStatusOverviewPage.you.itemLevel.text').endswith('45')
