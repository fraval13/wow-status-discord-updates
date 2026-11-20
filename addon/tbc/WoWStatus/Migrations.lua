-- Numbered upgrades of the saved data (#231). Each step runs once: after it
-- succeeds, the version it brings the data to is saved as schema_version (on
-- WoWStatusDB for the account, on each character), so a login never repeats it.
-- Version 1 is the shape every release saved before these steps existed; data
-- without a schema_version, or with a broken one, counts as version 1 and is
-- upgraded, never refused. Data saved by a newer release is left as it is.
-- WoWStatusDB.version stays 1: earlier releases and the companion refuse any
-- other value, so a player who goes back to an older release keeps working.
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
    {version = 3, name = "start group-name listing confirmations", run = function(db)
        -- Existing listings keep their state; none is treated as UI consent.
        if type(db.listing_confirmed) ~= "table" then db.listing_confirmed = {} end
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
        -- Filters out of range (a hand edit) are stored clamped, so the companion,
        -- which checks the saved value, reads this character again once it logs in.
        for _, key in ipairs({"level_interval", "loot_quality"}) do
            if settings[key] ~= nil and not WoWStatusSettings.valid(key, settings[key]) then
                WoWStatusSettings.set(key, WoWStatusSettings.get(key, character), character)
                -- As /wstatus quality does, so sharing and receiving filter alike.
                local quality = settings.loot_quality
                if key == "loot_quality" then settings.loot_rarities = {rare = quality <= 3, epic = quality <= 4, legendary = quality <= 5} end
            end
        end
    end},
    -- Retail achievements (#165) start off for new and upgraded characters alike,
    -- so nobody's group is suddenly flooded; ticking the option turns them on.
    -- Other editions never get the setting.
    {version = 3, name = "achievements start off on Retail", run = function(character)
        if not WoWStatusAdapter.achievements then return end
        local settings = character.settings
        for _, part in ipairs({"collection", "announcements", "in_game"}) do
            if type(settings[part]) ~= "table" then settings[part] = {} end
            if settings[part].achievement == nil then settings[part].achievement = false end
        end
    end},
    {version = 4, name = "normalize the manual Hardcore flag", run = function(character)
        local settings = character.settings
        if settings.manual_hardcore ~= nil then
            local Z = WoWStatusSettings
            Z.set("manual_hardcore", Z.get("manual_hardcore", character), character)
        end
    end},
    {version = 5, name = "normalize the personal level countdown", run = function(character)
        if character.personal_goal_level ~= nil then
            local Z = WoWStatusSettings
            Z.set("personal_goal_level", Z.get("personal_goal_level", character), character)
        end
    end},
}

local function latest(steps) return steps[#steps] and steps[#steps].version or 1 end
M.ACCOUNT_LATEST, M.CHARACTER_LATEST = latest(M.account), latest(M.character)

local function version(value)
    value = WoWStatusSafe.number(tonumber(value))
    if not value or value ~= math.floor(value) or value < 1 then return 1 end
    return value
end

-- Runs the steps newer than holder[field], saving each version as it is reached.
-- Returns true, or false and the failed step and its error; the failed step and
-- the ones after it run again at the next login.
local function upgrade(steps, holder, field, ...)
    local current = version(holder[field])
    -- A broken or text version is saved as the number it counts as.
    if holder[field] ~= current then holder[field] = current end
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

function M.upgradeAccount(db)
    return upgrade(M.account, db, "schema_version", db)
end

function M.upgradeCharacter(character, db)
    return upgrade(M.character, character, "schema_version", character, db)
end
