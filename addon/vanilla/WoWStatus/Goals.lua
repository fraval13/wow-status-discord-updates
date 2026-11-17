-- Shared group goals (#157): one goal per group at a time, with a progress bar.
-- A goal is a target over a measure the character lists already carry (level,
-- completed quests, dungeon clears, played time) or the log already holds
-- (deaths since the goal was set), in one of two shapes: everybody ("all of us
-- reach level 40") or together ("1000 quests between us"). Its wording is made
-- here from fixed phrases; there is no free text, so a goal can never become an
-- announcement channel.
--
-- The member who sets a goal whispers it on the character-list prefix
-- (WoWStatusChr, see Roster.lua) to the group's members online, and again at
-- each first contact of a session, like their character list:
--   A <group> <playerID> <set at> <measure> <shape> <target> <deadline|0>
--   A <group> <playerID> <cleared at> none - 0 0        (goal cleared)
-- Receivers accept it only from a character the player ID announced itself (its
-- list or visibility lines), so a record claiming another setter is refused. The
-- goal remembers the character that set it (the game names the sender), and
-- while it is open only that character may change or clear it. Progress is
-- worked out locally from what each client already has: nothing per member is
-- sent and nothing is polled. Hidden characters and friends hidden completely
-- are left out, as on the Leaderboard.
WoWStatusGoals = {}
local G, S = WoWStatusGoals, WoWStatusSafe
local T, TF = WoWStatusLocale.T, WoWStatusLocale.F
local DAY = 86400
-- A goal not heard from its setter for this long stops blocking a new one.
G.STALE = 30 * DAY
G.MAX_DEADLINE_DAYS = 366
G.DEADLINES = {0, 3, 7, 14, 30, 60, 90, 180, 365}
-- Measures in the order the editor offers them: key, label, smallest and largest
-- target, step, whether "together" is allowed, default target.
G.MEASURES = {
    {key="level", label="Level", min=2, step=1, together=false},
    {key="quests", label="Completed quests", min=10, max=100000, step=50, together=true, default=500},
    {key="dungeons", label="Dungeon clears", min=1, max=10000, step=1, together=true, default=10},
    {key="played", label="Played time (hours)", min=1, max=100000, step=10, together=true, default=100},
    {key="deaths", label="Deaths (fewer than)", min=1, max=1000, step=1, together=true, default=10},
}
local BY_KEY = {}
-- The last progress worked out per group: {[group] = {at, progress}}.
local cache = {}
-- A deadline that passed while this account was away is judged only once the
-- login sync has had time to bring the log and lists (G.SETTLE seconds of realm
-- time after this session's first check).
G.SETTLE = 180
G.NEWS_DELAY = 5
local sessionStart
for _, m in ipairs(G.MEASURES) do BY_KEY[m.key] = m end
-- The item after (step 1) or before (step -1) value in list, wrapping around.
local function cycle(list, value, step)
    local index = 1
    for i, item in ipairs(list) do if item == value then index = i end end
    return list[(index - 1 + step) % #list + 1]
end

local function maxLevel() return WoWStatusAdapter and WoWStatusAdapter.max_level or 60 end
function G.measure(key) return BY_KEY[key] end
function G.limits(key)
    local m = BY_KEY[key]
    if not m then return nil end
    if key == "level" then return m.min, maxLevel() end
    return m.min, m.max
end

local function integer(value) return type(value) == "number" and value == math.floor(value) and value == value end

-- Whether a goal's fields make a goal this version understands.
function G.valid(measure, shape, target, deadline, at)
    local low, high = G.limits(measure)
    if not low or (shape ~= "all" and shape ~= "sum") then return false end
    if shape == "sum" and not BY_KEY[measure].together then return false end
    if not integer(target) or target < low or target > high then return false end
    if not integer(at) or at < 1000000000 then return false end
    if not integer(deadline) then return false end
    if deadline ~= 0 and (deadline <= at or deadline > at + G.MAX_DEADLINE_DAYS * DAY) then return false end
    -- "Fewer than" can only be judged at an end, so a deaths goal needs a deadline.
    if measure == "deaths" and deadline == 0 then return false end
    return true
end

-- Saved goals, account-wide like groups: {[group id] = goal}. A saved table
-- that is not a valid goal is dropped.
-- Goals this file writes are valid, so a saved table is checked once, when it
-- is first seen (after loading, or when something else replaced it).
local checkedTable
local function goals()
    if type(WoWStatusDB) ~= "table" then return {} end
    if type(WoWStatusDB.goals) ~= "table" then WoWStatusDB.goals = {} end
    local all = WoWStatusDB.goals
    if all == checkedTable then return all end
    checkedTable = all
    for group, goal in pairs(all) do
        local ok = type(group) == "string" and type(goal) == "table" and type(goal.pid) == "string" and integer(goal.at)
            and (goal.cleared == true or G.valid(goal.measure, goal.shape, goal.target, goal.deadline, goal.at))
        if not ok then all[group] = nil end
    end
    return all
end
local function character() return WoWStatusPopups and WoWStatusPopups.character and WoWStatusPopups.character() end
local function joined(group) return WoWStatusGroups.contains(character(), group) end
local function ownId() return WoWStatusRoster.id and WoWStatusRoster.id() end
-- The logged-in character's key, as a goal's setter is kept.
local function ownKey()
    local c = character()
    local name = c and WoWStatusPopups.characterName and WoWStatusPopups.characterName(c)
    return name and WoWStatusRoster.key and WoWStatusRoster.key(name) or nil, name
end

-- The goal a group has now (cleared goals are none), or nil.
function G.get(group)
    local goal = type(group) == "string" and joined(group) and goals()[group]
    if not goal or goal.cleared then return nil end
    return goal
end
function G.mine(goal) return goal ~= nil and goal.pid == ownId() end
-- Whether this character may change or clear the goal: members accept a change
-- only from the character that set it.
function G.canChange(goal) return G.mine(goal) and goal.setter ~= nil and goal.setter == ownKey() end

-- The goal's wording, made from the measure and target only.
local TITLES = {
    level={all="Everybody reaches level %d"},
    quests={all="Everybody completes %d quests", sum="%d completed quests together"},
    dungeons={all="Everybody clears %d dungeons", sum="%d dungeon clears together"},
    played={all="Everybody plays %d hours", sum="%d hours played together"},
    deaths={all="Everybody stays under %d deaths", sum="Fewer than %d deaths together"},
}
function G.title(goal)
    local titles = goal and TITLES[goal.measure]
    local text = titles and titles[goal.shape]
    return text and TF(text, goal.target) or ""
end

-- Each player in the group with the characters that count: this account and
-- every member with a shared list, without hidden characters or friends hidden
-- completely (#169). {own, rows}. Players are told apart by their player ID, not
-- by the shown name, which unnamed players (and namesakes) share.
local function players(group)
    local list, byId = {}, {}
    for _, section in ipairs(WoWStatusRoster.sections()) do
        if section.key == "you" or section.key == group then
            local own = section.key == "you"
            for _, entry in ipairs(section.entries) do
                for _, row in ipairs(entry.rows) do
                    -- Members without a shared list carry no numbers to count.
                    if own or (row.listed and not (WoWStatusMutes and WoWStatusMutes.hidden(row.name))) then
                        local id = own and "you" or WoWStatusRoster.playerIdOf(row.name)
                            or ("?" .. (WoWStatusRoster.key(row.name) or row.name))
                        local player = byId[id]
                        if not player then player = {own=own, rows={}}; byId[id] = player; table.insert(list, player) end
                        table.insert(player.rows, row)
                    end
                end
            end
        end
    end
    return list
end

-- Deaths in the log from the goal's start to its deadline, per character key.
local function deathsSince(at, deadline)
    local counts = {}
    for _, e in ipairs(WoWStatusJournal.entries()) do
        local when = type(e) == "table" and S.number(e.at) or 0
        if type(e) == "table" and e.kind == "death" and when >= at and (deadline == 0 or when < deadline)
            and (not WoWStatusJournal.visible or WoWStatusJournal.visible(e)) then
            local k = WoWStatusRoster.key(e.sender)
            if k then counts[k] = (counts[k] or 0) + 1 end
        end
    end
    return counts
end

-- One player's value: the highest level, otherwise the sum over their characters.
local function valueOf(goal, player, deaths, logged)
    local value
    for _, row in ipairs(player.rows) do
        local v
        if goal.measure == "deaths" then v = deaths[WoWStatusRoster.key(row.name) or ""] or 0
        elseif goal.measure == "quests" and S.number(row.quests) == nil and not row.quests_source then
            -- An older version's quest milestone in the log, as the Leaderboard counts it.
            v = logged[WoWStatusRoster.key(row.name) or ""]
        elseif goal.measure == "played" then v = S.number(row.played) and math.floor(row.played / 3600)
        else v = S.number(row[goal.measure]) end
        if v then
            if goal.measure == "level" then value = math.max(value or 0, v) else value = (value or 0) + v end
        end
    end
    return value
end

-- Progress of a goal from what this client knows now:
-- {players, known, reached, total, fraction, done, failed}. Players whose numbers
-- are not shared (played time, an older version) are left out of "everybody".
function G.progress(group, goal)
    goal = goal or G.get(group)
    if not goal then return nil end
    local deaths = goal.measure == "deaths" and deathsSince(goal.at, goal.deadline) or {}
    local logged = goal.measure == "quests" and WoWStatusRoster.loggedQuests() or {}
    local result = {players=0, known=0, reached=0, total=0, worst=nil}
    for _, player in ipairs(players(group)) do
        result.players = result.players + 1
        local value = valueOf(goal, player, deaths, logged)
        if value then
            result.known = result.known + 1
            result.total = result.total + value
            if goal.measure == "deaths" then
                if value < goal.target then result.reached = result.reached + 1 end
                result.worst = math.max(result.worst or 0, value)
            elseif value >= goal.target then result.reached = result.reached + 1 end
        end
    end
    if goal.measure == "deaths" then
        local used = goal.shape == "sum" and result.total or (result.worst or 0)
        -- The bar shows the allowance left, so it empties as deaths come.
        result.fraction = math.max(0, 1 - used / goal.target)
        result.failed = used >= goal.target
        -- Kept to the deadline: reached, if the group's numbers were known.
        result.done = result.known > 1 and not result.failed
    elseif goal.shape == "sum" then
        result.fraction = math.min(1, result.total / goal.target)
        result.done = result.known > 1 and result.total >= goal.target
    else
        -- Out of at least two, like "done" below: one known player is never a full bar.
        result.fraction = result.reached / math.max(2, result.known)
        -- A group goal needs a group: with only one player's numbers known yet
        -- (lists still on their way), no goal is reached.
        result.done = result.known > 1 and result.reached == result.known
    end
    return result
end

-- Progress for the Overview band and the Leaderboard row: the last check's,
-- worked out again only after news (G.touch) or for a changed goal.
function G.view(group, goal)
    goal = goal or G.get(group)
    if not goal then return nil end
    local item = cache[group]
    if item and item.at == goal.at then return item.progress end
    local progress = G.progress(group, goal)
    cache[group] = {at=goal.at, progress=progress}
    return progress
end

-- Who set a goal, as shown: "you", the player's chosen name, or the character's
-- name. Worked out when shown, so a character hidden since is never named.
function G.setBy(goal)
    if G.mine(goal) then return T("you") end
    local sender = S.string(goal.sender)
    local by = sender and WoWStatusRoster.playerOf and WoWStatusRoster.playerOf(sender)
    if not by and sender and not WoWStatusRoster.isHidden(sender) then by = sender:match("^[^-]+") end
    return by and by:gsub("|", "||") or T("a group member")
end

-- A goal as the Overview band and the Leaderboard row show it: title, bar value
-- and status line.
function G.describe(group, goal)
    local progress = G.view(group, goal)
    return G.title(goal), G.fraction(goal, progress), G.status(goal, progress)
end

-- Days left until the deadline (at least 1 while it has not passed), or nil.
function G.daysLeft(goal, now)
    if not goal or goal.deadline == 0 then return nil end
    local left = goal.deadline - (now or S.now())
    if left <= 0 then return 0 end
    return math.ceil(left / DAY)
end

-- "reached", "missed" (deadline passed or over the death limit) or "open".
function G.outcome(goal)
    if not goal then return nil end
    if goal.done_at then return "reached" end
    if goal.missed_at then return "missed" end
    return "open"
end

-- Whether a goal still holds the group: open, not past its deadline and heard
-- from its setter recently. Only then is another member's goal refused.
function G.active(goal, now)
    if not goal or goal.cleared or goal.done_at or goal.missed_at then return false end
    now = now or S.now()
    if goal.deadline ~= 0 and now >= goal.deadline then return false end
    -- Also this account's own goal: it is "heard" when its setting character
    -- sends it, so a goal set on a character no longer played frees the group.
    if now - (goal.heard or goal.at) > G.STALE then return false end
    return true
end

-- The bar's value: full when reached, empty when missed, else the progress.
function G.fraction(goal, progress)
    local outcome = G.outcome(goal)
    if outcome == "reached" then return 1 end
    if outcome == "missed" then return 0 end
    return progress and progress.fraction or 0
end

-- One line for a goal's progress, as on the Overview band and the Leaderboard.
function G.status(goal, progress)
    if not goal then return "" end
    local outcome = G.outcome(goal)
    if outcome == "reached" then return T("Goal reached!") end
    if outcome == "missed" then
        return T(goal.over and "Over the limit this time." or "Not reached in time.")
    end
    progress = progress or {known=0, reached=0, total=0}
    local parts = {}
    if goal.measure == "deaths" then
        local used = goal.shape == "sum" and progress.total or (progress.worst or 0)
        table.insert(parts, TF("%d of %d deaths", used, goal.target))
    elseif goal.shape == "sum" then
        table.insert(parts, TF("%d of %d", math.min(progress.total, goal.target), goal.target))
    else
        table.insert(parts, TF("%d of %d there", progress.reached, progress.known))
    end
    local days = G.daysLeft(goal)
    if days == 1 then table.insert(parts, T("1 day left"))
    elseif days and days > 1 then table.insert(parts, TF("%d days left", days)) end
    return table.concat(parts, " · ")
end

local function line(group, goal)
    if goal.cleared then return table.concat({"A", group, goal.pid, goal.at, "none", "-", 0, 0}, " ") end
    return table.concat({"A", group, goal.pid, goal.at, goal.measure, goal.shape, goal.target, goal.deadline}, " ")
end
-- This account's goal line for a group while it is open (a cleared one for a
-- while too, so members who were away hear of it), or nil. Only the character
-- that set it sends it: members would refuse it from another one. Roster sends
-- it after the list.
function G.line(group)
    local goal = joined(group) and goals()[group]
    if not goal or goal.pid ~= ownId() or goal.setter ~= ownKey() then return nil end
    if goal.cleared then
        if S.now() - goal.at > G.STALE then return nil end
    elseif not G.active(goal) then return nil
    else goal.heard = math.floor(S.now()) end
    return line(group, goal)
end
local function broadcast(group, goal)
    if WoWStatusRoster.sharing and not WoWStatusRoster.sharing() then return end
    local text = line(group, goal)
    for _, peer in ipairs(WoWStatusPopups.peers(group)) do WoWStatusRoster.queue(peer, text) end
end

local function refresh()
    if WoWStatusMainWindow then
        WoWStatusMainWindow.refresh("overview")
        WoWStatusMainWindow.refresh("leaderboard")
        WoWStatusMainWindow.refresh("records")
        WoWStatusMainWindow.refresh("goal")
    end
end

-- Why this account cannot set a goal in a group now, or nil.
function G.blocked(group)
    if not joined(group) then return "Join a group first." end
    if not ownId() then return "Your character is not ready yet." end
    if WoWStatusRoster.sharing and not WoWStatusRoster.sharing() then
        return "Turn on sharing your character list to set a goal."
    end
    local goal = goals()[group]
    if goal and G.active(goal) and not G.canChange(goal) then
        if G.mine(goal) then return "Change this goal from the character that set it." end
        return "Only the member who set this goal can change it."
    end
    return nil
end

-- A new set time: realm time, and always after this account's previous goal.
local function stamp(group)
    local at = math.floor(S.now())
    -- After whatever goal is kept, whoever set it: members refuse an older one.
    local old = goals()[group]
    if old and at <= old.at then at = old.at + 1 end
    return at
end

-- Set (or change) this account's goal for a group. days: 0 for no deadline.
function G.set(group, measure, shape, target, days)
    if G.blocked(group) then return false end
    local at = stamp(group)
    days = tonumber(days) or 0
    local deadline = days > 0 and at + days * DAY or 0
    if not G.valid(measure, shape, target, deadline, at) then return false end
    local setter = ownKey()
    if not setter then return false end
    local goal = {pid=ownId(), setter=setter, at=at, measure=measure, shape=shape, target=target, deadline=deadline,
        heard=at}
    goals()[group] = goal
    broadcast(group, goal)
    cache[group] = nil
    G.check()
    refresh()
    return true
end

-- Clear this account's goal for a group.
function G.clear(group)
    local goal = G.get(group)
    if not goal or not G.canChange(goal) then return false end
    local cleared = {pid=goal.pid, setter=goal.setter, at=stamp(group), cleared=true}
    goals()[group] = cleared
    broadcast(group, cleared)
    refresh()
    return true
end

-- A goal line from a member. owns(pid, sender): whether the sender is one of the
-- characters that player ID announced. Returns ok, reason.
function G.receive(words, sender, owns)
    if #words ~= 8 then return false, "bad goal line" end
    local group, pid, at = words[2], words[3], tonumber(words[4])
    local measure, shape, target, deadline = words[5], words[6], tonumber(words[7]), tonumber(words[8])
    if not words[4]:match("^%d+$") or not integer(at) or at < 1000000000 or at > S.now() + 300 then
        return false, "bad goal time"
    end
    local cleared = measure == "none"
    if cleared then
        if shape ~= "-" or words[7] ~= "0" or words[8] ~= "0" then return false, "bad goal line" end
    elseif not (words[7]:match("^%d+$") and words[8]:match("^%d+$") and G.valid(measure, shape, target, deadline, at)) then
        return false, "bad goal"
    end
    -- The setter is the player ID; only its own characters may speak for it.
    if not owns(pid, sender) then return false, "setter is not the sender" end
    local setter = WoWStatusRoster.key(sender)
    if not setter then return false, "bad sender" end
    local all = goals()
    local old = all[group]
    if old then
        -- Never older than what is kept: a finished goal sent again by its setter
        -- must not replace the newer goal that followed it.
        if at < old.at then return false, "older goal" end
        local same = old.pid == pid and old.setter == setter
        if at == old.at then
            -- The same goal again (the setter's next session): still alive.
            local content = cleared and old.cleared or (not cleared and not old.cleared and old.measure == measure
                and old.shape == shape and old.target == target and old.deadline == deadline)
            if not (same and content) then return false, "changed goal without a new time" end
            old.heard = math.floor(S.now())
            return true
        end
        -- While a goal is open, only the character that set it may change it.
        if G.active(old) and not same then return false, "another member's goal" end
    elseif cleared then
        return true -- Nothing to clear.
    end
    if cleared then
        all[group] = {pid=pid, setter=setter, at=at, cleared=true}
    else
        all[group] = {pid=pid, setter=setter, at=at, measure=measure, shape=shape, target=target, deadline=deadline,
            sender=sender, heard=math.floor(S.now())}
    end
    G.check()
    refresh()
    return true
end

-- The group's label, as this account named it.
local function label(group)
    for _, item in ipairs(G.groups()) do if item.id == group then return item.label end end
    return group
end

-- The newest goal each group reached, for its Records medal: {[group] = record}.
local function medals()
    if type(WoWStatusDB) ~= "table" then return {} end
    if type(WoWStatusDB.goal_medals) ~= "table" then WoWStatusDB.goal_medals = {} end
    local all = WoWStatusDB.goal_medals
    for group, item in pairs(all) do
        if type(group) ~= "string" or type(item) ~= "table" or not integer(item.at) or not integer(item.set)
            or not G.valid(item.measure, item.shape, item.target, item.set + 1, item.set) then
            all[group] = nil
        end
    end
    return all
end

-- Work out each open goal's outcome. A goal that is reached gets one big banner
-- here (local only; nothing is sent) and holds the group's goal medal on Records.
function G.check()
    if type(WoWStatusDB) ~= "table" or not character() then return end
    local now = S.now()
    -- Every caller (a tick, a received goal, the editor) waits for the login sync
    -- before judging a deadline that passed while this account was away.
    sessionStart = sessionStart or now
    local unsettled = now - sessionStart < G.SETTLE
    local changed = false
    for group, goal in pairs(goals()) do
        if joined(group) and not goal.cleared and not goal.done_at and not goal.missed_at then
            local ended = goal.deadline ~= 0 and now >= goal.deadline
            local ok, progress = true, nil
            if not (ended and unsettled) then ok, progress = pcall(G.progress, group, goal) end
            cache[group] = ok and progress and {at=goal.at, progress=progress} or nil
            if ok and progress then
                if goal.measure == "deaths" then
                    if progress.failed then goal.missed_at, goal.over = math.floor(now), true
                    elseif ended and progress.done then goal.done_at = goal.deadline
                    elseif ended then goal.missed_at = goal.deadline end
                elseif progress.done then goal.done_at = math.floor(now)
                elseif ended then goal.missed_at = goal.deadline end
                if goal.done_at then
                    changed = true
                    -- The medal stays when the next goal replaces this one.
                    medals()[group] = {measure=goal.measure, shape=goal.shape, target=goal.target, at=goal.done_at,
                        set=goal.at}
                    local name = label(group):gsub("%-", " ")
                    if WoWStatusPopups.notice then
                        WoWStatusPopups.notice({sender=name, kind="goal", text=T("Goal reached:") .. " " .. G.title(goal),
                            flavour=T("Your group's goal is done. Well played, all of you.")})
                    end
                elseif goal.missed_at then changed = true end
            end
        end
    end
    if changed then refresh() end
end

-- The group's goal medal on Records: the newest goal reached, as a log-like entry.
-- It is kept apart from the goal, so it stays after the goal is cleared or replaced.
function G.medal(group)
    local item = type(group) == "string" and joined(group) and medals()[group]
    if not item then return nil end
    return {id="goal:" .. group .. ":" .. item.set, sender=G.title(item), text=G.title(item), at=item.at,
        kind="goal", holder=G.title(item)}
end

-- Checking goals rebuilds the character list, so it runs only when something
-- arrived (G.touch, from the roster) or every few minutes for deadlines and the
-- log, and not at all without an open goal.
G.CHECK_INTERVAL = 300
local dirty, checkedAt = false, nil
function G.touch() dirty = true end
function G.tick(now)
    checkedAt = checkedAt or now
    sessionStart = sessionStart or S.now()
    -- News is checked a few seconds after it comes, so a burst of lines at login
    -- costs one check, not one per line.
    local wait = dirty and G.NEWS_DELAY or G.CHECK_INTERVAL
    if now - checkedAt < wait then return end
    local open = false
    for group, goal in pairs(goals()) do
        if joined(group) and not goal.cleared and not goal.done_at and not goal.missed_at then open = true end
    end
    dirty, checkedAt = false, now
    if open then G.check() end
end

-- This account's groups, sorted by label, as Records lists them.
function G.groups()
    return WoWStatusFirsts and WoWStatusFirsts.groups and WoWStatusFirsts.groups() or {}
end
-- The group after this one, for the "next group" buttons.
function G.nextGroup(group)
    local ids = {}
    for _, item in ipairs(G.groups()) do table.insert(ids, item.id) end
    return #ids > 0 and cycle(ids, group, 1) or nil
end

---------------------------------------------------------------------------
-- The editor: a main-window page without a tab (/wstatus goal, or "Goal…" on
-- the Overview). Every control is a button, so a controller reaches all of it.
local page
local function editor()
    if type(WoWStatusDB) ~= "table" then return {} end
    if type(WoWStatusDB.goal_editor) ~= "table" then WoWStatusDB.goal_editor = {} end
    return WoWStatusDB.goal_editor
end
-- The draft being edited, kept valid for its measure.
local function draft()
    local d = editor()
    if not BY_KEY[d.measure] then d.measure = "level" end
    local m = BY_KEY[d.measure]
    if d.shape ~= "sum" or not m.together then d.shape = "all" end
    local low, high = G.limits(d.measure)
    if not integer(d.target) then d.target = m.default or high end
    d.target = math.max(low, math.min(high, d.target))
    local known = false
    for _, days in ipairs(G.DEADLINES) do if days == d.days then known = true end end
    if not known then d.days = 0 end
    if d.measure == "deaths" and d.days == 0 then d.days = 30 end
    return d
end
local function chosenGroup()
    local groups, d = G.groups(), editor()
    for _, group in ipairs(groups) do if group.id == d.group then return group, groups end end
    return groups[1], groups
end


local function render()
    if not page then return end
    local UI = WoWStatusUI
    local d = draft()
    local group, groups = chosenGroup()
    local m = BY_KEY[d.measure]
    page.heading:SetText(group and (T("Group goal") .. " · " .. group.label:gsub("|", "||")) or T("Join a group to set a goal."))
    UI.call(page.nextGroup, "SetEnabled", #groups > 1)
    page.measure:SetText(T("Measure:") .. " " .. T(m.label))
    UI.call(page.everybody, "SetEnabled", d.shape ~= "all")
    UI.call(page.together, "SetEnabled", d.shape ~= "sum" and m.together)
    page.shape:SetText(T("Shape:") .. " " .. T(d.shape == "sum" and "Together" or "Everybody"))
    page.target:SetText(T("Target:") .. " " .. d.target)
    local low, high = G.limits(d.measure)
    UI.call(page.less, "SetEnabled", d.target > low); UI.call(page.muchLess, "SetEnabled", d.target > low)
    UI.call(page.more, "SetEnabled", d.target < high); UI.call(page.muchMore, "SetEnabled", d.target < high)
    page.deadline:SetText(T("Deadline:") .. " " .. (d.days == 0 and T("none") or TF("%d days", d.days)))
    page.preview:SetText("|cffffd100" .. G.title({measure=d.measure, shape=d.shape, target=d.target}) .. "|r")
    local shown = group and G.get(group.id)
    if shown then
        local title, _, status = G.describe(group.id, shown)
        page.current:SetText(T("Current goal:") .. " " .. title .. "\n" .. T("Set by") .. " " .. G.setBy(shown)
            .. " · " .. status)
    else
        page.current:SetText(T("No goal in this group yet."))
    end
    local why = group and G.blocked(group.id) or (not group and "Join a group first.")
    page.note:SetText(why and ("|cffff6060" .. T(why) .. "|r") or
        T("Only the member who sets a goal can change or clear it. Friends see it while your character list is shared."))
    UI.call(page.save, "SetEnabled", group ~= nil and not why)
    UI.call(page.clear, "SetEnabled", shown ~= nil and G.canChange(shown))
end

local function build(parent)
    local UI = WoWStatusUI
    page = CreateFrame("Frame", "WoWStatusGoalPage", parent); page:SetAllPoints(parent)
    page.heading = UI.text(page, "GameFontNormalLarge", 24, -8, 520)
    local function button(text, width, x, y, onClick)
        local b = CreateFrame("Button", nil, page, "UIPanelButtonTemplate")
        b:SetSize(width, 24); b:SetPoint("TOPLEFT", x, y); b:SetText(T(text))
        b:SetScript("OnClick", function() onClick(); render() end)
        return b
    end
    page.nextGroup = button("Next group", 120, 600, -6, function()
        local group = chosenGroup()
        if group then editor().group = G.nextGroup(group.id) end
    end)
    local keys = {}
    for _, item in ipairs(G.MEASURES) do table.insert(keys, item.key) end
    local function setMeasure(step)
        local d = draft()
        d.measure = cycle(keys, d.measure, step)
        d.target = nil
    end
    page.measure = UI.text(page, "GameFontHighlight", 24, -50, 300)
    page.measureBack = button("<", 40, 330, -44, function() setMeasure(-1) end)
    page.measureNext = button(">", 40, 376, -44, function() setMeasure(1) end)
    page.shape = UI.text(page, "GameFontHighlight", 24, -86, 300)
    page.everybody = button("Everybody", 110, 330, -80, function() draft().shape = "all" end)
    page.together = button("Together", 110, 446, -80, function() draft().shape = "sum" end)
    page.target = UI.text(page, "GameFontHighlight", 24, -122, 300)
    local function move(steps)
        local d = draft()
        local low, high = G.limits(d.measure)
        d.target = math.max(low, math.min(high, d.target + steps * BY_KEY[d.measure].step))
    end
    -- Ten steps at once: quests, dungeons and hours have large targets.
    page.muchLess = button(("-%d"):format(10), 50, 330, -116, function() move(-10) end)
    page.less = button("-", 40, 386, -116, function() move(-1) end)
    page.more = button("+", 40, 432, -116, function() move(1) end)
    page.muchMore = button(("+%d"):format(10), 50, 478, -116, function() move(10) end)
    page.deadline = UI.text(page, "GameFontHighlight", 24, -158, 300)
    local function setDays(step)
        local d = draft()
        repeat d.days = cycle(G.DEADLINES, d.days, step) until not (d.measure == "deaths" and d.days == 0)
    end
    page.deadlineBack = button("<", 40, 330, -152, function() setDays(-1) end)
    page.deadlineNext = button(">", 40, 376, -152, function() setDays(1) end)
    page.preview = UI.text(page, "GameFontNormalLarge", 24, -196, 700)
    page.save = button("Set goal", 140, 24, -228, function()
        local d, group = draft(), chosenGroup()
        if group then G.set(group.id, d.measure, d.shape, d.target, d.days) end
    end)
    page.clear = button("Clear goal", 140, 172, -228, function()
        local group = chosenGroup()
        if group then G.clear(group.id) end
    end)
    page.current = UI.text(page, "GameFontHighlight", 24, -272, 700)
    page.note = UI.text(page, "GameFontHighlightSmall", 24, -320, 700)
    return page
end

function G.show(group)
    if group then editor().group = group end
    if WoWStatusMainWindow then WoWStatusMainWindow.show("goal") end
end

WoWStatusMainWindow.register("goal", "Group goal", build, render, {tab=false})
