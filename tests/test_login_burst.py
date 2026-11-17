"""Login burst measurement (#188): addon messages after PLAYER_LOGIN, in-memory only.

Every client runs the whole addon over one in-memory network and one clock, with
each shown frame's OnUpdate driven as the game drives it. Nothing here says how a
live client behaves: run `python tests/test_login_burst.py` for the figures that
docs/LOGIN_BURST.md quotes, and see that page for the live-client check.
"""
import collections
import sys

if __name__ == '__main__':
    # The figures run on the game's Lua 5.1: newer Lua seeds its string hashing
    # afresh in each runtime, which reorders peers and queues from run to run.
    import lupa
    from lupa import lua51
    lupa.LuaRuntime = lua51.LuaRuntime

from test_addon import STUBS, make_lua
from test_addon_claims import saved as saved_variables
from test_equipment import GEAR
from test_roster import EXTRA

BASE = 1793000000
# Every shown frame's OnUpdate runs, as the game runs them each frame; hidden
# frames (a dismissed toast) do not, as in the game. C_Timer tickers and
# timers run when they are due.
DRIVER = r'''
    __now=__now or 1793000000; __mono=__mono or 0
    function time() return math.floor(__now) end
    function GetTime() return __mono end
    __timers = {}
    C_Timer = {
        NewTicker=function(seconds, fn) table.insert(__timers, {every=seconds, at=__mono+seconds, fn=fn}) end,
        After=function(seconds, fn) table.insert(__timers, {at=__mono+seconds, fn=fn}) end,
    }
    function __advance(dt)
        __now=__now+dt; __mono=__mono+dt
        for _, f in ipairs(__frames) do
            if f.OnUpdate and f:IsVisible() then f.OnUpdate(f, dt) end
        end
        local due = {}
        for i = #__timers, 1, -1 do
            local timer = __timers[i]
            if __mono >= timer.at then
                table.insert(due, 1, timer)
                if timer.every then timer.at = timer.at + timer.every else table.remove(__timers, i) end
            end
        end
        for _, timer in ipairs(due) do timer.fn() end
    end
'''


def stubs_for(name, at, mono, extra=''):
    # Newer Lua seeds math.random afresh in each runtime; a fixed seed per client
    # and login keeps the figures the same on every run.
    seed = sum(name.encode()) * 7919 + int(mono)
    return (f'math.randomseed({seed})\n' + STUBS.replace('return "Thora" end', f'return "{name}" end')
            .replace('return "Player-123-0001" end', f'return "Player-123-{name}" end')
            + EXTRA + GEAR + f'\n__now={BASE + at}; __mono={mono}\n' + DRIVER + extra)


class Network:
    """Clients whispering over an in-memory network, with one clock."""

    def __init__(self, names, extra=''):
        self.now = 0.0
        self.clients = {}
        self.offsets = {}
        self.extra = extra  # client stubs added after the driver, e.g. INSTANCE
        self.log = []  # (time, sender, target, prefix, text)
        for name in names:
            self.join(name, self.fresh(name))

    def fresh(self, name):
        lua = make_lua(stubs_for(name, self.now, 1000 + self.now, self.extra))
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
        lua = make_lua(stubs_for(name, self.now, uptime, self.extra) + saved
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


# Inside an instance the game gives each addon-message prefix 10 messages,
# regained at one a second, and refuses the rest with a throttle result
# (docs/LIVE_POPUPS.md). This models that bucket: a refused send never reaches
# __sent, so the network never delivers it, and it is recorded in __refused.
INSTANCE = r'''
    Enum = Enum or {}
    Enum.SendAddonMessageResult = {Success=0, AddonMessageThrottle=3, ChannelThrottle=8,
        AddOnMessageLockdown=11, TargetOffline=12}
    function IsInInstance() return true, "party" end
    __refused, __buckets = {}, {}
    C_ChatInfo.SendAddonMessage = function(prefix, text, kind, target)
        local now, bucket = GetTime(), __buckets[prefix]
        if not bucket then bucket = {allowance=10, at=now}; __buckets[prefix] = bucket end
        bucket.allowance = math.min(10, bucket.allowance + (now - bucket.at)); bucket.at = now
        if bucket.allowance < 1 then
            table.insert(__refused, {prefix=prefix, text=text, target=target, at=now})
            return Enum.SendAddonMessageResult.AddonMessageThrottle
        end
        bucket.allowance = bucket.allowance - 1
        table.insert(__sent, {prefix=prefix, text=text, kind=kind, target=target})
        return Enum.SendAddonMessageResult.Success
    end
'''

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


def relog_after_absence(friends, missed, extra=''):
    """Thora logs out; the friends log `missed` level-ups and Mira changes gear; Thora logs in again.

    Returns the network, Thora's new client, the time of her PLAYER_LOGIN, the
    index of the first message after it, and the log IDs she missed: every entry
    a friend wrote that she lacks, whether or not it reached the other friends.
    """
    assert 'Mira' in friends
    net = Network((ME,) + friends, extra=extra)
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


def catch_up(net, me, login, missing, limit, at_least):
    """Run until Thora has every missed entry and Mira's new gear, and for at least `at_least` seconds.

    Returns the seconds after login until the first missed entry, all of them
    and the gear arrived (None for what did not arrive within `limit`).
    """
    first = done = changed = None
    while net.now - login < limit:
        net.advance(.25)
        have = ids(me)
        if first is None and missing & have:
            first = net.now - login
        if done is None and missing <= have:
            done = net.now - login
        if changed is None and gear(me, 'Mira').startswith('item:42:'):
            changed = net.now - login
        if done is not None and changed is not None and net.now - login >= at_least:
            break
    return first, done, changed


def test_a_login_sends_at_most_two_messages_a_second_per_prefix_and_loses_nothing():
    net, me, login, mark, missing = relog_after_absence(FRIENDS, 21)
    # 21 level-ups and Mira's first equip of the new (epic) item.
    assert len(missing) == 22 and not gear(me, 'Mira').startswith('item:42:')
    _, done, changed = catch_up(net, me, login, missing, limit=240, at_least=10)
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
    assert done is not None and changed is not None, 'catch-up did not finish within four minutes'
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
    # The character list's own lines, each ending in the game's answer (#286).
    chr_lines = [line for line in log if line.split(' ', 1)[1].startswith('send ')]
    assert chr_lines and all(line.endswith(': sent') for line in chr_lines)
    assert not any(group in line for line in log)


def refusals(lua, prefix):
    """Texts the modelled instance bucket refused on one prefix (INSTANCE only)."""
    total = lua.eval('__refused and #__refused or 0')
    return [lua.eval(f'__refused[{i}].text') for i in range(1, total + 1)
            if lua.eval(f'__refused[{i}].prefix') == prefix]


def facts(lua, name):
    """What one client knows about another character, as the tooltip reads it."""
    return lua.eval(f'(WoWStatusRoster.tooltipFacts("{name}-TestRealm"))')


def test_a_login_inside_an_instance_keeps_every_character_list_message():
    """#286: in an instance the character list must wait for the prefix allowance.

    Before the fix it sent two a second regardless and threw the game's answer
    away, so tens of list, quest, profession, statistics and XP lines were
    refused and never sent again.
    """
    net, me, _, _, missing = relog_after_absence(FRIENDS, 21, extra=INSTANCE)
    net.advance(120)
    dropped = [t for lua in net.clients.values() for t in refusals(lua, 'WoWStatusChr')]
    assert dropped == [], f'{len(dropped)} character-list messages refused inside an instance'
    # And the friends really do end up with her lines, not only an empty queue.
    for name in FRIENDS:
        seen = facts(net.clients[name], ME)
        assert seen is not None, f'{name} has no character list row for {ME}'
        assert seen['quests'] is not None and seen['professions'] is not None, f'{name} lacks lines for {ME}'
        assert seen['kills'] is not None, f'{name} lacks statistics for {ME}'


def instance_losses(friends, missed):
    """Character-list messages the instance bucket refuses in the 120 s after a login.

    The real send path, not a model: the client runs with INSTANCE, so every
    send meets the game's allowance and its answer goes back into the addon.
    """
    net, _, _, _, _ = relog_after_absence(friends, missed, extra=INSTANCE)
    net.advance(120)
    me = net.clients[ME]  # a fresh runtime since the login, so these are its own
    return len(refusals(me, 'WoWStatusChr')), me.eval(
        "#(function() local t={} for _,p in ipairs(__sent) do "
        "if p.prefix=='WoWStatusChr' then t[#t+1]=p end end return t end)()")


def figures():
    """Print the before figures docs/LOGIN_BURST.md quotes."""
    print('| Scenario | Sent by the login, 0-10 s | Received by it, 0-10 s | Whole group, 0-10 s '
          '| First missed entry | All missed entries | Changed gear | Character list past the allowance in an instance, 0-120 s |')
    print('|---|---|---|---|---|---|---|---|')
    for friends, missed in ((FRIENDS[:3], 21), (FRIENDS, 21), (FRIENDS, 105)):
        net, me, login, mark, missing = relog_after_absence(friends, missed)
        first, done, changed = catch_up(net, me, login, missing, limit=600, at_least=120)
        after = net.log[mark:]
        # The character list only: the log already waits for the allowance in an instance.
        lost, kept = instance_losses(friends, missed)
        instance = f'{lost} of {kept + lost}'

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
