-- Vanilla Classic / Classic Era adapter. Does not accept TBC or Retail clients.
WoWStatusAdapter = {client_id = "classic-era", display_name = "Vanilla Classic", max_level = 60}
local A, S = WoWStatusAdapter, WoWStatusSafe
local cachedIdentity

function A.supported()
    return WOW_PROJECT_ID and WOW_PROJECT_CLASSIC and WOW_PROJECT_ID == WOW_PROJECT_CLASSIC
end
function A.identity()
    local _, build, _, interface = GetBuildInfo()
    local guid, name, realm = S.stringCall(UnitGUID, "player"), S.stringCall(UnitName, "player"), S.stringCall(GetRealmName)
    if not guid or not name or not realm then return nil end
    cachedIdentity = {guid = guid, name = name, realm = realm, client = A.client_id,
                      build = tostring(build), interface = interface}
    return cachedIdentity
end
function A.playerName() return cachedIdentity and cachedIdentity.name or S.stringCall(UnitName, "player") end
function A.realmName()
    return S.stringCall(GetNormalizedRealmName) or (cachedIdentity and cachedIdentity.realm) or S.stringCall(GetRealmName)
end
function A.level()
    local level = S.number(S.call(UnitLevel, "player"))
    -- Loading/restricted values are unavailable observations, not a level-zero claim.
    if level and level >= 1 and level <= A.max_level then return level end
    return nil
end
function A.equipment(slot) return S.stringCall(GetInventoryItemLink, "player", slot) end
function A.zone() return S.stringCall(GetRealZoneText) end
function A.requestPlaytime() S.call(RequestTimePlayed) end
function A.snapshot(fields)
    local result = {}
    if fields.level then result.level = A.level() end
    if fields.class then
        local name, token = S.call(UnitClass, "player")
        result.class, result.class_id = S.string(name), S.string(token)
    end
    if fields.race then
        result.race = S.stringCall(UnitRace, "player")
        local sex = S.number(S.call(UnitSex, "player"))
        if sex == 2 then result.sex = "Male"
        elseif sex == 3 then result.sex = "Female" end
    end
    if fields.faction then result.faction = S.stringCall(UnitFactionGroup, "player") end
    if fields.guild then result.guild = S.stringCall(GetGuildInfo, "player") end
    if fields.zone then result.zone = A.zone() end
    if fields.gear then
        result.gear = {}
        for slot = 1, 19 do result.gear[tostring(slot)] = A.equipment(slot) end
    end
    return result
end
function A.item(link)
    if not S.string(link) then return nil end
    local getter = C_Item and C_Item.GetItemInfo or GetItemInfo
    local name, fullLink, quality = S.call(getter, link)
    return S.string(name) and S.string(fullLink), S.number(quality)
end
function A.chatRestricted()
    if C_ChatInfo and C_ChatInfo.InChatMessagingLockdown then
        local locked = S.call(C_ChatInfo.InChatMessagingLockdown)
        return locked ~= false
    end
    return false
end
function A.chatSender() return C_ChatInfo and C_ChatInfo.SendChatMessage or SendChatMessage end
