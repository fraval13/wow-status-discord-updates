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
    if not S.string(link) or not C_Item then return nil end
    local name, fullLink, quality = S.call(C_Item.GetItemInfo, link)
    return S.string(name) and S.string(fullLink), S.number(quality)
end
function A.chatRestricted()
    -- Missing/secret lockdown state is treated as unavailable, never a bypass opportunity.
    -- AreOutgoingAddonChatMessagesRestricted is not consulted: in the live Forever
    -- client it returns true in the open world while InChatMessagingLockdown is false
    -- and chat works, so it stopped every send before the game could answer. Each send
    -- still reports the game's real answer: an AddOnMessageLockdown result is retried
    -- after a pause like a throttle (WoWStatusPopups.sendResult), never forced through.
    if not C_ChatInfo or not C_ChatInfo.InChatMessagingLockdown then return true end
    return S.call(C_ChatInfo.InChatMessagingLockdown) ~= false
end
function A.chatSender()
    -- Do not depend on the deprecated SendChatMessage global/shim on the modern client.
    return C_ChatInfo and C_ChatInfo.SendChatMessage
end
function A.pvpRank()
    -- Mirrors the Forever client UI's rank-points faction, not Classic's removed globals.
    local info = S.value(S.call(C_MajorFactions and C_MajorFactions.GetMajorFactionProgressionInfo,2800))
    if type(info)~="table" then return nil end
    local rank = S.number(info.renownLevel)
    local season = S.number(S.call(GetCurrentArenaSeason))
    if not rank or rank<0 or rank>100 or rank~=math.floor(rank) then return nil end
    if rank==0 then return nil,0,season end
    local first = S.number(Enum and Enum.PvPRanks and Enum.PvPRanks.Rank_1)
    local faction = S.stringCall(UnitFactionGroup,"player")
    local sex = S.number(S.call(UnitSex,"player"))
    if not first or (faction~="Alliance" and faction~="Horde") or not sex then return nil end
    local key = "PVP_RANK_"..(first+rank-1).."_"..(faction=="Alliance" and 1 or 0)
    return S.stringCall(GetText,key,sex),rank,season
end
