-- The Activity page of the main window: the log's cards, filters, search and
-- day picker. Part of WoWStatusJournal; see JournalStore.lua, which loads first.
local J, S, P = WoWStatusJournal, WoWStatusSafe, WoWStatusPopups
local T = WoWStatusLocale.T
local I = J.internal
local panel, refresh
-- The name the Activity log shows for an entry's sender (also the minimap tooltip's).
function J.displayName(e)
    return (not e.owner and not e.sample and WoWStatusRoster and WoWStatusRoster.displayName)
        and WoWStatusRoster.displayName(e.sender) or (e.sender:match("^[^-]+") or e.sender)
end
local function label(parent,font,x,y,width)
    local f=parent:CreateFontString(nil,"OVERLAY",font);f:SetPoint("TOPLEFT",x,y);f:SetWidth(width);f:SetJustifyH("LEFT");return f
end
-- One line; the game ends a text that does not fit with "..." (the card's
-- tooltip has it in full) instead of wrapping it.
local function oneLine(f)
    f:SetWordWrap(false)
    if f.SetNonSpaceWrap then f:SetNonSpaceWrap(false) end
    if f.SetMaxLines then f:SetMaxLines(1) end
    f.oneLine=true
    return f
end
-- The tour (#64) shows sample entries instead of the real log, display only.
function J.displayEntries()
    local samples=WoWStatusGuide and WoWStatusGuide.sampleEntries()
    return samples or J.entries()
end
-- Display-only rows marking where each of this account's characters on this
-- client began tracking, when that was after level 1.
local function trackingMarkers()
    local list={}
    for _, c in pairs(I.db.characters or {}) do
        local start=c.tracking_start
        if type(start)=="table" and S.number(start.level) and start.level>1 and S.number(start.at)
            and c.identity.client==WoWStatusAdapter.client_id and c.settings.enabled then
            list[#list+1]={id="tracking:"..c.identity.client..":"..c.identity.guid,client=c.identity.client,
                sender=P.characterName(c),owner=c.identity.guid,kind="tracking",
                at=start.at,text="Tracking started at level "..start.level,groups={},origin="mine"}
        end
    end
    return list
end
-- Type filter groups for the Activity page: label and the entry kinds it shows.
J.TYPES={
    {"Level-ups",{level=true}}, {"Deaths",{death=true}}, {"Zones",{zone=true}}, {"Quests",{quest=true}},
    {"Professions",{profession=true,professionprogress=true}}, {"Dungeons and raids",{dungeon=true,raid=true}},
    {"Mounts",{mount=true,epicmount=true}}, {"Armor",{loot=true,equipment=true}}, {"Reputation",{reputation=true}},
    {"Class abilities",{unlock=true}}, {"PvP",{pvp=true,battleground=true}}, {"Joins",{introduction=true}}, {"Recaps",{recap=true}},
}
-- Retail only (#165), right after PvP.
if WoWStatusAdapter.achievements then
    for i,t in ipairs(J.TYPES) do
        if t[2].pvp then table.insert(J.TYPES,i+1,{"Achievements",{achievement=true}});break end
    end
end
-- The day an entry belongs to, in the player's local time: "YYYY-MM-DD".
local dayCache=setmetatable({},{__mode="k"})
local function dayOf(e)
    local day=dayCache[e]
    if not day and S.number(e.at) then day=WoWStatusHistory.day(e.at);dayCache[e]=day end
    return day
end
local function today() return WoWStatusHistory.day(S.now()) end
local function yesterday() return WoWStatusHistory.day(S.now(),-1) end
-- The picked day: "today" (the default, so the log stays fresh), a day key, or
-- nil for all days. It lasts until the next /reload.
local function pickedDay()
    if panel.day=="today" then return today() end
    return panel.day
end
-- Accents a player is unlikely to type: folded to plain letters so "aerie" finds
-- "Ærie Peak" and "doden" finds "Døden". CaseFold.lua is not the place for this —
-- it is generated, and it also canonicalises group names, which must not change.
-- Applied after WoWStatusCaseFold, so only the lowercase forms are listed.
local PLAIN={
    ["\195\160"]="a",["\195\161"]="a",["\195\162"]="a",["\195\163"]="a",["\195\164"]="a",["\195\165"]="a",
    ["\195\166"]="ae",["\195\167"]="c",["\195\168"]="e",["\195\169"]="e",["\195\170"]="e",["\195\171"]="e",
    ["\195\172"]="i",["\195\173"]="i",["\195\174"]="i",["\195\175"]="i",["\195\176"]="d",["\195\177"]="n",
    ["\195\178"]="o",["\195\179"]="o",["\195\180"]="o",["\195\181"]="o",["\195\182"]="o",["\195\184"]="o",
    ["\195\185"]="u",["\195\186"]="u",["\195\187"]="u",["\195\188"]="u",["\195\189"]="y",["\195\191"]="y",
    ["\195\190"]="th",["\195\159"]="ss",["\197\147"]="oe",["\197\141"]="o",["\196\129"]="a",["\196\147"]="e",
    ["\196\171"]="i",["\197\171"]="u",["\197\161"]="s",["\197\190"]="z",["\197\130"]="l",["\196\135"]="c",
}
local function plain(text)
    return (text:gsub("[%z\1-\127\194-\244][\128-\191]*",function(char) return PLAIN[char] or char end))
end
-- Case and accents folded together; both sides of a comparison go through this.
local function fold(text) return plain(WoWStatusCaseFold(text)) end
-- Free-text search over the log (#175). The text is folded for case and accents,
-- so "aerie" finds "Aerie Peak" and "dod" finds "Døden". Cached per entry and
-- rebuilt when the entry's own text or its death details change.
local searchCache=setmetatable({},{__mode="k"})
local function searchText(e)
    local d=J.details(e)
    local key=table.concat({tostring(e.text),tostring(e.sender),tostring(d and d.zone),tostring(d and d.killer)},"\1")
    local cached=searchCache[e]
    if cached and cached.key==key then return cached.text end
    -- The card's own message (zone and killer included), the character's name and
    -- the player behind it, which is what the Person filter calls them.
    local who=(not e.owner and not e.sample and WoWStatusRoster and WoWStatusRoster.displayName)
        and WoWStatusRoster.displayName(e.sender) or nil
    local text=fold(table.concat({J.deathText(e),tostring(e.sender),who or ""}," "))
    searchCache[e]={key=key,text=text}
    return text
end
-- What the player typed, folded the same way; nil when the box is empty.
local function searchQuery()
    local query=panel and S.string(panel.search)
    return query and query~="" and fold(query) or nil
end
local function visibleEntries(allDays)
    local list={}
    local samples=WoWStatusGuide and WoWStatusGuide.sampleEntries()
    local kinds=panel.typeFilter and J.TYPES[panel.typeFilter] and J.TYPES[panel.typeFilter][2]
    local query=searchQuery()
    for _,e in ipairs(J.displayEntries()) do
        local wanted=(panel.filter=="all" or panel.filter=="character" or (panel.filter=="mine")==not not e.owner)
            and (not panel.character or P.senderKey(e.sender)==panel.character)
            and (not kinds or kinds[e.kind])
            and (not query or searchText(e):find(query,1,true)~=nil)
        if J.visible(e) and wanted then list[#list+1]=e end
    end
    if not samples and not query and not panel.character and not kinds and (panel.filter=="all" or panel.filter=="mine") then
        for _, marker in ipairs(trackingMarkers()) do list[#list+1]=marker end
        table.sort(list,function(a,b) if a.at==b.at then return a.id>b.id end return a.at>b.at end)
    end
    -- A search looks through the whole log: a day picker left on Today would hide
    -- the very entry the player is looking for.
    local day=not allDays and not samples and not query and pickedDay()
    if day then
        local kept={}
        for _,e in ipairs(list) do if dayOf(e)==day then kept[#kept+1]=e end end
        list=kept
    end
    return list
end
-- A friend's update whose notification appeared less than a minute ago, not
-- yet reacted to: its log card offers the same reaction buttons.
J.REACT_WINDOW=60
function J.canReact(e)
    local shown=type(e)=="table" and S.number(e.shown_at)
    return shown~=nil and shown~=false and not e.owner and not e.sample and not e.reacted
        and S.now()>=shown and S.now()-shown<J.REACT_WINDOW
end
local function rowReactions(row,e)
    row.reactions=row.reactions or {}
    for _,button in ipairs(row.reactions) do button:Hide() end
    local list=J.canReact(e) and P.reactions(e) or {}
    local widest=0
    for i,reaction in ipairs(list) do
        local button=row.reactions[i]
        if not button then
            button=CreateFrame("Button",nil,row,"UIPanelButtonTemplate")
            button:SetScript("OnClick",function(self)
                if self.entry and J.canReact(self.entry) then P.react(self.entry,self.reaction) end
                if refresh then refresh() end
            end)
            row.reactions[i]=button
        end
        local text=P.reactionLabel(e,reaction)
        button.entry,button.reaction=e,reaction
        button:SetText(text)
        local label=button.GetFontString and button:GetFontString()
        local measured=label and label.GetStringWidth and S.number(label:GetStringWidth())
        local width=math.min(300,math.max(86,math.max(measured or 0,#text*6)+24))
        widest=math.max(widest,width)
        button:SetSize(width,24);button:ClearAllPoints();button:SetPoint("TOPRIGHT",-10,-10-(i-1)*28);button:Show()
    end
    -- The heading and message make room for the buttons.
    local width=#list>0 and 570-widest-8 or 570
    row.heading:SetWidth(width);row.message:SetWidth(width)
    return #list>0
end
local function render()
    if not panel then return end
    local list=visibleEntries();panel.entriesList=list
    panel.export:SetEnabled(#list>0 and not list[1].sample)
    panel.reactUntil=nil
    panel.empty:SetShown(#list==0)
    local query=searchQuery()
    local day=pickedDay()
    panel.empty:SetText(query and T("Nothing in the log matches that.")
        or T(not day and "No activity yet" or day==today() and "Nothing yet today." or "No activity on this day."))
    -- A search reaches past the day picker, so the count says how wide it looked.
    panel.searchCount:SetText(query and WoWStatusLocale.F("%d matches in the whole log",#list) or "")
    WoWStatusUI.call(panel.searchClear,"SetEnabled",query~=nil)
    panel.dayButton:SetText(WoWStatusUI.dayLabel(day,today(),yesterday()))
    -- What the type and person filters show, with Show all to clear them.
    local parts={}
    if panel.typeFilter and J.TYPES[panel.typeFilter] then parts[#parts+1]=T(J.TYPES[panel.typeFilter][1]) end
    if panel.character then parts[#parts+1]=(panel.characterName or "?"):gsub("|","||") end
    if panel.search then parts[#parts+1]=T("Search:").." "..panel.search:gsub("|","||") end
    panel.showing:SetText(#parts>0 and (T("Showing:").." |cffffd100"..table.concat(parts," · ").."|r") or "")
    panel.showAll:SetShown(#parts>0)
    if WoWStatusReactions then panel.reactionsButton:SetText(WoWStatusReactions.buttonLabel()) end
    panel.typeButton:SetText(T("Type:").." "..(panel.typeFilter and T(J.TYPES[panel.typeFilter][1]) or T("All")))
    panel.personButton:SetText(T("Person:").." "..(panel.character and (panel.characterName or "?"):gsub("|","||") or T("All")))
    panel.child:SetHeight(math.max(360,#list*132))
    local first=math.floor(panel.scroll:GetVerticalScroll()/132)+1
    for slot,row in ipairs(panel.rows) do
        local i=first+slot-1;local e=list[i]
        if e then
            row:ClearAllPoints();row:SetPoint("TOPLEFT",0,-(i-1)*132)
            local texture,r,g,b,heading=WoWStatusPresentation.theme(e)
            row.icon:SetTexture(texture);row.accent:SetColorTexture(r,g,b,1);row.heading:SetTextColor(r,g,b)
            row.heading:SetText(T(heading))
            local who=J.displayName(e)
            local message, bgStats = e.text, nil
            if e.kind == "battleground" then message, bgStats = WoWStatusBattlegrounds.parts(e.text) end
            message = bgStats and T(message) or J.deathText(e)
            row.message:SetText(who:gsub("|","||").." — "..WoWStatusPresentation.colourItem(e,(message..J.withText(e)):gsub("|","||")))
            local scope=e.imported=="achievement" and T("From your achievements (date only)") or e.owner and T("Your activity")
                or (e.origin=="catchup" and (T("Caught up via").." "..(e.via or T("a group member"))..(e.relay and (", "..T("passed on by").." "..e.relay) or ""))
                or e.origin=="legacy" and T("Saved group update") or T("Live group update"))
            -- A death that ends a long deathless streak says so before its caption (#164).
            local ended=WoWStatusStreaks and WoWStatusStreaks.endedText(e)
            local caption=bgStats or WoWStatusFlavour.text(e)
            row.flavour:ClearAllPoints();row.flavour:SetPoint("TOPLEFT",88,bgStats and -64 or -74)
            row.flavour:SetHeight(bgStats and 30 or 18);row.flavour:SetWordWrap(bgStats ~= nil)
            if row.flavour.SetMaxLines then row.flavour:SetMaxLines(bgStats and 2 or 1) end
            row.flavour.oneLine = not bgStats
            row.flavour:SetText(ended and ("|cffffd100"..ended:gsub("|","||").."|r"..(caption~="" and (" "..caption) or "")) or caption)
            local when=WoWStatusHistory.localTime(e.at)
            if e.imported then when=when:sub(1,10) end
            local reacted=J.reactionsText(e)
            local said=J.sentReaction(e)
            local mine=not e.owner and said and ("  |cffffd100"..T("You whispered").." “"..said:gsub("|","||").."”|r") or ""
            row.detail:SetText(when.." · "..scope..(reacted and ("  |cffffd100"..reacted.."|r") or "")..mine)
            -- Reaction buttons for a minute after the notification; the log redraws when they expire.
            if rowReactions(row,e) then
                local expires=S.number(e.shown_at)+J.REACT_WINDOW
                panel.reactUntil=math.min(panel.reactUntil or expires,expires)
            end
            row.event_id=e.id;row.entry=e;row:Show()
        else row.event_id=nil;row:Hide() end
    end

end
refresh=function()
    -- Every change to the log (reactions, mutes, new or aged-out entries) also
    -- reaches the Reactions page (#171), even before the Activity page is built.
    if WoWStatusReactions then WoWStatusReactions.changed() end
    if not panel then return end
    local offset=panel.scroll:GetVerticalScroll()
    local anchor=panel.entriesList and panel.entriesList[math.floor(offset/132)+1]
    if offset>0 and anchor then
        for i,e in ipairs(visibleEntries()) do
            if e.id==anchor.id then panel.scroll:SetVerticalScroll((i-1)*132+offset%132);break end
        end
    end
    render()
end
-- JournalStore.lua redraws through this whenever the log changes.
I.refresh=refresh
-- The people in the log, for the Person filter: {label, value=sender key}.
local function people()
    local list,seen={},{}
    for _,e in ipairs(J.displayEntries()) do
        local key=P.senderKey(e.sender)
        if key and not seen[key] and J.visible(e) then
            seen[key]=true
            local shown=(not e.owner and WoWStatusRoster and WoWStatusRoster.displayName) and WoWStatusRoster.displayName(e.sender)
                or (e.sender:match("^[^-]+") or e.sender)
            list[#list+1]={label=shown:gsub("|","||"),value=key,name=e.sender:match("^[^-]+") or e.sender}
        end
    end
    table.sort(list,function(a,b) return S.lowerASCII(a.label)<S.lowerASCII(b.label) end)
    return list
end
local function build(parent)
    panel=CreateFrame("Frame","WoWStatusActivityLog",parent);panel:SetAllPoints(parent)
    panel.scroll=CreateFrame("ScrollFrame",nil,panel,"UIPanelScrollFrameTemplate")
    panel.scroll:SetPoint("TOPLEFT",24,-38);panel.scroll:SetSize(710,436)
    panel.child=CreateFrame("Frame",nil,panel.scroll);panel.child:SetSize(686,420);panel.scroll:SetScrollChild(panel.child)
    panel.empty=label(panel.child,"GameFontHighlightLarge",24,-180,620)
    panel.empty:SetJustifyH("CENTER");panel.empty:SetText(T("No activity yet"))
    panel.rows={};panel.filter="all";panel.day="today"
    for i=1,6 do
        local row=WoWStatusUI.box(panel.child,680,124)
        row.accent=row:CreateTexture(nil,"OVERLAY");row.accent:SetPoint("TOPLEFT",4,-4);row.accent:SetSize(672,2)
        row.iconFrame=WoWStatusUI.icon(row,60);row.iconFrame:SetPoint("TOPLEFT",12,-20);row.icon=row.iconFrame.texture
        row.heading=oneLine(label(row,"GameFontNormalLarge",88,-12,570))
        row.message=oneLine(label(row,"GameFontHighlightLarge",88,-40,570));row.message:SetHeight(22)
        row:EnableMouse(true)
        row:SetScript("OnEnter",function(self)
            -- Armor: the item's own tooltip, with who equipped it.
            if self.entry and WoWStatusPresentation.itemTooltip(self,self.entry) then
                GameTooltip:AddLine(" ");GameTooltip:AddLine(T("Equipped by").." "..(self.entry.sender:match("^[^-]+") or self.entry.sender),.8,.8,.8)
                GameTooltip:Show()
            elseif GameTooltip and self.entry then
                -- The card's lines in full (they may be cut off with "...").
                local e=self.entry
                local who=J.displayName(e)
                GameTooltip:SetOwner(self,"ANCHOR_RIGHT");GameTooltip:SetText((who:gsub("|","||")))
                GameTooltip:AddLine(WoWStatusPresentation.colourItem(e,J.deathText(e):gsub("|","||")),1,1,1,true)
                local ended=WoWStatusStreaks and WoWStatusStreaks.endedText(e)
                if ended then GameTooltip:AddLine(ended:gsub("|","||"),1,.82,0,true) end
                local caption=WoWStatusFlavour.text(e)
                if caption and caption~="" then GameTooltip:AddLine(caption,.8,.8,.8,true) end
                local detail=self.detail and self.detail:GetText()
                if detail and detail~="" then GameTooltip:AddLine(detail,WoWStatusUI.MUTED,WoWStatusUI.MUTED,WoWStatusUI.MUTED,true) end
                GameTooltip:Show()
            end
        end)
        row:SetScript("OnLeave",function() if GameTooltip then GameTooltip:Hide() end end)
        row.flavour=oneLine(label(row,"GameFontHighlightSmall",88,-74,570))
        row.detail=oneLine(label(row,"GameFontHighlightSmall",88,-98,570))
        panel.rows[i]=row
    end
    -- Search box (#175). Nothing is stored, so it is empty at every /reload.
    label(panel,"GameFontNormal",24,-12,70):SetText(T("Search:"))
    panel.search=nil
    panel.searchBox=CreateFrame("EditBox",nil,panel,"InputBoxTemplate")
    panel.searchBox:SetPoint("TOPLEFT",96,-10);panel.searchBox:SetSize(300,24)
    panel.searchBox:SetAutoFocus(false);panel.searchBox:SetMaxLetters(48)
    panel.searchBox:SetScript("OnTextChanged",function(self)
        local text=S.string(self:GetText()) or ""
        if text==(panel.search or "") then return end
        panel.search=text~="" and text or nil
        -- Filtered after a short pause, not on every keystroke.
        panel.searchWait=.25
    end)
    panel.searchBox:SetScript("OnEnterPressed",function(self) self:ClearFocus() end)
    -- Escape, and B on a controller, leave the field without clearing the search.
    panel.searchBox:SetScript("OnEscapePressed",function(self) self:ClearFocus() end)
    panel.searchCount=label(panel,"GameFontHighlight",514,-12,220)
    panel.searchClear=CreateFrame("Button",nil,panel,"UIPanelButtonTemplate")
    panel.searchClear:SetPoint("TOPLEFT",404,-10);panel.searchClear:SetSize(100,24)
    panel.searchClear:SetText(T("Clear"))
    local function clearSearch()
        panel.searchBox:SetText("");panel.searchBox:ClearFocus()
        panel.search,panel.searchWait=nil,nil
        panel.scroll:SetVerticalScroll(0);render()
    end
    panel.clearSearch=clearSearch
    panel.searchClear:SetScript("OnClick",clearSearch)
    local waited=0
    panel:SetScript("OnUpdate",function(_,delta)
        if panel.searchWait then
            panel.searchWait=panel.searchWait-(delta or 0)
            if panel.searchWait<=0 then
                panel.searchWait=nil
                panel.scroll:SetVerticalScroll(0);render()
            end
        end
        waited=waited+(delta or 0)
        if waited<1 then return end
        waited=0
        if panel.reactUntil and S.now()>=panel.reactUntil then render() end
    end)
    if panel.scroll.HookScript then panel.scroll:HookScript("OnVerticalScroll",render)
    else panel.scroll:SetScript("OnVerticalScroll",render) end
    local buttons={{"All","all"},{"Mine","mine"},{"Friends","friends"}}
    for i,b in ipairs(buttons) do
        local widget=CreateFrame("Button",nil,panel,"UIPanelButtonTemplate");widget:SetPoint("TOPLEFT",24+(i-1)*114,-490);widget:SetSize(106,30);widget:SetText(T(b[1]))
        widget:SetScript("OnClick",function() panel.filter=b[2];panel.scroll:SetVerticalScroll(0);render() end)
    end
    -- Type and Person filters, combined with the buttons above.
    panel.typeButton=CreateFrame("Button",nil,panel,"UIPanelButtonTemplate");panel.typeButton:SetPoint("TOPLEFT",372,-490);panel.typeButton:SetSize(176,30)
    panel.typeButton:SetScript("OnClick",function(self)
        local items={{label=T("All"),value=0}}
        for i,t in ipairs(J.TYPES) do items[#items+1]={label=T(t[1]),value=i} end
        WoWStatusUI.menu(self,items,function(value)
            panel.typeFilter=value~=0 and value or nil;panel.scroll:SetVerticalScroll(0);render()
        end)
    end)
    panel.personButton=CreateFrame("Button",nil,panel,"UIPanelButtonTemplate");panel.personButton:SetPoint("TOPLEFT",556,-490);panel.personButton:SetSize(176,30)
    panel.personButton:SetScript("OnClick",function(self)
        local list,items=people(),{{label=T("All"),value=""}}
        for _,item in ipairs(list) do items[#items+1]={label=item.label,value=item.value} end
        WoWStatusUI.menu(self,items,function(value)
            panel.character,panel.characterName=value~="" and value or nil,nil
            for _,item in ipairs(list) do if item.value==value then panel.characterName=item.name end end
            panel.scroll:SetVerticalScroll(0);render()
        end)
    end)
    -- Day picker: a month calendar; days with activity (for the other filters) in gold.
    panel.dayButton=CreateFrame("Button",nil,panel,"UIPanelButtonTemplate");panel.dayButton:SetPoint("TOPLEFT",572,-522);panel.dayButton:SetSize(160,24)
    panel.dayButton:SetScript("OnClick",function(self)
        local counts={}
        for _,e in ipairs(visibleEntries(true)) do local d=dayOf(e);if d then counts[d]=(counts[d] or 0)+1 end end
        WoWStatusUI.calendar(self,pickedDay(),today(),counts,function(key)
            panel.day=key==today() and "today" or key;panel.scroll:SetVerticalScroll(0);render()
        end)
    end)
    -- Recent reactions (#171), with how many arrived since you last looked.
    panel.reactionsButton=CreateFrame("Button",nil,panel,"UIPanelButtonTemplate");panel.reactionsButton:SetPoint("TOPLEFT",24,-522);panel.reactionsButton:SetSize(130,24)
    panel.reactionsButton:SetText(T("Reactions"))
    panel.reactionsButton:SetScript("OnClick",function() if WoWStatusReactions then WoWStatusReactions.show() end end)
    panel.export=CreateFrame("Button",nil,panel,"UIPanelButtonTemplate")
    panel.export:SetPoint("TOPLEFT",162,-522);panel.export:SetSize(100,24);panel.export:SetText(T("Export"))
    panel.export:SetScript("OnClick",function() WoWStatusExport.activity(visibleEntries()) end)
    panel.showing=oneLine(label(panel,"GameFontHighlight",270,-528,174))
    panel.showAll=CreateFrame("Button",nil,panel,"UIPanelButtonTemplate");panel.showAll:SetPoint("TOPLEFT",450,-522);panel.showAll:SetSize(110,24)
    panel.showAll:SetText(T("Show all"));panel.showAll:Hide()
    panel.showAll:SetScript("OnClick",function()
        panel.filter,panel.typeFilter,panel.character,panel.characterName="all",nil,nil,nil
        clearSearch()
    end)
    return panel
end
-- The log is the Activity page of the main window (#57).
WoWStatusMainWindow.register("activity","Activity",build,function() J.markSeen();render() end)
function J.show()
    if not I.db then return end
    WoWStatusMainWindow.show("activity")
end
-- Open the Activity page showing only one character's entries.
function J.showCharacter(name)
    if not I.db or not P.senderKey(name) then return false end
    WoWStatusMainWindow.show("activity",true)
    panel.filter,panel.character,panel.characterName="all",P.senderKey(name),name:match("^[^-]+") or name
    panel.searchBox:SetText("");panel.search,panel.searchWait=nil,nil
    panel.day=nil -- A character's activity on every day.
    panel.scroll:SetVerticalScroll(0);render()
    if WoWStatusMainWindow.go then WoWStatusMainWindow.go({page="activity",character=name}) end
    return true
end
-- Open the Activity page scrolled to one entry (used by the Overview links).
function J.focus(id)
    if not I.db or not I.index[id] then return false end
    WoWStatusMainWindow.show("activity")
    -- Every filter goes, as Show all does. A type or person filter left from
    -- earlier in the session would hide the very entry we came to show, and
    -- the jump would quietly do nothing (#119).
    panel.filter,panel.typeFilter,panel.character,panel.characterName="all",nil,nil,nil
    panel.searchBox:SetText("");panel.search,panel.searchWait=nil,nil
    local day=dayOf(I.index[id])
    panel.day=day==today() and "today" or day
    for i,e in ipairs(visibleEntries()) do
        if e.id==id then panel.scroll:SetVerticalScroll((i-1)*132);render();return true end
    end
    panel.scroll:SetVerticalScroll(0);render()
    return false
end
