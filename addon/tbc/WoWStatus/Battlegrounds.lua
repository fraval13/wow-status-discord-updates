-- One result per finished battleground, with only this character's public
-- scoreboard row. Missing/restricted values stay unknown, never zero-filled.
WoWStatusBattlegrounds = {}
local B, S = WoWStatusBattlegrounds, WoWStatusSafe
local character, emitResult, pending, reported
local frame = CreateFrame("Frame")
local FIELDS = {"killing_blows", "honorable_kills", "deaths", "honor", "damage", "healing"}
local MODERN = {"killingBlows", "honorableKills", "deaths", "honorGained", "damageDone", "healingDone"}
local LIMITS = {99999, 99999, 99999, 9999999, 9999999999999, 9999999999999}
local function score(value, index)
    value = S.number(value)
    if value and value >= 0 and value <= LIMITS[index] and value == math.floor(value) then return value end
end
local function modernRow()
    local guid = S.string(S.call(UnitGUID, "player"))
    local info = guid and S.call(C_PvP and C_PvP.GetScoreInfoByPlayerGuid, guid)
    if type(info) ~= "table" then return nil end
    local values = {}
    for i, key in ipairs(MODERN) do values[i] = score(S.call(function() return info[key] end), i) end
    return values
end
local function legacyRow()
    local count = S.number(S.call(GetNumBattlefieldScores))
    if not count or count < 1 or count > 200 or type(GetBattlefieldScore) ~= "function" then return nil end
    local P = WoWStatusPopups
    local own = P.senderKey(P.characterName(character))
    for index = 1, math.floor(count) do
        -- Safe.call intentionally keeps only four returns; this legacy API has
        -- eleven. Guard each value before comparing or doing arithmetic.
        local ok, name, kb, hk, deaths, honor, _, _, _, _, damage, healing = pcall(GetBattlefieldScore, index)
        name = S.string(name)
        if ok and name and P.senderKey(name) == own then
            return {score(kb, 1), score(hk, 2), score(deaths, 3), score(honor, 4), score(damage, 5), score(healing, 6)}
        end
    end
end
function B.capture()
    if not character then return nil end
    local values = modernRow() or legacyRow()
    if not values then return nil end
    local stats = {}
    for i, key in ipairs(FIELDS) do stats[key] = values[i] end
    return next(stats) and stats or nil
end
local function complete(stats)
    for _, key in ipairs(FIELDS) do if not stats or stats[key] == nil then return false end end
    return true
end
local function finish()
    local data = pending.data
    pending, reported = nil, true
    emitResult("battleground", data)
end
function B.update()
    if not character then return end
    local _, kind = S.call(IsInInstance)
    if S.string(kind) ~= "pvp" then
        -- Leaving before the scoreboard arrives still keeps the known result.
        if pending then finish() end
        pending, reported = nil, false
        return
    end
    if reported then return end
    if not pending then
        local winner = S.number(S.call(GetBattlefieldWinner))
        local side = winner == 0 and "Horde" or winner == 1 and "Alliance" or nil
        local faction = S.stringCall(UnitFactionGroup, "player")
        local name = S.string(S.call(GetInstanceInfo)) or WoWStatusAdapter.zone()
        if not side or not faction or not name then return end
        pending = {data = {name = S.cut(name, 48), won = side == faction}, untilAt = S.uptime() + 3}
        -- Request only once, after the match has ended. No scoreboard polling
        -- during play and no combat-log tracking of damage or healing.
        S.call(RequestBattlefieldScoreData)
        if not pending or reported then return end
    end
    local stats = B.capture()
    if stats then
        pending.data.stats = pending.data.stats or {}
        for key, value in pairs(stats) do pending.data.stats[key] = value end
    end
    local supported = (C_PvP and type(C_PvP.GetScoreInfoByPlayerGuid) == "function")
        or type(GetBattlefieldScore) == "function"
    if complete(pending.data.stats) or not supported or S.uptime() >= pending.untilAt then finish() end
end
function B.init(current, callback)
    character, emitResult, pending, reported = current, callback, nil, false
end
for _, event in ipairs({"UPDATE_BATTLEFIELD_STATUS", "UPDATE_BATTLEFIELD_SCORE", "PVP_MATCH_COMPLETE", "PLAYER_ENTERING_WORLD"}) do
    if not C_EventUtils or not C_EventUtils.IsEventValid or S.call(C_EventUtils.IsEventValid, event) == true then
        pcall(frame.RegisterEvent, frame, event)
    end
end
frame:SetScript("OnEvent", function() B.update() end)
local elapsedSince = 0
frame:SetScript("OnUpdate", function(_, elapsed)
    if not pending then return end
    elapsedSince = elapsedSince + elapsed
    if elapsedSince >= .25 then elapsedSince = 0; B.update() end
end)

-- This same bounded text travels live and in log catch-up, without a second
-- message or a new wire format. Shorten only a long name, never a score.
function B.text(data)
    local name = S.string(data.name)
    if not name then return nil end
    name = S.cut(S.stripEscapes(name):gsub(S.CONTROL_OR_PIPE, " "), 48)
    local values, any = {}, false
    for i, key in ipairs(FIELDS) do
        local value = type(data.stats) == "table" and score(data.stats[key], i)
        values[i] = value and string.format("%.0f", value) or "-"
        if value then any = true end
    end
    local suffix = any and string.format(" (KB %s, HK %s, deaths %s, honor %s, dmg %s, heal %s)",
        values[1], values[2], values[3], values[4], values[5], values[6]) or ""
    local prefix = data.won and "Won " or "Lost "
    return prefix .. S.cut(name, 120 - #prefix - #suffix) .. suffix
end
function B.validText(text)
    local action, body = text:match("^(%a+) (.+)$")
    if action ~= "Won" and action ~= "Lost" then return false end
    local name, kb, hk, deaths, honor, damage, healing = body:match(
        "^(.+) %(KB ([%d%-]+), HK ([%d%-]+), deaths ([%d%-]+), honor ([%d%-]+), dmg ([%d%-]+), heal ([%d%-]+)%)$")
    if not name then return not body:find(" %(KB ") and #body <= 48 and body:find(S.NONSPACE) ~= nil end
    if #name > 48 or not name:find(S.NONSPACE) then return false end
    local any = false
    for i, value in ipairs({kb, hk, deaths, honor, damage, healing}) do
        if value ~= "-" then
            local number = score(tonumber(value), i)
            if not number or string.format("%.0f", number) ~= value then return false end
            any = true
        end
    end
    return any and #text <= 120
end


-- Split only for rendering: the saved/synced text and stable event ID stay intact.
function B.parts(text)
    if type(text) ~= "string" then return text, nil end
    local base, kb, hk, deaths, honor, damage, healing = text:match(
        "^(.+) %(KB ([%d%-]+), HK ([%d%-]+), deaths ([%d%-]+), honor ([%d%-]+), dmg ([%d%-]+), heal ([%d%-]+)%)$")
    if not base or not B.validText(text) then return text, nil end
    local T = WoWStatusLocale.T
    return base, T("Killing blows") .. ": " .. kb .. " · " .. T("HK") .. ": " .. hk .. " · " .. T("Deaths") .. ": " .. deaths
        .. "\n" .. T("Honor") .. ": " .. honor .. " · " .. T("Damage") .. ": " .. damage .. " · " .. T("Healing") .. ": " .. healing
end
