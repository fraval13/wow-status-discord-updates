-- Window themes and size (#60), saved account-wide in WoWStatusDB.theme and
-- applied immediately, without /reload. Themes only change background tint
-- (plain colour textures, no extra files), so the white and gold game fonts
-- stay readable on every theme; High contrast also strengthens box borders and
-- section lines. Night is the original look.
WoWStatusTheme = {}
local T, S = WoWStatusTheme, WoWStatusSafe
-- Achievement, the default since 1.15, is a solid dark brown like Retail's
-- achievement window, drawn with plain colour so every client shows it.
-- High contrast (#186) keeps every layout and changes only surfaces and lines:
-- an opaque black window, opaque black boxes with light borders and solid
-- section lines, so the game's white and gold text stands at its strongest.
T.ORDER = {"achievement", "night", "journal", "faction", "contrast"}
T.NAMES = {achievement="Achievement", night="Night", journal="Journal", faction="Faction", contrast="High contrast"}
-- Window size (#182): 70 to 200 % in whole percent, 100 % by default. A size
-- the screen cannot hold is shown smaller (see T.applied), never cut off.
T.MIN, T.MAX, T.STEP = .7, 2, .1
-- Notifications that follow the window size take it only within the old window
-- range, so a 200 % window does not also double every toast; their own size
-- (below) still goes from 50 to 200 %.
T.POPUP_FOLLOW_MIN, T.POPUP_FOLLOW_MAX = .8, 1.2
-- Notification size in percent, separate from the window size.
T.POPUP_MIN, T.POPUP_MAX, T.POPUP_DEFAULT = 50, 200, 100
-- The sizes offered in the options dropdown; /wstatus popupsize takes any in range.
T.POPUP_SIZES = {50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 175, 200}
local windows = {}
local main -- the first window attached (the main window), for its shown scale

-- A scale in whole percent, and a window size kept in range and rounded to
-- whole percent. Older saves held tenths (.8 to 1.2), which stay as they were.
local function percent(scale) return math.floor(scale * 100 + .5) end
local function clampScale(scale)
    return math.max(T.MIN, math.min(T.MAX, percent(scale) / 100))
end

local function settings()
    if type(WoWStatusDB) ~= "table" then return {name="night", scale=1, popups=false} end
    local value = type(WoWStatusDB.theme) == "table" and WoWStatusDB.theme or {}
    WoWStatusDB.theme = value
    -- The old default (Night) moves once to the new default; chosen themes stay.
    if not value.achievement_default then
        if value.name == nil or value.name == "night" then value.name = "achievement" end
        value.achievement_default = true
    end
    if not T.NAMES[value.name] then value.name = "achievement" end
    local scale = S.number(value.scale)
    value.scale = scale and clampScale(scale) or 1
    -- Notifications follow the theme by default since 1.15 (moved once; unticking stays).
    if not value.popups_default then value.popups = true; value.popups_default = true end
    value.popups = value.popups == true
    local size = S.number(value.popup_size)
    value.popup_size = size and math.max(T.POPUP_MIN, math.min(T.POPUP_MAX, math.floor(size + .5))) or T.POPUP_DEFAULT
    return value
end
T.settings = settings

-- Background colour {r, g, b, a} for the chosen theme.
function T.colour(alpha)
    local name = settings().name
    if name == "contrast" then return 0, 0, 0, 1 end -- opaque: nothing shows through behind text
    if name == "achievement" then return .16, .1, .045, alpha and math.max(alpha, .98) or 1 end -- solid dark brown
    if name == "journal" then return .2, .14, .07, alpha or .97 end   -- warm parchment brown
    if name == "faction" then
        local faction = S.stringCall(UnitFactionGroup, "player")
        if faction == "Horde" then return .24, .04, .03, alpha or .97 end
        return .03, .08, .24, alpha or .97                            -- Alliance blue
    end
    return .025, .035, .065, alpha or .98
end

-- The gold border drawn 6 units outside the main window, kept on screen too.
local BORDER = 6

-- UIParent's width and height (the screen in UI units), or nil when the client
-- cannot say.
local function screenSize()
    local width = UIParent and S.number(S.call(UIParent.GetWidth, UIParent))
    local height = UIParent and S.number(S.call(UIParent.GetHeight, UIParent))
    if not width or not height or width <= 0 or height <= 0 then return nil end
    return width, height
end

-- The largest scale at which a frame, with its border, fits inside UIParent;
-- nil when the client cannot say (then nothing is limited).
local function fitting(frame)
    local width, height = S.number(S.call(frame.GetWidth, frame)), S.number(S.call(frame.GetHeight, frame))
    local screenWidth, screenHeight = screenSize()
    if not width or not height or not screenWidth or width <= 0 or height <= 0 then return nil end
    return math.min(screenWidth / (width + 2 * BORDER), screenHeight / (height + 2 * BORDER))
end

-- The scale a window is shown at: the chosen size, or less when the screen
-- (resolution and UI scale) cannot hold the window at that size. Never below
-- half size, in case a client reports a nonsense screen while loading.
function T.applied(frame)
    local scale = settings().scale
    local fit = frame and fitting(frame)
    if fit then scale = math.min(scale, math.max(.5, math.floor(fit * 100) / 100)) end
    return scale
end

-- Moves a window, border included, back inside the screen when a size or
-- resolution change left part of it outside. The engine's own clamp
-- (SetClampedToScreen) is documented for dragging only, so this does the same
-- after a scale change, on every client. The top and left edges win, so the
-- title bar (where the window is dragged) and the close button stay reachable.
local function keepOnScreen(frame)
    local left, right = S.number(S.call(frame.GetLeft, frame)), S.number(S.call(frame.GetRight, frame))
    local top, bottom = S.number(S.call(frame.GetTop, frame)), S.number(S.call(frame.GetBottom, frame))
    local own = S.number(S.call(frame.GetEffectiveScale, frame))
    local parent = UIParent and S.number(S.call(UIParent.GetEffectiveScale, UIParent))
    local screenWidth, screenHeight = screenSize()
    if not left or not right or not top or not bottom or not own or not parent or not screenWidth
        or own <= 0 or parent <= 0 then return false end
    local ratio = own / parent -- frame units to UIParent units
    left, right = (left - BORDER) * ratio, (right + BORDER) * ratio
    top, bottom = (top + BORDER) * ratio, (bottom - BORDER) * ratio
    local dx, dy = 0, 0
    if right > screenWidth then dx = screenWidth - right end
    if left + dx < 0 then dx = -left end
    if bottom < 0 then dy = -bottom end
    if top + dy > screenHeight then dy = screenHeight - top end
    if dx == 0 and dy == 0 then return false end
    frame:ClearAllPoints()
    frame:SetPoint("BOTTOMLEFT", UIParent, "BOTTOMLEFT", (left + dx) / ratio + BORDER, (bottom + dy) / ratio + BORDER)
    return true
end

-- Register a window background; it is themed now and whenever settings change.
-- A window (not a popup) also stays on screen: clamped while dragged, and moved
-- back inside whenever it opens.
function T.attach(frame, background, popup)
    table.insert(windows, {frame=frame, background=background, popup=popup == true})
    if not popup then
        main = main or frame
        S.call(frame.SetClampedToScreen, frame, true)
        S.call(frame.SetClampRectInsets, frame, -BORDER, BORDER, BORDER, -BORDER)
        if type(frame.HookScript) == "function" then
            pcall(frame.HookScript, frame, "OnShow", function(self) keepOnScreen(self) end)
        end
    end
    T.apply()
end
-- The theme colour only, for the settings pages' own windows (opened in combat,
-- or when the game's Options cannot open): they look like the main window, but
-- keep their size, as they also sit inside Options.
function T.attachBackground(background)
    table.insert(windows, {background=background, colourOnly=true})
    T.apply()
end

-- Window scale as shown (the chosen size, or less where the screen cannot hold
-- it); for notifications, their own size times the window size when "Use the
-- theme and size for popups too" is on.
function T.scale(popup)
    local value = settings()
    if not popup then return T.applied(main) end
    local follow = math.max(T.POPUP_FOLLOW_MIN, math.min(T.POPUP_FOLLOW_MAX, value.scale))
    return (value.popups and follow or 1) * value.popup_size / 100
end
function T.popupSize() return settings().popup_size end
function T.popupSizeLabel(percent) return WoWStatusLocale.F("%d%%", percent or T.popupSize()) end
-- Sets the notification size from a percentage; false for a value out of range.
function T.setPopupSize(percent)
    percent = tonumber(percent)
    if not percent or percent ~= percent or percent < T.POPUP_MIN or percent > T.POPUP_MAX then return false end
    settings().popup_size = math.floor(percent + .5)
    T.apply()
    return true
end

-- Functions called after every change of theme, size or screen, such as the
-- Options label that shows the size.
local watchers = {}
function T.watch(fn) if type(fn) == "function" then table.insert(watchers, fn) end end

-- The date calendar and dropdown take the window's scale when they open; close
-- them when it changes rather than leave them at the old scale, away from
-- their button.
local function closePopovers()
    for _, frame in ipairs({WoWStatusUI and WoWStatusUI.calendarFrame, WoWStatusUI and WoWStatusUI.menuFrame}) do
        if frame and frame.IsShown and frame:IsShown() then frame:Hide() end
    end
end

local shownScale
function T.apply()
    local value = settings()
    for _, window in ipairs(windows) do
        if window.colourOnly then
            window.background:SetColorTexture(T.colour())
        elseif not window.popup then
            window.background:SetColorTexture(T.colour())
            window.frame:SetScale(T.applied(window.frame))
            keepOnScreen(window.frame)
        elseif value.popups then
            window.background:SetColorTexture(T.colour(.96))
        else
            window.background:SetColorTexture(.025, .035, .065, .96)
        end
    end
    local scale = main and T.applied(main)
    if shownScale and scale ~= shownScale then closePopovers() end
    shownScale = scale
    -- Boxes and section lines change only between the mood look and High
    -- contrast, not with a size step or between mood themes. An error is
    -- reported and tried again on the next apply, and never stops the rest.
    if WoWStatusUI and WoWStatusUI.restyle then
        local ok, err = pcall(WoWStatusUI.restyle, value.name == "contrast")
        if not ok and type(geterrorhandler) == "function" then geterrorhandler()(err) end
    end
    if WoWStatusPopups and WoWStatusPopups.restyle then WoWStatusPopups.restyle() end
    for _, fn in ipairs(watchers) do
        local ok, err = pcall(fn)
        if not ok and type(geterrorhandler) == "function" then geterrorhandler()(err) end
    end
end

-- True while the High contrast theme is chosen.
function T.highContrast() return settings().name == "contrast" end

function T.next()
    local value, index = settings(), 1
    for i, name in ipairs(T.ORDER) do if name == value.name then index = i end end
    value.name = T.ORDER[index % #T.ORDER + 1]
    T.apply()
    return value.name
end

-- Steps from the size shown, so stepping down from a size the screen cannot
-- hold changes the window at once instead of only the number.
function T.resize(delta)
    local value = settings()
    local base = main and math.min(value.scale, T.applied(main)) or value.scale
    value.scale = clampScale(base + (tonumber(delta) or 0))
    T.apply()
    return value.scale
end

-- The window size in whole percent, and setting it from a percentage (the
-- Options box); false for a value out of range, which keeps the old size.
function T.windowSize() return percent(settings().scale) end
function T.setWindowSize(percent)
    percent = tonumber(percent)
    if not percent or percent ~= percent or percent < T.MIN * 100 or percent > T.MAX * 100 then return false end
    settings().scale = clampScale(percent / 100)
    T.apply()
    return true
end

function T.setPopups(enabled)
    settings().popups = enabled == true
    T.apply()
end

function T.label()
    local value = settings()
    return "Theme: " .. T.NAMES[value.name] .. " · size " .. T.windowSize() .. "%"
end
-- A note for when the screen holds the main window only at a smaller size
-- than chosen; nil when it is shown at the chosen size.
function T.shownNote()
    local shown = main and percent(T.applied(main))
    if shown and shown < T.windowSize() then return "Shown at " .. shown .. "% to fit the screen" end
    return nil
end

-- A resolution or UI scale change can make the screen smaller or larger:
-- size and place the windows again for it.
if type(CreateFrame) == "function" then
    local events = CreateFrame("Frame")
    for _, event in ipairs({"DISPLAY_SIZE_CHANGED", "UI_SCALE_CHANGED"}) do
        pcall(events.RegisterEvent, events, event)
    end
    events:SetScript("OnEvent", function() T.apply() end)
end

-- Shared building blocks for the main window's pages: bordered boxes, round
-- level badges, XP bars and framed icons. Built only from textures every client
-- ships (tooltip border, minimap ring, status bar, portrait mask). A method a
-- client lacks is skipped rather than failing, so a page still draws.
WoWStatusUI = {}
local UI = WoWStatusUI
local function call(object, method, ...)
    local fn = object and object[method]
    if type(fn) == "function" then return pcall(fn, object, ...) end
    return false
end
UI.call = call
UI.XP_COLOUR = {.58, .0, .55}
UI.GOLD = {1, .82, 0}

-- A frame with the tooltip border (the look most addons use for panels).
function UI.box(parent, width, height, kind)
    local template = BackdropTemplateMixin and "BackdropTemplate" or nil
    local frame = CreateFrame(kind or "Frame", nil, parent, template)
    frame:SetSize(width, height)
    if not call(frame, "SetBackdrop", {bgFile="Interface\\Tooltips\\UI-Tooltip-Background",
        edgeFile="Interface\\Tooltips\\UI-Tooltip-Border", tile=true, tileSize=16, edgeSize=14,
        insets={left=3, right=3, top=3, bottom=3}}) then
        -- No backdrop API: a plain tinted background still separates the box.
        local bg = frame:CreateTexture(nil, "BACKGROUND"); bg:SetAllPoints(); bg:SetColorTexture(0, 0, 0, .35)
        frame.fallback = bg
    end
    UI.tint(frame)
    return frame
end
-- Box and section-line looks: the mood themes share one, High contrast has an
-- opaque black fill, a near-white border and solid lines twice as thick.
local STYLES = {
    mood = {fill=.45, fallback=.35, edge={.55, .55, .6, .8}, mark={1, .82, 0, .9}, line=.35, lineHeight=1,
        own=.12, stripe=.04},
    contrast = {fill=1, fallback=1, edge={.9, .9, .9, 1}, mark={1, .82, 0, 1}, line=1, lineHeight=2,
        own=.25, stripe=.08},
}
-- The look everything was last styled with (UI.restyle); until the first
-- restyle, the one the saved theme asks for.
local current
local function style() return current or (T.highContrast() and STYLES.contrast or STYLES.mood) end
-- Every box, section line and row stripe drawn, so a theme change can style
-- them again. Pages reuse their boxes, headers and rows, so these stay small.
local boxes, lines, stripes = {}, {}, {}
-- Box colours: dark fill, light border; gold border to highlight. Without the
-- backdrop API, the plain fallback fill takes the same strength.
function UI.tint(frame, highlighted, look)
    highlighted = highlighted and true or false
    boxes[frame] = highlighted
    look = look or style()
    call(frame, "SetBackdropColor", 0, 0, 0, look.fill)
    local edge = highlighted and look.mark or look.edge
    call(frame, "SetBackdropBorderColor", edge[1], edge[2], edge[3], edge[4])
    if frame.fallback then call(frame.fallback, "SetColorTexture", 0, 0, 0, look.fallback) end
end
local function styleLine(line, look)
    look = look or style()
    call(line, "SetColorTexture", 1, .82, 0, look.line)
    call(line, "SetHeight", look.lineHeight)
end
-- A list row's gold wash: "own" marks your own row, "stripe" every other row,
-- anything else none. Stronger on High contrast.
function UI.stripe(texture, kind, look)
    stripes[texture] = kind or false
    look = look or style()
    call(texture, "SetColorTexture", 1, .82, 0, kind == "own" and look.own or kind == "stripe" and look.stripe or 0)
end
-- Styles every box, section line and stripe for the mood look or High contrast
-- (T.apply); nothing to do when that look is already shown. The look counts
-- as shown only once everything took it, so a failure is tried again.
function UI.restyle(contrast)
    local look = contrast and STYLES.contrast or STYLES.mood
    if look == current then return end
    for frame, highlighted in pairs(boxes) do UI.tint(frame, highlighted, look) end
    for line in pairs(lines) do styleLine(line, look) end
    for texture, kind in pairs(stripes) do UI.stripe(texture, kind, look) end
    current = look
end

-- Never colour alone (#185). Secondary lines use one muted grey that keeps at
-- least 5:1 against every theme's window (the game's disabled .5 grey fell to
-- under 4:1 on Journal), and each state below carries a shape or text cue as
-- well as its colour.
UI.MUTED = 0x9d / 255
UI.MUTED_CODE = "|cff9d9d9d"
UI.ONLINE_ICON = "Interface\\FriendsFrame\\StatusIcon-Online" -- a filled dot
UI.OFFLINE_ICON = "Interface\\AddOns\\WoWStatus\\Textures\\Offline" -- a hollow ring
-- The states that once told themselves apart by colour alone, and the cue each
-- now carries besides its colour (tests/test_colour_cues.py walks every one).
UI.CUES = {
    {state="online", where="cards, leaderboard", cue="filled dot"},
    {state="offline", where="cards, leaderboard", cue="hollow ring"},
    {state="controller focus", where="every window", cue="gold outline with a dark inner outline"},
    {state="history graph first observation", where="level history graph", cue="larger square than a level-up"},
    {state="calendar today", where="date picker", cue="[brackets]"},
    {state="calendar day with entries", where="date picker", cue="bar under the day"},
    {state="calendar selected day", where="date picker", cue="lighter fill behind the day"},
}
-- An inline online/offline marker for a font string: filled when online,
-- hollow when not, so the shape tells them apart without the green.
function UI.presence(online, size)
    size = size or 12
    return "|T" .. (online and UI.ONLINE_ICON or UI.OFFLINE_ICON) .. ":" .. size .. ":" .. size .. "|t"
end
-- Gives a font string the muted secondary grey.
function UI.mute(text)
    if text and text.SetTextColor then text:SetTextColor(UI.MUTED, UI.MUTED, UI.MUTED) end
    return text
end
local DISABLED = {GameFontDisable=true, GameFontDisableSmall=true, GameFontDisableLarge=true}
-- Adds a handler after any the frame already has. SetScript would drop the
-- others (and, in the game, every HookScript hook too).
function UI.hook(frame, event, fn)
    if frame.HookScript then return frame:HookScript(event, fn) end
    local previous = frame.GetScript and frame:GetScript(event)
    frame:SetScript(event, function(...)
        if previous then previous(...) end
        fn(...)
    end)
end

function UI.text(parent, font, x, y, width, justify)
    local text = parent:CreateFontString(nil, "OVERLAY", font or "GameFontHighlight")
    text:SetPoint("TOPLEFT", x or 0, y or 0)
    if width then text:SetWidth(width) end
    text:SetJustifyH(justify or "LEFT")
    -- The game's disabled font is too dim for a secondary line; lift it.
    if DISABLED[font] then UI.mute(text) end
    return text
end

-- Lay out children of parent in one axis. Padding sets the top-left inset.
-- An explicit extent reserves space without resizing the widget.
function UI.stack(parent, options)
    options = options or {}
    local padding = options.padding or 0
    local spacing = options.spacing or 0
    local horizontal = options.horizontal
    local x = options.left or padding
    local y = options.top or padding
    local stack = {}

    function stack:add(widget, extent, inset)
        inset = inset or 0
        widget:ClearAllPoints()
        if horizontal then
            widget:SetPoint("TOPLEFT", parent, "TOPLEFT", x, -y - inset)
            x = x + (extent or widget:GetWidth()) + spacing
        else
            widget:SetPoint("TOPLEFT", parent, "TOPLEFT", x + inset, -y)
            local height = extent or (widget.GetStringHeight and widget:GetStringHeight()) or widget:GetHeight()
            y = y + height + spacing
        end
        return widget
    end

    function stack:row(height, gap)
        local row = UI.stack(parent, {horizontal = true, left = x, top = y, spacing = gap})
        y = y + height + spacing
        return row
    end

    return stack
end

-- A gold section title with a thin line under it.
function UI.header(parent, label, x, y, width)
    local title = UI.text(parent, "GameFontNormal", x, y, width)
    title:SetText(label)
    local line = parent:CreateTexture(nil, "ARTWORK")
    line:SetPoint("TOPLEFT", x, y - 16); line:SetSize(width or 300, 1)
    lines[line] = true; styleLine(line)
    title.line = line
    return title
end

-- A round level badge, styled like the minimap button ring.
function UI.levelBadge(parent, size)
    size = size or 30
    local badge = CreateFrame("Frame", nil, parent)
    badge:SetSize(size, size)
    -- Proportions of the minimap button: 32 px button, 54 px ring at its top-left,
    -- content centred one pixel left of and above the middle.
    local unit = size / 32
    badge.fill = badge:CreateTexture(nil, "BACKGROUND")
    badge.fill:SetPoint("CENTER", -unit, unit); badge.fill:SetSize(size * .72, size * .72)
    badge.fill:SetTexture("Interface\\CharacterFrame\\TempPortraitAlphaMask")
    call(badge.fill, "SetVertexColor", .08, .06, .02, .95)
    badge.ring = badge:CreateTexture(nil, "OVERLAY")
    badge.ring:SetPoint("TOPLEFT"); badge.ring:SetSize(54 * unit, 54 * unit)
    badge.ring:SetTexture("Interface\\Minimap\\MiniMap-TrackingBorder")
    badge.text = badge:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    badge.text:SetPoint("CENTER", -unit, unit)
    function badge:SetLevel(level) self.text:SetText(level and tostring(level) or "?") end
    return badge
end

-- An XP bar: purple fill on dark, with a percentage label. value is 0..1.
function UI.xpBar(parent, width, height)
    local bar = CreateFrame("StatusBar", nil, parent)
    bar:SetSize(width, height or 8)
    call(bar, "SetStatusBarTexture", "Interface\\TargetingFrame\\UI-StatusBar")
    call(bar, "SetStatusBarColor", UI.XP_COLOUR[1], UI.XP_COLOUR[2], UI.XP_COLOUR[3], 1)
    call(bar, "SetMinMaxValues", 0, 1)
    bar.bg = bar:CreateTexture(nil, "BACKGROUND"); bar.bg:SetAllPoints(); bar.bg:SetColorTexture(0, 0, 0, .6)
    bar.label = bar:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    bar.label:SetPoint("CENTER", 0, 0)
    function bar:SetProgress(value, label)
        value = type(value) == "number" and math.max(0, math.min(1, value)) or nil
        call(self, "SetValue", value or 0)
        self.progress = value
        self.label:SetText(label or (value and (math.floor(value * 100) .. "%") or ""))
        self:SetShown(value ~= nil)
    end
    return bar
end

-- A square icon with a thin dark frame.
function UI.icon(parent, size)
    local frame = CreateFrame("Frame", nil, parent)
    frame:SetSize(size, size)
    frame.border = frame:CreateTexture(nil, "BACKGROUND"); frame.border:SetAllPoints(); frame.border:SetColorTexture(0, 0, 0, .9)
    frame.texture = frame:CreateTexture(nil, "ARTWORK")
    frame.texture:SetPoint("TOPLEFT", 2, -2); frame.texture:SetPoint("BOTTOMRIGHT", -2, 2)
    call(frame.texture, "SetTexCoord", .07, .93, .07, .93)
    function frame:SetIcon(path, dimmed)
        self.texture:SetTexture(path)
        if not call(self.texture, "SetDesaturated", dimmed == true) and dimmed then
            call(self.texture, "SetVertexColor", .45, .45, .45)
        elseif not dimmed then call(self.texture, "SetVertexColor", 1, 1, 1) end
        self.path, self.dimmed = path, dimmed == true
    end
    return frame
end

-- Class colour as an escape-sequence prefix, or nil.
-- Gold with coin icons: "12g 34s 5c"; short shows only whole gold (from 1 gold).
local function coin(kind) return "|TInterface\\MoneyFrame\\UI-" .. kind .. "Icon:0:0:2:0|t" end
function UI.money(copper, short)
    copper = tonumber(copper)
    if not copper or copper < 0 then return nil end
    local g, s, c = math.floor(copper / 10000), math.floor(copper / 100) % 100, copper % 100
    if short and g > 0 then return g .. coin("Gold") end
    local parts = {}
    if g > 0 then table.insert(parts, g .. coin("Gold")) end
    if s > 0 or g > 0 then table.insert(parts, s .. coin("Silver")) end
    table.insert(parts, c .. coin("Copper"))
    return table.concat(parts, " ")
end
local function tr(text) return WoWStatusLocale.T(text) end
-- Dates as "YYYY-MM-DD" day keys, for the Activity log's day picker.
UI.MONTHS = {"January", "February", "March", "April", "May", "June", "July", "August", "September",
    "October", "November", "December"}
local WEEKDAYS = {"Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"}
function UI.daysIn(year, month)
    if month == 2 then return (year % 4 == 0 and (year % 100 ~= 0 or year % 400 == 0)) and 29 or 28 end
    return ({31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31})[month]
end
-- Weekday of a date, Monday = 1 ... Sunday = 7 (Zeller's congruence).
function UI.weekday(year, month, day)
    if month < 3 then month, year = month + 12, year - 1 end
    local k, j = year % 100, math.floor(year / 100)
    local h = (day + math.floor(13 * (month + 1) / 5) + k + math.floor(k / 4) + math.floor(j / 4) + 5 * j) % 7
    return (h + 5) % 7 + 1
end
function UI.dayKey(year, month, day) return string.format("%04d-%02d-%02d", year, month, day) end
-- "Today", "Yesterday" or "6 November" (with the year when it is not this year).
function UI.dayLabel(key, today, yesterday)
    if not key then return tr("All days") end
    if key == today then return tr("Today") end
    if key == yesterday then return tr("Yesterday") end
    local y, m, d = key:match("^(%d+)-(%d+)-(%d+)$")
    if not y then return key end
    local label = tonumber(d) .. " " .. tr(UI.MONTHS[tonumber(m)])
    if today and today:sub(1, 4) ~= y then label = label .. " " .. y end
    return label
end
-- A month calendar under owner. Days with activity (counts[key] > 0) are gold,
-- the picked day is highlighted; the arrows change month. onPick(key), or
-- onPick(nil) for all days.
function UI.calendar(owner, selected, today, counts, onPick)
    local cal = UI.calendarFrame
    if not cal then
        cal = UI.box(UIParent, 254, 252)
        -- Above the main window and its cards, which share its layer.
        cal:SetFrameStrata("TOOLTIP"); cal:EnableMouse(true)
        _G.WoWStatusCalendar = cal
        if UISpecialFrames then table.insert(UISpecialFrames, "WoWStatusCalendar") end
        cal.title = UI.text(cal, "GameFontNormal", 34, -10, 186, "CENTER")
        local function shift(step)
            cal.month = cal.month + step
            if cal.month < 1 then cal.month, cal.year = 12, cal.year - 1 end
            if cal.month > 12 then cal.month, cal.year = 1, cal.year + 1 end
            cal.render()
        end
        cal.previous = CreateFrame("Button", nil, cal, "UIPanelButtonTemplate")
        cal.previous:SetPoint("TOPLEFT", 8, -6); cal.previous:SetSize(26, 22); cal.previous:SetText("<")
        cal.previous:SetScript("OnClick", function() shift(-1) end)
        cal.next = CreateFrame("Button", nil, cal, "UIPanelButtonTemplate")
        cal.next:SetPoint("TOPLEFT", 220, -6); cal.next:SetSize(26, 22); cal.next:SetText(">")
        cal.next:SetScript("OnClick", function() shift(1) end)
        for i, name in ipairs(WEEKDAYS) do
            local label = UI.text(cal, "GameFontDisableSmall", 8 + (i - 1) * 34, -36, 32, "CENTER")
            label:SetText(tr(name))
        end
        cal.cells = {}
        for i = 1, 42 do
            local cell = UI.box(cal, 32, 24, "Button")
            cell:SetPoint("TOPLEFT", 8 + ((i - 1) % 7) * 34, -52 - math.floor((i - 1) / 7) * 26)
            cell.text = UI.text(cell, "GameFontHighlightSmall", 0, -6, 32, "CENTER")
            -- Not by colour alone (#185). A short bar under the number marks a day
            -- with entries, away from the border so a gold hover edge cannot hide
            -- it, and outside the label so a bracketed "[28]" still fits. The
            -- selected day also gets a lighter fill: brightness, not only gold.
            cell.mark = cell:CreateTexture(nil, "OVERLAY")
            cell.mark:SetSize(12, 2); cell.mark:SetPoint("BOTTOM", 0, 4)
            cell.mark:SetColorTexture(1, .82, 0, 1)
            cell.selection = cell:CreateTexture(nil, "ARTWORK")
            cell.selection:SetPoint("TOPLEFT", 2, -2); cell.selection:SetPoint("BOTTOMRIGHT", -2, 2)
            cell.selection:SetColorTexture(1, 1, 1, .2)
            cell:SetScript("OnClick", function(self) cal:Hide(); if cal.onPick then cal.onPick(self.key) end end)
            cell:SetScript("OnEnter", function(self) UI.tint(self, true) end)
            cell:SetScript("OnLeave", function(self) UI.tint(self, self.key == cal.selected) end)
            cal.cells[i] = cell
        end
        cal.today = CreateFrame("Button", nil, cal, "UIPanelButtonTemplate")
        cal.today:SetPoint("TOPLEFT", 8, -214); cal.today:SetSize(116, 26)
        cal.today:SetScript("OnClick", function() cal:Hide(); if cal.onPick then cal.onPick(cal.todayKey) end end)
        cal.all = CreateFrame("Button", nil, cal, "UIPanelButtonTemplate")
        cal.all:SetPoint("TOPLEFT", 130, -214); cal.all:SetSize(116, 26)
        cal.all:SetScript("OnClick", function() cal:Hide(); if cal.onPick then cal.onPick(nil) end end)
        function cal.render()
            cal.title:SetText(tr(UI.MONTHS[cal.month]) .. " " .. cal.year)
            local first, days = UI.weekday(cal.year, cal.month, 1), UI.daysIn(cal.year, cal.month)
            for i, cell in ipairs(cal.cells) do
                local day = i - first + 1
                if day >= 1 and day <= days then
                    local key = UI.dayKey(cal.year, cal.month, day)
                    local active, isToday = (cal.counts[key] or 0) > 0, key == cal.todayKey
                    local colour = active and "|cffffd100" or isToday and "|cffffffff" or UI.MUTED_CODE
                    cell.key = key
                    -- Not by colour alone (#185): today in brackets, a bar under a day
                    -- with entries, a lighter fill behind the selected day.
                    cell.text:SetText(colour .. (isToday and ("[" .. day .. "]") or tostring(day)) .. "|r")
                    cell.mark:SetShown(active)
                    cell.selection:SetShown(key == cal.selected)
                    UI.tint(cell, key == cal.selected)
                    cell:Show()
                else cell.key = nil; cell:Hide() end
            end
        end
        UI.calendarFrame = cal
    end
    if cal:IsShown() and cal.owner == owner then cal:Hide(); return cal end
    local start = selected or today or "2026-01-01"
    cal.year, cal.month = tonumber(start:sub(1, 4)), tonumber(start:sub(6, 7))
    cal.owner, cal.selected, cal.todayKey, cal.counts, cal.onPick = owner, selected, today, counts or {}, onPick
    cal.today:SetText(tr("Today")); cal.all:SetText(tr("All days"))
    cal.render()
    cal:ClearAllPoints(); cal:SetPoint("BOTTOMRIGHT", owner, "TOPRIGHT", 0, 4) -- Inside the window: the button is at its right edge.
    -- The window's size setting applies to the calendar too, so it lines up with the button.
    cal:SetScale(UI.ownerScale(owner))
    cal:Show()
    if cal.Raise then cal:Raise() end
    return cal
end
-- Played time: "3d 4h", "5h 12m" or "12m".
function UI.duration(seconds)
    seconds = tonumber(seconds)
    if not seconds or seconds < 0 then return nil end
    local d, h, m = math.floor(seconds / 86400), math.floor(seconds / 3600) % 24, math.floor(seconds / 60) % 60
    if d > 0 then return d .. "d " .. h .. "h" end
    if h > 0 then return h .. "h " .. m .. "m" end
    return m .. "m"
end
function UI.classColour(class)
    local colour = RAID_CLASS_COLORS and class and RAID_CLASS_COLORS[class]
    return colour and colour.colorStr and ("|c" .. colour.colorStr) or nil
end

-- A small drop-down list under a button: items {label=, value=}; onPick(value).
-- One shared list, closed by picking, by clicking its button again or by Escape.
-- Built from plain buttons, since the game's dropdown menus differ by client.
-- The scale of owner relative to UIParent: a frame parented to UIParent takes
-- it to line up with, and match the size of, a control in the main window.
function UI.ownerScale(owner)
    local own, screen = owner.GetEffectiveScale and S.number(S.call(owner.GetEffectiveScale, owner)),
        UIParent and UIParent.GetEffectiveScale and S.number(S.call(UIParent.GetEffectiveScale, UIParent))
    return own and screen and own > 0 and screen > 0 and own / screen or 1
end

-- minWidth widens the list beyond its button for longer labels.
function UI.menu(owner, items, onPick, minWidth)
    local menu = UI.menuFrame
    if not menu then
        menu = UI.box(UIParent, 200, 40)
        menu:SetFrameStrata("TOOLTIP"); menu:EnableMouse(true) -- Above the main window's cards.
        menu.scroll = CreateFrame("ScrollFrame", nil, menu, "UIPanelScrollFrameTemplate")
        menu.scroll:SetPoint("TOPLEFT", 6, -6)
        menu.list = CreateFrame("Frame", nil, menu.scroll)
        menu.scroll:SetScrollChild(menu.list)
        menu.rows = {}
        UI.menuFrame = menu
        _G.WoWStatusMenu = menu
        if UISpecialFrames then table.insert(UISpecialFrames, "WoWStatusMenu") end
    end
    if menu:IsShown() and menu.owner == owner then menu:Hide(); return menu end
    local width, rowHeight, visible = math.max(minWidth or 180, owner.GetWidth and owner:GetWidth() or 180), 22, math.min(#items, 14)
    menu:SetSize(width + (#items > 14 and 24 or 12), visible * rowHeight + 12)
    menu.scroll:SetSize(width, visible * rowHeight)
    menu.list:SetSize(width, #items * rowHeight)
    for i, item in ipairs(items) do
        local row = menu.rows[i]
        if not row then
            row = CreateFrame("Button", nil, menu.list)
            row:SetSize(width, rowHeight)
            row.highlight = row:CreateTexture(nil, "BACKGROUND"); row.highlight:SetAllPoints()
            row.highlight:SetColorTexture(1, .82, 0, .15); row.highlight:Hide()
            row.text = UI.text(row, "GameFontHighlight", 6, -4, width - 12)
            row:SetScript("OnEnter", function(self) self.highlight:Show() end)
            row:SetScript("OnLeave", function(self) self.highlight:Hide() end)
            row:SetScript("OnClick", function(self) menu:Hide(); if menu.onPick then menu.onPick(self.value) end end)
            menu.rows[i] = row
        end
        -- The list is shared: rows made for a narrower menu take this one's width.
        row:SetSize(width, rowHeight); row.text:SetWidth(width - 12)
        row:ClearAllPoints(); row:SetPoint("TOPLEFT", 0, -(i - 1) * rowHeight)
        row.text:SetText(item.label); row.value = item.value; row:Show()
    end
    for i = #items + 1, #menu.rows do menu.rows[i]:Hide() end
    menu.owner, menu.onPick, menu.items = owner, onPick, items
    menu:SetScale(UI.ownerScale(owner)) -- the window's size, like its button
    menu:ClearAllPoints(); menu:SetPoint("TOPLEFT", owner, "BOTTOMLEFT", 0, -2)
    call(menu.scroll, "SetVerticalScroll", 0)
    menu:Show()
    return menu
end

-- Keep the native settings pages, but show one short category at a time. All
-- controls retain their handlers and saved values; a hidden category's parent
-- keeps its controls out of both mouse and controller navigation.
function UI.settingsCategories(panel, definitions, initial)
    local layout = {panel=panel, definitions=definitions, selected=initial, frames={}, heights={}}
    UI.text(panel, "GameFontNormal", 24, -158, 180):SetText(WoWStatusLocale.T("Settings category:"))
    layout.pick = CreateFrame("Button", nil, panel, "UIPanelButtonTemplate")
    layout.pick:SetPoint("TOPLEFT", 210, -152); layout.pick:SetSize(350, 30)
    function layout:select(id)
        for _, item in ipairs(self.definitions) do
            if item.value == id then
                self.selected = id
                self:render()
                UI.call(self.panel:GetParent(), "SetVerticalScroll", 0)
                return true
            end
        end
        return false
    end
    layout.pick:SetScript("OnClick", function(owner)
        local choices = {}
        for _, item in ipairs(definitions) do
            choices[#choices+1] = {value=item.value, label=WoWStatusLocale.T(item.label)}
        end
        UI.menu(owner, choices, function(id) layout:select(id) end, 350)
    end)
    function layout:category(id, originalTop, relativeTop)
        if not self.frames[id] then
            local frame = CreateFrame("Frame", nil, self.panel)
            frame:SetPoint("TOPLEFT", 0, -204); frame:SetSize(600, 40)
            self.frames[id], self.heights[id] = frame, 40
        end
        self.active, self.origin, self.offset = id, originalTop, relativeTop or 0
    end
    function layout:parent() return self.active and self.frames[self.active] or self.panel end
    function layout:place(widget, x, y, height)
        if not self.active then return widget end
        local localY = y + self.origin - self.offset
        widget:ClearAllPoints(); widget:SetPoint("TOPLEFT", x, localY)
        self.heights[self.active] = math.max(self.heights[self.active], -localY + (height or 40))
        return widget
    end
    function layout:adopt(widget, x, y, height)
        widget:SetParent(self:parent())
        return self:place(widget, x, y, height)
    end
    function layout:render()
        for id, frame in pairs(self.frames) do
            frame:SetHeight(self.heights[id]); frame:SetShown(id == self.selected)
        end
        for _, item in ipairs(self.definitions) do
            if item.value == self.selected then self.pick:SetText(WoWStatusLocale.T(item.label) .. " ▾") end
        end
        local bottom = 204 + (self.heights[self.selected] or 40)
        self.panel:SetHeight(bottom + 72)
        if self.panel.close then
            self.panel.close:ClearAllPoints(); self.panel.close:SetPoint("TOPLEFT", 424, -bottom-20)
        end
    end
    function layout:finish() self.active=nil; self:render() end
    return layout
end
