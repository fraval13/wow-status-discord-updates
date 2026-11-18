-- Compact group status line (#62): "WoW Status · 3 online · Bob hit 42 (5m)".
-- It sits under the quest tracker when one is found and attaching is chosen,
-- otherwise it is a small panel you can drag; dragging an attached line unpins it. Clicking it opens the main
-- window. Settings are account-wide in WoWStatusDB.status_line.
WoWStatusStatusLine = {}
local L, S, A = WoWStatusStatusLine, WoWStatusSafe, WoWStatusAdapter
local Features = WoWStatusFeatures
local GOAL = "personalCountdown"
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

local T = WoWStatusLocale.T
local TF = WoWStatusLocale.F
-- The first ordinary riding milestone makes a useful preset. Players can pick
-- any higher level up to their edition's cap.
local RIDING_LEVEL = {["classic-era"] = 40, forever = 40, ["tbc-anniversary"] = 30, retail = 10}

local function goalState()
    if not Features.enabled(GOAL) then return nil end
    local character = WoWStatusPopups.character()
    if not character then return nil end
    local level = A.level()
    if not level then return nil end
    local saved = character.personal_goal_level
    local goal = S.number(saved)
    if saved ~= nil and (not goal or goal <= level or goal > A.max_level or goal ~= math.floor(goal)) then
        character.personal_goal_level, goal = nil, nil
    end
    return character, level, goal
end

local function countdown()
    local _, level, goal = goalState()
    if not goal then return nil end
    local levels = goal - level
    local xp = S.number(S.call(UnitXP, "player"))
    local maximum = S.number(S.call(UnitXPMax, "player"))
    if xp and maximum and maximum > 0 and xp >= 0 and xp < maximum then
        -- One partly filled bar plus one full bar for each later level.
        local bars = levels - 1 + math.ceil((maximum - xp) * 10 / maximum) / 10
        return TF("Levels left: %d (%.1f XP bars)", levels, bars)
    end
    return TF("Levels left: %d", levels)
end

local function age(seconds)
    if seconds < 60 then return T("now") end
    if seconds < 3600 then return math.floor(seconds / 60) .. "m" end
    if seconds < 86400 then return math.floor(seconds / 3600) .. "h" end
    return math.floor(seconds / 86400) .. "d"
end

-- The newest friend announcement, in a few words.
function L.latest()
    for _, e in ipairs(WoWStatusJournal.entries()) do
        if type(e) == "table" and not e.owner and WoWStatusJournal.visible(e) and e.kind ~= "introduction" then
            local name = WoWStatusRoster and WoWStatusRoster.displayName and WoWStatusRoster.displayName(e.sender)
                or tostring(e.sender or "?"):match("^[^-]+") or "?"
            local text = e.kind == "level" and S.number(e.level) and (name .. " " .. T("hit") .. " " .. e.level)
                or (name .. ": " .. T(tostring(e.text or "")))
            if #text > 48 then text = text:sub(1, 45) .. "..." end
            local now = S.now()
            return text:gsub("|", "||") .. " (" .. age(math.max(0, now - (e.at or now))) .. ")"
        end
    end
end

local function text(goal, grouped)
    if goal and not grouped then return "WoW Status · " .. goal end
    local parts = {"WoW Status", WoWStatusPopups.onlineCount() .. " " .. T("online")}
    -- Keep the existing quiet-hours notice. Otherwise the goal takes the
    -- latest-news slot while active, so the status line stays compact.
    local latest = (WoWStatusPopups.quietHoursText and WoWStatusPopups.quietHoursText()) or goal or L.latest()
    if latest then table.insert(parts, latest) end
    return table.concat(parts, " · ")
end

local function hasGroup()
    return next(WoWStatusGroups.selected(WoWStatusPopups.character and WoWStatusPopups.character() or nil)) ~= nil
end

function L.text()
    local goal = countdown()
    return text(goal, goal and hasGroup())
end

local function hidden(value, goal, grouped)
    if not value.enabled or (not goal and not grouped) then return true end
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
        -- Dragging always works: an attached line is unpinned from the quest
        -- tracker and stays where it is dropped (re-attach in the settings).
        if self.attached then
            local value = settings()
            if value then value.attach = false end
            self.attached = false
        end
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
    local goal, grouped = countdown(), hasGroup()
    if hidden(value, goal, grouped) then
        if line then line:Hide() end
        return
    end
    if not line then create() end
    place(value)
    line.text:SetText(text(goal, grouped))
    line:Show()
end

function L.set(key, enabled)
    local value = settings()
    if not value or value[key] == nil then return end
    value[key] = enabled == true
    L.update()
end

local function goalPageRefresh(page)
    local _, level, goal = goalState()
    local cap, riding = A.max_level, RIDING_LEVEL[A.client_id]
    page.target:SetText(goal and TF("Target level: %d", goal) or T("No level goal"))
    WoWStatusUI.call(page.less, "SetEnabled", goal ~= nil and goal > level + 1)
    WoWStatusUI.call(page.more, "SetEnabled", level ~= nil and (goal or level) < cap)
    WoWStatusUI.call(page.riding, "SetEnabled", level ~= nil and riding ~= nil and riding > level and riding ~= goal)
    WoWStatusUI.call(page.cap, "SetEnabled", level ~= nil and cap > level and cap ~= goal)
    WoWStatusUI.call(page.clear, "SetEnabled", goal ~= nil)
end

local function goalPage(parent)
    local page = CreateFrame("Frame", nil, parent)
    page:SetAllPoints(parent)
    WoWStatusUI.text(page, "GameFontNormalLarge", 24, -12, 700):SetText(T("Personal level countdown"))
    page.target = WoWStatusUI.text(page, "GameFontHighlight", 24, -52, 700)
    local function button(label, x, y, width, choose)
        local b = CreateFrame("Button", nil, page, "UIPanelButtonTemplate")
        b:SetPoint("TOPLEFT", x, y); b:SetSize(width, 26); b:SetText(T(label))
        b:SetScript("OnClick", function()
            local character, level, goal = goalState()
            if not character then return end
            local wanted = choose(level, goal)
            if wanted and (wanted <= level or wanted > A.max_level) then return end
            character.personal_goal_level = wanted
            L.update()
            goalPageRefresh(page)
        end)
        return b
    end
    page.less = button("-", 24, -80, 66, function(level, goal) return (goal or level) - 1 end)
    page.more = button("+", 98, -80, 66, function(level, goal) return (goal or level) + 1 end)
    page.riding = button("Riding level", 24, -118, 160, function() return RIDING_LEVEL[A.client_id] end)
    page.cap = button("Level cap", 192, -118, 160, function() return A.max_level end)
    page.clear = button("Clear goal", 360, -118, 160, function() return nil end)
    return page
end

local function configureGoal()
    if not Features.enabled(GOAL) then return end
    local window = WoWStatusMainWindow
    if not window.has("personal-countdown") then
        window.register("personal-countdown", "Personal level countdown", goalPage, goalPageRefresh, {tab=false})
    end
    window.show("personal-countdown")
end

Features.register(GOAL, "Personal level countdown", "Show a private level and XP countdown in the status line.", configureGoal)

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
