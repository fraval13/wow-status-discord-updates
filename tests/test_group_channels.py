"""Group chat channels are left when their group goes, including after /reload (#20)."""
from pathlib import Path

from test_addon import STUBS, make_lua

POPUPS = Path(__file__).parents[1] / 'addon/vanilla/WoWStatus/Popups.lua'
HEX22 = '0123456789abcdef012345'

# A client that remembers joined channels like the game does: in order, case-insensitively,
# and across /reload. GetChannelList returns (id, name, disabled) triples.
CHANNEL_STUBS = STUBS + r'''
__list = {}
__left = {}
__pairsFormat = false
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
function GetChannelList()
    local values = {}
    for _, entry in ipairs(__list) do
        table.insert(values, entry.id)
        table.insert(values, entry.name)
        if not __pairsFormat then table.insert(values, false) end
    end
    return (table.unpack or unpack)(values)
end
function joinedChannel(name) return find(name) ~= nil end
'''

UNRELATED = [
    'General - Dun Morogh',
    'Trade - City',
    'LookingForGroup',
    'WStatusFriends',          # the legacy default channel
    'MyGuildChat',
    'WStatus' + HEX22[:21],    # one hex character short
    'WStatus' + HEX22 + 'a',   # one hex character long
    'WStatus' + HEX22[:21] + 'g',  # right length, not hex
    'xWStatus' + HEX22,        # prefix is not anchored at the start
]


def group_channel(lua, label):
    return 'WStatus' + lua.eval('WoWStatusGroups.key')(label)[0]


def reload_popups(lua):
    """Simulate /reload: Popups module state restarts, the game keeps its channels."""
    lua.execute(POPUPS.read_text(encoding='utf-8'))
    lua.execute('WoWStatusPopups.init(WoWStatusDB, character, function() end)')


def joined(lua, name):
    return lua.eval('joinedChannel')(name)


def test_removing_a_group_after_reload_leaves_its_channel():
    lua = make_lua(CHANNEL_STUBS)
    lua.eval('WoWStatusGroups.update')('navsquad-test', '')
    lua.eval('WoWStatusPopups.tick')()
    channel = group_channel(lua, 'navsquad-test')
    assert joined(lua, channel)
    reload_popups(lua)
    assert joined(lua, channel)   # still a member, so nothing is left at init
    lua.eval('WoWStatusGroups.update')('', '')
    assert not joined(lua, channel)


def test_removing_a_group_without_reload_still_leaves_its_channel():
    lua = make_lua(CHANNEL_STUBS)
    lua.eval('WoWStatusGroups.update')('navsquad-test', '')
    lua.eval('WoWStatusPopups.tick')()
    channel = group_channel(lua, 'navsquad-test')
    lua.eval('WoWStatusGroups.update')('', '')
    assert not joined(lua, channel)


def test_only_the_removed_group_channel_is_left_and_unrelated_channels_stay():
    lua = make_lua(CHANNEL_STUBS)
    for name in UNRELATED:
        lua.eval('JoinTemporaryChannel')(name)
    lua.eval('WoWStatusGroups.update')('navsquad-test\nronkalot-test', '')
    lua.eval('WoWStatusPopups.tick')()
    removed, kept = group_channel(lua, 'navsquad-test'), group_channel(lua, 'ronkalot-test')
    assert joined(lua, removed) and joined(lua, kept)
    reload_popups(lua)
    lua.eval('WoWStatusGroups.update')('ronkalot-test', '')
    assert not joined(lua, removed)
    assert joined(lua, kept)
    for name in UNRELATED:
        assert joined(lua, name), name
    assert list(lua.eval('__left').values()) == [removed]


def test_leaving_all_groups_never_leaves_unrelated_channels():
    lua = make_lua(CHANNEL_STUBS)
    for name in UNRELATED:
        lua.eval('JoinTemporaryChannel')(name)
    lua.eval('WoWStatusGroups.update')('navsquad-test', '')
    lua.eval('WoWStatusPopups.tick')()
    reload_popups(lua)
    lua.eval('WoWStatusGroups.update')('', '')
    lua.eval('WoWStatusPopups.tick')()
    for name in UNRELATED:
        assert joined(lua, name), name
    assert list(lua.eval('__left').values()) == [group_channel(lua, 'navsquad-test')]


def test_older_pair_format_channel_list_is_understood():
    lua = make_lua(CHANNEL_STUBS)
    lua.execute('__pairsFormat = true')
    lua.eval('JoinTemporaryChannel')('General - Dun Morogh')
    lua.eval('WoWStatusGroups.update')('navsquad-test', '')
    lua.eval('WoWStatusPopups.tick')()
    channel = group_channel(lua, 'navsquad-test')
    reload_popups(lua)
    lua.eval('WoWStatusGroups.update')('', '')
    assert not joined(lua, channel)
    assert joined(lua, 'General - Dun Morogh')


def test_group_removed_elsewhere_is_left_on_the_next_reload():
    # Groups are account-wide: another character (or an older addon version) may have
    # dropped the group while this character's game session kept the channel.
    lua = make_lua(CHANNEL_STUBS)
    lua.eval('WoWStatusGroups.update')('navsquad-test\nronkalot-test', '')
    lua.eval('WoWStatusPopups.tick')()
    removed, kept = group_channel(lua, 'navsquad-test'), group_channel(lua, 'ronkalot-test')
    lua.execute(f'''
        local id = "{removed[len('WStatus'):]}"
        WoWStatusDB.account_groups[id] = nil
        for _, saved in pairs(WoWStatusDB.characters) do saved.group_ids[id] = nil end
    ''')
    reload_popups(lua)
    assert not joined(lua, removed)
    assert joined(lua, kept)


def test_missing_channel_list_api_falls_back_to_channels_joined_this_session():
    lua = make_lua(CHANNEL_STUBS)
    lua.execute('GetChannelList = nil')
    lua.eval('WoWStatusGroups.update')('navsquad-test', '')
    lua.eval('WoWStatusPopups.tick')()
    channel = group_channel(lua, 'navsquad-test')
    lua.eval('WoWStatusGroups.update')('', '')
    assert not joined(lua, channel)
