-- Public character observations. Missing APIs stay unavailable, never invented.
WoWStatusProgress = {}
local P, S = WoWStatusProgress, WoWStatusSafe
local questReady, questRequested = false, false
local professionAt, professionCache, questAt
local knownProfessions = {
    alchemy={2259,171,"Alchemy"}, blacksmithing={2018,164,"Blacksmithing"},
    enchanting={7411,333,"Enchanting"}, engineering={4036,202,"Engineering"},
    herbalism={2366,182,"Herbalism"}, leatherworking={2108,165,"Leatherworking"},
    mining={2575,186,"Mining"}, skinning={8613,393,"Skinning"}, tailoring={3908,197,"Tailoring"},
    cooking={2550,185,"Cooking"}, first_aid={3273,129,"First Aid"}, fishing={7620,356,"Fishing"},
}
local function stats(character)
    if not character.progress then
        local started = tonumber((character.epoch or ""):match("^(%d+)")) or time()
        if started < 1 or started > time() then started = time() end
        local deaths = 0
        for _, event in ipairs(character.history and character.history.events or {}) do
            if event.kind == "death" then deaths = deaths + 1 end
        end
        character.progress = {started_at=started, deaths=deaths, quest_ids={}}
    end
    local value = character.progress
    value.started_at, value.deaths, value.quest_ids = value.started_at or time(), value.deaths or 0, value.quest_ids or {}
    return value
end
local function readProfessions()
    local result, names, ids = {}, {}, {}
    for key, definition in pairs(knownProfessions) do
        local name = S.stringCall(GetSpellInfo, definition[1])
        if not name and C_Spell and C_Spell.GetSpellInfo then
            local info = S.value(S.call(C_Spell.GetSpellInfo, definition[1]))
            if type(info) == "table" then name = S.string(info.name) end
        end
        names[name or definition[3]], ids[definition[2]] = key, key
    end
    if GetProfessions and GetProfessionInfo then
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
    elseif GetNumSkillLines and GetSkillLineInfo then
        local count = S.number(S.call(GetNumSkillLines))
        if not count then return nil end
        local collapsed = false
        for index = 1, math.min(count, 512) do
            local ok, name, header, expanded, rank, _, _, maximum = pcall(GetSkillLineInfo, index)
            name, rank, maximum = S.string(name), S.number(rank), S.number(maximum)
            header, expanded = S.value(header), S.value(expanded)
            if ok and header and not expanded then collapsed = true end
            if ok and name and not header and names[name] and rank and maximum and maximum > 1 then
                table.insert(result, {name=name, skill=rank, max_skill=maximum, key=names[name], source="game_api"})
            end
        end
        if #result == 0 and collapsed then return nil end
    else return nil end
    table.sort(result, function(a,b) return a.name < b.name end)
    return result
end
function P.professions(force)
    if not force and professionAt and time() - professionAt < 5 then return professionCache end
    professionCache, professionAt = readProfessions(), time()
    return professionCache
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
    -- Keep high-water marks even when a skill header is collapsed or a trade
    -- is unlearned. Reopening a header/relearning must not look like a new trade.
    local titles = previous
    for _, p in ipairs(observed) do
        local old = previous[p.name]
        if not baseline and value.profession_ready and (not old or p.max_skill > old) then
            p.title = P.professionTitle(p.max_skill)
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
    local titles = {[75]="Apprentice", [150]="Journeyman", [225]="Expert", [300]="Artisan"}
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
    if zone and character.settings.fields.zone and character.settings.collection.zone then character.visited_zones[zone]=true end
end
function P.visitZone(character,zone)
    zone=S.string(zone)
    if not zone or not character.settings.enabled or not character.settings.fields.zone
        or not character.settings.collection.zone then return false end
    if not character.visited_zones then P.initZones(character,nil) end
    if character.visited_zones[zone] then return false end
    character.visited_zones[zone]=true
    return true
end
