"""Updates survive PC clocks that differ from each other (issue #7).

Clients stamp events with realm time (GetServerTime), the same clock on every
member's PC, and check peers' stamps against it. Older clients stamp their PC
clock, so a stamp that fits this PC's clock still counts. Mocked API only: the
real GetServerTime is checked in live clients (#25).
"""
import pytest
from test_addon import STUBS, make_lua
from test_journal import actor, clock, deliver_popup, mesh
from test_runtime_version import status_lines

REALM = 1793000000


def pc(name, skew=0, realm=True, peers=None):
    """A client whose PC clock is `skew` seconds off realm time, from its first
    load. realm=False leaves out GetServerTime: the client then stamps its PC
    clock, as clients from before issue #7 do. clock() moves realm time."""
    stubs = STUBS.replace('return "Thora" end', f'return "{name}" end').replace(
        'return "Player-123-0001" end', f'return "Player-123-{name}" end')
    stubs += f'''
        __now={REALM};__mono=0;__skew={skew}
        function time() return math.floor(__now+__skew) end
        function GetTime() return __mono end
    '''
    if realm:
        stubs += 'function GetServerTime() return math.floor(__now) end\n'
    lua = make_lua(stubs)
    lua.eval('WoWStatusGroups.update')('dawnwatch', '')
    lua.execute('for id in pairs(character().group_ids) do __channelNames={WoWStatusGroups.channel(id)} end')
    if peers is not None:
        lua.execute('__peers={' + ','.join(f'"{p}-TestRealm"' for p in peers) + '}')
    return lua


def said(lines, text):
    return any(text in line for line in lines)


def last_receive(lua):
    return lua.eval('WoWStatusDB.popups.last_receive.state')


def level_up(sender, receiver, at=10):
    clock(sender, at)
    clock(receiver, at)
    sender.eval('fire')('PLAYER_LEVEL_UP', 2)
    deliver_popup(sender, receiver)


def test_live_update_survives_three_minute_clock_difference():
    """The issue's repro, with the realm clock both PCs share."""
    sender, receiver = actor('Thora'), actor('Mira')
    for lua in (sender, receiver):
        lua.execute(f'function GetServerTime() return {REALM + 10} end')
    clock(sender, 10)
    clock(receiver, 10 + 180)
    sender.eval('fire')('PLAYER_LEVEL_UP', 2)
    deliver_popup(sender, receiver)
    assert receiver.eval('#WoWStatusJournal.entries()') == 1


@pytest.mark.parametrize('sender_skew,receiver_skew', [
    (0, 180), (0, -180), (180, 0), (-180, 0), (-400, 400), (3600, -3600)])
def test_live_updates_use_realm_time_whatever_the_pc_clocks_say(sender_skew, receiver_skew):
    sender, receiver = pc('Thora', sender_skew), pc('Mira', receiver_skew)
    level_up(sender, receiver)
    assert sender.eval('character().events[#character().events].at') == REALM + 10
    assert receiver.eval('#WoWStatusJournal.entries()') == 1
    assert receiver.eval('WoWStatusJournal.entries()[1].at') == REALM + 10
    assert last_receive(receiver) in ('queued', 'displayed')


def test_a_fast_pc_clock_does_not_expire_its_own_queued_update():
    """The send queue's 120 s limit is measured in realm time, like the stamp."""
    sender = pc('Thora', skew=180, peers=[])
    clock(sender, 10)
    sender.eval('fire')('PLAYER_LEVEL_UP', 2)
    assert sender.eval('WoWStatusDB.popups.last_send.state') == 'waiting_for_group_peers'
    sender.execute('__peers={"Mira-TestRealm"}')
    clock(sender, 10 + 119)
    sender.eval('WoWStatusPopups.tick')()
    assert sender.eval('WoWStatusDB.popups.last_send.state') == 'attempted_no_receipt'
    assert ' LEVEL 2 ' in sender.eval('__sent[#__sent].text')


def test_a_queued_update_still_expires_after_120_realm_seconds():
    sender = pc('Thora', skew=-180, peers=[])
    clock(sender, 10)
    sender.eval('fire')('PLAYER_LEVEL_UP', 2)
    sender.execute('__peers={"Mira-TestRealm"}')
    clock(sender, 10 + 121)
    sender.eval('WoWStatusPopups.tick')()
    assert sender.eval('WoWStatusDB.popups.last_send.state') == 'cancelled_or_expired'
    assert sender.eval('#__sent') == 0


@pytest.mark.parametrize('old_skew,receiver_skew', [
    (0, 0),        # Both PC clocks right: the stamp fits realm time.
    (0, 180),      # Only the receiver's PC is off: realm time still fits.
    (-600, -600),  # Both PCs equally wrong: only this PC's clock fits, as before.
    (600, 600),
])
def test_old_peer_packets_are_still_accepted(old_skew, receiver_skew):
    old, receiver = pc('Thora', old_skew, realm=False), pc('Mira', receiver_skew)
    level_up(old, receiver)
    assert old.eval('character().events[1].at') == REALM + 10 + old_skew
    assert receiver.eval('#WoWStatusJournal.entries()') == 1
    assert last_receive(receiver) in ('queued', 'displayed')


@pytest.mark.parametrize('kind', ['level', 'death'])
def test_status_explains_an_update_dropped_for_its_timestamp(kind):
    old, receiver = pc('Thora', -180, realm=False), pc('Mira')
    clock(old, 10)
    clock(receiver, 10)
    if kind == 'level':
        old.eval('fire')('PLAYER_LEVEL_UP', 2)
    else:
        old.eval('fire')('PLAYER_DEAD')
    deliver_popup(old, receiver)
    assert receiver.eval('#WoWStatusJournal.entries()') == 0
    assert last_receive(receiver) == 'rejected_stale'
    lines = status_lines(receiver)
    assert said(lines, f'Last received: {kind} from Thora-TestRealm — rejected_stale '
                '(stamped 180 s behind realm time)')
    assert said(lines, 'Clock: this PC matches realm time.')


def test_status_explains_a_future_timestamp_and_this_pcs_clock():
    old, receiver = pc('Thora', 400, realm=False), pc('Mira', -95)
    level_up(old, receiver)
    assert last_receive(receiver) == 'rejected_future'
    lines = status_lines(receiver)
    assert said(lines, 'rejected_future (stamped 400 s ahead of realm time)')
    assert said(lines, 'Clock: this PC is 95 s behind realm time.')


def test_status_says_when_realm_time_is_missing():
    lines = status_lines(pc('Mira', realm=False))
    assert said(lines, "Clock: realm time unavailable; using this PC's clock.")
    assert said(lines, 'Last received: none;')


@pytest.mark.parametrize('author_skew,late_skew', [(600, 0), (0, 600), (0, -600)])
def test_login_catch_up_survives_clock_skew(author_skew, late_skew):
    """Catch-up stamps (and the joiner's cutoff) are realm time as well."""
    author, late = pc('Thora', author_skew), pc('Mira', late_skew)
    clock(author, 10)
    author.eval('fire')('PLAYER_LEVEL_UP', 2)
    event_id = author.eval('WoWStatusJournal.entries()[1].id')
    late.eval('WoWStatusJournal.sync')()
    mesh({'Thora': author, 'Mira': late}, duration=40)
    assert late.eval('WoWStatusJournal.contains')(event_id)
    assert late.eval('WoWStatusJournal.entries()[1].at') == REALM + 10


def test_a_joiners_cutoff_is_never_ahead_of_realm_time():
    """A membership saved before this change can carry a PC-clock join time."""
    late = pc('Mira', 600)
    late.execute(f'for id in pairs(WoWStatusDB.account_group_joined_at) do '
                 f'WoWStatusDB.account_group_joined_at[id]={REALM + 600} end; __peers={{"Thora-TestRealm"}}')
    late.eval('WoWStatusJournal.sync')()
    for step in range(11, 20):
        clock(late, step)
        late.eval('WoWStatusJournal.tick')()
    query = next(p['text'] for p in late.eval('__sent').values() if ' Q ' in p['text'])
    cutoff = int(query.split(' ')[5])
    assert cutoff <= REALM + 19


def test_invalid_data_reports_from_a_fast_pc_are_accepted():
    """A W report's stamp has a 30 s future limit; realm time keeps it."""
    reporter = pc('Thora', 60, peers=['Thora', 'Eldrin', 'Mira'])
    friend = pc('Mira', 0, peers=['Thora', 'Eldrin', 'Mira'])
    group = reporter.eval('next(character().group_ids)')[0]
    client = reporter.eval('WoWStatusAdapter.client_id')
    attack = f'WSTATUS4 {client} death {REALM} forged Arbitrary injected text'
    assert not reporter.eval('WoWStatusPopups.receive')(attack, 'Eldrin-TestRealm', 'WStatus' + group)
    for step in range(1, 21):
        clock(reporter, step)
        reporter.eval('WoWStatusJournal.tick')()
    report = next(p['text'] for p in reporter.eval('__sent').values()
                  if p['prefix'] == 'WoWStatusLog' and ' W ' in p['text'] and p['target'] == 'Mira-TestRealm')
    clock(friend, 20)
    friend.eval('fire')('CHAT_MSG_ADDON', 'WoWStatusLog', report, 'WHISPER', 'Thora-TestRealm')
    assert 'Eldrin is a really bad boy' in friend.eval('WoWStatusLevelPopup.message:GetText()')


@pytest.mark.parametrize('skew', [-180, 180])
def test_level_history_stays_one_segment_whatever_the_pc_clock(skew):
    """Level-ups and the level checks between them are both stamped in realm time."""
    lua = pc('Thora', skew)
    clock(lua, 10)
    lua.execute('__level=2; fire("PLAYER_LEVEL_UP",2)')
    clock(lua, 20)
    lua.eval('fire')('PLAYER_ENTERING_WORLD')
    points = lua.eval('character().history.tracking.points')
    assert points[len(points)]['kind'] == 'level'
    assert points[len(points)]['at'] == REALM + 10
    assert lua.eval('character().history.tracking.observed_until') == REALM + 20
