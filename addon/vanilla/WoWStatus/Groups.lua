-- Account-wide group choices, with per-character join times and history boundaries.
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
    local canonical = WoWStatusCaseFold(text)
    for i = 1, #canonical do
        local byte = canonical:byte(i)
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
local function apply(character, force)
    if character.legacy_upload and not force then return end
    local previous, selected = character.group_ids or {}, {}
    for id, label in pairs(database.account_groups) do
        selected[id] = previous[id] or {joined_at = time(), label = label}
        selected[id].label = label
        if not previous[id] and character.settings.enabled
            and character.settings.fields.level and character.settings.collection.level then
            selected[id].baseline_level = character == getCharacter() and WoWStatusAdapter.level()
                or (character.snapshot and character.snapshot.level)
        end
    end
    character.group_ids = selected
    character.legacy_upload = false
    character.player_name = database.player_name or ""
    character.exported_at = time()
end
function G.init(db, getter, reporter)
    database, getCharacter, report = db, getter, reporter
    if not database.account_groups then
        -- Preserve existing selections, merging old character lists deterministically.
        database.account_groups = {}
        local keys, count = {}, 0
        for key in pairs(database.characters) do table.insert(keys, key) end
        table.sort(keys)
        for _, key in ipairs(keys) do
            local old = database.characters[key].group_ids or {}
            local ids = {}
            for id in pairs(old) do table.insert(ids, id) end
            table.sort(ids)
            for _, id in ipairs(ids) do
                local member = old[id]
                if not database.account_groups[id] then
                    if count < MAX_GROUPS then
                        database.account_groups[id] = member.label
                        count = count + 1
                    else
                        report("More than 8 old groups found. Review your account group list.")
                    end
                end
            end
        end
    end
    for _, character in pairs(database.characters) do apply(character) end
end
local function update(text, playerName)
    local selected, count = {}, 0
    for label in text:gmatch("[^\r\n]+") do
        local id, cleaned = G.key(label)
        if not id then return false, "Use a non-empty group name of up to 80 characters, one per line." end
        if selected[id] and WoWStatusCaseFold(selected[id].label) ~= WoWStatusCaseFold(cleaned) then
            return false, "These group names collide; choose a different name."
        end
        if not selected[id] then
            count = count + 1
            if count > MAX_GROUPS then return false, "Choose at most 8 group IDs." end
            selected[id] = {label = cleaned}
        end
    end
    playerName = playerName:match("^%s*(.-)%s*$")
    if #playerName > 40 or playerName:find("[%c|]") then return false, "Use a name of up to 40 characters." end
    database.account_groups = {}
    for id, member in pairs(selected) do database.account_groups[id] = member.label end
    database.player_name = playerName
    for _, saved in pairs(database.characters) do apply(saved, true) end
    if WoWStatusPopups then WoWStatusPopups.groupsChanged() end
    return true, "Group list saved for all characters on this account. /reload exports it. Removed groups stop receiving new data."
end
G.update = update
function G.text(character, multiline)
    local ids = {}
    for id, member in pairs(G.selected(character)) do table.insert(ids, member.label or id) end
    table.sort(ids)
    return table.concat(ids, multiline and "\n" or ", ")
end
function G.show(host)
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
        label("Your groups — all characters on this account", -20)
        label("Your name (shared with the selected groups; optional)", -55)
        panel.name = CreateFrame("EditBox", nil, panel, "InputBoxTemplate")
        panel.name:SetPoint("TOPLEFT", 28, -80); panel.name:SetSize(550, 28)
        panel.name:SetAutoFocus(false); panel.name:SetMaxLetters(40)
        label("Group IDs: one per line. Spaces, punctuation and Unicode names are supported.", -126)
        panel.idScroll = CreateFrame("ScrollFrame", nil, panel, "UIPanelScrollFrameTemplate")
        panel.idScroll:SetPoint("TOPLEFT", 28, -150); panel.idScroll:SetSize(530, 96)
        local inputBackground = panel.idScroll:CreateTexture(nil, "BACKGROUND")
        inputBackground:SetAllPoints()
        inputBackground:SetColorTexture(.10, .10, .13, 1)
        panel.ids = CreateFrame("EditBox", nil, panel.idScroll)
        panel.ids:SetFontObject("ChatFontNormal")
        panel.ids:SetTextInsets(8, 8, 8, 8)
        panel.ids:SetSize(530, 96)
        panel.idScroll:SetScrollChild(panel.ids)
        panel.ids:SetMultiLine(true)
        panel.ids:SetScript("OnEscapePressed", function(self) self:ClearFocus() end)
        panel.ids:SetScript("OnCursorChanged", function(self, x, y, width, height)
            local scroll = panel.idScroll:GetVerticalScroll()
            local top = math.max(0, -y)
            if top < scroll then panel.idScroll:SetVerticalScroll(top)
            elseif top + height > scroll + 96 then
                panel.idScroll:SetVerticalScroll(top + height - 96)
            end
        end)
        panel.ids:SetAutoFocus(false); panel.ids:SetMaxLetters(650)
        panel.ids:SetScript("OnEnterPressed", function(self) self:Insert("\n") end)
        panel.ids:SetScript("OnTextChanged", function(self)
            local lines = 1
            for line in (self:GetText() .. "\n"):gmatch("(.-)\n") do
                lines = lines + math.max(1, math.ceil(#line / 30))
            end
            self:SetHeight(math.max(96, lines * 18 + 12))
        end)
        label("Selected groups apply to every character on this account. New groups get current\n"
            .. "status and future events, not your earlier log. Knowing an ID permits joining.\n"
            .. "The companion needs the shared service address once; no Discord /link code.\n"
            .. "Popup channels use the same IDs; chat delivery still needs home validation.", -264)
        panel.status = label("", -340)
        local save = CreateFrame("Button", nil, panel, "UIPanelButtonTemplate")
        save:SetPoint("TOPLEFT", 24, -380); save:SetSize(160, 26); save:SetText("Save group list")
        save:SetScript("OnClick", function()
            local ok, message = update(panel.ids:GetText(), panel.name:GetText())
            panel.status:SetText(message)
            report(message)
            if ok and panel:GetParent() == UIParent then panel:Hide() end
        end)
        local close = CreateFrame("Button", nil, panel, "UIPanelButtonTemplate")
        close:SetPoint("TOPLEFT", 456, -380); close:SetSize(120, 26); close:SetText("Close")
        close:SetScript("OnClick", function() panel:Hide() end)
        panel.close = close
    end
    for i = #UISpecialFrames, 1, -1 do
        if UISpecialFrames[i] == "WoWStatusGroupWindow" then table.remove(UISpecialFrames, i) end
    end
    if not host then table.insert(UISpecialFrames, "WoWStatusGroupWindow") end
    panel.close:SetShown(not host)
    panel:SetScale(1)
    panel:SetParent(host or UIParent)
    panel:ClearAllPoints()
    panel:SetPoint(host and "TOPLEFT" or "CENTER")
    panel:SetFrameStrata(host and host:GetFrameStrata() or "FULLSCREEN_DIALOG")
    if host then panel:SetFrameLevel(host:GetFrameLevel() + 1) end
    if not host and WoWStatusSetup then WoWStatusSetup:Hide() end
    panel:SetMovable(not host)
    panel:RegisterForDrag("LeftButton")
    if host then panel:SetScript("OnDragStart", nil)
    else panel:SetScript("OnDragStart", panel.StartMoving) end
    panel:SetScript("OnDragStop", panel.StopMovingOrSizing)
    panel.status:SetText("")
    panel.idScroll:SetVerticalScroll(0)
    panel.name:SetText(database.player_name or "")
    panel.ids:SetText(G.text(getCharacter(), true))
    panel:Show()
end
