"""Relayed catch-up entries are claims by the relay (issue #3).

A relay must not be able to claim a member's next event ID before the event
happens, and the log must keep who relayed an entry first.
"""
import re

from test_journal import actor, clock, deliver_popup, mesh


def digest(text):
    a, b, c = 5381, 2166136261, 104729
    for byte in text.encode():
        a, b, c = (a * 33 + byte) % 2**32, (b * 65599 + byte) % 2**32, (c * 131 + byte) % 2**32
    return f'{a:08x}{b:08x}{c % 16777216:06x}'


def pack(values):
    return ''.join(f'{len(v.encode())}:{v}' for v in values)


def group_of(lua):
    return lua.eval('function() for id in pairs(character().group_ids) do return id end end')()


def send_entry(send, token, record):
    """Send one record as the D parts of a catch-up transfer."""
    encoded, d = pack(record).encode().hex(), digest(record[0])
    chunks = [encoded[i:i + 140] for i in range(0, len(encoded), 140)]
    for part, chunk in enumerate(chunks, 1):
        send(f'D {token} {d} {part}/{len(chunks)} {chunk}')


def relay(victim, sender, record, start=11, via=None, group=None):
    """Drive the normal H/Q/I/D catch-up exchange from a modified client."""
    group, client = group or group_of(victim), victim.eval('WoWStatusAdapter.client_id')
    # Packets go through the frame's CHAT_MSG_ADDON handler; this records what
    # J.receive returned, so a refused packet can't pass silently.
    victim.execute("""
        if not __receiveWrapped then
            local receive=WoWStatusJournal.receive
            function WoWStatusJournal.receive(...) __received=receive(...);return __received end
            __receiveWrapped=true
        end
    """)

    def send(text):
        victim.execute('__received=nil')
        victim.eval('fire')('CHAT_MSG_ADDON', 'WoWStatusLog', f'J2 {group} {text}', 'WHISPER', sender)
        return victim.eval('__received')
    # Only a query sent after this hello counts: with a stale token every later
    # packet would be refused and the caller's checks would pass without testing.
    before = victim.eval('#__sent')
    clock(victim, start)
    send(f'H {1793000000 + start}-1 {client}')
    token = None
    for step in range(30):
        clock(victim, start + step)
        victim.eval('WoWStatusJournal.tick')()
        for i in range(before + 1, victim.eval('#__sent') + 1):
            packet = victim.eval(f'__sent[{i}]')
            match = re.match(rf'J2 {group} Q (\S+) ', packet['text'])
            if packet['target'] == sender and match:
                token = match.group(1)
        if token:
            break
    assert token, f'{sender} was never queried'
    d = digest(record[0])
    assert send(f'I {token} 1 0 {d}'), 'inventory refused'
    if via:
        send(f'V {token} {d} {via}')
    send_entry(send, token, record)
    return token, d


def entries_from(lua, sender):
    return lua.eval('''function(sender)
        local r={}
        for _,e in ipairs(WoWStatusJournal.entries()) do
            if e.sender==sender then r[#r+1]={id=e.id,kind=e.kind,text=e.text,origin=e.origin,via=e.via,relay=e.relay} end
        end
        return r
    end''')(sender)


def kinds_from(lua, sender):
    return sorted(e['kind'] for e in entries_from(lua, sender).values())


def popup_text(lua):
    return lua.eval('WoWStatusLevelPopup and WoWStatusLevelPopup.message.text or ""')


def next_old_id(victim, thora):
    """The ID an older client gives Thora's next event: '<epoch>-<sequence+1>'."""
    client = victim.eval('WoWStatusAdapter.client_id')
    return f"{client}:thora-testrealm:{thora.eval('character().epoch')}-{thora.eval('character().sequence') + 1}"


def preclaim(victim, event_id, text='Died', sender='Mallory-TestRealm', at='1793000012', kind='death', start=11):
    client = victim.eval('WoWStatusAdapter.client_id')
    relay(victim, sender, [event_id, client, 'Thora-TestRealm', at, kind, '', text, '', '', '', ''], start=start)


def older_client(lua):
    """A sender without random nonce tails, as before this change."""
    lua.execute('function WoWStatusPopups.newNonce(c) return c.epoch.."-"..c.sequence end')
    return lua


def test_relay_cannot_preempt_a_members_next_event():
    """The issue's reproduction, verbatim apart from the shared helper."""
    victim, thora = actor('Mira'), actor('Thora')
    clock(victim, 10)
    clock(thora, 10)
    victim.execute('__peers={"Thora-TestRealm","Mallory-TestRealm"}')
    client = victim.eval('WoWStatusAdapter.client_id')
    nonce = f"{thora.eval('character().epoch')}-{thora.eval('character().sequence') + 1}"
    relay(victim, 'Mallory-TestRealm', [f'{client}:thora-testrealm:{nonce}', client, 'Thora-TestRealm',
                                        '1793000012', 'death', '', 'Died - written by Mallory', '', '', '', ''])
    thora.eval('fire')('PLAYER_LEVEL_UP', 2)
    deliver_popup(thora, victim)
    assert 'level' in kinds_from(victim, 'Thora-TestRealm')


def test_new_event_ids_have_an_unpredictable_tail():
    victim, thora = actor('Mira'), actor('Thora')
    clock(victim, 10)
    clock(thora, 10)
    victim.execute('__peers={"Thora-TestRealm","Mallory-TestRealm"}')
    guessed = next_old_id(victim, thora)
    preclaim(victim, guessed)
    thora.eval('fire')('PLAYER_LEVEL_UP', 2)
    thora.eval('fire')('PLAYER_LEVEL_UP', 3)
    nonces = [thora.eval(f'character().events[{i}].nonce') for i in (1, 2)]
    epoch, sequence = thora.eval('character().epoch'), thora.eval('character().sequence')
    assert re.fullmatch(rf'{epoch}-{sequence - 1}-[0-9a-f]{{8}}', nonces[0])
    assert re.fullmatch(rf'{epoch}-{sequence}-[0-9a-f]{{8}}', nonces[1])
    assert nonces[0][-8:] != nonces[1][-8:]
    assert all(len(n) <= 64 for n in nonces)
    # The live packet, the sender's log and the receiver's log all use that nonce.
    assert nonces[0] in thora.eval('__sent[1].text').split(' ')
    own_id = thora.eval('WoWStatusJournal.entries()[2].id')
    assert own_id.endswith(':thora-testrealm:' + nonces[0])
    deliver_popup(thora, victim)
    assert popup_text(victim) == 'Thora reached level 2!'
    entries = entries_from(victim, 'Thora-TestRealm')
    assert {e['id'] for e in entries.values()} == {guessed, own_id}
    assert kinds_from(victim, 'Thora-TestRealm') == ['death', 'level']


def test_live_packet_replaces_a_relay_only_entry():
    victim, thora = actor('Mira'), older_client(actor('Thora'))
    clock(victim, 10)
    clock(thora, 10)
    victim.execute('__peers={"Thora-TestRealm","Mallory-TestRealm"}')
    guessed = next_old_id(victim, thora)
    preclaim(victim, guessed)
    assert kinds_from(victim, 'Thora-TestRealm') == ['death']
    thora.eval('fire')('PLAYER_LEVEL_UP', 2)
    victim.execute('''
        __logWrites=0
        local received=WoWStatusJournal.received
        function WoWStatusJournal.received(item) __logWrites=__logWrites+1;return received(item) end
    ''')
    deliver_popup(thora, victim)
    assert victim.eval('__logWrites') == 1
    entries = list(entries_from(victim, 'Thora-TestRealm').values())
    assert len(entries) == 1
    assert (entries[0]['id'], entries[0]['kind'], entries[0]['text']) == (guessed, 'level', 'Reached level 2!')
    assert entries[0]['origin'] == 'live' and entries[0]['via'] is None
    assert popup_text(victim) == 'Thora reached level 2!'
    # A later relay can't swap it back (after the 10-minute hello rate, #4).
    preclaim(victim, guessed, sender='Mallory-TestRealm', start=700)
    assert kinds_from(victim, 'Thora-TestRealm') == ['level']


def test_live_packet_replaces_a_relay_claim_even_when_its_popup_is_dropped():
    victim = actor('Mira')
    group, client = group_of(victim), victim.eval('WoWStatusAdapter.client_id')
    channel = victim.eval('WoWStatusGroups.channel')(group)
    victim.execute('__peers={"Thora-TestRealm","Mallory-TestRealm"}')
    preclaim(victim, f'{client}:thora-testrealm:old-6')
    victim.execute('__combat=true')
    receive = victim.eval('WoWStatusPopups.receive')
    for level in range(2, 7):
        receive(f'WSTATUS2 {client} LEVEL {level} {victim.eval("time()")} old-{level}', 'Thora-TestRealm', channel)
    assert victim.eval('WoWStatusDB.popups.last_receive.state') == 'sender_queue_full'
    entry = entries_from(victim, 'Thora-TestRealm')
    texts = {e['id']: (e['text'], e['origin']) for e in entry.values()}
    assert texts[f'{client}:thora-testrealm:old-6'] == ('Reached level 6!', 'live')
    assert len(texts) == 4 + 1  # four queued level-ups plus the replaced claim


def test_matching_relayed_copy_stays_quiet_and_becomes_live():
    author, relay_client, late = actor('Thora'), actor('Eldrin'), actor('Mira')
    clock(author, 10)
    clock(relay_client, 10)
    author.eval('fire')('PLAYER_LEVEL_UP', 2)
    deliver_popup(author, relay_client)
    late.eval('WoWStatusJournal.sync')()
    mesh({'Eldrin': relay_client, 'Mira': late}, duration=40)
    [entry] = entries_from(late, 'Thora-TestRealm').values()
    assert (entry['origin'], entry['via'], entry['relay']) == ('catchup', 'Eldrin-TestRealm', None)
    deliver_popup(author, late)
    assert late.eval('WoWStatusLevelPopup') is None
    assert late.eval('WoWStatusDB.popups.last_receive.state') == 'already_in_log'
    [entry] = entries_from(late, 'Thora-TestRealm').values()
    assert (entry['origin'], entry['via']) == ('live', None)


def test_cut_live_text_matches_the_full_relayed_copy():
    victim = actor('Mira')
    group, client = group_of(victim), victim.eval('WoWStatusAdapter.client_id')
    channel = victim.eval('WoWStatusGroups.channel')(group)
    victim.execute('__peers={"Thora-TestRealm","Eldrin-TestRealm"}')
    full = 'Learned Jewelcrafting of the Very Long Localized Name (Artisan)'
    preclaim(victim, f'{client}:thora-testrealm:e-7', text=full, sender='Eldrin-TestRealm', kind='profession')
    cut = full[:45] + '...'
    now = victim.eval('time()')
    assert not victim.eval('WoWStatusPopups.receive')(
        f'WSTATUS3 {client} profession 1793000012 e-7 {cut.encode().hex()}', 'Thora-TestRealm', channel)
    assert now - 1793000012 < 120
    assert victim.eval('WoWStatusDB.popups.last_receive.state') == 'already_in_log'
    # The relay's longer text could be invented past the cut, so the live text wins.
    [entry] = entries_from(victim, 'Thora-TestRealm').values()
    assert (entry['text'], entry['origin']) == (cut, 'live')


def test_via_keeps_the_first_relay_across_hops():
    eldrin, mira = actor('Eldrin'), actor('Mira')
    clock(eldrin, 10)
    eldrin.execute('__peers={"Mallory-TestRealm","Mira-TestRealm"}')
    client = eldrin.eval('WoWStatusAdapter.client_id')
    forged = f'{client}:thora-testrealm:forged-1'
    preclaim(eldrin, forged, at='1793000012')
    [entry] = entries_from(eldrin, 'Thora-TestRealm').values()
    assert (entry['via'], entry['relay']) == ('Mallory-TestRealm', None)
    mira.eval('WoWStatusJournal.sync')()
    mesh({'Eldrin': eldrin, 'Mira': mira}, start=42, duration=40)
    sent = [eldrin.eval(f'__sent[{i}].text') for i in range(1, eldrin.eval('#__sent') + 1)]
    assert any(re.fullmatch(r'J2 \w+ V \S+ [0-9a-f]{22} Mallory-TestRealm', text) for text in sent)
    [entry] = entries_from(mira, 'Thora-TestRealm').values()
    assert (entry['id'], entry['origin']) == (forged, 'catchup')
    assert (entry['via'], entry['relay']) == ('Mallory-TestRealm', 'Eldrin-TestRealm')
    mira.execute('WoWStatusJournal.show()')
    details = mira.eval('''function()
        local r={}
        for _,row in ipairs(WoWStatusActivityLog.rows) do if row.entry then r[#r+1]=row.detail.text end end
        return table.concat(r,"\\n")
    end''')()
    assert 'Caught up via Mallory-TestRealm, passed on by Eldrin-TestRealm' in details
    # Another relay of the same entry later keeps the first one.
    mira.execute('__peers={"Eldrin-TestRealm","Zed-TestRealm"}')
    preclaim(mira, forged, sender='Zed-TestRealm', start=90)
    [entry] = entries_from(mira, 'Thora-TestRealm').values()
    assert (entry['via'], entry['relay']) == ('Mallory-TestRealm', 'Eldrin-TestRealm')


def test_relay_that_saw_an_entry_live_names_itself_and_sends_no_via():
    author, eldrin, mira = actor('Thora'), actor('Eldrin'), actor('Mira')
    clock(author, 10)
    clock(eldrin, 10)
    author.eval('fire')('PLAYER_LEVEL_UP', 2)
    deliver_popup(author, eldrin)
    mira.eval('WoWStatusJournal.sync')()
    mesh({'Eldrin': eldrin, 'Mira': mira}, duration=40)
    sent = [eldrin.eval(f'__sent[{i}].text') for i in range(1, eldrin.eval('#__sent') + 1)]
    assert not any(' V ' in text for text in sent)
    [entry] = entries_from(mira, 'Thora-TestRealm').values()
    assert (entry['via'], entry['relay']) == ('Eldrin-TestRealm', None)


def test_unsolicited_or_malformed_via_claims_are_ignored():
    victim = actor('Mira')
    group, client = group_of(victim), victim.eval('WoWStatusAdapter.client_id')
    victim.execute('__peers={"Mallory-TestRealm","Eldrin-TestRealm"}')
    receive = victim.eval('WoWStatusJournal.receive')
    d = digest(f'{client}:thora-testrealm:x-1')
    assert not receive(f'J2 {group} V unknown {d} Mallory-TestRealm', 'Eldrin-TestRealm', 'WHISPER')
    record = [f'{client}:thora-testrealm:x-1', client, 'Thora-TestRealm', '1793000012', 'death', '', 'Died',
              '', '', '', '']
    # A pipe in the claimed name, or a claim for an entry that was not offered, is dropped.
    token, d = relay(victim, 'Eldrin-TestRealm', record, via='Evil|cff-TestRealm')
    [entry] = entries_from(victim, 'Thora-TestRealm').values()
    assert (entry['via'], entry['relay']) == ('Eldrin-TestRealm', None)
    assert not receive(f'J2 {group} V {token} {"0" * 22} Mallory-TestRealm', 'Eldrin-TestRealm', 'WHISPER')


def test_old_nonces_are_still_accepted():
    victim = actor('Mira')
    group, client = group_of(victim), victim.eval('WoWStatusAdapter.client_id')
    channel = victim.eval('WoWStatusGroups.channel')(group)
    victim.execute('__peers={"Thora-TestRealm","Eldrin-TestRealm"}')
    now = victim.eval('time()')
    assert victim.eval('WoWStatusPopups.receive')(
        f'WSTATUS2 {client} LEVEL 5 {now} 1793000000-123456-7', 'Thora-TestRealm', channel)
    assert victim.eval('WoWStatusJournal.contains')(f'{client}:thora-testrealm:1793000000-123456-7')
    # An older relay's catch-up entry with an old-form ID.
    record = [f'{client}:eldrin-testrealm:1793000000-654321-3', client, 'Eldrin-TestRealm', '1793000012', 'death',
              '', 'Died', '', '', '', '']
    relay(victim, 'Eldrin-TestRealm', record)
    assert victim.eval('WoWStatusJournal.contains')(record[0])


def test_events_saved_before_random_tails_keep_their_ids():
    lua = actor('Thora')
    lua.execute('''
        local c=character()
        table.insert(c.history.events,{id=c.identity.guid..":"..c.epoch..":7",kind="death",at=time(),data={}})
        WoWStatusDB.journal.migrated={}
        WoWStatusJournal.init(WoWStatusDB,c)
    ''')
    epoch = lua.eval('character().epoch')
    assert lua.eval('WoWStatusJournal.contains')(f'classic-era:thora-testrealm:{epoch}-7')


def test_authors_own_copy_replaces_a_relay_claim_at_login_sync():
    """A member offline for the live packet later gets the author's copy, not the forgery."""
    thora, eldrin = actor('Thora'), actor('Eldrin')
    clock(thora, 10)
    thora.eval('fire')('PLAYER_LEVEL_UP', 2)
    real = thora.eval('WoWStatusJournal.entries()[1].id')
    clock(eldrin, 10)
    eldrin.execute('__peers={"Mallory-TestRealm","Thora-TestRealm"}')
    preclaim(eldrin, real, at='1793000010')
    assert kinds_from(eldrin, 'Thora-TestRealm') == ['death']
    eldrin.eval('WoWStatusJournal.sync')()
    mesh({'Thora': thora, 'Eldrin': eldrin}, start=42, duration=40)
    [entry] = entries_from(eldrin, 'Thora-TestRealm').values()
    assert (entry['id'], entry['kind'], entry['text']) == (real, 'level', 'Reached level 2!')
    assert (entry['origin'], entry['via'], entry['relay']) == ('catchup', 'Thora-TestRealm', None)


def test_authors_matching_copy_confirms_a_relayed_entry_once():
    thora, eldrin, mira = actor('Thora'), actor('Eldrin'), actor('Mira')
    clock(thora, 10)
    clock(eldrin, 10)
    thora.eval('fire')('PLAYER_LEVEL_UP', 2)
    deliver_popup(thora, eldrin)
    mira.eval('WoWStatusJournal.sync')()
    mesh({'Eldrin': eldrin, 'Mira': mira}, duration=40)
    [entry] = entries_from(mira, 'Thora-TestRealm').values()
    assert (entry['origin'], entry['via']) == ('catchup', 'Eldrin-TestRealm')
    # Thora comes online; a roster of a new size is read at once.
    everyone = {'Thora': thora, 'Eldrin': eldrin, 'Mira': mira}
    mira.eval('WoWStatusJournal.groupsChanged')()
    mesh(everyone, start=52, duration=40)
    [entry] = entries_from(mira, 'Thora-TestRealm').values()
    assert (entry['origin'], entry['via'], entry['relay']) == ('catchup', 'Thora-TestRealm', None)
    # Confirmed copies are not fetched again.
    fetched = mira.eval('#__sent')
    mira.eval('WoWStatusJournal.groupsChanged')()
    mesh(everyone, start=100, duration=40)
    assert any(' Q ' in mira.eval(f'__sent[{i}].text') for i in range(fetched + 1, mira.eval('#__sent') + 1))
    sent = [mira.eval(f'__sent[{i}].text') for i in range(fetched + 1, mira.eval('#__sent') + 1)]
    assert not any(' G ' in text for text in sent)


def test_a_forwarded_via_is_always_checked_by_the_forwarders_game():
    """A dishonest relay can't hide itself by naming someone else on the next hop."""
    eldrin, mira = actor('Eldrin'), actor('Mira')
    clock(eldrin, 10)
    eldrin.execute('__peers={"Evil-TestRealm","Mira-TestRealm"}')
    client = eldrin.eval('WoWStatusAdapter.client_id')
    forged = f'{client}:thora-testrealm:forged-2'
    relay(eldrin, 'Evil-TestRealm', [forged, client, 'Thora-TestRealm', '1793000012', 'death', '', 'Died',
                                      '', '', '', ''], via='Innocent-TestRealm')
    [entry] = entries_from(eldrin, 'Thora-TestRealm').values()
    assert (entry['via'], entry['relay']) == ('Innocent-TestRealm', 'Evil-TestRealm')
    mira.eval('WoWStatusJournal.sync')()
    mesh({'Eldrin': eldrin, 'Mira': mira}, start=42, duration=40)
    [entry] = entries_from(mira, 'Thora-TestRealm').values()
    assert (entry['via'], entry['relay']) == ('Evil-TestRealm', 'Eldrin-TestRealm')


def test_queued_parts_of_a_replaced_entry_are_not_sent():
    eldrin = older_client(actor('Eldrin'))
    group, client = group_of(eldrin), eldrin.eval('WoWStatusAdapter.client_id')
    channel = eldrin.eval('WoWStatusGroups.channel')(group)
    eldrin.execute('__peers={"Mallory-TestRealm","Thora-TestRealm","Mira-TestRealm"}')
    claimed = f'{client}:thora-testrealm:old-6'
    preclaim(eldrin, claimed)
    receive = eldrin.eval('WoWStatusJournal.receive')
    assert receive(f'J2 {group} Q mira-1 0 1793000000 7', 'Mira-TestRealm', 'WHISPER')
    assert receive(f'J2 {group} G mira-1 {digest(claimed)}', 'Mira-TestRealm', 'WHISPER')
    queued = eldrin.eval('#__sent')
    now = eldrin.eval('time()')
    eldrin.eval('WoWStatusPopups.receive')(f'WSTATUS2 {client} LEVEL 6 {now} old-6', 'Thora-TestRealm', channel)
    assert kinds_from(eldrin, 'Thora-TestRealm') == ['level']
    for step in range(20):
        clock(eldrin, 45 + step)
        eldrin.eval('WoWStatusJournal.tick')()
    sent = [eldrin.eval(f'__sent[{i}]') for i in range(queued + 1, eldrin.eval('#__sent') + 1)]
    to_mira = [p['text'] for p in sent if p['target'] == 'Mira-TestRealm' and p['prefix'] == 'WoWStatusLog']
    assert any(' I mira-1 ' in text for text in to_mira)
    assert not any(' D mira-1 ' in text or ' V mira-1 ' in text for text in to_mira)


def test_only_shared_events_get_a_nonce():
    lua = actor('Thora')
    clock(lua, 10)
    lua.eval('SlashCmdList.WOWSTATUS')('test')
    lua.eval('fire')('PLAYER_LEVEL_UP', 2)
    events = [(lua.eval(f'character().events[{i}].data.synthetic'), lua.eval(f'character().events[{i}].nonce'))
              for i in range(1, lua.eval('#character().events') + 1)]
    assert [synthetic for synthetic, _ in events] == [True, None]
    assert events[0][1] is None and events[1][1] is not None


def loot_record(client, event_id, text, quality, item_id):
    return [event_id, client, 'Thora-TestRealm', '1793000012', 'loot', '', text, str(quality), '4', 'INVTYPE_CHEST',
            str(item_id)]


def live_loot(victim, nonce, quality, item_id, name):
    group, client = group_of(victim), victim.eval('WoWStatusAdapter.client_id')
    channel = victim.eval('WoWStatusGroups.channel')(group)
    return victim.eval('WoWStatusPopups.receive')(
        f'WSTATUS7 {client} loot 1793000012 {nonce} {quality} 4 INVTYPE_CHEST {item_id} {name}', 'Thora-TestRealm',
        channel)


def loot_fields(lua):
    return lua.eval('''function()
        for _,e in ipairs(WoWStatusJournal.entries()) do
            if e.sender=="Thora-TestRealm" then return {text=e.text,quality=e.quality,item_id=e.item_id,origin=e.origin} end
        end
    end''')()


def test_a_confirmed_relay_claim_takes_every_field_from_the_live_copy():
    victim = actor('Mira')
    client = victim.eval('WoWStatusAdapter.client_id')
    victim.execute('__peers={"Thora-TestRealm","Mallory-TestRealm"}')
    record = loot_record(client, f'{client}:thora-testrealm:n-1', 'Equipped Robe', 4, 999)
    relay(victim, 'Mallory-TestRealm', record)
    assert loot_fields(victim)['item_id'] == 999
    assert not live_loot(victim, 'n-1', 3, 123, 'Robe')
    assert victim.eval('WoWStatusDB.popups.last_receive.state') == 'already_in_log'
    fields = loot_fields(victim)
    assert (fields['quality'], fields['item_id'], fields['origin']) == (3, 123, 'live')


def test_a_stub_text_claim_does_not_count_as_the_same_event():
    victim = actor('Mira')
    client = victim.eval('WoWStatusAdapter.client_id')
    victim.execute('__peers={"Thora-TestRealm","Mallory-TestRealm"}')
    relay(victim, 'Mallory-TestRealm', loot_record(client, f'{client}:thora-testrealm:n-2', 'Equipped ...', 4, 999))
    assert live_loot(victim, 'n-2', 3, 123, 'Robe')
    fields = loot_fields(victim)
    assert (fields['text'], fields['item_id'], fields['origin']) == ('Equipped Robe', 123, 'live')


def test_a_relay_cannot_extend_a_live_entrys_cut_text():
    victim = actor('Mira')
    victim.eval('WoWStatusGroups.update')('dawnwatch\nother-group', '')
    client = victim.eval('WoWStatusAdapter.client_id')
    first, second = victim.eval('''function()
        local ids={} for id in pairs(character().group_ids) do ids[#ids+1]=id end
        table.sort(ids) return ids[1],ids[2] end''')()
    victim.execute('__peers={"Thora-TestRealm","Mallory-TestRealm"}')
    full = 'Learned Jewelcrafting of the Very Long Localized Name (Artisan)'
    cut = full[:45] + '...'
    channel = victim.eval('WoWStatusGroups.channel')(first)
    now = victim.eval('time()')
    assert victim.eval('WoWStatusPopups.receive')(
        f'WSTATUS3 {client} profession {now} e-8 {cut.encode().hex()}', 'Thora-TestRealm', channel)
    record = [f'{client}:thora-testrealm:e-8', client, 'Thora-TestRealm', str(now), 'profession', '',
              full + ' and more', '', '', '', '']
    relay(victim, 'Mallory-TestRealm', record, group=second)
    [entry] = entries_from(victim, 'Thora-TestRealm').values()
    assert (entry['text'], entry['origin']) == (cut, 'live')
    assert victim.eval('function(g) return WoWStatusJournal.entries()[1].groups[g] end')(second)


def test_an_authenticated_copy_from_an_own_character_keeps_the_existing_entry():
    victim = actor('Mira')
    group, client = group_of(victim), victim.eval('WoWStatusAdapter.client_id')
    victim.execute('__peers={"Alt-TestRealm","Mallory-TestRealm"}')
    claim = [f'{client}:alt-testrealm:a-1', client, 'Alt-TestRealm', '1793000012', 'death', '', 'Died', '', '', '', '']
    relay(victim, 'Mallory-TestRealm', claim)
    # The account's new character Alt logs in on this client later.
    victim.execute('''
        local c=character()
        WoWStatusDB.characters["zz-alt"]={identity={name="Alt",realm="TestRealm",client=WoWStatusAdapter.client_id,
            guid="Player-123-Alt"},settings=c.settings,group_ids=c.group_ids}
    ''')
    real = list(claim)
    real[6] = 'Total deaths: 3'
    relay(victim, 'Alt-TestRealm', real, start=60, group=group)
    assert victim.eval('WoWStatusJournal.contains')(claim[0])
    assert [e['text'] for e in entries_from(victim, 'Alt-TestRealm').values()] == ['Died']


def test_a_via_naming_the_sender_keeps_the_games_spelling():
    victim = actor('Mira')
    client = victim.eval('WoWStatusAdapter.client_id')
    victim.execute('__peers={"Eldrin-TestRealm"}')
    record = [f'{client}:thora-testrealm:s-1', client, 'Thora-TestRealm', '1793000012', 'death', '', 'Died',
              '', '', '', '']
    relay(victim, 'Eldrin-TestRealm', record, via='ELDRIN')
    [entry] = entries_from(victim, 'Thora-TestRealm').values()
    assert (entry['via'], entry['relay']) == ('Eldrin-TestRealm', None)


def test_the_authors_full_copy_keeps_the_groups_of_a_relayed_cut_copy():
    victim = actor('Mira')
    victim.eval('WoWStatusGroups.update')('dawnwatch\nother-group', '')
    client = victim.eval('WoWStatusAdapter.client_id')
    first, second = victim.eval('''function()
        local ids={} for id in pairs(character().group_ids) do ids[#ids+1]=id end
        table.sort(ids) return ids[1],ids[2] end''')()
    victim.execute('__peers={"Thora-TestRealm","Eldrin-TestRealm"}')
    full = 'Learned Jewelcrafting of the Very Long Localized Name (Artisan)'
    record = [f'{client}:thora-testrealm:e-9', client, 'Thora-TestRealm', '1793000012', 'profession', '',
              full[:45] + '...', '', '', '', '']
    relay(victim, 'Eldrin-TestRealm', record, group=second)
    record[6] = full
    relay(victim, 'Thora-TestRealm', record, start=60, group=first)
    [entry] = entries_from(victim, 'Thora-TestRealm').values()
    assert (entry['text'], entry['via']) == (full, 'Thora-TestRealm')
    groups = victim.eval('function(a,b) local g=WoWStatusJournal.entries()[1].groups return g[a]==true and g[b]==true end')
    assert groups(first, second)
