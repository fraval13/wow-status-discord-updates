local A = WoWStatusAdapter
local H = WoWStatusHistory
local S = WoWStatusSafe
local waitingForIdentity, unsupportedWarned = false, false
local current, panel, discordPanel
local fields = {"level", "class", "race", "faction", "guild", "gear", "zone", "playtime", "professions", "deaths", "quests", "gold", "kills", "collection"}
local kinds = {"level", "death", "zone", "quest", "profession", "dungeon", "mount", "reputation", "unlock", "pvp"}
-- Retail only (#165): editions without achievements never show the option.
if A.achievements then kinds[#kinds + 1] = "achievement" end
local playtime, playtimeRecordedAt, pendingPlayedLevel
local frame = CreateFrame("Frame")
local refresh
-- What last hurt this character, from the combat log, for death details. Only
-- damage to this character is looked at; clients that hide the combat log
-- (secret values) simply give no killer.
local lastHit
local DAMAGE = {SWING_DAMAGE=true, RANGE_DAMAGE=true, SPELL_DAMAGE=true, SPELL_PERIODIC_DAMAGE=true,
    DAMAGE_SHIELD=true, DAMAGE_SPLIT=true, ENVIRONMENTAL_DAMAGE=true}
local ENVIRONMENT = {Falling="Falling", Drowning="Drowning", Fatigue="Fatigue", Fire="Fire", Lava="Lava", Slime="Slime",
    FALLING="Falling", DROWNING="Drowning", FATIGUE="Fatigue", FIRE="Fire", LAVA="Lava", SLIME="Slime"}
local function trackHit()
    if not CombatLogGetCurrentEventInfo then return end
    local ok, _, sub, _, _, sourceName, _, _, destGUID, _, _, _, environment = pcall(CombatLogGetCurrentEventInfo)
    if not ok or not DAMAGE[S.value(sub)] then return end
    -- The stored GUID: this runs for every combat event nearby, so it stays cheap.
    if not current or S.string(destGUID) ~= current.identity.guid then return end
    local name = sub == "ENVIRONMENTAL_DAMAGE" and ENVIRONMENT[S.string(environment) or ""] or S.string(sourceName)
    if name and #name <= 48 and not name:find(S.CONTROL_OR_PIPE) then
        lastHit = {name=name, at=S.uptime()}
    end
end

local T = WoWStatusLocale.T
-- Every chat message of the addon (also other modules' notices) passes here.
local function say(message)
    DEFAULT_CHAT_FRAME:AddMessage("|cff66ccffWoW Status:|r " .. T(message))
end

local function defaults()
    return {
        enabled = true, discord_enabled = false, discord_delivery = "summary", introduction_confirmed = false, character_role = "alt",
        fields = {level = true, class = true, race = true, faction = true, guild = true,
                  gear = true, zone = true, playtime = true, professions = true, deaths = true, quests = true, gold = true, kills = true, collection = true},
        collection = {introduction = true, level = true, loot = true, equipment = false,
                      death = true, zone = true, quest = true, profession = true, lfg = false},
        announcements = {introduction = true, level = true, loot = true,
                         equipment = false, death = true, zone = true, quest = true, profession = true, lfg = false},
        loot_quality = 3, loot_rarities={rare=true,epic=true,legendary=true}, level_interval = 10,
    }
end

-- A random per-character secret that stays in SavedVariables. The companion includes it
-- in uploads so a later enrollment of the same player can take the character back (#11).
-- It is never sent in game. Since patch 5.4.2, math.random uses the client's secure RNG.
local function claimSecret(character)
    local secret = character.claim_secret
    if type(secret) == "string" and #secret == 32 and not secret:find("[^0-9a-f]") then return end
    local digits = {}
    for i = 1, 32 do digits[i] = string.format("%x", math.random(0, 15)) end
    character.claim_secret = table.concat(digits)
end

local function snapshot()
    if not current then return end
    S.stampExport(current)
    if current.settings.enabled then current.enrolled = true end
    current.player_name = WoWStatusDB.player_name or ""
    current.snapshot = current.settings.enabled and A.snapshot(current.settings.fields) or {}
    local tracking = current.history and current.history.tracking
    local last = tracking and tracking.points[#tracking.points]
    if tracking and tracking.active and last and current.snapshot.level == last.level then
        tracking.observed_until = current.exported_at
    end
    if current.settings.enabled then
        for key, value in pairs(WoWStatusProgress.observe(current, current.settings.fields)) do
            current.snapshot[key] = value
        end
    end
    if current.settings.enabled and current.settings.fields.playtime and playtime then
        current.snapshot.playtime = playtime
        current.snapshot.playtime_recorded_at = playtimeRecordedAt
    end
end

local function queue(kind, data, fixed, targetGroups)
    if not current or not current.settings.enabled or not current.settings.collection[({raid="dungeon",epicmount="mount"})[kind] or kind] then
        return
    end
    if kind == "discovery" or kind == "lfg" then return end
    if kind == "dungeon" and data.source ~= "game_api" then return end
    if kind == "loot" and not WoWStatusLoot.allowed(current.settings,WoWStatusLoot.eventInfo(data)) then return end
    current.sequence = (current.sequence or 0) + 1
    local id = fixed or (current.identity.guid .. ":" .. current.epoch .. ":" .. current.sequence)
    for _, event in ipairs(current.events) do if event.id == id then return end end
    if #current.events >= 500 then
        table.remove(current.events, 1)
        if not current.warned then
            say("Recent buffer is full; older events remain in History.")
            current.warned = true
        end
    end
    data = H.copy(data or {})
    if current.settings.fields.zone then data.zone = A.zone() end
    local event = {id = id, kind = kind, at = S.now(), data = data,
        group_ids = H.copy(targetGroups or current.group_ids or {})}
    -- Only events that can be sent or logged for the group need a packet nonce.
    if WoWStatusJournal.shared(kind) and not data.synthetic then event.nonce = WoWStatusPopups.newNonce(current) end
    table.insert(current.events, event)
    H.record(current, event)
    WoWStatusJournal.recordLocal(event)
    snapshot()
    WoWStatusPopups.broadcast(current, event)
    WoWStatusScreenshots.event(event, current.settings)
    WoWStatusRecaps.note(event)
    return event
end

local function questMilestone()
    local milestone = WoWStatusProgress.questMilestone(current, current.snapshot.quests_completed, current.snapshot.quests_source)
    if milestone and current.settings.fields.quests then
        queue("quest", {completed=milestone, source=current.snapshot.quests_source})
    end
end

local function scrub()
    -- Remove data immediately when privacy choices change, before any disk export.
    local retained = {}
    for _, event in ipairs(current.events) do
        local allowed = current.settings.enabled and current.settings.collection[({raid="dungeon",epicmount="mount"})[event.kind] or event.kind]
        if event.kind == "level" and not current.settings.fields.level then allowed = false end
        if event.kind == "zone" and not current.settings.fields.zone then allowed = false end
        if event.kind == "equipment" and not current.settings.fields.gear then allowed = false end
        if event.kind == "quest" and not current.settings.fields.quests then allowed = false end
        if event.kind == "profession" and not current.settings.fields.professions then allowed = false end
        if event.kind == "loot" and not WoWStatusLoot.allowed(current.settings,WoWStatusLoot.eventInfo(event.data)) then allowed=false end
        if allowed then
            H.scrubEvent(current, event)
            table.insert(retained, event)
        end
    end
    current.events = retained
    H.scrub(current)
    local level = A.level()
    if level then H.sync(current, level, S.now()) end
    WoWStatusPopups.privacyChanged()
    WoWStatusJournal.privacyChanged()
    if not current.settings.enabled or not current.settings.fields.playtime then
        playtime, playtimeRecordedAt, pendingPlayedLevel = nil, nil, nil
        current.played_boundary = nil
    end
    if not current.settings.fields.professions then current.professions = nil end
    if WoWStatusEquipment and not current.settings.fields.gear then current.equipment_profile = nil end
    if WoWStatusEquipmentSync then WoWStatusEquipmentSync.privacyChanged() end
    snapshot()
end

local function button(parent, text, x, y, width, fn)
    local b = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
    b:SetPoint("TOPLEFT", x, y)
    b:SetSize(width, 26)
    b:SetText(T(text))
    b:SetScript("OnClick", fn)
    return b
end

local function label(parent, text, x, y, width)
    local t = parent:CreateFontString(nil, "OVERLAY", "GameFontHighlightLarge")
    t:SetPoint("TOPLEFT", x, y)
    t:SetWidth(width or 560)
    t:SetJustifyH("LEFT")
    t:SetText(T(text))
    return t
end

local openSettings, registerSettings
local NOT_SEEN_HEIGHT = 84 -- The "Friends not seen for a while" section.

local function showPanel(host)
    if not current then say("Character is not ready."); return end
    if not panel then
        panel = CreateFrame("Frame", "WoWStatusSetup", UIParent)
        panel:SetSize(600, (WoWStatusScreenshots.available() and 1606 or 1466) + WoWStatusUnitTooltip.HEIGHT + NOT_SEEN_HEIGHT)
        panel:SetPoint("CENTER");panel:SetFrameStrata("DIALOG");panel:EnableMouse(true)
        panel.background=panel:CreateTexture(nil,"BACKGROUND")
        panel.background:SetAllPoints();panel.background:SetColorTexture(.025,.035,.055,.96)
        if WoWStatusTheme and WoWStatusTheme.attachBackground then WoWStatusTheme.attachBackground(panel.background) end
        label(panel,"WoW Status",24,-20)
        label(panel,"Set the same group ID as your friends to start sharing.",24,-64,550)
        panel.checks={}
        local function section(text,y)
            local title=label(panel,text,24,y,550);title:SetTextColor(1,.82,.25)
        end
        local function checkbox(key,title,x,y,group)
            local check=CreateFrame("CheckButton",nil,panel,"UICheckButtonTemplate")
            check:SetPoint("TOPLEFT",x,y);check:SetSize(32,32)
            label(check,title,38,-6,group=="loot_rarities" and 460 or 230)
            check:SetScript("OnClick",function(self)
                local target=group and current.settings[group] or current.settings
                target[key]=self:GetChecked() and true or false
                if key=="enabled" and target[key] then current.enrolled=true end
                if group=="in_game" and target[key] then current.settings.collection[key]=true end
                scrub();refresh()
            end)
            panel.checks[#panel.checks+1]={widget=check,key=key,group=group}
        end
        button(panel,"Groups",24,-116,160,function() openSettings("groups") end)
        button(panel,"Activity log",204,-116,160,function() WoWStatusJournal.show() end)
        button(panel,"Notifications",384,-116,170,function() openSettings("previews") end)
        checkbox("enabled","Share my progress",24,-174)
        section("Announcements",-234)
        local titles={level="Level up",death="Deaths",zone="First zone visit",quest="Every 100 quests",
            profession="Profession milestones",dungeon="Dungeon / raid milestones",mount="Mount milestones",
            reputation="Reputation rank",unlock="Class ability unlock",pvp=A.pvpLabel or "PvP rank",achievement="Achievements"}
        for i,key in ipairs(kinds) do
            checkbox(key,titles[key] or key,(i-1)%2==0 and 24 or 310,-270-math.floor((i-1)/2)*42,"in_game")
        end
        -- The slot after the last kind: beside it on an odd count, else a new row.
        checkbox("recap","Share my session recaps",#kinds%2==1 and 310 or 24,-270-math.floor(#kinds/2)*42,"in_game")
        section("First-time equipment",-522)
        checkbox("loot","Announce first armor equips",24,-544,"in_game")
        checkbox("rare","Rare equipment",54,-586,"loot_rarities")
        checkbox("epic","Epic equipment",54,-628,"loot_rarities")
        checkbox("legendary","Legendary equipment",54,-670,"loot_rarities")
        section("Character details",-742)
        local names={level="Level and XP",class="Class",race="Race and male/female",faction="Faction",
            guild="Guild",gear="Equipment and combat stats",zone="Location",playtime="Played time",professions="Professions",deaths="Total deaths",quests="Completed quests",
            gold="Gold and gold earned",kills="Monsters killed",collection="Dungeons, mounts and honor kills"}
        for i,key in ipairs(fields) do
            checkbox(key,names[key] or key,(i-1)%2==0 and 24 or 310,-780-math.floor((i-1)/2)*42,"fields")
        end
        local bottom=-1072
        -- Clients without Screenshot() never show these options.
        if WoWStatusScreenshots.available() then
            section("Screenshots",-1072)
            checkbox("level","Screenshot on level up",24,-1108,"screenshots")
            checkbox("dungeon","Screenshot on first dungeon clear",310,-1108,"screenshots")
            checkbox("hide_ui","Hide interface in screenshots",24,-1150,"screenshots")
            bottom=-1212
        end
        section("Characters shown to friends",bottom)
        label(panel,"Untick bank alts to hide them from everyone's character list and leaderboard.",24,bottom-32,520)
        panel.visibility=WoWStatusRoster.buildVisibilitySettings(panel,bottom-84)
        bottom=bottom-260
        -- A short block in group members' unit tooltips (#183). Account-wide.
        section("Friends' tooltips",bottom)
        panel.unitTooltip=WoWStatusUnitTooltip.buildSettings(panel,bottom-36)
        bottom=bottom-36-WoWStatusUnitTooltip.HEIGHT
        -- "Not seen for a while" on the Overview (#172). Account-wide, local only.
        section("Friends not seen for a while",bottom)
        label(panel,"List friends on the Overview after this many quiet days:",24,bottom-40,320)
        panel.notSeen=button(panel,"",360,bottom-38,180,function(self)
            WoWStatusOverview.cycleNotSeenDays(); self:SetText(WoWStatusOverview.notSeenLabel())
            if WoWStatusMainWindow then WoWStatusMainWindow.refresh("overview") end
        end)
        bottom=bottom-NOT_SEEN_HEIGHT
        button(panel,"History / graph",24,bottom,170,function() WoWStatusHistoryUI.show(function() return current end,"logs") end)
        button(panel,"Diagnostics",214,bottom,170,function() WoWStatusDiagnostics.show() end)
        panel.close=button(panel,"Close",424,bottom,130,function() panel:Hide() end)
        -- Experiments, every one off until the player switches it on (#222).
        button(panel,"Labs: experimental features",24,bottom-40,360,function() WoWStatusLabs.show() end)
    end
    for i = #UISpecialFrames, 1, -1 do
        if UISpecialFrames[i] == "WoWStatusSetup" then table.remove(UISpecialFrames, i) end
    end
    if not host then table.insert(UISpecialFrames, "WoWStatusSetup") end
    panel.close:SetShown(not host)
    panel.background:SetShown(not host)
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

local function showDiscord(host)
    if not discordPanel then
        discordPanel = CreateFrame("Frame", "WoWStatusDiscordSettings", UIParent)
        discordPanel:SetSize(600, 930)
        discordPanel:EnableMouse(true)
        local bg = discordPanel:CreateTexture(nil, "BACKGROUND")
        bg:SetAllPoints(); bg:SetColorTexture(.04, .04, .07, .98)
        label(discordPanel, "Optional Discord sharing", 24, -20, 550)
        label(discordPanel, "Off by default. In-game sharing works without this.\n"
            .. "If enabled, run the companion to upload after /reload or logout.\n"
            .. "Discord receives a status card only when your progress changes.", 24, -60, 550)
        discordPanel.checks = {}
        local function check(key, text, y, group)
            local widget = CreateFrame("CheckButton", nil, discordPanel, "UICheckButtonTemplate")
            widget:SetPoint("TOPLEFT", 24, y); widget:SetSize(32, 32)
            label(widget, text, 38, -6, 460)
            widget:SetScript("OnClick", function(self)
                local target = group and current.settings[group] or current.settings
                target[key] = self:GetChecked() and true or false
                if key == "discord_enabled" and target[key] then
                    current.discord_enrolled, current.discord_since = true, S.now()
                end
                current.settings.discord_delivery = "summary"
                snapshot()
            end)
            table.insert(discordPanel.checks, {widget=widget, key=key, group=group})
        end
        check("discord_enabled", "Also share this character to Discord", -150)
        label(discordPanel, "Include in Discord status updates", 24, -204, 550)
        for i, kind in ipairs(kinds) do check(kind, kind, -238 - (i - 1) * 38, "announcements") end
        label(discordPanel, "Repeat uploads do not repeat old activity. Already posted messages\n"
            .. "remain in Discord. Turn off, then export and upload to apply a pause\n"
            .. "remotely; companion group privacy controls can pause immediately.", 24, -820, 550)
    end
        discordPanel.close = discordPanel.close or button(discordPanel, "Close", 424, -880, 110,
            function() discordPanel:Hide() end)
    for i = #UISpecialFrames, 1, -1 do
        if UISpecialFrames[i] == "WoWStatusDiscordSettings" then table.remove(UISpecialFrames, i) end
    end
    if not host then table.insert(UISpecialFrames, "WoWStatusDiscordSettings") end
    discordPanel.close:SetShown(not host)
    if not host then
        if panel then panel:Hide() end
        if WoWStatusGroupWindow then WoWStatusGroupWindow:Hide() end
    end
    discordPanel:SetParent(host or UIParent); discordPanel:ClearAllPoints()
    discordPanel:SetPoint(host and "TOPLEFT" or "CENTER")
    if host then discordPanel:SetFrameStrata(host:GetFrameStrata()); discordPanel:SetFrameLevel(host:GetFrameLevel()+1) end
    for _, entry in ipairs(discordPanel.checks) do
        local target = entry.group and current.settings[entry.group] or current.settings
        entry.widget:SetChecked(target[entry.key])
    end
    discordPanel:Show()
end

-- Both pages live inside the game's AddOns settings, with scrollable content.
local settingsCategory, groupsCategory, discordCategory, previewsCategory
-- Every registered canvas page, so openSettings() can fill them before the
-- Settings API shows one (#187).
local settingsPages = {}
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
    local built = false
    local function display()
        built = true
        show(scroll)
        local pages = {Groups=WoWStatusGroupWindow, Discord=WoWStatusDiscordSettings,
            ["Notifications"]=WoWStatusNotificationPreviews}
        content = pages[name] or WoWStatusSetup
        scroll:SetScrollChild(content)
        resize()
    end
    -- Build the content the first time the page is shown, not at login: a
    -- session that never opens Options never pays for these frames (#187).
    -- Canvas frames can be shown without an OnShow transition, so a refresh and
    -- openSettings() both make sure it exists; neither rebuilds a built page,
    -- so unsaved edits in it survive.
    local function ensure() if not built then display() end end
    page:SetScript("OnShow", display)
    page:SetScript("OnSizeChanged", resize)
    page.ensure = ensure
    settingsPages[#settingsPages + 1] = page
    page.OnRefresh = function() ensure(); resize() end
    page.refresh = page.OnRefresh -- Legacy InterfaceOptions refresh callback.
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
        -- Dormant integration: re-enable in Features.lua to restore this page.
        if WoWStatusFeatures.discord then
            local discord=settingsPage("Discord",600,showDiscord)
            discordCategory=Settings.RegisterCanvasLayoutSubcategory(settingsCategory,discord,"Discord (optional)")
            Settings.RegisterAddOnCategory(discordCategory)
        end
        local previews = settingsPage("Notifications", 600, WoWStatusPreviews.show)
        previewsCategory = Settings.RegisterCanvasLayoutSubcategory(settingsCategory, previews, "Notifications")
        Settings.RegisterAddOnCategory(previewsCategory)
    elseif InterfaceOptions_AddCategory then
        local page = settingsPage("WoW Status", 600, showPanel)
        InterfaceOptions_AddCategory(page)
        settingsCategory = page
        local groups = settingsPage("Groups", 620, WoWStatusGroups.show)
        groups.parent = page.name
        InterfaceOptions_AddCategory(groups)
        groupsCategory = groups
        if WoWStatusFeatures.discord then
            local discord=settingsPage("Discord",600,showDiscord)
            discord.parent=page.name;InterfaceOptions_AddCategory(discord);discordCategory=discord
        end
        local previews = settingsPage("Notifications", 600, WoWStatusPreviews.show)
        previews.parent = page.name
        InterfaceOptions_AddCategory(previews)
        previewsCategory = previews
    end
end
openSettings = function(mode)
    if mode=="discord" and not WoWStatusFeatures.discord then mode=nil end
    registerSettings()
    local category = mode == "previews" and previewsCategory or mode == "discord" and discordCategory or (mode == "groups" and groupsCategory or settingsCategory)
    if S.call(InCombatLockdown) == true then
        say("Cannot open now: settings cannot be opened during combat. Try again after combat.")
        return
    end
    local ok
    if category and category.GetID and Settings and Settings.OpenToCategory then
        ok=pcall(function() Settings.OpenToCategory(category:GetID()) end)
    elseif category and InterfaceOptionsFrame_OpenToCategory then
        ok=pcall(InterfaceOptionsFrame_OpenToCategory,category)
    else
        say("Cannot open now: WoW's addon settings are not ready. Try again shortly.")
        return
    end
    if not ok then
        say("Cannot open now: WoW could not open settings. Try Options > AddOns > WoW Status.")
        return
    end
    -- The category is open now, so make sure every page has its content. Login
    -- left them empty on purpose (#187) and the Settings API can show a canvas
    -- page without an OnShow to build from; nothing is built before WoW has
    -- actually opened the window.
    for _, page in ipairs(settingsPages) do pcall(page.ensure) end
end

refresh = function()
    if not panel then return end
    if panel.visibility then panel.visibility:refresh() end
    if panel.unitTooltip then panel.unitTooltip:refresh() end
    if panel.notSeen then panel.notSeen:SetText(WoWStatusOverview.notSeenLabel()) end
    for _, entry in ipairs(panel.checks) do
        local target = entry.group and current.settings[entry.group] or current.settings
        entry.widget:SetChecked(target[entry.key])
    end
end

-- Reports a saved-data upgrade step that failed, once a session (initialize()
-- runs again after loading screens and combat until it finds the character);
-- the step is tried again later.
local reportedSteps, unreadableWarned = {}, false
local function upgraded(ok, step, problem)
    if ok or reportedSteps[step] then return end
    reportedSteps[step] = true
    say(WoWStatusLocale.F("Could not upgrade saved data (step %d). It will be tried again later.",
        step.version) .. " " .. tostring(problem))
end

local function initialize()
    if not A.supported() then
        if not unsupportedWarned then
            say("This addon folder targets " .. A.display_name .. ". Collection is disabled on this client.")
            unsupportedWarned = true
        end
        return
    end
    if not WoWStatusDB then
        WoWStatusDB = {version = 1, characters = {}}
        WoWStatusLocale.set(WoWStatusLocale.clientLanguage())
        WoWStatusWhatsNew.fresh(WoWStatusDB)
        WoWStatusDB.guide_pending = true
    end
    -- Not the addon's data at all (a broken file or a hand edit): leave it alone.
    if type(WoWStatusDB) ~= "table" or type(WoWStatusDB.characters) ~= "table" then
        if not unreadableWarned then say("Saved data is unreadable. WoW Status leaves it unchanged."); unreadableWarned = true end
        return
    end
    -- Older releases and the companion read only version 1; progress is kept in
    -- schema_version instead (see Migrations.lua).
    WoWStatusDB.version = 1
    -- Older saved data is upgraded once, step by step, never refused (#231).
    upgraded(WoWStatusMigrations.upgradeAccount(WoWStatusDB))
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
        epoch = tostring(S.now()) .. "-" .. tostring(math.random(100000, 999999)),
    }
    current = WoWStatusDB.characters[key]
    current.identity = identity
    -- The realm as chat names it (see WoWStatusPopups.characterName).
    current.normalized_realm = A.realmName() or current.normalized_realm
    WoWStatusLoot.defaults(current.settings)
    WoWStatusScreenshots.defaults(current.settings)
    for _, character in pairs(WoWStatusDB.characters) do
        claimSecret(character)
        -- Not an upgrade: the Discord switch in Features.lua can turn either way
        -- between releases, so the hidden opt-ins are parked or restored at every login.
        if not WoWStatusFeatures.discord then
            if character.discord_hidden_opt_in==nil then character.discord_hidden_opt_in=character.settings.discord_enabled==true end
            if character.discord_hidden_enrolled==nil then character.discord_hidden_enrolled=character.discord_enrolled==true end
            character.settings.discord_enabled=false;character.discord_enrolled=false
        elseif character.discord_hidden_opt_in~=nil then
            character.settings.discord_enabled=character.discord_hidden_opt_in
            character.discord_enrolled=character.discord_hidden_enrolled or false;character.discord_hidden_enrolled=nil
            if character.discord_hidden_opt_in then character.discord_since=S.now();character.discord_enrolled=true end
            character.discord_hidden_opt_in=nil
        end
    end
    upgraded(WoWStatusMigrations.upgradeCharacter(current, WoWStatusDB))
    -- Not upgrades: options the addon no longer lets anyone change, held at
    -- their fixed values on every login. The tables exist even if an upgrade
    -- step failed, so the rest of the login carries on.
    for _, part in ipairs({"fields", "collection", "announcements", "in_game"}) do
        if type(current.settings[part]) ~= "table" then current.settings[part] = {} end
    end
    current.settings.discord_delivery = "summary"
    current.settings.collection.equipment = false
    current.settings.announcements.equipment = false
    current.settings.in_game.equipment = false
    current.settings.collection.recap=true
    current.settings.in_game.introduction=true
    current.settings.collection.introduction=true
    current.settings.announcements.introduction=true
    for _, removed in ipairs({"discovery", "lfg"}) do
        current.settings.collection[removed]=false
        current.settings.announcements[removed]=false
        current.settings.in_game[removed]=false
    end
    -- A kind that is not collected is not shown in game either.
    if current.settings.collection.loot==false then current.settings.in_game.loot=false end
    for _,kind in ipairs(kinds) do
        if current.settings.collection[kind]==false then current.settings.in_game[kind]=false end
    end
    WoWStatusGroups.init(WoWStatusDB, function() return current end, say)
    WoWStatusPopups.init(WoWStatusDB, function() return current end, say)
    WoWStatusMutes.init(WoWStatusDB)
    WoWStatusShare.init(WoWStatusDB, say)
    H.init(current)
    WoWStatusJournal.prepare(WoWStatusDB)
    H.scrub(current)
    WoWStatusMinimap.init(WoWStatusDB)
    WoWStatusFeatures.init(WoWStatusDB)
    WoWStatusJournal.init(WoWStatusDB,current)
    WoWStatusGroups.announce = function()
        current.introduced_groups=current.introduced_groups or {}
        for id,member in pairs(current.group_ids or {}) do
            if not current.introduced_groups[id] then
                local event=queue("introduction",{group=member.label},nil,{[id]=H.copy(member)})
                if event then current.introduced_groups[id]=true end
            end
        end
    end
    WoWStatusGroups.announce()
    if WoWStatusGroups.anniversary() then say("Another year together in your WoW Status group. Well played!") end
    -- Existing equipped items establish a silent baseline on first installation.
    if not current.equipped_items then
        current.equipped_items={}
        for slot=1,19 do
            local link=A.equipment(slot)
            local id=type(link)=="string" and tonumber(link:match("item:(%d+)"))
            if id then current.equipped_items[tostring(id)]=true end
        end
    end
    local level = A.level()
    if level then H.sync(current, level, S.now()) end
    WoWStatusProgress.initDeaths(current)
    WoWStatusProgress.initTotals(current)
    if level then WoWStatusJournal.backfill(current, level) end
    WoWStatusProgress.initZones(current,A.zone())
    snapshot()
    current.last_zone = A.zone()
    local dead = S.call(UnitIsDeadOrGhost, "player")
    if dead ~= nil then current.death_latched = dead == true or dead == 1 end
    WoWStatusProgress.questMilestone(current, current.snapshot.quests_completed, current.snapshot.quests_source, true)
    if current.settings.fields.professions then WoWStatusProgress.professionChanges(current, true) end
    WoWStatusMilestones.init(current, queue)
    WoWStatusAchievements.init(current, queue)
    WoWStatusRecaps.init(current,queue)
    WoWStatusRoster.init(WoWStatusDB, current, say)
    WoWStatusPopups.learnOwnName()
    registerSettings()
    if current.settings.enabled then
        if current.settings.fields.playtime then A.requestPlaytime() end
    end
    if WoWStatusGuide.check() then
        -- A brand-new account gets the setup guide instead of the Options page.
    elseif first then
        say("Set the same group ID as your friends in Options > AddOns > WoW Status.")
        openSettings()
    end
    WoWStatusWhatsNew.check(WoWStatusDB)
end

-- Client builds differ in event availability; one absent event must not abort
-- registration of the remaining observers, options and slash commands.
local EVENTS = {"ADDON_LOADED","PLAYER_LOGIN","PLAYER_ENTERING_WORLD","PLAYER_REGEN_ENABLED",
    "PLAYER_LOGOUT","PLAYER_LEVEL_UP","PLAYER_EQUIPMENT_CHANGED","ZONE_CHANGED_NEW_AREA",
    "PLAYER_DEAD","TIME_PLAYED_MSG","PLAYER_XP_UPDATE","QUEST_TURNED_IN","QUEST_LOG_UPDATE",
    "QUEST_QUERY_COMPLETE","SKILL_LINES_CHANGED","PLAYER_ALIVE","PLAYER_UNGHOST","PLAYER_MONEY","CHAT_MSG_COMBAT_XP_GAIN"}
-- What killed you, from the combat log. Midnight-era clients (WoW Forever,
-- Retail) forbid it: registering alone raises a "blocked action" dialog, and
-- pcall cannot stop that. Deaths there show the zone only.
if A.combat_log ~= false then table.insert(EVENTS, "COMBAT_LOG_EVENT_UNFILTERED") end
for _,event in ipairs(EVENTS) do
    if not C_EventUtils or not C_EventUtils.IsEventValid or S.call(C_EventUtils.IsEventValid,event)==true then
        pcall(frame.RegisterEvent,frame,event)
    end
end
frame:SetScript("OnEvent", function(_, event, ...)
    if event == "ADDON_LOADED" then
        if current then registerSettings();WoWStatusMinimap.init(WoWStatusDB) end
        return
    end
    -- Marks where a login's traffic starts in the debug log (#188).
    if event == "PLAYER_LOGIN" then S.debug("login") end
    if event == "PLAYER_LOGIN" or event == "PLAYER_ENTERING_WORLD" or event == "PLAYER_REGEN_ENABLED" then
        if not current then initialize()
        elseif event == "PLAYER_REGEN_ENABLED" or event == "PLAYER_ENTERING_WORLD" then
            if event == "PLAYER_ENTERING_WORLD" then WoWStatusPopups.learnOwnName() end
            local level = A.level()
            if level then H.sync(current, level, S.now()) end
            snapshot()
        end
        return
    end
    if not current then return end
    if event == "PLAYER_LOGOUT" then
        WoWStatusRecaps.logout()
        scrub()
    elseif event == "PLAYER_LEVEL_UP" then
        local level = S.number(...)
        if level and level >= 1 and level <= A.max_level and current.settings.fields.level then
            local maxLevel = A.max_level
            local event = queue("level", {level = level, maximum = level == maxLevel})
            if event and current.settings.fields.playtime then
                pendingPlayedLevel = event
                A.requestPlaytime()
            end
        end
    elseif event == "PLAYER_EQUIPMENT_CHANGED" then
        local slot=S.number(...)
        local item=slot and A.equipment(slot)
        if slot and slot>=1 and slot<=19 and item then
            WoWStatusLoot.capture(item,function(info)
                if A.equipment(slot)~=item then return end
                current.equipped_items=current.equipped_items or {}
                local key=tostring(info.item_id)
                if not current.equipped_items[key] then
                    current.equipped_items[key]=true
                    if WoWStatusLoot.allowed(current.settings,info) then
                        info.first_equip=true
                        local event=queue("loot",info)
                        if event and WoWStatusRoster.itemDetails then WoWStatusRoster.itemDetails(event) end
                    end
                end
            end)
        end
        snapshot() -- Keep the profile current without an equipment notification.
    elseif event == "ZONE_CHANGED_NEW_AREA" then
        local zone = A.zone()
        local first=WoWStatusProgress.visitZone(current,zone)
        if first and current.last_zone and zone~=current.last_zone then queue("zone",{zone=zone}) end
        if zone then current.last_zone = zone end
        snapshot()
    elseif event == "PLAYER_DEAD" then
        local hardcore = WoWStatusProgress.hardcore()
        if current.settings.enabled and current.settings.collection.death and WoWStatusProgress.death(current, hardcore) then
            -- A Hardcore death carries its own fixed text instead of a death total (#163).
            local data = hardcore and {hardcore=true}
                or current.settings.fields.deaths and {total_deaths=WoWStatusProgress.totalDeaths(current)} or {}
            local now = S.uptime()
            if lastHit and now - lastHit.at <= 5 then data.killer = lastHit.name end
            lastHit = nil
            local event = queue("death", data)
            if event and WoWStatusRoster.deathDetails then WoWStatusRoster.deathDetails(event) end
        end
    elseif event == "COMBAT_LOG_EVENT_UNFILTERED" then
        trackHit()
    elseif event == "PLAYER_ALIVE" or event == "PLAYER_UNGHOST" then
        -- PLAYER_ALIVE also fires on spirit release, while the player is still a ghost.
        -- Unlatching then would let a later PLAYER_DEAD recount the same death. An
        -- unavailable API clears the latch so death counting can never get stuck.
        local still_dead = S.call(UnitIsDeadOrGhost, "player")
        if not (still_dead == true or still_dead == 1) then current.death_latched = false end
    elseif event == "PLAYER_XP_UPDATE" then WoWStatusRecaps.activity(); snapshot()
    elseif event == "QUEST_QUERY_COMPLETE" or event == "QUEST_LOG_UPDATE" then
        WoWStatusProgress.queryComplete(); snapshot(); questMilestone(); WoWStatusRoster.refreshQuests()
    elseif event == "QUEST_TURNED_IN" then
        local id = S.number(...)
        if current.settings.enabled and current.settings.fields.quests then
            WoWStatusProgress.quest(current,id)
            snapshot()
            questMilestone()
            WoWStatusRoster.refreshQuests()
        end
    elseif event == "SKILL_LINES_CHANGED" then
        if current.settings.enabled and current.settings.fields.professions then
            for _, profession in ipairs(WoWStatusProgress.professionChanges(current)) do
                queue("profession", {name=profession.name, skill=profession.skill, max_skill=profession.max_skill, title=profession.title, learned=profession.learned})
            end
            WoWStatusJournal.professions(current.progress.professions)
        end
        snapshot()
    elseif event == "PLAYER_MONEY" then
        WoWStatusProgress.money(current)
    elseif event == "CHAT_MSG_COMBAT_XP_GAIN" then
        WoWStatusProgress.kill(current, ...)
    elseif event == "TIME_PLAYED_MSG" then
        if current.settings.enabled and current.settings.fields.playtime then
            local total, thisLevel = ...
            total, thisLevel = S.number(total), S.number(thisLevel)
            local level = A.level()
            if total and total >= 0 then playtime, playtimeRecordedAt = total, S.now() end
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
    local command, rest = message:match(S.SPLIT_WORD)
    -- What is shared (#152) needs no character: it describes the addon itself.
    if command == "privacy" then WoWStatusPrivacy.show(); return end
    if not current then
        -- The main window's pages need a ready character; say how many errors wait.
        if command == "errors" or command == "diagnostics" then
            say(WoWStatusLocale.F("WoW Status errors recorded: %d. They can be read here once the character is ready.",
                #WoWStatusDiagnostics.errors()))
        end
        say(A.display_name .. " character is not ready or identity is currently restricted."); return
    end
    if command == "groups" then
        if rest == "legacy" then
            current.group_ids = {}
            current.legacy_upload = true
            S.stampExport(current)
            WoWStatusPopups.groupsChanged()
            say("Legacy single-service upload selected. Only use with your own configured /link credentials.")
        else openSettings("groups") end
    elseif command == "milestones" then
        -- Milestone choices live on the main page; there is no separate Milestones page.
        openSettings()
        say("Milestone choices are on the main WoW Status page.")
    elseif command == "discover" or command == "dungeon" or command == "lfg" then
        say("Manual announcements have been removed. Milestones are detected automatically.")
    elseif command == "previews" then openSettings("previews")
    elseif command == "screenshot" then
        if not WoWStatusScreenshots.available() then say("Screenshots are not available in this client.")
        elseif not WoWStatusScreenshots.manual(current.settings) then say("A screenshot is already being taken.") end
    elseif command == "discord" and WoWStatusFeatures.discord then openSettings("discord")
    elseif command == "share" then WoWStatusShare.send(rest)
    elseif command == "minimap" then
        if rest == "" then say(WoWStatusMinimap.report())
        elseif rest == "reset" then WoWStatusMinimap.setOffset(nil); say("Minimap button distance reset.")
        -- Hiding the button is safe: the slash command stays, so say so (#177).
        elseif rest == "hide" or rest == "show" then
            WoWStatusMinimap.setVisible(rest == "show")
            if rest == "hide" then say(T("Minimap button hidden.") .. " " .. T(WoWStatusMinimap.WAYS))
            else say("Minimap button shown.") end
        -- A word is not a distance: without the guard, tonumber(rest) is nil and
        -- setOffset(nil) would quietly reset the distance instead.
        elseif tonumber(rest) and WoWStatusMinimap.setOffset(tonumber(rest)) then say("Minimap button distance set to " .. rest .. ".")
        else say("Usage: /wstatus minimap [hide | show | distance " .. WoWStatusMinimap.MIN_OFFSET .. " to " .. WoWStatusMinimap.MAX_OFFSET .. " | reset]") end
    elseif command == "controller" or command == "gamepad" then
        local choice = rest:lower()
        if choice == "on" or choice == "off" then WoWStatusGamepad.setAllowed(choice == "on")
        elseif choice ~= "" then say("Usage: /wstatus controller [on | off]"); return end
        say(WoWStatusGamepad.report())
    elseif command == "errors" or command == "diagnostics" then WoWStatusDiagnostics.show()
    elseif command == "labs" then WoWStatusLabs.show()

    elseif command == "compare" then WoWStatusCompare.show(rest ~= "" and rest or nil)

    elseif command == "together" then WoWStatusTogether.show()
    elseif command == "guide" then WoWStatusGuide.show()
    elseif command == "tour" then WoWStatusGuide.tour()
    elseif command == "news" then WoWStatusWhatsNew.show()
    elseif command == "mutes" or command == "muted" then WoWStatusMutes.show()
    elseif command == "goal" or command == "goals" then WoWStatusGoals.show()
    elseif command == "when" then WoWStatusWhenWePlay.show()
    elseif command == "sync" then say("Activity syncs automatically when group members log in.")
    elseif command == "journal" or command == "friends" or command == "activity" then WoWStatusPopups.showActivity()
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
        say("Sharing paused.")
    elseif command == "test" then
        queue("level", {level = 10, synthetic = true})
        say("Synthetic level 10 event requested; requires sharing, level field and level storage.")
    elseif command == "language" then
        local lang = rest:lower()
        if WoWStatusLocale.set(lang) then
            say("Language: " .. WoWStatusLocale.LANGUAGES[lang] .. ". Type /reload to change every window.")
        else
            local codes={}
            for _,choice in ipairs(WoWStatusLocale.options()) do codes[#codes+1]=choice.value end
            say(WoWStatusLocale.T("Use /wstatus language").." "..table.concat(codes,"|")..".")
        end
    elseif command == "personality" then
        -- Caption personality: /wstatus personality <name> (either language), or the list.
        local P = WoWStatusPersonalities
        local id = (rest or "") ~= "" and P.find(rest)
        if id then
            P.set(id)
            say(T("Caption personality:") .. " " .. P.name(id) .. ".")
        else
            say(T("Caption personalities:") .. " " .. P.names() .. ". " .. T("Use /wstatus personality <name>."))
        end
    elseif command == "voice" then
        -- Reaction voice: /wstatus voice <name> (either language), or the list.
        local P = WoWStatusPersonalities
        local id = (rest or "") ~= "" and P.findReaction(rest)
        if id then
            P.setReaction(id)
            say(T("Reaction voice:") .. " " .. P.name(id) .. ".")
        else
            say(T("Reaction voices:") .. " " .. P.reactionNames() .. ". " .. T("Use /wstatus voice <name>."))
        end
    elseif command == "voicetest" then
        -- Spoken reactions (Forever): hear a recorded line as a friend's reaction
        -- would sound, without a friend. /wstatus voicetest [voice] [level|zone]
        local V, P = WoWStatusVoices, WoWStatusPersonalities
        local text, voice
        if V then text, voice = V.simulate(rest) end
        if text then
            say(T("Spoken reaction test:") .. " " .. P.name(voice) .. ": " .. text)
        elseif voice == "busy" then
            say("A voice is already playing.")
        else
            say("No recorded voice to test here. Spoken reactions are for WoW Forever.")
        end
    elseif command == "debug" then
        local value = rest:lower()
        if value == "on" or value == "off" then
            WoWStatusDB.debug = value == "on" or nil
            if value == "on" then WoWStatusDB.debug_log = {} end
            say("Debug log " .. value .. (value == "on" and ". Type /reload to save it for reading." or "."))
        else
            say("Use /wstatus debug on or /wstatus debug off.")
        end
    elseif command == "popupsize" then
        if WoWStatusTheme.setPopupSize(rest) then
            say("Notification size: " .. WoWStatusTheme.popupSize() .. "%.")
            WoWStatusPopups.sample("level")
        else
            say("Notification size is now " .. WoWStatusTheme.popupSize() .. "%. Use /wstatus popupsize "
                .. WoWStatusTheme.POPUP_MIN .. "-" .. WoWStatusTheme.POPUP_MAX .. " (100 is the default).")
        end
    elseif command == "quiethours" then
        -- Quiet hours (#180): /wstatus quiethours [on | off | 22:00-07:00].
        local P, choice = WoWStatusPopups, S.trim(rest):lower()
        local from, to = S.trim(rest):match("^([^%-]+)%-([^%-]+)$")
        local start, stop = P.parseClock(from), P.parseClock(to)
        if choice == "on" or choice == "off" then P.setQuietHours("enabled", choice == "on")
        elseif start and stop then
            P.setQuietHours("start", start); P.setQuietHours("stop", stop); P.setQuietHours("enabled", true)
        elseif choice ~= "" then say("Usage: /wstatus quiethours [on | off | 22:00-07:00]"); return end
        local hours = P.quietHours()
        say(T(hours.enabled and "Quiet hours on (local time):" or "Quiet hours off:") .. " "
            .. P.clockText(hours.start) .. "-" .. P.clockText(hours.stop))
        if hours.enabled and hours.start == hours.stop then say("Same start and end: never quiet") end
        if WoWStatusStatusLine and WoWStatusStatusLine.update then WoWStatusStatusLine.update() end
    elseif command == "popuptime" then
        local P = WoWStatusPopups
        if rest ~= "" and P.setDuration(rest) then
            say(P.duration() == 0 and "Notifications now stay until dismissed."
                or WoWStatusLocale.F("Notifications now stay for %d seconds.", P.duration()))
            P.sample("level")
        else
            say(P.duration() == 0 and "Notifications stay until dismissed."
                or WoWStatusLocale.F("Notifications stay for %d seconds.", P.duration()))
            say(WoWStatusLocale.F("Use /wstatus popuptime %d-%d, or 0 to keep notifications until dismissed (%d is the default).",
                P.DURATION_MIN, P.DURATION_MAX, P.DURATION_DEFAULT))
        end
    elseif command == "interval" or command == "quality" then
        local number = tonumber(rest)
        local key = command == "interval" and "level_interval" or "loot_quality"
        if WoWStatusSettings.valid(key, number) and WoWStatusSettings.set(key, number, current) then
            if command=="quality" then
                current.settings.loot_rarities={rare=number<=3,epic=number<=4,legendary=number<=5}
            end
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
            local name = S.trim(rawName)
            if #name > 0 and #name <= 50 and #names < 6 then
                table.insert(names, {name = name, source = "player_entered"})
            end
        end
        current.professions = names
        snapshot()
        say("Shared profession labels updated. /reload to export.")
    elseif WoWStatusMainWindow.has(command) then WoWStatusMainWindow.show(command)
    else openSettings() end
end

if C_Timer and C_Timer.NewTicker then C_Timer.NewTicker(30, snapshot) end
