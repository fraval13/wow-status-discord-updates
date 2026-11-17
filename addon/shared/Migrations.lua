-- Numbered upgrades of the saved data (#231). Each step runs once: after it
-- succeeds, the version it brings the data to is saved (WoWStatusDB.version for
-- the account, schema_version on each character), so a login never repeats it.
-- Version 1 is the shape every release saved before these steps existed; data
-- without a version, or with a broken one, counts as version 1 and is upgraded,
-- never refused. Data saved by a newer release than this one is left as it is.
--
-- To change the saved shape, append a step with the next number and test it on
-- its own (tests/test_migrations.py). Never renumber or change a released step:
-- some players already ran it. A brand-new account or character starts at
-- version 1 and runs every step, so a step must also suit fresh defaults.
WoWStatusMigrations = {}
local M = WoWStatusMigrations

-- Kinds the addon no longer records or shows; the receiving and history code
-- refuses new ones, so old entries need removing only once.
local RETIRED = {discovery = true, lfg = true}

M.account = {
    {version = 2, name = "drop retired kinds from the activity log", run = function(db)
        local popups = db.popups
        if type(popups) ~= "table" or type(popups.activity) ~= "table" then return end
        local kept = {}
        for _, item in ipairs(popups.activity) do
            if type(item) ~= "table" or not RETIRED[item.kind] then table.insert(kept, item) end
        end
        popups.activity = kept
    end},
}

-- What each character step receives: the character's saved table (its settings
-- already hold defaults() for a new character) and the account table.
M.character = {
    {version = 2, name = "fill switches added after the first saved shape", run = function(character)
        local settings = character.settings
        -- Characters from before the Discord opt-in had only "enrolled".
        if settings.discord_enabled == nil then
            character.discord_enrolled = character.enrolled == true
            settings.discord_enabled = false
        end
        for _, part in ipairs({"fields", "collection", "announcements", "in_game"}) do
            if type(settings[part]) ~= "table" then settings[part] = {} end
        end
        for _, field in ipairs({"deaths", "quests", "gold", "kills", "collection"}) do
            if settings.fields[field] == nil then settings.fields[field] = true end
        end
        for _, kind in ipairs({"quest", "profession", "dungeon", "mount", "reputation", "unlock", "pvp"}) do
            if settings.collection[kind] == nil then settings.collection[kind] = true end
            if settings.announcements[kind] == nil then settings.announcements[kind] = true end
        end
        local inGame = settings.in_game
        if inGame.recap == nil then inGame.recap = false end
        if inGame.loot == nil then inGame.loot = true end
        for _, kind in ipairs({"level", "death", "zone", "quest", "profession", "dungeon", "mount", "reputation", "unlock", "pvp"}) do
            if inGame[kind] == nil then inGame[kind] = true end
        end
    end},
}

local function latest(steps) return steps[#steps] and steps[#steps].version or 1 end
M.ACCOUNT_LATEST, M.CHARACTER_LATEST = latest(M.account), latest(M.character)

local function version(value)
    value = tonumber(value)
    if not value or value ~= math.floor(value) or value < 1 then return 1 end
    return value
end

-- Runs the steps newer than holder[field], saving each version as it is reached.
-- Returns true, or false and the failed step and its error; the failed step and
-- the ones after it run again at the next login.
local function upgrade(steps, holder, field, ...)
    local current = version(holder[field])
    for _, step in ipairs(steps) do
        if step.version > current then
            local ok, problem = pcall(step.run, ...)
            if not ok then return false, step, problem end
            current = step.version
            holder[field] = current
        end
    end
    return true
end

function M.version(value) return version(value) end

function M.upgradeAccount(db)
    return upgrade(M.account, db, "version", db)
end

function M.upgradeCharacter(character, db)
    return upgrade(M.character, character, "schema_version", character, db)
end
