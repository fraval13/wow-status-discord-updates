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
    return data
end

-- The Leaderboard view: everyone in the group, sorted by level, deaths, quests or played time.
local SORTS = {{"level", "Level"}, {"deaths", "Deaths"}, {"quests", "Quests"}, {"played", "Played time"}}
local function sorted(list, by)
    table.sort(list, function(a, b)
        local x, y = a[by] or -1, b[by] or -1
        if x ~= y then return x > y end
        if by == "level" and (a.xp or -1) ~= (b.xp or -1) then return (a.xp or -1) > (b.xp or -1) end
        return a.name < b.name
    end)
    return list
end
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
    page.board[index] = row
    return row
end
local function renderBoard(chosen)
    local data, UI = state() or {}, WoWStatusUI
    local by = data.sort or "level"
    local list = chosen and sorted(WoWStatusRoster.leaderboard(chosen.id), by) or {}
    page.board = page.board or {}
    for i, entry in ipairs(list) do
        local row = page.board[i] or boardRow(i)
        row:ClearAllPoints(); row:SetPoint("TOPLEFT", 0, -(i - 1) * 28)
        row.bg:SetColorTexture(1, .82, 0, entry.own and .12 or (i % 2 == 0 and .04 or 0))
        row.rank:SetText(i .. ".")
        local name = (entry.name:match("^[^-]+") or entry.name):gsub("|", "||")
        local colour = UI.classColour(entry.class)
        row.name:SetText((entry.online and "|cff40ff40•|r " or "  ") .. (colour and (colour .. name .. "|r") or name))
        row.level:SetText(entry.level and (TF("Level %d", entry.level) .. (entry.xp and (" (" .. math.floor(entry.xp / 10) .. " %)") or "")) or "–")
        row.deaths:SetText(entry.deaths and tostring(entry.deaths) or "–")
        row.quests:SetText(entry.quests and (tostring(entry.quests)
            .. (entry.quests_source == "tracked_since" and (" (" .. T("tracked") .. ")") or "")) or "–")
        row.played:SetText(entry.played and UI.duration(entry.played) or "–")
        row:Show()
    end
    for i = #list + 1, #page.board do page.board[i]:Hide() end
    page.boardHeader:SetShown(true)
    page.list:SetHeight(math.max(1, #list * 28))
    page.boardEmpty:SetShown(#list == 0)
    page.sort:SetText(T("Sort:") .. " " .. T(by == "deaths" and "Deaths" or by == "quests" and "Quests" or by == "played" and "Played time" or "Level"))
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
    page.heading:SetText(chosen and (T("Leaderboard") .. " · " .. chosen.label:gsub("|", "||"))
        or T("Join a group to compare your characters with friends."))
    page.sort:ClearAllPoints(); page.sort:SetPoint("TOPRIGHT", -24, -8-top)
    UI.call(page.sort, "SetEnabled", chosen ~= nil)
    page.boardHeader:ClearAllPoints(); page.boardHeader:SetPoint("TOPLEFT", 24, -44-top)
    page.scroll:ClearAllPoints(); page.scroll:SetPoint("TOPLEFT", 24, -66-top)
    page.scroll:SetHeight(464-top)
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
    page.tabs = {}
    page.scroll = CreateFrame("ScrollFrame", nil, page, "UIPanelScrollFrameTemplate")
    page.scroll:SetSize(710, 464)
    page.list = CreateFrame("Frame", nil, page.scroll); page.list:SetSize(686, 24)
    page.scroll:SetScrollChild(page.list)
    page.boardHeader = CreateFrame("Frame", nil, page); page.boardHeader:SetSize(680, 20)
    UI.text(page.boardHeader, "GameFontNormal", 44, 0, 230):SetText(T("Character"))
    UI.text(page.boardHeader, "GameFontNormal", 280, 0, 105):SetText(T("Level"))
    UI.text(page.boardHeader, "GameFontNormal", 390, 0, 70, "RIGHT"):SetText(T("Deaths"))
    UI.text(page.boardHeader, "GameFontNormal", 465, 0, 100, "RIGHT"):SetText(T("Quests"))
    UI.text(page.boardHeader, "GameFontNormal", 570, 0, 100, "RIGHT"):SetText(T("Played time"))
    page.boardEmpty = UI.text(page.list, "GameFontDisable", 0, -6, 660)
    page.boardEmpty:SetText(T("Nobody in this group yet. Members appear when their character list arrives."))
    return page
end

WoWStatusMainWindow.register("leaderboard", "Leaderboard", build, L.render)
