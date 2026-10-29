-- One visual vocabulary for live toasts and the persistent activity log.
WoWStatusPresentation = {}
function WoWStatusPresentation.theme(item)
    local themes = {
        level={"level-arrow",1,.82,.2,"LEVEL UP!"},
        loot={"INV_Chest_Plate04",.72,.35,1,"LOOT FOUND"},
        death={"Ability_Rogue_FeignDeath",.95,.18,.2,"A FRIEND HAS FALLEN"},
        zone={"INV_Misc_Map_01",.25,.9,.6,"ON THE MOVE"},
        session={"Spell_Arcane_TeleportStormWind",.4,.7,1,"FRIEND UPDATE"},
        quest={"Achievement_Quests_Completed_08",1,.8,.2,"QUEST ACHIEVEMENT!"},
        profession={"Trade_Tailoring",.35,.85,1,"PROFESSION PROMOTION!"},
        introduction={"Achievement_Character_Human_Male",.9,.75,.4,"WELCOME, ADVENTURER!"},
        dungeon={"Achievement_Dungeon_Deadmines",1,.75,.2,"FIRST DUNGEON CLEAR!"},
        mount={"Ability_Mount_RidingHorse",1,.8,.3,"A NEW ADVENTURE!"},
        reputation={"Achievement_Reputation_01",.3,.8,1,"REPUTATION MILESTONE!"},
        unlock={"INV_Misc_Book_07",.6,.4,1,"CLASS ABILITY UNLOCKED!"},
        pvp={"Achievement_PVP_A_01",1,.35,.2,"PVP PROMOTION!"},
    }
    themes.questprogress={"INV_Misc_Book_09",1,.8,.2,"QUEST COMPLETED"}
    themes.equipment={"INV_Chest_Plate04",.3,.7,1,"EQUIPMENT"}
    if item.kind=="loot" then
        local rarities={[3]={0,.44,.87,"RARE ARMOR"},[4]={.64,.21,.93,"EPIC ARMOR"},[5]={1,.5,0,"LEGENDARY ARMOR"}}
        local rarity=rarities[item.quality]
        if rarity then themes.loot={"INV_Chest_Plate04",rarity[1],rarity[2],rarity[3],rarity[4]} end
    end
    local kind = ({professionprogress="profession"})[item.kind] or item.kind
    local theme = themes[item.level and "level" or kind] or themes.session
    local icon = theme[1]
    if item.kind == "profession" or item.kind == "professionprogress" then
        local professionIcons = {Alchemy="Trade_Alchemy", Blacksmithing="Trade_BlackSmithing",
            Enchanting="Trade_Engraving", Engineering="Trade_Engineering", Herbalism="Trade_Herbalism",
            Leatherworking="Trade_LeatherWorking", Mining="Trade_Mining", Skinning="INV_Misc_Pelt_Wolf_01",
            Tailoring="Trade_Tailoring", Cooking="INV_Misc_Food_15", ["First Aid"]="Spell_Holy_SealOfSacrifice",
            Fishing="Trade_Fishing"}
        local profession = (item.text or ""):match("^Learned (.-) %(") or (item.text or ""):match("^(.-):")
        if (item.text or ""):match("^Learned ") then theme[5] = "PROFESSION LEARNED!" end
        icon = professionIcons[profession] or "Trade_BlackSmithing"
    end
    local texture = item.level and "Interface\\AddOns\\WoWStatus\\Textures\\LevelUp"
        or ("Interface\\Icons\\" .. icon)
    return texture, theme[2], theme[3], theme[4], item.kind=="professionprogress" and "PROFESSION PROGRESS" or theme[5]
end
