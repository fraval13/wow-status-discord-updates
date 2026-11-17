-- Deathless streaks (#164): levels gained and time played since a character's
-- last death, worked out locally from the activity log. Nothing new is sent.
-- The log is bounded, so a streak with no death in the log started before it:
-- it reads "at least" instead of a wrong exact number. A character's streak is
-- shown only while its "Total deaths" field is shared (its roster row carries a
-- death total) and that total agrees with the last logged death, so a death the
-- log never saw (death announcements off) hides the streak instead of growing it.
WoWStatusStreaks = {}
local St, S = WoWStatusStreaks, WoWStatusSafe
local T = WoWStatusLocale.T
-- A streak this long is worth a Records row, a line when it ends, and the first
-- milestone; later milestones come every LONG_LEVELS levels or week.
St.LONG_LEVELS, St.LONG_DAYS = 5, 7
local DAY, WEEK = 86400, 7 * 86400
local ANNOUNCE_WITHIN = 600
-- Results are kept until the log changes, or this long (what is hidden, muted
-- or shared can change without a new entry), as the roster's log facts are.
local MEMO_SECONDS = 5

-- The roster's key: on WoW Forever it drops the internal realm, as the roster does.
local function key(sender) return WoWStatusRoster.key(sender) end
local function shortName(sender) return (tostring(sender):match("^[^-]+") or tostring(sender)) end
local function clock() return S.uptime() end

-- Longer first by levels, then by time.
local function longer(a, b)
    if a.levels ~= b.levels then return a.levels > b.levels end
    return a.seconds > b.seconds
end

-- {current={key=streak}, best={key=streak}, ended={entry id=streak}, total={key=n}, sender={key=name}}
-- for one group (nil: the whole visible log). A death counts in every group,
-- even when it was shared in another one: it ends the run all the same. A streak is {levels, seconds,
-- exact, start}; a current streak's seconds run to the character's newest log
-- entry, so a friend who stopped playing does not keep gaining days. Levels are
-- the rise in level since the death when the level then is known, else the
-- distinct levels reached, so a missing or repeated level-up entry cannot skew
-- it much. A Hardcore death ends its character's run: no current streak, until a
-- level-up shows a new character under the same name.
local function levels(r)
    if r.base and r.top then return math.max(0, r.top - r.base) end
    return r.count
end
local function compute(group)
    local list = {}
    for _, e in ipairs(WoWStatusJournal.entries()) do
        if type(e) == "table" and S.number(e.at) and type(e.id) == "string" and not e.imported
            and (not group or e.kind == "death" or (type(e.groups) == "table" and e.groups[group] == true))
            and WoWStatusJournal.visible(e) and key(e.sender) then
            list[#list + 1] = e
        end
    end
    table.sort(list, function(a, b) if a.at == b.at then return a.id < b.id end return a.at < b.at end)
    local run, result = {}, {current={}, best={}, ended={}, total={}, sender={}, finished={}}
    -- The total the previous death carried, if it carried one ("Died" has none).
    local previousTotal = {}
    local function keep(k, streak)
        local best = result.best[k]
        if not best or longer(streak, best) then result.best[k] = streak end
    end
    for _, e in ipairs(list) do
        local k = key(e.sender)
        local r = run[k]
        if not r or (result.finished[k] and e.kind == "level") then
            result.finished[k] = nil
            r = {start=e.at, exact=false, reached={}, count=0}; run[k] = r
        end
        result.sender[k] = e.sender
        r.last = e.at
        local level = e.kind == "level" and S.number(e.level)
        if level then
            if not r.reached[level] then r.reached[level], r.count = true, r.count + 1 end
            if not r.top or level > r.top then r.top = level end
        elseif e.kind == "death" then
            local total = tonumber(tostring(e.text or ""):match("^Total deaths: (%d+)$"))
            -- Totals that jump (3, then 5) mean a death between them never reached
            -- the log, so the run they bound was not deathless: it counts nowhere.
            local previous = previousTotal[k]
            if not (total and previous and total > previous + 1) then
                local streak = {levels=levels(r), seconds=math.max(0, e.at - r.start), exact=r.exact, start=r.start}
                result.ended[e.id] = streak
                keep(k, streak)
            end
            run[k] = {start=e.at, exact=true, reached={}, count=0, base=r.top, top=r.top, last=e.at}
            if total then result.total[k] = total end
            previousTotal[k] = total
            result.finished[k] = WoWStatusProgress.hardcoreDeath(e) or nil
        end
    end
    for k, r in pairs(run) do
        if not result.finished[k] then
            local streak = {levels=levels(r), seconds=math.max(0, r.last - r.start), exact=r.exact, start=r.start, current=true}
            result.current[k] = streak
            keep(k, streak)
        end
    end
    return result
end

local memo = {}
local function cached(name, build)
    local entries = WoWStatusJournal.entries()
    local stamp = tostring(entries) .. ":" .. #entries .. ":" .. tostring(entries[1] and entries[1].id)
    local m = memo[name]
    if m and m.stamp == stamp and clock() - m.at < MEMO_SECONDS then return m.value end
    local value = build()
    memo[name] = {stamp=stamp, at=clock(), value=value}
    return value
end
function St.compute(group) return cached("log:" .. tostring(group), function() return compute(group) end) end
-- Forget remembered results (the log or the roster changed under a test).
function St.reset() memo = {} end

-- The death total a roster row's character shares itself, or nil. A friend's
-- row says so in deaths_shared (false: not shared), because its deaths falls
-- back to the log; this account's own rows carry only what they share.
function St.sharedDeaths(row)
    if type(row) ~= "table" then return nil end
    if row.deaths_shared ~= nil then return S.number(row.deaths_shared) end
    return S.number(row.deaths)
end

-- Death totals that characters share in a group (own characters included):
-- key -> total. A character without the "Total deaths" field is missing.
function St.totals(group)
    return cached("board:" .. tostring(group), function()
        local totals = {}
        for _, row in ipairs(WoWStatusRoster.leaderboard(group) or {}) do
            local k = key(row.name)
            local deaths = St.sharedDeaths(row)
            if k and deaths then totals[k] = deaths end
        end
        return totals
    end)
end

-- Whether a character's streak may be shown, given the death total it shares.
local function shown(data, k, deaths)
    deaths = S.number(deaths)
    if not deaths then return false end
    local logged = data.total[k]
    return not (logged and deaths > logged)
end

-- A character's death total shared in any of the given groups, or nil.
local function sharedTotal(k, groups)
    local ids = {}
    for id, member in pairs(type(groups) == "table" and groups or {}) do if member == true then ids[#ids + 1] = id end end
    table.sort(ids)
    for _, id in ipairs(ids) do
        local deaths = St.totals(id)[k]
        if deaths then return deaths end
    end
    return nil
end

-- The current streak of the character in a roster row (a profile), or nil.
function St.forRow(row)
    if type(row) ~= "table" then return nil end
    local k, data = key(row.name), St.compute(nil)
    if not k or not shown(data, k, St.sharedDeaths(row)) then return nil end
    return data.current[k]
end

-- Records (#164): the longest current streak and the longest ever in a group,
-- each {name, streak}, only when long enough to be remarkable.
local function long(streak)
    return streak.levels >= St.LONG_LEVELS or streak.seconds >= St.LONG_DAYS * DAY
end
function St.records(group)
    local data, totals = St.compute(group), St.totals(group)
    local now, ever
    for k, streak in pairs(data.best) do
        if shown(data, k, totals[k]) then
            local current = data.current[k]
            if current and long(current) and (not now or longer(current, now.streak)
                or (not longer(now.streak, current) and k < now.key)) then
                now = {key=k, name=shortName(data.sender[k]), streak=current}
            end
            if long(streak) and (not ever or longer(streak, ever.streak)
                or (not longer(ever.streak, streak) and k < ever.key)) then
                ever = {key=k, name=shortName(data.sender[k]), streak=streak}
            end
        end
    end
    return now, ever
end

local function amount(n, one, many) return n .. " " .. T(n == 1 and one or many) end
local function atLeast(streak, text) return streak.exact and text or (T("at least") .. " " .. text) end

-- "12 levels · 9 days", "at least 3 days"; nil when there is nothing to say.
function St.describe(streak)
    if type(streak) ~= "table" then return nil end
    local parts = {}
    if streak.levels > 0 then parts[#parts + 1] = amount(streak.levels, "level", "levels") end
    local days = math.floor(streak.seconds / DAY)
    if days > 0 then parts[#parts + 1] = amount(days, "day", "days") end
    if #parts == 0 then return nil end
    return atLeast(streak, table.concat(parts, " · "))
end

local function capital(text) return (text:gsub("^%l", string.upper)) end

-- The log's line for a death that ends a long streak (#164): "12 levels without
-- a death ends in Stranglethorn Vale." A Hardcore death ends a whole life, which
-- is the memorial's to tell (#149), so it gets none.
function St.endedText(e)
    if type(e) ~= "table" or e.kind ~= "death" or WoWStatusProgress.hardcoreDeath(e) then return nil end
    local k = key(e.sender)
    local data = St.compute(nil)
    local streak = k and data.ended[e.id]
    if not streak or not long(streak) or not shown(data, k, sharedTotal(k, e.groups)) then return nil end
    -- The longer measure: levels when there are enough of them, else days.
    local what = atLeast(streak, streak.levels >= St.LONG_LEVELS and amount(streak.levels, "level", "levels")
        or amount(math.floor(streak.seconds / DAY), "day", "days"))
    local d = WoWStatusJournal.details(e)
    local zone = d and S.string(d.zone)
    return capital(what .. " " .. (zone and (T("without a death ends in") .. " " .. zone .. ".") or T("without a death ends here.")))
end

-- Milestones (#164): off by default. When on, a live or own log entry whose
-- character's streak since a logged death just reached a milestone shows a
-- local notice: every LONG_LEVELS levels and every week. The highest of each
-- announced is remembered per streak (its start), so none repeats. Nothing is
-- sent or logged.
local function state()
    if type(WoWStatusDB) ~= "table" then return nil end
    if type(WoWStatusDB.streaks) ~= "table" then WoWStatusDB.streaks = {} end
    local data = WoWStatusDB.streaks
    if type(data.weeks) ~= "table" then data.weeks = {} end
    return data
end
function St.milestones()
    return WoWStatusSettings.get("streak_milestones", WoWStatusDB) == true
end
function St.setMilestones(value)
    if state() then WoWStatusSettings.set("streak_milestones", value == true, WoWStatusDB) end
end

-- The notice text for an entry that brings its streak to a milestone, or nil.
local MEMORY = 200
local function milestone(e, streak, data, k)
    local seen = data.weeks[k]
    if type(seen) ~= "table" or seen.start ~= streak.start then seen = {start=streak.start} end
    -- Levels on the level-up that reaches them; a skipped one waits for the next.
    local levels = e.kind == "level" and streak.levels % St.LONG_LEVELS == 0 and streak.levels or 0
    local weeks = math.floor(streak.seconds / WEEK)
    local text
    -- One notice per entry; a week reached on a level milestone waits for the next.
    if levels >= St.LONG_LEVELS and levels > (S.number(seen.levels) or 0) then
        text, seen.levels = levels .. " levels without a death!", levels
    elseif weeks >= 1 and weeks > (S.number(seen.weeks) or 0) then
        text, seen.weeks = weeks == 1 and "A week without a death!" or (weeks .. " weeks without a death!"), weeks
    end
    if not text then return nil end
    if not data.weeks[k] then
        -- Bounded: past MEMORY characters, forget the one whose streak began first.
        local count, oldest, oldestStart = 0, nil, math.huge
        for other, value in pairs(data.weeks) do
            count = count + 1
            local at = type(value) == "table" and S.number(value.start) or -math.huge
            if at < oldestStart then oldest, oldestStart = other, at end
        end
        if count >= MEMORY and oldest then data.weeks[oldest] = nil end
    end
    data.weeks[k] = seen
    return text
end

function St.noted(e)
    local data = state()
    if not data or not St.milestones() or type(e) ~= "table" or e.imported or (e.origin ~= "live" and e.origin ~= "mine") then return end
    if e.kind == "death" or not S.number(e.at) or S.outside(e.at, ANNOUNCE_WITHIN, math.huge) then return end
    local k = key(e.sender)
    if not k then return end
    local logged = St.compute(nil)
    local streak = logged.current[k]
    -- Only a streak that starts at a logged death: one that starts where the log
    -- does moves forward as old entries are dropped, and would repeat milestones.
    if not streak or not streak.exact or not shown(logged, k, sharedTotal(k, e.groups)) then return end
    local text = milestone(e, streak, data, k)
    if text and WoWStatusPopups.notice then
        WoWStatusPopups.notice({sender=e.sender, kind="first", text=text, flavour=T("Deathless streak")})
    end
end
