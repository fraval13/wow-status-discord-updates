-- "When we play" (#158): when each player in the group has been around, read
-- only from the activity log this client already holds.
-- Nothing new is sent, no new sharing setting and no new protocol letters: the
-- page counts timestamps that friends' entries already carry. It is deliberately
-- coarse - one count per weekday and per four-hour block, never a minute - and
-- it reaches back only as far as the log does.
WoWStatusWhenWePlay = {}
local W, S = WoWStatusWhenWePlay, WoWStatusSafe
local T = WoWStatusLocale.T
local UI = WoWStatusUI
local page

W.BLOCK = 4                 -- hours in one block
W.BLOCKS = 6
W.DAYS = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}
W.DAY_PLURAL = {"Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays"}
-- Below this a row says "not enough yet" instead of pretending to know a habit.
W.MIN_ENTRIES = 6
W.MIN_DAYS = 10
W.MAX_WINDOW_DAYS = 400     -- the calendar loop is bounded whatever the log holds

-- The viewer's own local time, as the issue asks: the log carries timestamps,
-- and a friend two time zones away should read the hours they would play in.
function W.when(at)
    -- date() without a leading "!" is the player's own clock. One formatted
    -- string rather than "*t", so the oldest clients and the test harness read
    -- the same thing: weekday 0-6 (Sunday first), hour, and the calendar day.
    local ok, text = pcall(date, "%w %H %Y-%m-%d", at)
    if not ok or type(text) ~= "string" then return nil end
    local wday, hour, day = text:match("^(%d) (%d%d) (%d%d%d%d%-%d%d%-%d%d)$")
    wday, hour = tonumber(wday), tonumber(hour)
    if not wday or not hour then return nil end
    return {day=(wday + 6) % 7 + 1, hour=hour, block=math.floor(hour / W.BLOCK) + 1, date=day}
end

-- One row per player, not per character: their characters' entries are counted
-- together, under the player name their list announced.
local function personOf(entry)
    local sender = S.string(entry.sender) or "?"
    local player = WoWStatusRoster and WoWStatusRoster.playerOf and WoWStatusRoster.playerOf(sender)
    if type(player) == "string" and player ~= "" then return "p:" .. player, player end
    return "c:" .. sender, sender:match("^[^-]+") or sender
end

-- How many of each weekday the window covers, so "6 of the last 8 Wednesdays"
-- counts the Wednesdays that happened, not the ones a friend missed.
local function calendar(from, to)
    local counts, seen, at, steps = {}, {}, from, 0
    for day = 1, 7 do counts[day] = 0 end
    while at <= to and steps < W.MAX_WINDOW_DAYS do
        local t = W.when(at)
        if t and not seen[t.date] then seen[t.date] = true; counts[t.day] = counts[t.day] + 1 end
        at, steps = at + 86400, steps + 1
    end
    return counts
end

function W.enough(row)
    return row.total >= W.MIN_ENTRIES and row.days >= 2
end

-- "Tue-Thu", "Wed" or "Mon/Thu/Sat": the weekdays that carry at least half of
-- the player's busiest day.
function W.dayText(list)
    if #list == 0 then return nil end
    if #list == 1 then return T(W.DAYS[list[1]]) end
    local run = list[#list] - list[1] + 1 == #list
    if run then return T(W.DAYS[list[1]]) .. "-" .. T(W.DAYS[list[#list]]) end
    local parts = {}
    for i = 1, math.min(3, #list) do parts[#parts + 1] = T(W.DAYS[list[i]]) end
    return table.concat(parts, "/") .. (#list > 3 and "…" or "")
end

function W.blockText(block)
    return string.format("%02d:00-%02d:00", (block - 1) * W.BLOCK, block * W.BLOCK)
end

-- "usually Tue-Thu, 20:00-24:00", or nil while the log says too little.
function W.summary(row)
    if not W.enough(row) then return nil end
    local best = 0
    for day = 1, 7 do best = math.max(best, row.byDay[day]) end
    local top = {}
    for day = 1, 7 do
        if row.byDay[day] > 0 and row.byDay[day] >= best * .5 then top[#top + 1] = day end
    end
    local block, most = 1, -1
    for i = 1, W.BLOCKS do
        if row.byBlock[i] > most then block, most = i, row.byBlock[i] end
    end
    local days = W.dayText(top)
    return days and (days .. ", " .. W.blockText(block)) or nil
end

-- "Seen on 6 of the last 8 Wednesdays."
function W.dayDetail(row, day)
    local seen, of = row.seenDays[day], row.weekdays[day] or 0
    if of == 0 then return nil end
    -- Concatenated rather than one format string: the day name goes in by
    -- hand, so no pattern class ever reaches a translated text (#23).
    return T(W.DAY_PLURAL[day]) .. ": " .. WoWStatusLocale.F(T("seen on %d of the last %d"), seen, of)
end

-- Every player in the log, newest activity first. Hidden characters and muted
-- friends are left out: WoWStatusJournal.visible already drops the latter.
function W.data()
    local hidden = (WoWStatusRoster and WoWStatusRoster.hiddenNames and WoWStatusRoster.hiddenNames()) or {}
    local keyOf = WoWStatusRoster and WoWStatusRoster.key
    local people, rows, first, last = {}, {}, nil, nil
    for _, entry in ipairs(WoWStatusJournal.entries()) do
        local at, sender = S.number(entry.at), S.string(entry.sender)
        local blocked = sender and keyOf and hidden[keyOf(sender)]
        if at and sender and not blocked and WoWStatusJournal.visible(entry) then
            local t = W.when(at)
            if t then
                local id, name = personOf(entry)
                local row = people[id]
                if not row then
                    row = {id=id, name=name, mine=entry.owner ~= nil, total=0, days=0, last=at,
                        byDay={}, byBlock={}, seenDays={}, dates={}, weekdays={}}
                    for day = 1, 7 do row.byDay[day], row.seenDays[day] = 0, 0 end
                    for block = 1, W.BLOCKS do row.byBlock[block] = 0 end
                    people[id] = row
                    rows[#rows + 1] = row
                end
                row.total = row.total + 1
                row.byDay[t.day] = row.byDay[t.day] + 1
                row.byBlock[t.block] = row.byBlock[t.block] + 1
                row.last = math.max(row.last, at)
                if not row.dates[t.date] then
                    row.dates[t.date] = true
                    row.days = row.days + 1
                    row.seenDays[t.day] = row.seenDays[t.day] + 1
                end
                if not first or at < first then first = at end
                if not last or at > last then last = at end
            end
        end
    end
    local now = S.now()
    local weekdays = calendar(first or now, math.max(last or now, now))
    for _, row in ipairs(rows) do
        row.weekdays = weekdays
        row.summary = W.summary(row)
        local busiest = 0
        for day = 1, 7 do busiest = math.max(busiest, row.byDay[day]) end
        row.busiest = busiest
    end
    table.sort(rows, function(a, b)
        if a.mine ~= b.mine then return a.mine end -- your own row first, to compare against
        if a.total == b.total then return a.name < b.name end
        return a.total > b.total
    end)
    return rows, first, last
end

-- The page: a tabless page of the main window, opened from Overview or
-- /wstatus when. One button row per player, and a strip of day cells.
local ROW, CELL = 46, 26
local function cellColour(share)
    if share <= 0 then return .12, .14, .18, .9 end
    return .18 + .34 * share, .26 + .5 * share, .36 + .54 * share, .95
end
local function makeRow(index)
    local row = CreateFrame("Button", nil, page.list)
    row:SetSize(680, ROW); row:SetPoint("TOPLEFT", 0, -(index - 1) * ROW)
    row.name = UI.text(row, "GameFontNormal", 0, -6, 160)
    row.summary = UI.text(row, "GameFontHighlightSmall", 0, -26, 230)
    row.cells = {}
    for day = 1, 7 do
        local cell = row:CreateTexture(nil, "ARTWORK")
        cell:SetPoint("TOPLEFT", 240 + (day - 1) * (CELL + 4), -8); cell:SetSize(CELL, CELL)
        local caption = UI.text(row, "GameFontDisableSmall", 240 + (day - 1) * (CELL + 4), -36, CELL + 4)
        caption:SetText(T(W.DAYS[day]))
        row.cells[day] = cell
    end
    row.detail = UI.text(row, "GameFontHighlightSmall", 468, -16, 212)
    row:SetScript("OnClick", function(self)
        page.open = page.open ~= self.id and self.id or nil
        W.render()
    end)
    row:SetScript("OnEnter", function(self)
        if not GameTooltip or not self.row then return end
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:SetText((self.row.name:gsub("|", "||")))
        for day = 1, 7 do
            local detail = W.dayDetail(self.row, day)
            if detail then GameTooltip:AddLine(detail, 1, 1, 1, true) end
        end
        GameTooltip:AddLine(T("Click for the hours of the day."), .8, .8, .8, true)
        GameTooltip:Show()
    end)
    row:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
    page.rows[index] = row
    return row
end
local function makeBlocks()
    local strip = CreateFrame("Frame", nil, page.list)
    strip:SetSize(680, 44)
    strip.cells, strip.labels = {}, {}
    for i = 1, W.BLOCKS do
        local cell = strip:CreateTexture(nil, "ARTWORK")
        cell:SetPoint("TOPLEFT", 240 + (i - 1) * 74, -4); cell:SetSize(68, 18)
        local caption = UI.text(strip, "GameFontDisableSmall", 240 + (i - 1) * 74, -24, 74)
        caption:SetText(W.blockText(i):sub(1, 5))
        strip.cells[i], strip.labels[i] = cell, caption
    end
    strip.title = UI.text(strip, "GameFontHighlightSmall", 0, -8, 230)
    return strip
end
function W.render()
    if not page then return end
    local rows, first = W.data()
    page.empty:SetShown(#rows == 0)
    page.since:SetText(#rows == 0 and ""
        or (T("As far back as the log goes: since") .. " " .. WoWStatusHistory.oslo(first):sub(1, 10) .. "."))
    local y, shown = 0, 0
    for index, row in ipairs(rows) do
        local widget = page.rows[index] or makeRow(index)
        widget.id, widget.row = row.id, row
        widget:ClearAllPoints(); widget:SetPoint("TOPLEFT", 0, -y)
        widget.name:SetText((row.name:gsub("|", "||")) .. (row.mine and ("  " .. UI.MUTED_CODE .. T("(you)") .. "|r") or ""))
        widget.summary:SetText(row.summary and (T("usually") .. " " .. row.summary)
            or (UI.MUTED_CODE .. T("not enough yet") .. "|r"))
        for day = 1, 7 do
            local share = row.busiest > 0 and row.byDay[day] / row.busiest or 0
            widget.cells[day]:SetColorTexture(cellColour(share))
        end
        widget.detail:SetText(WoWStatusLocale.F(T("%d entries over %d days"), row.total, row.days))
        widget:Show()
        y, shown = y + ROW, shown + 1
        if page.open == row.id then
            page.blocks = page.blocks or makeBlocks()
            local strip = page.blocks
            strip:ClearAllPoints(); strip:SetPoint("TOPLEFT", 0, -y)
            strip.title:SetText(T("Hours of the day"))
            local most = 0
            for i = 1, W.BLOCKS do most = math.max(most, row.byBlock[i]) end
            for i = 1, W.BLOCKS do
                strip.cells[i]:SetColorTexture(cellColour(most > 0 and row.byBlock[i] / most or 0))
            end
            strip:Show()
            y = y + 44
        end
    end
    for index = shown + 1, #page.rows do page.rows[index]:Hide(); page.rows[index].row = nil end
    if page.blocks and not page.open then page.blocks:Hide() end
    page.list:SetHeight(math.max(1, y))
end
local function build(parent)
    page = CreateFrame("Frame", "WoWStatusWhenWePlayPage", parent); page:SetAllPoints(parent)
    page.heading = UI.text(page, "GameFontNormalLarge", 24, -4, 700)
    page.heading:SetText(T("When we play"))
    page.note = UI.text(page, "GameFontHighlightSmall", 24, -30, 700)
    page.note:SetText(T("Built only from the activity already in your log. Nothing is sent, and nobody is told you looked."))
    page.since = UI.text(page, "GameFontDisableSmall", 24, -50, 700)
    page.scroll = CreateFrame("ScrollFrame", nil, page, "UIPanelScrollFrameTemplate")
    page.scroll:SetPoint("TOPLEFT", 24, -72); page.scroll:SetSize(710, 456)
    page.list = CreateFrame("Frame", nil, page.scroll); page.list:SetSize(686, 1)
    page.scroll:SetScrollChild(page.list)
    page.rows = {}
    page.empty = UI.text(page, "GameFontHighlight", 24, -100, 680)
    page.empty:SetText(T("No activity in the log yet. This fills in as you and your friends play."))
    return page
end
WoWStatusMainWindow.register("whenweplay", "When we play", build, function() W.render() end, {tab=false})

function W.show() WoWStatusMainWindow.show("whenweplay") end
