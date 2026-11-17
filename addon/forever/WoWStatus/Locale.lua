-- Optional display language. English is the default and the fallback; every
-- other language is a bank of texts registered from its own file, so adding one
-- is one new file plus one TOC line and no change here (#154).
-- The player chooses in Options or with /wstatus language <code>, and the choice
-- is saved account-wide in WoWStatusDB.language; without a choice the client's
-- own locale picks a bank when one exists. Only what is shown changes: texts
-- sent between players stay in English, so mixed languages keep working.
-- A missing text falls back to English on its own, so a half-finished bank is
-- useful at once. Labels built once need a /reload to change; lists and popups
-- follow immediately.
WoWStatusLocale = {}
local W = WoWStatusLocale
-- code -> {exact = {English text -> translation}, patterns = {{pattern, replacement}, ...}}
W.BANKS = {}
-- code -> the language's name, written in that language.
W.LANGUAGES = {en = "English"}
-- code -> the switch button's label, written in the language it switches to.
W.SWITCH = {en = "Switch to English"}
-- WoW client locales that are not a bank code of their own. Every other locale
-- (deDE, frFR, ruRU, …) is looked up as itself, so a bank named after the
-- client's locale is found without touching this file.
W.CLIENT_LOCALES = {enUS = "en", enGB = "en"}

-- Register a language and return its own add(exact, patterns). The bank code
-- should be the WoW client locale it belongs to (deDE, frFR, …) so the client's
-- own setting finds it; "nn" has no client and is only ever chosen by hand.
function W.language(code, name, switchLabel)
    if type(code) ~= "string" or code == "" or code == "en" then return function() end end
    local bank = W.BANKS[code]
    if not bank then bank = {exact = {}, patterns = {}}; W.BANKS[code] = bank end
    W.LANGUAGES[code] = name or W.LANGUAGES[code] or code
    W.SWITCH[code] = switchLabel or W.SWITCH[code] or ("Switch to " .. W.LANGUAGES[code])
    return function(exact, patterns)
        for k, v in pairs(exact or {}) do bank.exact[k] = v end
        for _, rule in ipairs(patterns or {}) do table.insert(bank.patterns, rule) end
        return bank
    end
end

-- The client's own language, when a bank exists for it; English otherwise.
function W.clientLanguage()
    local ok, locale = pcall(GetLocale)
    if not ok or type(locale) ~= "string" or locale == "" then return "en" end
    local code = W.CLIENT_LOCALES[locale] or locale
    return W.BANKS[code] and code or "en"
end
-- The player's saved choice wins; without one the client decides.
function W.lang()
    local saved = type(WoWStatusDB) == "table" and WoWStatusDB.language
    if saved == "en" then return "en" end
    if type(saved) == "string" and W.BANKS[saved] then return saved end
    return W.clientLanguage()
end
function W.set(lang)
    if lang ~= "en" and not W.BANKS[lang] then return false end
    if type(WoWStatusDB) ~= "table" then return false end
    -- Stored even for English: without it a German client would switch itself back.
    WoWStatusDB.language = lang
    return true
end
-- Every language that can be chosen, English first, then the banks by code.
function W.languages()
    local codes, list = {}, {{code = "en", name = W.LANGUAGES.en}}
    for code in pairs(W.BANKS) do codes[#codes + 1] = code end
    table.sort(codes)
    for _, code in ipairs(codes) do list[#list + 1] = {code = code, name = W.LANGUAGES[code] or code} end
    return list
end
-- The next language in that list, so a two-language install keeps one-click switching.
function W.nextLanguage()
    local list, current = W.languages(), W.lang()
    for i, item in ipairs(list) do
        if item.code == current then return list[i % #list + 1].code end
    end
    return "en"
end

-- Translate a shown text: an exact entry, else the first matching pattern, else
-- the English text itself, so one missing line never blanks a window.
function W.T(text)
    if type(text) ~= "string" or text == "" then return text end
    local bank = W.BANKS[W.lang()]
    if not bank then return text end
    local exact = bank.exact[text]
    if exact then return exact end
    for _, rule in ipairs(bank.patterns) do
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
