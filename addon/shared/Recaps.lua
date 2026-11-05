-- Session recaps (#66): a short story of each play session, written to your
-- own activity log, with compact group sharing only when opted in. A session ends at logout
-- or after 30 minutes without activity; nothing happening means no recap.
-- The session is saved on the character, so /reload continues it: a logout
-- followed by a login within a minute counts as the same session.
WoWStatusRecaps = {}
local R, S = WoWStatusRecaps, WoWStatusSafe
R.IDLE, R.RELOAD = 1800, 60
local character,emit
local ORDER = {"dungeon", "raid", "death", "profession", "mount", "epicmount", "loot", "zone", "quest", "reputation", "unlock", "pvp"}

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
        epicmount=function() return "got a first epic mount" end,
        raid=function(n) return "defeated " .. count(n, "a first raid boss", "first raid bosses") end,
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

local sharedPhrases={level={"level up","level ups"},dungeon={"dungeon clear","dungeon clears"},
    raid={"raid boss kill","raid boss kills"},death={"death","deaths"},
    profession={"profession milestone","profession milestones"},mount={"first mount","first mounts"},
    epicmount={"epic mount","epic mounts"},loot={"first equip","first equips"},zone={"new zone","new zones"},
    quest={"quest milestone","quest milestones"},reputation={"reputation rank","reputation ranks"},
    unlock={"class unlock","class unlocks"},pvp={"PvP promotion","PvP promotions"}}
local sharedOrder={"level","dungeon","raid","death","profession","mount","epicmount","loot","zone","quest","reputation","unlock","pvp"}
function R.sharedText(session,settings)
    local parts={}
    for _,kind in ipairs(sharedOrder) do
        local n=S.number(session.counts[kind])
        local category=({raid="dungeon",epicmount="mount"})[kind] or kind
        local field=({level="level",zone="zone",quest="quests",profession="professions",loot="gear"})[kind]
        local allowed=not settings or (settings.collection[category] and settings.in_game[category]~=false
            and (not field or settings.fields[field]))
        if allowed and n and n>=1 and n<=10000 and n==math.floor(n) then
            local part=n.." "..sharedPhrases[kind][n==1 and 1 or 2]
            if #("Session recap: "..table.concat(parts,", ")..(#parts>0 and ", " or "")..part..".")<=120 then
                parts[#parts+1]=part
            end
        end
    end
    if #parts==0 then return nil end
    return "Session recap: "..table.concat(parts,", ").."."
end
function R.validShared(text)
    if type(text)~="string" or #text>120 then return false end
    local body=text:match("^Session recap: (.+)%.$")
    if not body then return false end
    local seen,parts={},{}
    for part in (body..", "):gmatch("(.-), ") do
        local n,phrase=part:match("^([1-9]%d*) (.+)$")
        n=tonumber(n)
        local kind
        for key,value in pairs(sharedPhrases) do if value[n==1 and 1 or 2]==phrase then kind=key end end
        if not n or n>10000 or not kind or seen[kind] then return false end
        seen[kind]=true;parts[#parts+1]=part
    end
    return #parts>0 and table.concat(parts,", ")==body
end
-- Write the recap (if anything happened) and end the session.
function R.close(at)
    local session = character and character.session
    if not session then return false end
    character.session = nil
    local text = R.text(session, character.chat_name or character.identity.name, at)
    if not text then return false end
    if emit and character.settings.enabled and character.settings.in_game.recap then
        local shared=R.sharedText(session,character.settings)
        if shared then return emit("recap",{text=shared,source="session_recap"})~=nil end
    end
    local main = session.top_level and "level" or (#session.dungeons > 0 and "dungeon") or next(session.counts)
    local flavour = WoWStatusFlavour.text({kind=main, level=session.top_level, sender=character.chat_name or character.identity.name,
        id="recap:" .. tostring(at)})
    return WoWStatusJournal.recordRecap(character, at, text, flavour)
end

-- Called with each newly created own event.
function R.note(event)
    if not character or type(event) ~= "table" or (event.data and event.data.synthetic) then return end
    if event.kind == "introduction" or event.kind=="recap" then return end
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
function R.init(current,callback)
    character,emit = current,callback or emit
    local session = character.session
    if type(session) ~= "table" then character.session = nil; session = nil end
    if session and session.ended_at then
        if S.now() - session.ended_at > R.RELOAD then R.close(session.ended_at)
        else session.ended_at = nil end
    end
    if not character.session then start() end
end

if C_Timer and C_Timer.NewTicker then C_Timer.NewTicker(60, function() R.tick() end) end
