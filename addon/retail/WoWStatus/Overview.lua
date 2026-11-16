-- Overview page (#58): "Since you were last here" plus your own status.
-- Uses only the local activity log (including entries recovered by login sync);
-- it sends nothing. The cut-off is the account's previous logout, kept across
-- /reload in WoWStatusDB.overview.
WoWStatusOverview = {}
local O, S = WoWStatusOverview, WoWStatusSafe
local T, TF = WoWStatusLocale.T, WoWStatusLocale.F
local MAX_LINES = 40
local SINCE_MIN, SINCE_MAX = 90, 154
local page

local function state()
    if type(WoWStatusDB) ~= "table" then return nil end
    if type(WoWStatusDB.overview) ~= "table" then WoWStatusDB.overview = {} end
    return WoWStatusDB.overview
end

-- "Not seen for a while" (#172): friends whose shared character list shows no
-- activity for this many days. Account-wide in WoWStatusDB.overview.not_seen_days;
-- 0 is off and the default (14) is stored as nothing. Purely local: it reads the
-- log and the character lists already here and never sends or whispers anything.
O.NOT_SEEN_CHOICES = {0, 7, 14, 30}
O.NOT_SEEN_DEFAULT = 14
local NOT_SEEN_SHOWN = 3
local function name(sender) return (tostring(sender or "?"):match("^[^-]+") or "?") end
local function notSeenChoice(days)
    for i, choice in ipairs(O.NOT_SEEN_CHOICES) do if choice == days then return i end end
end
function O.notSeenDays()
    local data = state()
    local value = data and S.number(data.not_seen_days)
    return notSeenChoice(value) and value or O.NOT_SEEN_DEFAULT
end
function O.setNotSeenDays(days)
    local data = state()
    if not data or not notSeenChoice(days) then return false end
    data.not_seen_days = days ~= O.NOT_SEEN_DEFAULT and days or nil
    return true
end
-- The next choice after the current one, wrapping round (the Options button).
function O.cycleNotSeenDays()
    local choices = O.NOT_SEEN_CHOICES
    O.setNotSeenDays(choices[notSeenChoice(O.notSeenDays()) % #choices + 1])
    return O.notSeenDays()
end
function O.notSeenLabel(days)
    days = days or O.notSeenDays()
    if days == 0 then return T("Off") end
    return TF("%d days", days)
end

-- Players quiet for at least `days`, longest first: {player, days, more}.
-- groups: R.groups(); now and the stamps are realm time (S.now). Only players
-- whose shared character list is here count (not "Not announced" senders), and
-- only while they share a group you are still in. One online character means
-- they are around. Hidden bank alts are already left out of R.groups.
-- When their newest activity is older than the oldest friend entry the log still
-- holds (`oldest`), later entries of theirs may have been dropped from the log,
-- so it reads "more than N days", N being how far back the log reaches.
local UNNAMED = "Unnamed player"
function O.notSeen(groups, now, days, oldest)
    local result = {}
    if not days or days <= 0 or type(now) ~= "number" then return result end
    local function consider(player, rows)
        local listed, online, seen = false, false, 0
        for _, row in ipairs(rows) do
            -- A friend muted with "Hide completely" (#169) stays out of it.
            if row.listed and type(row.groupIds) == "table" and next(row.groupIds)
                and not (WoWStatusMutes and WoWStatusMutes.hidden(row.name)) then
                listed = true
                if row.status == "online" then online = true end
                seen = math.max(seen, S.number(row.seen) or 0)
            end
        end
        if not listed or online or seen <= 0 then return end
        local quiet = math.floor(math.max(0, now - seen) / 86400)
        if quiet < days then return end
        local item = {player=player, days=quiet}
        if type(oldest) == "number" and seen < oldest then
            local span = math.floor(math.max(0, now - oldest) / 86400)
            if span >= days then item.days, item.more = span, true end
        end
        table.insert(result, item)
    end
    for _, entry in ipairs(groups or {}) do
        if not entry.self then
            local title = tostring(entry.name or entry.title or "?")
            if title == UNNAMED then
                -- Lists without a player name are merged under one header; each
                -- character there may be a different person, so each stands alone.
                for _, row in ipairs(entry.rows or {}) do
                    consider(name(row.name), {row})
                end
            else
                consider(title, entry.rows or {})
            end
        end
    end
    table.sort(result, function(a, b)
        if a.days ~= b.days then return a.days > b.days end
        return a.player < b.player
    end)
    return result
end

-- The oldest friend entry still in the log, or nil with none.
function O.logStart(entries)
    local oldest
    for _, e in ipairs(entries or {}) do
        local at = type(e) == "table" and not e.owner and S.number(e.at)
        if at and (not oldest or at < oldest) then oldest = at end
    end
    return oldest
end

-- "Not seen for a while: Thora (12 days), Bran (more than 31 days)", or nil.
function O.notSeenLine(list)
    if not list or #list == 0 then return nil end
    local parts = {}
    for i, item in ipairs(list) do
        if i > NOT_SEEN_SHOWN then
            table.insert(parts, TF("%d more", #list - NOT_SEEN_SHOWN)); break
        end
        local name = item.player:gsub("|", "||")
        local span = TF(item.more and "more than %d days" or "%d days", item.days)
        table.insert(parts, name .. " (" .. span .. ")")
    end
    return T("Not seen for a while:") .. " " .. table.concat(parts, ", ")
end

local function plural(count, one, many) return count == 1 and one or (count .. " " .. many) end

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
                p = {player=shown, kinds={}, at=e.at, sender=e.sender}
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
        death=function(k)
            -- A Hardcore death is permanent and never tallied (#163). Two characters
            -- with the same short name share a line: their ordinary deaths count.
            local n = 0
            for _, e in ipairs(k.entries) do if not WoWStatusProgress.hardcoreDeath(e) then n = n + 1 end end
            if n == 0 then return "died in Hardcore" end
            return n == 1 and "died once" or ("died " .. n .. " times")
        end,
        zone=function(k) return "discovered " .. plural(k.count, "a new zone", "new zones") end,
        quest=function(k) return k.entries[1].text end,
        profession=function(k) return plural(k.count, "a profession milestone", "profession milestones") end,
        mount=function() return "got a first mount" end,
        reputation=function(k) return plural(k.count, "a new reputation rank", "new reputation ranks") end,
        unlock=function(k) return plural(k.count, "a class ability unlock", "class ability unlocks") end,
        pvp=function(k) return plural(k.count, "a PvP promotion", "PvP promotions") end,
        achievement=function(k) return "earned " .. plural(k.count, "an achievement", "achievements") end,
        loot=function(k) return "equipped " .. plural(k.count, "a new item", "new items") end,
        introduction=function() return "joined the group" end,
    }
    -- Pinned friends (#170) first, in the order they were pinned; the rest stay newest first.
    local R = WoWStatusRoster
    if R and R.pinFirst and R.pinRanks then
        local ranks = R.pinRanks()
        order = R.pinFirst(order, function(p) local k = R.key(p.sender); return k and ranks[k] end)
    end
    local sequence = {"level", "dungeon", "death", "profession", "mount", "loot", "zone", "quest", "reputation", "unlock", "pvp", "achievement", "introduction"}
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
    if not level then return T("Your status is not available right now.") end
    local text = TF("You are level %d", level)
    local maximum = WoWStatusAdapter and WoWStatusAdapter.max_level
    local xp, xpMax = S.number(S.call(UnitXP, "player")), S.number(S.call(UnitXPMax, "player"))
    if maximum and level >= maximum then
        text = text .. " (" .. T("maximum level") .. ")"
    elseif xp and xpMax and xpMax > 0 and xp >= 0 and xp <= xpMax then
        text = text .. TF(" · %d%% of the way to level %d", math.floor(xp / xpMax * 100), level + 1)
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
    if level and maximum and level >= maximum then you.xp:SetProgress(1, T("Maximum level"))
    elseif xp and xpMax and xpMax > 0 then
        you.xp:SetProgress(xp / xpMax, TF("%d%% to level %d", math.floor(xp / xpMax * 100), (level or 0) + 1))
    else you.xp:SetProgress(nil) end
    local snapshot = character and character.snapshot or {}
    local facts = {}
    if S.number(snapshot.deaths_lifetime or snapshot.deaths) then table.insert(facts, T("Deaths:") .. " " .. (snapshot.deaths_lifetime or snapshot.deaths)) end
    if S.number(snapshot.quests_completed) then table.insert(facts, T("Quests:") .. " " .. snapshot.quests_completed) end
    local progress = character and character.progress
    local fields = character and character.settings and character.settings.fields or {}
    if fields.kills and WoWStatusProgress.totalKills then table.insert(facts, T("Kills:") .. " " .. WoWStatusProgress.totalKills(character)) end
    you.stats:SetText(table.concat(facts, "   "))
    -- Gold now, gold earned and played time.
    local more = {}
    local gold = fields.gold and progress and S.number(progress.gold)
    if gold then table.insert(more, T("Current:") .. " " .. UI.money(gold)) end
    if fields.gold and progress and WoWStatusProgress.goldEarned then
        table.insert(more, T("Earned:") .. " " .. UI.money(WoWStatusProgress.goldEarned(character), true))
    end
    local played = S.number(snapshot.playtime)
    if played then table.insert(more, T("Played:") .. " " .. UI.duration(played)) end
    you.stats2:SetText(table.concat(more, "   "))
    local average=character and fields.gear and WoWStatusRoster.itemLevel(WoWStatusPopups.characterName(character))
    you.itemLevel:SetText(T("Average item level:") .. " " .. (average and math.floor(average) or "—"))
    local newer = WoWStatusRoster.newerVersion and WoWStatusRoster.newerVersion()
    you.update:SetText(newer and (T("Update available:") .. " " .. newer .. " — wow.frankvalde.com") or "")
end

-- The "Your group" box: who is online now.
local function renderGroup()
    local group, names, seen = page.group, {}, {}
    local character = WoWStatusPopups.character and WoWStatusPopups.character()
    local groups = 0
    local ranks = WoWStatusRoster.pinRanks and WoWStatusRoster.pinRanks() or {}
    for id in pairs(WoWStatusGroups.selected(character)) do
        groups = groups + 1
        for _, peer in ipairs(WoWStatusPopups.peers(id)) do
            local key = WoWStatusPopups.senderKey(peer)
            -- Bank alts hidden from lists, and friends muted with "Hide completely" (#169).
            if key and not seen[key] and WoWStatusPopups.fullName(peer) and not WoWStatusRoster.isHidden(peer)
                and not (WoWStatusMutes and WoWStatusMutes.hidden(peer)) then
                seen[key] = true
                local k = WoWStatusRoster.key and WoWStatusRoster.key(peer)
                table.insert(names, {text=((peer:match("^[^-]+") or peer):gsub("|", "||")), pin=k and ranks[k]})
            end
        end
    end
    -- Pinned friends (#170) first, in the order they were pinned; then by name.
    table.sort(names, function(a, b) return a.text < b.text end)
    if WoWStatusRoster.pinFirst then names = WoWStatusRoster.pinFirst(names, function(item) return item.pin end) end
    for i, item in ipairs(names) do names[i] = item.text end
    local count = #names
    group.count:SetText(groups == 0 and T("Join a group in Options to share with friends.")
        or ("|cff40ff40" .. count .. "|r " .. T("online") .. " · " .. groups .. " " .. T(groups == 1 and "group" or "groups")))
    -- Everyone online, scrolling when the box is full.
    group.names:SetText(#names > 0 and table.concat(names, "\n") or (groups > 0 and T("Nobody else is online right now.") or ""))
    group.list:SetHeight(math.max(1, (S.number(group.names:GetStringHeight()) or 0) + 4))
    -- Friends not seen for a while (#172), under the names. Only shown, never sent.
    local days = O.notSeenDays()
    local text
    if groups > 0 and days > 0 and WoWStatusRoster.groups then
        text = O.notSeenLine(O.notSeen(WoWStatusRoster.groups(), S.now(), days, O.logStart(WoWStatusJournal.entries())))
    end
    group.notSeen:SetText(text or "")
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
            local who = item.entry.holder or ((item.entry.sender or "?"):match("^[^-]+") or "?")
            row.text:SetText("|cffffd100" .. T(item.medal.title) .. "|r — "
                .. who:gsub("|", "||")
                .. "  " .. WoWStatusUI.MUTED_CODE .. item.group:gsub("|", "||") .. " · " .. WoWStatusHistory.localTime(item.entry.at) .. "|r")
            row:Show()
        else row:Hide() end
    end
    box.empty:SetShown(#won == 0)
end

-- The group goal band (#157): one group's goal and its progress, with "Goal…"
-- to set or change it. With several groups, ">" shows the next group's.
local function renderGoal()
    local band, G = page.goal, WoWStatusGoals
    local groups = G and G.groups() or {}
    local data = state() or {}
    local chosen
    for _, group in ipairs(groups) do if group.id == data.goal_group then chosen = group end end
    if not chosen then
        -- The first group with a goal, else the first group.
        for _, group in ipairs(groups) do if not chosen and G.get(group.id) then chosen = group end end
        chosen = chosen or groups[1]
    end
    band.group = chosen and chosen.id
    WoWStatusUI.call(band.next, "SetEnabled", #groups > 1)
    WoWStatusUI.call(band.edit, "SetEnabled", chosen ~= nil)
    local goal = chosen and G.get(chosen.id)
    if not goal then
        band.title:SetText(chosen and (T("No group goal yet.") .. "  " .. WoWStatusUI.MUTED_CODE .. chosen.label:gsub("|", "||") .. "|r")
            or T("Join a group to share a goal with friends."))
        band.bar:SetProgress(nil); band.status:SetText("")
        return
    end
    local title, fraction, status = G.describe(chosen.id, goal)
    band.title:SetText("|cffffd100" .. title .. "|r  " .. WoWStatusUI.MUTED_CODE .. chosen.label:gsub("|", "||") .. "|r")
    band.bar:SetProgress(fraction, "")
    band.status:SetText(status)
end

local function render()
    if not page then return end
    local data = state() or {}
    page.status:SetText(O.ownStatus())
    for _, part in ipairs({renderYou, renderGroup, renderGoal, renderRecords}) do
        local ok, problem = pcall(part)
        if not ok then page.problem = problem end -- One box failing must not blank the page.
    end
    local since = data.since
    if WoWStatusGuide and WoWStatusGuide.touring() then since = S.now() - 86400 end
    local summary = O.summary(WoWStatusJournal.displayEntries(), since)
    page.heading:SetText(since and (T("Since you were last here") .. " (" .. WoWStatusHistory.localTime(since) .. ")")
        or T("Since you were last here"))
    local rows = {}
    for _, player in ipairs(summary) do
        table.insert(rows, {text="|cffffd100" .. player.player .. "|r"})
        for _, fact in ipairs(player.facts) do
            table.insert(rows, {text="   • " .. T(fact.text), id=fact.id})
        end
    end
    if #rows > MAX_LINES then
        local hidden = #rows - MAX_LINES + 1
        for i = #rows, MAX_LINES, -1 do rows[i] = nil end
        rows[MAX_LINES] = {text=TF("…and %d more lines in the Activity tab.", hidden)}
    end
    page.empty:SetText(not since and T("This summary starts after your next logout.")
        or T("Nothing new from your group since you were last here."))
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
    local you = UI.box(page, 350, 166); you:SetPoint("TOPLEFT", 24, -4); page.you = you
    you.portrait = you:CreateTexture(nil, "ARTWORK"); you.portrait:SetPoint("TOPLEFT", 12, -12); you.portrait:SetSize(56, 56)
    you.badge = UI.levelBadge(you, 28); you.badge:SetPoint("TOPLEFT", 46, -48)
    you.name = UI.text(you, "GameFontNormalLarge", 84, -12, 256)
    you.info = UI.text(you, "GameFontHighlightSmall", 84, -36, 256)
    you.xp = UI.xpBar(you, 250, 12); you.xp:SetPoint("TOPLEFT", 84, -56)
    page.status = UI.text(you, "GameFontHighlightSmall", 12, -86, 326)
    you.stats = UI.text(you, "GameFontHighlightSmall", 12, -102, 326)
    you.stats2 = UI.text(you, "GameFontHighlightSmall", 12, -118, 326)
    you.itemLevel = UI.text(you, "GameFontHighlightSmall", 12, -134, 326)
    you.update = UI.text(you, "GameFontNormalSmall", 12, -150, 326)
    -- Your group
    local group = UI.box(page, 336, 166); group:SetPoint("TOPLEFT", 386, -4); page.group = group
    UI.header(group, T("Your group"), 12, -10, 312)
    group.count = UI.text(group, "GameFontHighlight", 12, -34, 312)
    group.scroll = CreateFrame("ScrollFrame", nil, group, "UIPanelScrollFrameTemplate")
    group.scroll:SetPoint("TOPLEFT", 12, -56); group.scroll:SetSize(286, 64)
    group.list = CreateFrame("Frame", nil, group.scroll); group.list:SetSize(280, 64)
    group.scroll:SetScrollChild(group.list)
    group.names = UI.text(group.list, "GameFontHighlightSmall", 0, 0, 280)
    -- At most three lines, so a long list never runs out of the box.
    group.notSeen = UI.text(group, "GameFontDisableSmall", 12, -124, 312)
    group.notSeen:SetHeight(38)
    if group.notSeen.SetMaxLines then pcall(group.notSeen.SetMaxLines, group.notSeen, 3) end
    -- Group goal (#157)
    local goal = UI.box(page, 698, 40); goal:SetPoint("TOPLEFT", 24, -178); page.goal = goal
    goal.title = UI.text(goal, "GameFontHighlight", 12, -6, 360)
    goal.title:SetWordWrap(false)
    goal.bar = UI.xpBar(goal, 200, 10); goal.bar:SetPoint("TOPLEFT", 12, -24)
    goal.status = UI.text(goal, "GameFontHighlightSmall", 220, -22, 260)
    goal.next = CreateFrame("Button", nil, goal, "UIPanelButtonTemplate")
    goal.next:SetSize(32, 24); goal.next:SetPoint("TOPRIGHT", -112, -8); goal.next:SetText(">")
    goal.next:SetScript("OnClick", function()
        local data = state()
        if not data or not goal.group then return end
        data.goal_group = WoWStatusGoals.nextGroup(goal.group)
        render()
    end)
    goal.edit = CreateFrame("Button", nil, goal, "UIPanelButtonTemplate")
    goal.edit:SetSize(96, 24); goal.edit:SetPoint("TOPRIGHT", -10, -8); goal.edit:SetText(T("Goal…"))
    goal.edit:SetScript("OnClick", function() if goal.group then WoWStatusGoals.show(goal.group) end end)
    -- Since you were last here
    local since = UI.box(page, 698, 154); since:SetPoint("TOPLEFT", 24, -226); page.since = since
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
    UI.header(records, T("Latest records"), 12, -10, 674)
    records.rows = {}
    for i = 1, 3 do
        local row = CreateFrame("Frame", nil, records); row:SetSize(674, 26); row:SetPoint("TOPLEFT", 12, -32 - (i - 1) * 28)
        row.icon = UI.icon(row, 24); row.icon:SetPoint("TOPLEFT", 0, 0)
        row.text = UI.text(row, "GameFontHighlight", 32, -5, 640)
        records.rows[i] = row
    end
    records.empty = UI.text(records, "GameFontDisable", 12, -38, 674)
    records.empty:SetText(T("No records yet. The first to reach a milestone in your group earns it."))
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
