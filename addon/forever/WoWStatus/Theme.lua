-- Window themes and size (#60), saved account-wide in WoWStatusDB.theme and
-- applied immediately, without /reload. Themes only change background tint
-- (plain colour textures, no extra files), so the white and gold game fonts
-- stay readable on every theme. Night is the original look.
WoWStatusTheme = {}
local T, S = WoWStatusTheme, WoWStatusSafe
T.ORDER = {"night", "journal", "faction"}
T.NAMES = {night="Night", journal="Journal", faction="Faction"}
T.MIN, T.MAX, T.STEP = .8, 1.2, .1
local windows = {}

local function settings()
    if type(WoWStatusDB) ~= "table" then return {name="night", scale=1, popups=false} end
    local value = type(WoWStatusDB.theme) == "table" and WoWStatusDB.theme or {}
    WoWStatusDB.theme = value
    if not T.NAMES[value.name] then value.name = "night" end
    local scale = S.number(value.scale)
    value.scale = scale and math.max(T.MIN, math.min(T.MAX, math.floor(scale * 10 + .5) / 10)) or 1
    value.popups = value.popups == true
    return value
end
T.settings = settings

-- Background colour {r, g, b, a} for the chosen theme.
function T.colour(alpha)
    local name = settings().name
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

function T.scale(popup)
    local value = settings()
    if popup and not value.popups then return 1 end
    return value.scale
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
