-- Public-value boundary: never stringify, compare or serialize a secret game value.
WoWStatusSafe = {}
local S = WoWStatusSafe
-- Locale-independent byte classes. Never use Lua's built-in control or space
-- classes, or string.lower, on player text: they follow the C library's locale,
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
