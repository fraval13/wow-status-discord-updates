-- One visual vocabulary for live toasts and the persistent activity log.
WoWStatusPresentation = {}
local W = WoWStatusPresentation
-- Armor: the item's own icon, its name in quality colour and its game tooltip,
-- from the item ID the update carries (the base item: no random suffix or enchant).
local function itemID(item)
    return type(item) == "table" and (item.kind == "loot" or item.kind == "equipment") and tonumber(item.item_id) or nil
end
function W.itemIcon(item)
    local id = itemID(item)
    local get = (C_Item and C_Item.GetItemIconByID) or GetItemIcon
    if not id or not get then return nil end
    local ok, icon = pcall(get, id)
    icon = ok and WoWStatusSafe.value(icon)
    if (type(icon) == "number" and icon > 0) or (type(icon) == "string" and icon ~= "") then return icon end
    return nil
end
local QUALITY = {[2]="ff1eff00", [3]="ff0070dd", [4]="ffa335ee", [5]="ffff8000"}
-- The shown text with the item name in its quality colour ("Equipped |cffa335eeRobe|r").
function W.colourItem(item, shown)
    local colour = itemID(item) and QUALITY[tonumber(item.quality)]
    local name = colour and type(item.text) == "string" and item.text:match("^Equipped (.+)$")
    if not name or type(shown) ~= "string" then return shown end
    name = name:gsub("|", "||")
    local first, last = shown:find(name, 1, true)
    if not first then return shown end
    return shown:sub(1, first - 1) .. "|c" .. colour .. name .. "|r" .. shown:sub(last + 1)
end
-- The item's game tooltip (stats included); false when there is no item.
function W.itemTooltip(owner, item, anchor)
    local id = itemID(item)
    if not id or not GameTooltip then return false end
    GameTooltip:SetOwner(owner, anchor or "ANCHOR_RIGHT")
    local ok = GameTooltip.SetItemByID and pcall(GameTooltip.SetItemByID, GameTooltip, id)
    if not ok and GameTooltip.SetHyperlink then ok = pcall(GameTooltip.SetHyperlink, GameTooltip, "item:" .. id) end
    if not ok then GameTooltip:Hide(); return false end
    GameTooltip:Show()
    return true
end
function WoWStatusPresentation.theme(item)
    local themes = {
        level={"level-arrow",1,.82,.2,"LEVEL UP!"},
        loot={"INV_Chest_Plate04",.72,.35,1,"FIRST EQUIP!"},
        death={"Ability_Rogue_FeignDeath",.95,.18,.2,"A FRIEND HAS FALLEN"},
        zone={"INV_Misc_Map_01",.25,.9,.6,"ON THE MOVE"},
        session={"Spell_Arcane_TeleportStormWind",.4,.7,1,"FRIEND UPDATE"},
        quest={"Achievement_Quests_Completed_08",1,.8,.2,"QUEST ACHIEVEMENT!"},
        profession={"Trade_Tailoring",.35,.85,1,"PROFESSION PROMOTION!"},
        introduction={"Achievement_Character_Human_Male",.9,.75,.4,"WELCOME, ADVENTURER!"},
        guard={"INV_Misc_Book_07",1,.35,.2,"INVALID LOG DATA REPORTED"},
        -- A classic item icon every client ships; the achievement icon drew black.
        dungeon={"INV_Misc_Bone_HumanSkull_01",1,.75,.2,"FIRST DUNGEON CLEAR!"},
        raid={"Achievement_Boss_Ragnaros",1,.6,.15,"FIRST RAID BOSS!"},
        epicmount={"Ability_Mount_RidingHorse",.7,.3,1,"FIRST EPIC MOUNT!"},
        mount={"Ability_Mount_RidingHorse",1,.8,.3,"A NEW ADVENTURE!"},
        reputation={"Achievement_Reputation_01",.3,.8,1,"REPUTATION MILESTONE!"},
        unlock={"INV_Misc_Book_07",.6,.4,1,"CLASS ABILITY UNLOCKED!"},
        pvp={"Achievement_PVP_A_01",1,.35,.2,"PVP PROMOTION!"},
        first={"INV_Misc_Coin_01",1,.85,.3,"A NEW FIRST!"},
        recap={"INV_Misc_Book_09",.8,.7,.5,"SESSION RECAP"},
        tracking={"INV_Misc_Book_07",.6,.75,.9,"TRACKING STARTED"},
    }
    themes.questprogress={"INV_Misc_Book_09",1,.8,.2,"QUEST COMPLETED"}
    themes.equipment={"INV_Chest_Plate04",.3,.7,1,"EQUIPMENT"}
    if item.kind=="loot" then
        local rarities={[3]={0,.44,.87,"RARE ARMOR EQUIPPED!"},[4]={.64,.21,.93,"EPIC ARMOR EQUIPPED!"},[5]={1,.5,0,"LEGENDARY ARMOR EQUIPPED!"}}
        local rarity=rarities[item.quality]
        if rarity then themes.loot={"INV_Chest_Plate04",rarity[1],rarity[2],rarity[3],rarity[4]} end
    end
    if item.kind=="pvp" and (item.text or ""):match("^Reached honor level ") then themes.pvp[5]="HONOR LEVEL UP!" end
    local kind = ({professionprogress="profession"})[item.kind] or item.kind
    local theme = themes[item.level and "level" or kind] or themes.session
    local icon = theme[1]
    if item.kind == "profession" or item.kind == "professionprogress" then
        local professionIcons = {Alchemy="Trade_Alchemy", Blacksmithing="Trade_BlackSmithing",
            Inscription="INV_Inscription_Tradeskill01", Archaeology="Trade_Archaeology", Enchanting="Trade_Engraving", Jewelcrafting="INV_Misc_Gem_01", Engineering="Trade_Engineering", Herbalism="Trade_Herbalism",
            Leatherworking="Trade_LeatherWorking", Mining="Trade_Mining", Skinning="INV_Misc_Pelt_Wolf_01",
            Tailoring="Trade_Tailoring", Cooking="INV_Misc_Food_15", ["First Aid"]="Spell_Holy_SealOfSacrifice",
            Fishing="Trade_Fishing"}
        local profession = (item.text or ""):match("^Learned (.-) %(") or (item.text or ""):match("^(.-):")
        if (item.text or ""):match("^Learned ") then theme[5] = "PROFESSION LEARNED!" end
        icon = professionIcons[profession] or "Trade_BlackSmithing"
    end
    local texture = item.level and "Interface\\AddOns\\WoWStatus\\Textures\\LevelUp"
        or W.itemIcon(item) or ("Interface\\Icons\\" .. icon)
    return texture, theme[2], theme[3], theme[4], item.kind=="professionprogress" and "PROFESSION PROGRESS" or theme[5]
end
