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
        lua.execute('WoWStatusGroups.announce=nil;WoWStatusGroups.update("dawnwatch", "")')
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
def test_invalid_live_entry_is_dropped_without_a_warning(edition):
    # The "is a really bad boy" warning was removed after false alarms in live play.
    own, friend = member(edition=edition), member('Mira', edition)
    channel = 'WStatus' + group(own)
    client = own.eval('WoWStatusAdapter.client_id')
    attack = f'WSTATUS4 {client} death 1793000000 forged Arbitrary injected text'
    receive = own.eval('WoWStatusPopups.receive')
    for _ in range(20):
        assert not receive(attack, 'Eldrin-TestRealm', channel)
    assert own.eval('#WoWStatusJournal.entries()') == 0
    assert own.eval('#character().events') == 0
    own.eval('WoWStatusPopups.tick')()
    assert own.eval('WoWStatusLevelPopup') is None
    pump(own)
    assert warning_packets(own) == []
    # A report from an older version is ignored.
    report = f'J2 {group(friend)} W a {client} 1793000000 Eldrin-TestRealm'
    assert not friend.eval('WoWStatusJournal.receive')(report, 'Thora-TestRealm', 'WHISPER')
    friend.eval('WoWStatusPopups.tick')()
    assert friend.eval('WoWStatusLevelPopup') is None


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
def test_bad_catchup_is_dropped_without_a_warning(edition):
    lua = member(edition=edition)
    assert not offer_entry(lua)
    assert lua.eval('#WoWStatusJournal.entries()') == 0
    lua.eval('WoWStatusPopups.tick')()
    assert lua.eval('WoWStatusLevelPopup') is None
    pump(lua, start=6)
    assert warning_packets(lua) == []


def test_valid_level_cannot_smuggle_free_text_through_catchup():
    lua = member()
    assert not offer_entry(lua, level='30', detail='Unrelated announcement')
    assert lua.eval('#WoWStatusJournal.entries()') == 0
    lua.eval('WoWStatusPopups.tick')()
    assert lua.eval('WoWStatusLevelPopup') is None


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


def test_invalid_data_is_never_reported_to_the_group():
    lua = member()
    g = group(lua)
    report = lua.eval('WoWStatusJournal.reportInvalid')
    assert not report(g, 'Eldrin-TestRealm')
    pump(lua)
    assert warning_packets(lua) == []
