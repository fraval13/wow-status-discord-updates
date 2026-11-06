-- Caption personalities: optional voices for the flavour line under each
-- notification. "classic" is the original bank in Flavour.lua/FlavourNN.lua;
-- every other personality is a FlavourXxx.lua file, generated from
-- docs/caption-personalities/<id>/*.json by scripts/build_personalities.py.
-- The choice is account-wide (WoWStatusDB.personality) and presentation only:
-- nothing about it is sent to other players, so friends may each pick their own.
WoWStatusPersonalities = {}
local P = WoWStatusPersonalities
P.order = {"classic"}
P.defs = {classic = {name = "Classic", nn_name = "Klassisk"}}

-- A FlavourXxx.lua file adds its banks: en/nn = {kind = {lines…}}, nn line i
-- translating en line i. Death lines keep their "[CLASS] " tags.
function P.register(id, def)
    if type(id) ~= "string" or id == "classic" or type(def) ~= "table" or P.defs[id] then return end
    if type(def.en) ~= "table" then return end
    P.defs[id] = def
    table.insert(P.order, id)
end

function P.valid(id)
    return type(id) == "string" and P.defs[id] ~= nil
end

function P.current()
    local value = type(WoWStatusDB) == "table" and WoWStatusDB.personality
    return P.valid(value) and value or "classic"
end

function P.set(id)
    if not P.valid(id) or type(WoWStatusDB) ~= "table" then return false end
    WoWStatusDB.personality = id ~= "classic" and id or nil
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

-- English and Nynorsk banks for one personality (nil for classic: Flavour.lua owns those).
function P.banks(id)
    local def = id ~= "classic" and P.defs[id]
    if not def then return nil end
    return def.en, def.nn
end

function P.label()
    local T = WoWStatusLocale and WoWStatusLocale.T or function(text) return text end
    return T("Caption personality:") .. " " .. P.name()
end
