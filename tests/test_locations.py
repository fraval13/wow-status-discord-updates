"""Named world/minimap pins from live, scoped, expiring position reports."""
import math

import pytest
from test_client_compatibility import client_runtime
from test_equipment_sync import Network

MAP = r'''
__posX,__posY=.5,.5
function CreateVector2D(x,y) return {x=x,y=y,GetXY=function(self) return self.x,self.y end} end
C_Map={
 GetBestMapForUnit=function() return 42 end,
 GetPlayerMapPosition=function() return CreateVector2D(__posX,__posY) end,
 GetWorldPosFromMapPos=function(_,v) return 1,CreateVector2D(1000-v.y*1000,1000-v.x*1000) end,
 GetMapPosFromWorldPos=function(_,v,id) return id,CreateVector2D(1-v.y/1000,1-v.x/1000) end,
 GetMapWorldSize=function() return 1000,1000 end,
 GetMapInfo=function() return {name="Example Woods"} end,
}
'''


def network():
    net = Network('Mira', 'Thora')
    net.clients['Mira'].execute(MAP + '__posX=.55')
    net.clients['Thora'].execute(MAP)
    net.advance(25)
    return net


@pytest.mark.parametrize('edition', ['vanilla', 'tbc', 'forever', 'retail'])
def test_position_capture_is_public_and_restricted_values_never_become_coordinates(edition):
    lua = client_runtime(edition)
    lua.execute(MAP + '''
        local point=WoWStatusLocations.capture()
        assert(point.map==42 and point.x==.5 and point.y==.5)
        __secret={};function issecretvalue(v) return v==__secret end
        C_Map.GetPlayerMapPosition=function() return __secret end
        assert(WoWStatusLocations.capture()==nil)
        C_Map.GetPlayerMapPosition=function() return CreateVector2D(0,0) end
        assert(WoWStatusLocations.capture()==nil)
    ''')


def test_continuous_positions_are_scoped_named_and_not_saved_or_relayed():
    net = network()
    thora = net.clients['Thora']
    entries = thora.eval('WoWStatusLocations.entries()')
    assert len(entries) == 1 and entries[1].name == 'Mira-TestRealm'
    assert entries[1].x == .55
    before = len(net.packets)
    net.clients['Mira'].execute('__posX=.6')
    net.advance(12)
    assert thora.eval('WoWStatusLocations.entries()[1].x') == .6
    sent = [p for p in net.packets[before:] if p[0] == 'Mira' and p[2].startswith('L ')]
    assert 1 <= len(sent) <= 3  # At least five seconds per recipient, never every frame.
    assert thora.eval('WoWStatusDB.roster.positions') is None
    assert thora.eval('WoWStatusDB.roster.locations') is None
    # Only Mira reports Mira: receivers never forward it as a location payload.
    assert all(p[2].split()[3].startswith('Thora-') or p[2].split()[3] in ('-','C')
               for p in net.packets if p[0] == 'Thora' and p[2].startswith('L '))


@pytest.mark.parametrize('privacy', ['zone', 'hidden', 'sharing'])
def test_stopping_location_sharing_removes_the_marker(privacy):
    net = network()
    mira, thora = net.clients['Mira'], net.clients['Thora']
    assert len(thora.eval('WoWStatusLocations.entries()')) == 1
    if privacy == 'zone':
        mira.execute('character().settings.fields.zone=false')
    elif privacy == 'hidden':
        mira.eval('WoWStatusRoster.setHidden')(mira.eval('character()'), True)
    else:
        mira.eval('WoWStatusRoster.setSharing')(False)
    net.advance(15)
    assert len(thora.eval('WoWStatusLocations.entries()')) == 0


def test_offline_or_stale_markers_expire_and_cannot_be_replayed_as_fresh():
    net = network()
    thora = net.clients['Thora']
    stale = next(p[2] for p in reversed(net.packets) if p[0] == 'Mira' and p[2].startswith('L '))
    net.clients.pop('Mira')
    net.advance(95)
    assert len(thora.eval('WoWStatusLocations.entries()')) == 0
    assert not thora.eval('WoWStatusRoster.receive')(stale, 'Mira-TestRealm', 'WHISPER')


def test_world_and_minimap_pins_have_names_on_hover_and_follow_map_rotation():
    net = network()
    lua = net.clients['Thora']
    lua.execute('''
        local methods=getmetatable(CreateFrame("Frame")).__index
        function methods:GetHeight() return self.height end
        Minimap=CreateFrame("Frame");Minimap:SetSize(160,160);Minimap:Show()
        C_Minimap={GetViewRadius=function() return 100 end}
        function GetCVar() return "0" end
        WorldMapFrame=CreateFrame("Frame");WorldMapFrame:Show()
        WorldMapFrame.canvas=CreateFrame("Frame",nil,WorldMapFrame);WorldMapFrame.canvas:SetSize(680,500)
        function WorldMapFrame:GetMapID() return 42 end
        function WorldMapFrame:GetCanvasContainer() return self.canvas end
        GameTooltip={SetOwner=function() end,SetText=function(_,text) __tooltip=text end,AddLine=function() end,Show=function() end,Hide=function() end}
        WoWStatusLocations.renderPins()
        local L=WoWStatusLocations
        assert(#L.worldPins==1 and #L.miniPins==1)
        L.miniPins[1].OnEnter(L.miniPins[1])
        assert(__tooltip=="Mira")
        L.worldPins[1].OnEnter(L.worldPins[1]);assert(__tooltip=="Mira")
        assert(L.worldPins[1].OnClick and L.miniPins[1].OnClick)
        L.miniPins[1].OnClick(L.miniPins[1])
        assert(WoWStatusMapFriends:IsShown() and WoWStatusMapFriends.scroll.kind=="ScrollFrame")
        assert(WoWStatusMapFriends.rows[1].text:find("Mira",1,true))
    ''')
    project = lua.eval('WoWStatusLocations.minimapOffset')
    player = lua.table_from({'map': 42, 'x': .5, 'y': .5})
    west = lua.table_from({'map': 42, 'x': .45, 'y': .5})
    x, y = project(west, player, 100, 160, 160, math.pi/2)
    assert abs(x) < 1e-6 and y > 0  # Facing west puts the western marker above you.
    far = lua.table_from({'map': 42, 'x': .9, 'y': .5})
    assert project(far, player, 100, 160, 160, None) is None


def test_spoofed_names_and_unjoined_groups_cannot_create_a_pin():
    net = network()
    lua = net.clients['Thora']
    group = lua.eval('(next(character().group_ids))')
    pid = net.clients['Mira'].eval('WoWStatusDB.roster.id')
    now = int(lua.eval('WoWStatusSafe.now()'))
    receive = lua.eval('WoWStatusRoster.receive')
    assert not receive(f'L {group} {pid} Other-TestRealm {now} 42 5000 5000', 'Mira-TestRealm', 'WHISPER')
    assert not receive(f'L unrelated {pid} Mira-TestRealm {now} 42 5000 5000', 'Mira-TestRealm', 'WHISPER')
    assert not receive(f'L {group} {pid} Mira-TestRealm {now} 42 10001 5000', 'Mira-TestRealm', 'WHISPER')


def test_older_clients_are_not_sent_coordinates_before_the_support_handshake():
    net = Network('Mira', 'Thora')
    net.clients['Mira'].execute(MAP)
    net.clients['Thora'].execute('''
        WoWStatusLocations.hello=function() return false end
        WoWStatusLocations.receive=function() return false end
    ''')
    net.advance(45)
    assert any(source == 'Mira' and text.startswith('B ') and text.endswith(' C') for source, _, text in net.packets)
    assert not any(source == 'Mira' and text.startswith('L ') and not text.endswith(' C') for source, _, text in net.packets)


@pytest.mark.parametrize('edition', ['vanilla','forever','tbc','retail'])
def test_common_map_selects_the_nearest_shared_parent_and_bounds_cycles(edition):
    lua=client_runtime(edition)
    lua.execute(MAP+'''
        local parents={[42]=9,[43]=9,[9]=1,[90]=10,[10]=1}
        C_Map.GetMapInfo=function(id) return {parentMapID=parents[id] or 0} end
        local L=WoWStatusLocations
        assert(L.commonMap({{map=42},{map=43}})==9)
        assert(L.commonMap({{map=42},{map=90}})==1)
        assert(L.commonMap({{map=42}})==42 and L.commonMap({})==nil)
        parents[9]=42
        assert(L.commonMap({{map=42},{map=43}})==42)
    ''')


def test_show_everyone_opens_the_shared_map_and_keeps_both_named_markers():
    net=network()
    bob=net.add('Bob')
    bob.execute(MAP+'function C_Map.GetBestMapForUnit() return 43 end;__posX=.6')
    net.advance(180)  # Login gear catch-up has priority on the shared queue.
    lua=net.clients['Thora']
    lua.execute('''
        local methods=getmetatable(CreateFrame("Frame")).__index
        function methods:GetHeight() return self.height end
        C_Map.GetMapInfo=function(id) return {name="Example",parentMapID=id==9 and 0 or 9} end
        WorldMapFrame=CreateFrame("Frame");WorldMapFrame:Hide()
        WorldMapFrame.canvas=CreateFrame("Frame",nil,WorldMapFrame);WorldMapFrame.canvas:SetSize(680,500)
        function WorldMapFrame:SetMapID(id) self.map=id end
        function WorldMapFrame:GetMapID() return self.map end
        function WorldMapFrame:GetCanvasContainer() return self.canvas end
        local L=WoWStatusLocations
        assert(#L.entries()==2 and L.showAll())
        assert(WorldMapFrame:IsShown() and WorldMapFrame.map==9 and #L.worldPins==2)
        local list=L.show()
        assert(list.all:IsEnabled() and #list.rows==2)
        list.all.OnClick()
        assert(not list:IsShown() and WorldMapFrame:IsShown() and WorldMapFrame.map==9)
        assert(WoWStatusTalents==nil)
    ''')


def test_empty_map_list_has_an_explanation_and_no_dead_overview_button():
    lua=client_runtime('forever')
    lua.execute('''
        assert(WoWStatusLocations.showAll()==false)
        assert(WoWStatusMapFriends:IsShown() and WoWStatusMapFriends.empty:IsShown())
        assert(not WoWStatusMapFriends.all:IsEnabled())
        assert(__categories["WoW Status"] and WoWStatusPopups.character())
    ''')


def test_positions_are_redacted_from_the_persistent_debug_log():
    net=network()
    lua=net.clients['Thora']
    lua.execute('WoWStatusDB.debug=true')
    net.advance(10)
    lua.execute('''
        local found=false
        for _,line in ipairs(WoWStatusDB.debug_log) do
            if line:find("got L ",1,true) then
                found=true;assert(line:find("L <group> <map detail>",1,true))
                assert(not line:find("5500",1,true))
            end
        end
        assert(found)
    ''')


def test_position_updates_and_gear_transfers_coexist_on_realmless_forever():
    from test_forever_equipment_sync import ForeverNetwork, gear
    net=ForeverNetwork('Mira Stone','Thora Vale')
    for lua in net.clients.values():
        lua.execute(MAP)
    net.advance(180)
    for own,friend in (('Mira Stone','Thora Vale'),('Thora Vale','Mira Stone')):
        lua=net.clients[own]
        assert gear(lua,friend+'-PvE')['items'][1].startswith('item:16963:1503:')
        entries=lua.eval('WoWStatusLocations.entries()')
        assert len(entries)==1 and entries[1].name.startswith(friend+'-')


def test_earlier_map_support_handshake_works_without_serving_any_talent_data():
    net=network()
    assert any(text.startswith('B ') and text.endswith(' C') for _,_,text in net.packets)
    lua=net.clients['Thora']
    group=lua.eval('(next(character().group_ids))')
    pid=net.clients['Mira'].eval('WoWStatusDB.roster.id')
    assert lua.eval('WoWStatusLocations.canMap')(group,'Mira-TestRealm')
    assert not lua.eval('WoWStatusRoster.receive')(f'B {group} {pid} R Thora-TestRealm deadbeef','Mira-TestRealm','WHISPER')
    assert lua.eval('WoWStatusTalents') is None


def test_world_map_uses_public_child_rectangles_without_world_coordinates():
    lua=client_runtime('forever')
    lua.execute(MAP+"""
        C_Map.GetMapRectOnMap=function(child,parent)
            assert(child==42 and parent==1)
            return .1,.3,.2,.6
        end
        C_Map.GetWorldPosFromMapPos=function() error("world conversion is unavailable") end
        local x,y=WoWStatusLocations.project({map=42,x=.5,y=.5},1)
        assert(math.abs(x-.2)<.00001 and math.abs(y-.4)<.00001)
    """)
