-- Retail achievements (#165): a fixed whitelist of the achievements players
-- care about. Only the achievement ID travels between players; every client
-- looks the name and icon up in its own game data, so a sent name or icon is
-- never shown. Inert on editions whose adapter does not set achievements=true.
WoWStatusAchievements = {}
local AC, S = WoWStatusAchievements, WoWStatusSafe
-- Announcements this character may send per login session, and updates one
-- friend may show here per session: a burst (a meta achievement that completes
-- several others at once) cannot bury the group.
AC.SESSION_CAP, AC.RECEIVE_CAP = 5, 10
local NAME_LIMIT = 100
-- Retail achievement IDs. Anything not listed is never announced, and an ID the
-- receiver's client cannot name is dropped there. Review with each expansion.
AC.LIST = {}
local GROUPS = {
    -- Level 10, 20, ..., 80, 85, 90 (the same IDs Journal backfills dates from).
    level = {6, 7, 8, 9, 10, 11, 12, 13, 4826, 6193},
    -- Explore Eastern Kingdoms, Kalimdor, Outland, Northrend; World Explorer.
    exploration = {42, 43, 44, 45, 46},
    -- Somebody Likes Me, then 5 to 40 exalted reputations.
    reputation = {522, 523, 524, 521, 520, 519, 518, 1014, 1015},
    -- 10, 25 and 50 mounts; 100 mounts (Alliance and Horde).
    mount = {2141, 2142, 2143, 2536, 2537},
    -- Professional Journeyman to Grand Master.
    profession = {116, 731, 732, 733, 734},
    -- Classic, Outland and Northrend Dungeonmaster.
    dungeon = {1283, 1284, 1288},
}
for group, ids in pairs(GROUPS) do
    for _, id in ipairs(ids) do AC.LIST[id] = group end
end
local sent, received = 0, {}

function AC.available()
    return WoWStatusAdapter.achievements == true and type(GetAchievementInfo) == "function"
end
-- A whitelisted ID from a number or a packet's digits; nil for anything else.
function AC.id(value)
    if type(value) == "string" then
        if not value:match("^[1-9]%d?%d?%d?%d?%d?$") then return nil end
        value = tonumber(value)
    end
    value = S.number(value)
    if not value or value ~= math.floor(value) or not AC.LIST[value] then return nil end
    return value
end
-- Name and icon from this client's own game data, or nil.
function AC.info(id)
    id = AC.id(id)
    if not id or not AC.available() then return nil end
    local ok, _, name, _, _, _, _, _, _, _, icon = pcall(GetAchievementInfo, id)
    name = ok and S.string(name)
    if not name or #name > NAME_LIMIT or name:find(S.CONTROL_OR_PIPE) then return nil end
    name = S.trim(name)
    if name == "" then return nil end
    icon = S.value(icon)
    if not ((type(icon) == "number" and icon > 0) or (type(icon) == "string" and icon ~= "" and not icon:find(S.CONTROL_OR_PIPE))) then
        icon = nil
    end
    return name, icon
end
-- The shown text for an ID ("Earned achievement: Explore Kalimdor"), or nil.
function AC.text(id)
    local name = AC.info(id)
    return name and ("Earned achievement: " .. name) or nil
end
function AC.icon(id)
    local _, icon = AC.info(id)
    return icon
end
-- True while this friend may still show an achievement this session; counts it.
function AC.admit(key)
    if type(key) ~= "string" then return false end
    if (received[key] or 0) >= AC.RECEIVE_CAP then return false end
    received[key] = (received[key] or 0) + 1
    return true
end

local character, emit
function AC.init(current, callback)
    character, emit, sent = current, callback, 0
end
-- ACHIEVEMENT_EARNED: achievementID, alreadyEarned (earned before by another
-- character of this account). Only a first earn on the account is shared.
function AC.earned(rawID, alreadyEarned)
    if not character or not emit or not AC.available() then return nil end
    if S.value(alreadyEarned) == true or sent >= AC.SESSION_CAP then return nil end
    local id = AC.id(rawID)
    if not id or not AC.info(id) then return nil end
    local event = emit("achievement", {achievement_id=id})
    if event then sent = sent + 1 end
    return event
end

local frame = CreateFrame("Frame")
if AC.available() then
    if not C_EventUtils or not C_EventUtils.IsEventValid or S.call(C_EventUtils.IsEventValid, "ACHIEVEMENT_EARNED") then
        pcall(frame.RegisterEvent, frame, "ACHIEVEMENT_EARNED")
    end
end
frame:SetScript("OnEvent", function(_, _, ...) AC.earned(...) end)
