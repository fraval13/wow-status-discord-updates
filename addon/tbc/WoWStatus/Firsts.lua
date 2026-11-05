-- "Firsts" medals (#65): the first character in the log to reach a milestone.
-- Worked out from the activity log only, ordered by event time and then by
-- event ID, so every client with the same log after sync agrees. The log
-- already holds only entries from after each group was joined. A friend's new
-- First is announced with its own popup only when it arrived live and recently;
-- entries recovered by login sync update the Records page quietly.
WoWStatusFirsts = {}
local F, S = WoWStatusFirsts, WoWStatusSafe
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
    kind("death", "First death", "death")
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
function F.compute(entries)
    local sorted = {}
    for _, e in ipairs(entries or {}) do
        -- Imported pre-installation history is local only, so peers' logs would disagree.
        if type(e) == "table" and type(e.at) == "number" and type(e.id) == "string" and not e.imported
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

local function render()
    if not page then return end
    local result, medals = F.compute(WoWStatusJournal.entries())
    for i, medal in ipairs(medals) do
        local row = page.rows[i]
        if not row then
            row = page.list:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
            row:SetPoint("TOPLEFT", 0, -(i - 1) * 24); row:SetWidth(680); row:SetJustifyH("LEFT")
            page.rows[i] = row
        end
        local e = result[medal.key]
        row:SetText("|cffffd100" .. medal.title .. "|r — " .. (e and (name(e.sender):gsub("|", "||")
            .. " · " .. WoWStatusHistory.oslo(e.at)) or "nobody yet"))
        row:Show()
    end
    -- Session recaps (#66): your newest ones below the medals.
    local lines = {"", "|cffffd100Session recaps|r"}
    for _, e in ipairs(WoWStatusJournal.entries()) do
        if e.kind == "recap" and #lines < 12 and WoWStatusJournal.visible(e) then
            table.insert(lines, WoWStatusHistory.oslo(e.at):sub(1, 16) .. "  " .. e.text:gsub("|", "||"))
        end
    end
    if #lines == 2 then table.insert(lines, "No recaps yet. One is written after each play session.") end
    page.recaps = page.recaps or {}
    for i, text in ipairs(lines) do
        local row = page.recaps[i]
        if not row then
            row = page.list:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
            row:SetWidth(680); row:SetJustifyH("LEFT")
            page.recaps[i] = row
        end
        row:ClearAllPoints(); row:SetPoint("TOPLEFT", 0, -(#medals + i - 1) * 24)
        row:SetText(text); row:Show()
    end
    for i = #lines + 1, #page.recaps do page.recaps[i]:Hide() end
    page.list:SetHeight((#medals + #lines) * 24)
end
F.render = render

-- Called after the log changes. Announces only medals newly won by a live entry.
function F.update()
    local data = state()
    if not data or not WoWStatusJournal.entries then return end
    local result, medals = F.compute(WoWStatusJournal.entries())
    local quiet = not data.initialized
    for _, medal in ipairs(medals) do
        local e = result[medal.key]
        local previous = data.holders[medal.key]
        if e and previous ~= e.id then
            data.holders[medal.key] = e.id
            -- Recent by realm time, or by this PC's clock for an older peer's stamp.
            if not quiet and previous == nil and e.origin == "live"
                and not S.outside(e.at, ANNOUNCE_WITHIN, math.huge) and WoWStatusPopups.notice then
                WoWStatusPopups.notice({sender=e.sender, kind="first", text=medal.title .. "!",
                    flavour="A new record on the Records page."})
            end
        end
    end
    data.initialized = true
    if WoWStatusMainWindow then WoWStatusMainWindow.refresh("records") end
end

function F.buildRecords(parent)
    page = CreateFrame("Frame", "WoWStatusRecordsPage", parent); page:SetAllPoints(parent)
    page.heading = page:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
    page.heading:SetPoint("TOPLEFT", 24, -4); page.heading:SetText("Firsts and session recaps")
    page.scroll = CreateFrame("ScrollFrame", nil, page, "UIPanelScrollFrameTemplate")
    page.scroll:SetPoint("TOPLEFT", 24, -36); page.scroll:SetSize(710, 490)
    page.list = CreateFrame("Frame", nil, page.scroll); page.list:SetSize(686, 24)
    page.scroll:SetScrollChild(page.list)
    page.rows = {}
    return page
end

WoWStatusMainWindow.register("records", "Records", F.buildRecords, render)
