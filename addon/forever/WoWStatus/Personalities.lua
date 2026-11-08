-- Caption personalities: optional voices for the flavour line under each
-- notification. "classic" is the original bank in Flavour.lua/FlavourNN.lua;
-- every other personality is a FlavourXxx.lua file, generated from
-- docs/caption-personalities/<id>/*.json by scripts/build_personalities.py.
-- "random" (the default) is no bank of its own: each new caption picks one of
-- the other voices, Classic included, from the event's identity.
-- The choice is account-wide (WoWStatusDB.personality) and presentation only:
-- nothing about it is sent to other players, so friends may each pick their own.
-- Reactions (the GZ!/F/Congrats! whispers) have their own setting, the reaction
-- voice (WoWStatusDB.reaction_voice). They are sent to a friend in your name, so
-- the default is the gentle Wholesome voice (Classic when it is not loaded).
WoWStatusPersonalities = {}
local P = WoWStatusPersonalities
P.DEFAULT = "random"
P.order = {"random", "classic"}
P.defs = {random = {name = "Random", nn_name = "Tilfeldig"}, classic = {name = "Classic", nn_name = "Klassisk"}}

-- A FlavourXxx.lua file adds its banks: en/nn = {kind = {lines…}}, nn line i
-- translating en line i. Death lines keep their "[CLASS] " tags.
function P.register(id, def)
    if type(id) ~= "string" or type(def) ~= "table" or P.defs[id] then return end
    if type(def.en) ~= "table" then return end
    P.defs[id] = def
    table.insert(P.order, id)
end

function P.valid(id)
    return type(id) == "string" and P.defs[id] ~= nil
end

function P.current()
    local value = type(WoWStatusDB) == "table" and WoWStatusDB.personality
    return P.valid(value) and value or P.DEFAULT
end

function P.set(id)
    if not P.valid(id) or type(WoWStatusDB) ~= "table" then return false end
    WoWStatusDB.personality = id ~= P.DEFAULT and id or nil
    return true
end

function P.next()
    local current, index = P.current(), 1
    for i, id in ipairs(P.order) do if id == current then index = i end end
    local id = P.order[index % #P.order + 1]
    P.set(id)
    return id
end

-- The personality's display name in the chosen language.
function P.name(id)
    local def = P.defs[P.valid(id) and id or P.current()]
    local nn = WoWStatusLocale and WoWStatusLocale.lang() == "nn"
    return nn and def.nn_name or def.name
end

-- Accepts an id or a display name in either language, any case and spacing.
function P.find(text)
    if type(text) ~= "string" then return nil end
    local wanted = text:lower():gsub("[ \t\n\v\f\r%-_]", "")
    for _, id in ipairs(P.order) do
        local def = P.defs[id]
        for _, candidate in ipairs({id, def.name, def.nn_name}) do
            if type(candidate) == "string" and candidate:lower():gsub("[ \t\n\v\f\r%-_]", "") == wanted then return id end
        end
    end
end

function P.names()
    local list = {}
    for _, id in ipairs(P.order) do table.insert(list, P.name(id)) end
    return table.concat(list, ", ")
end

-- English and Nynorsk banks for one personality (nil for classic, whose banks
-- Flavour.lua owns, and for random, which has none).
function P.banks(id)
    local def = P.defs[id]
    if not def or not def.en then return nil end
    return def.en, def.nn
end

-- The voices "random" draws from: every personality with captions, Classic included.
function P.voices()
    local list = {}
    for _, id in ipairs(P.order) do
        if id ~= "random" then table.insert(list, id) end
    end
    return list
end

function P.label()
    local T = WoWStatusLocale and WoWStatusLocale.T or function(text) return text end
    return T("Caption personality:") .. " " .. P.name()
end

-- Reaction voice -------------------------------------------------------------

-- English and Nynorsk reaction banks for one personality: {gz = {lines…}, …}.
function P.reactionBanks(id)
    local def = P.defs[id]
    local banks = def and def.reactions
    if type(banks) ~= "table" or type(banks.en) ~= "table" then return nil end
    return banks.en, banks.nn
end

-- Classic, Random and every personality with reaction lines, in menu order.
function P.reactionVoices()
    local list = {}
    for _, id in ipairs(P.order) do
        if id == "classic" or id == "random" or P.reactionBanks(id) then table.insert(list, id) end
    end
    return list
end

local function reactionValid(id)
    for _, voice in ipairs(P.reactionVoices()) do if voice == id then return true end end
    return false
end

P.REACTION_DEFAULT = "wholesome"
local function reactionDefault()
    return reactionValid(P.REACTION_DEFAULT) and P.REACTION_DEFAULT or "classic"
end

function P.reactionVoice()
    local value = type(WoWStatusDB) == "table" and WoWStatusDB.reaction_voice
    return reactionValid(value) and value or reactionDefault()
end

function P.setReaction(id)
    if not reactionValid(id) or type(WoWStatusDB) ~= "table" then return false end
    WoWStatusDB.reaction_voice = id ~= reactionDefault() and id or nil
    return true
end

function P.nextReaction()
    local list, current, index = P.reactionVoices(), P.reactionVoice(), 1
    for i, id in ipairs(list) do if id == current then index = i end end
    local id = list[index % #list + 1]
    P.setReaction(id)
    return id
end

-- Accepts an id or a name in either language, like P.find, among reaction voices.
function P.findReaction(text)
    local id = P.find(text)
    return id and reactionValid(id) and id or nil
end

function P.reactionNames()
    local list = {}
    for _, id in ipairs(P.reactionVoices()) do table.insert(list, P.name(id)) end
    return table.concat(list, ", ")
end

function P.reactionLabel()
    local T = WoWStatusLocale and WoWStatusLocale.T or function(text) return text end
    return T("Reaction voice:") .. " " .. P.name(P.reactionVoice())
end

-- Fill a {level} or {zone} slot without pattern magic in either string.
local function fill(line, value)
    for _, slot in ipairs({"{level}", "{zone}"}) do
        local at = line:find(slot, 1, true)
        if at then return line:sub(1, at - 1) .. tostring(value or "") .. line:sub(at + #slot) end
    end
    return line
end

-- A whisper in the chosen reaction voice for a reaction key (gz, f, enjoy,
-- congrats_mount…), in the chosen language; nil means the Classic text.
-- Random picks Classic or one of the voices for each reaction.
function P.reactionLine(key, value)
    local voice = P.reactionVoice()
    if voice == "random" then
        local list = {}
        for _, id in ipairs(P.reactionVoices()) do if id ~= "random" then table.insert(list, id) end end
        voice = list[math.random(#list)]
    end
    if voice == "classic" then return nil end
    local en, nn = P.reactionBanks(voice)
    if not en then return nil end
    local useNN = WoWStatusLocale and WoWStatusLocale.lang() == "nn"
    local pool = (useNN and nn and nn[key]) or en[key]
    if type(pool) ~= "table" or #pool == 0 then return nil end
    -- Nynorsk lines with a recorded voice (Forever) are favoured, so friends hear them.
    local V = WoWStatusVoices
    local index = (pool == (nn and nn[key]) and V and V.available()) and V.pick(voice, key, #pool) or math.random(#pool)
    return fill(pool[index], value)
end

-- A received whisper that is one of the voices' reaction lines, in either
-- language: its key (gz, enjoy, congrats_mount…) and the filled-in level or zone.
local exact, patterns
function P.matchReaction(text)
    if type(text) ~= "string" then return nil end
    if not exact then
        exact, patterns = {}, {}
        for _, id in ipairs(P.order) do
            local en, nn = P.reactionBanks(id)
            for _, set in ipairs({en or {}, nn or {}}) do
                for key, lines in pairs(set) do
                    for _, line in ipairs(lines) do
                        local slot = line:find("{level}", 1, true) and "{level}" or (line:find("{zone}", 1, true) and "{zone}")
                        if slot then
                            local escaped = line:gsub("[%^%$%(%)%%%.%[%]%*%+%-%?]", "%%%0")
                            local at = escaped:find(slot, 1, true)
                            local capture = slot == "{level}" and "([0-9]+)" or "(.+)"
                            table.insert(patterns, {"^" .. escaped:sub(1, at - 1) .. capture .. escaped:sub(at + #slot) .. "$", key, #line})
                        elseif not exact[line] then
                            exact[line] = key
                        end
                    end
                end
            end
        end
    end
    if exact[text] then return exact[text] end
    if not patterns.sorted then
        -- Longer lines first: "Have fun in {zone}! …" before a shorter "{zone}! …".
        table.sort(patterns, function(a, b) return a[3] > b[3] end)
        patterns.sorted = true
    end
    for _, rule in ipairs(patterns) do
        local value = text:match(rule[1])
        if value then return rule[2], value end
    end
end
