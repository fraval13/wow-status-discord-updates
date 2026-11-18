-- Display-only locale registry (#154). Banks register before consumers load.
-- Saved language is account-wide; nil still means English for older accounts.
-- Only a fresh account takes its initial choice from the client. Wire texts
-- remain English. Captions keep their separate English/Nynorsk banks.
WoWStatusLocale = {}
local W = WoWStatusLocale
W.banks, W.LANGUAGES = {}, {}
local clients = {}

-- One new locale file and its TOC entry are enough. A partial bank is valid:
-- untranslated strings fall back to their English source, one string at a time.
function W.register(code, name, clientLocales, exact, patterns, chooseLabel)
    assert(type(code)=="string" and code:match("^[a-z][a-z0-9]*$"),"invalid display locale code")
    assert(type(name)=="string" and name~="" and not W.banks[code],"duplicate or unnamed display locale")
    local bank={exact=exact or {},patterns=patterns or {},chooseLabel=chooseLabel or name}
    W.banks[code],W.LANGUAGES[code]=bank,name
    for _,locale in ipairs(clientLocales or {}) do
        assert(type(locale)=="string" and not clients[locale],"duplicate client locale")
        clients[locale]=code
    end
    return bank
end
W.register("en","English",{"enUS","enGB"},nil,nil,"Switch to English")

function W.clientLanguage()
    local ok,locale=pcall(GetLocale)
    return ok and clients[locale] or "en"
end
function W.lang()
    local value=type(WoWStatusDB)=="table" and WoWStatusDB.language
    return W.banks[value] and value or "en"
end
function W.set(lang)
    if not W.banks[lang] or type(WoWStatusDB)~="table" then return false end
    WoWStatusDB.language=lang~="en" and lang or nil
    return true
end
function W.options()
    local list={}
    for code,name in pairs(W.LANGUAGES) do list[#list+1]={value=code,label=name} end
    table.sort(list,function(a,b)
        if a.value=="en" then return b.value~="en" end
        if b.value=="en" then return false end
        return a.value<b.value
    end)
    return list
end
-- Translate a shown text: an exact entry, else the first matching pattern.
function W.T(text)
    if type(text)~="string" or text=="" then return text end
    local code=W.lang()
    if code=="en" then return text end
    local bank=W.banks[code]
    local exact=bank.exact[text]
    if type(exact)=="string" and exact~="" then return exact end
    for _,rule in ipairs(bank.patterns) do
        if text:find(rule[1]) then
            local result=text:gsub(rule[1],rule[2],1)
            if result~="" then return result end
        end
    end
    return text
end
function W.F(text, ...) return string.format(W.T(text), ...) end
function W.extend(code,exact,patterns)
    local bank=assert(W.banks[code],"unregistered display locale")
    for k,v in pairs(exact or {}) do bank.exact[k]=v end
    for _,rule in ipairs(patterns or {}) do table.insert(bank.patterns,rule) end
end
-- Compatibility for independent Nynorsk copy additions using the older API.
function W.add(exact,patterns) W.extend("nn",exact,patterns) end
