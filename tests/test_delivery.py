"""Every peer gets every update, even in large groups (issue #9).

Popups whisper each update to every group peer, one a second, until receivers
would reject it as stale; a throttled whisper is sent again rather than skipped;
log sync paces itself to the game's per-prefix allowance in instances and checks
every send result. The game's limits are mocked here from the documented values
(10 messages per prefix, regained at 1 a second, whispers exempt outside
instances); the live clients are checked in issue #25.
"""
import pytest
from test_journal import actor, clock, mesh
from test_relay_provenance import group_of

BASE = 1793000000

# SendAddonMessage with the game's documented per-prefix allowance. __results
# forces the next results (0 = go through as normal). A throttled message is
# not delivered: it never reaches __sent, so mesh() never passes it on.
LIMITS = '''
Enum={SendAddonMessageResult={Success=0,AddonMessageThrottle=3,GeneralError=9,TargetOffline=12}}
__instance=false;__allowance=10;__regen=1;__allowances={};__throttled=0;__attempts={};__results={}
__chat={};DEFAULT_CHAT_FRAME={AddMessage=function(_,text) table.insert(__chat,text) end}
function IsInInstance() return __instance,__instance and "party" or "none" end
local deliver=C_ChatInfo.SendAddonMessage
C_ChatInfo.SendAddonMessage=function(prefix,text,kind,target)
    table.insert(__attempts,{prefix=prefix,target=target,text=text,at=__mono})
    if __falseAt and __falseAt[__mono] then return false end
    local forced=table.remove(__results,1)
    if forced==nil and __throttleAll then forced=3 end
    if forced~=nil and forced~=0 then return forced end
    if __instance or kind~="WHISPER" then
        local a=__allowances[prefix] or {left=__allowance,at=__mono}
        a.left=math.min(__allowance,a.left+(__mono-a.at)*__regen);a.at=__mono
        __allowances[prefix]=a
        if a.left<1 then __throttled=__throttled+1;return 3 end
        a.left=a.left-1
    end
    deliver(prefix,text,kind,target)
    return 0
end
'''


def peers(lua, count):
    lua.execute('__peers={' + ','.join(f'"Peer{i:02d}-TestRealm"' for i in range(count)) + '}')


def popup_attempts(lua):
    return [(a['target'].split('-')[0], a['at']) for a in lua.eval('__attempts').values()
            if a['prefix'] == 'WoWStatus']


def level_up(lua, level, at=10):
    clock(lua, at)
    lua.execute(f'__level={level}')
    lua.eval('fire')('PLAYER_LEVEL_UP', level)


def run(lua, start, stop):
    for second in range(start, stop):
        clock(lua, second)
        lua.eval('WoWStatusPopups.tick')()


def test_simultaneous_updates_reach_every_peer():
    """The issue's reproduction, verbatim apart from the imports above."""
    lua = actor('Thora', 'alpha\nbeta\ngamma')
    lua.execute('__peers={' + ','.join(f'"Peer{i:02d}-TestRealm"' for i in range(20)) + '}')
    lua.execute('__channelNames={} for id in pairs(character().group_ids) do '
                'table.insert(__channelNames, WoWStatusGroups.channel(id)) end')
    clock(lua, 10)
    for level in (2, 3, 4):
        lua.execute(f'__level={level}')
        lua.eval('fire')('PLAYER_LEVEL_UP', level)
    for second in range(11, 400):
        clock(lua, second)
        lua.eval('WoWStatusPopups.tick')()
    delivered = {}
    for i in range(1, lua.eval('#__sent') + 1):
        packet = lua.eval(f'__sent[{i}]')
        if packet['prefix'] == 'WoWStatus':
            delivered.setdefault(packet['text'], set()).add(packet['target'])
    # Each update reaches all 20 peers once: a peer in all three groups is not
    # whispered once per group (receivers would drop the copies anyway).
    assert sorted(len(t) for t in delivered.values()) == [20] * 3   # fails: [1, 20, 20, 20, 20, 20, 20]


@pytest.mark.parametrize('instance', [False, True])
def test_one_whisper_a_second_never_meets_the_prefix_allowance(instance):
    """Within the documented allowance, nothing is throttled, inside an instance too."""
    lua = actor('Thora', 'alpha\nbeta\ngamma')
    lua.execute(LIMITS + f'__instance={str(instance).lower()}')
    peers(lua, 20)
    for level in (2, 3, 4):
        level_up(lua, level)
    run(lua, 11, 400)
    assert lua.eval('__throttled') == 0
    assert len(popup_attempts(lua)) == 60  # 3 updates x 20 peers, once each
    assert lua.eval('WoWStatusDB.popups.last_send.state') == 'attempted_no_receipt'


def test_late_whisper_of_a_long_queue_is_accepted_by_its_peer():
    """The 135th whisper leaves over two minutes after the event; the peer still takes it."""
    sender = actor('Thora', 'alpha\nbeta\ngamma')
    peers(sender, 45)
    for level in (2, 3, 4):
        level_up(sender, level)
    sent_at = {}
    for second in range(11, 400):
        clock(sender, second)
        sender.eval('WoWStatusPopups.tick')()
        for i in range(len(sent_at) + 1, sender.eval('#__sent') + 1):
            sent_at[i] = second
    last = sender.eval(f'__sent[{len(sent_at)}]')
    assert sent_at[len(sent_at)] - 10 > 120   # Older clients would drop it as stale.
    assert last['target'] == 'Peer44-TestRealm'
    receiver = actor('Peer44', 'alpha\nbeta\ngamma')
    receiver.execute('__peers={"Thora-TestRealm"}')
    clock(receiver, sent_at[len(sent_at)])
    receiver.eval('fire')('CHAT_MSG_ADDON', 'WoWStatus', last['text'], 'WHISPER', 'Thora-TestRealm')
    assert receiver.eval('WoWStatusDB.popups.last_receive.state') == 'displayed'
    assert receiver.eval('WoWStatusJournal.entries()[1].text') == 'Reached level 4!'


def test_receivers_accept_updates_for_ten_minutes_and_no_longer():
    lua = actor('Mira')
    channel = lua.eval('__channelNames[1]')
    receive = lua.eval('WoWStatusPopups.receive')
    clock(lua, 1000)
    assert receive(f'WSTATUS2 classic-era LEVEL 5 {BASE + 1000 - 601} n-old', 'Eldrin-TestRealm', channel) is False
    assert receive(f'WSTATUS2 classic-era LEVEL 5 {BASE + 1000 - 600} n-late', 'Eldrin-TestRealm', channel) is True
    text = 'WSTATUS4 classic-era mount {} {} First mount: Brown Horse'
    assert receive(text.format(BASE + 1000 - 601, 'm-old'), 'Eldrin-TestRealm', channel) is False
    assert receive(text.format(BASE + 1000 - 600, 'm-late'), 'Eldrin-TestRealm', channel) is True


def test_throttled_whisper_is_sent_again_to_the_same_peer():
    lua = actor('Thora')
    lua.execute(LIMITS + '__results={3,3}')
    peers(lua, 3)
    level_up(lua, 2)
    assert lua.eval('WoWStatusDB.popups.last_send.state') == 'throttled_retrying'
    assert lua.eval('WoWStatusDB.popups.last_send.target') == 'Peer00-TestRealm'
    run(lua, 11, 40)
    # Waits 2 s, then 4 s, after a throttle; then one a second again.
    assert popup_attempts(lua) == [('Peer00', 10), ('Peer00', 12), ('Peer00', 16), ('Peer01', 17), ('Peer02', 18)]
    assert [p['target'] for p in lua.eval('__sent').values()] == [
        'Peer00-TestRealm', 'Peer01-TestRealm', 'Peer02-TestRealm']
    assert lua.eval('WoWStatusDB.popups.last_send.state') == 'attempted_no_receipt'


def test_failed_whisper_moves_on_and_an_older_clients_false_is_tried_twice():
    failed = actor('Thora')
    failed.execute(LIMITS + '__results={9}')
    peers(failed, 3)
    level_up(failed, 2)
    assert failed.eval('WoWStatusDB.popups.last_send.state') == 'blocked_or_uncertain'
    run(failed, 11, 40)
    assert popup_attempts(failed) == [('Peer00', 10), ('Peer01', 11), ('Peer02', 12)]

    older = actor('Thora')
    older.execute(LIMITS + '__results={false,false}')
    peers(older, 3)
    level_up(older, 2)
    assert older.eval('WoWStatusDB.popups.last_send.state') == 'uncertain_retrying'
    run(older, 11, 40)
    assert popup_attempts(older) == [('Peer00', 10), ('Peer00', 12), ('Peer01', 13), ('Peer02', 14)]
    assert [p['target'] for p in older.eval('__sent').values()] == ['Peer01-TestRealm', 'Peer02-TestRealm']


def test_a_client_whose_false_is_never_a_throttle_stops_retrying():
    lua = actor('Thora')
    lua.execute(LIMITS + '__results={false,false,false,false}')
    peers(lua, 4)
    level_up(lua, 2)
    run(lua, 11, 40)
    # Peer00's retry says false again, so later falses are taken as final.
    assert popup_attempts(lua) == [('Peer00', 10), ('Peer00', 12), ('Peer01', 13), ('Peer02', 14), ('Peer03', 15)]


def test_a_false_after_throttles_is_still_retried_and_waits_only_two_seconds():
    lua = actor('Thora')
    lua.execute(LIMITS + '__results={3,3,false}')
    peers(lua, 2)
    level_up(lua, 2)
    run(lua, 11, 40)
    # Throttles wait 2 s and 4 s; the false waits 2 s, then the retry goes through.
    assert popup_attempts(lua) == [('Peer00', 10), ('Peer00', 12), ('Peer00', 16), ('Peer00', 18), ('Peer01', 19)]
    assert [p['target'] for p in lua.eval('__sent').values()] == ['Peer00-TestRealm', 'Peer01-TestRealm']


def test_offline_peer_is_skipped_quietly():
    lua = actor('Thora')
    lua.execute(LIMITS + '__results={12}')
    peers(lua, 3)
    level_up(lua, 2)
    assert lua.eval('WoWStatusDB.popups.last_send.state') == 'peer_offline'
    assert lua.eval('WoWStatusDB.popups.last_send.target') == 'Peer00-TestRealm'
    run(lua, 11, 40)
    assert popup_attempts(lua) == [('Peer00', 10), ('Peer01', 11), ('Peer02', 12)]
    assert lua.eval('#__chat') == 0


def test_a_peer_who_left_the_channel_is_not_whispered_but_a_quiet_one_is():
    lua = actor('Thora')
    lua.execute(LIMITS)
    peers(lua, 15)
    level_up(lua, 2)
    # Peer12 leaves the group's channel after the list was taken. The roster is
    # read again within 10 s, before the sender reaches Peer12.
    lua.execute('table.remove(__peers, 15) table.remove(__peers, 13)')   # Peer14 too, the last.
    run(lua, 11, 40)
    targets = [target for target, _ in popup_attempts(lua)]
    assert targets == [f'Peer{i:02d}' for i in range(15) if i not in (12, 14)]
    assert lua.eval('WoWStatusDB.popups.last_send.state') == 'remaining_peers_left'
    # Without a roster read to go by, nobody is skipped: a friend last heard in
    # the channel over five minutes ago still gets the update.
    quiet = actor('Thora')
    quiet.execute(LIMITS + 'GetNumDisplayChannels=nil;__throttleAll=true')
    for name in ('Loud-TestRealm', 'Quiet-TestRealm'):
        quiet.eval('WoWStatusPopups.notePeer')(group_of(quiet), name)
    level_up(quiet, 2)
    run(quiet, 11, 320)
    quiet.execute('__throttleAll=false')
    run(quiet, 320, 340)
    assert sorted(target for target, at in popup_attempts(quiet) if at >= 320) == ['Loud', 'Quiet']


def test_peers_who_arrive_while_an_update_is_sending_get_it_too():
    """Also covers a list taken while the roster was still loading."""
    lua = actor('Thora')
    lua.execute(LIMITS)
    peers(lua, 15)
    level_up(lua, 2)
    lua.execute('table.insert(__peers,"Late01-TestRealm") table.insert(__peers,"Late02-TestRealm")')
    run(lua, 11, 40)
    assert [target for target, _ in popup_attempts(lua)] == [f'Peer{i:02d}' for i in range(15)] + ['Late01', 'Late02']


def test_a_final_false_is_retried_again_after_a_minute():
    lua = actor('Thora')
    lua.execute(LIMITS + '__falseAt={[10]=true,[12]=true,[13]=true,[75]=true}')
    peers(lua, 3)
    level_up(lua, 2)
    run(lua, 11, 40)
    # Peer00's retry says false again, so Peer01's false is not retried.
    assert popup_attempts(lua) == [('Peer00', 10), ('Peer00', 12), ('Peer01', 13), ('Peer02', 14)]
    level_up(lua, 3, at=75)
    run(lua, 76, 90)
    assert popup_attempts(lua)[4:] == [('Peer00', 75), ('Peer00', 77), ('Peer01', 78), ('Peer02', 79)]


def test_blocked_whispers_say_so_once_per_update():
    lua = actor('Thora')
    lua.execute(LIMITS + '__results={9,9,9}')
    peers(lua, 3)
    level_up(lua, 2)
    run(lua, 11, 40)
    assert len(popup_attempts(lua)) == 3
    assert sum('update blocked/uncertain' in line for line in lua.eval('__chat').values()) == 1


def test_a_full_send_queue_is_reported():
    lua = actor('Thora', 'alpha\nbeta\ngamma')
    lua.execute(LIMITS)
    peers(lua, 20)
    for level in range(2, 12):
        level_up(lua, level)   # 10 updates to 3 groups: 30 queued.
    assert lua.eval('WoWStatusDB.popups.last_send.state') == 'queued'
    level_up(lua, 12)   # Room for two of its three groups.
    assert lua.eval('WoWStatusDB.popups.last_send.state') == 'send_queue_full'
    level_up(lua, 13)
    assert lua.eval('WoWStatusDB.popups.last_send.state') == 'send_queue_full'


def test_a_replay_is_a_duplicate_for_as_long_as_it_is_accepted():
    """A stamp up to 300 s ahead is accepted until 600 s after it: 900 s from now."""
    lua = actor('Mira')
    channel = lua.eval('__channelNames[1]')
    receive = lua.eval('WoWStatusPopups.receive')
    clock(lua, 1000)
    ahead = f'WSTATUS4 classic-era mount {BASE + 1300} m-ahead First mount: Brown Horse'
    assert receive(ahead, 'Eldrin-TestRealm', channel) is True
    clock(lua, 1000 + 601)   # Another update prunes what is no longer needed.
    assert receive(f'WSTATUS2 classic-era LEVEL 5 {BASE + 1601} n-1', 'Eldrin-TestRealm', channel) is True
    assert lua.eval('WoWStatusDB.popups.seen["eldrin-testrealm:m-ahead"]') == BASE + 1000
    clock(lua, 1000 + 901)
    assert receive(f'WSTATUS2 classic-era LEVEL 6 {BASE + 1901} n-2', 'Eldrin-TestRealm', channel) is True
    assert lua.eval('WoWStatusDB.popups.seen["eldrin-testrealm:m-ahead"]') is None


def test_sender_stops_when_receivers_would_reject_the_update():
    lua = actor('Thora')
    lua.execute(LIMITS + '__throttleAll=true')
    peers(lua, 3)
    level_up(lua, 2)
    run(lua, 11, 800)
    attempts = popup_attempts(lua)
    assert all(target == 'Peer00' for target, _ in attempts)
    # The pause grows to 16 s and stays there, until the update is ten minutes old.
    assert [at for _, at in attempts[:6]] == [10, 12, 16, 24, 40, 56]
    assert max(at for _, at in attempts) <= 10 + 600
    assert max(at for _, at in attempts) > 10 + 600 - 16
    assert lua.eval('WoWStatusDB.popups.last_send.state') == 'cancelled_or_expired'
    assert lua.eval('#__sent') == 0


@pytest.mark.parametrize('values, expected', [
    ((False, 'error'), 'failed'),
    ((True,), 'sent'),
    ((True, True), 'sent'),
    ((True, False), 'uncertain'),
    ((True, 0), 'sent'),
    ((True, 3), 'throttled'),
    ((True, 8), 'throttled'),
    ((True, 11), 'throttled'),
    ((True, 9), 'failed'),
    ((True, 12), 'offline'),
    # The deprecated global wrapper returns a boolean first and the code second.
    ((True, False, None), 'uncertain'),
    ((True, True, 0), 'sent'),
    ((True, False, 3), 'throttled'),
    ((True, False, 9), 'failed'),
])
def test_send_results_are_read_from_the_last_return_value(values, expected):
    lua = actor('Thora')
    assert lua.eval('WoWStatusPopups.sendResult')(*values) == expected
    lua.execute('Enum={SendAddonMessageResult={Success=0,AddonMessageThrottle=3}}')
    assert lua.eval('WoWStatusPopups.sendResult')(*values) == expected


def seeded(name, count):
    """A member whose log holds count received entries it can pass on."""
    lua = actor(name)
    client, group = lua.eval('WoWStatusAdapter.client_id'), group_of(lua)
    lua.execute(f'''
        for i=1,{count} do
            table.insert(WoWStatusDB.journal.entries,{{id="{client}:someone-testrealm:n-"..i,client="{client}",
                sender="Someone-TestRealm",kind="death",text="Died",at={BASE}+i,groups={{["{group}"]=true}},origin="live"}})
        end
        WoWStatusJournal.groupsChanged()
    ''')
    assert lua.eval('#WoWStatusJournal.entries()') == count
    return lua


def log_sync(limits, duration):
    server, newcomer = seeded('Eldrin', 40), actor('Mira')
    for lua in (server, newcomer):
        lua.execute(LIMITS + limits)
    mesh({'Eldrin': server, 'Mira': newcomer}, start=11, duration=duration)
    return server, newcomer


def test_log_sync_in_an_instance_stays_within_the_prefix_allowance():
    server, newcomer = log_sync('__instance=true', 150)
    assert newcomer.eval('#WoWStatusJournal.entries()') == 40
    assert server.eval('__throttled') == 0
    assert newcomer.eval('__throttled') == 0


def test_throttled_log_packets_are_sent_again_not_lost():
    """The server may lower the allowance; a throttled packet waits and goes again."""
    server, newcomer = log_sync('__instance=true;__allowance=3;__regen=0.5', 300)
    assert server.eval('__throttled') > 0
    assert newcomer.eval('#WoWStatusJournal.entries()') == 40


def test_a_query_that_timed_out_while_queued_is_not_sent():
    """Its request is retried with a new query; the stale one would waste the allowance."""
    server, newcomer = seeded('Eldrin', 5), actor('Mira')
    for lua in (server, newcomer):
        lua.execute(LIMITS)
    newcomer.execute('__throttleAll=true')
    clients = {'Eldrin': server, 'Mira': newcomer}
    mesh(clients, start=11, duration=320)   # The first query waits more than 300 s.
    newcomer.execute('__throttleAll=false')
    mesh(clients, start=331, duration=60)
    assert newcomer.eval('#WoWStatusJournal.entries()') == 5
    queries = [a['text'].split(' ')[3] for a in newcomer.eval('__attempts').values()
               if a['prefix'] == 'WoWStatusLog' and a['text'].split(' ')[2] == 'Q']
    assert len(set(queries)) == 1   # Only the retry's token was ever tried.
