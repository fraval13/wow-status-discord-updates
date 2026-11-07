-- Public character observations. Missing APIs stay unavailable, never invented.
WoWStatusProgress = {}
local P, S = WoWStatusProgress, WoWStatusSafe
local questReady, questRequested = false, false
local professionAt, professionCache, professionComplete, questAt
local knownProfessions = {
    alchemy={2259,171,"Alchemy"}, blacksmithing={2018,164,"Blacksmithing"},
    enchanting={7411,333,"Enchanting"}, engineering={4036,202,"Engineering"},
    herbalism={2366,182,"Herbalism"}, leatherworking={2108,165,"Leatherworking"},
    mining={2575,186,"Mining"}, skinning={8613,393,"Skinning"}, tailoring={3908,197,"Tailoring"},
    jewelcrafting={25229,755,"Jewelcrafting"},
    cooking={2550,185,"Cooking"}, first_aid={3273,129,"First Aid"}, fishing={7620,356,"Fishing"},
}
local function stats(character)
    if not character.progress then
        local now = S.now()
        local started = tonumber((character.epoch or ""):match("^(%d+)")) or now
        if started < 1 or started > now then started = now end
        local deaths = 0
        for _, event in ipairs(character.history and character.history.events or {}) do
            if event.kind == "death" then deaths = deaths + 1 end
        end
        character.progress = {started_at=started, deaths=deaths, quest_ids={}}
    end
    local value = character.progress
    value.started_at, value.deaths, value.quest_ids = value.started_at or S.now(), value.deaths or 0, value.quest_ids or {}
    return value
end
local function readProfessions()
    if WoWStatusAdapter.professions then return WoWStatusAdapter.professions() end
    local result, names, ids, complete = {}, {}, {}, true
    for key, definition in pairs(knownProfessions) do
        local name = S.stringCall(GetSpellInfo, definition[1])
        if not name and C_Spell and C_Spell.GetSpellInfo then
            local info = S.value(S.call(C_Spell.GetSpellInfo, definition[1]))
            if type(info) == "table" then name = S.string(info.name) end
        end
        names[name or definition[3]], ids[definition[2]] = key, key
    end
    if C_SkillInfo and C_SkillInfo.GetSkillLineInfoByID then
        -- Forever's modern API returns structures rather than Classic tuples.
        -- Query known skill IDs directly so collapsed UI headers do not hide them.
        local available = false
        for key, definition in pairs(knownProfessions) do
            local ok, info = pcall(C_SkillInfo.GetSkillLineInfoByID, definition[2])
            info = S.value(info)
            if ok then available = true end
            if ok and type(info)=="table" then
                local name, rank, maximum = S.string(info.name),S.number(info.rank),S.number(info.maxRank)
                if name and rank and rank>0 and maximum and maximum>1 and S.value(info.isHeader)==false then
                    table.insert(result,{name=name,skill=rank,max_skill=maximum,key=key,source="game_api"})
                end
            end
        end
        if not available then return nil end
    elseif GetProfessions and GetProfessionInfo then
        local ok, a,b,c,d,e,f = pcall(GetProfessions)
        if not ok then return nil end
        for _, rawIndex in pairs({a,b,c,d,e,f}) do
            local index = S.number(rawIndex)
            if index then
                local valid, name, _, rank, maximum, _, _, skillID = pcall(GetProfessionInfo, index)
                name, rank, maximum, skillID = S.string(name), S.number(rank), S.number(maximum), S.number(skillID)
                if valid and name and rank and maximum and rank >= 0 and maximum > 0 then
                    table.insert(result, {name=name, skill=rank, max_skill=maximum, key=ids[skillID] or names[name], source="game_api"})
                end
            end
        end
    end
    local classic=WoWStatusAdapter.client_id=="classic-era" or WoWStatusAdapter.client_id=="tbc-anniversary"
    if #result==0 and GetNumSkillLines and GetSkillLineInfo and (classic or not GetProfessions) then
        local count = S.number(S.call(GetNumSkillLines))
        if not count then return nil end
        local collapsed = false
        for index = 1, math.min(count, 512) do
            local ok, name, header, expanded, rank, _, _, maximum = pcall(GetSkillLineInfo, index)
            name, rank, maximum = S.string(name), S.number(rank), S.number(maximum)
            header, expanded = S.value(header), S.value(expanded)
            if not ok then complete = false end
            if ok and header and not expanded then collapsed = true; complete = false end
            if ok and name and not header and names[name] and rank and maximum and maximum > 1 then
                table.insert(result, {name=name, skill=rank, max_skill=maximum, key=names[name], source="game_api"})
            end
        end
        if #result == 0 and collapsed then return nil end
    elseif not GetProfessions and not (C_SkillInfo and C_SkillInfo.GetSkillLineInfoByID) then return nil end
    table.sort(result, function(a,b) return a.name < b.name end)
    return result, complete
end
function P.professions(force)
    if not force and professionAt and time() - professionAt < 5 then return professionCache, professionComplete end
    professionCache, professionComplete = readProfessions()
    professionAt = time()
    return professionCache, professionComplete
end
function P.queryComplete() questReady, questAt = true, nil end
function P.observe(character, fields)
    local value, result = stats(character), {}
    if fields.level then
        local xp, maximum = S.number(S.call(UnitXP,"player")), S.number(S.call(UnitXPMax,"player"))
        if xp and maximum and maximum > 0 and xp >= 0 and xp <= maximum then
            result.xp_current, result.xp_max = xp, maximum
            result.xp_percent = math.floor(xp / maximum * 1000 + .5) / 10
        end
    end
    if fields.deaths then
        result.deaths, result.deaths_since = value.deaths, value.started_at
        if value.death_base then result.deaths_lifetime = P.totalDeaths(character) end
    end
    if fields.gold then
        result.gold = S.number(value.gold)
        result.gold_earned, result.gold_lifetime = P.goldEarned(character), value.gold_base ~= nil or nil
    end
    if fields.kills then
        result.kills, result.kills_lifetime, result.kills_since = P.totalKills(character), value.kill_base ~= nil or nil, value.started_at
    end
    if fields.quests then
        local completed, modern
        local sample = not questAt or time() - questAt >= 5
        if sample and C_QuestLog and C_QuestLog.GetAllCompletedQuestIDs then
            completed, modern = S.value(S.call(C_QuestLog.GetAllCompletedQuestIDs)), true
        elseif sample and questReady and GetQuestsCompleted then completed = S.value(S.call(GetQuestsCompleted)) end
        if type(completed) == "table" then
            local total = 0
            for key, item in pairs(completed) do
                local id = modern and S.number(item) or S.number(key)
                if id and id > 0 and (modern or S.value(item)) then total = total + 1 end
            end
            value.game_quests = math.max(value.game_quests or 0, total)
            questAt = time()
        elseif not questRequested and QueryQuestsCompleted then
            questRequested = true; pcall(QueryQuestsCompleted)
        end
        local total = 0
        for _ in pairs(value.quest_ids) do total = total + 1 end
        result.quests_completed = value.game_quests or total
        result.quests_source = value.game_quests and "game_api" or "tracked_since"
        result.quests_since = value.started_at
    end
    if fields.professions then
        local professions = P.professions()
        if professions then value.professions = professions end
        result.professions = value.professions or character.professions
    end
    return result
end
-- Gold and kills. Gold earned adds every rise in gold (loot, quests, sales,
-- mail); spending never lowers it. Kills count monsters killed for experience.
-- Both count from installation; where the client has statistics (Retail;
-- Forever if its client has them) the game's lifetime totals are used instead:
-- 1197 "Total kills" and 328 "Total gold acquired".
local STAT_KILLS, STAT_GOLD = 1197, 328
local LIMIT = 2000000000
local function statistic(id)
    if not GetStatistic then return nil end
    local raw = S.call(GetStatistic, id)
    local text = S.string(raw)
    local n = S.number(raw) or (text and tonumber(text))
    if not n and text then
        -- Money statistics are text with coin icons: "12|T...GoldIcon...|t 3|T...SilverIcon...|t".
        local g, s, c = tonumber(text:match("(%d+)|T[^|]*Gold")), tonumber(text:match("(%d+)|T[^|]*Silver")),
            tonumber(text:match("(%d+)|T[^|]*Copper"))
        if g or s or c then n = (g or 0) * 10000 + (s or 0) * 100 + (c or 0) end
    end
    if n and n >= 0 and n < LIMIT * 100 and n == math.floor(n) then return n end
    return nil
end
P.statistic = statistic
-- Reads the gold now; a rise since the last reading counts as earned.
function P.money(character)
    local value = stats(character)
    local copper = S.number(S.call(GetMoney))
    if not copper or copper < 0 or copper >= LIMIT * 100 or copper ~= math.floor(copper) then return nil end
    local last = S.number(value.gold)
    if last and copper > last then value.gold_earned = (value.gold_earned or 0) + (copper - last) end
    value.gold, value.gold_earned = copper, value.gold_earned or 0
    return copper
end
-- "<monster> dies, you gain <n> experience", built from the game's own text so
-- every client language works; rested and group bonus text may follow.
local killPattern, killFormat
local function killMatcher()
    local fmt = S.string(COMBATLOG_XPGAIN_FIRSTPERSON) or ("%" .. "s dies, you gain %" .. "d experience.")
    if fmt == killFormat then return killPattern end
    killFormat = fmt
    local out, i, named = {}, 1, false
    while i <= #fmt do
        local ch = fmt:sub(i, i)
        if ch == "%" then
            local j = i + 1
            while fmt:sub(j, j):match("[0-9%$]") do j = j + 1 end
            local conversion = fmt:sub(j, j)
            if conversion == "d" then table.insert(out, "%d+"); break end
            table.insert(out, conversion == "%" and "%%" or ".+")
            named = named or conversion ~= "%"
            i = j + 1
        else
            table.insert(out, ch:find("[%^%$%(%)%%%.%[%]%*%+%-%?]") and ("%" .. ch) or ch)
            i = i + 1
        end
    end
    killPattern = named and ("^" .. table.concat(out)) or false
    return killPattern
end
function P.kill(character, message)
    local pattern = killMatcher()
    message = S.string(message)
    if not pattern or not message or not message:find(pattern) then return false end
    local value = stats(character)
    value.kills = (value.kills or 0) + 1
    return true
end
-- At login: the game's lifetime figures, when it has them, plus what is counted afterwards.
function P.initTotals(character)
    local value = stats(character)
    P.money(character)
    local kills, gold = statistic(STAT_KILLS), statistic(STAT_GOLD)
    value.kill_base = kills and kills >= (value.kills or 0) and {lifetime=kills, tracked=value.kills or 0} or nil
    value.gold_base = gold and gold >= (value.gold_earned or 0) and {lifetime=gold, tracked=value.gold_earned or 0} or nil
    S.debug("statistics: kills " .. tostring(kills) .. ", gold acquired " .. tostring(gold)
        .. (GetStatistic and "" or " (no GetStatistic)") .. ", kill text " .. tostring(killMatcher()))
end
function P.totalKills(character)
    local value = stats(character)
    local base, kills = value.kill_base, value.kills or 0
    return base and (base.lifetime + math.max(0, kills - base.tracked)) or kills
end
function P.goldEarned(character)
    local value = stats(character)
    local base, earned = value.gold_base, value.gold_earned or 0
    return base and (base.lifetime + math.max(0, earned - base.tracked)) or earned
end

-- Honorable kills (lifetime, where the game gives them), different dungeons and
-- raids first cleared since installing, and mounts in the collection (where the
-- client has one; counted at most once a minute).
local mountsAt, mountsCount
function P.extras(character)
    local result = {}
    if GetPVPLifetimeStats then
        local ok, kills = pcall(GetPVPLifetimeStats)
        kills = ok and S.number(S.value(kills))
        if kills and kills >= 0 and kills < LIMIT then result.honor_kills = math.floor(kills) end
    end
    local dungeons = character.milestones and character.milestones.automatic_dungeons
    if type(dungeons) == "table" then
        local count = 0
        for _ in pairs(dungeons) do count = count + 1 end
        result.dungeons = count
    end
    -- Counted again after a minute; a client still loading its collection is asked again next time.
    if not mountsAt or time() - mountsAt >= 60 then
        if C_MountJournal and C_MountJournal.GetMountIDs and C_MountJournal.GetMountInfoByID then
            local ids = S.value(S.call(C_MountJournal.GetMountIDs))
            if type(ids) == "table" then
                local count = 0
                for _, raw in ipairs(ids) do
                    local id = S.number(raw)
                    if id then
                        -- (Not "id and pcall(...)": that keeps only pcall's first result.)
                        local ok, _, _, _, _, _, _, _, _, _, _, collected = pcall(C_MountJournal.GetMountInfoByID, id)
                        if ok and S.value(collected) == true then count = count + 1 end
                    end
                end
                mountsAt, mountsCount = time(), count
            end
        end
    end
    result.mounts = mountsCount
    return result
end

-- Clients with statistics (Retail; Forever if its client has them) count deaths
-- from before installation. Statistic 60 is "Total deaths". Classic Era and TBC
-- have no statistics, so their totals stay "since installation".
function P.lifetimeDeaths()
    if not GetStatistic then return nil end
    local raw = S.call(GetStatistic, 60)
    local total = tonumber(S.string(raw) or S.number(raw))
    if total and total >= 0 and total < 2000000000 and total == math.floor(total) then return total end
    return nil
end
-- Called at login: the statistic then plus deaths counted afterwards gives the
-- lifetime total without depending on when the game updates the statistic.
-- A statistic below the deaths already counted is not trusted.
function P.initDeaths(character)
    local value, lifetime = stats(character), P.lifetimeDeaths()
    if lifetime and lifetime >= value.deaths then
        value.death_base = {lifetime=lifetime, tracked=value.deaths}
    else value.death_base = nil end
end
function P.totalDeaths(character)
    local value = stats(character)
    local base = value.death_base
    if not base then return value.deaths end
    return base.lifetime + math.max(0, value.deaths - base.tracked)
end
function P.death(character)
    local value = stats(character)
    if character.death_latched then return false end
    character.death_latched = true
    value.deaths = value.deaths + 1
    return true
end
function P.quest(character, id)
    id = S.number(id)
    if not id or id <= 0 then return false end
    local value = stats(character)
    if value.quest_ids[tostring(id)] then return false end
    value.quest_ids[tostring(id)] = true
    questAt = nil
    return true
end
function P.professionChanges(character, baseline)
    local value, changed = stats(character), {}
    if baseline then value.profession_ready = false end
    local observed = P.professions(true)
    if not observed then return changed end
    local previous = value.profession_titles or {}
    if not value.profession_titles then
        for _, p in ipairs(value.professions or {}) do previous[p.name] = p.max_skill end
    end
    -- Remember professions across unlearning and collapsed skill headers.
    local titles = previous
    for _, p in ipairs(observed) do
        local old = previous[p.name]
        if not baseline and value.profession_ready and (not old or (WoWStatusAdapter.classicProfessionTitles~=false and p.max_skill > old)) then
            p.title = WoWStatusAdapter.classicProfessionTitles~=false and P.professionTitle(p.max_skill) or nil
            p.learned = not old or nil
            table.insert(changed,p)
        end
        titles[p.name] = math.max(old or 0, p.max_skill)
    end
    value.profession_ready = true
    value.professions, value.profession_titles = observed, titles
    return changed
end

function P.professionTitle(maximum)
    local titles = {[75]="Apprentice", [150]="Journeyman", [225]="Expert", [300]="Artisan", [375]="Master"}
    return titles[maximum] or "New profession rank"
end
-- Establish a baseline silently. Never announce old achievements on login or
-- when switching from locally tracked counts to the game's complete history.
function P.questMilestone(character, total, source, baseline)
    local value = stats(character)
    local previous = value.quest_milestone_count
    local changedSource = value.quest_milestone_source ~= source
    value.quest_milestone_source = source
    value.quest_milestone_count = math.max(changedSource and 0 or (previous or 0), total or 0)
    if baseline or changedSource or not previous or not total then return nil end
    if math.floor(total / 100) > math.floor(previous / 100) then return math.floor(total / 100) * 100 end
end

-- Per-character first recorded visits. Seed older observations to avoid upgrade
-- spam, and silently baseline the login zone rather than announcing a reload.
-- Map exploration remembers the areas of each zone a character uncovered, also
-- before the addon was installed. Zones with uncovered areas count as visited,
-- so they are not announced as first visits. Cities and other zones without
-- areas to uncover give no answer and are announced as before.
local function exploredCount(mapID)
    if not C_MapExplorationInfo or not C_MapExplorationInfo.GetExploredMapTextures then return nil end
    local list=S.value(S.call(C_MapExplorationInfo.GetExploredMapTextures,mapID))
    return type(list)=="table" and #list or nil
end
local ZONE_TYPE=3 -- Enum.UIMapType.Zone
function P.exploredZones()
    local names={}
    if not C_Map or not C_Map.GetMapInfo or not C_MapExplorationInfo or not C_MapExplorationInfo.GetExploredMapTextures then
        return names
    end
    local zoneType=S.number(Enum and Enum.UIMapType and Enum.UIMapType.Zone) or ZONE_TYPE
    for id=1,3000 do
        local info=S.value(S.call(C_Map.GetMapInfo,id))
        local name=type(info)=="table" and S.value(info.mapType)==zoneType and S.string(info.name)
        if name and not names[name] then
            local count=exploredCount(id)
            if count and count>0 then names[name]=true end
        end
    end
    return names
end
-- Whether the zone you are in was uncovered before this visit: two or more
-- areas, as arriving uncovers at most the one you enter.
local function exploredBefore(zone)
    if not C_Map or not C_Map.GetBestMapForUnit or not C_Map.GetMapInfo then return false end
    local id=S.number(S.call(C_Map.GetBestMapForUnit,"player"))
    local info=id and S.value(S.call(C_Map.GetMapInfo,id))
    if type(info)~="table" or S.string(info.name)~=zone then return false end
    local count=exploredCount(id)
    return count~=nil and count>=2
end
function P.initZones(character,zone)
    if not character.visited_zones then
        character.visited_zones={}
        for _,event in ipairs(character.history and character.history.events or {}) do
            local known=event.kind=="zone" and S.string(event.data and event.data.zone)
            if known then character.visited_zones[known]=true end
        end
        local previous=S.string(character.snapshot and character.snapshot.zone)
        if previous then character.visited_zones[previous]=true end
    end
    if character.settings.fields.zone and character.settings.collection.zone then
        -- Zones uncovered before installation (or while sharing was off) are not new.
        for name in pairs(P.exploredZones()) do character.visited_zones[name]=true end
        if zone then character.visited_zones[zone]=true end
    end
end
function P.visitZone(character,zone)
    zone=S.string(zone)
    if not zone or not character.settings.enabled or not character.settings.fields.zone
        or not character.settings.collection.zone then return false end
    if not character.visited_zones then P.initZones(character,nil) end
    if character.visited_zones[zone] then return false end
    character.visited_zones[zone]=true
    return not exploredBefore(zone)
end
