-- Optional automatic screenshots for a few big moments (#55, #56). Local only:
-- images go to the game's Screenshots folder and are never uploaded or sent.
-- Only live events created by this character trigger a shot; log sync,
-- previews and replayed history never reach this module.
WoWStatusScreenshots = {}
local SS, S = WoWStatusScreenshots, WoWStatusSafe
local TRIGGERS = {level=true, dungeon=true}
local OPTIONS = {"level", "dungeon", "hide_ui"}
local pending, hidden, generation = false, false, 0
SS.DELAY = 1          -- Let the level-up glow or completion screen appear first.
SS.RESTORE_AFTER = 2  -- Fallback when no SCREENSHOT_* event arrives.

function SS.available() return type(Screenshot) == "function" end

function SS.defaults(settings)
    if type(settings.screenshots) ~= "table" then settings.screenshots = {} end
    for _, key in ipairs(OPTIONS) do
        if type(settings.screenshots[key]) ~= "boolean" then settings.screenshots[key] = false end
    end
end

local function after(seconds, fn)
    if C_Timer and C_Timer.After then C_Timer.After(seconds, fn) else fn() end
end

-- Always bring the interface back, whatever happened to the shot.
function SS.restore()
    if hidden then
        hidden = false
        if UIParent and UIParent.Show then pcall(UIParent.Show, UIParent) end
    end
    pending = false
end

local function shoot(token)
    if token ~= generation then return end
    local ok = pcall(Screenshot)
    if not ok then SS.restore(); return end
    after(SS.RESTORE_AFTER, function() if token == generation then SS.restore() end end)
end

local function capture(hide)
    generation = generation + 1
    local token = generation
    -- UIParent holds protected frames, so it cannot be hidden (or shown again)
    -- during combat. Then the shot is taken with the interface visible.
    if hide and S.call(InCombatLockdown) ~= true and UIParent and UIParent.Hide
        and UIParent.IsShown and UIParent:IsShown() then
        hidden = pcall(UIParent.Hide, UIParent)
        if hidden then after(0, function() shoot(token) end); return end -- Next frame.
    end
    shoot(token)
end

-- Called with each newly created own event. Returns true when a shot is scheduled.
function SS.event(event, settings)
    local options = settings and settings.screenshots
    if type(event) ~= "table" or type(options) ~= "table" or not SS.available() then return false end
    if not TRIGGERS[event.kind] or options[event.kind] ~= true then return false end
    if type(event.data) == "table" and event.data.synthetic then return false end
    if pending then return false end -- One picture already covers this moment.
    pending = true
    after(SS.DELAY, function() capture(options.hide_ui == true) end)
    return true
end

-- /wstatus screenshot: a shot taken by hand, honouring the hide option.
function SS.manual(settings)
    if not SS.available() or pending then return false end
    pending = true
    local options = settings and settings.screenshots
    capture(type(options) == "table" and options.hide_ui == true)
    return true
end

local frame = CreateFrame("Frame")
for _, event in ipairs({"SCREENSHOT_SUCCEEDED", "SCREENSHOT_FAILED", "PLAYER_REGEN_DISABLED"}) do
    if not C_EventUtils or not C_EventUtils.IsEventValid or S.call(C_EventUtils.IsEventValid, event) == true then
        pcall(frame.RegisterEvent, frame, event)
    end
end
-- PLAYER_REGEN_DISABLED fires before combat lockdown starts, so showing the
-- interface again from it is still allowed.
frame:SetScript("OnEvent", function() SS.restore() end)
