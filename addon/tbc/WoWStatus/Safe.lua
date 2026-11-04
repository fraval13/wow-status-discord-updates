-- Public-value boundary: never stringify, compare or serialize a secret game value.
WoWStatusSafe = {}
local S = WoWStatusSafe
-- Locale-independent control-byte classes. Never use Lua's built-in control class:
-- it follows the C library's iscntrl, which in some locales (macOS UTF-8) also
-- matches bytes 0x80-0x9F, the second byte of AE, O-slash and A-ring (C3 86/98/85).
S.CONTROL = "[%z\1-\31\127]"
S.CONTROL_OR_PIPE = "[%z\1-\31\127|]"
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
