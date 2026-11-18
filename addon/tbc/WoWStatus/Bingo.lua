-- Grid view for the shared weekly bingo model in Firsts.lua.
WoWStatusBingo = {}
local B, F, T = WoWStatusBingo, WoWStatusFirsts, WoWStatusLocale.T
local SIZE = 5

local function active() return WoWStatusFeatures.enabled("bingo") end

local function refresh(page)
    local groups = active() and F.groups() or {}
    local selected = page.selected
    local group = groups[selected] or groups[1]
    if groups[selected] == nil then page.selected = 1 end
    local first = F.weekRange()
    page.heading:SetText(group and (group.label:gsub("|", "||") .. " · " .. first)
        or T("Join a group to see its bingo card."))
    WoWStatusUI.call(page.nextGroup, "SetEnabled", #groups > 1)
    local board = group and F.bingo(group.id)
    local win = board and F.bingoWins(board)
    page.detail:SetText(win and T("Bingo!") or "")
    if win then F.announceBingo(group.id, first, board) end
    for i, cell in ipairs(page.cells) do
        cell:SetShown(board ~= nil)
        if board then
            local label = T(board[i].text)
            local sender = board[i].by and board[i].by:gsub("|", "||")
            cell.label:SetText(label)
            cell.sender:SetText(sender or "")
            cell.detail = sender and (label .. " · " .. sender) or label
        end
    end
end

local function build(parent)
    local UI = WoWStatusUI
    local page = CreateFrame("Frame", nil, parent)
    page:SetAllPoints(parent)
    page.selected, page.cells = 1, {}
    page.heading = UI.text(page, "GameFontNormalLarge", 24, -12, 540)
    page.nextGroup = CreateFrame("Button", nil, page, "UIPanelButtonTemplate")
    page.nextGroup:SetPoint("TOPLEFT", 610, -8); page.nextGroup:SetSize(120, 26)
    page.nextGroup:SetText(T("Next group"))
    page.nextGroup:SetScript("OnClick", function()
        local count = #F.groups()
        if count > 1 then page.selected = page.selected % count + 1; refresh(page) end
    end)
    for i = 1, SIZE * SIZE do
        local cell = CreateFrame("Button", nil, page, "UIPanelButtonTemplate")
        cell:SetSize(136, 72)
        cell:SetPoint("TOPLEFT", 24 + (i - 1) % SIZE * 142, -48 - math.floor((i - 1) / SIZE) * 78)
        cell.label = UI.text(cell, "GameFontHighlightSmall", 6, -7, 124, "CENTER")
        cell.sender = UI.text(cell, "GameFontNormalSmall", 6, -51, 124, "CENTER")
        cell:SetScript("OnClick", function(self) page.detail:SetText(self.detail) end)
        page.cells[i] = cell
    end
    page.detail = UI.text(page, "GameFontHighlight", 24, -454, 706)
    return page
end

function B.update()
    if active() then WoWStatusMainWindow.refresh("bingo") end
end

function B.show()
    if not active() then return end
    local window = WoWStatusMainWindow
    if not window.has("bingo") then window.register("bingo", "Weekly group bingo card", build, refresh, {tab=false}) end
    window.show("bingo")
end
