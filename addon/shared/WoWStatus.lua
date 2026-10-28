local ADDON = ...
local A = WoWStatusAdapter
local H = WoWStatusHistory
local S = WoWStatusSafe
local waitingForIdentity, unsupportedWarned = false, false
local current, panel
local fields = {"level", "class", "race", "faction", "guild", "gear", "zone", "playtime", "professions"}
local kinds = {"introduction", "level", "loot", "equipment", "death", "zone", "session", "lfg"}
local equipmentBaseline = {}
local playtime, playtimeRecordedAt, pendingPlayedLevel
local frame = CreateFrame("Frame")
local refresh

local function say(message)
    DEFAULT_CHAT_FRAME:AddMessage("|cff66ccffWoW Status:|r " .. message)
end

local function defaults()
    return {
        enabled = true, introduction_confirmed = false, character_role = "alt",
        fields = {level = true, class = true, race = true, faction = true, guild = true,
                  gear = true, zone = true, playtime = true, professions = true},
        collection = {introduction = true, level = true, loot = true, equipment = true,
                      death = true, zone = true, session = true, lfg = true},
        announcements = {introduction = true, level = true, loot = true,
                         equipment = true, death = true, zone = true, session = true, lfg = true},
        loot_quality = 4, level_interval = 10,
    }
end

local function snapshot()
    if not current then return end
    current.exported_at = time()
    current.player_name = WoWStatusDB.player_name or ""
    current.snapshot = current.settings.enabled and A.snapshot(current.settings.fields) or {}
    local tracking = current.history and current.history.tracking
    local last = tracking and tracking.points[#tracking.points]
    if tracking and tracking.active and last and current.snapshot.level == last.level then
        tracking.observed_until = current.exported_at
    end
    if current.settings.enabled and current.settings.fields.professions then
        current.snapshot.professions = current.professions or {}
    end
    if current.settings.enabled and current.settings.fields.playtime and playtime then
        current.snapshot.playtime = playtime
        current.snapshot.playtime_recorded_at = playtimeRecordedAt
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
            say("Recent buffer is full; older events remain in History and will still be uploaded.")
            current.warned = true
        end
    end
    data = H.copy(data or {})
    if current.settings.fields.zone then data.zone = A.zone() end
    local event = {id = id, kind = kind, at = time(), data = data,
        group_ids = H.copy(current.group_ids or {})}
    table.insert(current.events, event)
    H.record(current, event)
    snapshot()
    return event
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
        if allowed then
            H.scrubEvent(current, event)
            table.insert(retained, event)
        end
    end
    current.events = retained
    H.scrub(current)
    local level = A.level()
    if level then H.sync(current, level, time()) end
    WoWStatusPopups.privacyChanged()
    if not current.settings.enabled or not current.settings.fields.playtime then
        playtime, playtimeRecordedAt, pendingPlayedLevel = nil, nil, nil
        current.played_boundary = nil
    end
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
    local t = parent:CreateFontString(nil, "OVERLAY", "GameFontHighlightLarge")
    t:SetPoint("TOPLEFT", x, y)
    t:SetWidth(width or 560)
    t:SetJustifyH("LEFT")
    t:SetText(text)
    return t
end

local openSettings, registerSettings

local function showPanel(host)
    if not current then say("Character is not ready."); return end
    if not panel then
        panel = CreateFrame("Frame", "WoWStatusSetup", UIParent)
        panel:SetSize(600, 1050)
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
        label(panel, "Export on /reload or logout; run the companion to upload.\n"
            .. "Required: character name, realm, client and GUID.\n"
            .. "Review the sharing choices and introduction preview below.", 24, -55, 550)
        panel.checks = {}
        local function checkbox(key, title, x, y, group)
            local check = CreateFrame("CheckButton", nil, panel, "UICheckButtonTemplate")
            check:SetPoint("TOPLEFT", x, y)
            check:SetSize(32, 32)
            label(check, title, 38, -6, 230)
            check:SetScript("OnClick", function(self)
                local target = group and current.settings[group] or current.settings
                target[key] = self:GetChecked() and true or false
                if key == "enabled" and target[key] then current.enrolled = true end
                if key == "enabled" and not target[key] then
                    current.settings.introduction_confirmed = false
                end
                if key == "playtime" and target[key] and current.settings.enabled then
                    A.requestPlaytime()
                end
                scrub()
                refresh()
            end)
            table.insert(panel.checks, {widget = check, key = key, group = group})
        end
        checkbox("enabled", "Share this character", 24, -144)
        button(panel, "Mark as my main", 350, -144, 180, function()
            for _, character in pairs(WoWStatusDB.characters) do
                character.settings.character_role = "alt"
                character.exported_at = time()
            end
            current.settings.character_role = "main"
            snapshot()
            refresh()
            say("Main selected locally. Export and upload; Discord /main takes priority if set.")
        end)
        label(panel, "Profile fields", 24, -196, 550)
        for i, key in ipairs(fields) do
            local x = (i - 1) % 2 == 0 and 24 or 300
            checkbox(key, key, x, -226 - math.floor((i - 1) / 2) * 38, "fields")
        end
        label(panel, "Event", 24, -432, 190)
        label(panel, "Daily recap", 238, -432, 150)
        label(panel, "Discord messages", 408, -432, 170)
        for i, key in ipairs(kinds) do
            local y = -466 - (i - 1) * 38
            label(panel, key, 24, y - 6, 190)
            checkbox(key, "", 270, y, "collection")
            checkbox(key, "", 460, y, "announcements")
        end
        panel.preview = label(panel, "", 24, -792, 550)
        button(panel, "Confirm introduction", 24, -860, 190, function()
            if not current.settings.enabled then say("Enable sharing first."); return end
            if not current.settings.collection.introduction then
                say("Enable introduction storage first."); return
            end
            current.settings.introduction_confirmed = true
            queue("introduction", {}, "introduction:" .. current.identity.guid)
            refresh()
            say("Introduction queued. Use /reload, then run the companion.")
        end)
        button(panel, "Pause sharing", 230, -860, 160, function()
            current.settings.enabled = false
            current.settings.introduction_confirmed = false
            scrub()
            refresh()
            say("Paused locally. /reload and upload to apply remotely, or use /privacy in Discord now.")
        end)
        button(panel, "History / graph", 24, -1000, 160, function()
            WoWStatusHistoryUI.show(function() return current end, "logs")
        end)
        button(panel, "Popup help", 194, -1000, 120, function() WoWStatusPopups.command("") end)
        button(panel, "Groups", 324, -1000, 90, function() openSettings(true) end)
        panel.close = button(panel, "Close", 424, -1000, 110, function() panel:Hide() end)
        label(panel, "Filters: /wstatus interval 10   /wstatus quality 4\n"
            .. "Test: /wstatus test    LFG: /wstatus lfg <message>\n"
            .. "Pause or removal applies on upload; posted messages remain.\n"
            .. "Posting filters do not limit stored events.", 24, -910, 550)
    end
    for i = #UISpecialFrames, 1, -1 do
        if UISpecialFrames[i] == "WoWStatusSetup" then table.remove(UISpecialFrames, i) end
    end
    if not host then table.insert(UISpecialFrames, "WoWStatusSetup") end
    panel.close:SetShown(not host)
    panel:SetScale(1)
    panel:SetParent(host or UIParent)
    panel:ClearAllPoints()
    panel:SetPoint(host and "TOPLEFT" or "CENTER")
    panel:SetMovable(not host)
    if host then panel:SetScript("OnDragStart", nil)
    else panel:SetScript("OnDragStart", panel.StartMoving) end
    panel:SetFrameStrata(host and host:GetFrameStrata() or "DIALOG")
    if host then panel:SetFrameLevel(host:GetFrameLevel() + 1) end
    if not host and WoWStatusGroupWindow then WoWStatusGroupWindow:Hide() end
    refresh()
    panel:Show()
end

-- Both pages live inside the game's AddOns settings, with scrollable content.
local settingsCategory, groupsCategory
local function settingsPage(name, width, show)
    local page = CreateFrame("Frame")
    page:Hide()
    page.name = name
    local scroll = CreateFrame("ScrollFrame", nil, page, "UIPanelScrollFrameTemplate")
    scroll:SetPoint("TOPLEFT", 0, -8)
    scroll:SetPoint("BOTTOMRIGHT", -30, 8)
    local content
    local function resize()
        if content then
            -- Reflowed controls use native font and checkbox sizes. Never shrink them.
            content:SetScale(1)
            content:SetFrameStrata(scroll:GetFrameStrata())
            content:SetFrameLevel(scroll:GetFrameLevel() + 1)
            local available = scroll:GetWidth()
            content:SetWidth(math.max(width, available or width))
        end
    end
    local function display()
        show(scroll)
        content = name == "Groups" and WoWStatusGroupWindow or WoWStatusSetup
        scroll:SetScrollChild(content)
        resize()
    end
    page:SetScript("OnShow", display)
    page:SetScript("OnSizeChanged", resize)
    -- Canvas frames start shown in WoW. Build while explicitly hidden so the first
    -- sidebar selection works even when the Settings API skips an OnShow transition.
    display()
    page.OnRefresh = resize
    page.refresh = resize -- Legacy InterfaceOptions refresh callback.
    return page
end

registerSettings = function()
    if settingsCategory then return end
    if Settings and Settings.RegisterCanvasLayoutCategory and Settings.RegisterCanvasLayoutSubcategory
        and Settings.RegisterAddOnCategory then
        local page = settingsPage("WoW Status", 600, showPanel)
        settingsCategory = Settings.RegisterCanvasLayoutCategory(page, "WoW Status")
        Settings.RegisterAddOnCategory(settingsCategory)
        local groups = settingsPage("Groups", 620, WoWStatusGroups.show)
        groupsCategory = Settings.RegisterCanvasLayoutSubcategory(settingsCategory, groups, "Groups")
        Settings.RegisterAddOnCategory(groupsCategory)
    elseif InterfaceOptions_AddCategory then
        local page = settingsPage("WoW Status", 600, showPanel)
        InterfaceOptions_AddCategory(page)
        settingsCategory = page
        local groups = settingsPage("Groups", 620, WoWStatusGroups.show)
        groups.parent = page.name
        InterfaceOptions_AddCategory(groups)
        groupsCategory = groups
    end
end
openSettings = function(groups)
    registerSettings()
    local category = groups and groupsCategory or settingsCategory
    if category and category.GetID and Settings and Settings.OpenToCategory then
        Settings.OpenToCategory(category:GetID())
    elseif category and InterfaceOptionsFrame_OpenToCategory then
        InterfaceOptionsFrame_OpenToCategory(category)
    elseif groups then WoWStatusGroups.show()
    else showPanel() end
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
        if not unsupportedWarned then
            say("This addon folder targets " .. A.display_name .. ". Collection is disabled on this client.")
            unsupportedWarned = true
        end
        return
    end
    WoWStatusDB = WoWStatusDB or {version = 1, characters = {}}
    if WoWStatusDB.version ~= 1 then say("Unsupported saved data version."); return end
    local identity = A.identity()
    if not identity then
        if not waitingForIdentity then
            say("Waiting for readable player identity. Collection will retry after loading/combat.")
            waitingForIdentity = true
        end
        return
    end
    waitingForIdentity = false
    local key = identity.client .. ":" .. identity.realm .. ":" .. identity.guid
    local first = not WoWStatusDB.characters[key]
    WoWStatusDB.characters[key] = WoWStatusDB.characters[key] or {
        identity = identity, settings = defaults(), snapshot = {}, events = {}, sequence = 0,
        epoch = tostring(time()) .. "-" .. tostring(math.random(100000, 999999)),
    }
    current = WoWStatusDB.characters[key]
    current.identity = identity
    WoWStatusGroups.init(WoWStatusDB, function() return current end, say)
    WoWStatusPopups.init(WoWStatusDB, function() return current end, say)
    H.init(current)
    H.scrub(current)
    local level = A.level()
    if level then H.sync(current, level, time()) end
    snapshot()
    for slot = 1, 19 do equipmentBaseline[slot] = A.equipment(slot) end
    registerSettings()
    if current.settings.enabled then
        if not first then queue("session", {state = "addon_loaded"}) end
        if current.settings.fields.playtime then A.requestPlaytime() end
    end
    if first then
        say("Sharing defaults are ON. Review character options and account groups in Options > AddOns > WoW Status.")
        openSettings()
    end
end

frame:RegisterEvent("ADDON_LOADED")
frame:RegisterEvent("PLAYER_LOGIN")
frame:RegisterEvent("PLAYER_ENTERING_WORLD")
frame:RegisterEvent("PLAYER_REGEN_ENABLED")
frame:RegisterEvent("PLAYER_LOGOUT")
frame:RegisterEvent("PLAYER_LEVEL_UP")
frame:RegisterEvent("PLAYER_EQUIPMENT_CHANGED")
frame:RegisterEvent("CHAT_MSG_LOOT")
frame:RegisterEvent("ZONE_CHANGED_NEW_AREA")
frame:RegisterEvent("PLAYER_DEAD")
frame:RegisterEvent("TIME_PLAYED_MSG")
frame:SetScript("OnEvent", function(_, event, ...)
    if event == "ADDON_LOADED" then
        if current then registerSettings() end
        return
    end
    if event == "PLAYER_LOGIN" or event == "PLAYER_ENTERING_WORLD" or event == "PLAYER_REGEN_ENABLED" then
        if not current then initialize()
        elseif event == "PLAYER_REGEN_ENABLED" or event == "PLAYER_ENTERING_WORLD" then
            local level = A.level()
            if level then H.sync(current, level, time()) end
            snapshot()
        end
        return
    end
    if not current then return end
    if event == "PLAYER_LOGOUT" then
        queue("session", {state = "addon_unloading"})
        scrub()
    elseif event == "PLAYER_LEVEL_UP" then
        local level = S.number(...)
        if level and level >= 1 and level <= A.max_level and current.settings.fields.level then
            local maxLevel = A.max_level
            local event = queue("level", {level = level, maximum = level == maxLevel})
            WoWStatusPopups.broadcast(current, event)
            if event and current.settings.fields.playtime then
                pendingPlayedLevel = event
                A.requestPlaytime()
            end
        end
    elseif event == "CHAT_MSG_LOOT" then
        -- Match only localized self-loot formats, never another party member's loot.
        local message = S.string(...)
        if not message then return end
        local function matches(format)
            format = S.string(format)
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
        local slot = S.number(...)
        if not slot or slot < 1 or slot > 19 then return end
        local link = A.equipment(slot)
        if current.settings.fields.gear and link and equipmentBaseline[slot] ~= link then
            local _, quality = A.item(link)
            queue("equipment", {item = link, quality = quality})
        end
        equipmentBaseline[slot] = link
        snapshot()
    elseif event == "ZONE_CHANGED_NEW_AREA" then
        local zone = A.zone()
        if zone and current.settings.fields.zone then queue("zone", {zone = zone}) end
        snapshot()
    elseif event == "PLAYER_DEAD" then queue("death")
    elseif event == "TIME_PLAYED_MSG" then
        if current.settings.enabled and current.settings.fields.playtime then
            local total, thisLevel = ...
            total, thisLevel = S.number(total), S.number(thisLevel)
            local level = A.level()
            if total and total >= 0 then playtime, playtimeRecordedAt = total, time() end
            if total and thisLevel and level and thisLevel >= 0 and total >= thisLevel then
                local boundary = total - thisLevel
                local previous = current.played_boundary
                if pendingPlayedLevel and pendingPlayedLevel.data.level == level and previous
                    and previous.level == level - 1 and boundary >= previous.total then
                    local seconds = boundary - previous.total
                    -- Update both retained copies before the next SavedVariables export.
                    for _, events in ipairs({current.events, current.history.events}) do
                        for _, saved in ipairs(events) do
                            if saved.id == pendingPlayedLevel.id then saved.data.played_level_seconds = seconds end
                        end
                    end
                end
                current.played_boundary = {level = level, total = boundary}
                pendingPlayedLevel = nil
            end
        end
        snapshot()
    end
end)

SLASH_WOWSTATUS1 = "/wstatus"
SlashCmdList.WOWSTATUS = function(message)
    local command, rest = message:match("^(%S*)%s*(.-)$")
    if not current then say(A.display_name .. " character is not ready or identity is currently restricted."); return end
    if command == "groups" then
        if rest == "legacy" then
            current.group_ids = {}
            current.legacy_upload = true
            current.exported_at = time()
            WoWStatusPopups.groupsChanged()
            say("Legacy single-service upload selected. Only use with your own configured /link credentials.")
        else openSettings(true) end
    elseif command == "popup" then
        WoWStatusPopups.command(rest)
    elseif command == "logs" or command == "graph" or command == "times" then
        local mode = command == "graph" and "graph" or (command == "times" and "timing" or "logs")
        WoWStatusHistoryUI.show(function() return current end, mode)
    elseif command == "pause" then
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
        for rawName in rest:gmatch("[^,]+") do
            local name = rawName:match("^%s*(.-)%s*$")
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
    else openSettings() end
end

if C_Timer and C_Timer.NewTicker then C_Timer.NewTicker(30, snapshot) end
