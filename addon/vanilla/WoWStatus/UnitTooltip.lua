-- A short WoW Status block in a group member's unit tooltip (#183).
-- Mousing over a character a friend in one of your groups has listed adds a
-- marker line and the values you picked, top first, from what the addon
-- already stores: item level, deaths, professions, level progress and more.
-- Nothing is requested or sent. Non-members, hidden characters and values a
-- character does not share add nothing; a character with none of the picked
-- values gets no block at all. Account-wide setting: on or off, and the list of
-- values, which you add to, remove from and reorder in Options. Defaults: on,
-- with item level, deaths and professions.
--
-- Modern clients (Retail, and Classic clients built on it) build tooltips from
-- tooltip data (TooltipDataProcessor) and no longer have OnTooltipSetUnit;
-- older ones have only the script. The script is used where it exists, the
-- processor otherwise: exactly one, each guarded, so a client with neither
-- simply shows no block.
WoWStatusUnitTooltip = {}
local U, S = WoWStatusUnitTooltip, WoWStatusSafe
local T = WoWStatusLocale.T

local function count(value) return value and value > 0 and tostring(value) or nil end
-- Every value the block can show, in the order Options lists the ones not picked.
-- show(facts) returns the text, or nil when the character does not share it.
U.VALUES = {
    {key="item_level", label="Average item level", show=function(f) return f.item_level and tostring(math.floor(f.item_level)) end},
    {key="deaths", label="Total deaths", show=function(f) return f.deaths and tostring(f.deaths) end},
    -- Two to a line, best skill first, so five professions do not stretch the tooltip.
    {key="professions", label="Professions", show=function(f)
        local lines, line = {}, {}
        for _, item in ipairs(f.professions or {}) do
            line[#line + 1] = item.name .. " " .. item.skill
            if #line == 2 then lines[#lines + 1], line = table.concat(line, ", "), {} end
        end
        if #line > 0 then lines[#lines + 1] = table.concat(line, ", ") end
        return #lines > 0 and lines or nil
    end},
    {key="level", label="Level progress", show=function(f) return f.xp and (math.floor(f.xp / 10) .. "%") end},
    {key="quests", label="Quests", show=function(f) return f.quests and tostring(f.quests) end},
    {key="played", label="Played", show=function(f) return f.played and WoWStatusUI and WoWStatusUI.duration(f.played) end},
    {key="gold", label="Gold", show=function(f) return f.gold and WoWStatusUI and WoWStatusUI.money(f.gold, true) end},
    {key="kills", label="Monsters killed", show=function(f) return count(f.kills) end},
    {key="dungeons", label="Dungeons cleared", show=function(f) return count(f.dungeons) end},
    {key="mounts", label="Mounts", show=function(f) return count(f.mounts) end},
    {key="honor_kills", label="Honorable kills", show=function(f) return count(f.honor_kills) end},
}
local BY_KEY = {}
for _, value in ipairs(U.VALUES) do BY_KEY[value.key] = value end
U.DEFAULT = {"item_level", "deaths", "professions"}

-- The saved setting, repaired once per table: shown is a list of keys, each
-- once. A key this version does not know is kept (a newer version wrote it)
-- but neither shown nor listed.
function U.settings()
    if type(WoWStatusDB) ~= "table" then return {enabled=false, shown={}} end
    local value = WoWStatusDB.unit_tooltip
    if value == U.repaired and type(value) == "table" then return value end
    value = type(value) == "table" and value or {}
    WoWStatusDB.unit_tooltip = value
    value.enabled = value.enabled ~= false
    value.size = nil -- An earlier draft of this setting.
    local list, seen = {}, {}
    for _, key in ipairs(type(value.shown) == "table" and value.shown or U.DEFAULT) do
        if type(key) == "string" and #key <= 40 and not seen[key] and #list < 40 then list[#list + 1], seen[key] = key, true end
    end
    value.shown, U.repaired = list, value
    return value
end
-- The picked values this version knows, top first.
function U.picked()
    local list = {}
    for _, key in ipairs(U.settings().shown) do if BY_KEY[key] then list[#list + 1] = key end end
    return list
end
function U.setEnabled(enabled) U.settings().enabled = enabled == true end
local function position(list, key)
    for i, item in ipairs(list) do if item == key then return i end end
end
-- Picked values go to the bottom of the list.
function U.addValue(key)
    local list = U.settings().shown
    if BY_KEY[key] and not position(list, key) then list[#list + 1] = key end
end
function U.removeValue(key)
    local list = U.settings().shown
    local i = position(list, key)
    if i then table.remove(list, i) end
end
-- Above the known value before it, past any unknown ones in between.
function U.moveUp(key)
    local list = U.settings().shown
    local i = position(list, key)
    if not i then return end
    for j = i - 1, 1, -1 do
        if BY_KEY[list[j]] then list[j], list[i] = list[i], list[j]; return end
    end
end

-- The block for a character name as {header, {label, value}, ...}, or nil.
function U.lines(name, liveLevel, guid)
    local value = U.settings()
    if not value.enabled or not WoWStatusRoster or not WoWStatusRoster.tooltipFacts then return nil end
    local picked, want = U.picked(), {}
    if #picked == 0 then return nil end
    for _, key in ipairs(picked) do want[key] = true end
    local facts = WoWStatusRoster.tooltipFacts(name, liveLevel, guid, want)
    if not facts then return nil end
    local rows = {}
    for _, key in ipairs(picked) do
        local item = BY_KEY[key]
        local shown = item.show(facts)
        local label = key == "quests" and facts.quests_source == "tracked_since" and "Quests (tracked)" or item.label
        -- A list value continues on lines without a label.
        for i, text in ipairs(type(shown) == "table" and shown or {shown}) do
            rows[#rows + 1] = {i == 1 and T(label) or " ", text}
        end
    end
    if #rows == 0 then return nil end
    -- The player behind the character, when you also know their other characters.
    local header = "WoW Status"
    if facts.alts > 0 and facts.player then header = header .. " · " .. facts.player:gsub("|", "||") end
    return {header=header, rows=rows}
end

-- data is the tooltip data on modern clients. Without a unit token from the
-- tooltip, "mouseover" counts only when its GUID is the one the tooltip shows,
-- so a block never lands on someone else's tooltip.
function U.add(tooltip, data)
    if not tooltip or tooltip ~= GameTooltip then return end
    local unit = S.string((select(2, S.call(tooltip.GetUnit, tooltip))))
    if not unit then
        local guid = type(data) == "table" and S.string(data.guid)
        if guid and S.stringCall(UnitGUID, "mouseover") == guid then unit = "mouseover" end
    end
    local name = WoWStatusRoster and WoWStatusRoster.unitName and WoWStatusRoster.unitName(unit)
    if not name then return end
    -- Once per build: a hook firing again for the same unit, before the tooltip
    -- was cleared (it then has fewer lines again), adds nothing.
    local lines = S.number(S.call(tooltip.NumLines, tooltip))
    if lines and U.added and U.added.name == name and lines >= U.added.lines then return end
    local block = U.lines(name, S.number(S.call(UnitLevel, unit)), S.stringCall(UnitGUID, unit))
    if not block then return end
    tooltip:AddLine(block.header, 1, .82, 0)
    for _, row in ipairs(block.rows) do tooltip:AddDoubleLine(row[1], row[2], .8, .8, .8, 1, 1, 1) end
    local after = S.number(S.call(tooltip.NumLines, tooltip))
    U.added = after and {name=name, lines=after} or nil
    if tooltip.Show then tooltip:Show() end -- Resize to fit the added lines.
end

local function safely(tooltip, data) pcall(U.add, tooltip, data) end
-- Installs one hook, once. Returns which: "data", "script" or nil.
function U.hook()
    if U.hooked ~= nil then return U.hooked end
    U.hooked = false
    local processor = type(TooltipDataProcessor) == "table" and TooltipDataProcessor.AddTooltipPostCall
    local unitType = type(Enum) == "table" and type(Enum.TooltipDataType) == "table" and Enum.TooltipDataType.Unit
    -- The script wherever GameTooltip still has it (it fires for units there,
    -- even if the shared processor table exists too); the data path otherwise.
    local hasScript = GameTooltip and GameTooltip.HookScript
        and (not GameTooltip.HasScript or GameTooltip:HasScript("OnTooltipSetUnit"))
    if hasScript and pcall(GameTooltip.HookScript, GameTooltip, "OnTooltipSetUnit", safely) then U.hooked = "script"
    elseif type(processor) == "function" and unitType ~= nil and pcall(processor, unitType, safely) then U.hooked = "data" end
    return U.hooked
end

-- Options: the switch and the list, below "Characters shown to friends". The
-- picked values come first, top first, each with Move up and Remove; the rest
-- follow with Add. Plain buttons, so a controller reaches every one.
U.ROW = 28
U.HEIGHT = 70 + #U.VALUES * U.ROW
function U.buildSettings(parent, y)
    local box = {rows={}}
    box.check = CreateFrame("CheckButton", nil, parent, "UICheckButtonTemplate")
    box.check:SetPoint("TOPLEFT", 24, y); box.check:SetSize(32, 32)
    box.label = box.check:CreateFontString(nil, "OVERLAY", "GameFontHighlightLarge")
    box.label:SetPoint("TOPLEFT", 38, -6); box.label:SetWidth(500); box.label:SetJustifyH("LEFT")
    box.label:SetText(T("Show WoW Status in group members' tooltips"))
    box.hint = parent:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    box.hint:SetPoint("TOPLEFT", 54, y - 42); box.hint:SetWidth(480); box.hint:SetJustifyH("LEFT")
    for i = 1, #U.VALUES do
        local row, top = {}, y - 62 - (i - 1) * U.ROW
        row.label = parent:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
        row.label:SetPoint("TOPLEFT", 54, top - 5); row.label:SetWidth(250); row.label:SetJustifyH("LEFT")
        row.up = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
        row.up:SetPoint("TOPLEFT", 310, top); row.up:SetSize(110, 24)
        row.toggle = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
        row.toggle:SetPoint("TOPLEFT", 428, top); row.toggle:SetSize(110, 24)
        row.up:SetScript("OnClick", function() if row.key then U.moveUp(row.key); box:refresh() end end)
        row.toggle:SetScript("OnClick", function()
            if not row.key then return end
            if row.picked then U.removeValue(row.key) else U.addValue(row.key) end
            box:refresh()
        end)
        box.rows[i] = row
    end
    function box:refresh()
        local value = U.settings()
        self.check:SetChecked(value.enabled)
        self.hint:SetText(T("Values shown, top first:"))
        local order, picked = {}, {}
        for _, key in ipairs(U.picked()) do order[#order + 1], picked[key] = key, true end
        for _, item in ipairs(U.VALUES) do if not picked[item.key] then order[#order + 1] = item.key end end
        for i, row in ipairs(self.rows) do
            row.key, row.picked = order[i], picked[order[i]] == true
            row.label:SetText(T(BY_KEY[row.key].label))
            if row.label.SetTextColor then
                -- An unpicked value also says so on its button (Add rather than Remove).
                local grey = WoWStatusUI and WoWStatusUI.MUTED or .62
                if row.picked then row.label:SetTextColor(1, 1, 1) else row.label:SetTextColor(grey, grey, grey) end
            end
            row.up:SetText(T("Move up")); row.toggle:SetText(T(row.picked and "Remove" or "Add"))
            -- A button that does nothing is hidden or disabled, so a controller skips it.
            row.up:SetShown(row.picked)
            if row.up.SetEnabled then row.up:SetEnabled(value.enabled and i > 1) end
            if row.toggle.SetEnabled then row.toggle:SetEnabled(value.enabled) end
        end
    end
    box.check:SetScript("OnClick", function(self) U.setEnabled(self:GetChecked() and true or false); box:refresh() end)
    box:refresh()
    return box
end

U.hook()
