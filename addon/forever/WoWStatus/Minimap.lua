-- Native minimap button; no external library or companion is required.
WoWStatusMinimap = {}
local M,button,db=WoWStatusMinimap
local S=WoWStatusSafe
local place
M.MIN_OFFSET,M.MAX_OFFSET=-40,80
-- Extra distance from the map's edge. Players can adjust it with
-- /wstatus minimap <number> where a client reports an unexpected map size (#85).
local function offset(default)
    local value=S.number(db and db.minimap_offset)
    if value and value>=M.MIN_OFFSET and value<=M.MAX_OFFSET then return value end
    return default
end
local function size(frame)
    if type(frame)~="table" or not frame.GetWidth then return nil end
    local width,height=S.number(S.call(frame.GetWidth,frame)),S.number(S.call(frame.GetHeight,frame))
    local scale=frame.GetEffectiveScale and S.number(S.call(frame.GetEffectiveScale,frame))
    return width,height,scale
end
-- One chat line with what is needed to diagnose a misplaced button.
function M.report()
    local function text(name,frame)
        local width,height,scale=size(frame)
        if not width then return name.."=missing" end
        return string.format("%s=%.0fx%.0f@%.2f",name,width,height or 0,scale or 0)
    end
    return WoWStatusAdapter.client_id.." · "..text("Minimap",Minimap).." · "..text("MinimapCluster",MinimapCluster)
        .." · "..text("MinimapBackdrop",MinimapBackdrop).." · "..text("MinimapCompassTexture",MinimapCompassTexture)
        .." · offset="..tostring(S.number(db and db.minimap_offset) or "default")
        .." · angle="..tostring(S.number(db and db.minimap_angle) or 225)
end
function M.setOffset(value)
    if not db then return false end
    if value==nil then db.minimap_offset=nil
    else
        value=S.number(value)
        if not value or value~=math.floor(value) or value<M.MIN_OFFSET or value>M.MAX_OFFSET then return false end
        db.minimap_offset=value
    end
    if place then place() end
    return true
end
function M.init(database)
    db=database
    if button or not Minimap then return end
    button=CreateFrame("Button","WoWStatusMinimapButton",Minimap)
    button:SetSize(32,32);button:SetFrameStrata("MEDIUM");button:EnableMouse(true)
    local icon=button:CreateTexture(nil,"ARTWORK");icon:SetPoint("CENTER",-1,1);icon:SetSize(21,21)
    button.icon=icon
    icon:SetTexture("Interface\\AddOns\\WoWStatus\\Textures\\Logo")
    local border=button:CreateTexture(nil,"OVERLAY");border:SetPoint("TOPLEFT");border:SetSize(54,54)
    border:SetTexture("Interface\\Minimap\\MiniMap-TrackingBorder")
    place=function()
        local angle=math.rad(S.number(db.minimap_angle) or 225)
        local radiusX,radiusY=70+offset(10),70+offset(10)
        if WoWStatusAdapter.client_id=="retail" or WoWStatusAdapter.client_id=="forever" then
            -- Mainline minimaps are larger than Classic's. Work in the map's
            -- own coordinates so inherited UI/Edit Mode scaling stays correct.
            local width=S.number(S.call(Minimap.GetWidth,Minimap))
            local height=S.number(S.call(Minimap.GetHeight,Minimap))
            if width and height and width>0 and height>0 then
                radiusX,radiusY=width/2+offset(10),height/2+offset(10)
            end
        end
        button:ClearAllPoints();button:SetPoint("CENTER",Minimap,"CENTER",math.cos(angle)*radiusX,math.sin(angle)*radiusY)
    end
    if Minimap.HookScript then
        pcall(Minimap.HookScript,Minimap,"OnSizeChanged",place)
        pcall(Minimap.HookScript,Minimap,"OnShow",place)
    end
    button:RegisterForClicks("LeftButtonUp","RightButtonUp")
    button:SetScript("OnClick",function(_,which)
        if which=="RightButton" then SlashCmdList.WOWSTATUS("") else WoWStatusJournal.show() end
    end)
    button:RegisterForDrag("LeftButton")
    button:SetScript("OnDragStart",function(self)
        self:SetScript("OnUpdate",function()
            local x,y=S.call(GetCursorPosition);local mx,my=S.call(Minimap.GetCenter,Minimap)
            x,y,mx,my=S.number(x),S.number(y),S.number(mx),S.number(my)
            local scale=S.number(S.call(Minimap.GetEffectiveScale,Minimap))
            if not x or not y or not mx or not my or not scale or scale<=0 then return end
            local dx,dy=x/scale-mx,y/scale-my
            db.minimap_angle=math.deg(math.atan2 and math.atan2(dy,dx) or math.atan(dy,dx));place()
        end)
    end)
    button:SetScript("OnDragStop",function(self) self:SetScript("OnUpdate",nil) end)
    button:SetScript("OnEnter",function(self)
        if GameTooltip then
            GameTooltip:SetOwner(self,"ANCHOR_LEFT");GameTooltip:SetText("WoW Status")
            local T=WoWStatusLocale.T
            -- Who is online, and the newest thing a friend did.
            local names=WoWStatusRoster and WoWStatusRoster.onlineNames and WoWStatusRoster.onlineNames() or {}
            local shown={}
            for i=1,math.min(#names,8) do shown[i]=names[i]:gsub("|","||") end
            local list=#names==0 and T("nobody") or (table.concat(shown,", ")..(#names>8 and (" +"..(#names-8)) or ""))
            GameTooltip:AddLine(T("Online now:").." "..list,.4,1,.4,true)
            local latest=WoWStatusJournal and WoWStatusJournal.latestFriend and WoWStatusJournal.latestFriend()
            if latest then
                local minutes=math.max(0,math.floor((time()-(latest.at or time()))/60))
                local when=minutes<60 and (minutes.." min") or minutes<1440 and (math.floor(minutes/60).." h") or (math.floor(minutes/1440).." d")
                local who=(latest.sender:match("^[^-]+") or latest.sender):gsub("|","||")
                GameTooltip:AddLine(T("Latest:").." "..who.." — "..WoWStatusJournal.deathText(latest):gsub("|","||").." · "..when,1,.82,0,true)
            end
            GameTooltip:AddLine(" ")
            GameTooltip:AddLine(T("Left-click: Activity log"),1,1,1)
            GameTooltip:AddLine(T("Right-click: Options"),1,1,1)
            GameTooltip:AddLine(T("Drag to move"),.7,.7,.7);GameTooltip:Show()
        end
    end)
    button:SetScript("OnLeave",function() if GameTooltip then GameTooltip:Hide() end end)
    place();button:Show()
end
