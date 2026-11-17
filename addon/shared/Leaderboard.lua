-- A main-window page for the group ranking, alongside Records and Characters.
-- The main window owns Escape/B; the ranking itself is a scrollable child page.
WoWStatusLeaderboard = {}
local L = WoWStatusLeaderboard
local T, TF = WoWStatusLocale.T, WoWStatusLocale.F
local page

local function state()
    if type(WoWStatusDB) ~= "table" then return {} end
    if type(WoWStatusDB.leaderboard) ~= "table" then
        local old = type(WoWStatusDB.firsts) == "table" and WoWStatusDB.firsts or {}
        WoWStatusDB.leaderboard = {tab=old.tab, sort=old.sort}
    end
    local data = WoWStatusDB.leaderboard
    if data.sort ~= "level" and data.sort ~= "deaths" and data.sort ~= "quests" and data.sort ~= "played" then data.sort="level" end
    -- Characters (one row each) or Players (one row per player, by their main; #200).
    if data.mode ~= "players" then data.mode = "characters" end
    return data
end

-- The Leaderboard view: everyone in the group, sorted by level, deaths, quests or played time.
local SORTS = {{"level", "Level"}, {"deaths", "Deaths"}, {"quests", "Quests"}, {"played", "Played time"}}
-- With "Pinned first" (#170), pinned players' characters lead, ranked among
-- themselves by the same sort; everyone stays on the board either way.
local function sorted(list, by, pinnedFirst)
    table.sort(list, function(a, b)
        if pinnedFirst and (a.pin ~= nil) ~= (b.pin ~= nil) then return a.pin ~= nil end
        local x, y = a[by] or -1, b[by] or -1
        if x ~= y then return x > y end
        if by == "level" and (a.xp or -1) ~= (b.xp or -1) then return (a.xp or -1) > (b.xp or -1) end
        return a.name < b.name
    end)
    return list
end
local ROW, PLAYER_ROW = 28, 44
local function boardRow(index)
    local UI = WoWStatusUI
    local row = CreateFrame("Frame", nil, page.list)
    row:SetSize(680, 26)
    row.bg = row:CreateTexture(nil, "BACKGROUND"); row.bg:SetAllPoints()
    row.rank = UI.text(row, "GameFontNormal", 8, -6, 30)
    row.name = UI.text(row, "GameFontHighlight", 44, -6, 230)
    row.level = UI.text(row, "GameFontHighlight", 280, -6, 105)
    row.deaths = UI.text(row, "GameFontHighlight", 390, -6, 70, "RIGHT")
    row.quests = UI.text(row, "GameFontHighlight", 465, -6, 100, "RIGHT")
    row.played = UI.text(row, "GameFontHighlight", 570, -6, 100, "RIGHT")
    -- Players mode: the main (or the default) and the alts collapsed under it.
    row.alts = UI.text(row, "GameFontDisableSmall", 44, -24, 626)
    row.alts:SetWordWrap(false)
    page.board[index] = row
    return row
end
local function short(name) return ((name:match("^[^-]+") or name):gsub("|", "||")) end
local function coloured(entry)
    local colour = WoWStatusUI.classColour(entry.class)
    return colour and (colour .. short(entry.name) .. "|r") or short(entry.name)
end
local MAX_ALTS = 6
-- One Players-mode entry as a ranking row: the main's numbers, the player's name.
local function playerEntry(item)
    local main, online, pin = item.main, false, nil
    for _, row in ipairs(item.rows) do online = online or row.online; pin = pin or row.pin end
    local name = item.name and item.name:gsub("|", "||")
        or (item.own and T("You")) or (item.player:match("^character:") and short(main.name)) or T("Unnamed player")
    local parts = {}
    for i, alt in ipairs(item.alts) do
        if i > MAX_ALTS then table.insert(parts, TF("%d more", #item.alts - MAX_ALTS)); break end
        table.insert(parts, coloured(alt) .. (alt.level and (" " .. alt.level) or ""))
    end
    -- A default is never presented as the player's choice.
    local line = coloured(main) .. " · " .. (item.chosen and T("main") or T("highest level, no main chosen"))
    if #parts > 0 then line = line .. "   " .. T("Alts:") .. " " .. table.concat(parts, ", ") end
    return {name=name, level=main.level, xp=main.xp, deaths=main.deaths, quests=main.quests,
        quests_source=main.quests_source, played=main.played, online=online, own=item.own, line=line, isPlayer=true, pin=pin}
end
local function renderBoard(chosen)
    local data, UI = state() or {}, WoWStatusUI
    local by = data.sort or "level"
    local players, pinned = data.mode == "players", data.pinned_first == true
    local list = {}
    if chosen and players then
        for _, item in ipairs(WoWStatusRoster.players(chosen.id)) do table.insert(list, playerEntry(item)) end
        sorted(list, by, pinned)
    elseif chosen then
        list = sorted(WoWStatusRoster.leaderboard(chosen.id), by, pinned)
    end
    local height = players and PLAYER_ROW or ROW
    page.board = page.board or {}
    for i, entry in ipairs(list) do
        local row = page.board[i] or boardRow(i)
        row:ClearAllPoints(); row:SetPoint("TOPLEFT", 0, -(i - 1) * height)
        row:SetSize(680, height - 2)
        -- Your own row and the zebra stripes, stronger on High contrast (#186).
        UI.stripe(row.bg, entry.own and "own" or (i % 2 == 0 and "stripe" or nil))
        row.rank:SetText(i .. ".")
        -- A filled dot online, a hollow ring offline: the shape says it, not only the green (#185).
        row.name:SetText(UI.presence(entry.online) .. " " .. (entry.isPlayer and entry.name or coloured(entry)))
        row.alts:SetText(entry.line or "")
        row.alts:SetShown(entry.line ~= nil)
        row.level:SetText(entry.level and (TF("Level %d", entry.level) .. (entry.xp and (" (" .. math.floor(entry.xp / 10) .. " %)") or "")) or "–")
        row.deaths:SetText(entry.deaths and tostring(entry.deaths) or "–")
        row.quests:SetText(entry.quests and (tostring(entry.quests)
            .. (entry.quests_source == "tracked_since" and (" (" .. T("tracked") .. ")") or "")) or "–")
        row.played:SetText(entry.played and UI.duration(entry.played) or "–")
        row:Show()
    end
    for i = #list + 1, #page.board do page.board[i]:Hide() end
    page.boardHeader:SetShown(true)
    page.list:SetHeight(math.max(1, #list * height))
    page.boardEmpty:SetShown(#list == 0)
    page.pinnedFirst:SetChecked(data.pinned_first == true)
    page.sort:SetText(T("Sort:") .. " " .. T(by == "deaths" and "Deaths" or by == "quests" and "Quests" or by == "played" and "Played time" or "Level"))
    page.mode:SetText(T("View:") .. " " .. T(players and "Players" or "Characters"))
    page.nameHeader:SetText(T(players and "Player" or "Character"))
    -- Your main in this group: Automatic (the default) or one of your listed characters.
    local choices = chosen and WoWStatusRoster.mainChoices() or {}
    local main = chosen and WoWStatusRoster.ownMain(chosen.id, choices)
    page.main:SetText(T("Main:") .. " " .. (main and short(main) or T("Automatic")))
    UI.call(page.main, "SetEnabled", #choices > 0)
end
-- Cycles this group's main: Automatic, then each listed character, highest level first.
local function nextMain()
    local group = page.group
    if not group then return end
    local choices = WoWStatusRoster.mainChoices()
    local current = WoWStatusRoster.ownMain(group, choices)
    local index = 0
    for i, item in ipairs(choices) do if item.name == current then index = i end end
    local pick = choices[index + 1]
    -- setMain re-renders this page through WoWStatusRoster.render.
    WoWStatusRoster.setMain(group, pick and pick.name or nil)
end

function L.render()
    if not page then return end
    local data, UI = state(), WoWStatusUI
    local groups, chosen = WoWStatusFirsts.groups(), nil
    for _, group in ipairs(groups) do if group.id == data.tab then chosen=group end end
    chosen = chosen or groups[1]
    for i, group in ipairs(groups) do
        local tab = page.tabs[i]
        if not tab then
            tab = CreateFrame("Button", nil, page, "UIPanelButtonTemplate")
            tab:SetSize(128, 24)
            tab:SetScript("OnClick", function(self)
                state().tab = self.group
                page.scroll:SetVerticalScroll(0)
                L.render()
            end)
            page.tabs[i] = tab
        end
        tab:ClearAllPoints(); tab:SetPoint("TOPLEFT", 24 + ((i-1)%5)*134, -4-math.floor((i-1)/5)*28)
        tab.group = group.id
        tab:SetText(group.label)
        UI.call(tab, "SetEnabled", group ~= chosen)
        tab:Show()
    end
    for i=#groups+1,#page.tabs do page.tabs[i]:Hide() end
    local top = math.ceil(#groups/5)*28
    page.group = chosen and chosen.id
    page.heading:ClearAllPoints(); page.heading:SetPoint("TOPLEFT", 24, -12-top)
    -- The heading makes room for "Pinned first" only while there is a board.
    UI.call(page.heading, "SetWidth", chosen and 390 or 660)
    page.pinnedFirst:SetShown(chosen ~= nil)
    page.heading:SetText(chosen and (T("Leaderboard") .. " · " .. chosen.label:gsub("|", "||"))
        or T("Join a group to compare your characters with friends."))
    page.sort:ClearAllPoints(); page.sort:SetPoint("TOPRIGHT", -24, -8-top)
    UI.call(page.sort, "SetEnabled", chosen ~= nil)
    -- View, Main and Pinned first get a line of their own, so the heading keeps its width (#200).
    page.mode:ClearAllPoints(); page.mode:SetPoint("TOPLEFT", 24, -38-top)
    UI.call(page.mode, "SetEnabled", chosen ~= nil)
    page.main:ClearAllPoints(); page.main:SetPoint("TOPLEFT", 150, -38-top)
    page.pinnedFirst:ClearAllPoints(); page.pinnedFirst:SetPoint("TOPLEFT", 360, -34-top)
    page.boardHeader:ClearAllPoints(); page.boardHeader:SetPoint("TOPLEFT", 24, -72-top)
    page.scroll:ClearAllPoints(); page.scroll:SetPoint("TOPLEFT", 24, -94-top)
    page.scroll:SetHeight(436-top)
    renderBoard(chosen)
end

local function build(parent)
    local UI = WoWStatusUI
    page = CreateFrame("Frame", "WoWStatusLeaderboardPage", parent); page:SetAllPoints(parent)
    page.heading = UI.text(page, "GameFontNormalLarge", 24, -12, 520)
    page.heading:SetWordWrap(false)
    page.sort = CreateFrame("Button", nil, page, "UIPanelButtonTemplate")
    page.sort:SetSize(140, 24)
    page.sort:SetScript("OnClick", function()
        local data, index = state(), 1
        for i, sort in ipairs(SORTS) do if sort[1] == data.sort then index=i end end
        data.sort = SORTS[index%#SORTS+1][1]
        page.scroll:SetVerticalScroll(0)
        L.render()
    end)
    -- "Pinned first" (#170): a view choice for this account, like the sort.
    page.pinnedFirst = CreateFrame("CheckButton", nil, page, "UICheckButtonTemplate")
    page.pinnedFirst:SetSize(32, 32)
    local pinnedLabel = page.pinnedFirst:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    pinnedLabel:SetPoint("TOPLEFT", 34, -8); pinnedLabel:SetText(T("Pinned first"))
    page.pinnedFirst:SetScript("OnClick", function(self)
        state().pinned_first = self:GetChecked() and true or nil
        page.scroll:SetVerticalScroll(0)
        L.render()
    end)
    page.pinnedFirst:SetScript("OnEnter", function(self)
        if GameTooltip then
            GameTooltip:SetOwner(self, "ANCHOR_TOP"); GameTooltip:SetText(T("Pinned first"))
            GameTooltip:AddLine(T("Players you pinned on the Characters page lead the board. Nobody is left out."), 1, 1, 1, true)
            GameTooltip:Show()
        end
    end)
    page.pinnedFirst:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
    page.mode = CreateFrame("Button", nil, page, "UIPanelButtonTemplate")
    page.mode:SetSize(120, 24)
    page.mode:SetScript("OnClick", function()
        local data = state()
        data.mode = data.mode == "players" and "characters" or "players"
        page.scroll:SetVerticalScroll(0)
        L.render()
    end)
    page.main = CreateFrame("Button", nil, page, "UIPanelButtonTemplate")
    page.main:SetSize(200, 24)
    page.main:SetScript("OnClick", nextMain)
    page.tabs = {}
    page.scroll = CreateFrame("ScrollFrame", nil, page, "UIPanelScrollFrameTemplate")
    page.scroll:SetSize(710, 464)
    page.list = CreateFrame("Frame", nil, page.scroll); page.list:SetSize(686, 24)
    page.scroll:SetScrollChild(page.list)
    page.boardHeader = CreateFrame("Frame", nil, page); page.boardHeader:SetSize(680, 20)
    page.nameHeader = UI.text(page.boardHeader, "GameFontNormal", 44, 0, 230)
    page.nameHeader:SetText(T("Character"))
    UI.text(page.boardHeader, "GameFontNormal", 280, 0, 105):SetText(T("Level"))
    UI.text(page.boardHeader, "GameFontNormal", 390, 0, 70, "RIGHT"):SetText(T("Deaths"))
    UI.text(page.boardHeader, "GameFontNormal", 465, 0, 100, "RIGHT"):SetText(T("Quests"))
    UI.text(page.boardHeader, "GameFontNormal", 570, 0, 100, "RIGHT"):SetText(T("Played time"))
    page.boardEmpty = UI.text(page.list, "GameFontDisable", 0, -6, 660)
    page.boardEmpty:SetText(T("Nobody in this group yet. Members appear when their character list arrives."))
    return page
end

WoWStatusMainWindow.register("leaderboard", "Leaderboard", build, L.render)
