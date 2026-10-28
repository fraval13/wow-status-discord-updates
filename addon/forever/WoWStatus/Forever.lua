-- Forever/Camelot adapter, authored from the mirrored client API; in-game checks pending.
WoWStatusAdapter = {client_id = "forever", display_name = "WoW Forever", max_level = 60}
local A, S = WoWStatusAdapter, WoWStatusSafe
local cachedIdentity

function A.supported()
    local _, _, _, interface = GetBuildInfo()
    interface = S.number(interface)
    if not interface or interface < 16000 or interface >= 17000 then return false end
    if WOW_PROJECT_CAMELOT then return WOW_PROJECT_ID == WOW_PROJECT_CAMELOT end
    -- Earlier client snapshots shared the Mainline project constant; retain the interface guard.
    return WOW_PROJECT_ID == WOW_PROJECT_MAINLINE
end
function A.identity()
    local _, build, _, interface = GetBuildInfo()
    local guid = S.stringCall(UnitGUID, "player")
    local name = S.stringCall(UnitName, "player")
    local realm = S.stringCall(GetRealmName)
    -- No replacement identity is fabricated when the actual player identity is restricted.
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
    if fields.race then result.race = S.stringCall(UnitRace, "player") end
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
    if not S.string(link) or not C_Item then return nil end
    local name, fullLink, quality = S.call(C_Item.GetItemInfo, link)
    return S.string(name) and S.string(fullLink), S.number(quality)
end
function A.chatRestricted()
    -- Missing/secret restriction state is treated as unavailable, never a bypass opportunity.
    if not C_ChatInfo or not C_ChatInfo.InChatMessagingLockdown then return true end
    return S.call(C_ChatInfo.InChatMessagingLockdown) ~= false
end
function A.chatSender()
    -- Do not depend on the deprecated SendChatMessage global/shim on the modern client.
    return C_ChatInfo and C_ChatInfo.SendChatMessage
end
