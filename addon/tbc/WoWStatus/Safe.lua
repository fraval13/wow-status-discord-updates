-- Public-value boundary: never stringify, compare or serialize a secret game value.
WoWStatusSafe = {}
local S = WoWStatusSafe
-- Locale-independent byte classes. Never use Lua's built-in control or space
-- classes on player text, nor string.lower on keys that peers compare or that
-- travel in packets: they follow the C library's locale,
-- which in some locales (macOS UTF-8) treats bytes 0x80-0xFF as Latin-1. That
-- matches the second byte of AE, O-slash and A-ring (C3 86/98/85) as a control
-- byte, 0x85 as a space, and lowercases the lead byte C3 to E3.
S.CONTROL = "[%z\1-\31\127]"
S.CONTROL_OR_PIPE = "[%z\1-\31\127|]"
S.SPACE = "[ \t\n\v\f\r]"
S.NONSPACE = "[^ \t\n\v\f\r]"
local TRIM = "^" .. S.SPACE .. "*(.-)" .. S.SPACE .. "*$"
S.SPLIT_WORD = "^(" .. S.NONSPACE .. "*)" .. S.SPACE .. "*(.-)$"
local LOWER = {}
for byte = 65, 90 do LOWER[string.char(byte)] = string.char(byte + 32) end
function S.trim(text)
    return text:match(TRIM)
end
function S.stripSpace(text)
    return (text:gsub(S.SPACE, ""))
end
function S.lowerASCII(text)
    return (text:gsub("[A-Z]", LOWER))
end
local COLOUR = "|c" .. ("[0-9a-fA-F]"):rep(8)
-- Remove WoW UI escapes (colour, named colour, link, texture, atlas, protected
-- text) but keep link text. "||" is a literal pipe and is kept as one "|".
function S.stripEscapes(text)
    text = text:gsub("||", "\1"):gsub(COLOUR, ""):gsub("|cn[^:|]*:", ""):gsub("|r", "")
    text = text:gsub("|H.-|h(.-)|h", "%1"):gsub("|T.-|t", ""):gsub("|A.-|a", ""):gsub("|K.-|k", "")
    return (text:gsub("\1", "|"))
end
function S.value(value)
    if issecretvalue and issecretvalue(value) then return nil end
    return value
end
function S.call(fn, ...)
    if type(fn) ~= "function" then return nil end
    local ok, a, b, c, d = pcall(fn, ...)
    if not ok then return nil end
    return S.value(a), S.value(b), S.value(c), S.value(d)
end
function S.string(value)
    value = S.value(value)
    if type(value) ~= "string" or value == "" then return nil end
    return value
end
function S.number(value)
    value = S.value(value)
    if type(value) ~= "number" or value ~= value or value == math.huge or value == -math.huge then return nil end
    return value
end
function S.stringCall(fn, ...)
    return S.string(S.call(fn, ...))
end
-- Realm time (issue #7). time() reads this PC's clock, which can be minutes
-- off; GetServerTime() is the realm's clock, the same on every member's PC.
-- Stamp everything stored or shared with it, and compare those stamps with it.
-- time() stays for short local intervals. Falls back to time() without the API.
function S.realmTime()
    local realm = S.number(S.call(GetServerTime))
    return realm and realm > 0 and math.floor(realm) or nil
end
function S.now()
    return S.realmTime() or time()
end
-- Checks a peer's timestamp against [now - past, now + ahead]. Updated clients
-- stamp realm time; older ones stamp their PC clock, so a stamp that fits this
-- PC's clock still counts (it did before). Returns nil when the stamp fits,
-- otherwise "stale" or "future" as judged by realm time.
function S.outside(at, past, ahead)
    local realm, pc = S.now(), time()
    if (at >= realm - past and at <= realm + ahead) or (at >= pc - past and at <= pc + ahead) then return nil end
    return at < realm - past and "stale" or "future"
end
