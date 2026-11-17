-- Retail achievements (#165): a fixed whitelist of the achievements players
-- care about. Only the achievement ID travels between players; every client
-- looks the name and icon up in its own game data, so a sent name or icon is
-- never shown. Inert on editions whose adapter does not set achievements=true.
WoWStatusAchievements = {}
local AC, S = WoWStatusAchievements, WoWStatusSafe
-- Live announcements this character may send per session, and achievements
-- one friend may show here per session: a burst (a meta achievement that
-- completes several others at once) cannot bury the group. Past the cap an
-- achievement is still recorded and reaches friends' logs quietly. A session
-- is the UI's: /reload starts a new one, as it does for all addon state.
AC.SESSION_CAP, AC.RECEIVE_CAP = 5, 10
local NAME_LIMIT = 100
-- Retail achievement IDs. Anything not listed is never announced, and an ID the
-- receiver's client cannot name is dropped there. Review with each expansion.
AC.LIST = {}
local GROUPS = {
    -- No level achievements: a level-up is already announced as one.
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
local sent, received, known = 0, {}, {}

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
-- Name and icon from this client's own game data, or nil. A found name is
-- remembered for the session: log rows ask on every render.
function AC.info(id)
    id = AC.id(id)
    if not id or not AC.available() then return nil end
    local cached = known[id]
    if cached then return cached.name, cached.icon end
    local ok, _, name, _, _, _, _, _, _, _, icon = pcall(GetAchievementInfo, id)
    name = ok and S.string(name)
    if not name or #name > NAME_LIMIT or name:find(S.CONTROL_OR_PIPE) then return nil end
    name = S.trim(name)
    if name == "" then return nil end
    known[id] = {name=name, icon=S.texture(icon)}
    return name, known[id].icon
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
-- True while this friend may still show an achievement this session. Counts
-- each update (nonce) once, so a copy from a second group or a resend is free.
function AC.admit(key, nonce)
    if type(key) ~= "string" or type(nonce) ~= "string" then return false end
    local friend = received[key] or {count=0, nonces={}}
    received[key] = friend
    if friend.nonces[nonce] then return true end
    if friend.count >= AC.RECEIVE_CAP then return false end
    friend.count, friend.nonces[nonce] = friend.count + 1, true
    return true
end
-- True while this character may still send a live announcement; counts it.
function AC.spend()
    if sent >= AC.SESSION_CAP then return false end
    sent = sent + 1
    return true
end

local character, emit
function AC.init(current, callback)
    character, emit = current, callback
end
-- ACHIEVEMENT_EARNED: achievementID, alreadyEarned (earned before by another
-- character of this account). Only a first earn on the account is shared.
function AC.earned(rawID, alreadyEarned)
    if not character or not emit or not AC.available() then return nil end
    if S.value(alreadyEarned) == true then return nil end
    local id = AC.id(rawID)
    if not id or not AC.info(id) then return nil end
    return emit("achievement", {achievement_id=id})
end

local frame = CreateFrame("Frame")
if AC.available() then
    if not C_EventUtils or not C_EventUtils.IsEventValid or S.call(C_EventUtils.IsEventValid, "ACHIEVEMENT_EARNED") then
        pcall(frame.RegisterEvent, frame, "ACHIEVEMENT_EARNED")
    end
end
frame:SetScript("OnEvent", function(_, _, ...) AC.earned(...) end)
