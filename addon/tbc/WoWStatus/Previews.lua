-- Local-only samples. Previewing never queues progress or sends a chat message.
WoWStatusPreviews = {}
local P,A = WoWStatusPreviews,WoWStatusAdapter
local panel, card
local examples = {
    {"level", "Level up"},
    {"introduction", "Joined the WoW Status group"}, {"loot", "First armor equip"},
    {"death", "Death"}, {"zone", "New location"},
    {"quest", "100 quests achievement"}, {"profession_learned", "Learn a profession"}, {"profession", "Profession title promotion"},
    {"dungeon", "First dungeon clear"}, {"mount", "First mount"},
    {"reputation", "Reputation promotion"}, {"unlock", "Major class unlock"},
    {"pvp", "PvP rank promotion"},
}
local function text(parent, value, x, y, width)
    local label = parent:CreateFontString(nil, "OVERLAY", "GameFontHighlightLarge")
    label:SetPoint("TOPLEFT",x,y); label:SetWidth(width or 550); label:SetJustifyH("LEFT"); label:SetText(value)
    return label
end
local function button(parent, value, x, y, width, fn)
    local widget=CreateFrame("Button",nil,parent,"UIPanelButtonTemplate")
    widget:SetPoint("TOPLEFT",x,y); widget:SetSize(width,30); widget:SetText(value); widget:SetScript("OnClick",fn)
    return widget
end
local function background(frame)
    local texture=frame:CreateTexture(nil,"BACKGROUND")
    texture:SetAllPoints(); texture:SetColorTexture(.025,.035,.055,.96)
    return texture
end
function P.statusCard()
    if not card then
        card=CreateFrame("Frame","WoWStatusStatusPreview",UIParent)
        card:SetSize(600,510); card:SetPoint("CENTER"); card:SetFrameStrata("FULLSCREEN_DIALOG"); card:EnableMouse(true)
        background(card)
        local icon=card:CreateTexture(nil,"ARTWORK")
        icon:SetPoint("TOPLEFT",24,-20); icon:SetSize(54,54)
        icon:SetTexture("Interface\\Icons\\Spell_Shadow_CurseOfTongues")
        text(card,"PREVIEW — example character",96,-24,470)
        text(card,"Previewlock · level 33 Warlock",96,-50,470)
        card.body=text(card,"Player: Alex (example)\nRace: Human · Male\nFaction: Alliance\nLevel: 33\nXP progress: 37.5% (15,000 / 40,000)\nTotal deaths: 15\nCompleted quests: 236\nLocation: Stranglethorn Vale\nTailoring: 185 / 225\nEnchanting: 150 / 225\n\nExample values only. Death totals are tracked from installation;\nolder deaths are unavailable on Classic Era.",24,-104,550)
        button(card,"Close",424,-462,140,function() card:Hide() end)
        table.insert(UISpecialFrames,"WoWStatusStatusPreview")
    end
    card:Show()
end
function P.show(host)
    if not panel then
        panel=CreateFrame("Frame","WoWStatusNotificationPreviews",UIParent)
        local visible={}
        for _,entry in ipairs(examples) do
            if entry[1]~="profession" or A.classicProfessionTitles~=false then table.insert(visible,entry) end
        end
        local options = 150 + #visible * 42
        local footer = options + 330
        panel:SetSize(600,footer+60); panel:EnableMouse(true); panel.background=background(panel)
        text(panel,"Notification previews",24,-20)
        text(panel,"Choose a notification to preview it.",24,-60)
        panel.guide=button(panel,"Setup guide",24,-96,170,function() WoWStatusGuide.show() end)
        panel.tour=button(panel,"Show me around",210,-96,170,function() WoWStatusGuide.tour() end)
        panel.buttons={}
        for i, entry in ipairs(visible) do
            local kind=entry[1]
            panel.buttons[kind]=button(panel,kind=="pvp" and A.pvpLabel or entry[2],24,-148-(i-1)*42,360,function() WoWStatusPopups.preview(kind) end)
        end
        -- Popup placement and big banners (#61). Account-wide.
        local function check(title,y,get,set)
            local widget=CreateFrame("CheckButton",nil,panel,"UICheckButtonTemplate")
            widget:SetPoint("TOPLEFT",24,y);widget:SetSize(32,32)
            text(widget,title,38,-6,460)
            widget:SetScript("OnClick",function(self) set(self:GetChecked() and true or false) end)
            widget.get=get
            return widget
        end
        panel.unlock=check("Unlock popup position",-options,function(o) return o.unlocked end,WoWStatusPopups.setUnlocked)
        panel.reset=button(panel,"Reset popup position",310,-options,250,function() WoWStatusPopups.resetPosition() end)
        panel.big=check("Big banners for big moments",-options-42,function(o) return o.big_banners end,WoWStatusPopups.setBigBanners)
        -- Group status line (#62). Account-wide.
        panel.line={}
        for i,entry in ipairs({{"enabled","Show the group status line"},{"attach","Attach it under the quest tracker"},
            {"hide_combat","Hide the status line in combat"},{"hide_instance","Hide the status line in dungeons and raids"}}) do
            local key=entry[1]
            panel.line[key]=check(entry[2],-options-84-(i-1)*42,function() return WoWStatusStatusLine.settings()[key] end,
                function(value) WoWStatusStatusLine.set(key,value) end)
        end
        panel.close=button(panel,"Close",424,-footer,140,function() panel:Hide() end)
    end
    local options=WoWStatusPopups.options()
    for _,widget in ipairs({panel.unlock,panel.big}) do widget:SetChecked(widget.get(options)) end
    for _,widget in pairs(panel.line) do widget:SetChecked(widget.get()) end
    panel:SetParent(host or UIParent); panel:ClearAllPoints(); panel:SetPoint(host and "TOPLEFT" or "CENTER")
    panel.close:SetShown(not host)
    panel.background:SetShown(not host)
    panel:SetFrameStrata(host and host:GetFrameStrata() or "FULLSCREEN_DIALOG")
    if host then panel:SetFrameLevel(host:GetFrameLevel()+1) end
    panel:Show()
end
