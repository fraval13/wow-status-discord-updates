"""Login burst measurement (#188): addon messages after PLAYER_LOGIN, in-memory only.

Every client runs the whole addon over one in-memory network and one clock, with
each shown frame's OnUpdate driven as the game drives it. Nothing here says how a
live client behaves: run `python tests/test_login_burst.py` for the figures that
docs/LOGIN_BURST.md quotes, and see that page for the live-client check.
"""
import collections
import sys

from test_addon import STUBS, make_lua
from test_equipment import GEAR
from test_roster import EXTRA

BASE = 1793000000
# Every shown frame's OnUpdate runs, as the game runs them each frame; hidden
# frames (a dismissed toast) do not, as in the game.
DRIVER = r'''
    __now=__now or 1793000000; __mono=__mono or 0
    function time() return math.floor(__now) end
    function GetTime() return __mono end
    function __advance(dt)
        __now=__now+dt; __mono=__mono+dt
        for _, f in ipairs(__frames) do
            if f.OnUpdate and f:IsVisible() then f.OnUpdate(f, dt) end
        end
    end
'''


def stubs_for(name, at, mono):
    # Newer Lua seeds math.random afresh in each runtime; a fixed seed per client
    # and login keeps the figures the same on every run.
    seed = sum(name.encode()) * 7919 + int(mono)
    return (f'math.randomseed({seed})\n' + STUBS.replace('return "Thora" end', f'return "{name}" end')
            .replace('return "Player-123-0001" end', f'return "Player-123-{name}" end')
            + EXTRA + GEAR + f'\n__now={BASE + at}; __mono={mono}\n' + DRIVER)


def saved_variables(lua):
    return lua.eval('''function()
        local function literal(value)
            if type(value)=="table" then
                local entries={}
                for key,item in pairs(value) do entries[#entries+1]="["..literal(key).."]="..literal(item) end
                return "{"..table.concat(entries,",").."}"
            elseif type(value)=="string" then return string.format("%q",value)
            else return tostring(value) end
        end
        return "WoWStatusDB="..literal(WoWStatusDB)
    end''')()


class Network:
    """Clients whispering over an in-memory network, with one clock."""

    def __init__(self, names):
        self.now = 0.0
        self.clients = {}
        self.offsets = {}
        self.log = []  # (time, sender, target, prefix, text)
        for name in names:
            self.join(name, self.fresh(name))

    def fresh(self, name):
        lua = make_lua(stubs_for(name, self.now, 1000 + self.now))
        lua.eval('WoWStatusGroups.update')('dawnwatch', '')
        # make_lua held back the join announcement; a later login must not send it.
        lua.execute('character().introduced_groups = {}; '
                    'for id in pairs(character().group_ids) do character().introduced_groups[id] = true end')
        pid = (name.encode().hex() * 8)[:16]
        lua.execute(f'WoWStatusDB.player_name = "{name}sPlayer"; WoWStatusDB.roster.id = "{pid}"; '
                    'WoWStatusRoster.observe(character()); WoWStatusEquipment.capture(character())')
        return lua

    def join(self, name, lua):
        self.clients[name] = lua
        self.offsets[name] = 0  # what PLAYER_LOGIN itself sent counts too
        self.roster()

    def leave(self, name):
        lua = self.clients.pop(name)
        lua.eval('fire')('PLAYER_LOGOUT')
        self.roster()
        return saved_variables(lua)

    def relog(self, name, saved, uptime=5000):
        lua = make_lua(stubs_for(name, self.now, uptime) + saved
                       + '\nfunction character() for _,c in pairs(WoWStatusDB.characters) do '
                       'if c.identity.guid==UnitGUID("player") then return c end end end\n')
        lua.eval('fire')('PLAYER_ENTERING_WORLD', True, False)
        self.join(name, lua)
        return lua

    def roster(self):
        peers = '{' + ','.join(f'"{n}-TestRealm"' for n in self.clients) + '}'
        for lua in self.clients.values():
            lua.execute('__peers=' + peers + '; fire("CHANNEL_ROSTER_UPDATE")')

    def advance(self, seconds, step=.25):
        for _ in range(round(seconds / step)):
            self.now += step
            for lua in self.clients.values():
                lua.eval('__advance')(step)
            self.deliver()

    def deliver(self):
        packets = []
        for name, lua in self.clients.items():
            total = lua.eval('#__sent')
            for i in range(self.offsets[name] + 1, total + 1):
                p = lua.eval(f'__sent[{i}]')
                target = (p['target'] or '').split('-')[0]
                packets.append((self.now, name, target, p['prefix'], p['text']))
            self.offsets[name] = total
        self.log.extend(packets)
        for _, sender, target, prefix, text in packets:
            if prefix and target in self.clients:
                self.clients[target].eval('fire')('CHAT_MSG_ADDON', prefix, text, 'WHISPER', sender + '-TestRealm')


FRIENDS = ('Eldrin', 'Mira', 'Kael', 'Brann', 'Lys', 'Odo', 'Vex')
ME = 'Thora'
PREFIXES = ('WoWStatus', 'WoWStatusLog', 'WoWStatusChr')


def ids(lua, own=False):
    """A client's log IDs; with own, only the entries it wrote itself."""
    entries = lua.eval('function(own) local t={} for _,e in ipairs(WoWStatusJournal.entries()) do '
                       'if not own or e.owner then t[#t+1]=e.id end end return t end')(own)
    return set(entries.values())


def gear(lua, name):
    snapshot = lua.eval(f'(WoWStatusRoster.equipment("{name}-TestRealm"))')
    return (snapshot and snapshot['items'][1]) or ''


def relog_after_absence(friends, missed):
    """Thora logs out; the friends log `missed` level-ups and Mira changes gear; Thora logs in again.

    Returns the network, Thora's new client, the time of her PLAYER_LOGIN, the
    index of the first message after it, and the log IDs she missed: every entry
    a friend wrote that she lacks, whether or not it reached the other friends.
    """
    assert 'Mira' in friends
    net = Network((ME,) + friends)
    net.advance(240)  # every list, log and gear snapshot exchanged
    saved = net.leave(ME)
    for i in range(missed):
        lua = net.clients[friends[i % len(friends)]]
        level = lua.eval('__level') + 1
        lua.execute(f'__level={level}')
        lua.eval('fire')('PLAYER_LEVEL_UP', level)
        net.advance(2)
    net.clients['Mira'].execute('__gear[1]="item:42:0:0:0:0:0:0:0"; fire("PLAYER_EQUIPMENT_CHANGED", 1)')
    net.advance(180)  # live updates and their retries have finished
    want = set().union(*(ids(net.clients[name], own=True) for name in friends))
    login, mark = net.now, len(net.log)
    me = net.relog(ME, saved)
    return net, me, login, mark, want - ids(me)


def sent(log, since, seconds, sender=None, target=None):
    return [p for p in log if since <= p[0] <= since + seconds
            and (sender is None or p[1] == sender) and (target is None or p[2] == target)]


def busiest_second(log, sender):
    """The most messages one client sent on one prefix within any one second."""
    busiest = 0
    for prefix in PREFIXES:
        times = sorted(p[0] for p in log if p[1] == sender and p[3] == prefix)
        for i, start in enumerate(times):
            busiest = max(busiest, sum(1 for t in times[i:] if t < start + 1))
    return busiest


def test_a_login_sends_at_most_two_messages_a_second_per_prefix_and_loses_nothing():
    net, me, login, mark, missing = relog_after_absence(FRIENDS, 21)
    # 21 level-ups and Mira's first equip of the new (epic) item.
    assert len(missing) == 22 and gear(me, 'Mira') != 'item:42:0:0:0:0:0:0:0'
    caught_up = None
    for _ in range(int(240 / .25)):
        net.advance(.25)
        if caught_up is None and missing <= ids(me) and gear(me, 'Mira').startswith('item:42:'):
            caught_up = net.now - login
        if caught_up is not None and net.now - login >= 10:
            break
    after = net.log[mark:]
    first_ten = sent(after, login, 10, sender=ME)
    # Each module paces its own whispers half a second apart: at most two a
    # second per prefix, so with two prefixes in use at most 42 in the first
    # ten seconds (both ends counted).
    assert set(p[3] for p in first_ten) <= set(PREFIXES)
    assert len(first_ten) <= 42
    for prefix in PREFIXES:
        assert len([p for p in first_ten if p[3] == prefix]) <= 21
    assert busiest_second(after, ME) <= 2
    # Nothing is lost: every missed log entry and the changed gear arrive.
    assert caught_up is not None, 'catch-up did not finish within four minutes'
    assert me.eval('WoWStatusLevelPopup') is None  # caught-up entries stay quiet


def everyone_logs_in_together():
    """Eight friends log out, then all log in again at the same moment."""
    names = (ME,) + FRIENDS
    net = Network(names)
    for name in names:
        net.clients[name].eval('fire')('PLAYER_LEVEL_UP', 2)
    net.advance(240)
    saved = {name: net.leave(name) for name in names}
    net.advance(60)
    login, mark = net.now, len(net.log)
    for i, name in enumerate(names):
        net.relog(name, saved[name], uptime=5000 + i * 37)
    net.advance(30)
    return names, login, net.log[mark:]


def test_eight_friends_logging_in_together_each_keep_the_same_pace():
    names, login, after = everyone_logs_in_together()
    for name in names:
        assert busiest_second(after, name) <= 2
        assert len(sent(after, login, 10, sender=name)) <= 42


def test_the_debug_log_marks_the_login_and_each_log_send_without_the_group():
    """What a live-client measurement reads (docs/LOGIN_BURST.md)."""
    net = Network((ME, 'Mira'))
    net.advance(60)
    net.clients[ME].eval('SlashCmdList.WOWSTATUS')('debug on')
    saved = net.leave(ME)
    net.advance(30)
    me = net.relog(ME, saved)
    net.advance(15)
    log = me.eval('table.concat(WoWStatusDB.debug_log, "\\n")').split('\n')
    group = me.eval('(next(character().group_ids))')
    login = [i for i, line in enumerate(log) if line.endswith(' login')]
    assert len(login) == 1
    log = log[login[0]:]
    assert any(' log send H to Mira-TestRealm: sent' in line for line in log)
    assert any(line.split(' ', 1)[1].startswith('send ') for line in log)  # the character list's own lines
    assert not any(group in line for line in log)


def over_allowance(times):
    """Sends past the game's per-prefix allowance (10, regained at 1 a second).

    The game applies it to whispers inside instances only (docs/LIVE_POPUPS.md),
    so this is what a login inside a dungeon would meet.
    """
    allowance, at, over = 10.0, 0.0, 0
    for when in sorted(times):
        allowance, at = min(10.0, allowance + when - at), when
        if allowance >= 1:
            allowance -= 1
        else:
            over += 1
    return over


def figures():
    """Print the before figures docs/LOGIN_BURST.md quotes."""
    print('| Scenario | Sent by the login, 0-10 s | Received by it, 0-10 s | Whole group, 0-10 s '
          '| First missed entry | All missed entries | Changed gear | Character list past the allowance in an instance, 0-120 s |')
    print('|---|---|---|---|---|---|---|---|')
    for friends, missed in ((FRIENDS[:3], 21), (FRIENDS, 21), (FRIENDS, 105)):
        net, me, login, mark, missing = relog_after_absence(friends, missed)
        first = done = changed = None
        for _ in range(int(600 / .25)):
            net.advance(.25)
            have = ids(me)
            if first is None and missing & have:
                first = net.now - login
            if done is None and missing <= have:
                done = net.now - login
            if changed is None and gear(me, 'Mira').startswith('item:42:'):
                changed = net.now - login
            if done is not None and changed is not None and net.now - login >= 120:
                break
        after = net.log[mark:]
        # The character list only: the log already waits for the allowance in an instance.
        roster = [p[0] - login for p in sent(after, login, 120, sender=ME) if p[3] == 'WoWStatusChr']
        instance = f'{over_allowance(roster)} of {len(roster)}'

        def by_prefix(packets):
            counts = collections.Counter(p[3] for p in packets)
            parts = ', '.join(f"{prefix[9:] or 'live'} {count}" for prefix, count in sorted(counts.items()))
            return f'{len(packets)} ({parts})'
        print(f'| {len(friends)} friends online, {len(missing)} entries missed '
              f'| {by_prefix(sent(after, login, 10, sender=ME))} '
              f'| {by_prefix(sent(after, login, 10, target=ME))} '
              f'| {len(sent(after, login, 10))} '
              f'| {first} s | {done} s | {changed} s | {instance} |')


    names, login, after = everyone_logs_in_together()
    each = [len(sent(after, login, 10, sender=name)) for name in names]
    received = max(len(sent(after, login, 10, target=name)) for name in names)
    print(f'\nEight friends logging in together, 0-10 s: {len(sent(after, login, 10))} messages in all, '
          f'{min(each)} to {max(each)} sent by each, at most {received} received by one.')


if __name__ == '__main__':
    sys.exit(figures())
