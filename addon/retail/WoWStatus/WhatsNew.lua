-- One-time "What's New" page after an update (#63). Account-wide: the last
-- version shown is stored in WoWStatusDB.whats_new_seen. A fresh install marks
-- the current version as seen, so only the setup guide appears then.
-- Notes come from WhatsNewData.lua, generated from CHANGELOG.md.
WoWStatusWhatsNew = {}
local W = WoWStatusWhatsNew
local panel

local function parts(version)
    local a, b, c = tostring(version or ""):match("^(%d+)%.(%d+)%.(%d+)$")
    if a then return {tonumber(a), tonumber(b), tonumber(c)} end
end
-- True when version a is newer than version b. Unreadable versions are never newer.
function W.newer(a, b)
    a, b = parts(a), parts(b)
    if not a then return false end
    if not b then return true end
    for i = 1, 3 do
        if a[i] ~= b[i] then return a[i] > b[i] end
    end
    return false
end

local function entries() return type(WoWStatusWhatsNewData) == "table" and WoWStatusWhatsNewData or {} end

function W.current()
    local version = WoWStatusPopups and WoWStatusPopups.runtimeVersion
    if parts(version) then return version end
    local latest = entries()[1]
    return latest and latest.version
end

-- Sections newer than `since` up to the running version; the newest section alone
-- when `since` is unknown (an update from a build before this page existed).
function W.sections(since)
    local current, found = W.current(), {}
    for _, entry in ipairs(entries()) do
        if not W.newer(entry.version, current) and (since == nil and #found == 0 or since and W.newer(entry.version, since)) then
            table.insert(found, entry)
        end
    end
    return found
end

function W.text(sections)
    local lines = {}
    for _, entry in ipairs(sections) do
        if #lines > 0 then table.insert(lines, " ") end
        table.insert(lines, "|cffffd100Version " .. entry.version .. "|r")
        for _, note in ipairs(entry.notes or {}) do table.insert(lines, "• " .. note) end
    end
    if #lines == 0 then return "No release notes for this version." end
    return table.concat(lines, "\n")
end

function W.show(sections)
    sections = sections or W.sections(nil)
    if not panel then
        panel = CreateFrame("Frame", "WoWStatusWhatsNewFrame", UIParent)
        panel:SetSize(560, 420); panel:SetPoint("CENTER"); panel:SetFrameStrata("DIALOG")
        panel:EnableMouse(true); panel:SetMovable(true); panel:RegisterForDrag("LeftButton")
        panel:SetScript("OnDragStart", panel.StartMoving); panel:SetScript("OnDragStop", panel.StopMovingOrSizing)
        local background = panel:CreateTexture(nil, "BACKGROUND")
        background:SetAllPoints(); background:SetColorTexture(.025, .035, .065, .97)
        panel.title = panel:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
        panel.title:SetPoint("TOPLEFT", 24, -20); panel.title:SetText("What's new in WoW Status")
        panel.body = panel:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
        panel.body:SetPoint("TOPLEFT", 24, -60); panel.body:SetWidth(512); panel.body:SetHeight(300)
        panel.body:SetJustifyH("LEFT"); panel.body:SetJustifyV("TOP"); panel.body:SetWordWrap(true)
        local close = CreateFrame("Button", nil, panel, "UIPanelButtonTemplate")
        close:SetPoint("BOTTOMRIGHT", -24, 18); close:SetSize(130, 28); close:SetText("Close")
        close:SetScript("OnClick", function() panel:Hide() end)
        table.insert(UISpecialFrames, "WoWStatusWhatsNewFrame")
    end
    panel.body:SetText(W.text(sections))
    panel:Show()
    return panel
end

-- A brand-new saved-variables table: nothing to announce.
function W.fresh(db)
    db.whats_new_seen = W.current()
end

-- At login: show the notes once when the running version is newer than the last seen.
function W.check(db)
    local current = W.current()
    if not current then return false end
    local seen = db.whats_new_seen
    if seen ~= nil and not W.newer(current, seen) then return false end
    db.whats_new_seen = current
    local sections = W.sections(parts(seen) and seen or nil)
    if #sections == 0 then return false end
    W.show(sections)
    return true
end
