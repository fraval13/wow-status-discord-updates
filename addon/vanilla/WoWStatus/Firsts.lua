-- "Firsts" medals (#65): the first character in the log to reach a milestone.
-- Worked out from the activity log only, ordered by event time and then by
-- event ID, so every client with the same log after sync agrees. The log
-- already holds only entries from after each group was joined. A friend's new
-- First is announced with its own popup only when it arrived live and recently;
-- entries recovered by login sync update the Records page quietly.
WoWStatusFirsts = {}
local F, S = WoWStatusFirsts, WoWStatusSafe
local T, TF = WoWStatusLocale.T, WoWStatusLocale.F
local ANNOUNCE_WITHIN = 600
local page

local function name(sender) return (tostring(sender or "?"):match("^[^-]+") or "?") end

function F.medals()
    local list = {}
    local maximum = WoWStatusAdapter and WoWStatusAdapter.max_level or 60
    for level = 10, maximum, 10 do
        table.insert(list, {key="level:" .. level, title="First to reach level " .. level,
            match=function(e) return e.kind == "level" and S.number(e.level) == level end})
    end
    if maximum % 10 ~= 0 then
        table.insert(list, {key="level:" .. maximum, title="First to reach level " .. maximum,
            match=function(e) return e.kind == "level" and S.number(e.level) == maximum end})
    end
    local function kind(key, title, wanted, extra)
        table.insert(list, {key=key, title=title,
            match=function(e) return e.kind == wanted and (not extra or extra(e)) end})
    end
    -- A group record, not the character's first death: the death popup next to it
    -- shows the lifetime total ("Total deaths: 33"), so the title must say "group".
    kind("death", "First in the group to die", "death")
    kind("dungeon", "First dungeon clear", "dungeon")
    kind("mount", "First mount", "mount")
    kind("raid", "First raid boss", "raid")
    kind("epicmount", "First epic mount", "epicmount")
    kind("epic", "First epic item", "loot", function(e) return (S.number(e.quality) or 0) >= 4 end)
    kind("artisan", "First Artisan profession", "profession", function(e)
        local maximum = tonumber(tostring(e.text or ""):match("%((%d+) max%)$"))
        return maximum ~= nil and maximum >= 300
    end)
    return list
end

-- Medal key -> winning entry. Ties: earlier time, then the smaller event ID.
-- With a group, only entries shared in that group count: each group has its own records.
function F.compute(entries, group)
    local sorted = {}
    for _, e in ipairs(entries or {}) do
        -- Imported pre-installation history is local only, so peers' logs would disagree.
        if type(e) == "table" and type(e.at) == "number" and type(e.id) == "string" and not e.imported
            and (not group or (type(e.groups) == "table" and e.groups[group]))
            and (not WoWStatusJournal.visible or WoWStatusJournal.visible(e)) then
            table.insert(sorted, e)
        end
    end
    table.sort(sorted, function(a, b) if a.at == b.at then return a.id < b.id end return a.at < b.at end)
    local medals, result = F.medals(), {}
    for _, e in ipairs(sorted) do
        for _, medal in ipairs(medals) do
            if not result[medal.key] and medal.match(e) then result[medal.key] = e end
        end
    end
    -- Level records also count milestones from members' synced character lists,
    -- so a level reached before the log (or before joining) still counts. The
    -- earliest time wins; on a tie the logged entry stays.
    if group and WoWStatusRoster and WoWStatusRoster.milestoneHolders then
        for _, medal in ipairs(medals) do
            local level = tonumber(medal.key:match("^level:(%d+)$"))
            if level then
                local best = result[medal.key]
                local holders = WoWStatusRoster.milestoneHolders(group, level)
                table.sort(holders, function(a, b) if a.at == b.at then return a.name < b.name end return a.at < b.at end)
                local h = holders[1]
                if h and (not best or h.at < best.at) then
                    result[medal.key] = {id="milestone:" .. group .. ":" .. level .. ":" .. (WoWStatusPopups.senderKey(h.name) or h.name),
                        sender=h.name, at=h.at, kind="level", level=level, milestone=true, exact=h.exact}
                end
            end
        end
    end
    return result, medals
end

-- Whether an entry can change the Records page: a possible medal holder or a
-- session recap. The log recounts the medals only when such an entry comes or
-- goes, so a long catch-up doesn't redo the whole-log sort per entry (#4).
function F.matters(e)
    if type(e) ~= "table" then return false end
    if e.kind == "recap" then return true end
    for _, medal in ipairs(F.medals()) do if medal.match(e) then return true end end
    return false
end

local function state()
    if type(WoWStatusDB) ~= "table" then return nil end
    if type(WoWStatusDB.firsts) ~= "table" then WoWStatusDB.firsts = {} end
    if type(WoWStatusDB.firsts.holders) ~= "table" then WoWStatusDB.firsts.holders = {} end
    return WoWStatusDB.firsts
end

-- Icon for a medal, from the same vocabulary as popups and the activity log.
local MEDAL_ITEMS = {death={kind="death"}, dungeon={kind="dungeon"}, mount={kind="mount"}, raid={kind="raid"},
    epicmount={kind="epicmount"}, epic={kind="loot", quality=4}, artisan={kind="profession", text="Tailoring: Artisan"}}
local function medalIcon(medal)
    local item = medal.key:match("^level:") and {kind="level", level=10} or MEDAL_ITEMS[medal.key] or {kind="first"}
    return (WoWStatusPresentation.theme(item))
end

local CARD_W, CARD_H, GAP = 336, 56, 8
local function card(index)
    local UI = WoWStatusUI
    local c = UI.box(page.list, CARD_W, CARD_H)
    c.icon = UI.icon(c, 40); c.icon:SetPoint("TOPLEFT", 8, -8)
    c.title = UI.text(c, "GameFontNormal", 56, -10, 270)
    c.holder = UI.text(c, "GameFontHighlightSmall", 56, -32, 270)
    page.rows[index] = c
    return c
end

-- The selected group tab, kept when it still exists.
local function selectedGroup(groups)
    local data = state() or {}
    for _, group in ipairs(groups) do if group.id == data.tab then return group end end
    return groups[1]
end
local function tabs(groups, chosen)
    local UI = WoWStatusUI
    page.tabs = page.tabs or {}
    for i, group in ipairs(groups) do
        local tab = page.tabs[i]
        if not tab then
            tab = CreateFrame("Button", nil, page, "UIPanelButtonTemplate")
            tab:SetSize(128, 24)
            tab:SetScript("OnClick", function(self)
                local data = state()
                if data then data.tab = self.group end
                F.render()
            end)
            page.tabs[i] = tab
        end
        tab:ClearAllPoints(); tab:SetPoint("TOPLEFT", 24 + ((i - 1) % 5) * 134, -4 - math.floor((i - 1) / 5) * 28)
        tab.group = group.id
        tab:SetText(group.label)
        UI.call(tab, "SetEnabled", group ~= chosen)
        tab:Show()
    end
    for i = #groups + 1, #page.tabs do page.tabs[i]:Hide() end
    return math.ceil(#groups / 5) * 28
end

-- The Leaderboard view: everyone in the group, sorted by level, deaths or quests.
local SORTS = {{"level", "Level"}, {"deaths", "Deaths"}, {"quests", "Quests"}}
local function sorted(list, by)
    table.sort(list, function(a, b)
        local x, y = a[by] or -1, b[by] or -1
        if x ~= y then return x > y end
        if by == "level" and (a.xp or -1) ~= (b.xp or -1) then return (a.xp or -1) > (b.xp or -1) end
        return a.name < b.name
    end)
    return list
end
local function boardRow(index)
    local UI = WoWStatusUI
    local row = CreateFrame("Frame", nil, page.list)
    row:SetSize(680, 26)
    row.bg = row:CreateTexture(nil, "BACKGROUND"); row.bg:SetAllPoints()
    row.rank = UI.text(row, "GameFontNormal", 8, -6, 30)
    row.name = UI.text(row, "GameFontHighlight", 44, -6, 260)
    row.level = UI.text(row, "GameFontHighlight", 310, -6, 130)
    row.deaths = UI.text(row, "GameFontHighlight", 450, -6, 100, "RIGHT")
    row.quests = UI.text(row, "GameFontHighlight", 560, -6, 110, "RIGHT")
    page.board[index] = row
    return row
end
local function renderBoard(chosen)
    local data, UI = state() or {}, WoWStatusUI
    local by = data.sort or "level"
    local list = chosen and sorted(WoWStatusRoster.leaderboard(chosen.id), by) or {}
    page.board = page.board or {}
    for i, entry in ipairs(list) do
        local row = page.board[i] or boardRow(i)
        row:ClearAllPoints(); row:SetPoint("TOPLEFT", 0, -(i - 1) * 28)
        row.bg:SetColorTexture(1, .82, 0, entry.own and .12 or (i % 2 == 0 and .04 or 0))
        row.rank:SetText(i .. ".")
        local name = (entry.name:match("^[^-]+") or entry.name):gsub("|", "||")
        local colour = UI.classColour(entry.class)
        row.name:SetText((entry.online and "|cff40ff40•|r " or "  ") .. (colour and (colour .. name .. "|r") or name))
        row.level:SetText(entry.level and (TF("Level %d", entry.level) .. (entry.xp and (" (" .. math.floor(entry.xp / 10) .. " %)") or "")) or "–")
        row.deaths:SetText(entry.deaths and tostring(entry.deaths) or "–")
        row.quests:SetText(entry.quests and tostring(entry.quests) or "–")
        row:Show()
    end
    for i = #list + 1, #page.board do page.board[i]:Hide() end
    page.boardHeader:SetShown(true)
    page.list:SetHeight(math.max(1, #list * 28))
    page.boardEmpty:SetShown(#list == 0)
    page.sort:SetText(T("Sort:") .. " " .. T(by == "deaths" and "Deaths" or by == "quests" and "Quests" or "Level"))
end

local function render()
    if not page then return end
    local UI = WoWStatusUI
    local groups = F.groups()
    local chosen = selectedGroup(groups)
    local top = tabs(groups, chosen)
    -- Firsts or Leaderboard, remembered.
    local data = state() or {}
    local board = data.view == "leaderboard"
    UI.call(page.viewFirsts, "SetEnabled", board); UI.call(page.viewBoard, "SetEnabled", not board)
    page.viewFirsts:ClearAllPoints(); page.viewFirsts:SetPoint("TOPLEFT", 430, -4 - top)
    page.viewBoard:ClearAllPoints(); page.viewBoard:SetPoint("TOPLEFT", 540, -4 - top)
    page.sort:ClearAllPoints(); page.sort:SetPoint("TOPLEFT", 280, -4 - top)
    page.sort:SetShown(board); page.boardHeader:SetShown(false); page.boardEmpty:SetShown(false)
    if page.board then for _, row in ipairs(page.board) do row:Hide() end end
    for _, row in ipairs(page.rows) do row:SetShown(not board) end
    if page.recapBox then page.recapBox:SetShown(not board) end
    if board then
        page.heading:ClearAllPoints(); page.heading:SetPoint("TOPLEFT", 24, -8 - top)
        page.heading:SetText(chosen and (T("Leaderboard") .. " · " .. chosen.label:gsub("|", "||"))
            or T("Join a group to compete for records with your friends."))
        page.boardHeader:ClearAllPoints(); page.boardHeader:SetPoint("TOPLEFT", 24, -38 - top)
        page.scroll:ClearAllPoints(); page.scroll:SetPoint("TOPLEFT", 24, -60 - top)
        page.scroll:SetHeight(470 - top)
        page.group = chosen and chosen.id
        renderBoard(chosen)
        return
    end
    page.heading:ClearAllPoints(); page.heading:SetPoint("TOPLEFT", 24, -8 - top)
    page.heading:SetText(chosen and (T("Firsts in") .. " " .. chosen.label:gsub("|", "||"))
        or T("Join a group to compete for records with your friends."))
    page.scroll:ClearAllPoints(); page.scroll:SetPoint("TOPLEFT", 24, -36 - top)
    page.scroll:SetHeight(494 - top)
    page.group = chosen and chosen.id
    local result, medals = F.compute(WoWStatusJournal.entries(), chosen and chosen.id or "")
    for i, medal in ipairs(medals) do
        local c = page.rows[i] or card(i)
        local column, line = (i - 1) % 2, math.floor((i - 1) / 2)
        c:ClearAllPoints(); c:SetPoint("TOPLEFT", column * (CARD_W + GAP), -line * (CARD_H + GAP))
        local e = result[medal.key]
        c.icon:SetIcon(medalIcon(medal), e == nil)
        c.title:SetText(T(medal.title))
        local when = e and WoWStatusHistory.oslo(e.at):sub(1, 16)
        -- Reached before WoW Status tracked it: the date is "by then".
        if e and e.milestone and not e.exact then when = T("before WoW Status, by") .. " " .. when:sub(1, 10) end
        local holder = e and (name(e.sender):gsub("|", "||") .. " · " .. when) or T("nobody yet")
        c.holder:SetText(e and holder or ("|cff808080" .. holder .. "|r"))
        UI.tint(c, e ~= nil)
        c.text = medal.title .. " — " .. holder -- Plain summary of the card.
        c:Show()
    end
    for i = #medals + 1, #page.rows do page.rows[i]:Hide() end
    local medalsHeight = math.ceil(#medals / 2) * (CARD_H + GAP)
    -- Session recaps (#66): your newest ones in their own box below the medals.
    local lines = {}
    for _, e in ipairs(WoWStatusJournal.entries()) do
        if e.kind == "recap" and #lines < 10 and WoWStatusJournal.visible(e) then
            table.insert(lines, "|cffffd100" .. WoWStatusHistory.oslo(e.at):sub(1, 16) .. "|r  " .. T(e.text):gsub("|", "||"))
        end
    end
    if #lines == 0 then table.insert(lines, T("No recaps yet. One is written after each play session.")) end
    local box = page.recapBox
    if not box then
        box = UI.box(page.list, 2 * CARD_W + GAP, 40); page.recapBox = box
        box.title = UI.header(box, T("Session recaps"), 12, -10, 2 * CARD_W + GAP - 24)
        page.recaps = {}
    end
    box:ClearAllPoints(); box:SetPoint("TOPLEFT", 0, -(medalsHeight + 6))
    for i, text in ipairs(lines) do
        local row = page.recaps[i]
        if not row then row = UI.text(box, "GameFontHighlight", 12, 0, 2 * CARD_W - 20); page.recaps[i] = row end
        row:ClearAllPoints(); row:SetPoint("TOPLEFT", 12, -14 - i * 22)
        row:SetText(text); row:Show()
    end
    for i = #lines + 1, #page.recaps do page.recaps[i]:Hide() end
    box:SetHeight(40 + #lines * 22)
    page.list:SetHeight(medalsHeight + 52 + #lines * 22)
end
F.render = render
F.medalIcon = medalIcon

-- Called after the log changes. Announces only medals newly won by a live entry.
-- This account's groups, sorted by their labels: {id, label}.
function F.groups()
    local list = {}
    local character = WoWStatusPopups and WoWStatusPopups.character and WoWStatusPopups.character()
    for id, member in pairs(WoWStatusGroups.selected(character)) do
        table.insert(list, {id=id, label=member.label or id})
    end
    table.sort(list, function(a, b) return S.lowerASCII(a.label) < S.lowerASCII(b.label) end)
    return list
end

function F.update()
    local data = state()
    if not data or not WoWStatusJournal.entries then return end
    data.group_holders = type(data.group_holders) == "table" and data.group_holders or {}
    local entries, announced = WoWStatusJournal.entries(), {}
    for _, group in ipairs(F.groups()) do
        local result, medals = F.compute(entries, group.id)
        -- The very first count stays quiet; later only live, recent entries are announced.
        local quiet = not data.initialized
        for _, medal in ipairs(medals) do
            local e = result[medal.key]
            local holderKey = group.id .. ":" .. medal.key
            local previous = data.group_holders[holderKey]
            if e and previous ~= e.id then
                data.group_holders[holderKey] = e.id
                -- Recent by realm time, or by this PC's clock for an older peer's stamp.
                -- One popup per entry and medal, even when it wins in several groups.
                local seen = e.id .. ":" .. medal.key
                if not quiet and previous == nil and e.origin == "live" and not announced[seen]
                    and not S.outside(e.at, ANNOUNCE_WITHIN, math.huge) and WoWStatusPopups.notice then
                    announced[seen] = true
                    WoWStatusPopups.notice({sender=e.sender, kind="first", text=medal.title .. "!",
                        flavour=T("A new record in") .. " " .. group.label:gsub("|", "||") .. "."})
                end
            end
        end
    end
    data.initialized = true
    if WoWStatusMainWindow then WoWStatusMainWindow.refresh("records") end
end

function F.buildRecords(parent)
    page = CreateFrame("Frame", "WoWStatusRecordsPage", parent); page:SetAllPoints(parent)
    page.heading = page:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
    page.heading:SetPoint("TOPLEFT", 24, -4); page.heading:SetText("Firsts in your group")
    page.scroll = CreateFrame("ScrollFrame", nil, page, "UIPanelScrollFrameTemplate")
    page.scroll:SetPoint("TOPLEFT", 24, -32); page.scroll:SetSize(710, 494)
    page.list = CreateFrame("Frame", nil, page.scroll); page.list:SetSize(686, 24)
    page.scroll:SetScrollChild(page.list)
    page.rows = {}
    local function button(label, width, fn)
        local b = CreateFrame("Button", nil, page, "UIPanelButtonTemplate")
        b:SetSize(width, 24); b:SetText(T(label)); b:SetScript("OnClick", fn)
        return b
    end
    page.viewFirsts = button("Firsts", 104, function() local d = state(); if d then d.view = "firsts" end; F.render() end)
    page.viewBoard = button("Leaderboard", 120, function() local d = state(); if d then d.view = "leaderboard" end; F.render() end)
    page.sort = button("", 140, function()
        local d = state()
        if not d then return end
        local index = 1
        for i, s in ipairs(SORTS) do if s[1] == (d.sort or "level") then index = i end end
        d.sort = SORTS[index % #SORTS + 1][1]
        F.render()
    end)
    local UI = WoWStatusUI
    page.boardHeader = CreateFrame("Frame", nil, page); page.boardHeader:SetSize(680, 20)
    UI.text(page.boardHeader, "GameFontNormal", 44, 0, 260):SetText(T("Character"))
    UI.text(page.boardHeader, "GameFontNormal", 310, 0, 130):SetText(T("Level"))
    UI.text(page.boardHeader, "GameFontNormal", 450, 0, 100, "RIGHT"):SetText(T("Deaths"))
    UI.text(page.boardHeader, "GameFontNormal", 560, 0, 110, "RIGHT"):SetText(T("Quests"))
    page.boardHeader:Hide()
    page.boardEmpty = UI.text(page.list, "GameFontDisable", 0, -6, 660)
    page.boardEmpty:SetText(T("Nobody in this group yet. Members appear when their character list arrives."))
    page.boardEmpty:Hide()
    return page
end

WoWStatusMainWindow.register("records", "Records", F.buildRecords, render)
