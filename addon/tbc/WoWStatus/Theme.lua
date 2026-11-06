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
-- The theme colour only, for the settings pages' own windows (opened in combat,
-- or when the game's Options cannot open): they look like the main window, but
-- keep their size, as they also sit inside Options.
function T.attachBackground(background)
    table.insert(windows, {background=background, colourOnly=true})
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
        if window.colourOnly then
            window.background:SetColorTexture(T.colour())
        elseif not window.popup then
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
        cal:SetFrameStrata("FULLSCREEN_DIALOG"); cal:EnableMouse(true)
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
                    local colour = (cal.counts[key] or 0) > 0 and "|cffffd100" or key == cal.todayKey and "|cffffffff" or "|cff808080"
                    cell.key = key
                    cell.text:SetText(colour .. day .. "|r")
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
    cal:Show()
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
function UI.menu(owner, items, onPick)
    local menu = UI.menuFrame
    if not menu then
        menu = UI.box(UIParent, 200, 40)
        menu:SetFrameStrata("FULLSCREEN_DIALOG"); menu:EnableMouse(true)
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
    local width, rowHeight, visible = math.max(180, owner.GetWidth and owner:GetWidth() or 180), 22, math.min(#items, 14)
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
        row:ClearAllPoints(); row:SetPoint("TOPLEFT", 0, -(i - 1) * rowHeight)
        row.text:SetText(item.label); row.value = item.value; row:Show()
    end
    for i = #items + 1, #menu.rows do menu.rows[i]:Hide() end
    menu.owner, menu.onPick, menu.items = owner, onPick, items
    menu:ClearAllPoints(); menu:SetPoint("TOPLEFT", owner, "BOTTOMLEFT", 0, -2)
    call(menu.scroll, "SetVerticalScroll", 0)
    menu:Show()
    return menu
end
