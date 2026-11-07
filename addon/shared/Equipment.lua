-- Last reported equipment, not first-equip announcements. Only the player's own
-- public values are captured. Friends request one bounded snapshot on demand.
WoWStatusEquipment = {}
local E, S = WoWStatusEquipment, WoWStatusSafe
E.STATS = {
    {"health", "Health"}, {"mana", "Mana"}, {"strength", "Strength"}, {"agility", "Agility"},
    {"stamina", "Stamina"}, {"intellect", "Intellect"}, {"spirit", "Spirit"}, {"armor", "Armor"},
    {"attack_power", "Attack power"}, {"ranged_power", "Ranged attack power"},
    {"spell_power", "Spell power"}, {"healing", "Bonus healing"}, {"crit", "Melee critical strike", true},
    {"spell_crit", "Spell critical strike", true}, {"dodge", "Dodge", true}, {"parry", "Parry", true},
    {"block", "Block", true}, {"haste", "Haste", true}, {"mastery", "Mastery", true},
    {"versatility", "Versatility", true},
}
E.SLOTS = {
    {1,"Head","HeadSlot"}, {2,"Neck","NeckSlot"}, {3,"Shoulders","ShoulderSlot"},
    {15,"Cloak","BackSlot"}, {5,"Chest","ChestSlot"}, {4,"Shirt","ShirtSlot"},
    {19,"Tabard","TabardSlot"}, {9,"Wrists","WristSlot"},
    {10,"Hands","HandsSlot"}, {6,"Waist","WaistSlot"}, {7,"Legs","LegsSlot"},
    {8,"Feet","FeetSlot"}, {11,"Finger 1","Finger0Slot"}, {12,"Finger 2","Finger1Slot"},
    {13,"Trinket 1","Trinket0Slot"}, {14,"Trinket 2","Trinket1Slot"},
    {16,"Main hand","MainHandSlot"}, {17,"Off hand","SecondaryHandSlot"},
    {18,"Ranged / relic","RangedSlot"}, {0,"Ammunition","AmmoSlot"},
}
local LIMIT = 1000000000
local function number(value)
    value = S.number(value)
    return value and value >= 0 and value < LIMIT and math.floor(value) or nil
end
-- Keep the enchant, gems and random suffix. Never accept arbitrary hyperlinks.
function E.item(value)
    local text = S.string(value)
    local item = text and (text:match("|H(item:[%d:%-]+)|h") or text:match("^(item:[%d:%-]+)$"))
    local id = item and tonumber(item:match("^item:(%d+)"))
    return item and #item <= 120 and id and id > 0 and id < LIMIT and item or nil
end
local function slotValue(slot)
    if type(GetInventoryItemLink) ~= "function" then return "?" end
    local ok, link = pcall(GetInventoryItemLink, "player", slot)
    if not ok or (issecretvalue and issecretvalue(link)) then return "?" end
    if link ~= nil then return E.item(link) or "?" end
    -- A known equipped item whose link is still loading is not an empty slot.
    for _, getter in pairs({GetInventoryItemID, GetInventoryItemTexture}) do
        local found, value = pcall(getter, "player", slot)
        if not found or (issecretvalue and issecretvalue(value)) then return "?" end
        if (type(value) == "number" and value > 0) or (type(value) == "string" and value ~= "") then return "?" end
    end
    return "-"
end
local function attackPower(fn)
    local base, positive, negative = S.call(fn, "player")
    base, positive, negative = S.number(base), S.number(positive), S.number(negative)
    return base and positive and negative and number(base + positive + negative) or nil
end
-- The character sheet's common spell bonus/crit is the lowest across schools.
local function spellValue(fn)
    local best
    for school = 2, 7 do
        local value = S.number(S.call(fn, school))
        if not value then return nil end
        if not best or value < best then best = value end
    end
    return best
end
function E.capture(character)
    local settings = character and character.settings
    if not settings or not settings.fields or not settings.fields.gear then
        if character then character.equipment_profile = nil end
        return nil
    end
    local snapshot = {at=math.floor(S.now()), items={}, stats={}}
    for slot = 0, 19 do snapshot.items[slot] = slotValue(slot) end
    local stats = snapshot.stats
    stats.health = number(S.call(UnitHealthMax, "player"))
    stats.mana = number(S.call(UnitPowerMax, "player", 0))
    for index, field in ipairs({"strength", "agility", "stamina", "intellect", "spirit"}) do
        local _, effective = S.call(UnitStat, "player", index)
        stats[field] = number(effective)
    end
    local _, armor = S.call(UnitArmor, "player")
    stats.armor = number(armor)
    stats.attack_power, stats.ranged_power = attackPower(UnitAttackPower), attackPower(UnitRangedAttackPower)
    stats.spell_power, stats.healing = number(spellValue(GetSpellBonusDamage)), number(S.call(GetSpellBonusHealing))
    -- Percentages travel as integer hundredths, independent of the PC's locale.
    local percent = {crit=S.call(GetCritChance), spell_crit=spellValue(GetSpellCritChance),
        dodge=S.call(GetDodgeChance), parry=S.call(GetParryChance), block=S.call(GetBlockChance),
        haste=S.call(GetHaste), mastery=S.call(GetMasteryEffect)}
    if CR_VERSATILITY_DAMAGE_DONE then
        local rating = S.number(S.call(GetCombatRatingBonus, CR_VERSATILITY_DAMAGE_DONE))
        local bonus = 0
        if type(GetVersatilityBonus) == "function" then bonus = S.number(S.call(GetVersatilityBonus, CR_VERSATILITY_DAMAGE_DONE)) end
        percent.versatility = rating and bonus and rating + bonus or nil
    end
    for field, value in pairs(percent) do
        value = S.number(value)
        stats[field] = value and math.abs(value * 100) < LIMIT and math.floor(value * 100 + .5) or nil
    end
    character.equipment_profile = snapshot
    return snapshot
end
-- Twenty slots (including explicit empty/unavailable slots), two stat blocks
-- and a timestamp. Replacements are committed only after all 23 parts arrive.
function E.parts(snapshot, hidden)
    if type(snapshot) ~= "table" then return {{hidden and "x" or "n", "-"}} end
    local parts = {{"t", tostring(snapshot.at)}}
    for slot = 0, 19 do parts[#parts + 1] = {tostring(slot), snapshot.items[slot] or "?"} end
    for block = 1, 2 do
        local values = {}
        for i = (block - 1) * 10 + 1, block * 10 do
            local value = S.number(snapshot.stats[E.STATS[i][1]])
            if value and (math.abs(value) >= LIMIT or value ~= math.floor(value) or (value < 0 and not E.STATS[i][3])) then value = nil end
            values[#values + 1] = value and tostring(value) or "-"
        end
        parts[#parts + 1] = {block == 1 and "a" or "b", table.concat(values, ",")}
    end
    return parts
end
function E.part(part, value)
    if part == "x" or part == "n" then return value == "-" end
    if part == "t" then
        local at = tonumber(value)
        return at and value:match("^%d+$") and at >= 1000000000 and at < 10000000000
            and not S.outside(at, 10000000000, 300) and at or nil
    end
    if part == "a" or part == "b" then
        local result, count = {}, 0
        for text in (value .. ","):gmatch("([^,]*),") do
            count = count + 1
            if count > 10 then return nil end
            if text ~= "-" then
                local n = tonumber(text)
                local spec = E.STATS[(part == "a" and 0 or 10) + count]
                if not text:match("^%-?%d+$") or not S.number(n) or math.abs(n) >= LIMIT or n ~= math.floor(n)
                    or (n < 0 and not spec[3]) then return nil end
                result[spec[1]] = n
            end
        end
        return count == 10 and result or nil
    end
    local slot = tonumber(part)
    if not slot or slot < 0 or slot > 19 or tostring(slot) ~= part then return nil end
    return (value == "-" or value == "?") and value or E.item(value)
end

-- Save locally without announcements or network traffic. Delayed item data and
-- restricted combat values are tried again after loading/combat has ended.
local frame = CreateFrame("Frame")
for _, event in ipairs({"PLAYER_EQUIPMENT_CHANGED", "PLAYER_ENTERING_WORLD", "PLAYER_REGEN_ENABLED",
    "PLAYER_LOGOUT", "GET_ITEM_INFO_RECEIVED", "UNIT_STATS", "UNIT_MAXHEALTH", "UNIT_MAXPOWER", "UNIT_INVENTORY_CHANGED"}) do
    if not C_EventUtils or not C_EventUtils.IsEventValid or S.call(C_EventUtils.IsEventValid, event) == true then
        pcall(frame.RegisterEvent, frame, event)
    end
end
local dirty = false
frame:SetScript("OnEvent", function(_, event, unit)
    if event:sub(1, 5) == "UNIT_" and S.string(unit) ~= "player" then return end
    local character = WoWStatusPopups and WoWStatusPopups.character()
    if event == "PLAYER_LOGOUT" then E.capture(character) else dirty = true end
end)
local elapsed = 0
frame:SetScript("OnUpdate", function(_, delta)
    elapsed = elapsed + delta
    if elapsed < 1 then return end
    elapsed = 0
    if dirty then
        dirty = false
        E.capture(WoWStatusPopups and WoWStatusPopups.character())
        if WoWStatusProfile and WoWStatusProfile.refreshEquipment then WoWStatusProfile.refreshEquipment() end
    end
end)
