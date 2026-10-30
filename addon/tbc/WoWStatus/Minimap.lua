-- Native minimap button; no external library or companion is required.
WoWStatusMinimap = {}
local M,button,db=WoWStatusMinimap
local S=WoWStatusSafe
function M.init(database)
    db=database
    if button or not Minimap then return end
    button=CreateFrame("Button","WoWStatusMinimapButton",Minimap)
    button:SetSize(32,32);button:SetFrameStrata("MEDIUM");button:EnableMouse(true)
    local icon=button:CreateTexture(nil,"ARTWORK");icon:SetPoint("CENTER",-1,1);icon:SetSize(21,21)
    button.icon=icon
    icon:SetTexture("Interface\\Icons\\INV_Misc_Book_09")
    local border=button:CreateTexture(nil,"OVERLAY");border:SetPoint("TOPLEFT");border:SetSize(54,54)
    border:SetTexture("Interface\\Minimap\\MiniMap-TrackingBorder")
    local function place()
        local angle=math.rad(S.number(db.minimap_angle) or 225)
        button:ClearAllPoints();button:SetPoint("CENTER",Minimap,"CENTER",math.cos(angle)*80,math.sin(angle)*80)
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
            GameTooltip:AddLine("Left-click: Activity log",1,1,1)
            GameTooltip:AddLine("Right-click: Options",1,1,1)
            GameTooltip:AddLine("Drag to move",.7,.7,.7);GameTooltip:Show()
        end
    end)
    button:SetScript("OnLeave",function() if GameTooltip then GameTooltip:Hide() end end)
    place();button:Show()
end
