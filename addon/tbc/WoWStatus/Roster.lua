-- Character list grouped by player, with portraits (#59).
-- Each account has a random player ID and uses the existing player name
-- (Options > Groups). At login, and when a new group member comes online, the
-- account's characters that have logged in with the addon are whispered to
-- the group's members on the WoWStatusChr prefix:
--   C <group> <playerID> <playerName|-> <Name-Realm> <RACE> <sex> <CLASS> <level>
--   X <group> <playerID>        (stop sharing: forget this player's list)
-- Receivers accept only known members of a joined group and strictly
-- validated fields. Nothing is sent when sharing the list is turned off.
WoWStatusRoster = {}
local R, S = WoWStatusRoster, WoWStatusSafe
local T, TF = WoWStatusLocale.T, WoWStatusLocale.F
-- A heading as shown: names stay, the English parts are translated.
local function shownTitle(title)
    if WoWStatusLocale.lang() == "en" then return title end
    title = title:gsub("^Not announced", T("Not announced")):gsub("^Unnamed player", T("Unnamed player"))
    title = title:gsub(" %(you%)", " (" .. T("you") .. ")")
    title = title:gsub("%((%d+) characters?%)", function(n) return "(" .. n .. " " .. T(n == "1" and "character" or "characters") .. ")" end)
    return title
end
-- "NightElf" as "Night Elf", or its Nynorsk name.
local function shownRace(race)
    local spaced = race:gsub("(%l)(%u)", "%1 %2")
    return T(spaced)
end
local PREFIX = "WoWStatusChr"
local MAX_PLAYERS, MAX_CHARACTERS = 64, 20
local CLASSES = {WARRIOR=true, PALADIN=true, HUNTER=true, ROGUE=true, PRIEST=true, DEATHKNIGHT=true, SHAMAN=true,
    MAGE=true, WARLOCK=true, MONK=true, DRUID=true, DEMONHUNTER=true, EVOKER=true}
local db, current, page, report
-- A roster line for the debug log, its group name left out.
local function redacted(text)
    local op, rest = tostring(text):match("^(" .. S.NONSPACE .. "+) " .. S.NONSPACE .. "+(.*)$")
    return op and (op .. " <group>" .. rest) or "?"
end
local outgoing, sentTo, lastSend, lastScan = {}, {}, 0, 0
local lastXp, xpSent, statsSent = 0, nil, nil
-- The Sync button: usable once a minute; list requests answered once a minute per member.
R.SYNC_COOLDOWN = 60
local syncedAt, answered = nil, {}
-- Members asked for their list this session (at first contact), and /who lookups.
local requested, whoAsked = {}, {}
local XP_INTERVAL = 300

-- One key per character for the list. WoW Forever spreads characters over many
-- internal realms ("CAMWOWEU4Realm3PvE") while chat and rosters name them without
-- a realm, and full names are unique there: the realm is left out, so "Annie Fett"
-- and "Annie Fett-CAMWOWEU5Realm3PvE" are one character (they were listed twice).
local function key(name)
    if WoWStatusAdapter.full_names then
        local short = S.string(name) and name:match("^([^-]+)")
        if not short or #short > 120 or short:find(S.CONTROL_OR_PIPE) then return nil end
        short = S.lowerASCII(S.stripSpace(short))
        return short ~= "" and short or nil
    end
    return WoWStatusPopups.senderKey(name)
end
R.key = key
R.shownRace = function(race) return shownRace(race) end

local function state()
    db.roster = type(db.roster) == "table" and db.roster or {}
    db.roster.players = type(db.roster.players) == "table" and db.roster.players or {}
    if type(db.roster.id) ~= "string" or not db.roster.id:match("^[0-9a-f]+$") or #db.roster.id ~= 16 then
        local digits = {}
        for i = 1, 16 do digits[i] = string.format("%x", math.random(0, 15)) end
        db.roster.id = table.concat(digits)
    end
    if db.roster.share == nil then db.roster.share = true end
    return db.roster
end

-- Who in a group reached a level milestone and when, from synced lists and this
-- account's own characters: {name, at, exact}.
function R.milestoneHolders(group, level)
    local list = {}
    if not db or not current or not WoWStatusGroups.selected(current)[group] then return list end
    for _, c in pairs(db.characters or {}) do
        if c.identity and c.identity.client == WoWStatusAdapter.client_id and type(c.roster_info) == "table" then
            local item = R.milestones(c)[level]
            local name = WoWStatusPopups.characterName(c)
            if item and WoWStatusPopups.fullName(name) then table.insert(list, {name=name, at=item.at, exact=item.exact}) end
        end
    end
    for _, player in pairs(state().players) do
        if type(player.groups) == "table" and player.groups[group] then
            for _, character in pairs(player.characters) do
                local item = type(character.milestones) == "table" and character.milestones[level]
                if type(item) == "table" and S.number(item.at) and WoWStatusPopups.fullName(character.name) then
                    table.insert(list, {name=character.name, at=item.at, exact=item.exact == true})
                end
            end
        end
    end
    return list
end

-- A friend running a newer version than this one: told once per version and
-- session in chat, and shown on the Overview. The game cannot reach CurseForge,
-- so it points to the homepage, which has a release at once.
local announcedVersions = {}
local function versionParts(text)
    local a, b, c = tostring(text or ""):match("^(%d+)%.(%d+)%.(%d+)$")
    return a and {tonumber(a), tonumber(b), tonumber(c)} or nil
end
function R.isNewer(version, than)
    local x, y = versionParts(version), versionParts(than)
    if not x or not y then return false end
    for i = 1, 3 do if x[i] ~= y[i] then return x[i] > y[i] end end
    return false
end
-- The newest version seen among friends, if newer than this one.
function R.newerVersion()
    local own, best = WoWStatusPopups.runtimeVersion, nil
    for _, player in pairs(db and state().players or {}) do
        local version = S.string(player.version)
        if version and R.isNewer(version, own) and (not best or R.isNewer(version, best)) then best = version end
    end
    return best
end
function R.checkNewer(version)
    local own = WoWStatusPopups.runtimeVersion
    if not R.isNewer(version, own) or announcedVersions[version] or not report then return false end
    announcedVersions[version] = true
    report("WoW Status " .. version .. " " .. T("is available") .. " (" .. T("you have") .. " " .. own .. "). "
        .. T("Get it at wow.frankvalde.com; the CurseForge app can take a few hours."))
    return true
end

-- The player name a friend chose (Options > Groups > "Your name"), from the
-- character lists they announced; nil when unknown or for this account.
function R.playerOf(sender)
    local k = db and key(sender)
    if not k then return nil end
    for _, player in pairs(state().players) do
        if player.characters[k] and S.string(player.name) then return player.name end
    end
    return nil
end
-- "Unshaved Brittlebeard (Frank)": the character as the game names it, and the
-- player behind it when they chose a name that adds something.
function R.displayName(sender)
    local short = tostring(sender or "?"):match("^[^-]+") or tostring(sender or "?")
    local player = R.playerOf(sender)
    if not player then return short end
    local first = S.lowerASCII(short:match("^(" .. S.NONSPACE .. "+)") or short)
    if S.lowerASCII(player) == S.lowerASCII(short) or S.lowerASCII(player) == first then return short end
    return short .. " (" .. player .. ")"
end

-- Race, sex and class of a member whose list never arrived (older versions), from
-- the GUID their channel roster entry carries: the game's own lookup, the same one
-- its unit menus use. Saved per name, so it still shows after they log off. The
-- game does not give a level this way.
local MAX_IDENTIFIED = 200
local function identify(name)
    local roster, k = state(), key(name)
    if not k then return nil end
    roster.identified = type(roster.identified) == "table" and roster.identified or {}
    local guid = WoWStatusPopups.guidFor and WoWStatusPopups.guidFor(name)
    if guid and GetPlayerInfoByGUID then
        local ok, _, class, _, race, sex = pcall(GetPlayerInfoByGUID, guid)
        class, race, sex = ok and S.string(class), ok and S.string(race), ok and S.number(sex)
        if class and CLASSES[class] and race and race:match("^[A-Za-z]+$") and (sex == 2 or sex == 3) then
            if not roster.identified[k] then
                local count, oldest, oldestAt = 0, nil, math.huge
                for id, item in pairs(roster.identified) do
                    count = count + 1; if (item.at or 0) < oldestAt then oldest, oldestAt = id, item.at or 0 end
                end
                if count >= MAX_IDENTIFIED and oldest then roster.identified[oldest] = nil end
            end
            roster.identified[k] = {class=class, race=race, sex=sex, at=time()}
        end
    end
    local item = roster.identified[k]
    return type(item) == "table" and item or nil
end
R.identify = identify

-- Public facts about the logged-in character, saved for the list.
function R.observe(character)
    if not character then return end
    local _, race = S.call(UnitRace, "player")
    local _, class = S.call(UnitClass, "player")
    local level = WoWStatusAdapter.level()
    local xp, maximum = S.number(S.call(UnitXP, "player")), S.number(S.call(UnitXPMax, "player"))
    -- Progress through the level in thousandths; none at the maximum level.
    local permille = xp and maximum and maximum > 0 and xp >= 0 and xp <= maximum
        and not (level and level >= (WoWStatusAdapter.max_level or 999)) and math.min(999, math.floor(xp / maximum * 1000)) or nil
    -- Total deaths, saved so other characters' cards keep their last known total.
    local deaths = character.settings and character.settings.fields.deaths and WoWStatusProgress.totalDeaths
        and S.number(WoWStatusProgress.totalDeaths(character)) or nil
    -- Gold, gold earned, kills and played time, each only with its field on.
    local fields = character.settings and character.settings.fields or {}
    local P = WoWStatusProgress
    if fields.gold and P.money then P.money(character) end
    local gold = fields.gold and character.progress and S.number(character.progress.gold) or nil
    local earned = fields.gold and P.goldEarned and P.goldEarned(character) or nil
    local kills = fields.kills and P.totalKills and P.totalKills(character) or nil
    local played = fields.playtime and character.snapshot and S.number(character.snapshot.playtime) or nil
    local extras = fields.collection and P.extras and P.extras(character) or {}
    character.roster_info = {race=S.string(race), sex=S.number(S.call(UnitSex, "player")), class=S.string(class),
        level=level, xp=permille, deaths=deaths, gold=gold, earned=earned, kills=kills, played=played,
        honor_kills=extras.honor_kills, dungeons=extras.dungeons, mounts=extras.mounts, at=time()}
end

local function playerName()
    local name = S.string(db.player_name)
    if name and #name >= 1 and #name <= 24 and not name:find(S.CONTROL_OR_PIPE) and not name:find(S.SPACE) then return name end
    return nil
end

-- This account's listed characters on this client, as message bodies.
-- When each of a character's level milestones (every 10 levels and the maximum)
-- was reached: {[level]={at, exact}}. Exact from its own level-ups (or Retail
-- level achievements); otherwise, for levels reached before WoW Status tracked
-- it, the time tracking began, meaning "by then". Records use these, so a member
-- who joined later still holds a level record reached long before (synced in "M").
function R.milestoneLevels()
    local list, maximum = {}, WoWStatusAdapter.max_level or 60
    for level = 10, maximum, 10 do table.insert(list, level) end
    if maximum % 10 ~= 0 then table.insert(list, maximum) end
    return list
end
-- Records ask for these per group and level, so each character's scan of the
-- log is reused within the same second.
local milestoneCache, milestoneAt = setmetatable({}, {__mode="k"}), nil
function R.milestones(c)
    local now = time()
    if milestoneAt ~= now then milestoneCache, milestoneAt = setmetatable({}, {__mode="k"}), now end
    if milestoneCache[c] then return milestoneCache[c] end
    local result = R.scanMilestones(c)
    milestoneCache[c] = result
    return result
end
function R.scanMilestones(c)
    local result, info = {}, c.roster_info
    local current = type(info) == "table" and S.number(info.level) or nil
    local exact = {}
    for _, event in ipairs(c.history and c.history.events or {}) do
        local level = event.kind == "level" and type(event.data) == "table" and not event.data.synthetic and S.number(event.data.level)
        if level and S.number(event.at) and (not exact[level] or event.at < exact[level]) then exact[level] = event.at end
    end
    for _, e in ipairs(WoWStatusJournal.entries()) do
        local level = e.kind == "level" and e.owner == c.identity.guid and e.client == c.identity.client and S.number(e.level)
        if level and S.number(e.at) and (not exact[level] or e.at < exact[level]) then exact[level] = e.at end
    end
    local start = type(c.tracking_start) == "table" and S.number(c.tracking_start.at) or (type(info) == "table" and S.number(info.at))
    for _, level in ipairs(R.milestoneLevels()) do
        if exact[level] then result[level] = {at=math.floor(exact[level]), exact=true}
        elseif current and current >= level and start then result[level] = {at=math.floor(start), exact=false} end
    end
    return result
end

-- "gold earned kills played" for an "S" line, or nil when none is shared.
local STAT_LIMIT = 1e12
local function numbers(info, keys)
    local values, any = {}, false
    for _, k in ipairs(keys) do
        local v = S.number(info[k])
        if v and v >= 0 and v < STAT_LIMIT and v == math.floor(v) then values[#values + 1] = tostring(v); any = true
        else values[#values + 1] = "-" end
    end
    return any and table.concat(values, " ") or nil
end
function R.statsLine(info) return numbers(info, {"gold", "earned", "kills", "played"}) end
-- "honor_kills dungeons mounts" for a "Q" line.
function R.extrasLine(info) return numbers(info, {"honor_kills", "dungeons", "mounts"}) end
local function ownLines(group)
    local roster, lines = state(), {}
    for _, c in pairs(db.characters or {}) do
        local info = c.roster_info
        -- WoW Forever: a character whose full name is not learnt yet would arrive as
        -- a first name only, which members drop; it is sent once the name is known.
        if type(info) == "table" and c.identity and c.identity.client == WoWStatusAdapter.client_id and not c.hide_from_list
            and info.race and (info.sex == 2 or info.sex == 3) and CLASSES[info.class] and S.number(info.level)
            and WoWStatusPopups.fullName(WoWStatusPopups.characterName(c)) then
            -- A message is split on spaces; WoW Forever names have one ("Edith Aateigen").
            -- Character names cannot contain "_", so it stands for a space here.
            local name = (WoWStatusPopups.characterName(c):gsub(" ", "_"))
            table.insert(lines, table.concat({"C", group, roster.id, playerName() or "-", name, info.race, info.sex, info.class, info.level}, " "))
            -- XP progress goes in its own line, which older versions ignore.
            if S.number(info.xp) then table.insert(lines, table.concat({"P", group, roster.id, name, info.xp}, " ")) end
            -- Gold, gold earned, kills and played seconds ("-" when not shared); older versions ignore it.
            local stats = R.statsLine(info)
            if stats then table.insert(lines, table.concat({"S", group, roster.id, name, stats}, " ")) end
            local extras = R.extrasLine(info)
            if extras then table.insert(lines, table.concat({"Q", group, roster.id, name, extras}, " ")) end
            -- Level milestones with their times, for records ("e" exact, "a" by then).
            for level, item in pairs(R.milestones(c)) do
                table.insert(lines, table.concat({"M", group, roster.id, name, level, item.at, item.exact and "e" or "a"}, " "))
            end
        end
    end
    -- Listed groups (the account ticked Listed), name in hex; older versions ignore "G".
    if #lines > 0 then
        for id, name in pairs(WoWStatusGroups.listed and WoWStatusGroups.listed() or {}) do
            if id ~= group then
                local hex = name:gsub(".", function(c) return string.format("%02x", c:byte()) end)
                table.insert(lines, table.concat({"G", group, roster.id, hex}, " "))
            end
        end
    end
    -- The addon version, once per list; older versions ignore this line.
    local version = WoWStatusPopups.runtimeVersion
    if #lines > 0 and type(version) == "string" and version:match("^%d+%.%d+%.%d+$") then
        table.insert(lines, table.concat({"V", group, roster.id, version}, " "))
    end
    table.sort(lines)
    return lines
end

local function enqueue(group, target)
    local peerKey = key(target)
    if not peerKey then return end
    sentTo[group] = sentTo[group] or {}
    if sentTo[group][peerKey] then return end
    sentTo[group][peerKey] = true
    if not state().share then return end
    for _, line in ipairs(ownLines(group)) do table.insert(outgoing, {target=target, text=line}) end
end

-- Members seen in a group's channel roster, saved so everyone in the group is
-- listed: also members on older versions that never send a usable list and
-- have nothing in the log (their join was announced long ago, or never).
local MAX_SEEN = 200
local function noteSeen(group, name)
    local k = key(name)
    if not k or not WoWStatusPopups.fullName(name) or WoWStatusPopups.isSelf(name) then return end
    local roster = state()
    roster.seen = type(roster.seen) == "table" and roster.seen or {}
    local item = roster.seen[k]
    if not item then
        local count, oldest, oldestAt = 0, nil, math.huge
        for id, other in pairs(roster.seen) do
            count = count + 1; if (other.at or 0) < oldestAt then oldest, oldestAt = id, other.at or 0 end
        end
        if count >= MAX_SEEN and oldest then roster.seen[oldest] = nil end
        item = {groups={}}
        roster.seen[k] = item
    end
    item.name, item.at = name, time()
    item.groups = type(item.groups) == "table" and item.groups or {}
    item.groups[group] = true
end
R.noteSeen = noteSeen

-- Details of this character's death for its groups' members online now.
function R.deathDetails(event)
    if not db or not current or type(event) ~= "table" or type(event.data) ~= "table" then return end
    local nonce = WoWStatusPopups.eventNonce(event)
    local function encode(text)
        text = S.string(text)
        if not text or #text > 48 or text:find(S.CONTROL_OR_PIPE) then return "-" end
        return (text:gsub(" ", "_"))
    end
    local zone, killer = encode(event.data.zone), encode(event.data.killer)
    if not nonce or (zone == "-" and killer == "-") then return end
    for group in pairs(event.group_ids or {}) do
        if WoWStatusGroups.selected(current)[group] then
            for _, peer in ipairs(WoWStatusPopups.peers(group)) do
                table.insert(outgoing, {target=peer, text=table.concat({"K", group, state().id, nonce, zone, killer}, " ")})
            end
        end
    end
end

-- The full item of a first armor equip (suffix, enchant) for its groups' members.
function R.itemDetails(event)
    if not db or not current or type(event) ~= "table" or type(event.data) ~= "table" then return end
    local nonce = WoWStatusPopups.eventNonce(event)
    local item = WoWStatusJournal.itemString(event.data.item)
    if not nonce or not item then return end
    for group in pairs(event.group_ids or {}) do
        if WoWStatusGroups.selected(current)[group] then
            for _, peer in ipairs(WoWStatusPopups.peers(group)) do
                table.insert(outgoing, {target=peer, text=table.concat({"I", group, state().id, nonce, item}, " ")})
            end
        end
    end
end

-- Send to group members not yet told this session (also after a change).
local lastPeers = {}
function R.scan()
    if not db or not current then return end
    local index = 0
    for group in pairs(WoWStatusGroups.selected(current)) do
        index = index + 1
        local names = table.concat(WoWStatusPopups.peers(group), ", ")
        if lastPeers[group] ~= names then
            lastPeers[group] = names
            S.debug("group " .. index .. " members online: " .. (names ~= "" and names or "none"))
        end
        for _, peer in ipairs(WoWStatusPopups.peers(group)) do
            noteSeen(group, peer); enqueue(group, peer)
            -- Ask each member once a session for their list: one sent while this
            -- account was offline (a level-up) never reached it. Older versions ignore it.
            local k = key(peer)
            requested[group] = requested[group] or {}
            if k and not requested[group][k] then
                requested[group][k] = true
                table.insert(outgoing, {target=peer, text="R " .. group .. " " .. state().id})
            end
        end
    end
end

-- /who: the game's own answer gives an online member's level now, also for
-- members whose version never refreshes a list. The game allows a /who only from
-- a click, so the Sync button looks up one member each time (those without a
-- recent list first); results of a /who the player types are read too.
-- Untested live on WoW Forever: if it blocks this, remove the lookup.
local MAX_WHO = 200
local function whoLevels()
    local roster = state()
    roster.who = type(roster.who) == "table" and roster.who or {}
    return roster.who
end
local function isMember(k)
    local seen = state().seen
    if type(seen) == "table" and seen[k] then return true end
    for _, player in pairs(state().players) do
        if player.characters[k] then return true end
    end
    return false
end
function R.readWho()
    if not db then return 0 end
    local F = C_FriendList
    local count = S.number(F and F.GetNumWhoResults and S.call(F.GetNumWhoResults) or S.call(GetNumWhoResults))
    if not count then return 0 end
    local levels, learnt, maximum = whoLevels(), 0, WoWStatusAdapter.max_level or 60
    for i = 1, math.min(count, 50) do
        local name, level
        if F and F.GetWhoInfo then
            local ok, info = pcall(F.GetWhoInfo, i)
            if ok and type(info) == "table" then name, level = S.string(info.fullName), S.number(info.level) end
        elseif GetWhoInfo then
            local ok, n, _, l = pcall(GetWhoInfo, i)
            if ok then name, level = S.string(n), S.number(l) end
        end
        local k = name and key(name)
        if k and level and level == math.floor(level) and level >= 1 and level <= maximum and isMember(k) then
            if not levels[k] then
                local n, oldest, oldestAt = 0, nil, math.huge
                for id, item in pairs(levels) do n = n + 1; if (item.at or 0) < oldestAt then oldest, oldestAt = id, item.at or 0 end end
                if n >= MAX_WHO and oldest then levels[oldest] = nil end
            end
            -- The same old results are read again on later system messages: count changes only.
            if not levels[k] or levels[k].level ~= level then learnt = learnt + 1 end
            levels[k] = {level=level, at=time()}
        end
    end
    if learnt > 0 then S.debug("/who: levels learnt for " .. learnt .. " group member(s)") end
    if learnt > 0 then R.render() end
    return learnt
end
-- The online member to look up: one never looked up this session, members whose
-- version sends no list requests (or no list) first, then the oldest list.
function R.whoTarget()
    if not db or not current then return nil end
    local lists = {}
    for _, player in pairs(state().players) do
        local fresh = S.string(player.version) and R.isNewer(player.version, "1.10.99")
        for k, c in pairs(player.characters) do lists[k] = {at=S.number(c.at) or 0, fresh=fresh} end
    end
    local best, bestScore
    for group in pairs(WoWStatusGroups.selected(current)) do
        for _, peer in ipairs(WoWStatusPopups.peers(group)) do
            local k = key(peer)
            if k and not whoAsked[k] and not WoWStatusPopups.isSelf(peer) and WoWStatusPopups.fullName(peer) then
                local list = lists[k]
                local score = (list and list.fresh and 1e10 or 0) + (list and list.at or 0)
                if not bestScore or score < bestScore then best, bestScore = peer, score end
            end
        end
    end
    return best
end
function R.whoLookup()
    local target = R.whoTarget()
    local F = C_FriendList
    local send = F and F.SendWho or SendWho
    S.debug("/who lookup: " .. tostring(target) .. (send and "" or " (no SendWho)"))
    if not target or not send then return nil end
    whoAsked[key(target)] = true
    local short = target:match("^([^%-]+)")
    pcall(send, 'n-"' .. short .. '"')
    return target
end

-- Groups friends listed: {[id] = {name, by = {[player ID] = {name, at}}}}. Bounded.
local MAX_LISTINGS, LISTING_DAYS = 32, 14
local function listings()
    local roster = state()
    roster.listings = type(roster.listings) == "table" and roster.listings or {}
    return roster.listings
end
-- Listed groups to browse: not yet joined, heard of in the last 14 days, newest first.
function R.listings()
    if not db or not current then return {} end
    local list, now = {}, time()
    for id, item in pairs(listings()) do
        if type(item) == "table" and S.string(item.name) and not WoWStatusGroups.contains(current, id) then
            local names, newest = {}, 0
            for _, by in pairs(type(item.by) == "table" and item.by or {}) do
                if type(by) == "table" and (S.number(by.at) or 0) > now - LISTING_DAYS * 86400 then
                    names[#names + 1] = S.string(by.name) or "?"
                    newest = math.max(newest, by.at)
                end
            end
            if #names > 0 then
                table.sort(names)
                list[#list + 1] = {id=id, name=item.name, by=table.concat(names, ", "), at=newest}
            end
        end
    end
    table.sort(list, function(a, b) return a.at > b.at end)
    return list
end
-- Ticking or unticking Listed: members get the listing now, or are told to drop it.
function R.listingChanged(id, listed)
    if not db or not current then return end
    R.changed() -- Resends the lists (it starts a new queue, so the "U" lines follow it).
    if not listed then
        for group in pairs(WoWStatusGroups.selected(current)) do
            if group ~= id then
                for _, peer in ipairs(WoWStatusPopups.peers(group)) do
                    table.insert(outgoing, {target=peer, text=table.concat({"U", group, state().id, id}, " ")})
                end
            end
        end
    end
end

-- Friends online now (not your own characters), for the minimap tooltip.
function R.onlineNames()
    if not db or not current then return {} end
    local names, seen = {}, {}
    for _, entry in ipairs(R.groups()) do
        if not entry.self then
            for _, row in ipairs(entry.rows) do
                local k = key(row.name)
                if row.status == "online" and k and not seen[k] then
                    seen[k] = true
                    names[#names + 1] = row.name:match("^[^-]+") or row.name
                end
            end
        end
    end
    table.sort(names)
    return names
end
-- Invitations: "N <shared group> <player ID> <group name in hex>" to one online
-- member, who can join or decline. Older versions ignore it.
local invitedFrom = {}
function R.invite(name, id)
    if not db or not current then return false, "Not ready yet." end
    local member = WoWStatusGroups.selected(current)[id]
    local label = member and member.label
    if not label then return false, "That group is not in your list." end
    local via
    for group in pairs(WoWStatusGroups.selected(current)) do
        if group ~= id and WoWStatusPopups.isPeer(group, WoWStatusPopups.senderKey(name)) then via = group end
    end
    if not via then return false, "They need to be online in a group you share." end
    local hex = label:gsub(".", function(c) return string.format("%02x", c:byte()) end)
    table.insert(outgoing, {target=name, text=table.concat({"N", via, state().id, hex}, " ")})
    return true, "Invite sent."
end
-- The first version that confirms live updates (WSACK).
R.ACK_VERSION = "1.24.0"
-- A member's addon version, from their list ("1.24.0"), or nil.
function R.versionOf(name)
    local k = db and key(name)
    if not k then return nil end
    for _, player in pairs(state().players) do
        if player.characters[k] then return S.string(player.version) end
    end
    return nil
end
-- Members whose client never confirmed a live update (it was sent twice):
-- {[key] = time}. Cleared when they confirm one.
local function unreachable()
    local roster = state()
    roster.unreachable = type(roster.unreachable) == "table" and roster.unreachable or {}
    return roster.unreachable
end
function R.unreached(name)
    local k = db and key(name)
    if k then unreachable()[k] = time(); R.render() end
end
function R.reached(name)
    local k = db and key(name)
    if k and unreachable()[k] then unreachable()[k] = nil; R.render() end
end
function R.isUnreachable(name)
    local k = db and key(name)
    local at = k and unreachable()[k]
    return at ~= nil and time() - at < 86400
end

-- After a privacy change: tell everyone again (or tell them to forget us).
function R.changed()
    if not db or not current then return end
    local roster = state()
    outgoing, sentTo = {}, {}
    if not roster.share then
        for group in pairs(WoWStatusGroups.selected(current)) do
            for _, peer in ipairs(WoWStatusPopups.peers(group)) do
                table.insert(outgoing, {target=peer, text="X " .. group .. " " .. roster.id})
            end
        end
    end
    R.scan()
end

-- Seconds until the Sync button can be used again (0 when ready).
function R.syncWait()
    local now = GetTime and GetTime() or time()
    return syncedAt and math.max(0, math.ceil(R.SYNC_COOLDOWN - (now - syncedAt))) or 0
end
local function updateSyncButton()
    if not page or not page.sync then return end
    local wait = R.syncWait()
    local button = page.sync
    if button.SetEnabled then button:SetEnabled(wait == 0)
    elseif wait == 0 and button.Enable then button:Enable()
    elseif button.Disable then button:Disable() end
    button.ready = wait == 0
    page.sync:SetText(wait == 0 and T("Sync now") or TF("Sync (%d s)", wait))
end
-- Everyone online in your groups: your list again, a request for theirs, and a
-- log catch-up as at login. Once a minute.
function R.syncNow()
    if not db or not current or R.syncWait() > 0 then return false end
    syncedAt = GetTime and GetTime() or time()
    R.changed()
    for group in pairs(WoWStatusGroups.selected(current)) do
        for _, peer in ipairs(WoWStatusPopups.peers(group)) do
            table.insert(outgoing, {target=peer, text="R " .. group .. " " .. state().id})
        end
    end
    if WoWStatusJournal.syncNow then WoWStatusJournal.syncNow() end
    updateSyncButton()
    return true
end

function R.setSharing(enabled)
    state().share = enabled == true
    R.changed()
end

function R.setHidden(character, hidden)
    character.hide_from_list = hidden == true or nil
    R.changed()
end

function R.tick()
    if not db or not current then return end
    if page and page.sync and page:IsShown() then updateSyncButton() end
    local now = GetTime and GetTime() or time()
    if now - lastScan >= 30 then lastScan = now; R.scan() end
    -- XP moves between level-ups: tell members at most every five minutes.
    local info = current.roster_info
    if now - lastXp >= XP_INTERVAL then
        lastXp = now
        -- Gold, kills and played time change between level-ups: refresh them too.
        R.observe(current)
        info = current.roster_info
        local stats = info and R.statsLine(info)
        if stats and stats ~= statsSent and state().share and not current.hide_from_list then
            statsSent = stats
            local name = (WoWStatusPopups.characterName(current):gsub(" ", "_"))
            for group in pairs(WoWStatusGroups.selected(current)) do
                for _, peer in ipairs(WoWStatusPopups.peers(group)) do
                    table.insert(outgoing, {target=peer, text=table.concat({"S", group, state().id, name, stats}, " ")})
                end
            end
        end
        if info and S.number(info.xp) and info.xp ~= xpSent and state().share and not current.hide_from_list then
            xpSent = info.xp
            local name = (WoWStatusPopups.characterName(current):gsub(" ", "_"))
            for group in pairs(WoWStatusGroups.selected(current)) do
                for _, peer in ipairs(WoWStatusPopups.peers(group)) do
                    table.insert(outgoing, {target=peer, text=table.concat({"P", group, state().id, name, info.xp}, " ")})
                end
            end
        end
    end
    if #outgoing == 0 or now - lastSend < .5 or WoWStatusAdapter.chatRestricted() then return end
    local item = table.remove(outgoing, 1)
    local send = C_ChatInfo and C_ChatInfo.SendAddonMessage or SendAddonMessage
    if send then
        lastSend = now
        S.debug("send " .. redacted(item.text) .. " to " .. tostring(item.target))
        WoWStatusPopups.whispered(item.target)
        pcall(send, PREFIX, item.text, "WHISPER", item.target)
    end
end

local function valid(words, max)
    local name, race, sex, class, level = words[5], words[6], tonumber(words[7]), words[8], tonumber(words[9])
    if not name or #name > 64 or name:find(S.CONTROL_OR_PIPE) or not name:match("^[^%-]+%-[^%-]+$") then return nil end
    if not race or not race:match("^[A-Za-z][A-Za-z]+$") or #race > 24 then return nil end
    if sex ~= 2 and sex ~= 3 or not CLASSES[class] then return nil end
    if not level or level ~= math.floor(level) or level < 1 or level > max then return nil end
    return {name=name, race=race, sex=sex, class=class, level=level}
end

local receive
function R.receive(message, sender, distribution)
    local ok, why = receive(message, sender, distribution)
    if db and type(message) == "string" then
        S.debug("got " .. redacted(message) .. " from " .. tostring(sender) .. ": " .. (ok and "ok" or tostring(why or "ignored")))
    end
    return ok
end
receive = function(message, sender, distribution)
    if not db or not current or distribution ~= "WHISPER" or type(message) ~= "string" or #message > 250 then return false end
    local words = {}
    for word in message:gmatch(S.NONSPACE .. "+") do words[#words + 1] = word end
    local op, group, pid = words[1], words[2], words[3]
    if not group or not WoWStatusGroups.contains(current, group) then return false, "not one of my groups" end
    -- Membership is by full name with realm, as the member list keeps it (the
    -- roster's own key leaves the realm out on WoW Forever, and never matched).
    local member = WoWStatusPopups.senderKey(sender)
    if not WoWStatusPopups.isPeer(group, member) then
        WoWStatusPopups.peers(group) -- Refresh the member list once before rejecting.
        if not WoWStatusPopups.isPeer(group, member) then return false, "not a member (" .. tostring(member) .. ")" end
    end
    if not pid or #pid ~= 16 or not pid:match("^[0-9a-f]+$") or pid == state().id then return false, "bad player ID" end
    local players = state().players
    if op == "X" and #words == 3 then players[pid] = nil; R.render(); return true end
    -- "R": a member asks for this account's list again (their Sync button).
    if op == "R" and #words == 3 then
        local k, now = key(sender), time()
        if not k or (answered[k] and now - answered[k] < R.SYNC_COOLDOWN) then return false, "answered this minute" end
        answered[k] = now
        if sentTo[group] then sentTo[group][k] = nil end
        enqueue(group, sender)
        return true
    end
    -- "K": details of a member's death (zone, killer); "_" stands for spaces, "-" for none.
    if op == "K" and #words == 6 then
        local nonce = words[4]
        if #nonce > 64 or not nonce:match("^[%w%-]+$") then return false end
        local function decode(text) return text ~= "-" and (text:gsub("_", " ")) or nil end
        local id = WoWStatusJournal.eventID(sender, nonce)
        return id ~= nil and WoWStatusJournal.setDetails(id, decode(words[5]), decode(words[6]))
    end
    if op == "I" and #words == 5 then
        local nonce = words[4]
        if #nonce > 64 or not nonce:match("^[%w%-]+$") then return false, "bad item line" end
        local id = WoWStatusJournal.eventID(sender, nonce)
        return id ~= nil and WoWStatusJournal.setItem(id, words[5])
    end
    if op == "V" and #words == 4 then
        local version, player = words[4], players[pid]
        if not player or #version > 16 or not version:match("^%d+%.%d+%.%d+$") then return false end
        player.version = version
        R.checkNewer(version)
        R.render()
        return true
    end
    if op == "M" and #words == 7 then
        local short, realmPart = words[4]:match("^([^%-]+)%-([^%-]+)$")
        local level, at, flag, player = tonumber(words[5]), tonumber(words[6]), words[7], players[pid]
        local maximum = WoWStatusAdapter.max_level or 60
        if not short or #words[4] > 64 or words[4]:find(S.CONTROL_OR_PIPE) or not player or not level or not at
            or level ~= math.floor(level) or level < 1 or level > maximum or at ~= math.floor(at)
            or at < 1000000000 or at > S.now() + 300 or (flag ~= "e" and flag ~= "a") then return false end
        local character = player.characters[key(short:gsub("_", " ") .. "-" .. realmPart) or ""]
        if not character then return false, "unknown character" end
        character.milestones = type(character.milestones) == "table" and character.milestones or {}
        local count = 0
        for _ in pairs(character.milestones) do count = count + 1 end
        if count >= 20 and not character.milestones[level] then return false end
        character.milestones[level] = {at=at, exact=flag == "e"}
        return true
    end
    -- "G": a member listed one of their groups; "U": they unlisted it.
    if op == "N" and #words == 4 then
        local hex = words[4]
        if #hex > 160 or #hex % 2 ~= 0 or not hex:match("^[0-9a-f]+$") then return false, "bad invite" end
        local name = hex:gsub("..", function(pair) return string.char(tonumber(pair, 16)) end)
        local id, cleaned = WoWStatusGroups.key(name)
        if not id or cleaned:find(S.CONTROL_OR_PIPE) then return false, "bad group name" end
        if WoWStatusGroups.contains(current, id) then return true end -- Already a member.
        local k = key(sender)
        if k and invitedFrom[k] and time() - invitedFrom[k] < 60 then return false, "invite repeated" end
        if k then invitedFrom[k] = time() end
        local player = players[pid]
        local from = R.displayName and R.displayName(sender) or sender
        if WoWStatusProfile and WoWStatusProfile.invited then WoWStatusProfile.invited(from, cleaned) end
        return true
    end
    if op == "G" and #words == 4 then
        local hex = words[4]
        if #hex > 160 or #hex % 2 ~= 0 or not hex:match("^[0-9a-f]+$") then return false, "bad listing" end
        local name = hex:gsub("..", function(pair) return string.char(tonumber(pair, 16)) end)
        local id, cleaned = WoWStatusGroups.key(name)
        if not id or cleaned:find(S.CONTROL_OR_PIPE) then return false, "bad group name" end
        local all = listings()
        if not all[id] then
            local count, oldest, oldestAt = 0, nil, math.huge
            for k, item in pairs(all) do
                count = count + 1
                local at = 0
                for _, by in pairs(type(item) == "table" and type(item.by) == "table" and item.by or {}) do at = math.max(at, S.number(by.at) or 0) end
                if at < oldestAt then oldest, oldestAt = k, at end
            end
            if count >= MAX_LISTINGS and oldest then all[oldest] = nil end
            all[id] = {name=cleaned, by={}}
        end
        local player = players[pid]
        all[id].by[pid] = {name=(player and player.name) or (S.string(sender) and sender:match("^[^-]+")) or "?", at=time()}
        return true
    end
    if op == "U" and #words == 4 then
        local item = listings()[words[4]]
        if item and type(item.by) == "table" then
            item.by[pid] = nil
            if not next(item.by) then listings()[words[4]] = nil end
        end
        return true
    end
    if op == "Q" and #words == 7 then
        local short, realmPart = words[4]:match("^([^%-]+)%-([^%-]+)$")
        local player = players[pid]
        if not short or #words[4] > 64 or words[4]:find(S.CONTROL_OR_PIPE) or not player then return false, "bad extras line" end
        local character = player.characters[key(short:gsub("_", " ") .. "-" .. realmPart) or ""]
        if not character then return false, "unknown character" end
        for i, k in ipairs({"honor_kills", "dungeons", "mounts"}) do
            local text = words[4 + i]
            local v = tonumber(text)
            if text ~= "-" and not (v and text:match("^%d+$") and v < STAT_LIMIT) then return false, "bad extras value" end
            character[k] = v
        end
        R.render()
        return true
    end
    if op == "S" and #words == 8 then
        local short, realmPart = words[4]:match("^([^%-]+)%-([^%-]+)$")
        local player = players[pid]
        if not short or #words[4] > 64 or words[4]:find(S.CONTROL_OR_PIPE) or not player then return false, "bad stats line" end
        local character = player.characters[key(short:gsub("_", " ") .. "-" .. realmPart) or ""]
        if not character then return false, "unknown character" end
        local values = {}
        for i, k in ipairs({"gold", "earned", "kills", "played"}) do
            local text = words[4 + i]
            local v = tonumber(text)
            if text ~= "-" and not (v and v >= 0 and v < STAT_LIMIT and v == math.floor(v) and text:match("^%d+$")) then
                return false, "bad stats value"
            end
            values[k] = v
        end
        for k, v in pairs({gold=values.gold or false, earned=values.earned or false, kills=values.kills or false, played=values.played or false}) do
            character[k] = v or nil
        end
        R.render()
        return true
    end
    if op == "P" and #words == 5 then
        local short, realmPart = words[4]:match("^([^%-]+)%-([^%-]+)$")
        local permille = tonumber(words[5])
        local player = players[pid]
        if not short or #words[4] > 64 or words[4]:find(S.CONTROL_OR_PIPE) or not player or not permille
            or permille ~= math.floor(permille) or permille < 0 or permille > 999 then return false end
        local character = player.characters[key(short:gsub("_", " ") .. "-" .. realmPart) or ""]
        if not character then return false, "unknown character" end
        character.xp = permille
        R.render()
        return true
    end
    if op ~= "C" or #words ~= 9 then return false, "unknown op or length" end
    local name = words[4]
    if #name > 24 or name:find(S.CONTROL_OR_PIPE) then return false end
    local character = valid(words, WoWStatusAdapter.max_level or 60)
    if not character then return false, "invalid character line" end
    local short, realmPart = character.name:match("^([^%-]+)%-(.+)$")
    character.name = short:gsub("_", " ") .. "-" .. realmPart
    local player = players[pid]
    if not player then
        local count, oldest, oldestAt = 0, nil, math.huge
        for id, p in pairs(players) do count = count + 1; if (p.at or 0) < oldestAt then oldest, oldestAt = id, p.at or 0 end end
        if count >= MAX_PLAYERS and oldest then players[oldest] = nil end
        player = {characters={}}
        players[pid] = player
    end
    player.name, player.at = name ~= "-" and name or nil, time()
    -- Which of this account's groups the list arrived through (never other groups).
    player.groups = type(player.groups) == "table" and player.groups or {}
    player.groups[group] = true
    local characterKey = key(character.name)
    if not characterKey then return false end
    if not player.characters[characterKey] then
        local count, oldest, oldestAt = 0, nil, math.huge
        for k, c in pairs(player.characters) do count = count + 1; if (c.at or 0) < oldestAt then oldest, oldestAt = k, c.at or 0 end end
        if count >= MAX_CHARACTERS and oldest then player.characters[oldest] = nil end
    end
    character.at = time()
    player.characters[characterKey] = character
    -- A full name replaces the first-name-only entry an older client announced.
    local first = character.name:match("^([^ %-]+) [^%-]+%-")
    if first then
        local old = key(first .. "-" .. realmPart)
        if old and old ~= characterKey then player.characters[old] = nil end
    end
    R.render()
    return true
end

-- Portrait, best available first: live unit, then race/sex face, then silhouette.
local UNITS = {"target", "mouseover", "focus", "party1", "party2", "party3", "party4"}
function R.portrait(texture, name, race, sex)
    local wanted = key(name)
    for _, unit in ipairs(UNITS) do
        local unitName, realm = S.call(UnitName, unit)
        unitName, realm = S.string(unitName), S.string(realm)
        if unitName and wanted and key(unitName .. "-" .. (realm and realm ~= "" and realm or S.stripSpace(WoWStatusAdapter.realmName() or ""))) == wanted
            and SetPortraitTexture then
            if pcall(SetPortraitTexture, texture, unit) then return "live" end
        end
    end
    if race and (sex == 2 or sex == 3) then
        if texture:SetTexture("Interface\\CharacterFrame\\TemporaryPortrait-" .. (sex == 3 and "Female" or "Male") .. "-" .. race) ~= false then
            return "met"
        end
    end
    if texture:SetTexture("Interface\\CharacterFrame\\TempPortrait") == false then
        texture:SetTexture("Interface\\Icons\\INV_Misc_QuestionMark")
    end
    return "unknown"
end

local function ago(at)
    local seconds = math.max(0, time() - (at or time()))
    if seconds < 3600 then return math.floor(seconds / 60) .. "m ago" end
    if seconds < 86400 then return math.floor(seconds / 3600) .. "h ago" end
    return math.floor(seconds / 86400) .. "d ago"
end

-- Groups for the Characters page: {title, rows={{name, race, sex, class, level, status, latest}}}.
function R.groups()
    local online, latest, lastSeen, shared, deaths = {}, {}, {}, {}, {}
    local selected = WoWStatusGroups.selected(current)
    local function share(k, group)
        if k and selected[group] then shared[k] = shared[k] or {}; shared[k][group] = true end
    end
    for group in pairs(selected) do
        for _, peer in ipairs(WoWStatusPopups.peers(group)) do
            local k = key(peer)
            if k then online[k] = true; share(k, group); noteSeen(group, peer) end
        end
    end
    -- Newer levels than a member's last list: their level-ups in the log, and /who.
    local fresher = {}
    for k, item in pairs(whoLevels()) do
        if type(item) == "table" and S.number(item.level) then fresher[k] = item.level end
    end
    for _, e in ipairs(WoWStatusJournal.entries()) do
        local k = key(e.sender)
        local level = k and e.kind == "level" and S.number(e.level)
        if level and (not fresher[k] or level > fresher[k]) then fresher[k] = level end
        if k and not latest[k] and e.kind ~= "recap" then latest[k] = e.text end
        -- A friend's total deaths, from their newest death announcement.
        if k and deaths[k] == nil and e.kind == "death" then
            deaths[k] = tonumber(tostring(e.text or ""):match("^Total deaths: (%d+)$")) or false
        end
        if k and (not lastSeen[k] or e.at > lastSeen[k]) then lastSeen[k] = e.at end
    end
    -- First-name-only entries (older WoW Forever clients announced "Unshaved")
    -- show as the one full name known for them ("Unshaved Brittlebeard").
    local full = {}
    local function note(name)
        local first, rest = tostring(name or ""):match("^([^ %-]+) [^%-]+%-(.+)$")
        if first then
            local k = key(first .. "-" .. rest)
            if k then
                local seen = full[k]
                if seen == nil then full[k] = name
                elseif seen and key(seen) ~= key(name) then full[k] = false end -- Two people: don't guess.
            end
        end
    end
    for group in pairs(WoWStatusGroups.selected(current)) do
        for _, peer in ipairs(WoWStatusPopups.peers(group)) do note(peer) end
    end
    for _, e in ipairs(WoWStatusJournal.entries()) do note(e.sender) end
    for _, player in pairs(state().players) do
        for _, character in pairs(player.characters) do note(character.name) end
    end
    for _, c in pairs(db.characters or {}) do note(WoWStatusPopups.characterName(c)) end
    local function resolve(name)
        local k = key(name)
        return (k and full[k]) or name
    end
    local merged, order, known = {}, {}, {}
    local function add(title, character, self, note)
        if not self then
            character = {name=resolve(character.name), race=character.race, sex=character.sex,
                class=character.class, level=character.level, xp=character.xp, at=character.at, groups=character.groups,
                deaths=character.deaths, gold=character.gold, earned=character.earned, kills=character.kills, played=character.played,
                honor_kills=character.honor_kills, dungeons=character.dungeons, mounts=character.mounts}
            -- This account's own characters are listed only under "(you)".
            if WoWStatusPopups.isSelf(character.name) then return end
            local newer = fresher[key(character.name) or ""]
            if newer and newer > (S.number(character.level) or 0) then character.level, character.xp = newer, nil end
        end
        -- WoW Forever: first-name-only characters come from older versions; your
        -- current character stays even before its full name is known.
        if not WoWStatusPopups.fullName(character.name) and not (self and character.current) then return end
        if not self and not (character.race and character.class) then
            local known = identify(character.name)
            if known then
                character.race, character.sex, character.class = character.race or known.race,
                    character.sex or known.sex, character.class or known.class
            end
        end
        local groupKey = S.lowerASCII(title)
        local entry = merged[groupKey]
        if not entry then entry = {title=title, rows={}}; merged[groupKey] = entry; table.insert(order, entry) end
        entry.note = entry.note or note
        entry.self = entry.self or self == true
        local k = key(character.name)
        if not k or known[k] then return end
        known[k] = true
        local status = self and (k == key(WoWStatusPopups.characterName(current)) and "online" or "offline")
            or (online[k] and "online") or ("last seen " .. ago(math.max(lastSeen[k] or 0, character.at or 0)))
        -- Shared groups, by this account's own labels for them.
        local labels, ids = {}, {}
        for group in pairs(shared[k] or character.groups or {}) do
            local member = selected[group]
            if member then table.insert(labels, member.label or group); ids[group] = true end
        end
        table.sort(labels)
        table.insert(entry.rows, {name=character.name, race=character.race, sex=character.sex, class=character.class,
            level=character.level, xp=character.xp, status=status, latest=latest[k], groups=labels, groupIds=ids,
            deaths=S.number(character.deaths) or deaths[k] or nil, gold=S.number(character.gold),
            earned=S.number(character.earned), kills=S.number(character.kills), played=S.number(character.played),
            honor_kills=S.number(character.honor_kills), dungeons=S.number(character.dungeons), mounts=S.number(character.mounts)})
    end
    for _, c in pairs(db.characters or {}) do
        local info = c.roster_info
        if type(info) == "table" and c.identity and c.identity.client == WoWStatusAdapter.client_id then
            local own = WoWStatusPopups.runtimeVersion
            add((playerName() or "You") .. " (you)", {name=WoWStatusPopups.characterName(c),
                race=info.race, sex=info.sex, class=info.class, level=info.level, xp=info.xp, at=info.at,
                deaths=c == current and current.settings.fields.deaths and WoWStatusProgress.totalDeaths(current) or info.deaths,
                gold=info.gold, earned=info.earned, kills=info.kills, played=info.played,
                honor_kills=info.honor_kills, dungeons=info.dungeons, mounts=info.mounts,
                current=c == current}, true, own and own ~= "unknown" and ("v" .. own) or nil)
        end
    end
    for _, player in pairs(state().players) do
        for _, character in pairs(player.characters) do
            add(player.name or "Unnamed player", {name=character.name, race=character.race, sex=character.sex,
                class=character.class, level=character.level, xp=character.xp, at=character.at, groups=player.groups,
                gold=character.gold, earned=character.earned, kills=character.kills, played=character.played,
                honor_kills=character.honor_kills, dungeons=character.dungeons, mounts=character.mounts},
                nil, S.string(player.version) and ("v" .. player.version) or "older version")
        end
    end
    -- Senders in the log that never announced a list.
    for _, e in ipairs(WoWStatusJournal.entries()) do
        if not e.owner and e.sender and key(e.sender) and not known[key(e.sender)] then
            local groups = {}
            for group in pairs(e.groups or {}) do groups[group] = true end
            add("Not announced", {name=resolve(e.sender), at=e.at, groups=groups}, nil,
                "older version or list sharing off")
        end
    end
    -- Members seen in a group roster with neither a list nor log entries.
    for k, item in pairs(type(state().seen) == "table" and state().seen or {}) do
        local groups = {}
        for group in pairs(type(item.groups) == "table" and item.groups or {}) do
            if selected[group] then groups[group] = true end
        end
        if not known[k] and S.string(item.name) and next(groups) then
            add("Not announced", {name=item.name, at=item.at, groups=groups}, nil, "older version or list sharing off")
        end
    end
    for _, entry in ipairs(order) do
        entry.name = entry.title
        entry.title = entry.title .. " (" .. #entry.rows .. (#entry.rows == 1 and " character)" or " characters)")
        table.sort(entry.rows, function(a, b) return (a.level or 0) > (b.level or 0) end)
    end
    return order
end

-- Characters page: one bordered card per character under each player's header.
local UI = WoWStatusUI
local CARD, HEADER, GAP = 58, 26, 6
local function header(index)
    local h = CreateFrame("Frame", nil, page.list)
    h:SetSize(680, HEADER)
    h.text = UI.header(h, "", 0, -4, 680)
    page.headers[index] = h
    return h
end
local function card(index)
    local c = UI.box(page.list, 680, CARD, "Button")
    c.portrait = c:CreateTexture(nil, "ARTWORK"); c.portrait:SetPoint("TOPLEFT", 10, -9); c.portrait:SetSize(40, 40)
    c.badge = UI.levelBadge(c, 24); c.badge:SetPoint("TOPLEFT", 34, -30)
    c.name = UI.text(c, "GameFontNormalLarge", 66, -8, 300)
    c.dot = c:CreateTexture(nil, "OVERLAY"); c.dot:SetPoint("TOPLEFT", 66, -32); c.dot:SetSize(14, 14)
    c.status = UI.text(c, "GameFontHighlightSmall", 82, -33, 200)
    c.xp = UI.xpBar(c, 230, 10); c.xp:SetPoint("TOPLEFT", 66, -46)
    c.class = UI.text(c, "GameFontHighlight", 380, -10, 280, "RIGHT")
    c.latest = UI.text(c, "GameFontDisableSmall", 380, -30, 280, "RIGHT")
    c.groups = UI.text(c, "GameFontHighlightSmall", 380, -44, 280, "RIGHT")
    -- Clicking a character shows its entries on the Activity page.
    c:SetScript("OnClick", function(self)
        -- Clicking a character opens their profile (with Show activity on it).
        if self.character and WoWStatusProfile then WoWStatusProfile.show(self.character, self.player)
        elseif self.character and WoWStatusJournal.showCharacter then WoWStatusJournal.showCharacter(self.character.name) end
    end)
    c:SetScript("OnEnter", function(self)
        UI.tint(self, true)
        if GameTooltip and self.character then
            local character = self.character
            GameTooltip:SetOwner(self, "ANCHOR_RIGHT"); GameTooltip:SetText(character.name)
            -- The shared statistics in full.
            local function line(label, value) if value then GameTooltip:AddDoubleLine(T(label), value, .8, .8, .8, 1, 1, 1) end end
            line("Gold", S.number(character.gold) and UI.money(character.gold))
            line("Gold earned", S.number(character.earned) and UI.money(character.earned))
            line("Monsters killed", S.number(character.kills) and tostring(character.kills))
            line("Played", S.number(character.played) and UI.duration(character.played))
            line("Honorable kills", S.number(character.honor_kills) and character.honor_kills > 0 and tostring(character.honor_kills))
            line("Dungeons cleared", S.number(character.dungeons) and character.dungeons > 0 and tostring(character.dungeons))
            line("Mounts", S.number(character.mounts) and character.mounts > 0 and tostring(character.mounts))
            if R.isUnreachable(character.name) then
                GameTooltip:AddLine(T("Your live updates did not reach this character. Ask them to /reload, or check that you are on the same realm type."), 1, .4, .4, true)
            end
            GameTooltip:AddLine(T("Click to open this character's profile."), 1, 1, 1, true); GameTooltip:Show()
        end
    end)
    c:SetScript("OnLeave", function(self) UI.tint(self, false); if GameTooltip then GameTooltip:Hide() end end)
    page.lines[index] = c
    return c
end

local function counted(name, count)
    return name .. " (" .. count .. (count == 1 and " character)" or " characters)")
end
-- The page's collapsible sections: your characters, one per group you are in
-- (a friend in two of your groups is in both), and characters in none of them.
-- Each section holds player entries as R.groups returns them.
function R.sections()
    local entries, sections = R.groups(), {}
    local mine = {key="you", title="Your characters", entries={}}
    for _, entry in ipairs(entries) do if entry.self then table.insert(mine.entries, entry) end end
    if #mine.entries > 0 then table.insert(sections, mine) end
    local list = {}
    for id, member in pairs(WoWStatusGroups.selected(current)) do table.insert(list, {id=id, label=member.label or id}) end
    table.sort(list, function(a, b) return S.lowerASCII(a.label) < S.lowerASCII(b.label) end)
    local placed = {}
    for _, group in ipairs(list) do
        local section = {key=group.id, title=group.label, entries={}, characters=0, online=0}
        for _, entry in ipairs(entries) do
            if not entry.self then
                local rows = {}
                for _, row in ipairs(entry.rows) do
                    if row.groupIds and row.groupIds[group.id] then
                        table.insert(rows, row); placed[row] = true
                        if row.status == "online" then section.online = section.online + 1 end
                    end
                end
                if #rows > 0 then
                    table.insert(section.entries, {title=counted(entry.name, #rows), name=entry.name, note=entry.note, rows=rows})
                    section.characters = section.characters + #rows
                end
            end
        end
        table.insert(sections, section)
    end
    local other = {key="other", title="Other", entries={}}
    for _, entry in ipairs(entries) do
        if not entry.self then
            local rows = {}
            for _, row in ipairs(entry.rows) do if not placed[row] then table.insert(rows, row) end end
            if #rows > 0 then table.insert(other.entries, {title=counted(entry.name, #rows), name=entry.name, note=entry.note, rows=rows}) end
        end
    end
    if #other.entries > 0 then table.insert(sections, other) end
    return sections
end
-- A group's leaderboard: this account's characters and every member listed in
-- the group, with level, XP, total deaths (newest death announcement) and
-- completed quests (newest quest milestone). Sorted by the caller.
function R.leaderboard(group)
    local quests = {}
    for _, e in ipairs(WoWStatusJournal.entries()) do
        local k = key(e.sender)
        local n = e.kind == "quest" and tonumber(tostring(e.text or ""):match("^Completed (%d+) quests!$"))
        if k and n and (not quests[k] or n > quests[k]) then quests[k] = n end
    end
    local list, seen = {}, {}
    for _, section in ipairs(R.sections()) do
        if section.key == "you" or section.key == group then
            for _, entry in ipairs(section.entries) do
                for _, row in ipairs(entry.rows) do
                    local k = key(row.name)
                    if k and not seen[k] then
                        seen[k] = true
                        local own = section.key == "you"
                        local q = quests[k]
                        if own and current and row.name == WoWStatusPopups.characterName(current) then
                            q = S.number(current.snapshot and current.snapshot.quests_completed) or q
                        end
                        table.insert(list, {name=row.name, class=row.class, level=S.number(row.level), xp=S.number(row.xp),
                            deaths=S.number(row.deaths), quests=q, online=row.status == "online", own=own})
                    end
                end
            end
        end
    end
    return list
end

-- Collapsed sections, saved account-wide by section key.
function R.collapsed(key)
    local roster = state()
    roster.collapsed = type(roster.collapsed) == "table" and roster.collapsed or {}
    return roster.collapsed[key] == true
end
function R.toggle(key)
    local roster = state()
    roster.collapsed = type(roster.collapsed) == "table" and roster.collapsed or {}
    roster.collapsed[key] = not roster.collapsed[key] or nil
    R.render()
end
local SECTION = 30
local function section(index)
    local b = CreateFrame("Button", nil, page.list)
    b:SetSize(680, SECTION - 4)
    b.bg = b:CreateTexture(nil, "BACKGROUND"); b.bg:SetAllPoints(); b.bg:SetColorTexture(1, .82, 0, .08)
    b.icon = b:CreateTexture(nil, "ARTWORK"); b.icon:SetPoint("TOPLEFT", 4, -5); b.icon:SetSize(16, 16)
    b.text = UI.text(b, "GameFontNormalLarge", 26, -5, 640)
    b:SetScript("OnClick", function(self) if self.key then R.toggle(self.key) end end)
    page.sections[index] = b
    return b
end

function R.render()
    if not page or not page.IsShown or not page:IsShown() then return end
    local index, headers, sections, y = 0, 0, 0, 0
    for _, part in ipairs(R.sections()) do
        sections = sections + 1
        local b = page.sections[sections] or section(sections)
        local closed = R.collapsed(part.key)
        b.key = part.key
        b:ClearAllPoints(); b:SetPoint("TOPLEFT", 0, -y)
        b.icon:SetTexture(closed and "Interface\\Buttons\\UI-PlusButton-Up" or "Interface\\Buttons\\UI-MinusButton-Up")
        local summary = part.characters and ("   |cff9d9d9d" .. part.characters .. " " .. T(part.characters == 1 and "character" or "characters")
            .. ", " .. part.online .. " " .. T("online") .. "|r") or ""
        b.text:SetText(T(part.title):gsub("|", "||") .. summary)
        b:Show()
        y = y + SECTION
        if not closed then
            if #part.entries == 0 then
                headers = headers + 1
                local h = page.headers[headers] or header(headers)
                h:ClearAllPoints(); h:SetPoint("TOPLEFT", 12, -y)
                h.text:SetText("|cff9d9d9d" .. T("Nobody else seen in this group yet.") .. "|r"); h:Show()
                y = y + HEADER
            end
            for _, group in ipairs(part.entries) do
                headers = headers + 1
                local h = page.headers[headers] or header(headers)
                h:ClearAllPoints(); h:SetPoint("TOPLEFT", 12, -y)
                -- The version note stays small and grey beside the title.
                h.text:SetText(shownTitle(group.title):gsub("|", "||") .. (group.note and ("   |cff808080" .. T(group.note) .. "|r") or "")); h:Show()
                y = y + HEADER
                for _, character in ipairs(group.rows) do
                    if index >= 200 then break end
                    index = index + 1
                    local c = page.lines[index] or card(index)
                    c:ClearAllPoints(); c:SetPoint("TOPLEFT", 0, -y)
                    c.portraitKind = R.portrait(c.portrait, character.name, character.race, character.sex)
                    local name = (character.name:match("^[^-]+") or character.name):gsub("|", "||")
                    local colour = UI.classColour(character.class)
                    c.name:SetText(colour and (colour .. name .. "|r") or name)
                    c.badge:SetLevel(character.level); c.badge:SetShown(character.level ~= nil)
                    local class = character.class and T(character.class:sub(1, 1) .. character.class:sub(2):lower()) or T("Never met")
                    c.class:SetText(character.race and (shownRace(character.race) .. " " .. class) or class)
                    local online = character.status == "online"
                    c.dot:SetTexture(online and "Interface\\FriendsFrame\\StatusIcon-Online" or "Interface\\FriendsFrame\\StatusIcon-Offline")
                    local gold = S.number(character.gold) and UI.money(character.gold, true)
                    -- Live updates did not reach them (their client never confirmed).
                    local lost = not group.self and R.isUnreachable(character.name) and ("   |cffff5555" .. T("not reached") .. "|r") or ""
                    c.status:SetText(T(character.status) .. (gold and ("   " .. gold) or "") .. lost)
                    local xp = S.number(character.xp)
                    c.xp:SetProgress(xp and xp / 1000, xp and TF("XP %d%%", math.floor(xp / 10)))
                    -- Level and total deaths at the end of the card.
                    local facts = {}
                    if character.level then table.insert(facts, TF("Level %d", character.level)) end
                    local died = S.number(character.deaths)
                    if died then table.insert(facts, died == 1 and T("1 death") or TF("%d deaths", died)) end
                    local kills = S.number(character.kills)
                    if kills and kills > 0 then table.insert(facts, kills == 1 and T("1 kill") or TF("%d kills", kills)) end
                    c.latest:SetText(table.concat(facts, " · "))
                    local groups = character.groups and #character.groups > 0 and table.concat(character.groups, ", ") or ""
                    c.groups:SetText(groups ~= "" and ("|cff9d9d9d" .. T("Groups:") .. "|r " .. groups:gsub("|", "||")) or "")
                    c.text = c.name -- Older callers read a row's text.
                    c.kind, c.character, c.player = "character", character, group
                    UI.tint(c, false)
                    c:Show()
                    y = y + CARD + GAP
                end
            end
        end
        y = y + 4
    end
    for i = index + 1, #page.lines do page.lines[i]:Hide() end
    for i = headers + 1, #page.headers do page.headers[i]:Hide() end
    for i = sections + 1, #page.sections do page.sections[i]:Hide() end
    page.list:SetHeight(math.max(1, y))
    page.empty:SetShown(index == 0 and sections == 0)
    page.count = index
end

local function build(parent)
    page = CreateFrame("Frame", "WoWStatusCharactersPage", parent); page:SetAllPoints(parent)
    page.scroll = CreateFrame("ScrollFrame", nil, page, "UIPanelScrollFrameTemplate")
    page.scroll:SetPoint("TOPLEFT", 24, -4); page.scroll:SetSize(710, 470)
    page.list = CreateFrame("Frame", nil, page.scroll); page.list:SetSize(686, 32); page.lines, page.headers, page.sections = {}, {}, {}
    page.scroll:SetScrollChild(page.list)
    page.empty = page:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    page.empty:SetPoint("TOPLEFT", 24, -12); page.empty:SetText(T("No characters yet."))
    page.share = CreateFrame("CheckButton", nil, page, "UICheckButtonTemplate")
    page.share:SetPoint("TOPLEFT", 24, -486); page.share:SetSize(32, 32)
    local shareLabel = page.share:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    shareLabel:SetPoint("TOPLEFT", 38, -8); shareLabel:SetText(T("Share my character list"))
    page.share:SetScript("OnClick", function(self) R.setSharing(self:GetChecked() and true or false) end)
    page.hide = CreateFrame("CheckButton", nil, page, "UICheckButtonTemplate")
    page.hide:SetPoint("TOPLEFT", 330, -486); page.hide:SetSize(32, 32)
    local hideLabel = page.hide:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    hideLabel:SetPoint("TOPLEFT", 38, -8); hideLabel:SetText(T("Hide this character from the list"))
    page.hide:SetScript("OnClick", function(self) R.setHidden(current, self:GetChecked() and true or false) end)
    page.sync = CreateFrame("Button", nil, page, "UIPanelButtonTemplate")
    page.sync:SetPoint("TOPLEFT", 594, -486); page.sync:SetSize(128, 28)
    page.sync:SetScript("OnClick", function() if R.syncNow() then R.whoLookup() end end)
    page.sync:SetScript("OnEnter", function(self)
        if GameTooltip then
            GameTooltip:SetOwner(self, "ANCHOR_TOP"); GameTooltip:SetText(T("Sync with everyone online"))
            GameTooltip:AddLine(T("Sends your character list, asks for theirs, looks up one friend's level with /who and catches up the activity log. Once a minute."), 1, 1, 1, true)
            GameTooltip:Show()
        end
    end)
    page.sync:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
    return page
end

WoWStatusMainWindow.register("characters", "Characters", build, function()
    if not page then return end
    page.share:SetChecked(state().share)
    page.hide:SetChecked(current and current.hide_from_list == true)
    updateSyncButton()
    R.render()
end)

-- Saved lists keyed before the realm was left out (WoW Forever): merge to one key,
-- keeping the newest copy of each character.
local function rekey(map)
    if type(map) ~= "table" then return end
    local merged = {}
    for old, item in pairs(map) do
        local name = type(item) == "table" and (item.name or old)
        local k = type(name) == "string" and key(name) or old
        local other = merged[k]
        if not other or (type(item) == "table" and (item.at or 0) > (other.at or 0)) then merged[k] = item end
    end
    for old in pairs(map) do map[old] = nil end
    for k, item in pairs(merged) do map[k] = item end
end

function R.init(database, character, reporter)
    db, current, report = database, character, reporter
    local roster = state()
    if WoWStatusAdapter.full_names and not roster.realmless then
        for _, player in pairs(roster.players) do rekey(player.characters) end
        rekey(roster.seen)
        roster.identified = nil -- Rebuilt from the GUIDs on the next roster read.
        roster.realmless = true
    end
    R.observe(character)
    -- The list sent at login already carries this XP.
    outgoing, sentTo, lastScan, lastXp = {}, {}, 0, 0
    requested, whoAsked = {}, {}
    xpSent = character and character.roster_info and character.roster_info.xp
    statsSent = character and character.roster_info and R.statsLine(character.roster_info)
    local register = C_ChatInfo and C_ChatInfo.RegisterAddonMessagePrefix or RegisterAddonMessagePrefix
    if register then pcall(register, PREFIX) end
end

local frame = CreateFrame("Frame")
for _, event in ipairs({"CHAT_MSG_ADDON", "PLAYER_LEVEL_UP", "PLAYER_XP_UPDATE", "WHO_LIST_UPDATE", "CHAT_MSG_SYSTEM",
    "ADDON_ACTION_BLOCKED", "ADDON_ACTION_FORBIDDEN"}) do pcall(frame.RegisterEvent, frame, event) end
frame:SetScript("OnEvent", function(_, event, prefix, message, distribution, sender)
    if event == "ADDON_ACTION_BLOCKED" or event == "ADDON_ACTION_FORBIDDEN" then
        if S.string(prefix) == "WoWStatus" then S.debug(event .. ": " .. tostring(S.string(message))) end
        return
    end
    -- A short /who answer arrives as a chat line; its results are readable then.
    if event == "WHO_LIST_UPDATE" or event == "CHAT_MSG_SYSTEM" then
        R.readWho()
        return
    end
    if event == "PLAYER_LEVEL_UP" or event == "PLAYER_XP_UPDATE" then
        if not current then return end
        R.observe(current)
        if event == "PLAYER_LEVEL_UP" then
            current.roster_info.level = S.number(prefix) or current.roster_info.level
            R.changed() -- Members get the new level now, not at the next login.
        end
        R.render()
        return
    end
    if S.string(prefix) == PREFIX then R.receive(S.string(message), S.string(sender), S.string(distribution)) end
end)
local elapsed = 0
frame:SetScript("OnUpdate", function(_, delta) elapsed = elapsed + delta; if elapsed >= .25 then elapsed = 0; R.tick() end end)
