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
    -- A Hardcore death is permanent and never a record (#163).
    kind("death", "First in the group to die", "death", function(e) return not WoWStatusProgress.hardcoreDeath(e) end)
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

local CARD_W, CARD_H, GAP = 336, 76, 8
local function card(index)
    local UI = WoWStatusUI
    local c = UI.box(page.list, CARD_W, CARD_H)
    c.icon = UI.icon(c, 40); c.icon:SetPoint("TOPLEFT", 8, -8)
    c.title = UI.text(c, "GameFontNormal", 56, -8, 270)
    c.title:SetHeight(32); c.title:SetWordWrap(true)
    c.holder = UI.text(c, "GameFontHighlightSmall", 56, -46, 270)
    c.holder:SetHeight(26); c.holder:SetWordWrap(true)
    page.rows[index] = c
    return c
end

-- The selected group, kept when it still exists.
local function selectedGroup(groups)
    local data = state() or {}
    for _, group in ipairs(groups) do if group.id == data.tab then return group end end
    return groups[1]
end
-- This week (Monday to Sunday, the player's local time) in one group, or an earlier
-- week (offset 1, 2, ...): highlights and one line per person.
local function dayOf(at) return WoWStatusHistory.day(at) end
local function shortName(sender) return (tostring(sender):match("^[^-]+") or tostring(sender)) end
function F.weekRange(offset)
    local now = S.now()
    local weekday = (tonumber(date("%w", now)) + 6) % 7 -- Monday = 0.
    local shift = -(offset or 0) * 7
    return WoWStatusHistory.day(now, shift - weekday), WoWStatusHistory.day(now, shift + 6 - weekday)
end
local function inGroup(e, group) return type(e.groups) == "table" and e.groups[group] == true end
function F.weekData(group, offset)
    local first, last = F.weekRange(offset)
    local people, order = {}, {}
    for _, e in ipairs(WoWStatusJournal.entries()) do
        local day = S.number(e.at) and dayOf(e.at)
        -- A Hardcore death never counts toward "Most deaths" or a person's line (#163).
        if day and day >= first and day <= last and inGroup(e, group) and WoWStatusJournal.visible(e)
            and not WoWStatusProgress.hardcoreDeath(e)
            and (e.kind == "level" or e.kind == "death" or e.kind == "zone" or e.kind == "loot" or e.kind == "quest") then
            local name = shortName(e.sender)
            local p = people[name]
            if not p then p = {name=name, level=0, death=0, zone=0, loot=0, quest=0}; people[name] = p; order[#order + 1] = p end
            if p[e.kind] then p[e.kind] = p[e.kind] + 1 end
        end
    end
    -- Most levels first, then by name. Written as two statements on purpose:
    -- "a.level ~= b.level and a.level > b.level or a.name < b.name" parses as
    -- (levels differ and a is higher) or (a sorts first by name), which answers
    -- true both ways round for two people on different levels.
    table.sort(order, function(a, b)
        if a.level ~= b.level then return a.level > b.level end
        return a.name < b.name
    end)
    local highlights, extras = {}, {}
    for _, measure in ipairs({{"level", "Most levels:"}, {"death", "Most deaths:"},
        {"zone", "Most explored:"}, {"loot", "Most new gear:"}}) do
        local top
        for _, p in ipairs(order) do
            if p[measure[1]] > 0 and (not top or p[measure[1]] > top[measure[1]]) then top = p end
        end
        if top then highlights[#highlights+1] = {label=measure[2], name=top.name, count=top[measure[1]]} end
    end
    if (offset or 0) == 0 and WoWStatusFeatures.enabled("bingo") then
        for _, line in ipairs(F.bingoLines(group)) do extras[#extras+1] = line end
    end
    if offset == 1 and WoWStatusFeatures.enabled("chronicle") then
        for _, line in ipairs(F.chronicleLines(group)) do extras[#extras+1] = line end
    end
    return {first=first, last=last, people=order, highlights=highlights, extras=extras}
end

-- Keep the plain-text summary for exports; the page lays out the same data in
-- columns so every person's numbers share one set of labels.
function F.week(group, offset)
    local report = F.weekData(group, offset)
    local lines = {}
    for _, h in ipairs(report.highlights) do
        lines[#lines+1] = "|cffffd100" .. T(h.label) .. "|r " .. h.name:gsub("|", "||") .. " (" .. h.count .. ")"
    end
    if #lines > 0 then lines[#lines+1] = " " end
    for _, p in ipairs(report.people) do
        local parts = {}
        if p.level > 0 then parts[#parts + 1] = "+" .. p.level .. " " .. T(p.level == 1 and "level" or "levels") end
        if p.death > 0 then parts[#parts + 1] = p.death .. " " .. T(p.death == 1 and "death" or "deaths") end
        if p.zone > 0 then parts[#parts + 1] = p.zone .. " " .. T(p.zone == 1 and "zone" or "zones") end
        if p.loot > 0 then parts[#parts + 1] = p.loot .. " " .. T("armor") end
        if p.quest > 0 then parts[#parts + 1] = (p.quest * 100) .. " " .. T("quests") end
        lines[#lines + 1] = p.name:gsub("|", "||") .. ": " .. table.concat(parts, " · ")
    end
    for _, line in ipairs(report.extras) do lines[#lines+1] = line end
    return lines, report.first, report.last
end

-- Labs experiment (#237): the killer and the zone behind the group's deaths.
WoWStatusFeatures.register("nemesis", "Group nemesis and deadliest zone",
    "Records name who has killed the group most, and the zone it died in most this week.")
-- The names (ties together) with the highest count, and that count.
local function leaders(counts)
    local top, names = 0, {}
    for name, n in pairs(counts) do
        if n > top then top, names = n, {name} elseif n == top then names[#names + 1] = name end
    end
    table.sort(names)
    return names, top
end
-- Only deaths with a known killer or zone count; a Hardcore death never does.
function F.nemesisLines(entries)
    local first, last = F.weekRange(0)
    local killers, weekKillers, weekZones = {}, {}, {}
    for _, e in ipairs(entries) do
        if e.kind == "death" and not WoWStatusProgress.hardcoreDeath(e) then
            local d = WoWStatusJournal.details(e)
            local day = dayOf(e.at)
            local thisWeek = day >= first and day <= last
            if d and d.killer then
                killers[d.killer] = (killers[d.killer] or 0) + 1
                if thisWeek then weekKillers[d.killer] = (weekKillers[d.killer] or 0) + 1 end
            end
            if d and d.zone and thisWeek then weekZones[d.zone] = (weekZones[d.zone] or 0) + 1 end
        end
    end
    local lines = {}
    local function add(label, counts, unit, unitMany)
        local names, n = leaders(counts)
        if n == 0 then return end
        lines[#lines + 1] = "|cffffd100" .. T(label) .. "|r " .. table.concat(names, ", "):gsub("|", "||")
            .. " — " .. n .. " " .. T(n == 1 and unit or unitMany)
    end
    add("Group nemesis:", killers, "kill", "kills")
    add("Nemesis this week:", weekKillers, "kill", "kills")
    add("Deadliest zone this week:", weekZones, "death", "deaths")
    return lines
end

-- Labs experiment (#239): a bingo card of group events for the week. The card is
-- seeded from the group ID and the week, so every member sees the same one
-- without anything being sent; the seed itself is never shown or logged.
WoWStatusFeatures.register("bingo", "Weekly group bingo card",
    "A 5x5 card of group events for the week, filled in from the shared log and shown under This week.",
    function() WoWStatusBingo.show() end)
-- A square: {text, test(list)}, where list is the week's entries (oldest first) and
-- test returns the name of whoever completed it, or nil.
local function nth(n, pred)
    return function(list)
        local count = 0
        for _, e in ipairs(list) do
            if pred(e) then count = count + 1; if count == n then return shortName(e.sender) end end
        end
    end
end
local function kindIs(k) return function(e) return e.kind == k end end
local function levelAtLeast(n) return function(e) return e.kind == "level" and (S.number(e.level) or 0) >= n end end
local function hourIn(from, to)
    return function(e)
        local hour = tonumber(WoWStatusHistory.oslo(e.at):sub(12, 13))
        return e.kind == "level" and hour ~= nil and hour >= from and hour <= to
    end
end
local function epic(e) return e.kind == "loot" and (S.number(e.quality) or 0) >= 4 end
local function rare(e) return e.kind == "loot" and (S.number(e.quality) or 0) >= 3 end
local function quests(e) return e.kind == "quest" end
local function anyone(n)
    return function(list)
        local seen, count = {}, 0
        for _, e in ipairs(list) do
            local name = shortName(e.sender)
            if not seen[name] then seen[name] = true; count = count + 1; if count == n then return name end end
        end
    end
end
F.BINGO = {
    {"A level-up", nth(1, kindIs("level"))}, {"Three level-ups", nth(3, kindIs("level"))},
    {"Five level-ups", nth(5, kindIs("level"))}, {"Ten level-ups", nth(10, kindIs("level"))},
    {"A level-up after midnight", nth(1, hourIn(0, 5))}, {"A level-up before lunch", nth(1, hourIn(6, 11))},
    {"A level-up in the evening", nth(1, hourIn(19, 23))}, {"Someone reaches level 20", nth(1, levelAtLeast(20))},
    {"Someone reaches level 40", nth(1, levelAtLeast(40))}, {"Someone reaches level 60", nth(1, levelAtLeast(60))},
    {"Someone dies", nth(1, kindIs("death"))}, {"Three deaths", nth(3, kindIs("death"))},
    {"Five deaths", nth(5, kindIs("death"))}, {"A new zone", nth(1, kindIs("zone"))},
    {"Three new zones", nth(3, kindIs("zone"))}, {"100 quests", nth(1, quests)},
    {"Two quest milestones", nth(2, quests)}, {"A dungeon clear", nth(1, kindIs("dungeon"))},
    {"Two dungeon clears", nth(2, kindIs("dungeon"))}, {"A raid boss", nth(1, kindIs("raid"))},
    {"A mount", nth(1, kindIs("mount"))}, {"An epic mount", nth(1, kindIs("epicmount"))},
    {"A new reputation standing", nth(1, kindIs("reputation"))}, {"A profession milestone", nth(1, kindIs("profession"))},
    {"A PvP promotion", nth(1, kindIs("pvp"))}, {"A newly unlocked ability", nth(1, kindIs("unlock"))},
    {"An armor first", nth(1, kindIs("loot"))}, {"Three armor firsts", nth(3, kindIs("loot"))},
    {"A rare or better item", nth(1, rare)}, {"An epic item", nth(1, epic)},
    {"Someone new joins the group", nth(1, kindIs("introduction"))},
    {"Two people active", anyone(2)}, {"Three people active", anyone(3)}, {"Five people active", anyone(5)},
    {"Ten entries in the log", nth(10, function() return true end)},
    {"Twenty-five entries in the log", nth(25, function() return true end)},
    {"Fifty entries in the log", nth(50, function() return true end)},
    {"A death and a level-up", function(list)
        local died, levelled
        for _, e in ipairs(list) do
            if e.kind == "death" then died = died or shortName(e.sender) end
            if e.kind == "level" then levelled = levelled or shortName(e.sender) end
        end
        return died and levelled and levelled or nil
    end},
    {"Four kinds of milestone", function(list)
        local kinds = {}
        for _, e in ipairs(list) do kinds[e.kind] = true end
        local n = 0
        for _ in pairs(kinds) do n = n + 1 end
        return n >= 4 and shortName(list[#list].sender) or nil
    end},
}
-- A number from text, for seeding. Integer arithmetic stays exact in Lua 5.1.
local function seedOf(text)
    local hash = 5381
    for i = 1, #text do hash = (hash * 131 + text:byte(i)) % 2147483629 end
    return hash + 1
end
-- Shared cards need one calendar even when friends display local dates.
-- Keep the original Oslo week for bingo, independently of the Records view.
function F.bingoWeekRange(offset)
    local now = S.now()
    local oslo = WoWStatusHistory.oslo(now)
    local wall = now + (oslo:find("+02:00", 1, true) and 7200 or 3600)
    local weekday = (tonumber(date("!%w", wall)) + 6) % 7
    local monday = wall - (weekday + (offset or 0) * 7) * 86400
    return date("!%Y-%m-%d", monday), date("!%Y-%m-%d", monday + 6 * 86400)
end
-- The week's card for a group: 25 {text, by} squares, "by" the name that filled it.
function F.bingo(group, offset)
    local first, last = F.bingoWeekRange(offset or 0)
    local list = {}
    for _, e in ipairs(WoWStatusJournal.entries()) do
        local day = S.number(e.at) and WoWStatusHistory.oslo(e.at):sub(1, 10)
        if day and day >= first and day <= last and inGroup(e, group) and WoWStatusJournal.visible(e)
            and not WoWStatusProgress.hardcoreDeath(e) then list[#list + 1] = e end
    end
    table.sort(list, function(a, b) return a.at < b.at end)
    local order = {}
    for i = 1, #F.BINGO do order[i] = i end
    local state = seedOf(tostring(group) .. "|" .. first)
    for i = #order, 2, -1 do
        state = (state * 48271) % 2147483647
        local j = state % i + 1
        order[i], order[j] = order[j], order[i]
    end
    local card = {}
    for i = 1, 25 do
        local square = F.BINGO[order[i]]
        card[i] = {text = square[1], by = square[2](list)}
    end
    return card, first
end
-- Whether any row, column or diagonal of a card is complete.
function F.bingoWins(card)
    local lines = {}
    for r = 0, 4 do
        local row, col = {}, {}
        for c = 1, 5 do row[c] = r * 5 + c; col[c] = (c - 1) * 5 + r + 1 end
        lines[#lines + 1] = row; lines[#lines + 1] = col
    end
    lines[#lines + 1] = {1, 7, 13, 19, 25}; lines[#lines + 1] = {5, 9, 13, 17, 21}
    for _, cells in ipairs(lines) do
        local all = true
        for _, i in ipairs(cells) do if not card[i].by then all = false end end
        if all then return true end
    end
    return false
end
function F.announceBingo(group, first, card)
    -- One banner per group and week.
    local seen = type(WoWStatusDB) == "table" and WoWStatusDB or nil
    if seen and WoWStatusPopups.notice then
        seen.bingo_weeks = type(seen.bingo_weeks) == "table" and seen.bingo_weeks or {}
        if seen.bingo_weeks[group] ~= first then
            seen.bingo_weeks[group] = first
            local by
            for _, square in ipairs(card) do by = by or square.by end
            WoWStatusPopups.notice({sender = by and (by .. "-" .. (GetRealmName and GetRealmName() or "Realm")) or "Group",
                kind = "first", text = T("Bingo!") .. " " .. T("The weekly card has a full line.")})
        end
    end
end

function F.bingoLines(group)
    local card, first = F.bingo(group, 0)
    local filled = 0
    for _, square in ipairs(card) do if square.by then filled = filled + 1 end end
    local win = F.bingoWins(card)
    local lines = {" ", "|cffffd100" .. T("Weekly bingo:") .. "|r " .. filled .. "/25" .. (win and ("  " .. T("Bingo!")) or "")}
    for _, square in ipairs(card) do
        lines[#lines + 1] = square.by and ("|cff40ff40[x]|r " .. T(square.text) .. " (" .. square.by:gsub("|", "||") .. ")")
            or (WoWStatusUI.MUTED_CODE .. "[ ] " .. T(square.text) .. "|r")
    end
    if win then F.announceBingo(group, first, card) end
    return lines
end

-- Labs experiment (#241): a short chapter for last week, made once from the
-- permitted log entries and kept on this computer. It stores the week's facts,
-- not sentences, so it follows the chosen language. Nothing is sent.
WoWStatusFeatures.register("chronicle", "Weekly chronicle",
    "A short chapter about last week's adventures, written once and shown under last week's list.")
function F.chronicleMake(group)
    local first, last = F.weekRange(1)
    local store = type(WoWStatusDB) == "table" and WoWStatusDB or nil
    if not store then return nil end
    store.chronicles = type(store.chronicles) == "table" and store.chronicles or {}
    local kept = store.chronicles[group]
    if type(kept) == "table" and kept.week == first then return kept end
    local people, deaths, hardcore, zones, entries = {}, 0, 0, 0, 0
    for _, e in ipairs(WoWStatusJournal.entries()) do
        local day = S.number(e.at) and dayOf(e.at)
        if day and day >= first and day <= last and inGroup(e, group) and WoWStatusJournal.visible(e) then
            entries = entries + 1
            local name = shortName(e.sender)
            if e.kind == "level" and S.number(e.level) then
                local p = people[name] or {n = 0, level = 0}
                p.n, p.level = p.n + 1, math.max(p.level, e.level)
                people[name] = p
            elseif e.kind == "death" then
                if WoWStatusProgress.hardcoreDeath(e) then hardcore = hardcore + 1 else deaths = deaths + 1 end
            elseif e.kind == "zone" then zones = zones + 1 end
        end
    end
    local top
    for name, p in pairs(people) do
        if not top or p.n > top.n or (p.n == top.n and name < top.name) then top = {name = name, n = p.n, level = p.level} end
    end
    -- The week's chapter is written once: later log changes do not rewrite it.
    kept = {week = first, top = top, deaths = deaths, hardcore = hardcore, zones = zones, entries = entries}
    store.chronicles[group] = kept
    return kept
end
function F.chronicleLines(group)
    local c = F.chronicleMake(group)
    if not c then return {} end
    local lines = {" ", "|cffffd100" .. T("Chronicle of the week") .. "|r"}
    if c.entries == 0 then
        lines[#lines + 1] = T("A quiet week. The road waits.")
        return lines
    end
    if c.top then
        lines[#lines + 1] = c.top.name:gsub("|", "||") .. " " .. T("climbed") .. " " .. c.top.n .. " "
            .. T(c.top.n == 1 and "level" or "levels") .. ", " .. T("reaching level") .. " " .. c.top.level .. "."
    end
    if c.deaths > 0 then
        lines[#lines + 1] = T("The group fell") .. " " .. c.deaths .. " " .. T(c.deaths == 1 and "time" or "times") .. "."
    end
    -- A Hardcore death is told plainly, with no joke (#163).
    if c.hardcore > 0 then lines[#lines + 1] = T("A Hardcore character fell this week. We remember them.") end
    if c.zones > 0 then
        lines[#lines + 1] = c.zones .. " " .. T(c.zones == 1 and "new place was explored." or "new places were explored.")
    end
    return lines
end

-- Fun records in one group, only when they are remarkable (high thresholds).
F.FUN = {zone_deaths=5, evening_levels=4, deaths=25, kills=1000, gold=1000000, armor=5}
function F.funRecords(group)
    local deathsIn, evenings, armor = {}, {}, {}
    local entries = {}
    for _, e in ipairs(WoWStatusJournal.entries()) do
        if inGroup(e, group) and WoWStatusJournal.visible(e) and S.number(e.at) then entries[#entries + 1] = e end
    end
    table.sort(entries, function(a, b) return a.at < b.at end)
    local firstSeen, toCap = {}, {}
    local cap = WoWStatusAdapter and WoWStatusAdapter.max_level
    for _, e in ipairs(entries) do
        local name = shortName(e.sender)
        firstSeen[name] = firstSeen[name] or e.at
        -- Time from a person's first recorded activity to the level cap (#166).
        if e.kind == "level" and cap and S.number(e.level) == cap and not toCap[name] then
            toCap[name] = e.at - firstSeen[name]
        end
        -- A Hardcore death (#163) adds nothing: no "dangerous zone", no streak.
        if e.kind == "death" and not WoWStatusProgress.hardcoreDeath(e) then
            local d = WoWStatusJournal.details(e)
            if d and d.zone then deathsIn[d.zone] = (deathsIn[d.zone] or 0) + 1 end
        elseif e.kind == "level" then
            local k = name .. "|" .. dayOf(e.at)
            evenings[k] = (evenings[k] or 0) + 1
        elseif e.kind == "loot" then
            armor[name] = (armor[name] or 0) + 1
        end
    end
    local lines = {}
    local function add(label, who, value)
        lines[#lines + 1] = "|cffffd100" .. T(label) .. "|r " .. tostring(who):gsub("|", "||") .. " — " .. value
    end
    local zone, count = nil, 0
    for z, n in pairs(deathsIn) do if n > count then zone, count = z, n end end
    if zone and count >= F.FUN.zone_deaths then add("Most dangerous zone:", zone, count .. " " .. T("deaths")) end
    -- Deathless streaks (#164): levels and days since the last death.
    local now, ever = WoWStatusStreaks.records(group)
    if now then add("Longest deathless streak now:", now.name, WoWStatusStreaks.describe(now.streak)) end
    -- The same run twice says nothing new: "ever" only when it differs from "now".
    if ever and not (now and now.streak == ever.streak) then
        add("Longest deathless streak ever:", ever.name, WoWStatusStreaks.describe(ever.streak))
    end
    local best, levels = nil, 0
    for k, n in pairs(evenings) do if n > levels then best, levels = k, n end end
    if best and levels >= F.FUN.evening_levels then
        local name, day = best:match("^(.-)|(.+)$")
        add("Best evening:", name, levels .. " " .. T("levels") .. " (" .. day .. ")")
    end
    local fastest, quickest = nil, nil
    for name, s in pairs(toCap) do
        if s > 0 and (not quickest or s < quickest or (s == quickest and name < fastest)) then fastest, quickest = name, s end
    end
    if fastest then
        local days = math.floor(quickest / 86400)
        add("Fastest to maximum level:", fastest, days >= 1 and (days .. " " .. T(days == 1 and "day" or "days"))
            or (math.max(1, math.floor(quickest / 3600)) .. " " .. T("hours")))
        lines[#lines] = lines[#lines] .. " (" .. T("since first recorded activity") .. ")"
    end
    local mostArmor, pieces = nil, 0
    for name, n in pairs(armor) do if n > pieces then mostArmor, pieces = name, n end end
    if mostArmor and pieces >= F.FUN.armor then add("Most new gear:", mostArmor, tostring(pieces)) end
    if WoWStatusFeatures.enabled("nemesis") then
        for _, line in ipairs(F.nemesisLines(entries)) do lines[#lines + 1] = line end
    end
    local board = WoWStatusRoster.leaderboard(group)
    local function top(field)
        local t
        for _, row in ipairs(board) do if row[field] and (not t or row[field] > t[field]) then t = row end end
        return t
    end
    local d = top("deaths")
    if d and d.deaths >= F.FUN.deaths then add("Most deaths:", shortName(d.name), tostring(d.deaths)) end
    local k = top("kills")
    if k and k.kills >= F.FUN.kills then add("Most monsters killed:", shortName(k.name), tostring(k.kills)) end
    local g = top("gold")
    if g and g.gold >= F.FUN.gold then add("Richest:", shortName(g.name), WoWStatusUI.money(g.gold, true)) end
    return lines
end

-- Wrapped text uses its rendered height rather than a fixed one-line step.
local function textHeight(text, fallback)
    return math.max(fallback or 20, S.number(S.call(text.GetStringHeight, text)) or 0)
end
local function textView(lines, empty)
    local UI = WoWStatusUI
    page.textRows = page.textRows or {}
    if #lines == 0 then lines = {UI.MUTED_CODE .. T(empty) .. "|r"} end
    local y = 0
    for i, text in ipairs(lines) do
        local row = page.textRows[i]
        if not row then
            row = UI.text(page.list, "GameFontHighlight", 8, 0, 660)
            row:SetWordWrap(true); page.textRows[i] = row
        end
        row:ClearAllPoints(); row:SetPoint("TOPLEFT", 8, -y)
        row:SetText(text); row:Show()
        y = y + textHeight(row, 24) + 10
    end
    for i = #lines + 1, #page.textRows do page.textRows[i]:Hide() end
    page.list:SetHeight(math.max(1, y))
end

local WEEK_COLUMNS = {
    {key="name", label="Character", x=8, width=222, align="LEFT"},
    {key="level", label="Level-ups", x=238, width=76},
    {key="death", label="Deaths", x=318, width=76},
    {key="zone", label="Zones", x=398, width=76},
    {key="loot", label="Armor", x=478, width=76},
    {key="quest", label="Quests", x=558, width=112},
}
local function weekView(report)
    local UI = WoWStatusUI
    local frame = page.weekly
    if not frame then
        frame = CreateFrame("Frame", nil, page.list); page.weekly = frame
        frame:SetPoint("TOPLEFT"); frame:SetSize(686, 1)
        frame.highlights, frame.headers, frame.rows, frame.notes = {}, {}, {}, {}
    end
    frame:Show()
    for i, h in ipairs(report.highlights) do
        local row = frame.highlights[i]
        if not row then
            row = CreateFrame("Frame", nil, frame); row:SetSize(330, 46)
            row.label = UI.text(row, "GameFontNormalSmall", 8, 0, 314)
            row.value = UI.text(row, "GameFontHighlight", 8, -18, 314)
            row.value:SetHeight(28); row.value:SetWordWrap(true)
            frame.highlights[i] = row
        end
        row:ClearAllPoints(); row:SetPoint("TOPLEFT", ((i-1)%2)*348, -math.floor((i-1)/2)*52)
        row.label:SetText(T(h.label)); row.value:SetText(h.name:gsub("|", "||") .. " (" .. h.count .. ")")
        row:Show()
    end
    for i=#report.highlights+1,#frame.highlights do frame.highlights[i]:Hide() end
    local y = math.ceil(#report.highlights/2)*52 + 8
    for i, col in ipairs(WEEK_COLUMNS) do
        local header = frame.headers[i]
        if not header then
            header = UI.text(frame, "GameFontNormalSmall", col.x, 0, col.width, col.align or "RIGHT")
            frame.headers[i] = header
        end
        header:ClearAllPoints(); header:SetPoint("TOPLEFT", col.x, -y)
        header:SetText(T(col.label)); header:SetShown(#report.people > 0)
    end
    if #report.people > 0 then y = y + 26 end
    for i, person in ipairs(report.people) do
        local row = frame.rows[i]
        if not row then
            row = CreateFrame("Frame", nil, frame); row:SetWidth(686)
            row.fill = row:CreateTexture(nil, "BACKGROUND"); row.fill:SetAllPoints()
            row.fill:SetColorTexture(1, 1, 1, i%2 == 1 and .045 or 0)
            row.cells = {}
            for c, col in ipairs(WEEK_COLUMNS) do
                local cell = UI.text(row, "GameFontHighlight", col.x, -8, col.width, col.align or "RIGHT")
                cell:SetWordWrap(true); row.cells[c] = cell
            end
            frame.rows[i] = row
        end
        for c, col in ipairs(WEEK_COLUMNS) do
            local value = person[col.key]
            if col.key == "name" then value = value:gsub("|", "||")
            elseif value == 0 then value = UI.MUTED_CODE .. "–|r"
            elseif col.key == "level" then value = "+" .. value
            elseif col.key == "quest" then value = tostring(value*100)
            else value = tostring(value) end
            row.cells[c]:SetText(value)
        end
        local height = textHeight(row.cells[1], 20) + 16
        row:ClearAllPoints(); row:SetPoint("TOPLEFT", 0, -y); row:SetHeight(height); row:Show()
        y = y + height
    end
    for i=#report.people+1,#frame.rows do frame.rows[i]:Hide() end
    local notes = report.extras
    if #report.people == 0 and #notes == 0 then notes = {T("Nothing happened in this group this week.")} end
    if #notes > 0 then y = y + 12 end
    for i, line in ipairs(notes) do
        local note = frame.notes[i]
        if not note then
            note = UI.text(frame, "GameFontHighlight", 8, 0, 660); note:SetWordWrap(true); frame.notes[i] = note
        end
        note:ClearAllPoints(); note:SetPoint("TOPLEFT", 8, -y); note:SetText(line); note:Show()
        y = y + textHeight(note, 24) + 8
    end
    for i=#notes+1,#frame.notes do frame.notes[i]:Hide() end
    frame:SetHeight(math.max(1,y)); page.list:SetHeight(math.max(1,y))
end

local function render()
    if not page then return end
    local UI = WoWStatusUI
    local groups = F.groups()
    local chosen = selectedGroup(groups)
    local data = state() or {}
    local view = data.view or "firsts"
    if view ~= "firsts" and view ~= "week" and view ~= "fun" then view, data.view = "firsts", "firsts" end
    local titles = {firsts="Firsts", week="This week", fun="Fun records"}
    UI.dropdownLabel(page.view, T("View:") .. " " .. T(titles[view]))
    UI.dropdownLabel(page.pick, chosen and chosen.label:gsub("|", "||") or T("No group"))
    UI.call(page.pick, "SetEnabled", #groups > 1)
    UI.call(page.view, "SetEnabled", chosen ~= nil)
    page.weekBack:SetShown(view == "week" and chosen ~= nil)
    page.weekNext:SetShown(view == "week" and chosen ~= nil)
    if page.textRows then for _, row in ipairs(page.textRows) do row:Hide() end end
    if page.weekly then page.weekly:Hide() end
    for _, row in ipairs(page.rows) do row:SetShown(view == "firsts") end
    if page.recapBox then page.recapBox:SetShown(view == "firsts") end
    page.group = chosen and chosen.id
    page.export:SetEnabled(chosen ~= nil)
    page.dates:SetText("")
    page.heading:SetWidth(view == "week" and 530 or 690)
    page.heading:SetHeight(view == "week" and 28 or 48)
    if not chosen then
        page.heading:SetText(T("Join a group to compete for records with your friends."))
    end
    page.scroll:ClearAllPoints(); page.scroll:SetPoint("TOPLEFT", 24, -114)
    page.scroll:SetHeight(416)
    if not chosen and view ~= "firsts" then
        page.list:SetHeight(1)
        return
    end
    if view == "week" then
        page.weekOffset = page.weekOffset or 0
        local report = F.weekData(chosen.id, page.weekOffset)
        page.heading:SetText(T(page.weekOffset == 0 and "This week" or "Week"))
        page.dates:SetText(T("Dates: from") .. " " .. report.first .. " " .. T("to") .. " " .. report.last)
        UI.call(page.weekNext, "SetEnabled", page.weekOffset > 0)
        weekView(report)
        return
    elseif view == "fun" then
        page.heading:SetText(T("Fun records"))
        textView(F.funRecords(chosen.id), "No fun records yet. They appear when someone does something remarkable.")
        return
    end
    if chosen then page.heading:SetText(T("Firsts in") .. " " .. chosen.label:gsub("|", "||")) end
    local result, medals = {}, {}
    if chosen then result, medals = F.compute(WoWStatusJournal.entries(), chosen.id) end
    for i, medal in ipairs(medals) do
        local c = page.rows[i] or card(i)
        local column, line = (i - 1) % 2, math.floor((i - 1) / 2)
        c:ClearAllPoints(); c:SetPoint("TOPLEFT", column * (CARD_W + GAP), -line * (CARD_H + GAP))
        local e = result[medal.key]
        c.icon:SetIcon(medalIcon(medal), e == nil)
        c.title:SetText(T(medal.title))
        local when = e and WoWStatusHistory.localTime(e.at)
        -- Reached before WoW Status tracked it: the date is "by then".
        if e and e.milestone and not e.exact then when = T("before WoW Status, by") .. " " .. when:sub(1, 10) end
        local empty = medal.key == "dungeon" and T("No dungeon clear recorded yet.") or T("nobody yet")
        local who = e and (e.holder or name(e.sender)) or ""
        local holder = e and (who:gsub("|", "||") .. " · " .. when) or empty
        c.holder:SetText(e and holder or (WoWStatusUI.MUTED_CODE .. holder .. "|r"))
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
            table.insert(lines, "|cffffd100" .. WoWStatusHistory.localTime(e.at) .. "|r  " .. T(e.text):gsub("|", "||"))
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
    local recapY = 36
    for i, text in ipairs(lines) do
        local row = page.recaps[i]
        if not row then row = UI.text(box, "GameFontHighlight", 12, 0, 2 * CARD_W - 20); page.recaps[i] = row end
        row:SetWordWrap(true)
        row:ClearAllPoints(); row:SetPoint("TOPLEFT", 12, -recapY)
        row:SetText(text); row:Show()
        recapY = recapY + textHeight(row, 22) + 8
    end
    for i = #lines + 1, #page.recaps do page.recaps[i]:Hide() end
    box:SetHeight(recapY + 12)
    page.list:SetHeight(medalsHeight + recapY + 24)
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

-- quietly: recount without announcing (a mute change, #169).
function F.update(quietly)
    local data = state()
    if not data or not WoWStatusJournal.entries then return end
    data.group_holders = type(data.group_holders) == "table" and data.group_holders or {}
    local entries, announced = WoWStatusJournal.entries(), {}
    for _, group in ipairs(F.groups()) do
        local result, medals = F.compute(entries, group.id)
        -- The very first count stays quiet; later only live, recent entries are announced.
        local quiet = quietly or not data.initialized
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
                    WoWStatusPopups.notice({sender=e.sender, kind="first", source_kind=e.kind, text=medal.title .. "!",
                        flavour=T("A new record in") .. " " .. group.label:gsub("|", "||") .. "."})
                end
            end
        end
    end
    data.initialized = true
    if WoWStatusMainWindow then
        WoWStatusMainWindow.refresh("records")
        WoWStatusMainWindow.refresh("leaderboard")
    end
end

function F.buildRecords(parent)
    page = CreateFrame("Frame", "WoWStatusRecordsPage", parent); page:SetAllPoints(parent)
    local UI = WoWStatusUI
    page.heading = UI.text(page, "GameFontNormalLarge", 24, -52, 530)
    page.heading:SetHeight(28); page.heading:SetWordWrap(true)
    page.dates = UI.text(page, "GameFontHighlightSmall", 24, -84, 690)
    page.dates:SetHeight(20)
    page.scroll = CreateFrame("ScrollFrame", nil, page, "UIPanelScrollFrameTemplate")
    page.scroll:SetPoint("TOPLEFT", 24, -114); page.scroll:SetSize(710, 416)
    page.list = CreateFrame("Frame", nil, page.scroll); page.list:SetSize(686, 24)
    page.scroll:SetScrollChild(page.list)
    page.rows = {}
    local function button(label, x, width, fn)
        local b = CreateFrame("Button", nil, page, "UIPanelButtonTemplate")
        b:SetPoint("TOPLEFT", x, -8); b:SetSize(width, 28)
        UI.buttonLabel(b, T(label)); b:SetScript("OnClick", fn)
        b:SetScript("OnEnter", function(self)
            if GameTooltip and self.fullLabel and self.fullLabel ~= "" then
                GameTooltip:SetOwner(self, "ANCHOR_TOP")
                GameTooltip:ClearLines(); GameTooltip:AddLine(self.fullLabel, 1, 1, 1, true); GameTooltip:Show()
            end
        end)
        b:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
        return b
    end
    local function resetScroll() UI.call(page.scroll, "SetVerticalScroll", 0) end
    page.pick = button("", 24, 290, function(self)
        local items = {}
        for _, group in ipairs(F.groups()) do
            items[#items+1] = {label=group.label:gsub("|", "||"), value=group.id}
        end
        if #items < 2 then return end
        UI.menu(self, items, function(id)
            local d = state(); if d then d.tab = id end
            resetScroll(); F.render()
        end, 360)
    end)
    page.view = button("", 326, 256, function(self)
        UI.menu(self, {
            {label=T("Firsts"), value="firsts"}, {label=T("This week"), value="week"},
            {label=T("Fun records"), value="fun"},
        }, function(value)
            local d = state(); if d then d.view = value end
            if value == "week" then page.weekOffset = 0 end
            resetScroll(); F.render()
        end, 256)
    end)
    page.export = button("Export", 594, 118, function()
        local d = state() or {}
        WoWStatusExport.records(page.group, d.view or "firsts", page.weekOffset or 0)
    end)
    -- Earlier weeks (until /reload the view starts at this week).
    page.weekBack = button("<", 586, 56, function()
        page.weekOffset = (page.weekOffset or 0) + 1; resetScroll(); F.render()
    end)
    page.weekNext = button(">", 654, 56, function()
        page.weekOffset = math.max(0, (page.weekOffset or 0) - 1); resetScroll(); F.render()
    end)
    page.weekBack:ClearAllPoints(); page.weekBack:SetPoint("TOPLEFT", 586, -52)
    page.weekNext:ClearAllPoints(); page.weekNext:SetPoint("TOPLEFT", 654, -52)
    return page
end

WoWStatusMainWindow.register("records", "Records", F.buildRecords, render)
