local ADDON = ...
local A = WoWStatusAdapter
local current, panel
local fields = {"level", "class", "race", "faction", "guild", "gear", "zone", "playtime", "professions"}
local kinds = {"introduction", "level", "loot", "equipment", "death", "zone", "session", "lfg"}
local equipmentBaseline = {}
local playtime
local frame = CreateFrame("Frame")
local refresh

local function say(message)
    DEFAULT_CHAT_FRAME:AddMessage("|cff66ccffWoW Status:|r " .. message)
end

local function defaults()
    return {
        enabled = false, introduction_confirmed = false, character_role = "alt",
        fields = {level = true, class = true, race = true, faction = true, guild = false,
                  gear = false, zone = false, playtime = false, professions = false},
        collection = {introduction = true, level = true, loot = true, equipment = false,
                      death = false, zone = false, session = false, lfg = false},
        announcements = {introduction = true, level = true, loot = true,
                         equipment = false, death = false, zone = false, session = false, lfg = false},
        loot_quality = 4, level_interval = 10,
    }
end

local function snapshot()
    if not current then return end
    current.exported_at = time()
    current.snapshot = current.settings.enabled and A.snapshot(current.settings.fields) or {}
    if current.settings.enabled and current.settings.fields.professions then
        current.snapshot.professions = current.professions or {}
    end
    if current.settings.enabled and current.settings.fields.playtime and playtime then
        current.snapshot.playtime = playtime
    end
end

local function queue(kind, data, fixed)
    if not current or not current.settings.enabled or not current.settings.collection[kind] then
        return
    end
    if kind == "introduction" and not current.settings.introduction_confirmed then return end
    current.sequence = (current.sequence or 0) + 1
    local id = fixed or (current.identity.guid .. ":" .. current.epoch .. ":" .. current.sequence)
    for _, event in ipairs(current.events) do if event.id == id then return end end
    if #current.events >= 500 then
        table.remove(current.events, 1)
        if not current.warned then
            say("Export buffer is full. Oldest events are being removed. Run your companion regularly.")
            current.warned = true
        end
    end
    table.insert(current.events, {id = id, kind = kind, at = time(), data = data or {}})
    snapshot()
end

local function introductionText()
    local s = current.settings.enabled and A.snapshot(current.settings.fields) or {}
    local text = "A new adventurer joins the tracker: " .. current.identity.name
    if s.level then text = text .. " — level " .. s.level end
    if s.race then text = text .. " " .. s.race end
    if s.class then text = text .. " " .. s.class end
    return text .. " on " .. current.identity.realm .. "!"
end

local function scrub()
    -- Remove data immediately when privacy choices change, before any disk export.
    local retained = {}
    for _, event in ipairs(current.events) do
        local allowed = current.settings.enabled and current.settings.collection[event.kind]
        if event.kind == "level" and not current.settings.fields.level then allowed = false end
        if event.kind == "zone" and not current.settings.fields.zone then allowed = false end
        if event.kind == "equipment" and not current.settings.fields.gear then allowed = false end
        if event.kind == "introduction" and not current.settings.introduction_confirmed then
            allowed = false
        end
        if allowed then table.insert(retained, event) end
    end
    current.events = retained
    if not current.settings.fields.playtime then playtime = nil end
    if not current.settings.fields.professions then current.professions = nil end
    snapshot()
end

local function button(parent, text, x, y, width, fn)
    local b = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
    b:SetPoint("TOPLEFT", x, y)
    b:SetSize(width, 26)
    b:SetText(text)
    b:SetScript("OnClick", fn)
    return b
end

local function label(parent, text, x, y, width)
    local t = parent:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    t:SetPoint("TOPLEFT", x, y)
    t:SetWidth(width or 560)
    t:SetJustifyH("LEFT")
    t:SetText(text)
    return t
end

local function showPanel()
    if not current then say("Character is not ready."); return end
    if not panel then
        panel = CreateFrame("Frame", "WoWStatusSetup", UIParent)
        panel:SetSize(900, 650)
        panel:SetPoint("CENTER")
        panel:SetFrameStrata("DIALOG")
        panel:EnableMouse(true)
        panel:SetMovable(true)
        panel:RegisterForDrag("LeftButton")
        panel:SetScript("OnDragStart", panel.StartMoving)
        panel:SetScript("OnDragStop", panel.StopMovingOrSizing)
        local bg = panel:CreateTexture(nil, "BACKGROUND")
        bg:SetAllPoints()
        bg:SetColorTexture(0.04, 0.04, 0.07, 0.98)
        label(panel, "WoW Status — character sharing", 24, -20)
        label(panel, "Export happens on /reload or logout. Run the companion to upload.\n"
            .. "Name, realm, client and character GUID are required when enrolled.\n"
            .. "Existing characters are introduced as joining the tracker.\n"
            .. "Chat messages already delivered remain after data deletion.", 24, -48)
        panel.checks = {}
        local function checkbox(key, title, x, y, group)
            local check = CreateFrame("CheckButton", nil, panel, "UICheckButtonTemplate")
            check:SetPoint("TOPLEFT", x, y)
            label(check, title, 34, -8, 230)
            check:SetScript("OnClick", function(self)
                local target = group and current.settings[group] or current.settings
                target[key] = self:GetChecked() and true or false
                if key == "enabled" and target[key] then current.enrolled = true end
                if key == "enabled" and not target[key] then
                    current.settings.introduction_confirmed = false
                end
                if key == "playtime" and target[key] and current.settings.enabled then
                    RequestTimePlayed()
                end
                scrub()
                refresh()
            end)
            table.insert(panel.checks, {widget = check, key = key, group = group})
        end
        checkbox("enabled", "Share this character (opt in)", 24, -128)
        button(panel, "Mark as my main", 600, -128, 180, function()
            for _, character in pairs(WoWStatusDB.characters) do
                character.settings.character_role = "alt"
                character.exported_at = time()
            end
            current.settings.character_role = "main"
            snapshot()
            refresh()
            say("Main selected locally. Export and upload; Discord /main takes priority if set.")
        end)
        label(panel, "Profile fields", 24, -172, 250)
        label(panel, "Store events / daily recap", 300, -172, 280)
        label(panel, "Immediate announcements", 600, -172, 280)
        for i, key in ipairs(fields) do checkbox(key, key, 24, -190 - (i - 1) * 30, "fields") end
        for i, key in ipairs(kinds) do
            checkbox(key, key, 300, -190 - (i - 1) * 30, "collection")
            checkbox(key, key, 600, -190 - (i - 1) * 30, "announcements")
        end
        panel.preview = label(panel, "", 24, -470, 850)
        button(panel, "Confirm introduction", 24, -514, 180, function()
            if not current.settings.enabled then say("Enable sharing first."); return end
            if not current.settings.collection.introduction then
                say("Enable introduction storage first."); return
            end
            current.settings.introduction_confirmed = true
            queue("introduction", {}, "introduction:" .. current.identity.guid)
            refresh()
            say("Introduction queued. Use /reload, then run the companion.")
        end)
        button(panel, "Pause sharing", 220, -514, 160, function()
            current.settings.enabled = false
            current.settings.introduction_confirmed = false
            scrub()
            refresh()
            say("Paused locally. /reload and upload to apply remotely, or use /privacy in Discord now.")
        end)
        button(panel, "Close", 480, -600, 110, function() panel:Hide() end)
        label(panel, "Filters: /wstatus interval 10   /wstatus quality 4\n"
            .. "Test: /wstatus test    LFG: /wstatus lfg <your message>\n"
            .. "Server data removal: /privacy in Discord. Pausing takes effect on upload.\n"
            .. "Enabled data is retained until deletion. Posting filters do not limit stored events.", 24, -550)
        table.insert(UISpecialFrames, "WoWStatusSetup")
    end
    refresh()
    panel:Show()
end

refresh = function()
    if not panel then return end
    for _, entry in ipairs(panel.checks) do
        local target = entry.group and current.settings[entry.group] or current.settings
        entry.widget:SetChecked(target[entry.key])
    end
    panel.preview:SetText("Character role: " .. (current.settings.character_role or "alt") .. " | Introduction: " .. introductionText()
        .. (current.settings.introduction_confirmed and "\nConfirmed." or "\nNot confirmed."))
end

local function initialize()
    if not A.supported() then
        say("Unsupported client. This build targets Classic Era; collection is disabled.")
        return
    end
    WoWStatusDB = WoWStatusDB or {version = 1, characters = {}}
    if WoWStatusDB.version ~= 1 then say("Unsupported saved data version."); return end
    local identity = A.identity()
    local key = identity.client .. ":" .. identity.realm .. ":" .. identity.guid
    local first = not WoWStatusDB.characters[key]
    WoWStatusDB.characters[key] = WoWStatusDB.characters[key] or {
        identity = identity, settings = defaults(), snapshot = {}, events = {}, sequence = 0,
        epoch = tostring(time()) .. "-" .. tostring(math.random(100000, 999999)),
    }
    current = WoWStatusDB.characters[key]
    current.identity = identity
    snapshot()
    for slot = 1, 19 do equipmentBaseline[slot] = GetInventoryItemLink("player", slot) end
    if current.settings.enabled then
        queue("session", {state = "addon_loaded"})
        if current.settings.fields.playtime then RequestTimePlayed() end
    end
    if first then
        say("First run: sharing is OFF. Choose fields and preview your introduction with /wstatus.")
        showPanel()
    end
end

frame:RegisterEvent("PLAYER_LOGIN")
frame:RegisterEvent("PLAYER_LOGOUT")
frame:RegisterEvent("PLAYER_LEVEL_UP")
frame:RegisterEvent("PLAYER_EQUIPMENT_CHANGED")
frame:RegisterEvent("CHAT_MSG_LOOT")
frame:RegisterEvent("ZONE_CHANGED_NEW_AREA")
frame:RegisterEvent("PLAYER_DEAD")
frame:RegisterEvent("TIME_PLAYED_MSG")
frame:SetScript("OnEvent", function(_, event, ...)
    if event == "PLAYER_LOGIN" then initialize(); return end
    if not current then return end
    if event == "PLAYER_LOGOUT" then
        queue("session", {state = "addon_unloading"})
        scrub()
    elseif event == "PLAYER_LEVEL_UP" then
        local level = ...
        if current.settings.fields.level then
            local maxLevel = GetMaxPlayerLevel and GetMaxPlayerLevel() or 60
            queue("level", {level = level, maximum = level == maxLevel})
        end
    elseif event == "CHAT_MSG_LOOT" then
        -- Match only localized self-loot formats, never another party member's loot.
        local message = ...
        local function matches(format)
            if not format then return false end
            local pattern = format:gsub("([%(%)%.%%%+%-%*%?%[%]%^%$])", "%%%1")
            pattern = pattern:gsub("%%%%s", ".+"):gsub("%%%%d", "%%d+")
            return message:match("^" .. pattern .. "$") ~= nil
        end
        if matches(LOOT_ITEM_SELF) or matches(LOOT_ITEM_SELF_MULTIPLE) then
            local link = message:match("(|Hitem:.-|h.-|h)")
            local item, quality = A.item(link)
            if item and quality then
                queue("loot", {item = item, quality = quality})
            end
        end
    elseif event == "PLAYER_EQUIPMENT_CHANGED" then
        local slot = ...
        local link = GetInventoryItemLink("player", slot)
        if current.settings.fields.gear and link and equipmentBaseline[slot] ~= link then
            queue("equipment", {item = link})
        end
        equipmentBaseline[slot] = link
        snapshot()
    elseif event == "ZONE_CHANGED_NEW_AREA" then
        if current.settings.fields.zone then queue("zone", {zone = GetRealZoneText()}) end
        snapshot()
    elseif event == "PLAYER_DEAD" then queue("death")
    elseif event == "TIME_PLAYED_MSG" then
        if current.settings.enabled and current.settings.fields.playtime then playtime = ... end
        snapshot()
    end
end)

SLASH_WOWSTATUS1 = "/wstatus"
SlashCmdList.WOWSTATUS = function(message)
    local command, rest = message:match("^(%S*)%s*(.-)$")
    if not current then say("Classic Era character is not ready."); return end
    if command == "pause" then
        current.settings.enabled = false
        current.settings.introduction_confirmed = false
        scrub()
        refresh()
        say("Paused. /reload and upload to apply remotely, or use Discord /privacy immediately.")
    elseif command == "test" then
        queue("level", {level = 10, synthetic = true})
        say("Synthetic level 10 event requested; requires sharing, level field and level storage.")
    elseif command == "interval" or command == "quality" then
        local number = tonumber(rest)
        local upper = command == "interval" and 100 or 5
        local lower = command == "interval" and 1 or 0
        if number and number == math.floor(number) and number >= lower and number <= upper then
            current.settings[command == "interval" and "level_interval" or "loot_quality"] = number
            scrub()
            say("Filter updated.")
        else say("Invalid filter value.") end
    elseif command == "professions" then
        if not current.settings.enabled or not current.settings.fields.professions then
            say("Enable profession sharing first. Names are player-entered, not verified skill ranks.")
            return
        end
        local names = {}
        for name in rest:gmatch("[^,]+") do
            name = name:match("^%s*(.-)%s*$")
            if #name > 0 and #name <= 50 and #names < 6 then
                table.insert(names, {name = name, source = "player_entered"})
            end
        end
        current.professions = names
        snapshot()
        say("Shared profession labels updated. /reload to export.")
    elseif command == "lfg" and #rest > 0 and #rest <= 200 then
        queue("lfg", {text = rest})
        say("LFG update requested; requires sharing and LFG storage.")
    else showPanel() end
end

if C_Timer and C_Timer.NewTicker then C_Timer.NewTicker(30, snapshot) end
