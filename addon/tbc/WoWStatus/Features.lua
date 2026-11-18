-- Discord integration is retained for a future return. Uncomment/change this
-- flag to true to restore its settings page and saved opt-ins. It stays
-- code-only: it is not an experiment and never appears on the Labs page.
WoWStatusFeatures = {discord = false}
local F = WoWStatusFeatures
-- Experiments (#222). A module registers one at load time; it is off for every
-- player until that player switches it on, on the Labs page, for the whole
-- account. Nothing here reaches other players or the saved log.
local list, byId, db = {}, {}, nil
function F.init(database) db = database end
-- The saved toggles, or nil before init: then everything reads as off.
local function saved()
    if type(db) ~= "table" then return nil end
    if type(db.labs) ~= "table" then db.labs = {} end
    return db.labs
end
-- label and description are English keys; Locale.T translates them for display.
function F.register(id, label, description, configure)
    if type(id) ~= "string" or id == "" or byId[id] then return false end
    local item = {id = id, label = label or id, description = description, configure = configure}
    byId[id] = item
    list[#list + 1] = item
    return true
end
function F.experiments() return list end
function F.known(id) return byId[id] ~= nil end
-- Only a saved true means on. Anything else — nil, a string, a number left by a
-- hand-edited or truncated SavedVariables file — reads as off, so a malformed
-- value can never switch an experiment on.
function F.enabled(id)
    if not byId[id] then return false end
    local store = saved()
    return store ~= nil and store[id] == true
end
function F.set(id, value)
    local store = saved()
    if not byId[id] or not store then return false end
    -- nil rather than false: an account that never turned anything on keeps an
    -- empty table, and the file says nothing about experiments at all.
    store[id] = value == true or nil
    return true
end
function F.anyEnabled()
    for _, item in ipairs(list) do if F.enabled(item.id) then return true end end
    return false
end
function F.allOff()
    local store = saved()
    if not store then return false end
    for id in pairs(byId) do store[id] = nil end
    return true
end
