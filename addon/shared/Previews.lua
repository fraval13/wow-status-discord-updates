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
        local previews = options + 964 + voiceRows
        local footer = previews + 96 + #visible * 42
        panel:SetSize(600,footer+60); panel:EnableMouse(true); panel.background=background(panel)
        text(panel,"Notifications",24,-20)
        panel.guide=button(panel,"Setup guide",24,-96,170,function() WoWStatusGuide.show() end)
        panel.tour=button(panel,"Show me around",210,-96,170,function() WoWStatusGuide.tour() end)
        -- Friends muted from their profile (#169), to check and unmute.
        panel.mutes=button(panel,"Muted friends",396,-96,170,function() WoWStatusMutes.show() end)
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
        -- The window size (#182) as a percentage to type, with - and + stepping 10 %.
        panel.windowSize=CreateFrame("EditBox",nil,panel,"InputBoxTemplate")
        -- A small line under the label when the screen shows the window smaller.
        panel.themeNote=panel:CreateFontString(nil,"OVERLAY","GameFontHighlightSmall")
        panel.themeNote:SetPoint("TOPLEFT",24,-options-282);panel.themeNote:SetWidth(300);panel.themeNote:SetJustifyH("LEFT")
        local function refreshTheme()
            panel.theme:SetText(T(WoWStatusTheme.label()))
            local note=WoWStatusTheme.shownNote()
            panel.themeNote:SetText(note and T(note) or "")
            if not panel.windowSize.typing then panel.windowSize:SetText(tostring(WoWStatusTheme.windowSize())) end
        end
        panel.refreshTheme=refreshTheme
        -- A resolution or UI scale change can change the note.
        WoWStatusTheme.watch(refreshTheme)
        -- A step applies what was typed first; a button click does not take focus.
        local function step(delta)
            panel.windowSize.typing=nil;panel.windowSize:ClearFocus()
            WoWStatusTheme.resize(delta);refreshTheme()
        end
        panel.themeNext=button(panel,"Next theme",330,-options-256,120,function() WoWStatusTheme.next();refreshTheme() end)
        panel.smaller=button(panel,"-",456,-options-256,26,function() step(-WoWStatusTheme.STEP) end)
        panel.windowSize:SetPoint("TOPLEFT",490,-options-256);panel.windowSize:SetSize(36,30)
        panel.windowSize:SetAutoFocus(false);panel.windowSize:SetMaxLetters(3)
        if panel.windowSize.SetNumeric then panel.windowSize:SetNumeric(true) end
        text(panel,"%",528,-options-262,14)
        -- Applied on Enter and whenever the box loses focus (a click elsewhere, or
        -- B on a controller, which has no Enter); out of range shows the old size.
        local function applyWindowSize()
            panel.windowSize.typing=nil
            if tonumber(panel.windowSize:GetText())~=WoWStatusTheme.windowSize() then
                WoWStatusTheme.setWindowSize(panel.windowSize:GetText())
            end
            refreshTheme()
        end
        panel.windowSize:SetScript("OnEditFocusGained",function(self) self.typing=true end)
        panel.windowSize:SetScript("OnEditFocusLost",applyWindowSize)
        -- Clearing focus applies it (OnEditFocusLost).
        panel.windowSize:SetScript("OnEnterPressed",function(self) self:ClearFocus() end)
        panel.windowSize:SetScript("OnEscapePressed",function(self) self:SetText(tostring(WoWStatusTheme.windowSize()));self:ClearFocus() end)
        panel.larger=button(panel,"+",544,-options-256,26,function() step(WoWStatusTheme.STEP) end)
        panel.themePopups=check("Use the theme and size for popups too",-options-298,function() return WoWStatusTheme.settings().popups end,
            WoWStatusTheme.setPopups)
        -- Notification size in percent (complaints that toasts were too big or small).
        text(panel,("Notification size (%d–%d%%)"):format(WoWStatusTheme.POPUP_MIN,WoWStatusTheme.POPUP_MAX),24,-options-346,250)
        -- A dropdown, so a controller can pick a size without typing.
        panel.popupSize=button(panel,"",290,-options-340,180,function(self)
            local items={}
            for _,percent in ipairs(WoWStatusTheme.POPUP_SIZES) do
                items[#items+1]={label=WoWStatusTheme.popupSizeLabel(percent),value=percent}
            end
            WoWStatusUI.menu(self,items,function(percent)
                -- A sample at the new size.
                if WoWStatusTheme.setPopupSize(percent) then WoWStatusPopups.sample("level") end
                self:SetText(WoWStatusTheme.popupSizeLabel())
            end)
        end)
        -- How long each notification stays (#159); a sample shows the new length.
        text(panel,"Notification duration:",24,-options-390,250)
        panel.popupDuration=button(panel,"",290,-options-384,180,function(self)
            local items={}
            for _,seconds in ipairs(WoWStatusPopups.DURATIONS) do
                items[#items+1]={label=WoWStatusPopups.durationLabel(seconds),value=seconds}
            end
            WoWStatusUI.menu(self,items,function(seconds)
                WoWStatusPopups.setDuration(seconds);self:SetText(WoWStatusPopups.durationLabel())
                WoWStatusPopups.sample("level")
            end)
        end)
        -- Language (optional Nynorsk). Built windows change after a reload.
        panel.language=text(panel,"",24,-options-432,250)
        panel.languageSwitch=button(panel,"",290,-options-426,150,function()
            WoWStatusLocale.set(WoWStatusLocale.lang()=="nn" and "en" or "nn")
            panel.refreshLanguage()
            panel.reload:Show()
        end)
        panel.reload=button(panel,"",450,-options-426,130,function() if ReloadUI then ReloadUI() end end)
        panel.reload:Hide()
        -- Quiet mode: notifications wait in the instances ticked (off by default).
        panel.quiet=check("Quiet mode: hold notifications in",-options-558,function() return WoWStatusPopups.quietSettings().enabled end,
            function(value) WoWStatusPopups.setQuiet("enabled",value) end)
        -- Quiet hours (#180): a daily window on the local clock, off by default.
        -- Earlier/Later move each end by half an hour, wrapping round midnight.
        panel.quietHours=check("Quiet hours: hide friends' notifications by the clock",-options-640,
            function() return WoWStatusPopups.quietHours().enabled end,
            function(value) WoWStatusPopups.setQuietHours("enabled",value);panel.refreshQuietHours() end)
        panel.quietClock={}
        for i,entry in ipairs({{"start","From"},{"stop","To"}}) do
            local key,y=entry[1],-options-676-(i-1)*38
            text(panel,entry[2],54,y-6,60)
            panel.quietClock[key]=text(panel,"",120,y-6,70)
            panel.quietClock[key.."Earlier"]=button(panel,"Earlier",200,y,90,function()
                WoWStatusPopups.shiftQuietHours(key,-1);panel.refreshQuietHours() end)
            panel.quietClock[key.."Later"]=button(panel,"Later",296,y,90,function()
                WoWStatusPopups.shiftQuietHours(key,1);panel.refreshQuietHours() end)
        end
        panel.quietState=panel:CreateFontString(nil,"OVERLAY","GameFontHighlightSmall")
        panel.quietState:SetPoint("TOPLEFT",400,-options-682);panel.quietState:SetWidth(170);panel.quietState:SetJustifyH("LEFT")
        -- The window can begin or end while the page is open: check once a second.
        local sinceQuietCheck=0
        panel:SetScript("OnUpdate",function(_,elapsed)
            sinceQuietCheck=sinceQuietCheck+(tonumber(elapsed) or 0)
            if sinceQuietCheck>=1 then sinceQuietCheck=0;panel.refreshQuietState() end
        end)
        function panel.refreshQuietState()
            local hours=WoWStatusPopups.quietHours()
            panel.quietState:SetText(WoWStatusPopups.quietHoursText()
                or (hours.enabled and hours.start==hours.stop and WoWStatusLocale.T("Same start and end: never quiet")) or "")
        end
        function panel.refreshQuietHours()
            local hours=WoWStatusPopups.quietHours()
            panel.quietHours:SetChecked(hours.enabled)
            panel.quietClock.start:SetText(WoWStatusPopups.clockText(hours.start))
            panel.quietClock.stop:SetText(WoWStatusPopups.clockText(hours.stop))
            panel.refreshQuietState()
            if WoWStatusStatusLine and WoWStatusStatusLine.update then WoWStatusStatusLine.update() end
        end
        -- Sounds, one per kind of notification; picking one plays it.
        text(panel,"Sounds",24,-options-760,300)
        panel.sounds={}
        for i,entry in ipairs(WoWStatusPopups.SOUND_KINDS) do
            local kind,y=entry[1],-options-794-(i-1)*34
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
            local y=-options-962
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
            local widget=check(entry[2],-options-594,function() return WoWStatusPopups.quietSettings()[key] end,
                function(value) WoWStatusPopups.setQuiet(key,value) end)
            widget:ClearAllPoints();widget:SetPoint("TOPLEFT",54+(i-1)*170,-options-594)
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
        text(panel,"Caption personality:",24,-options-474,300)
        panel.personalityPick=button(panel,"",330,-options-468,230,function(self)
            WoWStatusUI.menu(self,choices(P.order),function(id)
                P.set(id);panel.refreshVoices()
                WoWStatusPopups.sample("level")
            end)
        end)
        -- Reaction voice: how the GZ!/F/Congrats! whispers to friends sound. Its own
        -- setting (Wholesome by default), since these are sent in your name.
        text(panel,"Reaction voice:",24,-options-516,300)
        panel.reactionVoicePick=button(panel,"",330,-options-510,230,function(self)
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
    panel.refreshQuietHours()
    for kind,widget in pairs(panel.sounds) do widget:SetText(WoWStatusLocale.T(WoWStatusPopups.soundName(WoWStatusPopups.sound(kind)))) end
    for _,widget in pairs(panel.quietKinds) do widget:SetChecked(widget.get() == true) end
    panel.popupSize:SetText(WoWStatusTheme.popupSizeLabel())
    panel.popupDuration:SetText(WoWStatusPopups.durationLabel())
    panel.refreshLanguage()
    panel.windowSize.typing=nil
    panel.refreshTheme()
    panel.refreshVoices()
    if panel.refreshSpoken then panel.refreshSpoken() end
    panel:SetParent(host or UIParent); panel:ClearAllPoints(); panel:SetPoint(host and "TOPLEFT" or "CENTER")
    panel.close:SetShown(not host)
    panel.background:SetShown(not host)
    panel:SetFrameStrata(host and host:GetFrameStrata() or "FULLSCREEN_DIALOG")
    if host then panel:SetFrameLevel(host:GetFrameLevel()+1) end
    panel:Show()
end
