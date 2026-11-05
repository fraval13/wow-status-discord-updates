"""Group chat channels are left when their group goes, including after /reload (#20)."""
from pathlib import Path

from test_addon import STUBS, make_lua

POPUPS = Path(__file__).parents[1] / 'addon/vanilla/WoWStatus/Popups.lua'
HEX22 = '0123456789abcdef012345'

# A client that remembers joined channels like the game does: in order, case-insensitively,
# and across /reload.
CHANNEL_STUBS = STUBS + r'''
__list = {}
__left = {}
local function find(name)
    for i, entry in ipairs(__list) do if entry.name:lower() == name:lower() then return i end end
end
function GetChannelName(name)
    local i = find(name)
    if i then return __list[i].id, __list[i].name end
    return 0, nil
end
function JoinTemporaryChannel(name)
    if not find(name) then table.insert(__list, {id = #__list + 1, name = name}) end
end
function LeaveChannelByName(name)
    table.insert(__left, name)
    local i = find(name)
    if i then table.remove(__list, i) end
end
function joinedChannel(name) return find(name) ~= nil end
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
    lua = make_lua(CHANNEL_STUBS)
    lua.eval('WoWStatusGroups.update')('dawnwatch-test', '')
    lua.eval('WoWStatusPopups.tick')()
    channel = group_channel(lua, 'dawnwatch-test')
    assert joined(lua, channel)
    reload_popups(lua)
    assert joined(lua, channel)   # still a member, so init leaves nothing
    lua.eval('WoWStatusGroups.update')('', '')
    assert not joined(lua, channel)


def test_removing_a_group_without_reload_still_leaves_its_channel():
    lua = make_lua(CHANNEL_STUBS)
    lua.eval('WoWStatusGroups.update')('dawnwatch-test', '')
    lua.eval('WoWStatusPopups.tick')()
    channel = group_channel(lua, 'dawnwatch-test')
    lua.eval('WoWStatusGroups.update')('', '')
    assert not joined(lua, channel)
    assert lua.eval('savedChannelCount()') == 0


def test_only_the_removed_group_channel_is_left_and_unrelated_channels_stay():
    lua = make_lua(CHANNEL_STUBS)
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
    lua = make_lua(CHANNEL_STUBS)
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
    lua = make_lua(CHANNEL_STUBS)
    channel = group_channel(lua, 'dawnwatch-test')
    lua.eval('JoinTemporaryChannel')(channel)
    lua.eval('WoWStatusGroups.update')('dawnwatch-test', '')
    lua.eval('WoWStatusPopups.tick')()
    reload_popups(lua)
    lua.eval('WoWStatusGroups.update')('', '')
    assert joined(lua, channel)
    assert left(lua) == []


def test_damaged_saved_channel_list_cannot_name_other_channels():
    lua = make_lua(CHANNEL_STUBS)
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
    lua.execute('__list = {}')
    reload_popups(lua)


def test_entries_from_an_earlier_session_never_leave_a_channel_joined_by_hand():
    lua = make_lua(CHANNEL_STUBS)
    channel = group_channel(lua, 'dawnwatch-test')
    lua.execute(f'WoWStatusDB.popups.joined_channels = {{["{channel.lower()}"] = true}}')
    relog(lua)
    assert lua.eval('savedChannelCount()') == 0
    lua.eval('JoinTemporaryChannel')(channel)
    lua.eval('WoWStatusGroups.update')('emberhold-test', '')
    assert joined(lua, channel)
    assert left(lua) == []


def test_relog_rejoins_and_records_current_groups_so_removal_still_leaves():
    lua = make_lua(CHANNEL_STUBS)
    lua.eval('WoWStatusGroups.update')('dawnwatch-test', '')
    lua.eval('WoWStatusPopups.tick')()
    channel = group_channel(lua, 'dawnwatch-test')
    relog(lua)
    assert joined(lua, channel)   # the addon joined it again at login
    reload_popups(lua)
    lua.eval('WoWStatusGroups.update')('', '')
    assert not joined(lua, channel)


def test_a_join_still_pending_when_its_group_is_removed_is_still_left():
    lua = make_lua(CHANNEL_STUBS)
    lua.execute('__pending = {}; JoinTemporaryChannel = function(name) table.insert(__pending, name) end')
    lua.eval('WoWStatusGroups.update')('dawnwatch-test', '')
    lua.eval('WoWStatusPopups.tick')()
    channel = group_channel(lua, 'dawnwatch-test')
    assert not joined(lua, channel)   # the server has not confirmed the join yet
    lua.eval('WoWStatusGroups.update')('', '')
    assert left(lua) == [channel.lower()]
    assert lua.eval('savedChannelCount()') == 0


def test_without_get_channel_name_saved_channels_are_kept_and_left():
    lua = make_lua(CHANNEL_STUBS)
    lua.eval('WoWStatusGroups.update')('dawnwatch-test', '')
    lua.eval('WoWStatusPopups.tick')()
    channel = group_channel(lua, 'dawnwatch-test')
    lua.execute('GetChannelName = nil')
    reload_popups(lua)
    lua.eval('WoWStatusGroups.update')('', '')
    assert not joined(lua, channel)
