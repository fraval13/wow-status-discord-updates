-- Retail 12.x adapter, checked against the mirrored 12.1.5 client API.
WoWStatusAdapter = {client_id = "retail", display_name = "WoW Retail", max_level = 90, classicProfessionTitles = false, pvpLabel = "Honor level", max_pvp_rank = 10000}
local A, S = WoWStatusAdapter, WoWStatusSafe
local cachedIdentity

function A.supported()
    local _, _, _, interface = GetBuildInfo()
    interface = S.number(interface)
    return interface and interface>=120000 and interface<130000
        and WOW_PROJECT_MAINLINE and WOW_PROJECT_ID==WOW_PROJECT_MAINLINE or false
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
    -- Missing/secret restriction state is treated as unavailable, never a bypass opportunity.
    if not C_ChatInfo or not C_ChatInfo.InChatMessagingLockdown then return true end
    if C_ChatInfo.AreOutgoingAddonChatMessagesRestricted
        and S.call(C_ChatInfo.AreOutgoingAddonChatMessagesRestricted) ~= false then return true end
    return S.call(C_ChatInfo.InChatMessagingLockdown) ~= false
end
function A.chatSender()
    -- Do not depend on the deprecated SendChatMessage global/shim on the modern client.
    return C_ChatInfo and C_ChatInfo.SendChatMessage
end
function A.pvpRank()
    local rank = S.number(S.call(UnitHonorLevel,"player"))
    if not rank or rank<0 or rank>A.max_pvp_rank or rank~=math.floor(rank) then return nil end
    return "Honor level "..rank,rank
end
function A.pvpText(_,rank) return "Reached honor level "..rank end
function A.professions()
    -- The Retail ProfessionsBook uses these owned-profession indices. Querying
    -- every trade-skill definition would incorrectly include unlearned trades.
    if not GetProfessions or not GetProfessionInfo then return nil end
    local ok,a,b,c,d,e,f=pcall(GetProfessions)
    if not ok then return nil end
    local keys={[171]="alchemy",[164]="blacksmithing",[333]="enchanting",[202]="engineering",
        [182]="herbalism",[165]="leatherworking",[186]="mining",[393]="skinning",[197]="tailoring",
        [755]="jewelcrafting",[773]="inscription",[794]="archaeology",[185]="cooking",[356]="fishing"}
    local result={}
    for _,raw in pairs({a,b,c,d,e,f}) do
        local index=S.number(raw)
        if index then
            local valid,name,_,rank,maximum,_,_,id=pcall(GetProfessionInfo,index)
            name,rank,maximum,id=S.string(name),S.number(rank),S.number(maximum),S.number(id)
            if not valid or not name or not rank or not maximum or maximum<1 then return nil end
            table.insert(result,{name=name,skill=rank,max_skill=maximum,key=keys[id],source="game_api"})
        end
    end
    table.sort(result,function(a,b) return a.name<b.name end)
    return result
end
