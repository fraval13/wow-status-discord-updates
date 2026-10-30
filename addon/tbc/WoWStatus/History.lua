-- Saved event history and level timing. Pure data helpers are shared with the UI.
WoWStatusHistory = {}
local H = WoWStatusHistory
local indices = setmetatable({}, {__mode = "k"})

local function copy(value)
    if type(value) ~= "table" then return value end
    local result = {}
    for key, item in pairs(value) do result[key] = copy(item) end
    return result
end
H.copy = copy

-- Modern Europe/Oslo DST: last Sunday in March/October at 01:00 UTC.
local function daysBeforeYear(year)
    local y = year - 1
    return 365 * y + math.floor(y / 4) - math.floor(y / 100) + math.floor(y / 400)
end
local function transition(year, month)
    local leap = (year % 4 == 0 and (year % 100 ~= 0 or year % 400 == 0)) and 1 or 0
    local beforeMonth = month == 3 and (59 + leap) or (273 + leap)
    local lastDay = daysBeforeYear(year) - daysBeforeYear(1970) + beforeMonth + 30
    local weekday = (lastDay + 4) % 7 -- Sunday = 0; Unix epoch was a Thursday.
    return (lastDay - weekday) * 86400 + 3600
end
function H.oslo(at)
    local year = tonumber(date("!%Y", at))
    local summer = at >= transition(year, 3) and at < transition(year, 10)
    local offset = summer and 7200 or 3600
    return date("!%Y-%m-%d %H:%M:%S", at + offset) .. (summer and " +02:00" or " +01:00")
end
function H.duration(seconds)
    seconds = math.max(0, math.floor(seconds))
    local days = math.floor(seconds / 86400)
    local hours = math.floor(seconds / 3600) % 24
    local minutes = math.floor(seconds / 60) % 60
    return (days > 0 and (days .. "d ") or "") .. hours .. "h " .. minutes .. "m " .. (seconds % 60) .. "s"
end

local function allowed(character, event)
    if event.kind=="quest" and not event.data.completed then return false end
    if event.kind == "discovery" or event.kind == "lfg" then return false end
    if event.kind == "dungeon" and event.data.source ~= "game_api" then return false end
    if event.kind=="loot" and not WoWStatusLoot.allowed(character.settings,WoWStatusLoot.eventInfo(event.data)) then return false end
    local settings = character.settings
    if not settings.enabled or not settings.collection[event.kind] then return false end
    if event.kind == "level" and not settings.fields.level then return false end
    if event.kind == "equipment" and not settings.fields.gear then return false end
    if event.kind == "zone" and not settings.fields.zone then return false end
    return true
end

function H.init(character)
    character.history = character.history or {version = 1, timezone = "Europe/Oslo", events = {}}
    local history = character.history
    history.timezone = "Europe/Oslo"
    history.events = history.events or {}
    history.tracking = history.tracking or {points = {}, segment = 0, active = false}
    local seen = {}
    for _, event in ipairs(history.events) do seen[event.id] = true end
    -- Upgrade the old rolling buffer without fabricating older events.
    for _, event in ipairs(character.events or {}) do
        if not seen[event.id] then
            table.insert(history.events, copy(event))
            seen[event.id] = true
        end
    end
    indices[character] = seen
    if #history.tracking.points == 0 then
        local levels = {}
        for _, event in ipairs(history.events) do
            if event.kind == "level" and not event.data.synthetic then table.insert(levels, event) end
        end
        table.sort(levels, function(a, b) return a.at < b.at end)
        local previous
        for _, event in ipairs(levels) do
            if not previous or event.data.level ~= previous.level + 1 or event.at < previous.at then
                history.tracking.segment = history.tracking.segment + 1
            end
            local point = {kind = "level", level = event.data.level, at = event.at,
                event_id = event.id, segment = character.epoch .. ":" .. history.tracking.segment}
            table.insert(history.tracking.points, point)
            previous = point
        end
        if previous then
            history.tracking.active = true
            history.tracking.observed_until = previous.at
        end
    end
end

function H.sync(character, level, at)
    if not character.history then H.init(character) end
    local tracking = character.history.tracking
    if not character.settings.enabled or not character.settings.fields.level
        or not character.settings.collection.level then
        character.history.tracking = {points = {}, segment = 0, active = false}
        return
    end
    local last = tracking.points[#tracking.points]
    if not tracking.active or not last or last.level ~= level or at < last.at then
        tracking.segment = tracking.segment + 1
        table.insert(tracking.points, {kind = "baseline", level = level, at = at,
            segment = character.epoch .. ":" .. tracking.segment})
    end
    tracking.active = true
    tracking.observed_until = at
end

function H.record(character, event)
    if not character.history then H.init(character) end
    local seen = indices[character]
    if not seen then H.init(character); seen = indices[character] end
    if seen[event.id] then return end
    table.insert(character.history.events, copy(event))
    seen[event.id] = true
    if event.kind == "level" and not event.data.synthetic then
        local tracking = character.history.tracking
        local last = tracking.points[#tracking.points]
        if not tracking.active or not last or event.data.level ~= last.level + 1 or event.at < last.at then
            tracking.segment = tracking.segment + 1
        end
        table.insert(tracking.points, {kind = "level", level = event.data.level, at = event.at,
            event_id = event.id, segment = character.epoch .. ":" .. tracking.segment})
        tracking.active = true
        tracking.observed_until = event.at
    end
end

function H.scrubEvent(character, event)
    if not character.settings.fields.zone then event.data.zone = nil end
    if not character.settings.fields.playtime then event.data.played_level_seconds = nil end
end

function H.scrub(character)
    if not character.history then H.init(character) end
    local events = {}
    for _, event in ipairs(character.history.events) do
        if allowed(character, event) then
            H.scrubEvent(character, event)
            table.insert(events, event)
        end
    end
    character.history.events = events
    indices[character] = nil
    -- Rebuild the transient ID index; it must never become part of SavedVariables.
    local seen = {}
    for _, event in ipairs(events) do seen[event.id] = true end
    indices[character] = seen
    if not character.settings.enabled or not character.settings.fields.level
        or not character.settings.collection.level then
        character.history.tracking = {points = {}, segment = 0, active = false}
    end
end

function H.timing(character)
    local result = {}
    local points = character.history and character.history.tracking.points or {}
    for i = 2, #points do
        local previous, point = points[i - 1], points[i]
        if previous.segment == point.segment and point.kind == "level"
            and point.level == previous.level + 1 and point.at >= previous.at then
            table.insert(result, {level = previous.level, next_level = point.level,
                seconds = point.at - previous.at, partial = previous.kind == "baseline",
                started_at = previous.at, finished_at = point.at})
        end
    end
    return result
end

function H.serialize(value)
    if type(value) ~= "table" then return tostring(value) end
    local keys, result = {}, {}
    for key in pairs(value) do table.insert(keys, key) end
    table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
    for _, key in ipairs(keys) do
        table.insert(result, tostring(key) .. "=" .. H.serialize(value[key]))
    end
    return "{" .. table.concat(result, ", ") .. "}"
end
