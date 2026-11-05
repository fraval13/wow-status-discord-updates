"""Zones uncovered on the map before installation are not announced as first visits."""
from test_addon import STUBS, make_lua

MAPS = STUBS + '''
__zone = "Dun Morogh"
function GetRealZoneText() return __zone end
__maps = {[1]={name="Elwynn Forest",mapType=3},[2]={name="Westfall",mapType=3},[3]={name="Duskwood",mapType=3},
    [4]={name="Eastern Kingdoms",mapType=2}}
__explored = {[1]={{},{},{}}, [2]={}, [3]={}, [4]={{}}}
__best = nil
C_Map = {GetMapInfo=function(id) return __maps[id] end, GetBestMapForUnit=function() return __best end}
C_MapExplorationInfo = {GetExploredMapTextures=function(id) return __explored[id] end}
'''


def zones_announced(lua):
    return [e.data.zone for e in lua.eval('character().events').values() if e.kind == 'zone']


def test_explored_zones_are_known_at_login_and_new_ones_are_announced():
    lua = make_lua(MAPS)
    lua.execute('''
        local visited = character().visited_zones
        assert(visited["Elwynn Forest"] and not visited["Westfall"] and not visited["Eastern Kingdoms"])
        -- Explored before installation: no announcement.
        __zone, __best = "Elwynn Forest", 1; fire("ZONE_CHANGED_NEW_AREA")
        -- A real first visit: arriving uncovers one area at most.
        __zone, __best = "Westfall", 2; __explored[2] = {{}}; fire("ZONE_CHANGED_NEW_AREA")
        -- Uncovered while the addon was not running (after this login's scan).
        __zone, __best = "Duskwood", 3; __explored[3] = {{}, {}, {}}; fire("ZONE_CHANGED_NEW_AREA")
    ''')
    assert zones_announced(lua) == ['Westfall']


def test_clients_without_map_exploration_announce_as_before():
    lua = make_lua(STUBS + '__zone = "Dun Morogh"\nfunction GetRealZoneText() return __zone end\n')
    lua.execute('__zone = "Westfall"; fire("ZONE_CHANGED_NEW_AREA")')
    assert zones_announced(lua) == ['Westfall']
