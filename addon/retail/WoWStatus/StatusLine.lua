-- Compact group status line (#62): "WoW Status · 3 online · Bob hit 42 (5m)".
-- It sits under the quest tracker when one is found and attaching is chosen,
-- otherwise it is a small panel you can drag. Clicking it opens the main
-- window. Settings are account-wide in WoWStatusDB.status_line.
WoWStatusStatusLine = {}
local L, S = WoWStatusStatusLine, WoWStatusSafe
local line, inCombat

local function settings()
    if type(WoWStatusDB) ~= "table" then return nil end
    local value = type(WoWStatusDB.status_line) == "table" and WoWStatusDB.status_line or {}
    WoWStatusDB.status_line = value
    if value.enabled == nil then value.enabled = true end
    if value.attach == nil then value.attach = true end
    if value.hide_combat == nil then value.hide_combat = false end
    if value.hide_instance == nil then value.hide_instance = false end
    return value
end
L.settings = settings

-- Retail's objective tracker, then the Classic-era quest watch frames.
function L.tracker()
    for _, name in ipairs({"ObjectiveTrackerFrame", "QuestWatchFrame", "WatchFrame"}) do
        local frame = _G[name]
        if type(frame) == "table" and frame.IsShown and frame:IsShown() then return frame end
    end
end

local function age(seconds)
    if seconds < 60 then return "now" end
    if seconds < 3600 then return math.floor(seconds / 60) .. "m" end
    if seconds < 86400 then return math.floor(seconds / 3600) .. "h" end
    return math.floor(seconds / 86400) .. "d"
end

-- The newest friend announcement, in a few words.
function L.latest()
    for _, e in ipairs(WoWStatusJournal.entries()) do
        if type(e) == "table" and not e.owner and WoWStatusJournal.visible(e) and e.kind ~= "introduction" then
            local name = tostring(e.sender or "?"):match("^[^-]+") or "?"
            local text = e.kind == "level" and S.number(e.level) and (name .. " hit " .. e.level)
                or (name .. ": " .. tostring(e.text or ""))
            if #text > 48 then text = text:sub(1, 45) .. "..." end
            return text:gsub("|", "||") .. " (" .. age(math.max(0, WoWStatusSafe.now() - (e.at or WoWStatusSafe.now()))) .. ")"
        end
    end
end

function L.text()
    local parts = {"WoW Status", WoWStatusPopups.onlineCount() .. " online"}
    local latest = L.latest()
    if latest then table.insert(parts, latest) end
    return table.concat(parts, " · ")
end

local function hidden(value)
    if not value.enabled or not next(WoWStatusGroups.selected(WoWStatusPopups.character and WoWStatusPopups.character() or nil)) then
        return true
    end
    if value.hide_combat and inCombat then return true end
    if value.hide_instance then
        local inside, kind = S.call(IsInInstance)
        if inside == true and (kind == "party" or kind == "raid") then return true end
    end
    return false
end

local function place(value)
    line:ClearAllPoints()
    local tracker = value.attach and L.tracker() or nil
    line.attached = tracker ~= nil
    if tracker then
        line:SetPoint("TOPLEFT", tracker, "BOTTOMLEFT", 0, -4)
    elseif type(value.position) == "table" and type(value.position.point) == "string"
        and type(value.position.x) == "number" and type(value.position.y) == "number" then
        line:SetPoint(value.position.point, UIParent, value.position.relative or value.position.point,
            value.position.x, value.position.y)
    else
        line:SetPoint("TOPRIGHT", UIParent, "TOPRIGHT", -90, -260)
    end
end

local function create()
    line = CreateFrame("Button", "WoWStatusStatusLineFrame", UIParent)
    line:SetSize(320, 22); line:SetFrameStrata("LOW")
    line:SetMovable(true); line:RegisterForDrag("LeftButton")
    local background = line:CreateTexture(nil, "BACKGROUND")
    background:SetAllPoints(); background:SetColorTexture(0, 0, 0, .45)
    line.text = line:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    line.text:SetPoint("LEFT", 6, 0); line.text:SetWidth(308); line.text:SetJustifyH("LEFT")
    line:SetScript("OnClick", function(self)
        if self.moved then self.moved = false; return end
        WoWStatusMainWindow.show()
    end)
    line:SetScript("OnDragStart", function(self)
        if self.attached then return end -- Attached lines follow the tracker.
        self.moved = true; self:StartMoving()
    end)
    line:SetScript("OnDragStop", function(self)
        self:StopMovingOrSizing()
        local value = settings()
        if value and self.GetPoint then
            local point, _, relative, x, y = self:GetPoint(1)
            if type(point) == "string" and type(x) == "number" and type(y) == "number" then
                value.position = {point=point, relative=relative, x=x, y=y}
            end
        end
    end)
end

function L.update()
    local value = settings()
    if not value or not WoWStatusPopups.onlineCount then return end
    if hidden(value) then
        if line then line:Hide() end
        return
    end
    if not line then create() end
    place(value)
    line.text:SetText(L.text())
    line:Show()
end

function L.set(key, enabled)
    local value = settings()
    if not value or value[key] == nil then return end
    value[key] = enabled == true
    L.update()
end

local frame = CreateFrame("Frame")
for _, event in ipairs({"PLAYER_ENTERING_WORLD", "PLAYER_REGEN_DISABLED", "PLAYER_REGEN_ENABLED",
    "CHANNEL_ROSTER_UPDATE", "ZONE_CHANGED_NEW_AREA"}) do
    if not C_EventUtils or not C_EventUtils.IsEventValid or S.call(C_EventUtils.IsEventValid, event) == true then
        pcall(frame.RegisterEvent, frame, event)
    end
end
frame:SetScript("OnEvent", function(_, event)
    if event == "PLAYER_REGEN_DISABLED" then inCombat = true
    elseif event == "PLAYER_REGEN_ENABLED" then inCombat = false end
    L.update()
end)
if C_Timer and C_Timer.NewTicker then C_Timer.NewTicker(5, function() L.update() end) end
