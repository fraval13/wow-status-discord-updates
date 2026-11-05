-- Optional display language: English (default) or Nynorsk. WoW has no Norwegian
-- client, so the player chooses it (Options, or /wstatus language nn|en); it is
-- saved account-wide in WoWStatusDB.language. Only what is shown changes: texts
-- sent between players stay in English, so mixed languages keep working.
-- Labels built once need a /reload to change; lists and popups follow at once.
WoWStatusLocale = {}
local W = WoWStatusLocale
local NN = {}       -- exact English text -> Nynorsk
local PATTERNS = {} -- {Lua pattern, replacement}, tried in order
W.NN, W.PATTERNS = NN, PATTERNS
W.LANGUAGES = {en="English", nn="Nynorsk"}

function W.lang()
    local value = type(WoWStatusDB) == "table" and WoWStatusDB.language
    return value == "nn" and "nn" or "en"
end
function W.set(lang)
    if not W.LANGUAGES[lang] or type(WoWStatusDB) ~= "table" then return false end
    WoWStatusDB.language = lang ~= "en" and lang or nil
    return true
end

-- Translate a shown text: an exact entry, else the first matching pattern.
function W.T(text)
    if W.lang() ~= "nn" or type(text) ~= "string" or text == "" then return text end
    local exact = NN[text]
    if exact then return exact end
    for _, rule in ipairs(PATTERNS) do
        if text:find(rule[1]) then
            local result = text:gsub(rule[1], rule[2], 1)
            return result
        end
    end
    return text
end
-- Translate, then fill in values like string.format.
function W.F(text, ...)
    return string.format(W.T(text), ...)
end

-- Add translations: an exact table and a list of {pattern, replacement}.
function W.add(exact, patterns)
    for k, v in pairs(exact or {}) do NN[k] = v end
    for _, rule in ipairs(patterns or {}) do table.insert(PATTERNS, rule) end
end
