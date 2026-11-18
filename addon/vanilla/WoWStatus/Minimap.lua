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
-- Tooltip shared by the minimap button and the AddOn Compartment entry.
local function fillTooltip(tooltip,draggable)
    local T=WoWStatusLocale.T
    tooltip:SetText("WoW Status")
    -- Who is online, and the newest thing a friend did.
    local names=WoWStatusRoster and WoWStatusRoster.onlineNames and WoWStatusRoster.onlineNames() or {}
    local shown={}
    for i=1,math.min(#names,8) do shown[i]=names[i]:gsub("|","||") end
    local list=#names==0 and T("nobody") or (table.concat(shown,", ")..(#names>8 and (" +"..(#names-8)) or ""))
    tooltip:AddLine(T("Online now:").." "..list,.4,1,.4,true)
    local latest=WoWStatusJournal and WoWStatusJournal.latestFriend and WoWStatusJournal.latestFriend()
    if latest then
        local minutes=math.max(0,math.floor((S.now()-(latest.at or S.now()))/60))
        local when=minutes<60 and (minutes.." min") or minutes<1440 and (math.floor(minutes/60).." h") or (math.floor(minutes/1440).." d")
        local who=(latest.sender:match("^[^-]+") or latest.sender):gsub("|","||")
        tooltip:AddLine(T("Latest:").." "..who.." — "..WoWStatusJournal.deathText(latest):gsub("|","||").." · "..when,1,.82,0,true)
    end
    -- Quiet hours (#180): say so, so silence does not look like a fault.
    local quiet=WoWStatusPopups and WoWStatusPopups.quietHoursText and WoWStatusPopups.quietHoursText()
    if quiet then tooltip:AddLine(quiet,.6,.8,1,true) end
    tooltip:AddLine(" ")
    tooltip:AddLine(T("Left-click: Activity log"),1,1,1)
    tooltip:AddLine(T("Right-click: Options"),1,1,1)
    if draggable then tooltip:AddLine(T("Drag to move"),.7,.7,.7) end
end
-- Same actions as the minimap button: left opens the log, right the options.
-- Other mouse buttons do nothing, as on the button.
local function click(which)
    if which=="RightButton" then SlashCmdList.WOWSTATUS("")
    elseif which=="LeftButton" then WoWStatusJournal.show() end
end
-- The frame our tooltip was last shown on. Leaving hides the tooltip only while
-- that frame still owns it: moving to the next menu entry can hand GameTooltip
-- to that entry before our leave handler runs. Remembering the frame also
-- covers a leave call that passes no frame or a different one.
local tipOwner
local function showTooltip(owner,draggable)
    if not GameTooltip or not owner then return end
    GameTooltip:SetOwner(owner,"ANCHOR_LEFT");fillTooltip(GameTooltip,draggable);GameTooltip:Show()
    tipOwner=owner
end
local function hideTooltip()
    local owner=tipOwner;tipOwner=nil
    if not GameTooltip or not owner then return end
    if GameTooltip.GetOwner and GameTooltip:GetOwner()~=owner then return end
    GameTooltip:Hide()
end
-- The AddOn Compartment (the minimap's addon list on Retail and Forever) calls
-- these globals, named by the AddonCompartmentFunc* lines in the TOC (#161). Clients without a
-- compartment ignore those lines, so the globals are simply never called there.
-- Clients before 11.0 pass the mouse button as a string; the 11.0 menu passes a
-- table with buttonName.
function WoWStatus_OnAddonCompartmentClick(_,input)
    -- The entry exists from load, before the character is set up; the options
    -- command then says why nothing opens instead of failing silently.
    if not db then SlashCmdList.WOWSTATUS("") return end
    click(type(input)=="table" and input.buttonName or input)
end
function WoWStatus_OnAddonCompartmentEnter(_,owner) showTooltip(owner,false) end
function WoWStatus_OnAddonCompartmentLeave() hideTooltip() end
-- The button can be switched off (#177). Account-wide, and never a lock-out:
-- /wstatus and the key binding open the addon without it.
function M.visible()
    return not (db and db.minimap_hidden)
end
local function apply()
    if button and button.SetShown then button:SetShown(M.visible()) end
end
function M.setVisible(show)
    if not db then return false end
    db.minimap_hidden=(not show) or nil
    apply()
    return true
end
-- Named in the chat confirmation and under the tick, so nobody hides the
-- button and believes the addon is gone.
M.WAYS="Open it with /wstatus, or with the key binding under Key Bindings."
function M.init(database)
    db=database
    if button then apply(); return end
    if not Minimap then return end
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
    button:SetScript("OnClick",function(_,which) click(which) end)
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
    button:SetScript("OnEnter",function(self) showTooltip(self,true) end)
    button:SetScript("OnLeave",function() hideTooltip() end)
    place();button:Show();apply()
end
