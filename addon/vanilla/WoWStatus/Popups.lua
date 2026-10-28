-- In-game group updates. Custom channels discover peers; addon whispers carry data.
WoWStatusPopups = {}
local P = WoWStatusPopups
local A, S = WoWStatusAdapter, WoWStatusSafe
local prefs, getCharacter, notify, toast, active
local incoming, outgoing = {}, {}
local lastDisplay, lastAttempt = 0, 0
local joinedByAddon, syncPending = {}, false
local frame = CreateFrame("Frame")
local PREFIX = "WSTATUS1"
local ADDON_PREFIX = "WoWStatus"
local rosterRequested = {}
local activityPanel
local refreshActivity

local function realm()
    local value = A.realmName()
    return value and value:gsub("%s", "") or ""
end
function P.senderKey(sender)
    sender = S.string(sender)
    if type(sender) ~= "string" or #sender == 0 or #sender > 120 or sender:find("[%c|]") then return nil end
    if not sender:find("-", 1, true) then sender = sender .. "-" .. realm() end
    return sender:gsub("%s", ""):lower()
end
local function combat()
    return InCombatLockdown and InCombatLockdown()
end
local function canShare(character, event)
    if not (prefs and prefs.broadcast and character and character.settings.enabled) then return false end
    if not event then return true end
    if not character.settings.collection[event.kind] then return false end
    if character.settings.in_game and character.settings.in_game[event.kind] == false then return false end
    if event.kind == "level" and not character.settings.fields.level then return false end
    if event.kind == "zone" and not character.settings.fields.zone then return false end
    if event.kind == "equipment" and not character.settings.fields.gear then return false end
    return true
end
local function channels()
    local result = {}
    if not prefs then return result end
    local character = getCharacter()
    local groups = WoWStatusGroups.selected(character)
    for id in pairs(groups) do
        if WoWStatusGroups.valid(id) then result[WoWStatusGroups.channel(id):lower()] = id end
    end
    if not next(result) and prefs.legacy_channel then result[prefs.channel:lower()] = "legacy" end
    return result
end
local function joined(group)
    if not prefs or not GetChannelName then return nil end
    local name = group and WoWStatusGroups.channel(group) or prefs.channel
    if not channels()[name:lower()] then return nil end
    local id, actual = S.call(GetChannelName, name)
    if type(id) ~= "number" or id < 1 or type(actual) ~= "string" or actual:lower() ~= name:lower() then return nil end
    return id
end
-- channelIndex here is the display index, not the numbered /chat shortcut.
function P.peers(group)
    local peers, seen = {}, {}
    if not GetNumDisplayChannels or not GetChannelDisplayInfo then return peers end
    local count = S.number(S.call(GetNumDisplayChannels))
    local getter = C_ChatInfo and C_ChatInfo.GetChannelRosterInfo or GetChannelRosterInfo
    if not count or not getter then return peers end
    local expected = WoWStatusGroups.channel(group):lower()
    for index = 1, math.min(count, 128) do
        local ok, name, header, _, _, members = pcall(GetChannelDisplayInfo, index)
        name, members = S.string(name), S.number(members)
        if ok and name and name:lower() == expected and S.value(header) == false then
            if SetSelectedDisplayChannel and (not rosterRequested[group] or time() - rosterRequested[group] >= 30) then
                rosterRequested[group] = time()
                local previous = S.number(S.call(GetSelectedDisplayChannel))
                pcall(SetSelectedDisplayChannel, index)
                if previous and previous ~= index then pcall(SetSelectedDisplayChannel, previous) end
            end
            for member = 1, math.min(members or 0, 64) do
                local target = S.string(S.call(getter, index, member))
                local key = target and P.senderKey(target)
                local own = P.senderKey((A.playerName() or "") .. "-" .. realm())
                if key and key ~= own and not seen[key] then
                    seen[key] = true; table.insert(peers, target)
                end
            end
            break
        end
    end
    return peers
end
local function remember(item)
    if item.preview then return end
    prefs.activity = prefs.activity or {}
    table.insert(prefs.activity, 1, {sender = item.sender, level = item.level,
        kind = item.kind or "level", text = item.text, at = time(), group_id = item.group_id})
    while #prefs.activity > 200 do table.remove(prefs.activity) end
    if refreshActivity then refreshActivity() end
end
function P.groupsChanged()
    if not prefs then return end
    prefs.legacy_channel = false
    local allowed = channels()
    for name in pairs(joinedByAddon) do
        if not allowed[name] then
            if LeaveChannelByName then pcall(LeaveChannelByName, name) end
            joinedByAddon[name] = nil
        end
    end
    local kept = {}
    for _, item in ipairs(incoming) do
        if item.preview or (item.group_id and WoWStatusGroups.contains(getCharacter(), item.group_id)) then
            table.insert(kept, item)
        end
    end
    incoming = kept
    if active and not active.preview and not WoWStatusGroups.contains(getCharacter(), active.group_id) then
        active = nil
        if toast then toast:Hide() end
    end
    kept = {}
    for _, item in ipairs(outgoing) do
        if item.group_id and WoWStatusGroups.contains(getCharacter(), item.group_id) then table.insert(kept, item) end
    end
    outgoing, syncPending = kept, true
    local history = {}
    for _, item in ipairs(prefs.activity or {}) do
        if item.group_id and WoWStatusGroups.contains(getCharacter(), item.group_id) then table.insert(history, item) end
    end
    prefs.activity = history
    if refreshActivity then refreshActivity() end
end
local function syncGroups()
    if not syncPending or combat() then return end
    syncPending = false
    for id in pairs(WoWStatusGroups.selected(getCharacter())) do
        if WoWStatusGroups.valid(id) and not joined(id) and JoinTemporaryChannel then
            local name = WoWStatusGroups.channel(id)
            local ok = pcall(JoinTemporaryChannel, name)
            if ok then joinedByAddon[name:lower()] = true end
        end
    end
end
local function status(state, event)
    prefs.last_send = {state = state, at = time(), event_id = event and event.id or nil}
end
local function clear()
    incoming, outgoing, active = {}, {}, nil
    if toast then toast:Hide() end
end
local function pruneSeen(now)
    local count, oldest, oldestAt = 0, nil, math.huge
    for key, at in pairs(prefs.seen) do
        if type(at) ~= "number" or now - at > 600 or at > now + 300 then prefs.seen[key] = nil
        else
            count = count + 1
            if at < oldestAt then oldest, oldestAt = key, at end
        end
    end
    if count >= 256 and oldest then prefs.seen[oldest] = nil end

end

function P.init(database, getter, reporter)
    database.popups = database.popups or {
        receive = true, broadcast = true, sound = false, channel = "WStatusFriends",
        trusted = {}, seen = {},
    }
    prefs, getCharacter, notify = database.popups, getter, reporter
    prefs.trusted, prefs.seen = prefs.trusted or {}, prefs.seen or {}
    prefs.level_claims = prefs.level_claims or {}
    prefs.channel = prefs.channel or "WStatusFriends"
    prefs.activity = prefs.activity or {}
    if not database.in_game_primary then
        prefs.receive, prefs.broadcast = true, true
        database.in_game_primary = true
    end
    local register = C_ChatInfo and C_ChatInfo.RegisterAddonMessagePrefix or RegisterAddonMessagePrefix
    if register then pcall(register, ADDON_PREFIX) end
    clear()
    pruneSeen(time())
    syncPending = true
    syncGroups()
end

function P.receive(text, sender, channel)
    text, sender, channel = S.string(text), S.string(sender), S.string(channel)
    if not prefs or not prefs.receive or type(text) ~= "string" or #text > 220
        or type(channel) ~= "string" then return false end
    local group = channels()[channel:lower()]
    if not group then return false end
    local key = P.senderKey(sender)
    local selfKey = P.senderKey((A.playerName() or "") .. "-" .. realm())
    if not key or key == selfKey or (group == "legacy" and not prefs.trusted[key]) then return false end
    local client, kind, atText, nonce, encoded = text:match("^WSTATUS3 ([%w%-]+) (%a+) (%d+) ([%w%-]+) ([a-f0-9]+)$")
    if client then
        local allowed = {introduction=true, loot=true, equipment=true, death=true, zone=true, session=true, lfg=true}
        local at, now = tonumber(atText), time()
        if client ~= A.client_id or not allowed[kind] or #nonce > 64 or #encoded > 96
            or #encoded % 2 ~= 0 or at < now - 120 or at > now + 300 then return false end
        local detail = encoded:gsub("..", function(pair) return string.char(tonumber(pair, 16)) end)
        if detail:find("[%c]") then return false end
        pruneSeen(now)
        local duplicate = key .. ":" .. nonce
        if prefs.seen[duplicate] or #incoming >= 128 then return false end
        prefs.seen[duplicate] = now
        local item = {sender=sender, key=key, kind=kind, text=detail, received_at=now,
            group_id=group ~= "legacy" and group or nil}
        remember(item)
        table.insert(incoming, item)
        P.tick()
        return true
    end
    local client, levelText, atText, nonce = text:match("^WSTATUS2 ([%w%-]+) LEVEL (%d+) (%d+) ([%w%-]+)$")
    if not client and A.client_id == "classic-era" then
        levelText, atText, nonce = text:match("^" .. PREFIX .. " LEVEL (%d+) (%d+) ([%w%-]+)$")
        if levelText then client = "classic-era" end
    end
    if client ~= A.client_id then return false end
    local level, at, now = tonumber(levelText), tonumber(atText), time()
    if not level or level < 2 or level > A.max_level or not at or not nonce or #nonce > 64
        or at < now - 120 or at > now + 300 then return false end
    pruneSeen(now)
    local duplicateKey = key .. ":" .. level
    local claims = prefs.level_claims[key]
    if prefs.seen[duplicateKey] or (claims and claims.levels[level]) then return false end
    local waiting
    for _, item in ipairs(incoming) do
        if item.level and item.key == key and item.group_id == (group ~= "legacy" and group or nil) then waiting = item; break end
    end
    -- Distinct rapid levels are queued/coalesced, not rejected as implausibly fast.
    if not waiting and #incoming >= 128 then return false end
    if not claims then
        local count, oldest, oldestAt = 0, nil, math.huge
        for senderKey, value in pairs(prefs.level_claims) do
            count = count + 1
            if value.at < oldestAt then oldest, oldestAt = senderKey, value.at end
        end
        if count >= 512 and oldest then prefs.level_claims[oldest] = nil end
        claims = {levels = {}, at = now}
        prefs.level_claims[key] = claims
    end
    claims.levels[level], claims.at = true, now
    prefs.seen[duplicateKey] = now
    if waiting then
        waiting.level = math.max(waiting.level, level)
        waiting.count = (waiting.count or 1) + 1
        waiting.received_at = now
    else
        table.insert(incoming, {sender = sender, key = key, level = level, received_at = now,
            count = 1, group_id = group ~= "legacy" and group or nil})
    end
    remember({sender=sender, level=level, group_id=group ~= "legacy" and group or nil})
    P.tick()
    return true
end

local function show(item, now)
    if not toast then
        toast = CreateFrame("Frame", "WoWStatusLevelPopup", UIParent)
        toast:SetSize(560, 108)
        toast:SetPoint("TOP", 0, -170)
        toast:SetFrameStrata("DIALOG")
        local bg = toast:CreateTexture(nil, "BACKGROUND")
        bg:SetAllPoints(); bg:SetColorTexture(.025, .035, .065, .96)
        toast.accent = toast:CreateTexture(nil, "OVERLAY")
        toast.accent:SetPoint("TOPLEFT"); toast.accent:SetSize(560, 3)
        toast.icon = toast:CreateTexture(nil, "ARTWORK")
        toast.icon:SetPoint("TOPLEFT", 18, -22); toast.icon:SetSize(64, 64)
        toast.glow = toast:CreateTexture(nil, "OVERLAY")
        toast.glow:SetTexture("Interface\\Buttons\\UI-ActionButton-Border")
        toast.glow:SetPoint("CENTER", toast.icon, "CENTER"); toast.glow:SetSize(112, 112)
        toast.glow:SetBlendMode("ADD")
        toast.heading = toast:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
        toast.heading:SetPoint("TOPLEFT", 104, -14); toast.heading:SetWidth(438)
        toast.heading:SetJustifyH("LEFT")
        toast.message = toast:CreateFontString(nil, "OVERLAY", "GameFontHighlightLarge")
        toast.message:SetPoint("TOPLEFT", 104, -38); toast.message:SetWidth(438)
        toast.message:SetJustifyH("LEFT")
        toast.detail = toast:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
        toast.detail:SetPoint("BOTTOMLEFT", 104, 12); toast.detail:SetWidth(438)
        toast.detail:SetJustifyH("LEFT")
        toast:SetScript("OnUpdate", function(self, elapsed)
            self.age = (self.age or 0) + elapsed
            local entrance = math.min(1, self.age / .22)
            local fade = math.max(0, math.min(1, (6 - self.age) / .5))
            self:SetAlpha(entrance * fade)
            self:ClearAllPoints(); self:SetPoint("TOP", 0, -170 - (1 - entrance) * 12)
            self.glow:SetAlpha(.5 + .3 * math.sin(self.age * 7))
            if self.age >= 6 then self:Hide(); active = nil end
        end)
    end
    local alias = not item.preview and prefs.trusted[item.key]
    local name = item.sender:match("^[^-]+") or item.sender
    if type(alias) == "string" and alias ~= "" then name = alias .. "’s " .. name end
    name = name:gsub("|", "||")
    local themes = {
        level={"Spell_Holy_BlessingOfStrength",1,.82,.2,"LEVEL UP!"},
        loot={"INV_Misc_Bag_10",.72,.35,1,"LOOT FOUND"},
        equipment={"INV_Chest_Plate04",.3,.7,1,"GEAR CHANGED"},
        death={"Ability_Rogue_FeignDeath",.95,.18,.2,"A FRIEND HAS FALLEN"},
        zone={"INV_Misc_Map_01",.25,.9,.6,"ON THE MOVE"},
        session={"Spell_Arcane_TeleportStormWind",.4,.7,1,"FRIEND UPDATE"},
        lfg={"INV_Misc_Head_Human_01",.2,.85,1,"LOOKING FOR GROUP"},
        introduction={"INV_Misc_Head_Human_01",.9,.75,.4,"WELCOME, ADVENTURER!"},
    }
    local theme = themes[item.level and "level" or item.kind] or themes.session
    toast.icon:SetTexture("Interface\\Icons\\" .. theme[1])
    toast.glow:SetVertexColor(theme[2], theme[3], theme[4])
    toast.accent:SetColorTexture(theme[2], theme[3], theme[4], 1)
    toast.heading:SetTextColor(theme[2], theme[3], theme[4]); toast.heading:SetText(theme[5])
    local detail = item.level and ("reached level " .. item.level .. "!"
        .. ((item.count or 1) > 1 and (" (" .. item.count .. " recorded level-ups)") or ""))
        or ((item.text or "Shared an update"):gsub("|", "||"))
    toast.message:SetText(name .. (item.level and " " or " — ") .. detail)
    toast.detail:SetText(item.preview and "Local preview — not sent or saved as progress"
        or ("Reported in " .. (item.group_id and ("group " .. ((WoWStatusGroups.selected(getCharacter())[item.group_id] or {}).label or item.group_id)) or "your legacy channel") .. " · player-reported"))
    toast.age = 0
    toast:SetAlpha(0)
    toast:Show()
    item.hide_at = now + 6
    active, lastDisplay = item, now
    if prefs.sound and PlaySound and SOUNDKIT and SOUNDKIT.IG_MAINMENU_OPEN then
        PlaySound(SOUNDKIT.IG_MAINMENU_OPEN)
    end
end

local function tick()
    if not prefs then return end
    local now = time()
    syncGroups()
    if not prefs.receive then
        incoming, active = {}, nil
        if toast then toast:Hide() end
    end
    if active and not active.preview and not (active.group_id
        and WoWStatusGroups.contains(getCharacter(), active.group_id)) and not prefs.trusted[active.key] then
        active = nil
        if toast then toast:Hide() end
    end
    if combat() then
        if active then
            table.insert(incoming, 1, active)
            active = nil
            if toast then toast:Hide() end
        end
        return
    end
    if active and now >= active.hide_at then active = nil; if toast then toast:Hide() end end
    if prefs.receive and not active and #incoming > 0 and now - lastDisplay >= 7 then
        local item = table.remove(incoming, 1)
        if now - item.received_at <= 600 and (item.preview or (item.group_id and WoWStatusGroups.contains(getCharacter(), item.group_id))
            or prefs.trusted[item.key]) then show(item, now) end
    end
    if #outgoing == 0 or now - lastAttempt < 1 then return end
    local item, character = outgoing[1], getCharacter()
    if not canShare(character, item.event) or now - item.at > 120
        or (item.group_id and not WoWStatusGroups.contains(character, item.group_id)) then
        table.remove(outgoing, 1)
        status("cancelled_or_expired", item.event)
        return
    end
    if not joined(item.group_id) then status("not_joined", item.event); return end
    if A.chatRestricted() then status("chat_restricted", item.event); return end
    local send, args
    if item.group_id then
        send = C_ChatInfo and C_ChatInfo.SendAddonMessage or SendAddonMessage
        if not send then status("unsupported_addon_whispers", item.event); return end
        if not item.targets then
            local targets = P.peers(item.group_id)
            if #targets == 0 then status("waiting_for_group_peers", item.event); return end
            item.targets, item.target = targets, 1
        end
        args = {ADDON_PREFIX, item.group_id .. " " .. item.message, "WHISPER", item.targets[item.target]}
    else
        send = A.chatSender()
        if not send then status("unsupported_api", item.event); return end
        args = {item.message, "CHANNEL", nil, tostring(joined(item.group_id))}
    end
    lastAttempt = now
    local unpackArgs = unpack or table.unpack
    local ok, result = pcall(send, unpackArgs(args, 1, 4))
    result = S.value(result)
    if item.targets and item.target < #item.targets then item.target = item.target + 1
    else table.remove(outgoing, 1) end
    local accepted = ok and result ~= false
    if type(result) == "number" then
        accepted = ok and Enum and Enum.SendAddonMessageResult and result == Enum.SendAddonMessageResult.Success
    end
    status(accepted and "attempted_no_receipt" or "blocked_or_uncertain", item.event)
    if not accepted then notify("In-game update blocked/uncertain; see /wstatus popup status.") end
end

local ticking = false
function P.tick()
    if ticking then return end
    ticking = true
    local ok, problem = pcall(tick)
    ticking = false
    if not ok then error(problem) end
end

local function eventText(event)
    local data = event.data or {}
    if event.kind == "introduction" then return "Joined the tracker" end
    if event.kind == "death" then return "Died" end
    if event.kind == "session" then return data.state == "addon_loaded" and "Started a session" or "Ended a session" end
    if event.kind == "zone" then return "Entered " .. (data.zone or "a new zone") end
    if event.kind == "lfg" then return "LFG: " .. (data.text or "") end
    if event.kind == "loot" or event.kind == "equipment" then
        local item = data.item and data.item:match("%[([^%]]+)%]") or "an item"
        return (event.kind == "loot" and "Looted " or "Equipped ") .. item
    end
end
function P.broadcast(character, event)
    if not event or not canShare(character, event) or event.data.synthetic or #outgoing >= 32 then return end
    local nonce = character.epoch .. "-" .. character.sequence
    local text
    if event.kind == "level" then
        if event.data.level < 2 or event.data.level > A.max_level then return end
        text = "WSTATUS2 " .. A.client_id .. " LEVEL " .. event.data.level .. " " .. event.at .. " " .. nonce
    else
        if event.kind == "loot" and (event.data.quality or 0) < character.settings.loot_quality then return end
        local detail = eventText(event)
        if not detail then return end
        detail = detail:gsub("[%c]", " ")
        if #detail > 48 then
            detail = detail:sub(1, 45):gsub("[\194-\244][\128-\191]*$", "") .. "..."
        end
        local encoded = detail:gsub(".", function(char) return string.format("%02x", char:byte()) end)
        text = "WSTATUS3 " .. A.client_id .. " " .. event.kind .. " " .. event.at .. " " .. nonce .. " " .. encoded
    end
    if #text > 220 then return end
    local groups = WoWStatusGroups.selected(character)
    for id in pairs(groups) do
        if #outgoing < 32 and event.group_ids and event.group_ids[id] then
            table.insert(outgoing, {message = text, at = event.at, event = event, group_id = id})
        end
    end
    if not next(groups) and prefs.legacy_channel then
        table.insert(outgoing, {message = text, at = event.at, event = event})
    end
    status(#outgoing > 0 and "queued" or "no_group_selected", event)
    P.tick()
end

function P.privacyChanged()
    if not prefs then return end
    local kept = {}
    for _, item in ipairs(outgoing) do
        if canShare(getCharacter(), item.event) then table.insert(kept, item) end
    end
    outgoing = kept
    if not canShare(getCharacter()) and prefs.last_send then status("disabled_by_character_privacy") end
end

local function activityLabel(parent, text, x, y, width)
    local label = parent:CreateFontString(nil, "OVERLAY", "GameFontHighlightLarge")
    label:SetPoint("TOPLEFT", x, y); label:SetWidth(width); label:SetJustifyH("LEFT"); label:SetText(text)
    return label
end
refreshActivity = function()
    if not activityPanel then return end
    local lines = {}
    for i, item in ipairs(prefs.activity or {}) do
        if i > 75 then break end
        local group = item.group_id and WoWStatusGroups.selected(getCharacter())[item.group_id]
        if group or not item.group_id then
            local detail = item.level and ("reached level " .. item.level) or item.text or "shared an update"
            local text = WoWStatusHistory.oslo(item.at) .. " · " .. item.sender .. " — " .. detail
                .. (group and (" [" .. group.label .. "]") or "")
            table.insert(lines, (text:gsub("|", "||")))
        end
    end
    activityPanel.text:SetText(#lines > 0 and table.concat(lines, "\n\n")
        or "No group updates received yet.\n\nChoose the same group ID as your friends. You must be online and able to communicate in WoW. No companion or Discord account is needed.")
    activityPanel.child:SetHeight(math.max(340, activityPanel.text:GetStringHeight() + 30))
    local state = prefs.last_send and prefs.last_send.state or "No update sent yet"
    activityPanel.status:SetText("Receive: " .. tostring(prefs.receive) .. " · Send: " .. tostring(prefs.broadcast)
        .. " · " .. state .. "\nGroups: " .. WoWStatusGroups.text(getCharacter()))
end
function P.showActivity()
    if not prefs then return end
    if not activityPanel then
        activityPanel = CreateFrame("Frame", "WoWStatusActivity", UIParent)
        activityPanel:SetSize(720, 560); activityPanel:SetPoint("CENTER")
        activityPanel:SetFrameStrata("FULLSCREEN_DIALOG"); activityPanel:EnableMouse(true)
        activityPanel:SetMovable(true); activityPanel:RegisterForDrag("LeftButton")
        activityPanel:SetScript("OnDragStart", activityPanel.StartMoving)
        activityPanel:SetScript("OnDragStop", activityPanel.StopMovingOrSizing)
        local bg = activityPanel:CreateTexture(nil, "BACKGROUND")
        bg:SetAllPoints(); bg:SetColorTexture(.04, .04, .07, .98)
        activityLabel(activityPanel, "WoW Status — group activity", 24, -20, 670)
        activityPanel.status = activityLabel(activityPanel, "", 24, -55, 670)
        activityPanel.scroll = CreateFrame("ScrollFrame", nil, activityPanel, "UIPanelScrollFrameTemplate")
        activityPanel.scroll:SetPoint("TOPLEFT", 24, -120); activityPanel.scroll:SetSize(650, 370)
        activityPanel.child = CreateFrame("Frame", nil, activityPanel.scroll)
        activityPanel.child:SetSize(620, 350); activityPanel.scroll:SetScrollChild(activityPanel.child)
        activityPanel.text = activityLabel(activityPanel.child, "", 0, 0, 620)
        for i, entry in ipairs({{"Refresh", function() refreshActivity() end},
            {"Diagnostics", function() P.command("status") end}, {"Close", function() activityPanel:Hide() end}}) do
            local button = CreateFrame("Button", nil, activityPanel, "UIPanelButtonTemplate")
            button:SetPoint("TOPLEFT", 24 + (i - 1) * 160, -515); button:SetSize(140, 28)
            button:SetText(entry[1]); button:SetScript("OnClick", entry[2])
        end
        table.insert(UISpecialFrames, "WoWStatusActivity")
    end
    refreshActivity(); activityPanel:Show()
end

function P.command(text)
    if not prefs then return end
    local command, rest = text:match("^(%S*)%s*(.-)$")
    if command == "on" then prefs.receive = true; notify("Popup reception enabled for your selected group IDs. Use /wstatus groups to choose them.")
    elseif command == "off" then
        prefs.receive, prefs.broadcast = false, false
        clear()
        status("disabled")
        notify("Popup reception and broadcasts are off.")
    elseif command == "send" and (rest == "on" or rest == "off") then
        prefs.broadcast = rest == "on"
        if not prefs.broadcast then outgoing = {} end
        notify(prefs.broadcast and "Broadcasts enabled for shared characters with level collection. Group updates use addon whispers; both players must be reachable in WoW."
            or "Popup broadcasts disabled.")
    elseif command == "sound" and (rest == "on" or rest == "off") then
        prefs.sound = rest == "on"
        notify("Popup sound " .. rest .. ".")
    elseif command == "channel" and rest:match("^WStatus[%w]+$") and #rest <= 30 then
        if next(WoWStatusGroups.selected(getCharacter())) then
            notify("Group IDs control popup channels. Edit /wstatus groups instead."); return
        end
        clear()
        prefs.channel, prefs.legacy_channel = rest, true
        notify("Channel selected. Join it yourself with /join " .. rest .. ". Everyone must choose the same channel.")
    elseif command == "trust" or command == "untrust" then
        local sender, alias = rest:match("^(%S+)%s*(.-)$")
        local key = P.senderKey(sender)
        if not key or #alias > 40 or alias:find("[%c|]") then notify("Use trust Character-Realm [optional friend label]."); return end
        if command == "trust" then
            local count = 0
            for _ in pairs(prefs.trusted) do count = count + 1 end
            if count >= 200 and not prefs.trusted[key] then notify("Trust list is full."); return end
            prefs.trusted[key] = alias ~= "" and alias or true
        else prefs.trusted[key] = nil end
        notify("Trust preference updated for " .. sender .. ".")
        P.tick()
    elseif command == "test" then
        if not prefs.receive then notify("Enable reception with /wstatus popup on first."); return end
        if #incoming < 20 then
            table.insert(incoming, {sender = "Preview", key = "local-preview", level = 25,
                received_at = time(), preview = true})
            P.tick()
        end
    elseif command == "status" then
        notify("Popups: receive=" .. tostring(prefs.receive) .. ", broadcast=" .. tostring(prefs.broadcast)
            .. ", sound=" .. tostring(prefs.sound) .. ", channel=" .. prefs.channel
            .. ", groups=" .. WoWStatusGroups.text(getCharacter()) .. ".")
        for id in pairs(WoWStatusGroups.selected(getCharacter())) do
            notify("Group " .. id .. ": joined=" .. tostring(joined(id) ~= nil) .. ", discovered peers=" .. #P.peers(id))
        end
        notify("Last broadcast: " .. (prefs.last_send and prefs.last_send.state or "none")
            .. ". Delivery is not acknowledged. Character privacy gates outgoing levels.")
    else
        notify("Popup commands: on | off | send on/off | sound on/off | channel WStatusNAME")
        notify("Trust: trust Character-Realm [friend label] | untrust Character-Realm. Test: test. Diagnostics: status.")
    end
end

frame:RegisterEvent("CHAT_MSG_CHANNEL")
frame:RegisterEvent("CHAT_MSG_ADDON")
frame:RegisterEvent("CHANNEL_ROSTER_UPDATE")
frame:RegisterEvent("PLAYER_REGEN_ENABLED")
frame:RegisterEvent("PLAYER_REGEN_DISABLED")
frame:SetScript("OnEvent", function(_, event, ...)
    if not prefs or not getCharacter then return end
    if event == "CHAT_MSG_ADDON" then
        local prefix, text, distribution, sender = ...
        prefix, text, distribution = S.string(prefix), S.string(text), S.string(distribution)
        if prefix ~= ADDON_PREFIX or distribution ~= "WHISPER" or not text or #text > 243 then return end
        local group, message = text:match("^([a-f0-9]+) (.+)$")
        if group and WoWStatusGroups.valid(group) and WoWStatusGroups.contains(getCharacter(), group) then
            P.receive(message, sender, WoWStatusGroups.channel(group))
        end
    elseif event == "CHAT_MSG_CHANNEL" then
        local text, sender, _, _, _, _, _, _, channel = ...
        P.receive(text, sender, channel)
    else P.tick() end
end)
local accumulated = 0
frame:SetScript("OnUpdate", function(_, elapsed)
    accumulated = accumulated + elapsed
    if accumulated >= .25 then accumulated = 0; P.tick() end
end)
