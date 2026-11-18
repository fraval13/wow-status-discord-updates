-- Two characters side by side (#160). Everything here is read from the roster
-- the client already holds: no new traffic, no new sharing settings, and only
-- characters the viewer may already see on the Characters page.
WoWStatusCompare = {}
local C, S = WoWStatusCompare, WoWStatusSafe
local T, TF = WoWStatusLocale.T, WoWStatusLocale.F
local page, registered
local left, right
local function key(name) return WoWStatusRoster.key(name) end
-- Every character the viewer may pick: their own first, then the group's.
-- R.groups() has already left out hidden characters, so this list cannot show
-- somebody a bank alt its owner ticked away.
function C.candidates()
    local list, seen = {}, {}
    for _, group in ipairs(WoWStatusRoster.groups()) do
        for _, row in ipairs(group.rows) do
            local k = key(row.name)
            if k and not seen[k] then
                seen[k] = true
                list[#list + 1] = {name = row.name, row = row, mine = WoWStatusPopups.isSelf(row.name) == true,
                    label = (row.name:match("^[^%-]+") or row.name) .. (row.level and (" · " .. row.level) or "")}
            end
        end
    end
    return list
end
local function find(name)
    for _, item in ipairs(C.candidates()) do
        if key(item.name) == key(name or "") then return item end
    end
    return nil
end
-- A value nobody shared is not a zero. Rows say so instead of inventing one.
local NOT_SHARED = "not shared"
-- {label, read(row) -> number or nil, format(number), better = "high"|"low"|nil}
local MEASURES = {
    {"Level", function(row) return S.number(row.level) end, tostring, "high"},
    {"XP into the level", function(row) local xp = S.number(row.xp); return xp and math.floor(xp / 10) end,
        function(value) return value .. "%" end, "high"},
    {"Quests", function(row) return S.number(row.quests) end, tostring, "high"},
    {"Deaths", function(row) return S.number(row.deaths) end, tostring, "low"},
    {"Monsters killed", function(row) return S.number(row.kills) end, tostring, "high"},
    {"Dungeons cleared", function(row) return S.number(row.dungeons) end, tostring, "high"},
    {"Mounts", function(row) return S.number(row.mounts) end, tostring, "high"},
    {"Honorable kills", function(row) return S.number(row.honor_kills) end, tostring, "high"},
    -- More playing is not better than less, so no side wins this row.
    {"Played", function(row) return S.number(row.played) end, function(value) return WoWStatusUI.duration(value) end},
    -- The interesting row: are they faster, or just playing more?
    {"Played per level", function(row)
        local played, level = S.number(row.played), S.number(row.level)
        return played and level and level > 1 and math.floor(played / level) or nil
    end, function(value) return WoWStatusUI.duration(value) end, "low"},
    {"Gold", function(row) return S.number(row.gold) end, function(value) return WoWStatusUI.money(value) end, "high"},
}
-- The two columns and one row per measure:
-- {label, left, right, gap, winner = 1 | 2 | nil}. A row neither side shared is
-- left out: an empty table says more than eleven "not shared" lines.
function C.data(one, two)
    local a, b = find(one), find(two)
    local rows = {}
    for _, measure in ipairs(MEASURES) do
        local label, read, format, better = measure[1], measure[2], measure[3], measure[4]
        local x = a and read(a.row) or nil
        local y = b and read(b.row) or nil
        if x ~= nil or y ~= nil then
            local winner, gap
            if x ~= nil and y ~= nil and better and x ~= y then
                winner = ((x > y) == (better == "high")) and 1 or 2
                gap = format(math.abs(x - y))
            end
            rows[#rows + 1] = {label = label, winner = winner, gap = gap,
                left = x ~= nil and format(x) or nil, right = y ~= nil and format(y) or nil}
        end
    end
    return {left = a, right = b, rows = rows}
end
-- How fresh a column is: the status line the Characters page and the profile
-- already show. The roster keeps no capture time per value.
function C.freshness(item)
    if not item then return "" end
    return T(item.row.status or "Never met")
end
local function render()
    if not page then return end
    local data = C.data(left, right)
    local function name(item)
        if not item then return T("Choose a character") end
        local short = (item.name:match("^[^%-]+") or item.name):gsub("|", "||")
        local colour = WoWStatusUI.classColour(item.row.class)
        return colour and (colour .. short .. "|r") or short
    end
    page.leftPick:SetText(name(data.left))
    page.rightPick:SetText(name(data.right))
    page.leftWhen:SetText(C.freshness(data.left))
    page.rightWhen:SetText(C.freshness(data.right))
    WoWStatusUI.call(page.swap, "SetEnabled", data.left ~= nil and data.right ~= nil)
    page.empty:SetShown(#data.rows == 0)
    page.empty:SetText(data.left and data.right and T("Neither of them has shared any numbers yet.")
        or T("Choose two characters to put their numbers side by side."))
    for i, row in ipairs(page.rows) do
        local item = data.rows[i]
        row:SetShown(item ~= nil)
        if item then
            row.label:SetText(T(item.label))
            local function cell(value, mine)
                if value == nil then return WoWStatusUI.MUTED_CODE .. "" .. T(NOT_SHARED) .. "|r" end
                return (item.winner == mine and "|cff40ff40" or "") .. value .. (item.winner == mine and "|r" or "")
            end
            row.left:SetText(cell(item.left, 1))
            row.right:SetText(cell(item.right, 2))
            row.gap:SetText(item.gap and ("|cffffd100" .. item.gap .. "|r") or "")
        end
    end
end
C.render = render
local function pick(side)
    return function(self)
        local items = {}
        for _, item in ipairs(C.candidates()) do items[#items + 1] = {label = item.label, value = item.name} end
        if #items == 0 then return end
        WoWStatusUI.menu(self, items, function(value)
            if side == 1 then left = value else right = value end
            render()
        end, 180)
    end
end
local function build(parent)
    local UI = WoWStatusUI
    page = CreateFrame("Frame", "WoWStatusComparePage", parent); page:SetAllPoints(parent)
    UI.text(page, "GameFontNormalLarge", 24, -12, 400):SetText(T("Compare"))
    page.leftPick = CreateFrame("Button", nil, page, "UIPanelButtonTemplate")
    page.leftPick:SetPoint("TOPLEFT", 24, -44); page.leftPick:SetSize(200, 26)
    page.leftPick:SetScript("OnClick", pick(1))
    page.rightPick = CreateFrame("Button", nil, page, "UIPanelButtonTemplate")
    page.rightPick:SetPoint("TOPLEFT", 304, -44); page.rightPick:SetSize(200, 26)
    page.rightPick:SetScript("OnClick", pick(2))
    page.swap = CreateFrame("Button", nil, page, "UIPanelButtonTemplate")
    page.swap:SetPoint("TOPLEFT", 584, -44); page.swap:SetSize(140, 26); page.swap:SetText(T("Swap sides"))
    page.swap:SetScript("OnClick", function() left, right = right, left; render() end)
    page.leftWhen = UI.text(page, "GameFontHighlightSmall", 24, -74, 200)
    page.rightWhen = UI.text(page, "GameFontHighlightSmall", 304, -74, 200)
    page.empty = UI.text(page, "GameFontHighlightLarge", 24, -140, 660)
    page.rows = {}
    for i = 1, #MEASURES do
        local row = CreateFrame("Frame", nil, page)
        row:SetPoint("TOPLEFT", 24, -104 - (i - 1) * 34); row:SetSize(700, 30)
        row.label = UI.text(row, "GameFontNormal", 0, -6, 200)
        row.left = UI.text(row, "GameFontHighlight", 206, -6, 140, "RIGHT")
        row.right = UI.text(row, "GameFontHighlight", 356, -6, 140, "RIGHT")
        row.gap = UI.text(row, "GameFontHighlight", 520, -6, 160)
        page.rows[i] = row
    end
    return page
end
-- No tab: the tab row is full, so /wstatus compare and the Leaderboard button
-- open it. Registered once the main window's file has loaded, as Diagnostics does.
local function register()
    if registered or type(WoWStatusMainWindow) ~= "table" then return end
    registered = WoWStatusMainWindow.register("compare", "Compare", build, render, {tab = false}) and true
end
C.register = register
-- show(other): the viewer's own character against other, or the pickers as they were.
function C.show(other)
    register()
    local candidates = C.candidates()
    if other and find(other) then right = find(other).name end
    if not left then
        -- Default to the character the viewer is playing.
        for _, item in ipairs(candidates) do
            if item.mine then left = item.name; break end
        end
        left = left or (candidates[1] and candidates[1].name) or nil
    end
    if left and not right then
        for _, item in ipairs(candidates) do
            if key(item.name) ~= key(left) then right = item.name; break end
        end
    end
    if WoWStatusMainWindow then return WoWStatusMainWindow.show("compare") end
    return false
end
