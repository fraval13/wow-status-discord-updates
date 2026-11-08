"""Group chat channels are left when their group goes, including after /reload (#20)."""
from pathlib import Path

from test_addon import STUBS, make_lua

POPUPS = Path(__file__).parents[1] / 'addon/vanilla/WoWStatus/Popups.lua'
HEX22 = '0123456789abcdef012345'

# A client that remembers joined channels like the game does: in order, case-insensitively,
# and across /reload.
CHANNEL_STUBS = STUBS + r'''
__slots = {}   -- channel number -> name, the client's chat channel list
__left = {}
local function find(name)
    for i, entry in pairs(__slots) do if entry:lower() == name:lower() then return i end end
end
function GetChannelName(which)
    if type(which) == "number" then
        local name = __slots[which]
        if name then return which, name end
        return 0, nil
    end
    local i = find(which)
    if i then return i, __slots[i] end
    return 0, nil
end
-- Like the game: a join takes the lowest free number, and leaving leaves a gap.
function JoinTemporaryChannel(name)
    if find(name) then return end
    local i = 1
    while __slots[i] do i = i + 1 end
    __slots[i] = name
end
function LeaveChannelByName(name)
    table.insert(__left, name)
    local i = find(name)
    if i then __slots[i] = nil end
end
function joinedChannel(name) return find(name) ~= nil end
function channelNumber(name) return find(name) or 0 end
-- The channels the client joins by itself a moment after login.
CLIENT_CHANNELS = {"General - Dun Morogh", "Trade - City", "LocalDefense - Dun Morogh", "LookingForGroup"}
function __clientChannels()
    for _, name in ipairs(CLIENT_CHANNELS) do JoinTemporaryChannel(name) end
end
-- The client's own clock, so a test can let the addon's waiting deadlines pass.
__now = 1
function GetTime() return __now end
function __advance(seconds) __now = __now + seconds end
function savedChannelCount()
    local n = 0
    for _ in pairs(WoWStatusDB.popups.joined_channels) do n = n + 1 end
    return n
end
'''

UNRELATED = [
    'General - Dun Morogh',
    'Trade - City',
    'LookingForGroup',
    'WStatusFriends',          # the legacy default channel
    'MyGuildChat',
    'WStatus' + HEX22,         # group-shaped, but joined by the player with /join
]

DAMAGED_SAVE = '''
WoWStatusDB.popups.joined_channels = {
    ["general - dun morogh"] = true, ["wstatusfriends"] = true,
    ["wstatus0123456789abcdef01234"] = true,
    ["wstatus0123456789abcdef012345"] = "yes",
    [1] = true,
}
'''

OVERSIZED_SAVE = '''
local saved = {}
for i = 1, 100 do
    local name = string.format("wstatus%022x", i)
    saved[name] = true
    if i <= 5 then JoinTemporaryChannel(name) end
end
WoWStatusDB.popups.joined_channels = saved
'''


def make_client(stubs=CHANNEL_STUBS):
    """A client that has already joined its own channels, as a moment after login."""
    lua = make_lua(stubs)
    lua.eval('__clientChannels')()
    return lua


def group_channel(lua, label):
    return 'WStatus' + lua.eval('WoWStatusGroups.key')(label)[0]


def reload_popups(lua):
    """Simulate /reload: Popups module state restarts, the game keeps its channels."""
    lua.execute(POPUPS.read_text(encoding='utf-8'))
    lua.execute('WoWStatusPopups.init(WoWStatusDB, character, function() end)')


def joined(lua, name):
    return lua.eval('joinedChannel')(name)


def left(lua):
    return [name.lower() for name in lua.eval('__left').values()]


def test_removing_a_group_after_reload_leaves_its_channel():
    lua = make_client()
    lua.eval('WoWStatusGroups.update')('dawnwatch-test', '')
    lua.eval('WoWStatusPopups.tick')()
    channel = group_channel(lua, 'dawnwatch-test')
    assert joined(lua, channel)
    reload_popups(lua)
    assert joined(lua, channel)   # still a member, so init leaves nothing
    lua.eval('WoWStatusGroups.update')('', '')
    assert not joined(lua, channel)


def test_removing_a_group_without_reload_still_leaves_its_channel():
    lua = make_client()
    lua.eval('WoWStatusGroups.update')('dawnwatch-test', '')
    lua.eval('WoWStatusPopups.tick')()
    channel = group_channel(lua, 'dawnwatch-test')
    lua.eval('WoWStatusGroups.update')('', '')
    assert not joined(lua, channel)
    assert lua.eval('savedChannelCount()') == 0


def test_only_the_removed_group_channel_is_left_and_unrelated_channels_stay():
    lua = make_client()
    for name in UNRELATED:
        lua.eval('JoinTemporaryChannel')(name)
    lua.eval('WoWStatusGroups.update')('dawnwatch-test\nemberhold-test', '')
    lua.eval('WoWStatusPopups.tick')()
    removed, kept = group_channel(lua, 'dawnwatch-test'), group_channel(lua, 'emberhold-test')
    assert joined(lua, removed) and joined(lua, kept)
    reload_popups(lua)
    lua.eval('WoWStatusGroups.update')('emberhold-test', '')
    assert not joined(lua, removed)
    assert joined(lua, kept)
    for name in UNRELATED:
        assert joined(lua, name), name
    assert left(lua) == [removed.lower()]


def test_leaving_all_groups_never_leaves_unrelated_channels():
    lua = make_client()
    for name in UNRELATED:
        lua.eval('JoinTemporaryChannel')(name)
    lua.eval('WoWStatusGroups.update')('dawnwatch-test', '')
    lua.eval('WoWStatusPopups.tick')()
    reload_popups(lua)
    lua.eval('WoWStatusGroups.update')('', '')
    lua.eval('WoWStatusPopups.tick')()
    for name in UNRELATED:
        assert joined(lua, name), name
    assert left(lua) == [group_channel(lua, 'dawnwatch-test').lower()]


def test_a_group_channel_the_player_joined_first_is_not_left():
    # The addon only leaves what it joined; a channel already joined by hand stays theirs.
    lua = make_client()
    channel = group_channel(lua, 'dawnwatch-test')
    lua.eval('JoinTemporaryChannel')(channel)
    lua.eval('WoWStatusGroups.update')('dawnwatch-test', '')
    lua.eval('WoWStatusPopups.tick')()
    reload_popups(lua)
    lua.eval('WoWStatusGroups.update')('', '')
    assert joined(lua, channel)
    assert left(lua) == []


def test_damaged_saved_channel_list_cannot_name_other_channels():
    lua = make_client()
    lua.eval('JoinTemporaryChannel')('General - Dun Morogh')
    lua.eval('JoinTemporaryChannel')('WStatusFriends')
    lua.execute(DAMAGED_SAVE)
    reload_popups(lua)
    assert lua.eval('savedChannelCount()') == 0
    lua.execute(OVERSIZED_SAVE)
    reload_popups(lua)
    assert lua.eval('savedChannelCount()') == 5   # only the channels joined right now
    lua.eval('WoWStatusGroups.update')('', '')
    assert joined(lua, 'General - Dun Morogh') and joined(lua, 'WStatusFriends')
    assert sorted(left(lua)) == ['wstatus%022x' % i for i in range(1, 6)]
    assert lua.eval('savedChannelCount()') == 0


def relog(lua):
    """Simulate logout and login: the game drops temporary channels, saved data stays."""
    lua.execute('__slots = {}')
    lua.eval('__clientChannels')()   # the client joins General and Trade again too
    reload_popups(lua)


def test_entries_from_an_earlier_session_never_leave_a_channel_joined_by_hand():
    lua = make_client()
    channel = group_channel(lua, 'dawnwatch-test')
    lua.execute(f'WoWStatusDB.popups.joined_channels = {{["{channel.lower()}"] = true}}')
    relog(lua)
    assert lua.eval('savedChannelCount()') == 0
    lua.eval('JoinTemporaryChannel')(channel)
    lua.eval('WoWStatusGroups.update')('emberhold-test', '')
    assert joined(lua, channel)
    assert left(lua) == []


def test_relog_rejoins_and_records_current_groups_so_removal_still_leaves():
    lua = make_client()
    lua.eval('WoWStatusGroups.update')('dawnwatch-test', '')
    lua.eval('WoWStatusPopups.tick')()
    channel = group_channel(lua, 'dawnwatch-test')
    relog(lua)
    assert joined(lua, channel)   # the addon joined it again at login
    reload_popups(lua)
    lua.eval('WoWStatusGroups.update')('', '')
    assert not joined(lua, channel)


def test_a_join_still_pending_when_its_group_is_removed_is_still_left():
    lua = make_client()
    lua.execute('__pending = {}; JoinTemporaryChannel = function(name) table.insert(__pending, name) end')
    lua.eval('WoWStatusGroups.update')('dawnwatch-test', '')
    lua.eval('WoWStatusPopups.tick')()
    channel = group_channel(lua, 'dawnwatch-test')
    assert not joined(lua, channel)   # the server has not confirmed the join yet
    lua.eval('WoWStatusGroups.update')('', '')
    assert left(lua) == [channel.lower()]
    assert lua.eval('savedChannelCount()') == 0


def test_without_get_channel_name_saved_channels_are_kept_and_left():
    lua = make_client()
    lua.eval('WoWStatusGroups.update')('dawnwatch-test', '')
    lua.eval('WoWStatusPopups.tick')()
    channel = group_channel(lua, 'dawnwatch-test')
    lua.execute('GetChannelName = nil')
    reload_popups(lua)
    lua.eval('WoWStatusGroups.update')('', '')
    assert not joined(lua, channel)


# Chat channel numbers. The client joins General, Trade and the zone channels a
# moment after the addon loads, and the game always gives a join the lowest free
# number, so joining at once would take /1 and /2 from them.
def test_a_group_channel_waits_so_general_and_trade_keep_their_numbers():
    lua = make_lua(CHANNEL_STUBS)   # at login the client has joined nothing yet
    lua.eval('WoWStatusGroups.update')('dawnwatch-test', '')
    lua.eval('WoWStatusPopups.tick')()
    channel = group_channel(lua, 'dawnwatch-test')
    assert not joined(lua, channel)                  # waits instead of taking /1
    lua.eval('__clientChannels')()
    lua.eval('WoWStatusPopups.tick')()
    assert lua.eval('channelNumber')(channel) == 5   # after the client's four
    assert lua.eval('channelNumber')('General - Dun Morogh') == 1
    assert lua.eval('channelNumber')('Trade - City') == 2
    assert left(lua) == []


def test_a_second_group_channel_follows_the_first():
    lua = make_client()
    lua.eval('WoWStatusGroups.update')('dawnwatch-test\nemberhold-test', '')
    lua.eval('WoWStatusPopups.tick')()
    numbers = sorted(lua.eval('channelNumber')(group_channel(lua, label))
                     for label in ('dawnwatch-test', 'emberhold-test'))
    assert numbers == [5, 6]


def test_a_group_channel_settles_for_a_lower_number_when_the_low_ones_stay_free():
    lua = make_lua(CHANNEL_STUBS)
    lua.eval('JoinTemporaryChannel')('General - Dun Morogh')
    lua.eval('JoinTemporaryChannel')('Trade - City')
    lua.eval('WoWStatusGroups.update')('dawnwatch-test', '')
    lua.eval('WoWStatusPopups.tick')()
    channel = group_channel(lua, 'dawnwatch-test')
    assert not joined(lua, channel)      # still hoping for the zone channels
    lua.eval('__advance')(20)            # past the preferred wait, not the last one
    lua.eval('WoWStatusPopups.tick')()
    assert lua.eval('channelNumber')(channel) == 3
    assert lua.eval('channelNumber')('General - Dun Morogh') == 1
    assert lua.eval('channelNumber')('Trade - City') == 2


def test_a_player_without_general_and_trade_still_gets_the_group_channel():
    # Sharing with friends matters more than the number: the wait always ends.
    lua = make_lua(CHANNEL_STUBS)
    lua.eval('WoWStatusGroups.update')('dawnwatch-test', '')
    lua.eval('WoWStatusPopups.tick')()
    channel = group_channel(lua, 'dawnwatch-test')
    assert not joined(lua, channel)
    lua.eval('__advance')(70)            # past every wait
    lua.eval('WoWStatusPopups.tick')()
    assert joined(lua, channel)


def test_a_reload_keeps_the_number_the_channel_already_has():
    lua = make_client()
    lua.eval('WoWStatusGroups.update')('dawnwatch-test', '')
    lua.eval('WoWStatusPopups.tick')()
    channel = group_channel(lua, 'dawnwatch-test')
    assert lua.eval('channelNumber')(channel) == 5
    reload_popups(lua)
    lua.eval('WoWStatusPopups.tick')()
    assert lua.eval('channelNumber')(channel) == 5   # no leave and rejoin
    assert left(lua) == []


def test_a_group_added_later_in_the_session_waits_for_the_low_numbers_too():
    lua = make_lua(CHANNEL_STUBS)
    lua.eval('__advance')(600)            # well into the session
    lua.eval('WoWStatusGroups.update')('dawnwatch-test', '')
    lua.eval('WoWStatusPopups.tick')()
    channel = group_channel(lua, 'dawnwatch-test')
    assert not joined(lua, channel)       # the wait belongs to the join, not to login
    lua.eval('__clientChannels')()
    lua.eval('WoWStatusPopups.tick')()
    assert lua.eval('channelNumber')(channel) == 5
