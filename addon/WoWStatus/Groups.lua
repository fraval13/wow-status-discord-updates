-- Per-character routing list. A group ID opts in to one destination, never all destinations.
WoWStatusGroups = {}
local G = WoWStatusGroups
local getCharacter, database, report, panel
local MAX_GROUPS = 8

function G.valid(id)
    return type(id) == "string" and #id == 22 and id:match("^[a-f0-9]+$") ~= nil
end
function G.key(text)
    text = text:match("^%s*(.-)%s*$")
    local _, characters = text:gsub("[^\128-\191]", "")
    if text == "" or characters > 80 or text:find("[%c]") then return nil end
    local a, b, c = 5381, 2166136261, 104729
    for i = 1, #text do
        local byte = text:byte(i)
        a = (a * 33 + byte) % 4294967296
        b = (b * 65599 + byte) % 4294967296
        c = (c * 131 + byte) % 4294967296
    end
    return string.format("%08x%08x%06x", a, b, c % 16777216), text
end
function G.channel(id) return "WStatus" .. id end
function G.selected(character)
    return character and character.group_ids or {}
end
function G.contains(character, id)
    return character and character.group_ids and character.group_ids[id] ~= nil
end
function G.init(db, getter, reporter)
    database, getCharacter, report = db, getter, reporter
    local character = getter()
    -- The new flow requires explicit group selection. Old /link deployments remain opt-in legacy.
    character.group_ids = character.group_ids or {}
end
local function update(text, playerName)
    local character, selected, count = getCharacter(), {}, 0
    for label in text:gmatch("[^\r\n]+") do
        local id, cleaned = G.key(label)
        if not id then return false, "Use a non-empty group name of up to 80 characters, one per line." end
        if selected[id] and selected[id].label ~= cleaned then
            return false, "These group names collide; choose a different name."
        end
        if not selected[id] then
            count = count + 1
            if count > MAX_GROUPS then return false, "Choose at most 8 group IDs." end
            selected[id] = character.group_ids[id] or {joined_at = time(), label = cleaned}
            selected[id].label = cleaned
            if not character.group_ids[id] and character.settings.enabled
                and character.settings.fields.level and character.settings.collection.level then
                selected[id].baseline_level = UnitLevel("player")
            end
        end
    end
    playerName = playerName:match("^%s*(.-)%s*$")
    if #playerName > 40 or playerName:find("[%c|]") then return false, "Use a name of up to 40 characters." end
    character.group_ids = selected
    character.legacy_upload = false
    database.player_name = playerName
    character.player_name = playerName
    character.exported_at = time()
    if WoWStatusPopups then WoWStatusPopups.groupsChanged() end
    return true, "Group list saved for this character. /reload exports it. Removed groups stop receiving new data."
end
G.update = update
function G.text(character, multiline)
    local ids = {}
    for id, member in pairs(G.selected(character)) do table.insert(ids, member.label or id) end
    table.sort(ids)
    return table.concat(ids, multiline and "\n" or ", ")
end
function G.show()
    if not panel then
        panel = CreateFrame("Frame", "WoWStatusGroupWindow", UIParent)
        panel:SetSize(620, 430)
        panel:SetPoint("CENTER")
        panel:SetFrameStrata("DIALOG")
        panel:EnableMouse(true)
        local bg = panel:CreateTexture(nil, "BACKGROUND")
        bg:SetAllPoints(); bg:SetColorTexture(.04, .04, .07, .98)
        local function label(text, y)
            local f = panel:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
            f:SetPoint("TOPLEFT", 24, y); f:SetWidth(570); f:SetJustifyH("LEFT"); f:SetText(text)
            return f
        end
        label("Your groups — current character", -20)
        label("Your name (shared with the selected groups; optional)", -55)
        panel.name = CreateFrame("EditBox", nil, panel, "InputBoxTemplate")
        panel.name:SetPoint("TOPLEFT", 28, -80); panel.name:SetSize(550, 28)
        panel.name:SetAutoFocus(false); panel.name:SetMaxLetters(40)
        label("Group IDs: one per line. Spaces, punctuation and Unicode names are supported.", -126)
        panel.idScroll = CreateFrame("ScrollFrame", nil, panel, "UIPanelScrollFrameTemplate")
        panel.idScroll:SetPoint("TOPLEFT", 28, -150); panel.idScroll:SetSize(530, 96)
        panel.ids = CreateFrame("EditBox", nil, panel.idScroll, "InputBoxTemplate")
        panel.ids:SetSize(500, 96)
        panel.idScroll:SetScrollChild(panel.ids)
        panel.ids:SetMultiLine(true)
        panel.ids:SetAutoFocus(false); panel.ids:SetMaxLetters(650)
        panel.ids:SetScript("OnEnterPressed", function(self) self:Insert("\n") end)
        panel.ids:SetScript("OnTextChanged", function(self)
            local lines = 1
            for line in (self:GetText() .. "\n"):gmatch("(.-)\n") do
                lines = lines + math.max(1, math.ceil(#line / 30))
            end
            self:SetHeight(math.max(96, lines * 18 + 12))
        end)
        label("Only selected groups receive this character's updates. New groups get current\n"
            .. "status and future events, not your earlier log. Knowing an ID permits joining.\n"
            .. "The companion needs the shared service address once; no Discord /link code.\n"
            .. "Popup channels use the same IDs; chat delivery still needs home validation.", -264)
        local save = CreateFrame("Button", nil, panel, "UIPanelButtonTemplate")
        save:SetPoint("TOPLEFT", 24, -380); save:SetSize(160, 26); save:SetText("Save group list")
        save:SetScript("OnClick", function()
            local ok, message = update(panel.ids:GetText(), panel.name:GetText())
            report(message)
            if ok then panel:Hide() end
        end)
        local close = CreateFrame("Button", nil, panel, "UIPanelButtonTemplate")
        close:SetPoint("TOPLEFT", 456, -380); close:SetSize(120, 26); close:SetText("Close")
        close:SetScript("OnClick", function() panel:Hide() end)
        table.insert(UISpecialFrames, "WoWStatusGroupWindow")
    end
    panel.name:SetText(database.player_name or "")
    panel.ids:SetText(G.text(getCharacter(), true))
    panel:Show()
end
