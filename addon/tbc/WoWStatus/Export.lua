-- Copyable export of the activity log and records (#176).
-- A WoW addon cannot write files, so the text goes into a read-only, selectable
-- multiline edit box: select it and press Ctrl-C. Nothing leaves the client.
-- The text is built a chunk at a time from the window's OnUpdate, so a log of
-- thousands of entries never freezes the game.
-- The export names the characters and the players in your group, and it never
-- names the group itself: a group name is a shared secret (#1). Nothing here
-- reads entry.groups or a group's label, and tests/test_export.py asserts it.
WoWStatusExport = {}
local E, S = WoWStatusExport, WoWStatusSafe
local T = WoWStatusLocale.T
local UI = WoWStatusUI
local frame

-- Entries turned into lines per frame, and the most text one box is given.
E.CHUNK = 150
E.MAX_CHARACTERS = 400000
-- Which entries the log export takes: what the Activity page shows right now
-- (its type, person and day filters), everything, or the last seven days.
E.SCOPES = {
    {"shown", "What the Activity page shows"},
    {"all", "Everything"},
    {"week", "The last seven days"},
}
E.WARNING = "This text names the characters and players in your group. It never names the group itself. Read it before you paste it anywhere public."

-- Plain text for a spreadsheet or a chat message: colour codes, item links,
-- textures and control characters out, and the game's doubled pipe back to one.
local function plain(text)
    text = tostring(text or "")
    text = text:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", "")
    text = text:gsub("|H.-|h(.-)|h", "%1"):gsub("|T.-|t", "")
    text = text:gsub("||", "|"):gsub(S.CONTROL, " ")
    return (text:gsub(S.SPACE .. "+$", ""))
end
E.plain = plain

local function csv(value)
    value = plain(value)
    if value:find('[",]') then return '"' .. value:gsub('"', '""') .. '"' end
    return value
end

local function shortName(sender)
    sender = plain(sender)
    return sender:match("^[^-]+") or sender
end
-- The player behind a character, when their list says so; "" otherwise.
local function playerOf(sender)
    local player = WoWStatusRoster and WoWStatusRoster.playerOf and WoWStatusRoster.playerOf(sender)
    return type(player) == "string" and plain(player) or ""
end
local function when(at) return WoWStatusHistory.oslo(S.number(at) or 0) end

-- One log entry: an ISO date first, so the line sorts and a spreadsheet reads it.
function E.logLine(entry, format)
    local stamp = when(entry.at)
    local text = plain(WoWStatusJournal.deathText(entry))
    if format == "csv" then
        return table.concat({csv(stamp:sub(1, 10)), csv(stamp:sub(12, 16)), csv(entry.sender),
            csv(playerOf(entry.sender)), csv(entry.kind), csv(text)}, ",")
    end
    return stamp:sub(1, 16) .. "  " .. string.format("%-16s", shortName(entry.sender)) .. "  " .. text
end

-- The records of one group as lines for a chat message: firsts, this week and
-- the fun records, without the group's name.
function E.records(group)
    local lines, F = {}, WoWStatusFirsts
    group = group or ""
    local result, medals = F.compute(WoWStatusJournal.entries(), group)
    lines[#lines + 1] = T("Firsts")
    for _, medal in ipairs(medals) do
        local e = result[medal.key]
        local who = e and plain(e.holder or shortName(e.sender)) or T("nobody yet")
        lines[#lines + 1] = "- " .. T(medal.title) .. ": " .. who .. (e and (" (" .. when(e.at):sub(1, 10) .. ")") or "")
    end
    local function section(title, source, empty)
        lines[#lines + 1] = ""
        lines[#lines + 1] = title
        if #source == 0 then lines[#lines + 1] = "- " .. T(empty) end
        for _, line in ipairs(source) do lines[#lines + 1] = "- " .. plain(line) end
    end
    local week, first, last = F.week(group, 0)
    section(T("This week") .. " " .. tostring(first) .. " - " .. tostring(last), week,
        "Nothing happened in this group this week.")
    section(T("Fun records"), F.funRecords(group),
        "No fun records yet. They appear when someone does something remarkable.")
    return lines
end

local function header(kind, format, scope, count)
    if format == "csv" then return {"date,time,character,player,kind,entry"} end
    local what = kind == "records" and T("Records") or T("Activity log")
    local lines = {"WoW Status - " .. what, T("Exported") .. " " .. when(S.now()):sub(1, 16)}
    if kind == "log" then
        local label = scope
        for _, item in ipairs(E.SCOPES) do if item[1] == scope then label = T(item[2]) end end
        lines[#lines + 1] = label .. " - " .. count .. " " .. T("entries")
    end
    lines[#lines + 1] = T(E.WARNING)
    lines[#lines + 1] = ""
    return lines
end

-- A build in progress. E.step turns the next chunk of items into lines; the
-- window calls it from OnUpdate until it reports done.
function E.begin(kind, items, format, scope)
    format = format == "csv" and "csv" or "text"
    local job = {kind=kind, items=items or {}, format=format, scope=scope,
        index=0, lines={}, length=0, truncated=false, done=false}
    for _, line in ipairs(header(kind, format, scope, #job.items)) do job.lines[#job.lines + 1] = line end
    job.done = #job.items == 0
    return job
end
function E.step(job, budget)
    if job.done then return true end
    local stop = math.min(#job.items, job.index + (budget or E.CHUNK))
    while job.index < stop do
        job.index = job.index + 1
        local item = job.items[job.index]
        local line = job.kind == "log" and E.logLine(item, job.format) or plain(item)
        if job.length + #line + 1 > E.MAX_CHARACTERS then
            job.truncated, job.index = true, #job.items
            break
        end
        job.lines[#job.lines + 1] = line
        job.length = job.length + #line + 1
    end
    job.done = job.index >= #job.items
    if job.done and job.truncated then
        job.lines[#job.lines + 1] = T("The export was cut off here: there is more than one box can hold.")
    end
    return job.done
end
function E.text(job) return table.concat(job.lines, "\n") end
function E.progress(job) return job.index, #job.items end

-- The window: WoWStatusExportWindow, B closes it (UISpecialFrames).
local function button(parent, label, x, y, width, onClick)
    local widget = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
    widget:SetPoint("TOPLEFT", x, y); widget:SetSize(width, 26); widget:SetText(T(label))
    widget:SetScript("OnClick", onClick)
    return widget
end
local function scopeLabel(scope)
    for _, item in ipairs(E.SCOPES) do if item[1] == scope then return T(item[2]) end end
    return T("Everything")
end
function E.paint()
    if not frame or not frame.job then return end
    local job = frame.job
    frame.built = E.text(job)
    frame.box:SetText(frame.built)
    UI.call(frame.box, "SetCursorPosition", 0)
    local done, total = E.progress(job)
    frame.count:SetText(job.done and (total .. " " .. T(job.kind == "log" and "entries" or "lines"))
        or (T("Building") .. " " .. done .. " / " .. total))
    frame.scopeButton:SetText(T("Scope:") .. " " .. scopeLabel(frame.scope))
    frame.formatButton:SetText(T("Format:") .. " " .. T(job.format == "csv" and "CSV" or "Plain text"))
    UI.call(frame.formatButton, "SetEnabled", frame.kind == "log")
    UI.call(frame.selectAll, "SetEnabled", job.done)
end
function E.rebuild()
    if not frame then return end
    local items
    if frame.kind == "records" then
        items = E.records(frame.group)
        frame.title:SetText(T("Export records"))
    else
        items = WoWStatusJournal.exportEntries(frame.scope)
        frame.title:SetText(T("Export the activity log"))
    end
    frame.job = E.begin(frame.kind, items, frame.kind == "log" and frame.format or "text", frame.scope)
    E.step(frame.job) -- The first chunk at once, so the box is never empty.
    E.paint()
end
local function build()
    frame = CreateFrame("Frame", "WoWStatusExportWindow", UIParent)
    frame:SetSize(620, 480); frame:SetPoint("CENTER"); frame:SetFrameStrata("FULLSCREEN_DIALOG")
    frame:EnableMouse(true)
    local background = frame:CreateTexture(nil, "BACKGROUND")
    background:SetAllPoints(); background:SetColorTexture(.025, .035, .055, .96)
    if WoWStatusTheme and WoWStatusTheme.attachBackground then WoWStatusTheme.attachBackground(background) end
    frame.title = UI.text(frame, "GameFontHighlightLarge", 24, -20, 560)
    frame.help = UI.text(frame, "GameFontHighlightSmall", 24, -48, 560)
    frame.help:SetText(T("Click in the box, press Ctrl-A to select everything and Ctrl-C to copy. Nothing is sent anywhere."))
    frame.warning = UI.text(frame, "GameFontHighlightSmall", 24, -80, 560)
    frame.warning:SetText(T(E.WARNING))
    UI.mute(frame.warning)
    frame.scopeButton = button(frame, "", 24, -116, 264, function(self)
        local items = {}
        for _, item in ipairs(E.SCOPES) do items[#items + 1] = {label=T(item[2]), value=item[1]} end
        UI.menu(self, items, function(value) frame.scope = value; E.rebuild() end)
    end)
    frame.formatButton = button(frame, "", 296, -116, 180, function()
        frame.format = frame.format == "csv" and "text" or "csv"
        E.rebuild()
    end)
    frame.count = UI.text(frame, "GameFontHighlightSmall", 484, -122, 110)
    frame.scroll = CreateFrame("ScrollFrame", nil, frame, "UIPanelScrollFrameTemplate")
    frame.scroll:SetPoint("TOPLEFT", 24, -152); frame.scroll:SetSize(548, 286)
    frame.box = CreateFrame("EditBox", nil, frame.scroll)
    frame.box:SetMultiLine(true); frame.box:SetAutoFocus(false); frame.box:SetWidth(528)
    frame.box:SetFontObject("GameFontHighlightSmall")
    frame.box:SetScript("OnEscapePressed", function(self) self:ClearFocus() end)
    -- Read-only: the box is for selecting and copying, so anything typed into
    -- it is put straight back. (WoW edit boxes have no read-only flag.)
    local function restore(self, user)
        if user and frame.built and self:GetText() ~= frame.built then
            self:SetText(frame.built); UI.call(self, "HighlightText")
        end
    end
    frame.box:SetScript("OnTextChanged", restore)
    frame.box:SetScript("OnChar", function(self) restore(self, true) end)
    frame.scroll:SetScrollChild(frame.box)
    frame.selectAll = button(frame, "Select all", 24, -446, 140, function()
        UI.call(frame.box, "SetFocus"); UI.call(frame.box, "HighlightText")
    end)
    frame.close = button(frame, "Close", 452, -446, 140, function() frame:Hide() end)
    frame:SetScript("OnUpdate", function()
        if not frame.job or frame.job.done then return end
        E.step(frame.job)
        E.paint()
    end)
    if UISpecialFrames then table.insert(UISpecialFrames, "WoWStatusExportWindow") end
end

function E.showLog(scope)
    if not frame then build() end
    frame.kind, frame.scope = "log", scope or frame.scope or "shown"
    frame.format = frame.format or "text"
    E.rebuild()
    frame:Show()
    return frame
end
function E.showRecords(group)
    if not frame then build() end
    frame.kind, frame.group = "records", group
    E.rebuild()
    frame:Show()
    return frame
end
function E.frame() return frame end
