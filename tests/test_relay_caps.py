"""One relay must not be able to flood the activity log (issue #4).

Own entries and received entries are capped separately, one member can deliver
only a bounded share of new catch-up entries per session, and a member's sync
hellos start at most one pull per ten minutes.
"""
import re

from test_journal import actor, clock, mesh
from test_relay_provenance import digest, entries_from, group_of, pack, relay, send_entry

BASE = 1793000000


def test_one_relay_cannot_evict_own_log():
    """The issue's reproduction, verbatim apart from the imports above."""
    victim = actor('Mira')
    clock(victim, 10)
    victim.eval('fire')('PLAYER_LEVEL_UP', 2)
    own = victim.eval('WoWStatusJournal.entries()[1].id')
    victim.execute('__peers={"Mallory-TestRealm"}')
    group, client = group_of(victim), victim.eval('WoWStatusAdapter.client_id')
    send = lambda text: victim.eval('fire')('CHAT_MSG_ADDON', 'WoWStatusLog', f'J2 {group} {text}',  # noqa: E731
                                            'WHISPER', 'Mallory-TestRealm')
    send(f'H hello-1 {client}')
    seen, forged, now = 0, 0, 11.0
    while forged < 2010 and now < 3000:
        clock(victim, now)
        victim.eval('WoWStatusJournal.tick')()
        count = victim.eval('#__sent')
        for i in range(seen + 1, count + 1):
            match = re.match(rf'J2 {group} Q (\S+) (\d+) ', victim.eval(f'__sent[{i}].text'))
            if not match:
                continue
            token, offset, records = match.group(1), int(match.group(2)), []
            for _ in range(6):
                forged += 1
                records.append([f'{client}:someone-testrealm:f-{forged}', client, 'Someone-TestRealm',
                                str(1793000011 + forged % 600), 'death', '', 'Died', '', '', '', ''])
            send(f'I {token} {offset + 6} 1 ' + ','.join(digest(r[0]) for r in records))
            for record in records:
                encoded = pack(record).encode().hex()
                chunks = [encoded[j:j + 140] for j in range(0, len(encoded), 140)]
                for part, chunk in enumerate(chunks, 1):
                    send(f'D {token} {digest(record[0])} {part}/{len(chunks)} {chunk}')
        seen, now = count, now + 0.5
    assert victim.eval('WoWStatusJournal.contains')(own) is True   # fails: own entry evicted


def sender_of(index):
    """A distinct made-up member name per forged record: 'Aa'..'Zz' and so on."""
    letters = 'abcdefghijklmnopqrstuvwxyz'
    name = ''
    index += 26
    while index:
        index, rest = divmod(index, 26)
        name = letters[rest] + name
    return name.capitalize() + '-TestRealm'


def serve(victim, sender, record_for, start, stop, pages=None, deliver=True, during=None):
    """Answer the victim's catch-up queries to sender, in any group, from one list.

    record_for(n) gives the relay's n-th newest record (1-based), six a page; the
    list has `pages` pages (unbounded if None). With deliver=False the requested
    entries are never sent. during maps a time to a call made when it is reached.
    Returns the number of pages queried and the number of
    entries the victim fetched with G.
    """
    client = victim.eval('WoWStatusAdapter.client_id')

    def send(group, text):
        victim.eval('fire')('CHAT_MSG_ADDON', 'WoWStatusLog', f'J2 {group} {text}', 'WHISPER', sender)

    def record(n):
        return [part.replace('{client}', client) for part in record_for(n)]
    seen, queried, fetched, now = victim.eval('#__sent'), 0, 0, start
    records = {}
    during = dict(during or {})
    while now < stop:
        clock(victim, now)
        for at in sorted(at for at in during if at <= now):
            during.pop(at)()
        victim.eval('WoWStatusJournal.tick')()
        count = victim.eval('#__sent')
        for i in range(seen + 1, count + 1):
            packet = victim.eval(f'__sent[{i}]')
            if packet['target'] != sender:
                continue
            fetch = re.match(r'J2 (\S+) G (\S+) (\S+)$', packet['text'])
            if fetch:
                group, token = fetch.group(1), fetch.group(2)
                for d in fetch.group(3).split(','):
                    fetched += 1
                    if deliver:
                        send_entry(lambda text: send(group, text), token, records[d])
                continue
            query = re.match(r'J2 (\S+) Q (\S+) (\d+) ', packet['text'])
            if not query:
                continue
            queried += 1
            group, token, offset = query.group(1), query.group(2), int(query.group(3))
            page = [record(offset + k) for k in range(1, 7)]
            for r in page:
                records[digest(r[0])] = r
            more = pages is None or offset + 6 < pages * 6
            send(group, f'I {token} {offset + 6} {1 if more else 0} ' + ','.join(digest(r[0]) for r in page))
        seen, now = count, now + 0.5
    return queried, fetched


def forged_record(n, sender=None):
    sender = sender or sender_of(n)
    key = sender.lower()
    return ['{client}:' + f'{key}:f-{n}', '{client}', sender, str(BASE + 11 + n % 600),
            'death', '', 'Died', '', '', '', '']


def received_from(lua, relay):
    return lua.eval('''function(relay)
        local n=0
        for _,e in ipairs(WoWStatusJournal.entries()) do if e.via==relay and not e.owner then n=n+1 end end
        return n
    end''')(relay)


def claiming(lua, sender):
    return lua.eval('''function(sender)
        local n=0
        for _,e in ipairs(WoWStatusJournal.entries()) do if e.sender==sender then n=n+1 end end
        return n
    end''')(sender)


def groups_of(lua):
    return lua.eval('''function()
        local ids={} for id in pairs(character().group_ids) do ids[#ids+1]=id end
        table.sort(ids) return ids[1],ids[2] end''')()


def queries_to(lua, target):
    return [p['text'] for p in lua.eval('__sent').values()
            if p['target'] == target and p['prefix'] == 'WoWStatusLog' and ' Q ' in p['text']]


def test_received_entries_never_evict_own_entries_and_each_side_keeps_its_cap():
    victim = actor('Mira')
    group = group_of(victim)
    victim.execute(f'''
        local c,list=character(),WoWStatusDB.journal.entries
        local name=c.identity.name.."-"..c.identity.realm
        for i=1,2100 do
            list[#list+1]={{id="own:"..i,client=c.identity.client,sender=name,owner=c.identity.guid,kind="death",
                text="Died",at={BASE}-100000+i,groups={{["{group}"]=true}},origin="mine"}}
        end
        -- Every received entry is newer than every own one.
        for i=1,2100 do
            list[#list+1]={{id=c.identity.client..":someone-testrealm:r-"..i,client=c.identity.client,
                sender="Someone-TestRealm",kind="death",text="Died",at={BASE}-50000+i,groups={{["{group}"]=true}},
                origin="catchup",via="Someone-TestRealm"}}
        end
        WoWStatusJournal.init(WoWStatusDB,c)
    ''')
    counts = victim.eval('''function()
        local own,received,oldest=0,0,nil
        for _,e in ipairs(WoWStatusJournal.entries()) do
            if e.owner then own=own+1 else received=received+1;oldest=math.min(oldest or e.at,e.at) end
        end
        return own,received,oldest
    end''')()
    # Each side keeps its newest 2,000 of 2,100, though every received entry is newer.
    assert tuple(counts) == (2000, 2000, BASE - 50000 + 101)
    assert victim.eval('WoWStatusJournal.contains')('own:2100')
    assert victim.eval('WoWStatusJournal.contains')('own:101')
    assert not victim.eval('WoWStatusJournal.contains')('own:100')


def test_local_only_entries_keep_their_own_limit_within_the_own_cap():
    victim = actor('Mira')
    group = group_of(victim)
    victim.execute(f'''
        local c,list=character(),WoWStatusDB.journal.entries
        local name=c.identity.name.."-"..c.identity.realm
        for i=1,1200 do
            list[#list+1]={{id="private:"..i,client=c.identity.client,sender=name,owner=c.identity.guid,kind="death",
                text="Died",at={BASE}-200000+i,groups={{}},origin="mine"}}
        end
        for i=1,500 do
            list[#list+1]={{id="own:"..i,client=c.identity.client,sender=name,owner=c.identity.guid,kind="death",
                text="Died",at={BASE}-300000+i,groups={{["{group}"]=true}},origin="mine"}}
        end
        WoWStatusJournal.init(WoWStatusDB,c)
    ''')
    assert victim.eval('#WoWStatusJournal.entries()') == 1500
    assert victim.eval('WoWStatusJournal.contains')('private:201')
    assert not victim.eval('WoWStatusJournal.contains')('private:200')
    assert victim.eval('WoWStatusJournal.contains')('own:1')


def test_one_relay_delivers_at_most_its_session_share():
    victim = actor('Mira')
    victim.execute('__peers={"Mallory-TestRealm"}')
    queried, fetched = serve(victim, 'Mallory-TestRealm', forged_record, 11, 400, pages=60)
    # Every page is read, but only the first 300 new entries are fetched.
    assert (queried, fetched) == (60, 300)
    assert received_from(victim, 'Mallory-TestRealm') == 300
    # A later hello from the same member, after the rate interval, starts a pull
    # that fetches nothing new this session.
    group, client = group_of(victim), victim.eval('WoWStatusAdapter.client_id')
    clock(victim, 700)
    assert victim.eval('WoWStatusJournal.receive')(f'J2 {group} H {BASE + 690}-1 {client}',
                                                    'Mallory-TestRealm', 'WHISPER')
    queried, fetched = serve(victim, 'Mallory-TestRealm', lambda n: forged_record(n + 1000), 701, 900, pages=10)
    assert (queried, fetched) == (10, 0)
    assert received_from(victim, 'Mallory-TestRealm') == 300


def test_another_members_share_is_separate():
    victim = actor('Mira')
    victim.execute('__peers={"Mallory-TestRealm","Eldrin-TestRealm"}')
    serve(victim, 'Mallory-TestRealm', forged_record, 11, 400)
    assert received_from(victim, 'Mallory-TestRealm') == 300
    group, client = group_of(victim), victim.eval('WoWStatusAdapter.client_id')
    clock(victim, 401)
    victim.eval('WoWStatusJournal.receive')(f'J2 {group} H {BASE + 400}-1 {client}', 'Eldrin-TestRealm', 'WHISPER')
    serve(victim, 'Eldrin-TestRealm', lambda n: forged_record(n + 5000), 401, 450, pages=3)
    assert received_from(victim, 'Eldrin-TestRealm') == 18


def test_one_relay_vouches_for_at_most_a_hundred_entries_per_claimed_member():
    victim = actor('Mira')
    victim.execute('__peers={"Mallory-TestRealm"}')

    def record(n):
        # Alternate: an entry about Someone, then one Mallory wrote herself.
        return forged_record(n, 'Someone-TestRealm' if n % 2 else 'Mallory-TestRealm')
    queried, fetched = serve(victim, 'Mallory-TestRealm', record, 11, 400)
    assert fetched == 300
    assert claiming(victim, 'Someone-TestRealm') == 100
    # A member's own entries count only toward its overall share.
    assert claiming(victim, 'Mallory-TestRealm') == 150


def test_a_login_hello_delayed_by_a_chat_lockdown_still_starts_a_pull():
    """Review round 1: a hello held back for a long time is still a login hello."""
    victim = actor('Mira')
    victim.execute('__peers={"Thora-TestRealm"}')
    group, client = group_of(victim), victim.eval('WoWStatusAdapter.client_id')
    clock(victim, 100)
    victim.eval('WoWStatusJournal.tick')()  # the victim's own login window is over
    victim.execute('__sent={}')
    clock(victim, 2000)
    # Thora logged in at 0; her hello waited in her send queue until now.
    assert victim.eval('WoWStatusJournal.receive')(f'J2 {group} H {BASE}-1 {client}', 'Thora-TestRealm', 'WHISPER')
    for step in range(10):
        clock(victim, 2001 + step)
        victim.eval('WoWStatusJournal.tick')()
    assert len(queries_to(victim, 'Thora-TestRealm')) == 1


def test_hellos_over_the_rate_wait_and_start_one_pull_when_it_ends():
    victim = actor('Mira')
    victim.execute('__peers={"Mallory-TestRealm","Eldrin-TestRealm"}')
    group, client = group_of(victim), victim.eval('WoWStatusAdapter.client_id')
    clock(victim, 100)
    victim.eval('WoWStatusJournal.tick')()
    victim.execute('__sent={}')
    receive = victim.eval('WoWStatusJournal.receive')

    def hello(at, sender='Mallory-TestRealm', serial=1):
        clock(victim, at)
        return receive(f'J2 {group} H {BASE + at}-{serial} {client}', sender, 'WHISPER')

    def pump(start, stop):
        """Tick each second, answering every query with an empty page so pulls end."""
        for now in range(start, stop):
            clock(victim, now)
            victim.eval('WoWStatusJournal.tick')()
            for target in ('Mallory-TestRealm', 'Eldrin-TestRealm'):
                for text in queries_to(victim, target):
                    receive(f'J2 {group} I {text.split(" ")[3]} 0 0 -', target, 'WHISPER')

    def pulls(target='Mallory-TestRealm'):
        return len(queries_to(victim, target))

    assert hello(1000)
    pump(1001, 1010)
    assert pulls() == 1
    # The same nonce again is a duplicate, quietly accepted without a new pull.
    assert receive(f'J2 {group} H {BASE + 1000}-1 {client}', 'Mallory-TestRealm', 'WHISPER')
    # New login nonces within ten minutes are over the rate: no pull now.
    assert not hello(1300, serial=2)
    assert not hello(1590, serial=3)
    pump(1590, 1600)
    assert pulls() == 1
    # When the interval ends, the waiting hellos start one pull between them.
    pump(1600, 1610)
    assert pulls() == 2
    # Another member's hello has its own rate.
    assert hello(1610, 'Eldrin-TestRealm')
    # The deferred pull started a new interval.
    assert not hello(1700, serial=4)
    pump(1700, 2199)
    assert pulls() == 2
    pump(2200, 2205)
    assert pulls() == 3


def test_a_member_withholding_entries_cannot_reset_its_hello_rate():
    """Review round 2: only a retry with no answer at all clears the rate."""
    victim = actor('Mira')
    victim.execute('__peers={"Mallory-TestRealm"}')
    group, client = group_of(victim), victim.eval('WoWStatusAdapter.client_id')
    clock(victim, 100)
    victim.eval('WoWStatusJournal.tick')()
    receive = victim.eval('WoWStatusJournal.receive')
    clock(victim, 1000)
    assert receive(f'J2 {group} H {BASE + 1000}-1 {client}', 'Mallory-TestRealm', 'WHISPER')
    # Mallory answers both the pull and its retry but never sends the entries.
    queried, fetched = serve(victim, 'Mallory-TestRealm', forged_record, 1001, 1300, pages=1, deliver=False)
    assert queried == 2
    clock(victim, 1300)
    assert not receive(f'J2 {group} H {BASE + 1300}-2 {client}', 'Mallory-TestRealm', 'WHISPER')


def test_a_dropped_entry_does_not_stall_the_pull():
    """Review round 2: an entry this client can't keep still finishes its page."""
    victim = actor('Mira')
    victim.execute('__peers={"Eldrin-TestRealm"}')

    def record(n):
        values = forged_record(n)
        if n == 2:
            values[4] = 'futurekind'  # a kind from a newer version
        if n == 3:
            values[3] = str(BASE - 100)  # before this client joined the group
        return values
    queried, fetched = serve(victim, 'Eldrin-TestRealm', record, 11, 200, pages=5)
    assert (queried, fetched) == (5, 30)
    assert received_from(victim, 'Eldrin-TestRealm') == 28


def test_a_full_responder_answers_queries_past_two_thousand():
    """Review round 2: with separate caps a log can offer up to 4,000 entries."""
    responder = actor('Thora')
    group = group_of(responder)
    clock(responder, 5000)
    responder.execute(f'''
        local c,list=character(),WoWStatusDB.journal.entries
        local name=c.identity.name.."-"..c.identity.realm
        for i=1,1500 do
            list[#list+1]={{id=c.identity.client..":thora-testrealm:o-"..i,client=c.identity.client,sender=name,
                owner=c.identity.guid,kind="death",text="Died",at={BASE}+i,groups={{["{group}"]=true}},origin="mine"}}
            list[#list+1]={{id=c.identity.client..":someone-testrealm:r-"..i,client=c.identity.client,
                sender="Someone-TestRealm",kind="death",text="Died",at={BASE}+i,groups={{["{group}"]=true}},
                origin="live"}}
        end
        WoWStatusJournal.init(WoWStatusDB,c)
        __peers={{"Mira-TestRealm"}}
        __sent={{}}
    ''')
    assert responder.eval('#WoWStatusJournal.entries()') == 3000
    assert responder.eval('WoWStatusJournal.receive')(f'J2 {group} Q q-1 2004 {BASE} 7', 'Mira-TestRealm', 'WHISPER')
    for step in range(5):
        clock(responder, 5001 + step)
        responder.eval('WoWStatusJournal.tick')()
    answers = [p['text'] for p in responder.eval('__sent').values() if ' I q-1 ' in p['text']]
    assert len(answers) == 1 and answers[0].split(' ')[4:6] == ['2010', '1']


def test_the_authors_copy_replaces_a_claim_after_the_authors_share_is_spent():
    """Review round 2: paging continues for fetches that add no entry."""
    victim = actor('Mira')
    victim.execute('__peers={"Mallory-TestRealm"}')
    client = victim.eval('WoWStatusAdapter.client_id')
    claim = [f'{client}:thora-testrealm:x-1', client, 'Thora-TestRealm', str(BASE + 12), 'death', '', 'Died',
             '', '', '', '']
    relay(victim, 'Mallory-TestRealm', claim)
    victim.execute('__peers={"Mallory-TestRealm","Thora-TestRealm"}')

    def record(n):
        if n == 307:
            return ['{client}:thora-testrealm:x-1', '{client}', 'Thora-TestRealm', str(BASE + 12), 'death', '',
                    'Total deaths: 3', '', '', '', '']
        return forged_record(n, 'Thora-TestRealm')
    queried, fetched = serve(victim, 'Thora-TestRealm', record, 45, 400, pages=52)
    assert (queried, fetched) == (52, 301)
    [entry] = [e for e in entries_from(victim, 'Thora-TestRealm').values() if e['id'] == claim[0]]
    assert (entry['text'], entry['via']) == ('Total deaths: 3', 'Thora-TestRealm')


def test_a_member_who_reconnects_soon_after_a_failed_pull_is_pulled_when_the_interval_ends():
    victim = actor('Mira')
    victim.execute('__peers={"Eldrin-TestRealm"}')
    group, client = group_of(victim), victim.eval('WoWStatusAdapter.client_id')
    clock(victim, 100)
    victim.eval('WoWStatusJournal.tick')()
    receive = victim.eval('WoWStatusJournal.receive')
    clock(victim, 1000)
    assert receive(f'J2 {group} H {BASE + 1000}-1 {client}', 'Eldrin-TestRealm', 'WHISPER')
    clock(victim, 1001)
    victim.eval('WoWStatusJournal.tick')()
    # Eldrin goes offline mid-pull and leaves the channel roster.
    victim.execute('__peers={}')
    for now in range(1002, 1300):
        clock(victim, now)
        victim.eval('WoWStatusJournal.tick')()
    assert len(queries_to(victim, 'Eldrin-TestRealm')) == 1
    # He logs in again 5 minutes later: his hello waits for the interval to end.
    victim.execute('__peers={"Eldrin-TestRealm"}')
    clock(victim, 1300)
    assert not receive(f'J2 {group} H {BASE + 1290}-1 {client}', 'Eldrin-TestRealm', 'WHISPER')
    for now in range(1301, 1610):
        clock(victim, now)
        victim.eval('WoWStatusJournal.tick')()
    assert len(queries_to(victim, 'Eldrin-TestRealm')) == 2


def test_a_waiting_hello_waits_for_the_running_pull_and_restarts_from_the_newest():
    """Review round 3: neither lost while a long pull runs, nor resumed at its end."""
    victim = actor('Mira')
    victim.execute('__peers={"Mallory-TestRealm"}')
    group, client = group_of(victim), victim.eval('WoWStatusAdapter.client_id')
    clock(victim, 100)
    victim.eval('WoWStatusJournal.tick')()
    receive = victim.eval('WoWStatusJournal.receive')
    clock(victim, 1000)
    assert receive(f'J2 {group} H {BASE + 1000}-1 {client}', 'Mallory-TestRealm', 'WHISPER')
    reload = {1300: lambda: receive(f'J2 {group} H {BASE + 1300}-2 {client}', 'Mallory-TestRealm', 'WHISPER')}
    # Mallory always has more: the pull runs to the page limit, past the interval.
    serve(victim, 'Mallory-TestRealm', forged_record, 1001, 2100, during=reload)
    offsets = [int(text.split(' ')[4]) for text in queries_to(victim, 'Mallory-TestRealm')]
    first = offsets.index(2004) + 1  # the page limit: 335 pages of 6
    assert offsets[:first] == list(range(0, 2005, 6))
    # The waiting hello's pull starts after it, from the newest entries again.
    assert offsets[first] == 0


def test_the_hello_rate_ignores_pc_clock_changes():
    """Review round 3: the rate runs on game uptime, not the PC clock."""
    victim = actor('Mira')
    victim.execute('__peers={"Mallory-TestRealm"}')
    group, client = group_of(victim), victim.eval('WoWStatusAdapter.client_id')
    clock(victim, 100)
    victim.eval('WoWStatusJournal.tick')()
    receive = victim.eval('WoWStatusJournal.receive')
    clock(victim, 1000)
    assert receive(f'J2 {group} H {BASE + 1000}-1 {client}', 'Mallory-TestRealm', 'WHISPER')
    for now in range(1001, 1010):
        clock(victim, now)
        victim.eval('WoWStatusJournal.tick')()
    [query] = queries_to(victim, 'Mallory-TestRealm')
    receive(f'J2 {group} I {query.split(" ")[3]} 0 0 -', 'Mallory-TestRealm', 'WHISPER')
    # Eleven minutes of play later, the PC clock is set back an hour.
    clock(victim, 1660)
    victim.execute('__now=__now-3600')
    assert receive(f'J2 {group} H {BASE - 1940}-2 {client}', 'Mallory-TestRealm', 'WHISPER')


def test_the_records_page_is_recounted_only_when_its_entries_come_or_go():
    """Review round 3: a catch-up of other entries skips the whole-log recount."""
    victim = actor('Mira')
    group = group_of(victim)
    clock(victim, 10000)
    victim.execute(f"""
        local c,list=character(),WoWStatusDB.journal.entries
        list[#list+1]={{id=c.identity.client..":thora-testrealm:d-1",client=c.identity.client,
            sender="Thora-TestRealm",kind="death",text="Died",at={BASE}+50,groups={{["{group}"]=true}},origin="live"}}
        for i=1,1999 do
            list[#list+1]={{id=c.identity.client..":thora-testrealm:z-"..i,client=c.identity.client,
                sender="Thora-TestRealm",kind="zone",text="Entered Zone "..i,at={BASE}+100+i,
                groups={{["{group}"]=true}},origin="live"}}
        end
        WoWStatusJournal.init(WoWStatusDB,c)
        __recounts=0
        local update=WoWStatusFirsts.update
        function WoWStatusFirsts.update() __recounts=__recounts+1;return update() end
    """)
    received = victim.eval('WoWStatusJournal.received')

    def live(nonce, kind, text, at):
        return received(victim.table_from({'sender': 'Eldrin-TestRealm', 'nonce': nonce, 'kind': kind,
                                           'text': text, 'at': BASE + at, 'group_id': group}))
    # The received side is full: a new zone evicts the oldest entry, a possible
    # medal holder (Thora's death), so the medals are recounted.
    assert live('z-a', 'zone', 'Entered Elwynn Forest', 9000)
    assert victim.eval('__recounts') == 1
    # The next zone only evicts a zone: nothing on the Records page changes.
    assert live('z-b', 'zone', 'Entered Westfall', 9001)
    assert victim.eval('__recounts') == 1
    assert live('d-b', 'death', 'Died', 9002)
    assert victim.eval('__recounts') == 2
    assert victim.eval('WoWStatusFirsts.compute(WoWStatusJournal.entries()).death.id').endswith(':d-b')


def test_a_member_in_two_shared_groups_uses_its_share_once_per_entry():
    """Review round 1: fetching an entry again for a second group is not charged."""
    victim = actor('Mira')
    victim.eval('WoWStatusGroups.update')('dawnwatch\nother-group', '')
    victim.execute('__peers={"Thora-TestRealm"}')
    record = lambda n: forged_record(n, 'Thora-TestRealm')  # noqa: E731
    queried, fetched = serve(victim, 'Thora-TestRealm', record, 11, 400, pages=40)
    assert claiming(victim, 'Thora-TestRealm') == 240
    first, second = groups_of(victim)
    both = victim.eval('''function(a,b)
        local n=0
        for _,e in ipairs(WoWStatusJournal.entries()) do if e.groups[a] and e.groups[b] then n=n+1 end end
        return n
    end''')(first, second)
    assert (both, fetched) == (240, 480)


def test_login_sync_still_recovers_entries_from_every_member():
    clients = {name: actor(name) for name in ('Thora', 'Eldrin', 'Mira')}
    for i, lua in enumerate(clients.values()):
        clock(lua, 10)
        lua.eval('fire')('PLAYER_LEVEL_UP', i + 2)
    mesh(clients, start=11, duration=100)
    for lua in clients.values():
        assert lua.eval('#WoWStatusJournal.entries()') == 3
