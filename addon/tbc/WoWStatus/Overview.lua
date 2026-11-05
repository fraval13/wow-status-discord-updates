-- Overview page (#58): "Since you were last here" plus your own status.
-- Uses only the local activity log (including entries recovered by login sync);
-- it sends nothing. The cut-off is the account's previous logout, kept across
-- /reload in WoWStatusDB.overview.
WoWStatusOverview = {}
local O, S = WoWStatusOverview, WoWStatusSafe
local MAX_LINES = 40
local SINCE_MIN, SINCE_MAX = 90, 232
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
                local shown = WoWStatusRoster and WoWStatusRoster.displayName and WoWStatusRoster.displayName(e.sender) or key
                p = {player=shown, kinds={}, at=e.at}
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
    row:SetSize(640, 22)
    row.text = row:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    row.text:SetPoint("TOPLEFT", 0, 0); row.text:SetWidth(640); row.text:SetJustifyH("LEFT")
    row:SetScript("OnClick", function(self) if self.id then WoWStatusJournal.focus(self.id) end end)
    parent.lines[index] = row
    return row
end

-- The "You" box: portrait, level, XP and a few counts from your own snapshot.
local function renderYou()
    local UI, you = WoWStatusUI, page.you
    local character = WoWStatusPopups.character and WoWStatusPopups.character()
    if SetPortraitTexture then pcall(SetPortraitTexture, you.portrait, "player") end
    local level = S.number(S.call(UnitLevel, "player"))
    you.badge:SetLevel(level)
    local _, class = S.call(UnitClass, "player")
    local name = character and WoWStatusPopups.characterName(character):match("^[^-]+")
        or S.stringCall(UnitName, "player") or "You"
    local colour = UI.classColour(S.string(class))
    local safe = (name:gsub("|", "||"))
    you.name:SetText(colour and (colour .. safe .. "|r") or safe)
    local race = S.stringCall(UnitRace, "player")
    local zone = WoWStatusAdapter.zone and WoWStatusAdapter.zone()
    local className = S.stringCall(UnitClass, "player")
    you.info:SetText(table.concat({race or "", className or "", zone and ("· " .. zone) or ""}, " "))
    local xp, xpMax = S.number(S.call(UnitXP, "player")), S.number(S.call(UnitXPMax, "player"))
    local maximum = WoWStatusAdapter.max_level
    if level and maximum and level >= maximum then you.xp:SetProgress(1, "Maximum level")
    elseif xp and xpMax and xpMax > 0 then
        you.xp:SetProgress(xp / xpMax, math.floor(xp / xpMax * 100) .. "% to level " .. ((level or 0) + 1))
    else you.xp:SetProgress(nil) end
    local snapshot = character and character.snapshot or {}
    local facts = {}
    if S.number(snapshot.deaths_lifetime or snapshot.deaths) then table.insert(facts, "Deaths: " .. (snapshot.deaths_lifetime or snapshot.deaths)) end
    if S.number(snapshot.quests_completed) then table.insert(facts, "Quests: " .. snapshot.quests_completed) end
    you.stats:SetText(table.concat(facts, "   "))
end

-- The "Your group" box: who is online now.
local function renderGroup()
    local group, names, seen = page.group, {}, {}
    local character = WoWStatusPopups.character and WoWStatusPopups.character()
    local groups = 0
    for id in pairs(WoWStatusGroups.selected(character)) do
        groups = groups + 1
        for _, peer in ipairs(WoWStatusPopups.peers(id)) do
            local key = WoWStatusPopups.senderKey(peer)
            if key and not seen[key] and WoWStatusPopups.fullName(peer) then
                seen[key] = true; table.insert(names, ((peer:match("^[^-]+") or peer):gsub("|", "||")))
            end
        end
    end
    table.sort(names)
    local count = WoWStatusPopups.onlineCount()
    group.count:SetText(groups == 0 and "Join a group in Options to share with friends."
        or ("|cff40ff40" .. count .. "|r online · " .. groups .. (groups == 1 and " group" or " groups")))
    -- Everyone online, scrolling when the box is full.
    group.names:SetText(#names > 0 and table.concat(names, "\n") or (groups > 0 and "Nobody else is online right now." or ""))
    group.list:SetHeight(math.max(1, (S.number(group.names:GetStringHeight()) or 0) + 4))
end

-- The "Latest records" box: the three newest Firsts medals.
local function renderRecords()
    local box, won = page.records, {}
    if WoWStatusFirsts and WoWStatusFirsts.compute and WoWStatusFirsts.groups then
        -- Each group has its own records; the newest across all of them.
        for _, group in ipairs(WoWStatusFirsts.groups()) do
            local result, medals = WoWStatusFirsts.compute(WoWStatusJournal.entries(), group.id)
            for _, medal in ipairs(medals) do
                if result[medal.key] then table.insert(won, {medal=medal, entry=result[medal.key], group=group.label}) end
            end
        end
    end
    table.sort(won, function(a, b) return a.entry.at > b.entry.at end)
    for i, row in ipairs(box.rows) do
        local item = won[i]
        if item then
            row.icon:SetIcon(WoWStatusFirsts.medalIcon(item.medal))
            row.text:SetText("|cffffd100" .. item.medal.title .. "|r — "
                .. ((item.entry.sender or "?"):match("^[^-]+") or "?"):gsub("|", "||")
                .. "  |cff9d9d9d" .. item.group:gsub("|", "||") .. " · " .. WoWStatusHistory.oslo(item.entry.at):sub(1, 16) .. "|r")
            row:Show()
        else row:Hide() end
    end
    box.empty:SetShown(#won == 0)
end

local function render()
    if not page then return end
    local data = state() or {}
    page.status:SetText(O.ownStatus())
    for _, part in ipairs({renderYou, renderGroup, renderRecords}) do
        local ok, problem = pcall(part)
        if not ok then page.problem = problem end -- One box failing must not blank the page.
    end
    local since = data.since
    if WoWStatusGuide and WoWStatusGuide.touring() then since = S.now() - 86400 end
    local summary = O.summary(WoWStatusJournal.displayEntries(), since)
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
    -- The box fits its lines (no empty space below a few), up to the room above
    -- Latest records; longer summaries scroll.
    local height = math.max(SINCE_MIN, math.min(SINCE_MAX, 50 + math.max(1, #rows) * 24))
    page.since:SetHeight(height)
    page.scroll:SetHeight(height - 48)
    page.list:SetHeight(math.max(1, #rows) * 24)
    page.rows = rows
end
O.render = render

local function build(parent)
    local UI = WoWStatusUI
    page = CreateFrame("Frame", "WoWStatusOverviewPage", parent); page:SetAllPoints(parent)
    -- You
    local you = UI.box(page, 350, 136); you:SetPoint("TOPLEFT", 24, -4); page.you = you
    you.portrait = you:CreateTexture(nil, "ARTWORK"); you.portrait:SetPoint("TOPLEFT", 12, -12); you.portrait:SetSize(56, 56)
    you.badge = UI.levelBadge(you, 28); you.badge:SetPoint("TOPLEFT", 46, -48)
    you.name = UI.text(you, "GameFontNormalLarge", 84, -12, 256)
    you.info = UI.text(you, "GameFontHighlightSmall", 84, -36, 256)
    you.xp = UI.xpBar(you, 250, 12); you.xp:SetPoint("TOPLEFT", 84, -56)
    page.status = UI.text(you, "GameFontHighlightSmall", 12, -86, 326)
    you.stats = UI.text(you, "GameFontHighlightSmall", 12, -110, 326)
    -- Your group
    local group = UI.box(page, 336, 136); group:SetPoint("TOPLEFT", 386, -4); page.group = group
    UI.header(group, "Your group", 12, -10, 312)
    group.count = UI.text(group, "GameFontHighlight", 12, -34, 312)
    group.scroll = CreateFrame("ScrollFrame", nil, group, "UIPanelScrollFrameTemplate")
    group.scroll:SetPoint("TOPLEFT", 12, -56); group.scroll:SetSize(286, 70)
    group.list = CreateFrame("Frame", nil, group.scroll); group.list:SetSize(280, 70)
    group.scroll:SetScrollChild(group.list)
    group.names = UI.text(group.list, "GameFontHighlightSmall", 0, 0, 280)
    -- Since you were last here
    local since = UI.box(page, 698, 232); since:SetPoint("TOPLEFT", 24, -148); page.since = since
    page.heading = UI.text(since, "GameFontNormalLarge", 12, -10, 674)
    page.scroll = CreateFrame("ScrollFrame", nil, since, "UIPanelScrollFrameTemplate")
    page.scroll:SetPoint("TOPLEFT", 12, -38); page.scroll:SetSize(650, 184)
    page.list = CreateFrame("Frame", nil, page.scroll); page.list:SetSize(640, MAX_LINES * 24)
    page.list.lines = {}
    page.scroll:SetScrollChild(page.list)
    page.empty = UI.text(since, "GameFontHighlight", 12, -44, 674)
    -- Latest records
    -- Directly under "Since you were last here", which sizes to its lines.
    local records = UI.box(page, 698, 124); records:SetPoint("TOPLEFT", since, "BOTTOMLEFT", 0, -8); page.records = records
    UI.header(records, "Latest records", 12, -10, 674)
    records.rows = {}
    for i = 1, 3 do
        local row = CreateFrame("Frame", nil, records); row:SetSize(674, 26); row:SetPoint("TOPLEFT", 12, -32 - (i - 1) * 28)
        row.icon = UI.icon(row, 24); row.icon:SetPoint("TOPLEFT", 0, 0)
        row.text = UI.text(row, "GameFontHighlight", 32, -5, 640)
        records.rows[i] = row
    end
    records.empty = UI.text(records, "GameFontDisable", 12, -38, 674)
    records.empty:SetText("No records yet. The first to reach a milestone in your group earns it.")
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
        data.last_logout = S.now()
    elseif not started then
        started = true -- Once per load; zone changes fire this event again.
        if reloading ~= true and type(data.last_logout) == "number" then data.since = data.last_logout end
    end
end)
