-- Overview page (#58): "Since you were last here" plus your own status.
-- Uses only the local activity log (including entries recovered by login sync);
-- it sends nothing. The cut-off is the account's previous logout, kept across
-- /reload in WoWStatusDB.overview.
WoWStatusOverview = {}
local O, S = WoWStatusOverview, WoWStatusSafe
local MAX_LINES = 40
local page

local function state()
    if type(WoWStatusDB) ~= "table" then return nil end
    if type(WoWStatusDB.overview) ~= "table" then WoWStatusDB.overview = {} end
    return WoWStatusDB.overview
end

local function plural(count, one, many) return count == 1 and one or (count .. " " .. many) end
local function name(sender) return (tostring(sender or "?"):match("^[^-]+") or "?") end

-- Facts per player, newest player first. Each fact links to its newest entry.
-- entries: newest first, as WoWStatusJournal.entries() returns them.
function O.summary(entries, since)
    if type(since) ~= "number" then return {} end
    local players, order = {}, {}
    for _, e in ipairs(entries or {}) do
        if type(e) == "table" and not e.owner and type(e.at) == "number" and e.at > since
            and (not WoWStatusJournal.visible or WoWStatusJournal.visible(e)) then
            local key = name(e.sender)
            local p = players[key]
            if not p then
                p = {player=key, kinds={}, at=e.at}
                players[key] = p; table.insert(order, p)
            end
            local kind = p.kinds[e.kind]
            if not kind then kind = {count=0, id=e.id, entries={}}; p.kinds[e.kind] = kind end
            kind.count = kind.count + 1
            table.insert(kind.entries, e)
        end
    end
    local result = {}
    local labels = {
        death=function(k) return k.count == 1 and "died once" or ("died " .. k.count .. " times") end,
        zone=function(k) return "discovered " .. plural(k.count, "a new zone", "new zones") end,
        quest=function(k) return k.entries[1].text end,
        profession=function(k) return plural(k.count, "a profession milestone", "profession milestones") end,
        mount=function() return "got a first mount" end,
        reputation=function(k) return plural(k.count, "a new reputation rank", "new reputation ranks") end,
        unlock=function(k) return plural(k.count, "a class ability unlock", "class ability unlocks") end,
        pvp=function(k) return plural(k.count, "a PvP promotion", "PvP promotions") end,
        loot=function(k) return "equipped " .. plural(k.count, "a new item", "new items") end,
        introduction=function() return "joined the group" end,
    }
    local sequence = {"level", "dungeon", "death", "profession", "mount", "loot", "zone", "quest", "reputation", "unlock", "pvp", "introduction"}
    for _, p in ipairs(order) do
        local facts = {}
        for _, kind in ipairs(sequence) do
            local k = p.kinds[kind]
            if k then
                if kind == "level" then
                    local top
                    for _, e in ipairs(k.entries) do
                        local level = S.number(e.level)
                        if level and (not top or level > top) then top = level end
                    end
                    local text = k.count == 1 and ("reached level " .. (top or "?"))
                        or ("gained " .. k.count .. " levels" .. (top and (" (now " .. top .. ")") or ""))
                    table.insert(facts, {text=text, id=k.id, kind=kind})
                elseif kind == "dungeon" then
                    for _, e in ipairs(k.entries) do
                        local dungeon = tostring(e.text or ""):match("^First clear: (.+)$")
                        table.insert(facts, {text="cleared " .. (dungeon or "a dungeon"), id=e.id, kind=kind})
                    end
                else
                    table.insert(facts, {text=labels[kind] and labels[kind](k) or plural(k.count, "an update", "updates"), id=k.id, kind=kind})
                end
            end
        end
        for other, k in pairs(p.kinds) do
            local known = false
            for _, kind in ipairs(sequence) do if kind == other then known = true end end
            if not known then table.insert(facts, {text=plural(k.count, "an update", "updates"), id=k.id, kind=other}) end
        end
        table.insert(result, {player=p.player, facts=facts})
    end
    return result
end

-- One plain sentence per player, as in "Bob gained 3 levels (now 42), cleared Deadmines".
function O.sentence(player)
    local parts = {}
    for _, fact in ipairs(player.facts) do table.insert(parts, fact.text) end
    return player.player .. " " .. table.concat(parts, ", ")
end

function O.ownStatus()
    local level = S.number(S.call(UnitLevel, "player"))
    if not level then return "Your status is not available right now." end
    local text = "You are level " .. level
    local maximum = WoWStatusAdapter and WoWStatusAdapter.max_level
    local xp, xpMax = S.number(S.call(UnitXP, "player")), S.number(S.call(UnitXPMax, "player"))
    if maximum and level >= maximum then
        text = text .. " (maximum level)"
    elseif xp and xpMax and xpMax > 0 and xp >= 0 and xp <= xpMax then
        text = text .. string.format(" · %d%% of the way to level %d", math.floor(xp / xpMax * 100), level + 1)
    end
    return text .. "."
end

local function line(parent, index)
    local row = CreateFrame("Button", nil, parent)
    row:SetSize(680, 22)
    row.text = row:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    row.text:SetPoint("TOPLEFT", 0, 0); row.text:SetWidth(680); row.text:SetJustifyH("LEFT")
    row:SetScript("OnClick", function(self) if self.id then WoWStatusJournal.focus(self.id) end end)
    parent.lines[index] = row
    return row
end

local function render()
    if not page then return end
    local data = state() or {}
    page.status:SetText(O.ownStatus())
    local since = data.since
    local summary = O.summary(WoWStatusJournal.entries(), since)
    page.heading:SetText(since and ("Since you were last here (" .. WoWStatusHistory.oslo(since) .. ")")
        or "Since you were last here")
    local rows = {}
    for _, player in ipairs(summary) do
        table.insert(rows, {text="|cffffd100" .. player.player .. "|r"})
        for _, fact in ipairs(player.facts) do
            table.insert(rows, {text="   • " .. fact.text, id=fact.id})
        end
    end
    if #rows > MAX_LINES then
        local hidden = #rows - MAX_LINES + 1
        for i = #rows, MAX_LINES, -1 do rows[i] = nil end
        rows[MAX_LINES] = {text="…and " .. hidden .. " more lines in the Activity tab."}
    end
    page.empty:SetText(not since and "This summary starts after your next logout."
        or "Nothing new from your group since you were last here.")
    page.empty:SetShown(#rows == 0)
    for i, row in ipairs(rows) do
        local widget = page.list.lines[i] or line(page.list, i)
        widget:ClearAllPoints(); widget:SetPoint("TOPLEFT", 0, -(i - 1) * 24)
        widget.text:SetText(row.text); widget.id = row.id; widget:Show()
    end
    for i = #rows + 1, #page.list.lines do page.list.lines[i].id = nil; page.list.lines[i]:Hide() end
    page.rows = rows
end
O.render = render

local function build(parent)
    page = CreateFrame("Frame", "WoWStatusOverviewPage", parent); page:SetAllPoints(parent)
    page.status = page:CreateFontString(nil, "OVERLAY", "GameFontHighlightLarge")
    page.status:SetPoint("TOPLEFT", 24, -4); page.status:SetWidth(720); page.status:SetJustifyH("LEFT")
    page.heading = page:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
    page.heading:SetPoint("TOPLEFT", 24, -44); page.heading:SetWidth(720); page.heading:SetJustifyH("LEFT")
    page.scroll = CreateFrame("ScrollFrame", nil, page, "UIPanelScrollFrameTemplate")
    page.scroll:SetPoint("TOPLEFT", 24, -76); page.scroll:SetSize(710, 450)
    page.list = CreateFrame("Frame", nil, page.scroll); page.list:SetSize(686, MAX_LINES * 24)
    page.list.lines = {}
    page.scroll:SetScrollChild(page.list)
    page.empty = page:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    page.empty:SetPoint("TOPLEFT", 24, -84); page.empty:SetWidth(720); page.empty:SetJustifyH("LEFT")
    return page
end

WoWStatusMainWindow.register("overview", "Overview", build, render)

-- PLAYER_ENTERING_WORLD(isInitialLogin, isReloadingUi): a reload keeps the
-- previous cut-off. Clients without these arguments treat every load as a login.
local frame, started = CreateFrame("Frame"), false
for _, event in ipairs({"PLAYER_LOGOUT", "PLAYER_ENTERING_WORLD"}) do pcall(frame.RegisterEvent, frame, event) end
frame:SetScript("OnEvent", function(_, event, _, reloading)
    local data = state()
    if not data then return end
    if event == "PLAYER_LOGOUT" then
        data.last_logout = time()
    elseif not started then
        started = true -- Once per load; zone changes fire this event again.
        if reloading ~= true and type(data.last_logout) == "number" then data.since = data.last_logout end
    end
end)
