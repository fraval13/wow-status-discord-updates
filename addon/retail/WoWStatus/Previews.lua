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
local T = WoWStatusLocale.T
local function text(parent, value, x, y, width)
    local label = parent:CreateFontString(nil, "OVERLAY", "GameFontHighlightLarge")
    label:SetPoint("TOPLEFT",x,y); label:SetWidth(width or 550); label:SetJustifyH("LEFT"); label:SetText(T(value))
    return label
end
local function button(parent, value, x, y, width, fn)
    local widget=CreateFrame("Button",nil,parent,"UIPanelButtonTemplate")
    widget:SetPoint("TOPLEFT",x,y); widget:SetSize(width,30); widget:SetText(T(value)); widget:SetScript("OnClick",fn)
    return widget
end
local function background(frame)
    local texture=frame:CreateTexture(nil,"BACKGROUND")
    texture:SetAllPoints(); texture:SetColorTexture(.025,.035,.055,.96)
    if WoWStatusTheme and WoWStatusTheme.attachBackground then WoWStatusTheme.attachBackground(texture) end
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
        -- Settings first; below a line, the previews.
        local options = 150
        local previews = options + 760
        local footer = previews + 96 + #visible * 42
        panel:SetSize(600,footer+60); panel:EnableMouse(true); panel.background=background(panel)
        text(panel,"Notifications",24,-20)
        panel.guide=button(panel,"Setup guide",24,-96,170,function() WoWStatusGuide.show() end)
        panel.tour=button(panel,"Show me around",210,-96,170,function() WoWStatusGuide.tour() end)
        panel.divider=panel:CreateTexture(nil,"ARTWORK")
        panel.divider:SetPoint("TOPLEFT",24,-previews);panel.divider:SetSize(540,1);panel.divider:SetColorTexture(.82,.68,.32,.6)
        text(panel,"Previews",24,-previews-16)
        text(panel,"Choose a notification to preview it.",24,-previews-48)
        panel.buttons={}
        for i, entry in ipairs(visible) do
            local kind=entry[1]
            panel.buttons[kind]=button(panel,kind=="pvp" and A.pvpLabel or entry[2],24,-previews-88-(i-1)*42,360,function() WoWStatusPopups.preview(kind) end)
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
        -- Window theme and size (#60). Account-wide, applied at once.
        panel.theme=text(panel,WoWStatusTheme.label(),24,-options-262,300)
        local function refreshTheme() panel.theme:SetText(WoWStatusTheme.label()) end
        panel.themeNext=button(panel,"Next theme",330,-options-256,120,function() WoWStatusTheme.next();refreshTheme() end)
        panel.smaller=button(panel,"Smaller",460,-options-256,50,function() WoWStatusTheme.resize(-WoWStatusTheme.STEP);refreshTheme() end)
        panel.larger=button(panel,"Larger",514,-options-256,50,function() WoWStatusTheme.resize(WoWStatusTheme.STEP);refreshTheme() end)
        panel.themePopups=check("Use the theme and size for popups too",-options-298,function() return WoWStatusTheme.settings().popups end,
            WoWStatusTheme.setPopups)
        -- Notification size in percent (complaints that toasts were too big or small).
        text(panel,("Notification size (%d–%d%%)"):format(WoWStatusTheme.POPUP_MIN,WoWStatusTheme.POPUP_MAX),24,-options-346,250)
        panel.popupSize=CreateFrame("EditBox",nil,panel,"InputBoxTemplate")
        panel.popupSize:SetPoint("TOPLEFT",290,-options-340);panel.popupSize:SetSize(60,30)
        panel.popupSize:SetAutoFocus(false);panel.popupSize:SetMaxLetters(3)
        if panel.popupSize.SetNumeric then panel.popupSize:SetNumeric(true) end
        text(panel,"%",354,-options-346,20)
        local function applySize()
            local ok=WoWStatusTheme.setPopupSize(panel.popupSize:GetText())
            panel.popupSize:SetText(tostring(WoWStatusTheme.popupSize()))
            panel.popupSize:ClearFocus()
            -- A sample at the new size; an out-of-range value keeps the old one.
            if ok then WoWStatusPopups.preview("level") end
        end
        panel.popupSize:SetScript("OnEnterPressed",applySize)
        panel.popupSize:SetScript("OnEscapePressed",function(self) self:SetText(tostring(WoWStatusTheme.popupSize()));self:ClearFocus() end)
        panel.popupSizeApply=button(panel,"Apply",380,-options-340,90,applySize)
        -- Language (optional Nynorsk). Built windows change after a reload.
        panel.language=text(panel,"",24,-options-390,250)
        panel.languageSwitch=button(panel,"",290,-options-384,150,function()
            WoWStatusLocale.set(WoWStatusLocale.lang()=="nn" and "en" or "nn")
            panel.refreshLanguage()
            panel.reload:Show()
        end)
        panel.reload=button(panel,"",450,-options-384,130,function() if ReloadUI then ReloadUI() end end)
        panel.reload:Hide()
        -- Quiet mode: notifications wait in the instances ticked (off by default).
        panel.quiet=check("Quiet mode: hold notifications in",-options-474,function() return WoWStatusPopups.quietSettings().enabled end,
            function(value) WoWStatusPopups.setQuiet("enabled",value) end)
        -- Sounds, one per kind of notification; picking one plays it.
        text(panel,"Sounds",24,-options-556,300)
        panel.sounds={}
        for i,entry in ipairs(WoWStatusPopups.SOUND_KINDS) do
            local kind,y=entry[1],-options-590-(i-1)*34
            text(panel,entry[2],44,y-4,200)
            local widget=button(panel,"",250,y,200,function(self)
                local items={}
                for _,sound in ipairs(WoWStatusPopups.SOUNDS) do items[#items+1]={label=WoWStatusLocale.T(sound[1]),value=sound[2]} end
                WoWStatusUI.menu(self,items,function(id)
                    WoWStatusPopups.setSound(kind,id);WoWStatusPopups.playSound(id)
                    self:SetText(WoWStatusLocale.T(WoWStatusPopups.soundName(id)))
                end)
            end)
            widget.kind=kind
            panel.sounds[kind]=widget
        end
        panel.quietKinds={}
        for i,entry in ipairs({{"pvp","Battlegrounds"},{"raid","Raids"},{"party","Dungeons"}}) do
            local key=entry[1]
            local widget=check(entry[2],-options-510,function() return WoWStatusPopups.quietSettings()[key] end,
                function(value) WoWStatusPopups.setQuiet(key,value) end)
            widget:ClearAllPoints();widget:SetPoint("TOPLEFT",54+(i-1)*170,-options-510)
            panel.quietKinds[key]=widget
        end
        -- The switch names its target in that language, so each reader finds it.
        function panel.refreshLanguage()
            local nn=WoWStatusLocale.lang()=="nn"
            panel.language:SetText(WoWStatusLocale.T("Language:").." "..WoWStatusLocale.LANGUAGES[WoWStatusLocale.lang()])
            panel.languageSwitch:SetText(nn and "Switch to English" or "Bytt til nynorsk")
            panel.reload:SetText(WoWStatusLocale.T("Reload to apply"))
        end
        -- Caption personality: the voice of the line under each notification.
        -- Account-wide; new notifications use it, saved ones keep their caption.
        panel.personality=text(panel,WoWStatusPersonalities.label(),24,-options-432,300)
        panel.personalityNext=button(panel,"Next personality",330,-options-426,180,function()
            WoWStatusPersonalities.next()
            panel.personality:SetText(WoWStatusPersonalities.label())
            WoWStatusPopups.preview("level")
        end)
        panel.close=button(panel,"Close",424,-footer,140,function() panel:Hide() end)
    end
    local options=WoWStatusPopups.options()
    for _,widget in ipairs({panel.unlock,panel.big}) do widget:SetChecked(widget.get(options)) end
    for _,widget in pairs(panel.line) do widget:SetChecked(widget.get()) end
    panel.themePopups:SetChecked(panel.themePopups.get())
    panel.quiet:SetChecked(panel.quiet.get() == true)
    for kind,widget in pairs(panel.sounds) do widget:SetText(WoWStatusLocale.T(WoWStatusPopups.soundName(WoWStatusPopups.sound(kind)))) end
    for _,widget in pairs(panel.quietKinds) do widget:SetChecked(widget.get() == true) end
    panel.popupSize:SetText(tostring(WoWStatusTheme.popupSize()))
    panel.refreshLanguage()
    panel.theme:SetText(WoWStatusTheme.label())
    panel.personality:SetText(WoWStatusPersonalities.label())
    panel:SetParent(host or UIParent); panel:ClearAllPoints(); panel:SetPoint(host and "TOPLEFT" or "CENTER")
    panel.close:SetShown(not host)
    panel.background:SetShown(not host)
    panel:SetFrameStrata(host and host:GetFrameStrata() or "FULLSCREEN_DIALOG")
    if host then panel:SetFrameLevel(host:GetFrameLevel()+1) end
    panel:Show()
end
