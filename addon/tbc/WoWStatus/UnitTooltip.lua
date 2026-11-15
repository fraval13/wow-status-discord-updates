-- A short WoW Status block in a group member's unit tooltip (#183).
-- Mousing over a character a friend in one of your groups has listed adds a
-- marker line and up to three shared values from the stored character list:
-- level progress, total deaths, completed quests and played time, in that
-- order. Nothing is requested or sent. Non-members, hidden characters and
-- values a character does not share add nothing; a character with no shared
-- value gets no block at all. Account-wide setting: on or off, and how many
-- values (1-3). Defaults: on, two values, so the block is three lines.
--
-- Modern clients (Retail, and Classic clients built on it) build tooltips from
-- tooltip data (TooltipDataProcessor) and no longer have OnTooltipSetUnit;
-- older ones have only the script. The script is used where it exists, the
-- processor otherwise: exactly one, each guarded, so a client with neither
-- simply shows no block.
WoWStatusUnitTooltip = {}
local U, S = WoWStatusUnitTooltip, WoWStatusSafe
local T = WoWStatusLocale.T
U.MIN, U.MAX, U.DEFAULT = 1, 3, 2

function U.settings()
    if type(WoWStatusDB) ~= "table" then return {enabled=false, size=U.DEFAULT} end
    local value = type(WoWStatusDB.unit_tooltip) == "table" and WoWStatusDB.unit_tooltip or {}
    WoWStatusDB.unit_tooltip = value
    value.enabled = value.enabled ~= false
    local size = S.number(value.size)
    value.size = size and math.max(U.MIN, math.min(U.MAX, math.floor(size + .5))) or U.DEFAULT
    return value
end
function U.setEnabled(enabled) U.settings().enabled = enabled == true end
-- The next size, 1 after the largest.
function U.nextSize()
    local value = U.settings()
    value.size = value.size >= U.MAX and U.MIN or value.size + 1
    return value.size
end

-- The block for a character name as {header, {label, value}, ...}, or nil.
function U.lines(name, liveLevel, guid)
    local value = U.settings()
    if not value.enabled or not WoWStatusRoster or not WoWStatusRoster.tooltipFacts then return nil end
    local facts = WoWStatusRoster.tooltipFacts(name, liveLevel, guid)
    if not facts then return nil end
    local rows = {}
    local function add(label, shown)
        if shown and #rows < value.size then rows[#rows + 1] = {T(label), shown} end
    end
    add("Level progress", facts.xp and (math.floor(facts.xp / 10) .. "%"))
    add("Total deaths", facts.deaths and tostring(facts.deaths))
    add(facts.quests_source == "tracked_since" and "Quests (tracked)" or "Quests", facts.quests and tostring(facts.quests))
    add("Played", facts.played and WoWStatusUI and WoWStatusUI.duration(facts.played))
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

-- Options: the switch and the size, below "Characters shown to friends".
function U.buildSettings(parent, y)
    local box = {}
    box.check = CreateFrame("CheckButton", nil, parent, "UICheckButtonTemplate")
    box.check:SetPoint("TOPLEFT", 24, y); box.check:SetSize(32, 32)
    box.label = box.check:CreateFontString(nil, "OVERLAY", "GameFontHighlightLarge")
    box.label:SetPoint("TOPLEFT", 38, -6); box.label:SetWidth(500); box.label:SetJustifyH("LEFT")
    box.label:SetText(T("Show WoW Status in group members' tooltips"))
    box.size = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
    box.size:SetPoint("TOPLEFT", 54, y - 40); box.size:SetSize(240, 26)
    function box:refresh()
        local value = U.settings()
        self.check:SetChecked(value.enabled)
        self.size:SetText(WoWStatusLocale.F("Values shown: %d", value.size))
        -- A button that does nothing is disabled, so a controller skips it.
        if self.size.SetEnabled then self.size:SetEnabled(value.enabled) end
    end
    box.check:SetScript("OnClick", function(self) U.setEnabled(self:GetChecked() and true or false); box:refresh() end)
    box.size:SetScript("OnClick", function() U.nextSize(); box:refresh() end)
    box:refresh()
    return box
end

U.hook()
