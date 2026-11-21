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
def test_map_sharing_is_independent_of_character_list_and_detail_settings(privacy):
    net = network()
    mira, thora = net.clients['Mira'], net.clients['Thora']
    assert len(thora.eval('WoWStatusLocations.entries()')) == 1
    if privacy == 'zone':
        mira.execute('character().settings.fields.zone=false')
    elif privacy == 'hidden':
        mira.eval('WoWStatusRoster.setHidden')(mira.eval('character()'), True)
    else:
        mira.eval('WoWStatusRoster.setSharing')(False)
    mira.execute('__posX=.65')
    net.advance(15)
    assert thora.eval('WoWStatusLocations.entries()[1].x') == .65


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
        for _,frame in ipairs(__frames) do if frame.OnUpdate then frame.OnUpdate(frame,.25) end end
        local L=WoWStatusLocations
        assert(#L.worldPins==1 and #L.miniPins==1)
        L.miniPins[1].OnEnter(L.miniPins[1])
        assert(__tooltip=="Mira")
        L.worldPins[1].OnEnter(L.worldPins[1]);assert(__tooltip=="Mira")
        assert(L.worldPins[1].OnClick==nil and L.miniPins[1].OnClick==nil)
        assert(WoWStatusMapFriends==nil and WoWStatusCharactersPage==nil)
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


def test_joining_a_group_is_enough_without_a_roster_or_any_addon_window():
    net=Network('Mira','Thora')
    for lua in net.clients.values():
        lua.execute(MAP+'''
            WoWStatusRoster.setSharing(false)
            character().settings.fields.zone=false
            WoWStatusRoster.setHidden(character(),true)
        ''')
    net.advance(50)
    for own,friend in (('Mira','Thora'),('Thora','Mira')):
        lua=net.clients[own]
        entries=lua.eval('WoWStatusLocations.entries()')
        assert len(entries)==1 and entries[1].name==friend+'-TestRealm'
        assert lua.eval('WoWStatusCharactersPage') is None
        assert lua.eval('WoWStatusMapFriends') is None
    net.clients['Mira'].execute('__posX=.7')
    net.advance(12)
    assert net.clients['Thora'].eval('WoWStatusLocations.entries()[1].x')==.7


def test_leaving_the_group_stops_reporting_and_removes_received_positions():
    net=network()
    lua=net.clients['Thora']
    lua.eval('WoWStatusGroups.update')('', '')
    before=len(net.packets)
    net.advance(15)
    assert len(lua.eval('WoWStatusLocations.entries()'))==0
    assert not any(source=='Thora' and text.startswith('L ') for source,_,text in net.packets[before:])


def test_missing_public_position_withdraws_only_the_senders_marker():
    net=network()
    net.clients['Mira'].execute('C_Map.GetPlayerMapPosition=function() return nil end')
    net.advance(10)
    assert len(net.clients['Thora'].eval('WoWStatusLocations.entries()'))==0
    assert any(source=='Mira' and text.startswith('L ') and text.endswith(' -') for source,_,text in net.packets)


def test_another_member_cannot_withdraw_someone_elses_marker_by_claiming_their_id():
    net=network()
    net.add('Bob').execute(MAP)
    net.advance(60)
    lua=net.clients['Thora']
    group=lua.eval('(next(character().group_ids))')
    pid=net.clients['Mira'].eval('WoWStatusDB.roster.id')
    assert lua.eval('WoWStatusRoster.receive')(f'L {group} {pid} -','Bob-TestRealm','WHISPER')
    assert any(entry.name=='Mira-TestRealm' for entry in lua.eval('WoWStatusLocations.entries()').values())


@pytest.mark.parametrize('edition', ['vanilla','forever','tbc','retail'])
def test_native_group_member_positions_do_not_require_a_shared_roster_on_any_edition(edition):
    lua=client_runtime(edition)
    lua.execute(MAP+'''
        WoWStatusGroups.update("dawnwatch","")
        __peers={"Mira-TestRealm"}
        WoWStatusRoster.setSharing(false)
        character().settings.fields.zone=false
        local group=next(character().group_ids)
        local pid="aaaaaaaaaaaaaaaa"
        assert(WoWStatusDB.roster.players[pid]==nil)
        local text=table.concat({"L",group,pid,"Mira-TestRealm",WoWStatusSafe.now(),42,5500,5000}," ")
        assert(WoWStatusRoster.receive(text,"Mira-TestRealm","WHISPER"))
        local entries=WoWStatusLocations.entries()
        assert(#entries==1 and entries[1].name=="Mira-TestRealm" and entries[1].x==.55)
        assert(WoWStatusDB.roster.players[pid]==nil and WoWStatusMapFriends==nil)
    ''')


def test_opt_out_stops_sending_and_withdraws_your_marker_but_keeps_friends_visible():
    net=network()
    mira,thora=net.clients['Mira'],net.clients['Thora']
    mira.execute('''
        SlashCmdList.WOWSTATUS("")
        for _,entry in ipairs(WoWStatusSetup.checks) do
            if entry.key=="share_position" then __positionCheck=entry.widget end
        end
        assert(__positionCheck and __positionCheck:GetChecked())
        __positionCheck:SetChecked(false);__positionCheck.OnClick(__positionCheck)
        assert(character().settings.share_position==false and not WoWStatusLocations.sharing())
    ''')
    before=len(net.packets)
    net.advance(15)
    assert len(thora.eval('WoWStatusLocations.entries()'))==0
    assert len(mira.eval('WoWStatusLocations.entries()'))==1
    assert not any(source=='Mira' and text.startswith('L ') and not text.endswith(' -')
                   for source,_,text in net.packets[before:])
    mira.execute('__positionCheck:SetChecked(true);__positionCheck.OnClick(__positionCheck)')
    net.advance(12)
    assert len(thora.eval('WoWStatusLocations.entries()'))==1


def test_opt_out_blocks_a_coordinate_already_queued_before_the_setting_changed():
    net=network()
    mira=net.clients['Mira']
    mira.execute('''
        local group=next(character().group_ids)
        local text=table.concat({"L",group,WoWStatusDB.roster.id,"Mira-TestRealm",WoWStatusSafe.now(),42,8100,5000}," ")
        assert(WoWStatusRoster.queueLocation(group,"Thora-TestRealm",text,true))
        character().settings.share_position=false
        -- Hold the location producer: the queued-coordinate privacy check must
        -- work independently of a subsequent coalesced withdrawal.
        WoWStatusLocations.tick=function() end
    ''')
    before=len(net.packets)
    net.advance(12)
    assert not any(source=='Mira' and text.startswith('L ') and ' 8100 ' in text
                   for source,_,text in net.packets[before:])


@pytest.mark.parametrize('edition',['vanilla','forever','tbc','retail'])
def test_position_preference_defaults_on_and_preserves_the_character_opt_out(edition):
    lua=client_runtime(edition)
    lua.execute('''
        local L=WoWStatusLocations
        assert(character().settings.share_position==true and L.sharing())
        character().settings.share_position=false
        L.init(WoWStatusDB,character(),WoWStatusRoster.queueLocation)
        assert(character().settings.share_position==false and not L.sharing())
        character().settings.share_position=nil
        L.init(WoWStatusDB,character(),WoWStatusRoster.queueLocation)
        assert(character().settings.share_position==true and L.sharing())
    ''')


def test_markers_sit_on_the_zooming_canvas_with_class_colours_and_names_under_them():
    net = network()
    lua = net.clients['Thora']
    lua.execute('''
        local methods=getmetatable(CreateFrame("Frame")).__index
        function methods:GetHeight() return self.height end
        function methods:SetColorTexture(r,g,b,a) self.colour={r,g,b,a} end
        Minimap=CreateFrame("Frame");Minimap:SetSize(160,160);Minimap:Show()
        C_Minimap={GetViewRadius=function() return 100 end}
        function GetCVar() return "0" end
        WorldMapFrame=CreateFrame("Frame");WorldMapFrame:Show()
        -- The container keeps still; the child is what pans and zooms.
        WorldMapFrame.container=CreateFrame("Frame",nil,WorldMapFrame);WorldMapFrame.container:SetSize(680,500)
        WorldMapFrame.child=CreateFrame("Frame",nil,WorldMapFrame.container);WorldMapFrame.child:SetSize(1360,1000)
        function WorldMapFrame:GetMapID() return 42 end
        function WorldMapFrame:GetCanvasContainer() return self.container end
        function WorldMapFrame:GetCanvas() return self.child end
        -- SetText takes one argument: gsub's substitution count must not reach it.
        GameTooltip={SetOwner=function() end,
            SetText=function(_,text,...) __tooltip,__extra=text,select("#",...) end,
            AddLine=function() end,Show=function() end,Hide=function() end}
        for _,frame in ipairs(__frames) do if frame.OnUpdate then frame.OnUpdate(frame,.25) end end
        local L=WoWStatusLocations
        local class=WoWStatusRoster.classFor("Mira-TestRealm")
        assert(class,"the roster knows a group friend's class")
        assert(WoWStatusRoster.classFor("Nobody-TestRealm")==nil)
        RAID_CLASS_COLORS={[class]={r=.1,g=.2,b=.3}}
        L.renderPins()
        local world=L.worldPins[1]
        assert(world:GetParent()==WorldMapFrame.child)
        assert(world.icon.colour[1]==.1 and world.icon.colour[2]==.2 and world.icon.colour[3]==.3)
        assert(world.label:GetText()=="Mira" and world.label:IsShown()~=false)
        world.OnEnter(world)
        assert(__tooltip=="Mira" and __extra==0)
        -- The minimap marker keeps the colour but not the name, for room.
        assert(L.miniPins[1].icon.colour[1]==.1 and L.miniPins[1].label:IsShown()==false)
        -- An unknown class keeps the former green.
        RAID_CLASS_COLORS={}
        L.renderPins()
        assert(math.abs(L.worldPins[1].icon.colour[1]-.22)<1e-9)
    ''')
