-- "Together": what the whole group adds up to (#167). Local arithmetic over the
-- roster and the log the client already holds; nothing is sent, and nothing new
-- is recorded. Hidden characters are left out, because R.groups() leaves them
-- out, and a total that misses a member says so instead of under-reporting in
-- silence.
WoWStatusTogether = {}
local G, S = WoWStatusTogether, WoWStatusSafe
local T, TF = WoWStatusLocale.T, WoWStatusLocale.F
local page, registered, chosen
local period = "total"
G.PERIODS = {
    {value="daily", label="Daily"}, {value="weekly", label="Weekly"},
    {value="monthly", label="Monthly"}, {value="yearly", label="Yearly"},
    {value="total", label="Total"},
}

-- Local calendar dates, rather than elapsed 24-hour spans, keep DST days and
-- month/year boundaries consistent with the Activity and Records pages.
function G.periodRange(value, at)
    at = at or S.now()
    local today = WoWStatusHistory.day(at)
    local year, month = today:match("^(%d+)%-(%d+)%-%d+$")
    if value == "daily" then return today, today end
    if value == "weekly" then
        local weekday = (tonumber(date("%w", at)) + 6) % 7
        return WoWStatusHistory.day(at, -weekday), WoWStatusHistory.day(at, 6 - weekday)
    end
    if value == "monthly" then
        year, month = tonumber(year), tonumber(month)
        local leap = year % 4 == 0 and (year % 100 ~= 0 or year % 400 == 0)
        local days = ({31, leap and 29 or 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31})[month]
        return today:sub(1, 7) .. "-01", today:sub(1, 7) .. "-" .. days
    end
    if value == "yearly" then return year .. "-01-01", year .. "-12-31" end
end
-- {key, caption, read(row), format(total)}
local MEASURES = {
    {"played", "Hours played", function(row) return S.number(row.played) end,
        function(total) return WoWStatusUI.duration(total) end},
    {"level", "Levels between us", function(row) return S.number(row.level) end, tostring},
    {"quests", "Quests finished", function(row) return S.number(row.quests) end, tostring},
    {"deaths", "Deaths survived", function(row) return S.number(row.deaths) end, tostring},
    {"kills", "Monsters felled", function(row) return S.number(row.kills) end, tostring},
    {"dungeons", "Dungeons cleared", function(row) return S.number(row.dungeons) end, tostring},
    {"mounts", "Mounts earned", function(row) return S.number(row.mounts) end, tostring},
    {"honor_kills", "Honorable kills", function(row) return S.number(row.honor_kills) end, tostring},
    {"gold", "Gold gathered", function(row) return S.number(row.gold) end,
        function(total) return WoWStatusUI.money(total) end},
}
local ACTIVITY = {
    {"level", "Level-up milestones"}, {"death", "Deaths recorded"},
    {"quest", "Quest milestones"}, {"profession", "Profession milestones"},
    {"dungeon", "Dungeon clears"}, {"raid", "Raid boss kills"},
    {"mount", "Mount milestones"}, {"loot", "Armor first equips"},
    {"reputation", "Reputation milestones"}, {"unlock", "Class unlocks"},
    {"pvp", "PvP promotions"}, {"achievement", "Achievements earned"},
    {"zone", "Zones explored"},
}
-- The group's characters, each counted once however many groups it is in.
function G.members(group)
    local list, seen = {}, {}
    for _, entry in ipairs(WoWStatusRoster.groups()) do
        for _, row in ipairs(entry.rows) do
            local k = WoWStatusRoster.key(row.name)
            -- groupIds is a map of the groups this account shares with them.
            local ours = type(row.groupIds) == "table" and row.groupIds[group] == true
            if k and ours and not seen[k] then
                seen[k] = true; list[#list + 1] = row
            end
        end
    end
    return list
end
-- {since, members, rows={{caption, total, shared, of}}, week={...}}
function G.totals(group)
    local members = G.members(group)
    local rows = {}
    for _, measure in ipairs(MEASURES) do
        local read, total, shared = measure[3], nil, 0
        for _, row in ipairs(members) do
            local value = read(row)
            if value then total = (total or 0) + value; shared = shared + 1 end
        end
        if total then
            rows[#rows + 1] = {caption = measure[2], total = measure[4](total),
                               shared = shared, of = #members}
        end
    end
    -- Zones are not a number anybody shares: they are counted from the log, by
    -- name, so two friends in Duskwood are one zone discovered.
    local zones, count = {}, 0
    local first, last = WoWStatusFirsts.weekRange(0)
    local week = {level = 0, death = 0, zone = 0, quest = 0, dungeon = 0}
    for _, e in ipairs(WoWStatusJournal.entries()) do
        local ours = type(e.groups) == "table" and e.groups[group] == true and WoWStatusJournal.visible(e)
        if ours and e.kind == "zone" then
            local name = S.string(e.text) and e.text:match("^Entered (.+)$")
            if name and not zones[name] then zones[name] = true; count = count + 1 end
        end
        if ours and week[e.kind] and S.number(e.at) then
            local day = WoWStatusHistory.day(e.at)
            if day >= first and day <= last then week[e.kind] = week[e.kind] + 1 end
        end
    end
    if count > 0 then
        rows[#rows + 1] = {caption = "Zones discovered", total = tostring(count), shared = #members, of = #members}
    end
    return {since = WoWStatusGroups.historySince(group), members = #members, rows = rows, week = week}
end
-- "Since 2026-03-14" when the account's join date is known.
function G.sinceText(data)
    if not S.number(data.since) then return T("Since you joined") end
    return T("Since") .. " " .. WoWStatusHistory.day(data.since)
end

-- A dated view counts only milestones the visible retained log can establish.
-- Snapshot totals (gold, played time, kills, etc.) have no historical deltas.
function G.activity(group, value)
    local first, last = G.periodRange(value)
    if not first then return G.totals(group) end
    local counts, zones, entries = {}, {}, 0
    for _, measure in ipairs(ACTIVITY) do counts[measure[1]] = 0 end
    local hidden = WoWStatusRoster.hiddenNames()
    local now = S.now()
    for _, e in ipairs(WoWStatusJournal.entries()) do
        local at, key = S.number(e.at), WoWStatusRoster.key(e.sender)
        if at and at <= now and not e.imported and not e.sample and not hidden[key or ""]
            and type(e.groups) == "table" and e.groups[group] == true and WoWStatusJournal.visible(e) then
            local day = WoWStatusHistory.day(at)
            if day >= first and day <= last then
                local kind = e.kind == "epicmount" and "mount" or e.kind
                if counts[kind] ~= nil then
                    entries = entries + 1
                    if kind == "zone" then
                        local name = S.string(e.text) and e.text:match("^Entered (.+)$")
                        if name and not zones[name] then zones[name] = true; counts.zone = counts.zone + 1 end
                    else counts[kind] = counts[kind] + 1 end
                end
            end
        end
    end
    local rows = {}
    for _, measure in ipairs(ACTIVITY) do
        rows[#rows + 1] = {caption=measure[2], total=tostring(counts[measure[1]])}
    end
    return {first=first, last=last, rows=rows, entries=entries, members=#G.members(group)}
end
-- What the group added this week, in one line, or nil for a quiet week.
function G.weekText(week)
    local parts = {}
    local function part(count, one, many)
        if count > 0 then parts[#parts + 1] = count .. " " .. T(count == 1 and one or many) end
    end
    part(week.level, "level", "levels")
    part(week.quest, "quest milestone", "quest milestones")
    part(week.zone, "new zone", "new zones")
    part(week.dungeon, "dungeon", "dungeons")
    part(week.death, "death", "deaths")
    if #parts == 0 then return nil end
    return T("This week together:") .. " " .. table.concat(parts, " · ")
end
local function render()
    if not page then return end
    local UI = WoWStatusUI
    local groups = WoWStatusFirsts.groups()
    if not chosen then chosen = groups[1] and groups[1].id or nil end
    local label
    for _, group in ipairs(groups) do if group.id == chosen then label = group.label end end
    if not label then chosen = groups[1] and groups[1].id or nil; label = groups[1] and groups[1].label end
    UI.dropdownLabel(page.pick, label and label:gsub("|", "||") or T("No group"))
    UI.call(page.pick, "SetEnabled", #groups > 1)
    UI.call(page.period, "SetEnabled", chosen ~= nil)
    local periodLabel = "Total"
    for _, item in ipairs(G.PERIODS) do if item.value == period then periodLabel = item.label end end
    UI.dropdownLabel(page.period, T("Period:") .. " " .. T(periodLabel))
    if not chosen then
        page.heading:SetText(T("Join a group to add your adventures up together."))
        page.since:SetText("")
        page.week:SetText("")
        for _, tile in ipairs(page.tiles) do tile:Hide() end
        return
    end
    local data = period == "total" and G.totals(chosen) or G.activity(chosen, period)
    page.heading:SetText(T("Together") .. " · " .. label:gsub("|", "||"))
    local dates = data.first and (T("Dates: from") .. " " .. data.first .. " " .. T("to") .. " " .. data.last) or G.sinceText(data)
    page.since:SetText(dates .. "  " .. UI.MUTED_CODE
        .. TF("%d characters", data.members) .. "|r")
    page.week:SetText(data.first
        and T("Recorded milestones in your retained log. Older activity may be missing.")
        or (G.weekText(data.week) or T("Nothing added yet this week.")))
    for i, tile in ipairs(page.tiles) do
        local item = data.rows[i]
        tile:SetShown(item ~= nil)
        if item then
            tile.number:SetText("|cffffd100" .. item.total .. "|r")
            tile.caption:SetText(T(item.caption))
            -- A total that misses somebody says so rather than under-reporting quietly.
            tile.note:SetText(item.shared and item.shared < item.of
                and TF("Based on data from %d of %d characters", item.shared, item.of) or "")
        end
    end
    page.list:SetHeight(math.ceil(#data.rows / 3) * 112)
end
G.render = render
local function build(parent)
    local UI = WoWStatusUI
    page = CreateFrame("Frame", "WoWStatusTogetherPage", parent); page:SetAllPoints(parent)
    page.heading = UI.text(page, "GameFontNormalLarge", 24, -12, 460)
    page.pick = CreateFrame("Button", nil, page, "UIPanelButtonTemplate")
    page.pick:SetPoint("TOPRIGHT", -24, -8); page.pick:SetSize(180, 26)
    page.pick:SetScript("OnClick", function(self)
        local items = {}
        for _, group in ipairs(WoWStatusFirsts.groups()) do
            items[#items + 1] = {label = group.label, value = group.id}
        end
        if #items < 2 then return end
        UI.menu(self, items, function(value) chosen = value; render() end, 180)
    end)
    page.since = UI.text(page, "GameFontHighlight", 24, -42, 700)
    page.since:SetWidth(496); page.since:SetHeight(28)
    page.period = CreateFrame("Button", nil, page, "UIPanelButtonTemplate")
    page.period:SetPoint("TOPRIGHT", -24, -40); page.period:SetSize(180, 26)
    page.period:SetScript("OnClick", function(self)
        if not chosen then return end
        local items = {}
        for _, item in ipairs(G.PERIODS) do items[#items + 1] = {label=T(item.label), value=item.value} end
        UI.menu(self, items, function(value)
            period = value
            UI.call(page.scroll, "SetVerticalScroll", 0)
            render()
        end, 180)
    end)
    page.week = UI.text(page, "GameFontHighlightSmall", 24, -74, 700)
    page.week:SetHeight(28)
    page.scroll = CreateFrame("ScrollFrame", nil, page, "UIPanelScrollFrameTemplate")
    page.scroll:SetPoint("TOPLEFT", 24, -108); page.scroll:SetSize(706, 420)
    page.list = CreateFrame("Frame", nil, page.scroll); page.list:SetSize(700, 448)
    page.scroll:SetScrollChild(page.list)
    page.tiles = {}
    for i = 1, math.max(#MEASURES + 1, #ACTIVITY) do
        local column, line = (i - 1) % 3, math.floor((i - 1) / 3)
        local tile = UI.box(page.list, 228, 104)
        tile:SetPoint("TOPLEFT", column * 236, -line * 112)
        tile.number = UI.text(tile, "GameFontNormalHuge", 12, -12, 204)
        tile.caption = UI.text(tile, "GameFontNormal", 12, -52, 204)
        tile.note = UI.text(tile, "GameFontDisableSmall", 12, -76, 204)
        tile.note:SetHeight(24); tile.note:SetWordWrap(true)
        page.tiles[i] = tile
    end
    return page
end
-- No tab: the tab row is full, so the Overview button and /wstatus together
-- open it, as Diagnostics does.
local function register()
    if registered or type(WoWStatusMainWindow) ~= "table" then return end
    registered = WoWStatusMainWindow.register("together", "Together", build, render, {tab = false}) and true
end
G.register = register
function G.show()
    register()
    if WoWStatusMainWindow then return WoWStatusMainWindow.show("together") end
    return false
end
