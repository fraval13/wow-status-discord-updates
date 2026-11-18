-- Compact group status line (#62): "WoW Status · 3 online · Bob hit 42 (5m)".
-- It sits under the quest tracker when one is found and attaching is chosen,
-- otherwise it is a small panel you can drag; dragging an attached line unpins it. Clicking it opens the main
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

local T = WoWStatusLocale.T
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

-- Labs (#238): a private race to a level against one friend. Stored for this
-- character only and never sent; the friend is not told. It reads the level-ups
-- already in the shared log.
WoWStatusFeatures.register("race", "Race a friend to a level",
    "Pick a friend and a level (/wstatus race Name 40): the status line shows both of you, and a banner says who got there first. The friend is never told.")
local function raceStore()
    local character = WoWStatusPopups.character and WoWStatusPopups.character()
    if type(WoWStatusDB) ~= "table" or not character or not character.identity then return nil end
    WoWStatusDB.races = type(WoWStatusDB.races) == "table" and WoWStatusDB.races or {}
    return WoWStatusDB.races, character.identity.guid
end
function L.race()
    if not WoWStatusFeatures.enabled("race") then return nil end
    local store, id = raceStore()
    local race = store and store[id]
    if type(race) ~= "table" or type(race.friend) ~= "string" or not S.number(race.target) then return nil end
    return race
end
-- Highest level and earliest time at or after the target, for one side of the log.
local function reached(sender, owner, target)
    local top, first = 0, nil
    for _, e in ipairs(WoWStatusJournal.entries()) do
        if e.kind == "level" and S.number(e.level) and WoWStatusJournal.visible(e)
            and ((owner and e.owner) or (not owner and not e.owner and e.sender == sender)) then
            if e.level > top then top = e.level end
            if e.level >= target and S.number(e.at) and (not first or e.at < first) then first = e.at end
        end
    end
    return top, first
end
-- The friend's full sender name, from the log, for a typed name.
local function friendSender(name)
    local want = S.lowerASCII(name)
    for _, e in ipairs(WoWStatusJournal.entries()) do
        if not e.owner and e.kind == "level" and type(e.sender) == "string" and WoWStatusJournal.visible(e)
            and S.lowerASCII(e.sender:match("^[^-]+") or e.sender) == want then return e.sender end
    end
end
function L.raceStart(name, target)
    if not WoWStatusFeatures.enabled("race") then return false, "Turn on Race a friend on the Labs page first." end
    local store, id = raceStore()
    target = math.floor(S.number(target) or 0)
    local max = WoWStatusAdapter.max_level or 60
    if not store or target < 2 or target > max then return false, "Pick a level from 2 to " .. max .. "." end
    local sender = type(name) == "string" and friendSender(name)
    if not sender then return false, "No friend by that name in your activity log yet." end
    store[id] = {friend = sender, target = target}
    L.update()
    return true
end
function L.raceCancel()
    local store, id = raceStore()
    if store and store[id] then store[id] = nil; L.update(); return true end
    return false
end
-- The status line text, or nil. Settles the race when either side got there.
function L.raceText()
    local race = L.race()
    if not race then return nil end
    local store, id = raceStore()
    local mine, myAt = reached(nil, true, race.target)
    local theirs, theirAt = reached(race.friend, false, race.target)
    local name = race.friend:match("^[^-]+") or race.friend
    if theirs == 0 then store[id] = nil; return nil end -- Left the group: end cleanly.
    if myAt or theirAt then
        store[id] = nil
        local won = myAt and (not theirAt or myAt <= theirAt)
        if WoWStatusPopups.notice then
            WoWStatusPopups.notice({sender = race.friend, kind = "first",
                text = won and (T("You won the race to level") .. " " .. race.target .. "!")
                    or (name .. " " .. T("got to level") .. " " .. race.target .. " " .. T("first") .. "!")})
        end
        return nil
    end
    return T("Race to") .. " " .. race.target .. ": " .. T("you") .. " " .. mine .. " · " .. name:gsub("|", "||") .. " " .. theirs
end

function L.text()
    local parts = {"WoW Status", WoWStatusPopups.onlineCount() .. " " .. T("online")}
    local race = L.raceText()
    if race then return race end
    -- Quiet hours take the place of the latest news, so the line stays one line.
    local latest = WoWStatusPopups.quietHoursText and WoWStatusPopups.quietHoursText() or L.latest()
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
