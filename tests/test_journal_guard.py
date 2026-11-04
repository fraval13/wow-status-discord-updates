"""Hostile packets are simulated locally; no warnings are sent to real players."""
import pytest
from test_client_compatibility import client_runtime
from test_journal import actor, clock


def member(name='Thora', edition='vanilla'):
    if edition == 'vanilla':
        lua = actor(name)
    else:
        lua = client_runtime(edition, name, extra='''
            __now=1793000000;__mono=0
            function time() return math.floor(__now) end
            function GetTime() return __mono end
        ''')
        lua.execute('WoWStatusGroups.announce=nil;WoWStatusGroups.update("navsquad", "")')
    lua.execute('''
        __peers={"Thora-TestRealm","Eldrin-TestRealm","Mira-TestRealm"}
        for id in pairs(character().group_ids) do __channelNames={WoWStatusGroups.channel(id)} end
    ''')
    return lua


def group(lua):
    return lua.eval('next(character().group_ids)')[0]


def warning_packets(lua):
    return [p for p in lua.eval('__sent').values()
            if p['prefix'] == 'WoWStatusLog' and ' W ' in p['text']]


def pump(lua, start=1, duration=20):
    for step in range(start, start + duration):
        clock(lua, step)
        lua.eval('WoWStatusJournal.tick')()


@pytest.mark.parametrize('edition', ['vanilla', 'forever', 'tbc', 'retail'])
def test_invalid_live_entry_warns_group_once_without_logging_or_echo(edition):
    own, friend = member(edition=edition), member('Mira', edition)
    channel = 'WStatus' + group(own)
    client = own.eval('WoWStatusAdapter.client_id')
    attack = f'WSTATUS4 {client} death 1793000000 forged Arbitrary injected text'
    receive = own.eval('WoWStatusPopups.receive')
    for _ in range(20):
        assert not receive(attack, 'Eldrin-TestRealm', channel)
    assert own.eval('#WoWStatusJournal.entries()') == 0
    assert own.eval('#character().events') == 0
    assert own.eval('WoWStatusLevelPopup.message:GetText()') == (
        'Eldrin is a really bad boy, shame on you!')
    assert 'Thora-TestRealm' in own.eval('WoWStatusLevelPopup.detail:GetText()')
    pump(own)
    reports = warning_packets(own)
    assert {p['target'] for p in reports} == {'Eldrin-TestRealm', 'Mira-TestRealm'}
    assert len(reports) == 2
    for packet in reports:
        assert len(packet['text'].encode()) <= 243
        if packet['target'] == 'Mira-TestRealm':
            for _ in range(20):
                friend.eval('fire')('CHAT_MSG_ADDON', 'WoWStatusLog', packet['text'],
                                   'WHISPER', 'Thora-TestRealm')
    assert 'Eldrin is a really bad boy' in friend.eval('WoWStatusLevelPopup.message:GetText()')
    assert friend.eval('#WoWStatusJournal.entries()') == 0
    pump(friend)
    assert warning_packets(friend) == []


def digest(text):
    a, b, c = 5381, 2166136261, 104729
    for byte in text.encode():
        a = (a * 33 + byte) % 4294967296
        b = (b * 65599 + byte) % 4294967296
        c = (c * 131 + byte) % 4294967296
    return f'{a:08x}{b:08x}{c % 16777216:06x}'


def offer_entry(lua, *, claimed='Mira-TestRealm', level='999', detail='Injected text'):
    pump(lua, duration=5)
    query = next(p['text'] for p in lua.eval('__sent').values()
                 if p['target'] == 'Eldrin-TestRealm' and ' Q ' in p['text'])
    token = query.split()[3]
    client = lua.eval('WoWStatusAdapter.client_id')
    event_id = f'{client}:{claimed.lower()}:forged'
    fingerprint = digest(event_id)
    receive = lua.eval('WoWStatusJournal.receive')
    assert receive(f'J2 {group(lua)} I {token} 1 0 {fingerprint}',
                   'Eldrin-TestRealm', 'WHISPER')
    fields = [event_id, client, claimed, '1793000001', 'level', level, detail, '', '', '', '']
    data = ''.join(f'{len(s.encode())}:{s}' for s in fields).encode().hex()
    chunks = [data[i:i+140] for i in range(0, len(data), 140)]
    result = None
    for i, chunk in enumerate(chunks, 1):
        result = receive(f'J2 {group(lua)} D {token} {fingerprint} {i}/{len(chunks)} {chunk}',
                         'Eldrin-TestRealm', 'WHISPER')
    return result


@pytest.mark.parametrize('edition', ['vanilla', 'forever', 'tbc', 'retail'])
def test_bad_catchup_attributes_direct_relay_not_forged_author(edition):
    lua = member(edition=edition)
    assert not offer_entry(lua)
    assert lua.eval('#WoWStatusJournal.entries()') == 0
    assert 'Eldrin is a really bad boy' in lua.eval('WoWStatusLevelPopup.message:GetText()')
    pump(lua, start=6)
    assert warning_packets(lua)
    assert all(p['text'].endswith('Eldrin-TestRealm') for p in warning_packets(lua))


def test_valid_level_cannot_smuggle_free_text_through_catchup():
    lua = member()
    assert not offer_entry(lua, level='30', detail='Unrelated announcement')
    assert lua.eval('#WoWStatusJournal.entries()') == 0
    assert 'Eldrin is a really bad boy' in lua.eval('WoWStatusLevelPopup.message:GetText()')


def test_normal_drops_and_untrusted_reports_never_trigger_public_warning():
    lua = member()
    receive = lua.eval('WoWStatusJournal.receive')
    g = group(lua)
    for packet, sender in [
        (f'J2 {g} D unknown abc 1/1 abcd', 'Eldrin-TestRealm'),
        (f'J2 {g} W a classic-era 1793000000 Eldrin-TestRealm', 'Stranger-TestRealm'),
        (f'J2 {g} W a forever 1793000000 Eldrin-TestRealm', 'Eldrin-TestRealm'),
        (f'J2 {g} W a classic-era 1792999000 Eldrin-TestRealm', 'Eldrin-TestRealm'),
        (f'J2 {g} W a classic-era 1793000000 Stranger-TestRealm', 'Eldrin-TestRealm'),
        (f'J2 {g} W a classic-era 1793000000 |Hbad', 'Eldrin-TestRealm'),
    ]:
        assert not receive(packet, sender, 'WHISPER')
    popups = lua.eval('WoWStatusPopups.receive')
    assert not popups('WSTATUS2 forever LEVEL 999 1793000000 old', 'Eldrin-TestRealm', 'WStatus'+g)
    assert not popups('WSTATUS2 classic-era LEVEL 999 1792999000 old', 'Eldrin-TestRealm', 'WStatus'+g)
    assert not popups('WSTATUS4 classic-era quest 1793000000 old A single quest', 'Eldrin-TestRealm', 'WStatus'+g)
    assert lua.eval('WoWStatusLevelPopup') is None
    pump(lua)
    assert warning_packets(lua) == []


def test_warning_limits_pause_expiry_and_group_removal():
    lua = member()
    g = group(lua)
    report = lua.eval('WoWStatusJournal.reportInvalid')
    assert report(g, 'Eldrin-TestRealm')
    assert not report(g, 'Mira-TestRealm')  # Global limit, even for another sender.
    clock(lua, 61)
    assert not report(g, 'Eldrin-TestRealm')  # Ten-minute per-sender limit.
    assert report(g, 'Mira-TestRealm')
    lua.execute('__restricted=true')
    pump(lua, start=62, duration=130)
    lua.execute('__restricted=false')
    pump(lua, start=192)
    assert warning_packets(lua) == []  # Both warnings expired during lockdown.
    lua.execute('character().settings.enabled=false')
    clock(lua, 700)
    assert not report(g, 'Eldrin-TestRealm')
    lua.execute('character().settings.enabled=true')
    assert report(g, 'Eldrin-TestRealm')
    lua.eval('WoWStatusGroups.update')('', '')
    pump(lua, start=701)
    assert warning_packets(lua) == []
