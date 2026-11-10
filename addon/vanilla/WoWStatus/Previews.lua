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
        -- Spoken reactions (Forever only) add their own rows below the sounds.
        local V = WoWStatusVoices
        local voiceRows = V and V.available() and 370 or 0
        local previews = options + 802 + voiceRows
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
        panel.quiet=check("Quiet mode: hold notifications in",-options-516,function() return WoWStatusPopups.quietSettings().enabled end,
            function(value) WoWStatusPopups.setQuiet("enabled",value) end)
        -- Sounds, one per kind of notification; picking one plays it.
        text(panel,"Sounds",24,-options-598,300)
        panel.sounds={}
        for i,entry in ipairs(WoWStatusPopups.SOUND_KINDS) do
            local kind,y=entry[1],-options-632-(i-1)*34
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
        -- Spoken reactions: friends' Nynorsk reactions read aloud (every one by
        -- default, or one per interval), and whether this player's own reactions
        -- always use a voiced line. WoW cannot download files, so the pack link is
        -- shown to copy.
        if voiceRows > 0 then
            local y=-options-800
            text(panel,"Spoken reactions",24,y,300)
            panel.voices=check("Read friends' reactions aloud",y-36,function() return V.enabled() end,V.setEnabled)
            -- The addon's own lines when it carries some, else one from the pack.
            panel.voiceTest=button(panel,"Play a sample",400,y-36,160,function() if not V.test() then V.simulate() end end)
            panel.voiceAlways=check("Always send a voiced reaction when one is available",y-76,
                function() return V.alwaysVoiced() end,V.setAlwaysVoiced)
            text(panel,"Minutes between spoken reactions:",24,y-124,300)
            panel.voiceInterval=button(panel,"",330,y-118,140,function(self)
                local items={}
                for _,minutes in ipairs(V.INTERVALS) do items[#items+1]={label=V.intervalLabel(minutes),value=minutes} end
                WoWStatusUI.menu(self,items,function(minutes) V.setInterval(minutes);panel.refreshSpoken() end)
            end)
            -- Which volume slider the voices follow; picking one plays a sample on it.
            text(panel,"Volume slider for voices:",24,y-164,300)
            panel.voiceChannel=button(panel,"",330,y-158,200,function(self)
                local items={}
                for _,entry in ipairs(V.CHANNELS) do items[#items+1]={label=V.channelLabel(entry[1]),value=entry[1]} end
                WoWStatusUI.menu(self,items,function(channel)
                    V.setChannel(channel);panel.refreshSpoken()
                    if not V.test() then V.simulate() end
                end)
            end)
            text(panel,"Only Nynorsk reactions are read aloud. Voices are AI-generated (Google Gemini).",24,y-204,540)
            panel.voicePack=text(panel,"",24,y-244,540)
            panel.voiceGet=text(panel,"Get the full voice pack: copy this link into your browser, unzip it into Interface/AddOns and restart WoW.",
                24,y-284,540)
            panel.voiceLink=CreateFrame("EditBox",nil,panel,"InputBoxTemplate")
            panel.voiceLink:SetPoint("TOPLEFT",30,y-332);panel.voiceLink:SetSize(530,30);panel.voiceLink:SetAutoFocus(false)
            local function selectLink(self)
                self:SetText(V.packURL() or "")
                WoWStatusUI.call(self,"HighlightText")
            end
            panel.voiceLink:SetScript("OnEditFocusGained",selectLink)
            panel.voiceLink:SetScript("OnMouseUp",function(self) self:SetFocus();selectLink(self) end)
            -- The link is for copying only; typing puts it back.
            panel.voiceLink:SetScript("OnTextChanged",function(self,typed) if typed then selectLink(self) end end)
            panel.voiceLink:SetScript("OnEscapePressed",function(self) self:ClearFocus() end)
            function panel.refreshSpoken()
                panel.voices:SetChecked(V.enabled())
                panel.voiceAlways:SetChecked(V.alwaysVoiced())
                panel.voiceInterval:SetText(V.intervalLabel())
                panel.voiceChannel:SetText(V.channelLabel())
                local version=V.packVersion()
                if V.bundled() then
                    panel.voicePack:SetText(WoWStatusLocale.T("Every voice comes with this download; no voice pack is needed."))
                else
                    panel.voicePack:SetText(version and WoWStatusLocale.F("Voice pack %d is installed.",version)
                        or WoWStatusLocale.T("Voice pack: not installed. Install it to hear friends' reactions read aloud."))
                end
                -- A build with every voice inside has no pack to fetch.
                panel.voiceGet:SetShown(not V.bundled());panel.voiceLink:SetShown(not V.bundled())
                panel.voiceLink:SetText(V.packURL() or "")
            end
        end
        panel.quietKinds={}
        for i,entry in ipairs({{"pvp","Battlegrounds"},{"raid","Raids"},{"party","Dungeons"}}) do
            local key=entry[1]
            local widget=check(entry[2],-options-552,function() return WoWStatusPopups.quietSettings()[key] end,
                function(value) WoWStatusPopups.setQuiet(key,value) end)
            widget:ClearAllPoints();widget:SetPoint("TOPLEFT",54+(i-1)*170,-options-552)
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
        -- Each is a dropdown listing every choice by name (WoWStatusUI.menu).
        local P=WoWStatusPersonalities
        local function choices(ids)
            local items={}
            for _,id in ipairs(ids) do items[#items+1]={label=P.name(id),value=id} end
            return items
        end
        text(panel,"Caption personality:",24,-options-432,300)
        panel.personalityPick=button(panel,"",330,-options-426,230,function(self)
            WoWStatusUI.menu(self,choices(P.order),function(id)
                P.set(id);panel.refreshVoices()
                WoWStatusPopups.preview("level")
            end)
        end)
        -- Reaction voice: how the GZ!/F/Congrats! whispers to friends sound. Its own
        -- setting (Wholesome by default), since these are sent in your name.
        text(panel,"Reaction voice:",24,-options-474,300)
        panel.reactionVoicePick=button(panel,"",330,-options-468,230,function(self)
            WoWStatusUI.menu(self,choices(P.reactionVoices()),function(id)
                P.setReaction(id);panel.refreshVoices()
            end)
        end)
        function panel.refreshVoices()
            panel.personalityPick:SetText(P.name(P.current()))
            panel.reactionVoicePick:SetText(P.name(P.reactionVoice()))
        end
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
    panel.refreshVoices()
    if panel.refreshSpoken then panel.refreshSpoken() end
    panel:SetParent(host or UIParent); panel:ClearAllPoints(); panel:SetPoint(host and "TOPLEFT" or "CENTER")
    panel.close:SetShown(not host)
    panel.background:SetShown(not host)
    panel:SetFrameStrata(host and host:GetFrameStrata() or "FULLSCREEN_DIALOG")
    if host then panel:SetFrameLevel(host:GetFrameLevel()+1) end
    panel:Show()
end
