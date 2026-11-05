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

local function render()
    if not page then return end
    local UI = WoWStatusUI
    local result, medals = F.compute(WoWStatusJournal.entries())
    for i, medal in ipairs(medals) do
        local c = page.rows[i] or card(i)
        local column, line = (i - 1) % 2, math.floor((i - 1) / 2)
        c:ClearAllPoints(); c:SetPoint("TOPLEFT", column * (CARD_W + GAP), -line * (CARD_H + GAP))
        local e = result[medal.key]
        c.icon:SetIcon(medalIcon(medal), e == nil)
        c.title:SetText(medal.title)
        local holder = e and (name(e.sender):gsub("|", "||") .. " · " .. WoWStatusHistory.oslo(e.at):sub(1, 16)) or "nobody yet"
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
            table.insert(lines, "|cffffd100" .. WoWStatusHistory.oslo(e.at):sub(1, 16) .. "|r  " .. e.text:gsub("|", "||"))
        end
    end
    if #lines == 0 then table.insert(lines, "No recaps yet. One is written after each play session.") end
    local box = page.recapBox
    if not box then
        box = UI.box(page.list, 2 * CARD_W + GAP, 40); page.recapBox = box
        box.title = UI.header(box, "Session recaps", 12, -10, 2 * CARD_W + GAP - 24)
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
    page.heading:SetPoint("TOPLEFT", 24, -4); page.heading:SetText("Firsts in your group")
    page.scroll = CreateFrame("ScrollFrame", nil, page, "UIPanelScrollFrameTemplate")
    page.scroll:SetPoint("TOPLEFT", 24, -32); page.scroll:SetSize(710, 494)
    page.list = CreateFrame("Frame", nil, page.scroll); page.list:SetSize(686, 24)
    page.scroll:SetScrollChild(page.list)
    page.rows = {}
    return page
end

WoWStatusMainWindow.register("records", "Records", F.buildRecords, render)
