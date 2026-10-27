-- Classic Era API boundary. Forever support must be verified in its own client.
WoWStatusAdapter = {}
local A = WoWStatusAdapter

function A.identity()
    local _, build, _, interface = GetBuildInfo()
    return {
        guid = UnitGUID("player"), name = UnitName("player"), realm = GetRealmName(),
        client = "classic-era", build = tostring(build), interface = interface,
    }
end

function A.supported()
    return WOW_PROJECT_ID and WOW_PROJECT_CLASSIC and WOW_PROJECT_ID == WOW_PROJECT_CLASSIC
end

function A.snapshot(fields)
    local s = {}
    if fields.level then s.level = UnitLevel("player") end
    if fields.class then s.class = UnitClass("player") end
    if fields.race then s.race = UnitRace("player") end
    if fields.faction then s.faction = UnitFactionGroup("player") end
    if fields.guild then s.guild = GetGuildInfo("player") end
    if fields.zone then s.zone = GetRealZoneText() end
    if fields.gear then
        s.gear = {}
        for slot = 1, 19 do
            local link = GetInventoryItemLink("player", slot)
            if link then s.gear[tostring(slot)] = link end
        end
    end
    -- Playtime is filled only after explicit RequestTimePlayed() consent.
    return s
end

function A.item(link)
    if not link then return nil end
    local getter = C_Item and C_Item.GetItemInfo or GetItemInfo
    if not getter then return nil end
    local name, fullLink, quality = getter(link)
    return name and fullLink, quality
end
