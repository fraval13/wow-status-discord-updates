-- Window themes and size (#60), saved account-wide in WoWStatusDB.theme and
-- applied immediately, without /reload. Themes only change background tint
-- (plain colour textures, no extra files), so the white and gold game fonts
-- stay readable on every theme. Night is the original look.
WoWStatusTheme = {}
local T, S = WoWStatusTheme, WoWStatusSafe
-- Achievement, the default since 1.15, is a solid dark brown like Retail's
-- achievement window, drawn with plain colour so every client shows it.
T.ORDER = {"achievement", "night", "journal", "faction"}
T.NAMES = {achievement="Achievement", night="Night", journal="Journal", faction="Faction"}
T.MIN, T.MAX, T.STEP = .8, 1.2, .1
-- Notification size in percent, separate from the window size.
T.POPUP_MIN, T.POPUP_MAX, T.POPUP_DEFAULT = 50, 200, 100
local windows = {}

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
    value.scale = scale and math.max(T.MIN, math.min(T.MAX, math.floor(scale * 10 + .5) / 10)) or 1
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
    if name == "achievement" then return .16, .1, .045, alpha and math.max(alpha, .98) or 1 end -- solid dark brown
    if name == "journal" then return .2, .14, .07, alpha or .97 end   -- warm parchment brown
    if name == "faction" then
        local faction = S.stringCall(UnitFactionGroup, "player")
        if faction == "Horde" then return .24, .04, .03, alpha or .97 end
        return .03, .08, .24, alpha or .97                            -- Alliance blue
    end
    return .025, .035, .065, alpha or .98
end

-- Register a window background; it is themed now and whenever settings change.
function T.attach(frame, background, popup)
    table.insert(windows, {frame=frame, background=background, popup=popup == true})
    T.apply()
end

-- Window scale; for notifications, their own size times the window size when
-- "Use the theme and size for popups too" is on.
function T.scale(popup)
    local value = settings()
    if not popup then return value.scale end
    return (value.popups and value.scale or 1) * value.popup_size / 100
end
function T.popupSize() return settings().popup_size end
-- Sets the notification size from a percentage; false for a value out of range.
function T.setPopupSize(percent)
    percent = tonumber(percent)
    if not percent or percent ~= percent or percent < T.POPUP_MIN or percent > T.POPUP_MAX then return false end
    settings().popup_size = math.floor(percent + .5)
    T.apply()
    return true
end

function T.apply()
    local value = settings()
    for _, window in ipairs(windows) do
        if not window.popup then
            window.background:SetColorTexture(T.colour())
            window.frame:SetScale(value.scale)
        elseif value.popups then
            window.background:SetColorTexture(T.colour(.96))
        else
            window.background:SetColorTexture(.025, .035, .065, .96)
        end
    end
    if WoWStatusPopups and WoWStatusPopups.restyle then WoWStatusPopups.restyle() end
end

function T.next()
    local value, index = settings(), 1
    for i, name in ipairs(T.ORDER) do if name == value.name then index = i end end
    value.name = T.ORDER[index % #T.ORDER + 1]
    T.apply()
    return value.name
end

function T.resize(delta)
    local value = settings()
    value.scale = math.max(T.MIN, math.min(T.MAX, math.floor((value.scale + delta) * 10 + .5) / 10))
    T.apply()
    return value.scale
end

function T.setPopups(enabled)
    settings().popups = enabled == true
    T.apply()
end

function T.label()
    local value = settings()
    return "Theme: " .. T.NAMES[value.name] .. " · size " .. math.floor(value.scale * 100 + .5) .. "%"
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
-- Box colours: dark fill, grey border; gold border to highlight.
function UI.tint(frame, highlighted)
    call(frame, "SetBackdropColor", 0, 0, 0, .45)
    if highlighted then call(frame, "SetBackdropBorderColor", 1, .82, 0, .9)
    else call(frame, "SetBackdropBorderColor", .55, .55, .6, .8) end
end

function UI.text(parent, font, x, y, width, justify)
    local text = parent:CreateFontString(nil, "OVERLAY", font or "GameFontHighlight")
    text:SetPoint("TOPLEFT", x or 0, y or 0)
    if width then text:SetWidth(width) end
    text:SetJustifyH(justify or "LEFT")
    return text
end

-- A gold section title with a thin line under it.
function UI.header(parent, label, x, y, width)
    local title = UI.text(parent, "GameFontNormal", x, y, width)
    title:SetText(label)
    local line = parent:CreateTexture(nil, "ARTWORK")
    line:SetPoint("TOPLEFT", x, y - 16); line:SetSize(width or 300, 1); line:SetColorTexture(1, .82, 0, .35)
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
function UI.classColour(class)
    local colour = RAID_CLASS_COLORS and class and RAID_CLASS_COLORS[class]
    return colour and colour.colorStr and ("|c" .. colour.colorStr) or nil
end
