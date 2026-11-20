-- Live reported positions, only over joined groups. Never persisted or relayed.
-- Whispers are paced through the roster's shared queue; stale pins expire.
WoWStatusLocations = {}
local L,S=WoWStatusLocations,WoWStatusSafe
local T,TF=WoWStatusLocale.T,WoWStatusLocale.F
local db,current,send
local reports,lastFor={},{}
local capabilities,helloAt={},{}
local lastTick,cursor=0,0
local peerCache,peerCacheAt={},-5
local MAX_REPORTS,EXPIRE=128,90
local worldPins,miniPins={},{}
local window
local function key(name) return WoWStatusRoster.key(name) end
local function integer(value,low,high)
    value=S.number(value);return value and value==math.floor(value) and value>=low and value<=high and value or nil
end
local function xy(vector)
    if type(S.value(vector))~="table" then return nil end
    local x,y=S.call(vector.GetXY,vector)
    x,y=S.number(x) or S.number(vector.x),S.number(y) or S.number(vector.y)
    return x,y
end
local function vector(x,y)
    return S.call(CreateVector2D,x,y) or {x=x,y=y}
end
function L.capture()
    if not C_Map then return nil end
    local map=integer(S.call(C_Map.GetBestMapForUnit,"player"),1,1000000)
    if not map then return nil end
    local x,y=xy(S.call(C_Map.GetPlayerMapPosition,map,"player"))
    if not x or not y or x<0 or y<0 or x>1 or y>1 or (x==0 and y==0) then return nil end
    return {map=map,x=x,y=y,at=math.floor(S.now())}
end
local function allowed()
    return db and current and db.roster.share and not current.hide_from_list
        and current.settings and current.settings.fields and current.settings.fields.zone
        and not (WoWStatusGuide and WoWStatusGuide.touring())
end
local function recipients()
    if S.uptime()-peerCacheAt<5 then return peerCache end
    local list={}
    for group in pairs(WoWStatusGroups.selected(current)) do
        local peers=WoWStatusPopups.peers(group)
        if #peers==0 then peers=WoWStatusRoster.recentMembers(group) end
        for _,peer in ipairs(peers) do
            if not WoWStatusPopups.isSelf(peer) and #list<128 then list[#list+1]={group=group,peer=peer,id=group..":"..(key(peer) or "")} end
        end
    end
    table.sort(list,function(a,b) return a.id<b.id end)
    peerCache,peerCacheAt=list,S.uptime()
    return list
end
function L.forget(owner,group)
    for k,r in pairs(reports) do
        if r.owner==owner then
            if group then r.groups[group]=nil;if not next(r.groups) then reports[k]=nil end else reports[k]=nil end
        end
    end
end
local function trim(map,maximum)
    local count=0;for _ in pairs(map) do count=count+1 end
    while count>maximum do
        local oldest,at
        for k,v in pairs(map) do
            local stamp=type(v)=="table" and v.at or v
            if not at or stamp<at then oldest,at=k,stamp end
        end
        if not oldest then break end
        map[oldest]=nil;count=count-1
    end
end
-- Keep the earlier B/C map-support handshake for existing map-capable clients.
-- This module handles only that capability, not talent requests or snapshots.
function L.hello(group,peer,reply)
    if not db or (WoWStatusGuide and WoWStatusGuide.touring()) or WoWStatusPopups.isSelf(peer) then return false end
    local k=group..":"..(key(peer) or "")
    if helloAt[k] and S.uptime()-helloAt[k]<(reply and 5 or 120) then return false end
    if send(group,peer,table.concat({"B",group,db.roster.id,"C"}," ")) then
        helloAt[k]=S.uptime();trim(helloAt,128);return true
    end
    return false
end
function L.canMap(group,peer)
    local c=capabilities[group..":"..(key(peer) or "")]
    return c~=nil and S.uptime()-c.at<180
end
function L.receive(w,sender)
    if not db or (WoWStatusGuide and WoWStatusGuide.touring()) then return false end
    local group,pid=w[2],w[3]
    if #w==4 and w[4]=="C" then
        capabilities[group..":"..(key(sender) or "")]={owner=pid,at=S.uptime()}
        trim(capabilities,128);L.hello(group,sender,true);return true
    end
    local owner=db.roster.players and db.roster.players[pid]
    if not owner or not owner.characters or not owner.characters[key(sender) or ""] then return false end
    if #w==4 and w[4]=="-" then L.forget(pid,group);return true end
    if #w~=8 or #w[4]>64 or w[4]:find(S.CONTROL_OR_PIPE) or not w[4]:match("^[^%-]+%-[^%-]+$") then return false end
    local name=w[4]:gsub("_"," ")
    if key(name)~=key(sender) or WoWStatusRoster.isHidden(name) then return false end
    local at,map,x,y=integer(tonumber(w[5]),1,100000000000),integer(tonumber(w[6]),1,1000000),
        integer(tonumber(w[7]),0,10000),integer(tonumber(w[8]),0,10000)
    if not at or not map or not x or not y or (x==0 and y==0) or S.outside(at,EXPIRE,5) then return false end
    local k=pid..":"..(key(name) or "")
    local old=reports[k]
    if old and old.at>at then return false end
    local count,oldest,stamp=0,nil,math.huge
    for id,r in pairs(reports) do count=count+1;if r.received<stamp then oldest,stamp=id,r.received end end
    if not old and count>=MAX_REPORTS and oldest then reports[oldest]=nil end
    local groups=old and old.groups or {};groups[group]=true
    reports[k]={owner=pid,name=name,map=map,x=x/10000,y=y/10000,at=at,received=S.uptime(),groups=groups}
    return true
end
function L.entries()
    local list={}
    if not db then return list end
    for k,r in pairs(reports) do
        local shared=false
        for group in pairs(r.groups) do
            if WoWStatusGroups.contains(current,group) then shared=true else r.groups[group]=nil end
        end
        if not shared or S.uptime()-r.received>EXPIRE or S.outside(r.at,EXPIRE,5) or WoWStatusRoster.isHidden(r.name) then reports[k]=nil
        else list[#list+1]=r end
    end
    table.sort(list,function(a,b) return a.name<b.name end)
    return list
end
-- Convert using the game's map definitions, preserving its north/west world axes.
local function world(item)
    if item.continent then return item.continent,item.north,item.west end
    if not C_Map then return nil end
    local continent,pos=S.call(C_Map.GetWorldPosFromMapPos,item.map,vector(item.x,item.y))
    continent=S.number(continent)
    local north,west=xy(pos)
    if continent and north and west then item.continent,item.north,item.west=continent,north,west;return continent,north,west end
end
function L.project(item,map)
    if item.map==map then return item.x,item.y end
    -- Parent-map rectangles also cover continents on a world map, where a
    -- world-coordinate conversion may not provide a projection.
    if C_Map then
        local left,right,top,bottom=S.call(C_Map.GetMapRectOnMap,item.map,map)
        left,right,top,bottom=S.number(left),S.number(right),S.number(top),S.number(bottom)
        if left and right and top and bottom and right>left and bottom>top then
            local x,y=left+(right-left)*item.x,top+(bottom-top)*item.y
            if x>=0 and x<=1 and y>=0 and y<=1 then return x,y end
        end
    end
    local continent,north,west=world(item)
    if not continent or not C_Map then return nil end
    local projected,pos=S.call(C_Map.GetMapPosFromWorldPos,continent,vector(north,west),map)
    if S.number(projected)~=map then return nil end
    local x,y=xy(pos)
    if x and y and x>=0 and x<=1 and y>=0 and y<=1 then return x,y end
end
function L.minimapOffset(item,player,radius,width,height,facing)
    if not player or not radius or radius<=0 or not width or not height then return nil end
    local continent,north,west=world(item)
    local ownContinent,ownNorth,ownWest=world(player)
    local east,up
    if continent and ownContinent and continent==ownContinent then east,up=ownWest-west,north-ownNorth
    elseif item.map==player.map and C_Map then
        local w,h=S.call(C_Map.GetMapWorldSize,item.map);w,h=S.number(w),S.number(h)
        if w and h then east,up=(item.x-player.x)*w,(player.y-item.y)*h end
    end
    if not east or not up then return nil end
    if facing then
        local cosine,sine=math.cos(facing),math.sin(facing)
        east,up=east*cosine+up*sine,-east*sine+up*cosine
    end
    local square=S.stringCall(GetMinimapShape)=="SQUARE"
    local x,y=east/radius,up/radius
    if (square and (math.abs(x)>1 or math.abs(y)>1)) or (not square and x*x+y*y>1) then return nil end
    return x*(width/2-7),y*(height/2-7)
end
local function tooltip(self)
    if not GameTooltip or not self.item then return end
    local item=self.item
    GameTooltip:SetOwner(self,"ANCHOR_RIGHT")
    GameTooltip:SetText((item.name:match("^[^-]+") or item.name):gsub("|","||"))
    local info=C_Map and S.call(C_Map.GetMapInfo,item.map)
    local name=type(info)=="table" and S.string(info.name)
    GameTooltip:AddLine((name and name:gsub("|","||").." · " or "")..string.format("%.1f, %.1f",item.x*100,item.y*100),1,1,1)
    GameTooltip:AddLine(TF("Position received %d sec ago",math.max(0,math.floor(S.uptime()-item.received))),1,.82,0)
    GameTooltip:Show()
end
local function pin(parent,pool,index)
    local button=pool[index]
    if not button then
        button=CreateFrame("Button",nil,parent);button:SetSize(16,16)
        button.icon=button:CreateTexture(nil,"ARTWORK");button.icon:SetAllPoints()
        button.icon:SetTexture(WoWStatusUI.ONLINE_ICON)
        button:SetScript("OnEnter",tooltip);button:SetScript("OnLeave",function() if GameTooltip then GameTooltip:Hide() end end)
        button:SetScript("OnClick",function(self) if self.item then L.show(self.item.name) end end)
        pool[index]=button
    end
    button:SetParent(parent)
    return button
end
local DIAMETERS={outdoor={466+2/3,400,333+1/3,266+2/3,200,133+1/3},indoor={300,240,180,120,80,50}}
function L.renderPins()
    local list=L.entries()
    if #list==0 then
        for _,p in ipairs(worldPins) do p:Hide() end;for _,p in ipairs(miniPins) do p:Hide() end
        L.worldPins,L.miniPins=worldPins,miniPins;return
    end
    local frame=WorldMapFrame
    local visible=frame and S.call(frame.IsShown,frame)
    local canvas=visible and (S.call(frame.GetCanvasContainer,frame) or (frame.ScrollContainer and frame.ScrollContainer.Child))
    local map=visible and S.number(S.call(frame.GetMapID,frame))
    local width,height=canvas and S.number(S.call(canvas.GetWidth,canvas)),canvas and S.number(S.call(canvas.GetHeight,canvas))
    local count=0
    if canvas and map and width and height and width>0 and height>0 then
        for _,item in ipairs(list) do
            local x,y=L.project(item,map)
            if x and y then
                count=count+1;local p=pin(canvas,worldPins,count);p.item=item
                p:ClearAllPoints();p:SetPoint("CENTER",canvas,"TOPLEFT",x*width,-y*height)
                p:SetFrameLevel((S.number(S.call(canvas.GetFrameLevel,canvas)) or 1)+30)
                p:SetAlpha(S.uptime()-item.received>15 and .55 or 1);p:Show()
            end
        end
    end
    for i=count+1,#worldPins do worldPins[i]:Hide() end
    count=0
    local mini=Minimap
    if mini and S.call(mini.IsShown,mini)~=false then
        local player=L.capture()
        local radius=C_Minimap and S.number(S.call(C_Minimap.GetViewRadius))
        if not radius then
            local zoom=integer(S.call(mini.GetZoom,mini),0,5)
            local outside=tonumber(S.stringCall((C_CVar and C_CVar.GetCVar) or GetCVar,"minimapZoom"))
            if zoom then radius=DIAMETERS[outside==zoom and "outdoor" or "indoor"][zoom+1]/2 end
        end
        local facing
        local rotate=S.stringCall((C_CVar and C_CVar.GetCVar) or GetCVar,"rotateMinimap")=="1"
        if rotate then facing=S.number(S.call(GetPlayerFacing)) end
        local w,h=S.number(S.call(mini.GetWidth,mini)),S.number(S.call(mini.GetHeight,mini))
        if not rotate or facing then
            for _,item in ipairs(list) do
                local x,y=L.minimapOffset(item,player,radius,w,h,facing)
                if x and y then
                    count=count+1;local p=pin(mini,miniPins,count);p.item=item
                    p:ClearAllPoints();p:SetPoint("CENTER",mini,"CENTER",x,y)
                    p:SetFrameLevel((S.number(S.call(mini.GetFrameLevel,mini)) or 1)+30)
                    p:SetAlpha(S.uptime()-item.received>15 and .55 or 1);p:Show()
                end
            end
        end
    end
    for i=count+1,#miniPins do miniPins[i]:Hide() end
    L.worldPins,L.miniPins=worldPins,miniPins
end
local function openMap(item)
    if not WorldMapFrame then S.call((C_AddOns and C_AddOns.LoadAddOn) or LoadAddOn,"Blizzard_WorldMap") end
    if not WorldMapFrame or type(WorldMapFrame.SetMapID)~="function" then return false end
    local ok=pcall(WorldMapFrame.SetMapID,WorldMapFrame,item.map)
    if not ok then return false end
    if window then window:Hide() end
    if WoWStatusMainWindow then WoWStatusMainWindow.hide() end
    WorldMapFrame:Show();L.renderPins();return true
end
-- Find the nearest shared zone/continent/world instead of showing only the
-- first friend's zone. Walk bounded, public map-parent chains without cycles.
function L.commonMap(list)
    local function ancestors(map)
        local chain,seen={},{}
        for _=1,16 do
            if not map or seen[map] then break end
            chain[#chain+1]=map;seen[map]=true
            local info=C_Map and S.call(C_Map.GetMapInfo,map)
            map=type(info)=="table" and integer(info.parentMapID,1,1000000) or nil
        end
        return chain
    end
    if #list==0 then return nil end
    local chain=ancestors(list[1].map)
    local shared={};for _,id in ipairs(chain) do shared[id]=true end
    for i=2,#list do
        local found={};for _,id in ipairs(ancestors(list[i].map)) do found[id]=true end
        for id in pairs(shared) do if not found[id] then shared[id]=nil end end
    end
    for _,id in ipairs(chain) do if shared[id] then return id end end
end
function L.showAll()
    local list=L.entries()
    local map=L.commonMap(list)
    if map and openMap({map=map}) then return true end
    local frame=L.show()
    if #list>0 then frame.note:SetText(T("The world map is not available right now.")) end
    return false
end
function L.renderList()
    if not window or not window:IsShown() then return end
    local list=L.entries()
    for i,item in ipairs(list) do
        local row=window.rows[i]
        if not row then
            row=CreateFrame("Button",nil,window.list,"UIPanelButtonTemplate");row:SetSize(480,40)
            row:SetScript("OnClick",function(self)
                if self.item and not openMap(self.item) then window.note:SetText(T("The world map is not available right now.")) end
            end)
            row:SetScript("OnEnter",tooltip);row:SetScript("OnLeave",function() if GameTooltip then GameTooltip:Hide() end end)
            window.rows[i]=row
        end
        row.item=item;row:ClearAllPoints();row:SetPoint("TOPLEFT",0,-(i-1)*46)
        WoWStatusUI.buttonLabel(row,(item.name:match("^[^-]+") or item.name):gsub("|","||")
            .." · "..TF("%d sec ago",math.max(0,math.floor(S.uptime()-item.received))))
        row:Show()
    end
    for i=#list+1,#window.rows do window.rows[i]:Hide() end
    window.list:SetHeight(math.max(1,#list*46));window.empty:SetShown(#list==0)
    window.all:SetEnabled(#list>0)
end
function L.show(name)
    if not window then
        local UI=WoWStatusUI
        window=UI.box(UIParent,550,470,nil,"WoWStatusMapFriends")
        window:SetPoint("CENTER");window:SetFrameStrata("FULLSCREEN_DIALOG");window:EnableMouse(true)
        UI.header(window,T("Friends on the map"),20,-20,500)
        window.note=UI.text(window,"GameFontHighlightSmall",20,-52,500)
        window.note:SetText(T("Reported positions expire when updates stop. Select a friend to open their map."));window.note:SetHeight(32)
        window.scroll=CreateFrame("ScrollFrame",nil,window,"UIPanelScrollFrameTemplate")
        window.scroll:SetPoint("TOPLEFT",20,-94);window.scroll:SetSize(490,310)
        window.list=CreateFrame("Frame",nil,window.scroll);window.list:SetSize(480,1);window.scroll:SetScrollChild(window.list)
        window.empty=UI.text(window,"GameFontHighlight",20,-100,480)
        window.empty:SetText(T("No recent positions. Friends need the updated addon and Location enabled."))
        window.close=CreateFrame("Button",nil,window,"UIPanelButtonTemplate")
        window.close:SetPoint("BOTTOMRIGHT",-20,16);window.close:SetSize(120,28);window.close:SetText(T("Close"))
        window.close:SetScript("OnClick",function() window:Hide() end)
        window.all=CreateFrame("Button",nil,window,"UIPanelButtonTemplate")
        window.all:SetPoint("BOTTOMLEFT",20,16);window.all:SetSize(260,28)
        window.all:SetText(T("Show everyone on map"));window.all:SetScript("OnClick",L.showAll)
        window.rows={};table.insert(UISpecialFrames,"WoWStatusMapFriends")
    end
    window:Show();if window.Raise then window:Raise() end;L.renderList()
    if name then for i,row in ipairs(window.rows) do if row.item and key(row.item.name)==key(name) then window.scroll:SetVerticalScroll((i-1)*46);break end end end
    return window
end
function L.tick()
    if not db or S.uptime()-lastTick<1 then return end
    lastTick=S.uptime()
    if WoWStatusGuide and WoWStatusGuide.touring() then return end
    if WoWStatusRoster.equipmentQueueSize()>=24 then return end
    local peers=recipients()
    if #peers==0 then return end
    local own=allowed() and L.capture()
    local name=WoWStatusPopups.characterName(current)
    if not S.string(name) or #name>64 then return end
    for offset=1,#peers do
        local index=(cursor+offset-1)%#peers+1
        local peer=peers[index]
        local last=lastFor[peer.id]
        local compatible=L.canMap(peer.group,peer.peer)
        if (compatible and own and (not last or S.uptime()-last>=5)) or (not own and last) then
            local text=own and table.concat({"L",peer.group,db.roster.id,name:gsub(" ","_"),own.at,own.map,
                math.floor(own.x*10000+.5),math.floor(own.y*10000+.5)}," ")
                or table.concat({"L",peer.group,db.roster.id,"-"}," ")
            if send(peer.group,peer.peer,text,own and "zone" or nil,own and current or nil,"position") then
                lastFor[peer.id]=own and S.uptime() or nil;trim(lastFor,256);cursor=index
            end
            break
        end
    end
end
function L.init(database,character,transport)
    db,current,send=database,character,transport
    reports,lastFor={},{};capabilities,helloAt={},{};lastTick,cursor=0,0;peerCache,peerCacheAt={},-5
    for _,p in ipairs(worldPins) do p:Hide() end;for _,p in ipairs(miniPins) do p:Hide() end
end
local driver=CreateFrame("Frame")
local elapsed=0
driver:SetScript("OnUpdate",function(_,delta)
    elapsed=elapsed+delta;if elapsed<.25 then return end;elapsed=0
    if db then L.renderPins();L.renderList() end
end)
