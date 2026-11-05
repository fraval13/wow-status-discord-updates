-- Session recaps (#66): a short story of each play session, written to your
-- own activity log as a private entry (never sent). A session ends at logout
-- or after 30 minutes without activity; nothing happening means no recap.
-- The session is saved on the character, so /reload continues it: a logout
-- followed by a login within a minute counts as the same session.
WoWStatusRecaps = {}
local R, S = WoWStatusRecaps, WoWStatusSafe
R.IDLE, R.RELOAD = 1800, 60
local character
local ORDER = {"dungeon", "death", "profession", "mount", "loot", "zone", "quest", "reputation", "unlock", "pvp"}

local function count(n, one, many) return n == 1 and one or (n == 2 and many == "times" and "twice") or (n .. " " .. many) end

local function level() return S.number(WoWStatusAdapter.level and WoWStatusAdapter.level()) end

local function start(startLevel)
    character.session = {started=S.now(), last=S.now(), start_level=startLevel or level(), counts={}, dungeons={}}
    return character.session
end

local function prefix(at)
    local hour = tonumber(date("%H", at)) or 20
    if hour >= 4 and hour < 12 then return "This morning" end
    if hour >= 12 and hour < 18 then return "This afternoon" end
    return "Tonight"
end

-- The recap sentence, or nil when nothing happened.
function R.text(session, name, at)
    if type(session) ~= "table" or type(session.counts) ~= "table" or not next(session.counts) then return nil end
    local c, parts = session.counts, {}
    local from, to = S.number(session.start_level), S.number(session.top_level)
    if to and from and to > from then table.insert(parts, "went from " .. from .. " to " .. to)
    elseif to then table.insert(parts, "reached level " .. to) end
    local phrases = {
        death=function(n) return "died " .. count(n, "once", "times") end,
        zone=function(n) return "discovered " .. count(n, "a new zone", "new zones") end,
        profession=function(n) return count(n, "reached a profession milestone", "profession milestones") end,
        mount=function() return "got a first mount" end,
        loot=function(n) return "equipped " .. count(n, "a new item", "new items") end,
        quest=function() return "passed another 100 quests" end,
        reputation=function(n) return count(n, "gained a reputation rank", "reputation ranks") end,
        unlock=function(n) return count(n, "unlocked a class ability", "class ability unlocks") end,
        pvp=function(n) return count(n, "earned a PvP promotion", "PvP promotions") end,
    }
    for _, kind in ipairs(ORDER) do
        if kind == "dungeon" and #session.dungeons > 0 then
            table.insert(parts, "cleared " .. table.concat(session.dungeons, " and "))
        elseif c[kind] and phrases[kind] then
            table.insert(parts, phrases[kind](c[kind]))
        end
    end
    if #parts == 0 then return nil end
    return prefix(at or session.last or S.now()) .. ": " .. name .. " " .. table.concat(parts, ", ") .. "."
end

-- Write the recap (if anything happened) and end the session.
function R.close(at)
    local session = character and character.session
    if not session then return false end
    character.session = nil
    local text = R.text(session, character.identity.name, at)
    if not text then return false end
    local main = session.top_level and "level" or (#session.dungeons > 0 and "dungeon") or next(session.counts)
    local flavour = WoWStatusFlavour.text({kind=main, level=session.top_level, sender=character.identity.name,
        id="recap:" .. tostring(at)})
    return WoWStatusJournal.recordRecap(character, at, text, flavour)
end

-- Called with each newly created own event.
function R.note(event)
    if not character or type(event) ~= "table" or (event.data and event.data.synthetic) then return end
    if event.kind == "introduction" then return end
    local data = event.data or {}
    local session = character.session or start(event.kind == "level" and S.number(data.level) and data.level - 1 or nil)
    session.last = S.now()
    session.counts[event.kind] = (session.counts[event.kind] or 0) + 1
    if event.kind == "level" and S.number(data.level) then
        session.top_level = math.max(session.top_level or 0, data.level)
    elseif event.kind == "dungeon" and S.string(data.name) and #session.dungeons < 4 then
        table.insert(session.dungeons, data.name)
    end
end

function R.activity()
    if character and character.session then character.session.last = S.now() end
end

function R.tick()
    local session = character and character.session
    if session and not session.ended_at and S.now() - (session.last or S.now()) >= R.IDLE then R.close(session.last) end
end

function R.logout()
    if character and character.session then character.session.ended_at = S.now() end
end

-- At login: a session that ended more than a minute ago gets its recap now;
-- a shorter gap (a /reload) continues it.
function R.init(current)
    character = current
    local session = character.session
    if type(session) ~= "table" then character.session = nil; session = nil end
    if session and session.ended_at then
        if S.now() - session.ended_at > R.RELOAD then R.close(session.ended_at)
        else session.ended_at = nil end
    end
    if not character.session then start() end
end

if C_Timer and C_Timer.NewTicker then C_Timer.NewTicker(60, function() R.tick() end) end
