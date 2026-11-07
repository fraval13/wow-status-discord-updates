"""Equipment snapshots over the mocked roster transport, never a live inspect."""
import pytest
from test_journal import clock
from test_profile import open_profile
from test_roster import pair, pump

GEAR = r'''
    __gear = {[1]="item:16963:1503:0:0:0:0:-12:99", [16]="item:19019:2564:0:0:0:0:0:0"}
    function GetInventoryItemLink(_, slot) return __gear[slot] end
    function UnitHealthMax() return 4321 end
    function UnitPowerMax(_, kind) assert(kind == 0); return 2500 end
    function UnitStat(_, index) return 10, 100 + index, 2, -1 end
    function UnitArmor() return 900, 1234, 900, 334 end
    function UnitAttackPower() return 100, 40, -10 end
    function UnitRangedAttackPower() return 80, 20, -5 end
    function GetCritChance() return 12.34 end
    function GetSpellCritChance(school) return school end
    function GetSpellBonusDamage(school) return school * 10 end
    function GetSpellBonusHealing() return 75 end
    function GetDodgeChance() return 3.21 end
    function GetParryChance() return 5 end
    function GetBlockChance() return 10 end
    function GetHaste() return 8.9 end
    function GetMasteryEffect() return 13.5 end
    CR_VERSATILITY_DAMAGE_DONE = 29
    function GetCombatRatingBonus(rating) assert(rating == 29); return 4.5 end
'''


def clients():
    own, friend = pair()
    own.execute(GEAR)
    pump(own, friend)
    pump(friend, own)
    return own, friend


def transfer(sender, receiver=None, start=200, steps=60):
    before = sender.eval('#__sent')
    for step in range(steps):
        sender.execute(f'__mono = {start + step}')
        sender.eval('WoWStatusRoster.tick')()
    name = sender.eval('WoWStatusAdapter.playerName()') + '-TestRealm'
    packets = []
    for i in range(before + 1, sender.eval('#__sent') + 1):
        packet = sender.eval(f'__sent[{i}]')
        if packet['prefix'] != 'WoWStatusChr':
            continue
        assert len(packet['text'].encode()) <= 250
        packets.append(packet['text'])
        if receiver is not None:
            receiver.eval('WoWStatusRoster.receive')(packet['text'], name, 'WHISPER')
    return packets


def snapshot(lua, name='Mira-TestRealm'):
    return lua.eval(f'(WoWStatusRoster.equipment("{name}"))')


def request(own, friend):
    assert friend.eval('WoWStatusRoster.requestEquipment')('Mira-TestRealm')
    packets = transfer(friend, own)
    assert sum(p.startswith('D ') for p in packets) == 1
    return packets


def test_full_equipment_and_public_stats_are_requested_without_announcements():
    own, friend = clients()
    before = own.eval('#WoWStatusJournal.entries()')
    assert snapshot(friend) is None
    request(own, friend)
    packets = transfer(own, friend)
    assert sum(p.startswith('E ') for p in packets) == 23
    result = snapshot(friend)
    assert result['items'][1] == 'item:16963:1503:0:0:0:0:-12:99'
    assert result['items'][16] == 'item:19019:2564:0:0:0:0:0:0'
    assert result['items'][17] == '-'
    assert len(list(result['items'].keys())) == 20
    assert result['stats']['health'] == 4321
    assert result['stats']['armor'] == 1234
    assert result['stats']['strength'] == 101
    assert result['stats']['attack_power'] == 130
    assert result['stats']['crit'] == 1234
    assert result['stats']['spell_power'] == 20
    assert own.eval('#WoWStatusJournal.entries()') == before
    assert not friend.eval('WoWStatusRoster.requestEquipment')('Mira-TestRealm')


def test_partial_reordered_and_duplicate_packets_never_replace_a_whole_snapshot():
    own, friend = clients()
    request(own, friend)
    parts = [p for p in transfer(own) if p.startswith('E ')]
    receive = friend.eval('WoWStatusRoster.receive')
    for part in reversed(parts[1:]):
        assert receive(part, 'Mira-TestRealm', 'WHISPER')
    assert receive(parts[1], 'Mira-TestRealm', 'WHISPER')  # Duplicate doesn't complete it.
    assert snapshot(friend) is None
    assert receive(parts[0], 'Mira-TestRealm', 'WHISPER')
    original = snapshot(friend)['items'][1]
    clock(own, 61)
    clock(friend, 61)
    own.execute('__gear[1] = nil')
    request(own, friend)
    parts = [p for p in transfer(own, start=400) if p.startswith('E ')]
    for part in parts[:-1]:
        assert receive(part, 'Mira-TestRealm', 'WHISPER')
    assert snapshot(friend)['items'][1] == original
    assert receive(parts[-1], 'Mira-TestRealm', 'WHISPER')
    assert snapshot(friend)['items'][1] == '-'


def test_a_late_older_response_cannot_overwrite_the_latest_refresh():
    own, friend = clients()
    request(own, friend)
    old_parts = [p for p in transfer(own) if p.startswith('E ')]
    clock(own, 61)
    clock(friend, 61)
    own.execute('__gear[1] = nil')
    request(own, friend)
    transfer(own, friend, start=400)
    assert snapshot(friend)['items'][1] == '-'
    receive = friend.eval('WoWStatusRoster.receive')
    assert all(not receive(p, 'Mira-TestRealm', 'WHISPER') for p in old_parts)
    assert snapshot(friend)['items'][1] == '-'


@pytest.mark.parametrize('privacy', ['field', 'hidden', 'sharing'])
def test_privacy_is_checked_before_answering_and_again_while_queued(privacy):
    own, friend = clients()
    request(own, friend)
    if privacy == 'field':
        own.execute('character().settings.fields.gear = false')
    elif privacy == 'hidden':
        own.execute('character().hide_from_list = true')
    else:
        own.execute('WoWStatusDB.roster.share = false')
    assert not any(p.startswith('E ') for p in transfer(own, friend))
    clock(own, 61)
    clock(friend, 61)
    request(own, friend)
    parts = [p for p in transfer(own, friend, start=400) if p.startswith('E ')]
    assert len(parts) == (0 if privacy == 'sharing' else 1)
    assert snapshot(friend) is None


def test_a_disabled_equipment_field_removes_the_cached_snapshot():
    own, friend = clients()
    request(own, friend)
    transfer(own, friend)
    assert snapshot(friend) is not None
    own.execute('character().settings.fields.gear = false')
    clock(own, 61)
    clock(friend, 61)
    request(own, friend)
    transfer(own, friend, start=400)
    assert snapshot(friend) is None
    assert friend.eval('select(2, WoWStatusRoster.equipment("Mira-TestRealm"))')


def test_leaving_the_group_stops_a_queued_snapshot_and_tours_never_request_gear():
    own, friend = clients()
    friend.execute('WoWStatusGuide.tour()')
    assert not friend.eval('WoWStatusRoster.requestEquipment')('Mira-TestRealm')
    assert not any(p.startswith('D ') for p in transfer(friend, own))
    friend.execute('WoWStatusGuide.endTour()')
    request(own, friend)
    own.execute('WoWStatusGroups.update("", "")')
    assert not any(p.startswith('E ') for p in transfer(own, friend, start=400))


def test_percentage_stats_include_negative_haste_and_additional_versatility():
    own, friend = clients()
    own.execute('function GetHaste() return -12.5 end; function GetVersatilityBonus() return 3 end')
    request(own, friend)
    transfer(own, friend)
    result = snapshot(friend)
    assert result['stats']['haste'] == -1250
    assert result['stats']['versatility'] == 750


def test_empty_slots_and_items_waiting_for_the_game_cache_are_distinct():
    own, _ = clients()
    own.execute('''
        __gear[1] = nil
        function GetInventoryItemID(_, slot) return slot == 1 and 16963 or 0 end
        local s = WoWStatusEquipment.capture(character())
        assert(s.items[1] == "?" and s.items[17] == "-")
        function GetInventoryItemID() return 0 end
        assert(WoWStatusEquipment.capture(character()).items[1] == "-")
    ''')


def test_snapshot_survives_a_roster_refresh_and_offline_character_is_available():
    own, friend = clients()
    request(own, friend)
    transfer(own, friend)
    own.execute('WoWStatusRoster.changed()')
    transfer(own, friend, start=400)
    friend.execute('__peers = {"Thora-TestRealm"}')
    assert snapshot(friend)['stats']['health'] == 4321
    view = open_profile(friend, 'Mira')
    assert view.equipment.slots[16].item == 'item:19019:2564:0:0:0:0:0:0'
    assert 'Last reported:' in view.equipment.updated.text


def test_the_owner_can_answer_for_an_offline_alt_but_not_a_hidden_alt():
    own, friend = clients()
    own.execute('''
        local c = character()
        WoWStatusEquipment.capture(c)
        local alt = {identity={guid="Player-Alt", client=c.identity.client, name="Alt", realm="TestRealm"},
            settings={fields={gear=true}}, roster_info=c.roster_info, equipment_profile=c.equipment_profile}
        WoWStatusDB.characters["alt"] = alt
        WoWStatusRoster.changed()
    ''')
    transfer(own, friend, start=400)
    assert friend.eval('WoWStatusRoster.requestEquipment')('Alt-TestRealm')
    transfer(friend, own, start=400)
    transfer(own, friend, start=500)
    assert snapshot(friend, 'Alt-TestRealm')['items'][1].startswith('item:16963:1503:')
    clock(own, 61)
    clock(friend, 61)
    own.execute('WoWStatusDB.characters.alt.hide_from_list = true')
    assert friend.eval('WoWStatusRoster.requestEquipment')('Alt-TestRealm')
    transfer(friend, own, start=600)
    transfer(own, friend, start=700)
    assert snapshot(friend, 'Alt-TestRealm') is None


def test_a_group_member_can_request_gear_without_sharing_their_own_character_list():
    own, friend = clients()
    own.execute('WoWStatusDB.roster.players = {}')
    request(own, friend)
    transfer(own, friend)
    assert snapshot(friend)['items'][1].startswith('item:16963:')


def test_unsolicited_forged_expired_or_malformed_parts_are_rejected():
    own, friend = clients()
    request(own, friend)
    parts = [p for p in transfer(own) if p.startswith('E ')]
    receive = friend.eval('WoWStatusRoster.receive')
    item = next(p for p in parts if 'item:' in p)
    words = item.split()
    for index, bad in ((1, 'othergroup'), (2, '0123456789abcdef'), (3, 'Bob-TestRealm'),
                       (4, 'ffffffff'), (5, '20'), (6, 'item:0'), (6, '|Hspell:1|h')):
        changed = words.copy()
        changed[index] = bad
        assert not receive(' '.join(changed), 'Mira-TestRealm', 'WHISPER')
    assert not receive(item, 'Stranger-TestRealm', 'WHISPER')
    assert not receive(item, 'Mira-TestRealm', 'CHANNEL')
    clock(friend, 181)
    assert not receive(item, 'Mira-TestRealm', 'WHISPER')
    assert snapshot(friend) is None


@pytest.mark.parametrize('factory', ['vanilla', 'forever', 'tbc', 'retail'])
def test_missing_and_secret_api_values_stay_unavailable(factory):
    if factory == 'forever':
        from test_forever import forever_runtime
        lua = forever_runtime()
        lua.eval('fire')('PLAYER_LOGIN')
    elif factory == 'retail':
        from test_retail import retail_runtime
        lua = retail_runtime()
    elif factory == 'tbc':
        from test_tbc import tbc_runtime
        lua = tbc_runtime()
    else:
        from test_addon import make_lua
        lua = make_lua()
    lua.execute(GEAR + '''
        __secret = setmetatable({}, {__tostring=function() error("secret was stringified") end})
        function issecretvalue(value) return value == __secret end
        function GetInventoryItemLink() return __secret end
        function UnitStat() return 1, __secret end
        function UnitHealthMax() return __secret end
        UnitArmor = nil
        GetCritChance = function() error("unavailable") end
        local s = WoWStatusEquipment.capture(character())
        assert(s.items[1] == "?" and s.stats.strength == nil and s.stats.health == nil)
        assert(s.stats.armor == nil and s.stats.crit == nil)
        assert(s.stats.mana == 2500)
        GetInventoryItemLink = nil
        assert(WoWStatusEquipment.capture(character()).items[1] == "?")
    ''')


def test_profile_scrolls_below_history_and_tooltips_keep_enchants_and_suffixes():
    own, friend = clients()
    view = open_profile(friend, 'Mira')
    transfer(friend, own)
    transfer(own, friend)
    friend.execute('assert(WoWStatusProfileView.scroll.child == WoWStatusProfileView.body)')
    view.scroll.OnMouseWheel(view.scroll, -30)
    assert view.scroll.scroll == 832
    cells = ' '.join(cell.text for cell in view.attributes.cells.values())
    assert 'Health:|r 4321' in cells and 'Melee critical strike:|r 12.34%' in cells
    friend.execute('''
        GameTooltip = {SetOwner=function() end, Show=function() end, Hide=function() end,
            SetHyperlink=function(_, item) __tooltip = item end}
        local slot = WoWStatusProfileView.equipment.slots[1]
        slot.OnEnter(slot)
        assert(__tooltip == "item:16963:1503:0:0:0:0:-12:99")
        WoWStatusLocale.set("nn")
        WoWStatusProfile.refreshEquipment()
        assert(WoWStatusProfileView.attributes.cells[1].text:find("Helse:", 1, true))
    ''')


def test_packets_handle_the_longest_names_and_item_strings():
    own, friend = clients()
    long_name = 'M' * 31 + '-' + 'R' * 32
    own.execute(f'WoWStatusPopups.characterName = function() return "{long_name}" end; WoWStatusRoster.changed()')
    transfer(own, friend, start=400)
    own.execute('__gear[1] = "item:1" .. string.rep(":123456789", 11)')
    assert friend.eval('WoWStatusRoster.requestEquipment')(long_name)
    transfer(friend, own, start=400)
    parts = [p for p in transfer(own, friend, start=500) if p.startswith('E ')]
    assert len(parts) == 23
    assert snapshot(friend, long_name)['items'][1].startswith('item:1:')


@pytest.mark.parametrize('which', ['request', 'response'])
def test_explicit_game_throttles_pause_and_retry_equipment_packets(which):
    own, friend = clients()
    target = friend if which == 'request' else own
    target.execute('''
        Enum = {SendAddonMessageResult={Success=0, AddonMessageThrottle=8}}
        local send = C_ChatInfo.SendAddonMessage
        __throttle = true
        C_ChatInfo.SendAddonMessage = function(prefix, text, ...)
            if prefix == "WoWStatusChr" and (text:sub(1, 2) == "D " or text:sub(1, 2) == "E ") then
                if __throttle then __throttle = false; return 8 end
                send(prefix, text, ...); return 0
            end
            return send(prefix, text, ...)
        end
    ''')
    request(own, friend)
    transfer(own, friend)
    assert snapshot(friend)['items'][16].startswith('item:19019:2564:')
