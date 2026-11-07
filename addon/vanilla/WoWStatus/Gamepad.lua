-- Controller navigation for WoW Status windows. With the game's own gamepad
-- support switched on (C_GamePad.IsEnabled), the top WoW Status window takes the
-- controller's menu buttons while it is open:
--   D-pad       move a gold highlight between the window's buttons and fields
--   A (PAD1)    press it (a text field takes focus)
--   X (PAD3)    right-click it
--   B (PAD2)    leave a text field, else close a menu, go Back, or close the window
--   LB / RB     previous / next page of the main window
--   right stick scroll the list under the highlight
-- Every other button passes through to the game, and nothing is taken in combat:
-- the frame lets go on PLAYER_REGEN_DISABLED, while that is still allowed, and
-- only takes the buttons again after combat. Controls are found by walking the
-- window's visible frames, so pages need no changes to be reachable. With the
-- ConsolePort addon loaded this steps aside, as ConsolePort has its own cursor.
-- Bindings.xml adds key bindings (open, activity log, dismiss notification) that
-- players can put on controller buttons in the game's key binding menu.
WoWStatusGamepad = {}
local G = WoWStatusGamepad
local T = WoWStatusLocale and WoWStatusLocale.T or function(text) return text end

G.SCROLL_SPEED = 900 -- Pixels a second with the right stick held fully.
G.STICK_DEADZONE = .25
G.POLL = .2 -- Seconds between checks for an open window.
local STRATA = {BACKGROUND=1, LOW=2, MEDIUM=3, HIGH=4, DIALOG=5, FULLSCREEN=6, FULLSCREEN_DIALOG=7, TOOLTIP=8}
local DIRECTIONS = {PADDUP={0, 1}, PADDDOWN={0, -1}, PADDLEFT={-1, 0}, PADDRIGHT={1, 0}}
local CLICKABLE = {Button=true, CheckButton=true}

local driver, highlight, root, focus, capturing, revealed
local stick = 0
local shownOrder, counter = {}, 0
local remembered = setmetatable({}, {__mode="k"}) -- The last focus in each window.

local function call(object, method, ...)
    if type(object) ~= "table" or type(object[method]) ~= "function" then return nil end
    local ok, a, b, c, d = pcall(object[method], object, ...)
    if ok then return a, b, c, d end
    return nil
end
-- All of a frame's child frames (call() keeps only the first few results).
local function children(frame)
    if type(frame) ~= "table" or type(frame.GetChildren) ~= "function" then return {} end
    local packed = {pcall(frame.GetChildren, frame)}
    if not packed[1] then return {} end
    table.remove(packed, 1)
    return packed
end
local function number(value) return type(value) == "number" and value == value and value or nil end

-- Account-wide opt-out (/wstatus controller off).
function G.allowed() return not (type(WoWStatusDB) == "table" and WoWStatusDB.controller == false) end
function G.setAllowed(value)
    if type(WoWStatusDB) ~= "table" then return false end
    WoWStatusDB.controller = (not value) and false or nil
    G.update()
    return true
end

function G.consolePort()
    if rawget(_G, "ConsolePort") ~= nil then return true end
    local loaded = C_AddOns and C_AddOns.IsAddOnLoaded or rawget(_G, "IsAddOnLoaded")
    if type(loaded) ~= "function" then return false end
    local ok, result = pcall(loaded, "ConsolePort")
    return ok and result == true
end

-- The game's gamepad support is switched on, and this client can route its buttons to a frame.
function G.supported()
    if not driver or type(driver.EnableGamePadButton) ~= "function" then return false end
    if not (C_GamePad and type(C_GamePad.IsEnabled) == "function") then return false end
    local ok, enabled = pcall(C_GamePad.IsEnabled)
    return ok and enabled == true
end

local function combat() return type(InCombatLockdown) == "function" and InCombatLockdown() and true or false end

-- Open WoW Status windows: shown UISpecialFrames entries named WoWStatus*. One inside
-- another (the profile inside the main window) is part of it, not a window of its own.
local function windows()
    local list, seen = {}, {}
    for _, name in ipairs(UISpecialFrames or {}) do
        local frame = type(name) == "string" and name:find("^WoWStatus") and rawget(_G, name)
        if type(frame) == "table" and not seen[frame] then
            seen[frame] = true
            if call(frame, "IsVisible") then
                if not shownOrder[frame] then counter = counter + 1; shownOrder[frame] = counter end
                list[#list + 1] = frame
            else
                shownOrder[frame] = nil
            end
        end
    end
    return list
end
local function inside(frame, ancestor)
    local parent = frame
    for _ = 1, 64 do
        if parent == ancestor then return true end
        parent = call(parent, "GetParent")
        if type(parent) ~= "table" then return false end
    end
    return false
end
G.inside = inside
-- The window on top: highest strata, then the one opened last.
function G.top()
    local open = windows()
    local best
    for _, frame in ipairs(open) do
        local nested = false
        for _, other in ipairs(open) do
            if other ~= frame and inside(frame, other) then nested = true; break end
        end
        if not nested then
            local strata = STRATA[call(frame, "GetFrameStrata")] or 0
            if not best or strata > best.strata or (strata == best.strata and shownOrder[frame] > best.order) then
                best = {frame=frame, strata=strata, order=shownOrder[frame]}
            end
        end
    end
    return best and best.frame or nil, open
end

-- A frame's rectangle in screen pixels: left, bottom, right, top.
local function rect(frame)
    local left, bottom, width, height = call(frame, "GetRect")
    left, bottom, width, height = number(left), number(bottom), number(width), number(height)
    if not (left and bottom and width and height) then return nil end
    local scale = number(call(frame, "GetEffectiveScale")) or 1
    return left * scale, bottom * scale, (left + width) * scale, (bottom + height) * scale
end
G.rect = rect
local function centre(frame)
    local left, bottom, right, top = rect(frame)
    if not left then return nil end
    return (left + right) / 2, (bottom + top) / 2
end
local function contains(frame, x, y)
    local left, bottom, right, top = rect(frame)
    return left ~= nil and x >= left and x <= right and y >= bottom and y <= top
end

local function scrollFrameOf(control, stop)
    local parent = call(control, "GetParent")
    for _ = 1, 64 do
        if type(parent) ~= "table" or parent == stop then return nil end
        if call(parent, "GetObjectType") == "ScrollFrame" then return parent end
        parent = call(parent, "GetParent")
    end
end
G.scrollFrameOf = scrollFrameOf
-- Whether a control lies within its scroll frame's visible area.
local function inView(control, scroll)
    if not scroll then return true end
    local _, bottom, _, top = rect(scroll)
    local _, low, _, high = rect(control)
    if not (bottom and low) then return false end
    return high <= top + 1 and low >= bottom - 1
end
G.inView = inView

local function enabled(control)
    if type(control.IsEnabled) ~= "function" then return true end
    return call(control, "IsEnabled") ~= false
end
-- Whether a frame is something a player clicks or types in.
function G.interactive(control)
    local kind = call(control, "GetObjectType")
    if kind == "EditBox" then return enabled(control) end
    if CLICKABLE[kind] then return enabled(control) and call(control, "GetScript", "OnClick") ~= nil end
    if kind == "Frame" and call(control, "IsMouseEnabled") then
        return call(control, "GetScript", "OnMouseUp") ~= nil or call(control, "GetScript", "OnMouseDown") ~= nil
    end
    return false
end

-- Every visible control in a window. A scroll frame's own scroll bar is left out
-- (the right stick scrolls), and so is anything covered by a window inside this one,
-- such as the Characters page under an open profile.
function G.controls(window, open)
    local covers = {}
    for _, other in ipairs(open or {}) do
        if other ~= window and inside(other, window) then covers[#covers + 1] = other end
    end
    local list = {}
    local function covered(control)
        local x, y = centre(control)
        if not x then return true end
        for _, cover in ipairs(covers) do
            if not inside(control, cover) and contains(cover, x, y) then return true end
        end
        return false
    end
    local function walk(frame, depth)
        if depth > 24 then return end
        for _, child in ipairs(children(frame)) do
            if type(child) == "table" and child ~= highlight and call(child, "IsVisible") then
                local kind = call(child, "GetObjectType")
                local scrollBar = (kind == "Slider" or kind == "EventFrame") and call(frame, "GetObjectType") == "ScrollFrame"
                    or child == frame.ScrollBar or (frame.scrollBar ~= nil and child == frame.scrollBar)
                if not scrollBar then
                    if G.interactive(child) and not covered(child) then list[#list + 1] = child end
                    walk(child, depth + 1)
                end
            end
        end
    end
    walk(window, 0)
    return list
end

-- The next control from `from` in direction (dx, dy): ahead of it, preferring
-- the nearest one in line. Controls scrolled out of a list's view count only
-- when moving within that list, which then scrolls to them.
function G.nearest(from, candidates, dx, dy, window)
    local fx, fy = centre(from)
    if not fx then return nil end
    local fromScroll = scrollFrameOf(from, window)
    local best, bestScore
    for _, control in ipairs(candidates) do
        if control ~= from then
            local x, y = centre(control)
            local scroll = x and scrollFrameOf(control, window)
            if x and (inView(control, scroll) or scroll == fromScroll) then
                local ax, ay = x - fx, y - fy
                local along = ax * dx + ay * dy
                if along > 1 then
                    local across = math.abs(ax * dy - ay * dx)
                    local score = along + across * 2.5
                    if not bestScore or score < bestScore then best, bestScore = control, score end
                end
            end
        end
    end
    return best
end

-- The first control in reading order that is in view.
function G.first(candidates, window)
    local best, bx, by
    for _, control in ipairs(candidates) do
        local left, _, _, top = rect(control)
        if left and inView(control, scrollFrameOf(control, window)) then
            if not best or top > by + 4 or (math.abs(top - by) <= 4 and left < bx) then
                best, bx, by = control, left, top
            end
        end
    end
    return best
end

-- Scroll a control's list so that it is in view.
function G.reveal(control, window)
    local scroll = scrollFrameOf(control, window)
    if not scroll or inView(control, scroll) then return end
    local _, bottom, _, top = rect(scroll)
    local _, low, _, high = rect(control)
    if not (bottom and low) then return end
    local scale = number(call(scroll, "GetEffectiveScale")) or 1
    local current = number(call(scroll, "GetVerticalScroll")) or 0
    local range = number(call(scroll, "GetVerticalScrollRange")) or math.huge
    local target = high > top and current - (high - top) / scale - 8 or current + (bottom - low) / scale + 8
    call(scroll, "SetVerticalScroll", math.max(0, math.min(range, target)))
end

local function leave(control)
    if not control then return end
    local script = call(control, "GetScript", "OnLeave")
    if script then pcall(script, control) end
end
local function enter(control)
    local script = call(control, "GetScript", "OnEnter")
    if script then pcall(script, control) end
end

local function createHighlight()
    highlight = CreateFrame("Frame", "WoWStatusGamepadFocus", UIParent)
    call(highlight, "EnableMouse", false)
    local fill = highlight:CreateTexture(nil, "OVERLAY")
    call(fill, "SetAllPoints"); call(fill, "SetColorTexture", 1, .82, 0, .12)
    local edges = {{"TOPLEFT", "TOPRIGHT", nil, 2}, {"BOTTOMLEFT", "BOTTOMRIGHT", nil, 2},
        {"TOPLEFT", "BOTTOMLEFT", 2, nil}, {"TOPRIGHT", "BOTTOMRIGHT", 2, nil}}
    for _, edge in ipairs(edges) do
        local line = highlight:CreateTexture(nil, "OVERLAY")
        call(line, "SetColorTexture", 1, .82, 0, .95)
        call(line, "SetPoint", edge[1]); call(line, "SetPoint", edge[2])
        if edge[3] then call(line, "SetWidth", edge[3]) else call(line, "SetHeight", edge[4]) end
    end
    highlight:Hide()
end

local function place()
    if not highlight then return end
    if not (focus and revealed and root) then highlight:Hide(); return end
    call(highlight, "ClearAllPoints")
    call(highlight, "SetPoint", "TOPLEFT", focus, "TOPLEFT", -3, 3)
    call(highlight, "SetPoint", "BOTTOMRIGHT", focus, "BOTTOMRIGHT", 3, -3)
    call(highlight, "SetFrameStrata", call(root, "GetFrameStrata") or "FULLSCREEN_DIALOG")
    call(highlight, "SetFrameLevel", math.min(9000, (number(call(focus, "GetFrameLevel")) or 1) + 20))
    highlight:Show()
end

function G.focus() return focus end
function G.root() return root end
function G.setFocus(control)
    if control == focus then place(); return end
    leave(focus)
    focus = control
    if root then remembered[root] = control end
    if control then
        G.reveal(control, root)
        if revealed then enter(control) end
    end
    place()
end

local function valid(control, candidates)
    if not control then return false end
    for _, other in ipairs(candidates) do if other == control then return true end end
    return false
end

local function release()
    if capturing and driver and not combat() then
        call(driver, "EnableGamePadButton", false)
        call(driver, "EnableGamePadStick", false)
        capturing = false
    end
    stick = 0
end

-- Follow the open windows: take the controller's buttons while a WoW Status window
-- is open (outside combat), and let go when none is.
function G.update()
    if not driver then return end
    local window = nil
    if G.allowed() and G.supported() and not G.consolePort() then window = G.top() end
    if window ~= root then
        leave(focus)
        root, focus = window, window and remembered[window] or nil
    end
    if window and not combat() then
        if not capturing then
            call(driver, "EnableGamePadButton", true)
            call(driver, "EnableGamePadStick", true)
            capturing = true
        end
    elseif not window then
        release()
    end
    if focus and not call(focus, "IsVisible") then focus = nil end
    if root and revealed and not focus then
        -- A controller player sees where they are in a window that just opened.
        local _, open = G.top()
        G.setFocus(G.first(G.controls(root, open), root))
        return
    end
    place()
end

-- Move the highlight in a direction, or onto the window's first control.
function G.move(dx, dy)
    if not root then return false end
    local _, open = G.top()
    local candidates = G.controls(root, open)
    if not valid(focus, candidates) then focus = nil end
    local wasShown = revealed
    revealed = true
    if not focus or not wasShown then
        -- The first press only shows where the highlight is.
        local target = focus or G.first(candidates, root)
        if target and target == focus then G.reveal(focus, root); enter(focus); place() else G.setFocus(target) end
        return true
    end
    local scroll = scrollFrameOf(focus, root)
    if not inView(focus, scroll) then
        -- The stick scrolled it away: start again from what is in view.
        local visible = {}
        for _, control in ipairs(candidates) do
            if scrollFrameOf(control, root) == scroll and inView(control, scroll) then visible[#visible + 1] = control end
        end
        G.setFocus(G.first(visible, root) or G.first(candidates, root))
        return true
    end
    local target = G.nearest(focus, candidates, dx, dy, root)
    if target then G.setFocus(target)
    elseif scroll and dy ~= 0 then
        -- Nothing further in that direction: scroll the list instead.
        local current = number(call(scroll, "GetVerticalScroll")) or 0
        local range = number(call(scroll, "GetVerticalScrollRange")) or 0
        call(scroll, "SetVerticalScroll", math.max(0, math.min(range, current - dy * 80)))
    end
    return true
end

-- Press the highlighted control, as a click with the given mouse button.
function G.activate(button)
    if not (root and focus and revealed) then return G.move(0, 0) end
    local kind = call(focus, "GetObjectType")
    if kind == "EditBox" then
        if button == "LeftButton" then call(focus, "SetFocus") end
        return true
    end
    if CLICKABLE[kind] then
        call(focus, "Click", button)
    else
        local down, up = call(focus, "GetScript", "OnMouseDown"), call(focus, "GetScript", "OnMouseUp")
        if down then pcall(down, focus, button) end
        if up then pcall(up, focus, button) end
    end
    G.update()
    return true
end

local function typing()
    local edit = type(GetCurrentKeyBoardFocus) == "function" and GetCurrentKeyBoardFocus() or nil
    if edit and root and inside(edit, root) then return edit end
end

-- B: leave a text field, close a menu, step Back, or close the window.
function G.cancel()
    local edit = typing()
    if edit then call(edit, "ClearFocus"); return true end
    if not root then return false end
    local main = rawget(_G, "WoWStatusMainFrame")
    if root == main and WoWStatusMainWindow and WoWStatusMainWindow.back and WoWStatusMainWindow.back() then
        G.update()
        return true
    end
    leave(focus)
    root:Hide()
    G.update()
    return true
end

-- LB/RB: the previous or next page of the main window.
function G.page(step)
    local M = WoWStatusMainWindow
    if not (M and root and root == rawget(_G, "WoWStatusMainFrame") and M.pages) then return false end
    local order, current = M.pages(), M.active and M.active()
    if #order == 0 then return false end
    local index = 1
    for i, key in ipairs(order) do if key == current then index = i end end
    index = (index - 1 + step) % #order + 1
    M.show(order[index])
    focus = nil
    G.update()
    return true
end

-- One controller button; returns whether it was used (the rest reach the game).
function G.press(button)
    if not root then return false end
    local direction = DIRECTIONS[button]
    if direction then return G.move(direction[1], direction[2]) end
    if button == "PAD1" then return G.activate("LeftButton") end
    if button == "PAD3" then return G.activate("RightButton") end
    if button == "PAD2" then return G.cancel() end
    if button == "PADLSHOULDER" then return G.page(-1) end
    if button == "PADRSHOULDER" then return G.page(1) end
    return false
end

-- The right stick scrolls the list under the highlight, or the window's first list.
local function scrollTarget()
    if not root then return nil end
    local scroll = focus and scrollFrameOf(focus, root)
    if scroll then return scroll end
    local function find(frame, depth)
        if depth > 24 then return nil end
        for _, child in ipairs(children(frame)) do
            if type(child) == "table" and call(child, "IsVisible") then
                if call(child, "GetObjectType") == "ScrollFrame" then return child end
                local found = find(child, depth + 1)
                if found then return found end
            end
        end
    end
    return find(root, 0)
end
function G.stick(name, y)
    if name ~= "Right" then return false end
    y = number(y) or 0
    stick = math.abs(y) >= G.STICK_DEADZONE and y or 0
    return true
end
function G.tick(elapsed)
    if stick == 0 or not root then return end
    local scroll = scrollTarget()
    if not scroll then return end
    local current = number(call(scroll, "GetVerticalScroll")) or 0
    local range = number(call(scroll, "GetVerticalScrollRange")) or 0
    call(scroll, "SetVerticalScroll", math.max(0, math.min(range, current - stick * G.SCROLL_SPEED * elapsed)))
end

-- Key bindings (Bindings.xml); work with or without a controller.
function G.toggle()
    local M = WoWStatusMainWindow
    if not M then return end
    if M.active and M.active() then M.hide() else M.show() end
end
function G.activity()
    if WoWStatusPopups and WoWStatusPopups.showActivity then WoWStatusPopups.showActivity() end
end
function G.dismiss()
    return WoWStatusPopups and WoWStatusPopups.dismiss and WoWStatusPopups.dismiss() or false
end

function G.bindingNames()
    _G.BINDING_HEADER_WOWSTATUS = "WoW Status"
    _G.BINDING_NAME_WOWSTATUS_TOGGLE = T("Open or close WoW Status")
    _G.BINDING_NAME_WOWSTATUS_ACTIVITY = T("Open the activity log")
    _G.BINDING_NAME_WOWSTATUS_DISMISS = T("Dismiss the notification")
end

function G.report()
    if not G.allowed() then return "Controller navigation is off. Type /wstatus controller on to turn it on." end
    if G.consolePort() then return "Controller navigation steps aside for ConsolePort." end
    if not G.supported() then return "Controller navigation is on; it starts when gamepad support is enabled in the game's options." end
    return "Controller navigation is on: D-pad moves, A selects, B goes back, LB/RB change page, the right stick scrolls."
end

local function init()
    if driver or type(CreateFrame) ~= "function" then return end
    driver = CreateFrame("Frame", "WoWStatusGamepadDriver", UIParent)
    createHighlight()
    -- A client without these script types raises an error; call() keeps it quiet.
    call(driver, "SetScript", "OnGamePadButtonDown", function(self, button)
        local used = G.press(button) and true or false
        if not combat() then call(self, "SetPropagateKeyboardInput", not used) end
    end)
    call(driver, "SetScript", "OnGamePadStick", function(_, name, _, y) G.stick(name, y) end)
    local waited = 0
    driver:SetScript("OnUpdate", function(_, elapsed)
        elapsed = number(elapsed) or 0
        G.tick(elapsed)
        waited = waited + elapsed
        if waited >= G.POLL then waited = 0; G.update() end
    end)
    driver:SetScript("OnEvent", function(_, event, active)
        if event == "PLAYER_REGEN_DISABLED" then
            -- Still allowed during this event; combat lockdown starts after it.
            if capturing then
                call(driver, "EnableGamePadButton", false)
                call(driver, "EnableGamePadStick", false)
                capturing = false
            end
            stick = 0
        elseif event == "GAME_PAD_ACTIVE_CHANGED" then
            -- The mouse took over: hide the highlight until a controller button is pressed.
            if active == false then leave(focus); revealed = false; place() end
        elseif event == "PLAYER_LOGIN" then
            G.bindingNames()
        end
        if event ~= "PLAYER_REGEN_DISABLED" then G.update() end
    end)
    for _, event in ipairs({"PLAYER_LOGIN", "PLAYER_REGEN_DISABLED", "PLAYER_REGEN_ENABLED", "GAME_PAD_ACTIVE_CHANGED"}) do
        pcall(driver.RegisterEvent, driver, event) -- Unknown events raise an error in some clients.
    end
    driver:Show()
end

G.bindingNames()
init()
