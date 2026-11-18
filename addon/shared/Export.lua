-- Local, selectable CSV (#176). Nothing here sends a packet or writes saved data.
WoWStatusExport = {}
local E, S, J = WoWStatusExport, WoWStatusSafe, WoWStatusJournal
local T, TF = WoWStatusLocale.T, WoWStatusLocale.F
local frame, job
local BATCH, PAGE_ROWS, PAGE_BYTES = 32, 256, 32768
local function tableOrEmpty(value) return type(value)=="table" and value or {} end
local function plain(value)
    return (S.stripEscapes(S.string(value) or ""):gsub(S.CONTROL," "))
end
-- Only group secrets are removed: character/player names are deliberately part of
-- this user-requested copy. Never serialize a saved table, event ID or routing ID.
local function secrets()
    local db, found, seen = tableOrEmpty(WoWStatusDB), {}, {}
    local function add(value)
        value=plain(value)
        if value=="" then return end
        value=WoWStatusCaseFold(value)
        if not seen[value] then seen[value]=true;found[#found+1]=value end
    end
    local function group(id,label)
        add(id);add(label)
        if S.string(id) then add(WoWStatusGroups.channel(id)) end
    end
    for id,label in pairs(tableOrEmpty(db.account_groups)) do group(id,label) end
    for id in pairs(tableOrEmpty(db.listed_groups)) do group(id) end
    for _,c in pairs(tableOrEmpty(db.characters)) do
        for id,member in pairs(tableOrEmpty(tableOrEmpty(c).group_ids)) do group(id,tableOrEmpty(member).label) end
    end
    local roster=tableOrEmpty(db.roster)
    for id,item in pairs(tableOrEmpty(roster.listings)) do group(id,tableOrEmpty(item).name) end
    local popups=tableOrEmpty(db.popups)
    add(popups.channel)
    for channel in pairs(tableOrEmpty(popups.joined_channels)) do add(channel) end
    return found
end
local function contains(text,hidden)
    local folded=WoWStatusCaseFold(text)
    for _,word in ipairs(hidden) do if folded:find(word,1,true) then return true end end
    return false
end
local function cell(value,hidden)
    local text=plain(value)
    -- Blank the whole field, even for a substring/Unicode case-fold match. This
    -- avoids revealing a name embedded in a goal title, player name or caption.
    if contains(text,hidden) then text="" end
    -- A CSV quote alone does not stop spreadsheet formula evaluation.
    if text:match("^ *[=+@%-]") then text="'"..text end
    return '"'..text:gsub('"','""')..'"'
end
local function csv(values,hidden)
    local out={}
    for i=1,7 do out[i]=cell(values[i],hidden) end
    return table.concat(out,",")
end
local function stamp(at)
    if not S.number(at) then return "" end
    local ok,value=pcall(function() return date("!%Y-%m-%dT%H:%M:%SZ",at) end)
    return ok and S.string(value) or ""
end
local function player(e)
    if e.owner then return tableOrEmpty(WoWStatusDB).player_name or "" end
    return WoWStatusRoster.playerOf(e.sender) or ""
end
local function activityRow(e)
    if type(e)~="table" or e.sample or not J.visible(e) then return nil end
    return {stamp(e.at),e.sender,player(e),T(e.kind),J.deathText(e),"",""}
end
local function member(group)
    for _,g in ipairs(WoWStatusFirsts.groups()) do if g.id==group then return true end end
    return false
end
local function recordRows(group,view,offset)
    if not member(group) then return {} end
    local F,rows=WoWStatusFirsts,{}
    if view=="week" or view=="fun" then
        local lines,first,last
        if view=="week" then lines,first,last=F.week(group,offset) else lines=F.funRecords(group) end
        for _,line in ipairs(lines) do
            rows[#rows+1]={"","","",T(view=="week" and "This week" or "Fun records"),line,first or "",last or ""}
        end
    else
        local result,medals=F.compute(J.entries(),group)
        for _,medal in ipairs(medals) do
            local e=result[medal.key]
            if e then
                local detail=T(medal.title)
                if e.milestone and not e.exact then detail=detail.." · "..T("Reached by this date") end
                rows[#rows+1]={stamp(e.at),e.holder or e.sender,player(e),T("Firsts"),detail,"",""}
            end
        end
        -- Match the recap box on the Firsts page, including its ten-row limit.
        local count=0
        for _,e in ipairs(J.entries()) do
            if e.kind=="recap" and not e.sample and J.visible(e) and count<10 then
                rows[#rows+1]=activityRow(e);count=count+1
            end
        end
    end
    return rows
end
local function clearText()
    frame.text="";frame.box:SetText("")
    frame.select:SetEnabled(false);frame.previous:SetEnabled(false);frame.next:SetEnabled(false)
end
local function showPage(index)
    if not job or not job.ready then return end
    if job.allowed and not job.allowed() then job=nil;clearText();frame.status:SetText(T("Export is no longer available."));return end
    local page=job.pages[index]
    if not page then return end
    local text=table.concat(page,"\n")
    -- Check again on each page: membership/listings can change while it is open.
    if contains(text,secrets()) then
        job=nil;clearText();frame.status:SetText(T("Cannot export safely with the current group names."));return
    end
    job.page=index;frame.text=text
    frame.box:SetText((text:gsub("|","||")))
    if frame.box.SetCursorPosition then frame.box:SetCursorPosition(0) end
    frame.scroll:SetVerticalScroll(0)
    frame.box:SetHeight(math.max(300, S.number(S.call(frame.box.GetTextHeight,frame.box)) or #page*16))
    frame.select:SetEnabled(job.count>0);frame.previous:SetEnabled(index>1);frame.next:SetEnabled(index<#job.pages)
    frame.status:SetText(TF("Page %d of %d · %d rows",index,#job.pages,job.count))
end
local function step()
    local active=job
    if not active or active.ready then return end
    if active.allowed and not active.allowed() then
        job=nil;clearText();frame.status:SetText(T("Export is no longer available."));return
    end
    if active.prepare then active.items=active.prepare();active.prepare=nil end
    for _=1,BATCH do
        local item=active.items[active.cursor]
        if not item then
            active.ready=true;active.items=nil;showPage(1);return
        end
        active.cursor=active.cursor+1
        local row=active.row(item)
        if row then
            local line=csv(row,active.hidden)
            local page=active.pages[#active.pages]
            if #page>1 and (#page>PAGE_ROWS or active.bytes+#line+1>PAGE_BYTES) then
                page={active.header};active.pages[#active.pages+1]=page;active.bytes=#active.header
            end
            page[#page+1]=line;active.bytes=active.bytes+#line+1;active.count=active.count+1
        end
    end
    frame.status:SetText(TF("Preparing export: %d rows",active.count))
end
local function build()
    frame=CreateFrame("Frame","WoWStatusExportWindow",UIParent)
    frame:SetSize(740,520);frame:SetPoint("CENTER");frame:SetFrameStrata("FULLSCREEN_DIALOG")
    if frame.SetToplevel then frame:SetToplevel(true) end
    frame:EnableMouse(true)
    local bg=frame:CreateTexture(nil,"BACKGROUND");bg:SetAllPoints();bg:SetColorTexture(.025,.035,.065,.98)
    local function label(font,x,y,width)
        local f=frame:CreateFontString(nil,"OVERLAY",font)
        f:SetPoint("TOPLEFT",x,y);f:SetWidth(width);f:SetJustifyH("LEFT");return f
    end
    frame.title=label("GameFontNormalLarge",24,-20,690)
    frame.warning=label("GameFontHighlight",24,-48,690)
    frame.hint=label("GameFontDisable",24,-82,690)
    frame.status=label("GameFontHighlight",24,-116,690)
    frame.scroll=CreateFrame("ScrollFrame",nil,frame,"UIPanelScrollFrameTemplate")
    frame.scroll:SetPoint("TOPLEFT",24,-144);frame.scroll:SetSize(668,314)
    frame.box=CreateFrame("EditBox",nil,frame.scroll)
    frame.box:SetMultiLine(true);frame.box:SetAutoFocus(false);frame.box:SetFontObject("GameFontHighlightSmall")
    frame.box:SetWidth(650);frame.box:SetHeight(314);frame.box:SetMaxLetters(0)
    frame.box:SetScript("OnEscapePressed",function(self) self:ClearFocus() end)
    frame.box:SetScript("OnTextChanged",function(self,user)
        if user then self:SetText(((frame.text or ""):gsub("|","||"))) end
    end)
    frame.scroll:SetScrollChild(frame.box)
    local function button(x,width,action)
        local b=CreateFrame("Button",nil,frame,"UIPanelButtonTemplate")
        b:SetPoint("BOTTOMLEFT",x,20);b:SetSize(width,28);b:SetScript("OnClick",action);return b
    end
    frame.select=button(24,150,function() frame.box:SetFocus();if frame.box.HighlightText then frame.box:HighlightText() end end)
    frame.previous=button(188,150,function() if job then showPage(job.page-1) end end)
    frame.next=button(350,150,function() if job then showPage(job.page+1) end end)
    frame.close=button(560,150,function() frame:Hide() end)
    frame:SetScript("OnUpdate",step)
    frame:SetScript("OnHide",function() job=nil;clearText();frame.box:ClearFocus() end)
    table.insert(UISpecialFrames,"WoWStatusExportWindow")
end
local function begin(items,row,allowed,prepare)
    if not frame then build() end
    frame.title:SetText(T("Copy export"))
    frame.warning:SetText(T("Contains character and player names. Group names are removed. Check before sharing."))
    frame.hint:SetText(T("CSV · UTC timestamps. Select all, then copy. Use Next page for the rest. Nothing is sent."))
    frame.select:SetText(T("Select all"));frame.previous:SetText(T("Previous page"))
    frame.next:SetText(T("Next page"));frame.close:SetText(T("Close"))
    local hidden=secrets()
    local header=csv({T("Timestamp (UTC)"),T("Character"),T("Player"),T("Category"),T("Details"),
        T("Period start (local date)"),T("Period end (local date)")},{})
    job={items=items,row=row,allowed=allowed,prepare=prepare,cursor=1,count=0,pages={{header}},bytes=#header,
        header=header,hidden=hidden}
    clearText();frame.status:SetText(TF("Preparing export: %d rows",0));frame:Show()
    if frame.Raise then frame:Raise() end
    return frame
end
function E.activity(entries)
    -- Keep the page's exact filter selection, including rows beyond the viewport.
    return begin(entries,activityRow)
end
function E.records(group,view,offset)
    return begin({},function(row) return row end,function() return member(group) end,
        function() return recordRows(group,view,offset or 0) end)
end
