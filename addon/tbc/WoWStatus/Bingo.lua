-- A weekly Labs board built from the local copy of a group's activity.
WoWStatusBingo = {}
local B, F, S = WoWStatusBingo, WoWStatusFeatures, WoWStatusSafe
local T, TF = WoWStatusLocale.T, WoWStatusLocale.F
local ID = "weeklyBingo"
local SIZE = 5
local rules = {
    {"level", "Gain a level"}, {"death", "An ordinary death"},
    {"zone", "Discover a zone"}, {"quest", "Reach a quest milestone"},
    {"profession", "Reach a profession milestone"}, {"loot", "Equip eligible armor"},
    {"dungeon", "Clear a dungeon"}, {"raid", "Defeat a raid boss"},
    {"mount", "Ride a first mount"}, {"epicmount", "Get a first epic mount"},
    {"reputation", "Earn a reputation rank"}, {"unlock", "Learn a class ability"},
    {"pvp", "Earn a PvP rank"}, {"introduction", "Join the WoW Status group"},
}
local function rule(kind, label, matches)
    rules[#rules + 1] = {kind, label, matches}
end
local function levelSquare(low, high)
    rule("level", function() return TF("Reach a level from %d to %d", low, high) end,
        function(e) return e.level and e.level >= low and e.level <= high end)
end
local cap = WoWStatusAdapter.max_level
for low = 1, cap, 10 do levelSquare(low, math.min(cap, low + 9)) end
for _, item in ipairs({{3, "Equip rare armor"}, {4, "Equip epic armor"}, {5, "Equip legendary armor"}}) do
    local quality = item[1]
    rule("loot", item[2], function(e) return e.quality == quality end)
end
local function prefix(kind, label, text)
    rule(kind, label, function(e) return (e.text or ""):sub(1, #text) == text end)
end
prefix("profession", "Learn a new profession", "Learned ")
prefix("mount", "Take a first mount ride", "First mount ride")
for _, item in ipairs({
    {0, 6, "from midnight to dawn"}, {6, 12, "in the morning"},
    {12, 18, "in the afternoon"}, {18, 24, "in the evening"},
}) do
    local low, high, label = item[1], item[2], item[3]
    for _, kind in ipairs({"level", "zone", "quest"}) do
        local labels = {level="Level up %s",zone="Discover a zone %s",quest="Reach a quest milestone %s"}
        rule(kind, function() return TF(labels[kind], T(label)) end, function(_, _, stamp)
            local hour = tonumber(stamp:sub(12, 13))
            return hour and hour >= low and hour < high
        end)
    end
end

local function displayLabel(square)
    local label = square[2]
    if type(label) == "function" then return label() end
    return T(label)
end

-- The stored group ID is already hashed. A private deterministic shuffle avoids
-- changing the game's RNG, and the shared calendar gives peers the same week.
function B.draw(group, week)
    local seed, pool, result = 1, {}, {}
    local input = group .. week
    for i = 1, #input do seed = (seed * 131 + input:byte(i)) % 2147483647 end
    for _, square in ipairs(rules) do pool[#pool + 1] = square end
    for i = 1, SIZE * SIZE do
        seed = (seed * 48271) % 2147483647
        local pick = seed % #pool + 1
        result[i] = table.remove(pool, pick)
    end
    return result
end

function B.won(filled)
    local diagonal, reverse = true, true
    for y = 0, SIZE - 1 do
        local row, column = true, true
        for x = 1, SIZE do
            row = row and filled[y * SIZE + x]
            column = column and filled[(x - 1) * SIZE + y + 1]
        end
        if row or column then return true end
        diagonal = diagonal and filled[y * SIZE + y + 1]
        reverse = reverse and filled[y * SIZE + SIZE - y]
    end
    return not not (diagonal or reverse)
end

function B.fill(board, group, first, last, entries, excluded)
    local J, filled = WoWStatusJournal, {}
    for _, e in ipairs(entries) do
        if e.id ~= excluded and type(e.sender) == "string" and S.number(e.at)
            and type(e.groups) == "table" and e.groups[group] and J.visible(e)
            and not WoWStatusProgress.hardcoreDeath(e) then
            local stamp = WoWStatusHistory.oslo(e.at)
            local day = stamp:sub(1, 10)
            if day >= first and day <= last then
                for i, square in ipairs(board) do
                    local previous = filled[i]
                    if square[1] == e.kind and (not previous or e.at < previous.at
                        or (e.at == previous.at and e.sender < previous.sender))
                        and (not square[3] or square[3](e, day, stamp)) then
                        filled[i] = e
                    end
                end
            end
        end
    end
    return filled
end

local winners, winnerWeek = {}, nil
local function active() return F.enabled(ID) end
function B.update(entry)
    if not active() then return end
    local first, last = WoWStatusFirsts.weekRange()
    if first ~= winnerWeek then winners, winnerWeek = {}, first end
    if entry and (entry.origin == "live" or entry.origin == "mine") then
        for _, group in ipairs(WoWStatusFirsts.groups()) do
            local id = group.id
            if not winners[id] and entry.groups and entry.groups[id] then
                local board, entries = B.draw(id, first), WoWStatusJournal.entries()
                if B.won(B.fill(board, id, first, last, entries)) then
                    winners[id] = true
                    if not B.won(B.fill(board, id, first, last, entries, entry.id)) then
                        WoWStatusPopups.notice({kind="first", text=T("Bingo!"), sender=entry.sender,
                            flavour=T("Your group completed a bingo line.")})
                    end
                end
            end
        end
    end
    WoWStatusMainWindow.refresh("bingo")
end

local function refresh(page)
    local groups = active() and WoWStatusFirsts.groups() or {}
    local selected = page.selected
    local group = groups[selected] or groups[1]
    if groups[selected] == nil then page.selected = 1 end
    local first, last = WoWStatusFirsts.weekRange()
    page.heading:SetText(group and (group.label:gsub("|", "||") .. " · " .. first)
        or T("Join a group to see its bingo card."))
    WoWStatusUI.call(page.nextGroup, "SetEnabled", #groups > 1)
    local board = group and B.draw(group.id, first)
    local filled = board and B.fill(board, group.id, first, last, WoWStatusJournal.entries())
    page.detail:SetText(filled and B.won(filled) and T("Bingo!") or "")
    for i, cell in ipairs(page.cells) do
        cell:SetShown(board ~= nil)
        if board then
            local label = displayLabel(board[i])
            local sender = filled[i] and filled[i].sender:gsub("|", "||")
            cell.label:SetText(label)
            cell.sender:SetText(sender and (sender:match("^[^-]+") or sender) or "")
            cell.detail = sender and (label .. " · " .. sender) or label
        end
    end
end

local function build(parent)
    local UI = WoWStatusUI
    local page = CreateFrame("Frame", nil, parent)
    page:SetAllPoints(parent)
    page.selected, page.cells = 1, {}
    page.heading = UI.text(page, "GameFontNormalLarge", 24, -12, 540)
    page.nextGroup = CreateFrame("Button", nil, page, "UIPanelButtonTemplate")
    page.nextGroup:SetPoint("TOPLEFT", 610, -8); page.nextGroup:SetSize(120, 26)
    page.nextGroup:SetText(T("Next group"))
    page.nextGroup:SetScript("OnClick", function()
        local count = #WoWStatusFirsts.groups()
        if count > 1 then page.selected = page.selected % count + 1; refresh(page) end
    end)
    for i = 1, SIZE * SIZE do
        local cell = CreateFrame("Button", nil, page, "UIPanelButtonTemplate")
        cell:SetSize(136, 72)
        cell:SetPoint("TOPLEFT", 24 + (i - 1) % SIZE * 142, -48 - math.floor((i - 1) / SIZE) * 78)
        cell.label = UI.text(cell, "GameFontHighlightSmall", 6, -7, 124, "CENTER")
        cell.sender = UI.text(cell, "GameFontNormalSmall", 6, -51, 124, "CENTER")
        cell:SetScript("OnClick", function(self) page.detail:SetText(self.detail) end)
        page.cells[i] = cell
    end
    page.detail = UI.text(page, "GameFontHighlight", 24, -454, 706)
    return page
end

local function open()
    if not active() then return end
    local window = WoWStatusMainWindow
    if not window.has("bingo") then window.register("bingo", "Weekly group bingo", build, refresh, {tab=false}) end
    window.show("bingo")
end

F.register(ID, "Weekly group bingo", "Fill a bingo card from your group's weekly activity.", open)
