-- Experimental Classic channel transport. No HTTP, hidden chat or delivery promises.
WoWStatusPopups = {}
local P = WoWStatusPopups
local prefs, getCharacter, notify, toast, active
local incoming, outgoing, senderTimes = {}, {}, {}
local lastDisplay, lastAttempt = 0, 0
local joinedByAddon, syncPending = {}, false
local frame = CreateFrame("Frame")
local PREFIX = "WSTATUS1"

local function realm()
    local value = GetNormalizedRealmName and GetNormalizedRealmName() or GetRealmName()
    return value:gsub("%s", "")
end
function P.senderKey(sender)
    if type(sender) ~= "string" or #sender == 0 or #sender > 120 or sender:find("[%c|]") then return nil end
    if not sender:find("-", 1, true) then sender = sender .. "-" .. realm() end
    return sender:gsub("%s", ""):lower()
end
local function combat()
    return InCombatLockdown and InCombatLockdown()
end
local function canShare(character)
    return prefs and prefs.broadcast and character and character.settings.enabled
        and character.settings.fields.level and character.settings.collection.level
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
    local id, actual = GetChannelName(name)
    if type(id) ~= "number" or id < 1 or type(actual) ~= "string" or actual:lower() ~= name:lower() then return nil end
    return id
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
    for key, at in pairs(senderTimes) do if now - at > 600 then senderTimes[key] = nil end end
end

function P.init(database, getter, reporter)
    database.popups = database.popups or {
        receive = false, broadcast = false, sound = false, channel = "WStatusFriends",
        trusted = {}, seen = {},
    }
    prefs, getCharacter, notify = database.popups, getter, reporter
    prefs.trusted, prefs.seen = prefs.trusted or {}, prefs.seen or {}
    prefs.channel = prefs.channel or "WStatusFriends"
    clear()
    pruneSeen(time())
    syncPending = true
    syncGroups()
end

function P.receive(text, sender, channel)
    if not prefs or not prefs.receive or type(text) ~= "string" or #text > 160
        or type(channel) ~= "string" then return false end
    local group = channels()[channel:lower()]
    if not group then return false end
    local key = P.senderKey(sender)
    local selfKey = P.senderKey(UnitName("player") .. "-" .. realm())
    if not key or key == selfKey or (group == "legacy" and not prefs.trusted[key]) then return false end
    local levelText, atText, nonce = text:match("^" .. PREFIX .. " LEVEL (%d+) (%d+) ([%w%-]+)$")
    local level, at, now = tonumber(levelText), tonumber(atText), time()
    if not level or level < 2 or level > 60 or not at or not nonce or #nonce > 64
        or at < now - 120 or at > now + 300 then return false end
    pruneSeen(now)
    local duplicateKey = key .. ":" .. level
    if prefs.seen[duplicateKey] or (senderTimes[key] and now - senderTimes[key] < 3)
        or #incoming >= 20 then return false end
    prefs.seen[duplicateKey], senderTimes[key] = now, now
    table.insert(incoming, {sender = sender, key = key, level = level, received_at = now,
        group_id = group ~= "legacy" and group or nil})
    P.tick()
    return true
end

local function show(item, now)
    if not toast then
        toast = CreateFrame("Frame", "WoWStatusLevelPopup", UIParent)
        toast:SetSize(480, 100)
        toast:SetPoint("TOP", 0, -150)
        toast:SetFrameStrata("DIALOG")
        local bg = toast:CreateTexture(nil, "BACKGROUND")
        bg:SetAllPoints()
        bg:SetColorTexture(.03, .10, .16, .95)
        toast.heading = toast:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
        toast.heading:SetPoint("TOP", 0, -14)
        toast.heading:SetText("A friend leveled up!")
        toast.message = toast:CreateFontString(nil, "OVERLAY", "GameFontHighlightLarge")
        toast.message:SetPoint("CENTER", 0, -4)
        toast.message:SetWidth(450)
        toast.detail = toast:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
        toast.detail:SetPoint("BOTTOM", 0, 12)
    end
    local alias = not item.preview and prefs.trusted[item.key]
    local name = item.sender:match("^[^-]+") or item.sender
    if type(alias) == "string" and alias ~= "" then name = alias .. "’s " .. name end
    toast.message:SetText(name .. " reached level " .. item.level .. "!")
    toast.detail:SetText(item.preview and "Local preview — not sent or saved as progress"
        or ("Reported in " .. (item.group_id and ("group " .. ((WoWStatusGroups.selected(getCharacter())[item.group_id] or {}).label or item.group_id)) or "your legacy channel") .. " · player-reported"))
    toast:Show()
    item.hide_at = now + 6
    active, lastDisplay = item, now
    if prefs.sound and PlaySound and SOUNDKIT and SOUNDKIT.IG_MAINMENU_OPEN then
        PlaySound(SOUNDKIT.IG_MAINMENU_OPEN)
    end
end

function P.tick()
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
    if #outgoing == 0 or now - lastAttempt < 5 then return end
    local item, character = outgoing[1], getCharacter()
    if not canShare(character) or now - item.at > 120
        or (item.group_id and not WoWStatusGroups.contains(character, item.group_id)) then
        table.remove(outgoing, 1)
        status("cancelled_or_expired", item.event)
        return
    end
    if not joined(item.group_id) then status("not_joined", item.event); return end
    local restricted = C_ChatInfo and C_ChatInfo.InChatMessagingLockdown
    if restricted then
        local ok, locked = pcall(restricted)
        if not ok or locked then status("chat_restricted", item.event); return end
    end
    local send = C_ChatInfo and C_ChatInfo.SendChatMessage or SendChatMessage
    if not send then status("unsupported_api", item.event); return end
    lastAttempt = now
    table.remove(outgoing, 1)
    local ok, result = pcall(send, item.message, "CHANNEL", nil, tostring(joined(item.group_id)))
    -- A call returning successfully is not a receipt of delivery. Do not blind-retry errors.
    status(ok and result ~= false and "attempted_no_receipt" or "blocked_or_uncertain", item.event)
    if not ok or result == false then notify("Popup broadcast blocked/uncertain; see /wstatus popup status.") end
end

function P.broadcast(character, event)
    if not canShare(character) or not event or event.kind ~= "level" or event.data.synthetic then return end
    if event.data.level < 2 or event.data.level > 60 or #outgoing >= 10 then return end
    local nonce = character.epoch .. "-" .. character.sequence
    local text = PREFIX .. " LEVEL " .. event.data.level .. " " .. event.at .. " " .. nonce
    local groups = WoWStatusGroups.selected(character)
    for id in pairs(groups) do
        if #outgoing < 10 and event.group_ids and event.group_ids[id] then
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
    if prefs and not canShare(getCharacter()) then
        outgoing = {}
        if prefs.last_send then status("disabled_by_character_privacy") end
    end
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
        notify(prefs.broadcast and "Broadcasts enabled for shared characters with level collection. Channel messages are visible."
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
        else prefs.trusted[key] = nil; senderTimes[key] = nil end
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
            notify("Group channel " .. id .. ": joined=" .. tostring(joined(id) ~= nil))
        end
        notify("Last broadcast: " .. (prefs.last_send and prefs.last_send.state or "none")
            .. ". Delivery is not acknowledged. Character privacy gates outgoing levels.")
    else
        notify("Popup commands: on | off | send on/off | sound on/off | channel WStatusNAME")
        notify("Trust: trust Character-Realm [friend label] | untrust Character-Realm. Test: test. Diagnostics: status.")
    end
end

frame:RegisterEvent("CHAT_MSG_CHANNEL")
frame:RegisterEvent("PLAYER_REGEN_ENABLED")
frame:RegisterEvent("PLAYER_REGEN_DISABLED")
frame:SetScript("OnEvent", function(_, event, ...)
    if event == "CHAT_MSG_CHANNEL" then
        local text, sender, _, _, _, _, _, _, channel = ...
        P.receive(text, sender, channel)
    else P.tick() end
end)
local accumulated = 0
frame:SetScript("OnUpdate", function(_, elapsed)
    accumulated = accumulated + elapsed
    if accumulated >= .25 then accumulated = 0; P.tick() end
end)
