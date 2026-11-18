-- The option schema (#231): each option states its type, default and range once,
-- and WoWStatusSettings.get/set keep the saved value inside them. A missing value,
-- one of the wrong type or one out of range reads as the default (or, for an
-- option that clamps, as the nearest bound), so a hand-edited or old saved file
-- never reaches the code that uses it. New options declare themselves here.
-- (Not named Settings: that is the game's own options API on newer clients.)
WoWStatusSettings = {}
local Z = WoWStatusSettings

-- key: the name callers use. scope: "account" (path below WoWStatusDB) or
-- "character" (path below a character's saved table). type: "boolean" or
-- "integer". min/max: the range; also: values allowed outside it (the popup
-- duration's 0, "until dismissed"). round: a fraction rounds to the nearest whole
-- number instead of being refused. clamp: out of range becomes the nearest bound;
-- without it, get falls back to the default and set refuses the value. sparse:
-- the default is not stored, so a later change of default reaches everyone.
Z.schema = {
    -- How long a notification stays (#159), in seconds; 0 keeps it until dismissed.
    {key = "popup_duration", scope = "account", path = {"popups", "popup_duration"},
     type = "integer", default = 6, min = 3, max = 20, also = {0}, round = true, sparse = true},
    {key = "big_banners", scope = "account", path = {"popups", "big_banners"}, type = "boolean", default = true},
    -- Reduce motion (#184): notifications appear and go without sliding, fading or pulsing.
    {key = "reduce_motion", scope = "account", path = {"popups", "reduce_motion"},
     type = "boolean", default = false, sparse = true},
    -- Quiet hours (#180): minutes after midnight on the local clock.
    {key = "quiet_hours_enabled", scope = "account", path = {"popups", "quiet_hours", "enabled"},
     type = "boolean", default = false},
    {key = "quiet_hours_start", scope = "account", path = {"popups", "quiet_hours", "start"},
     type = "integer", default = 22 * 60, min = 0, max = 24 * 60 - 1},
    {key = "quiet_hours_stop", scope = "account", path = {"popups", "quiet_hours", "stop"},
     type = "integer", default = 7 * 60, min = 0, max = 24 * 60 - 1},
    -- Deathless streak milestones (#164): off unless the player turns them on.
    {key = "streak_milestones", scope = "account", path = {"streaks", "milestones"},
     type = "boolean", default = false, sparse = true},
    -- Character filters (/wstatus interval, /wstatus quality).
    {key = "level_interval", scope = "character", path = {"settings", "level_interval"},
     type = "integer", default = 10, min = 1, max = 100, clamp = true},
    {key = "loot_quality", scope = "character", path = {"settings", "loot_quality"},
     type = "integer", default = 3, min = 0, max = 5, clamp = true},
}

local entries = {}
for _, entry in ipairs(Z.schema) do entries[entry.key] = entry end

function Z.entry(key)
    local entry = entries[key]
    if not entry then error("Unknown WoW Status option: " .. tostring(key), 2) end
    return entry
end
function Z.default(key) return Z.entry(key).default end

-- The value as the option allows it and whether it was already exact, or nil for
-- a value of the wrong kind. Text that reads as a number counts as that number.
local function normalize(entry, value)
    if entry.type == "boolean" then
        if type(value) == "boolean" then return value, true end
        return nil
    end
    if type(value) == "string" then value = tonumber(value) end
    -- NaN and the infinities are numbers too, but never valid.
    value = WoWStatusSafe.number(value)
    if not value then return nil end
    if entry.also then
        for _, allowed in ipairs(entry.also) do
            if value == allowed then return value, true end
        end
    end
    if value ~= math.floor(value) then
        if not entry.round then return nil end
        value = math.floor(value + .5)
    end
    if (entry.min and value < entry.min) or (entry.max and value > entry.max) then
        if not entry.clamp then return nil end
        return math.max(entry.min or value, math.min(entry.max or value, value)), false
    end
    return value, true
end

-- Whether value fits the option exactly, without clamping.
function Z.valid(key, value)
    local _, exact = normalize(Z.entry(key), value)
    return exact == true
end

-- owner: the table the option's path starts from (WoWStatusDB for an account
-- option, the character for a character option). Without one, the default.
function Z.get(key, owner)
    local entry = Z.entry(key)
    local value = owner
    for _, part in ipairs(entry.path) do
        if type(value) ~= "table" then value = nil; break end
        value = value[part]
    end
    value = normalize(entry, value)
    if value == nil then return entry.default end
    return value
end

-- Stores value (clamped, for an option that clamps) and returns true, or returns
-- false and leaves the saved value as it was.
function Z.set(key, value, owner)
    local entry = Z.entry(key)
    value = normalize(entry, value)
    if value == nil or type(owner) ~= "table" then return false end
    local parent = owner
    for i = 1, #entry.path - 1 do
        local part = entry.path[i]
        if type(parent[part]) ~= "table" then parent[part] = {} end
        parent = parent[part]
    end
    if entry.sparse and value == entry.default then value = nil end
    parent[entry.path[#entry.path]] = value
    return true
end
