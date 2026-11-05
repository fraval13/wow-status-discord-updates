"""One relay must not be able to flood the activity log (issue #4).

Own entries and received entries are capped separately, one member can deliver
only a bounded share of catch-up entries per session, and sync hellos are
honored only within their login window and at a bounded rate.
"""
import re

from test_journal import actor, clock, mesh
from test_relay_provenance import digest, group_of, pack

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


def serve(victim, sender, record_for, start, stop, pages=None):
    """Answer the victim's catch-up queries to sender, in any group, from one list.

    record_for(n) gives the relay's n-th newest record (1-based), six a page; the
    list has `pages` pages (unbounded if None). Returns the number of pages queried
    and the number of entries the victim fetched with G.
    """
    client = victim.eval('WoWStatusAdapter.client_id')

    def send(group, text):
        victim.eval('fire')('CHAT_MSG_ADDON', 'WoWStatusLog', f'J2 {group} {text}', 'WHISPER', sender)

    def record(n):
        return [part.replace('{client}', client) for part in record_for(n)]
    seen, queried, fetched, now = victim.eval('#__sent'), 0, 0, start
    records = {}
    while now < stop:
        clock(victim, now)
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
                    encoded = pack(records[d]).encode().hex()
                    chunks = [encoded[j:j + 140] for j in range(0, len(encoded), 140)]
                    for part, chunk in enumerate(chunks, 1):
                        send(group, f'D {token} {d} {part}/{len(chunks)} {chunk}')
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
    queried, fetched = serve(victim, 'Mallory-TestRealm', forged_record, 11, 400)
    assert fetched == 300
    assert received_from(victim, 'Mallory-TestRealm') == 300
    # Paging stopped with the share, long before the 334-page limit.
    assert queried == 50
    # A later hello from the same member, after the rate interval, starts a pull
    # that fetches nothing more this session.
    group, client = group_of(victim), victim.eval('WoWStatusAdapter.client_id')
    clock(victim, 700)
    assert victim.eval('WoWStatusJournal.receive')(f'J2 {group} H {BASE + 690}-1 {client}',
                                                    'Mallory-TestRealm', 'WHISPER')
    queried, fetched = serve(victim, 'Mallory-TestRealm', lambda n: forged_record(n + 1000), 701, 760)
    assert (queried, fetched) == (1, 0)
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


def test_hello_over_the_rate_is_ignored():
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

    def pump(start):
        """Tick, then answer every query with an empty page so each pull ends."""
        for step in range(10):
            clock(victim, start + step)
            victim.eval('WoWStatusJournal.tick')()
        for target in ('Mallory-TestRealm', 'Eldrin-TestRealm'):
            for text in queries_to(victim, target):
                receive(f'J2 {group} I {text.split(" ")[3]} 0 0 -', target, 'WHISPER')

    assert hello(1000)
    pump(1001)
    assert len(queries_to(victim, 'Mallory-TestRealm')) == 1
    # The same nonce again is a duplicate, quietly accepted without a new pull.
    assert receive(f'J2 {group} H {BASE + 1000}-1 {client}', 'Mallory-TestRealm', 'WHISPER')
    # A new login nonce within ten minutes is over the rate.
    assert not hello(1300, serial=2)
    assert not hello(1599, serial=3)
    pump(1600)
    assert len(queries_to(victim, 'Mallory-TestRealm')) == 1
    # Another member's hello has its own rate.
    assert hello(1610, 'Eldrin-TestRealm')
    # Ten minutes after the last honored hello, the member's next one counts again.
    assert hello(1620, serial=4)
    pump(1621)
    assert len(queries_to(victim, 'Mallory-TestRealm')) == 2


def test_a_failed_pull_does_not_use_up_the_hello_rate():
    victim = actor('Mira')
    victim.execute('__peers={"Eldrin-TestRealm"}')
    group, client = group_of(victim), victim.eval('WoWStatusAdapter.client_id')
    clock(victim, 100)
    victim.eval('WoWStatusJournal.tick')()
    receive = victim.eval('WoWStatusJournal.receive')
    clock(victim, 1000)
    assert receive(f'J2 {group} H {BASE + 1000}-1 {client}', 'Eldrin-TestRealm', 'WHISPER')
    # Eldrin disconnects: the pull and its one retry time out unanswered.
    for now in range(1001, 1300):
        clock(victim, now)
        victim.eval('WoWStatusJournal.tick')()
    assert len(queries_to(victim, 'Eldrin-TestRealm')) == 2
    # He logs in again within ten minutes of his first hello; that one counts.
    clock(victim, 1300)
    assert receive(f'J2 {group} H {BASE + 1290}-1 {client}', 'Eldrin-TestRealm', 'WHISPER')
    for now in range(1301, 1310):
        clock(victim, now)
        victim.eval('WoWStatusJournal.tick')()
    assert len(queries_to(victim, 'Eldrin-TestRealm')) == 3


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
