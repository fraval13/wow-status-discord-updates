-- Paginated, scrollable event records and an elapsed-time level line graph.
WoWStatusHistoryUI = {}
local UI, H = WoWStatusHistoryUI, WoWStatusHistory
local panel, getCharacter
local mode, page, category = "logs", 1, "all"
local PAGE_SIZE = 75

local function label(parent, text, x, y, width)
    local font = parent:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    font:SetPoint("TOPLEFT", x, y)
    font:SetWidth(width)
    font:SetJustifyH("LEFT")
    font:SetText(text)
    return font
end
local function button(parent, text, x, y, width, fn)
    local b = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
    b:SetPoint("TOPLEFT", x, y)
    b:SetSize(width, 25)
    b:SetText(text)
    b:SetScript("OnClick", fn)
    return b
end
local function setText(text)
    panel.text:SetText(text)
    panel.child:SetHeight(math.max(350, panel.text:GetStringHeight() + 30))
    panel.scroll:SetVerticalScroll(0)
end
local function hideGraph()
    for _, object in ipairs(panel.graphObjects) do object:Hide() end
    panel.lineUsed, panel.fontUsed, panel.dotUsed = 0, 0, 0
end
local function graphLabel(text, x, y, width)
    panel.fontUsed = panel.fontUsed + 1
    local font = panel.fontPool[panel.fontUsed]
    if not font then
        font = label(panel.child, text, x, y, width or 130)
        panel.fontPool[panel.fontUsed] = font
        table.insert(panel.graphObjects, font)
    else
        font:ClearAllPoints()
        font:SetPoint("TOPLEFT", x, y)
        font:SetWidth(width or 130)
        font:SetText(text)
        font:Show()
    end
    return font
end
local function line(x1, y1, x2, y2, r, g, b)
    if not panel.child.CreateLine then return end
    panel.lineUsed = panel.lineUsed + 1
    local object = panel.linePool[panel.lineUsed]
    if not object then
        object = panel.child:CreateLine(nil, "OVERLAY")
        panel.linePool[panel.lineUsed] = object
        table.insert(panel.graphObjects, object)
    end
    object:Show()
    object:SetThickness(2)
    object:SetColorTexture(r, g, b, 1)
    object:SetStartPoint("TOPLEFT", panel.child, x1, -y1)
    object:SetEndPoint("TOPLEFT", panel.child, x2, -y2)
end

local function graph(character)
    local points = character.history and character.history.tracking.points or {}
    panel.text:SetText("")
    panel.child:SetHeight(360)
    if #points == 0 then
        setText("No collected level history. Enable sharing, the level field and level collection.\n"
            .. "Tracking starts with an observation; earlier level-up times cannot be reconstructed.")
        return
    end
    if not panel.child.CreateLine then
        setText("This client does not provide the line drawing API. Use the Level times tab.\n"
            .. "Graph API compatibility must be checked on your installed client.")
        return
    end
    local first, last = points[1], points[#points]
    local endAt = math.max(last.at, character.history.tracking.observed_until or last.at)
    local firstAt, lastAt = first.at, endAt
    for _, point in ipairs(points) do
        firstAt, lastAt = math.min(firstAt, point.at), math.max(lastAt, point.at)
    end
    local span = math.max(1, lastAt - firstAt)
    local low, high = first.level, first.level + 1
    for _, point in ipairs(points) do
        low, high = math.min(low, point.level), math.max(high, point.level)
    end
    local left, top, width, height = 62, 30, 710, 230
    local function x(at) return left + ((at - firstAt) / span) * width end
    local function y(level) return top + height - ((level - low) / math.max(1, high - low)) * height end
    line(left, top, left, top + height, .7, .7, .7)
    line(left, top + height, left + width, top + height, .7, .7, .7)
    local ticks = math.min(4, math.max(1, high - low))
    for i = 0, ticks do
        local level = low + (high - low) * i / ticks
        graphLabel(string.format("%.0f", level), 4, -y(level) + 6, 48)
        local at = firstAt + span * i / ticks
        graphLabel(H.duration(at - firstAt), math.min(x(at) - 35, left + width - 125), -(top + height + 10), 125)
    end
    graphLabel("Level", 4, 0, 60)
    graphLabel("Elapsed clock time since first observation (includes offline time)", 150, -310, 640)
    graphLabel(H.oslo(firstAt) .. "  →  " .. H.oslo(lastAt) .. " · Europe/Oslo", 62, -335, 740)
    for i, point in ipairs(points) do
        if i > 1 then
            local previous = points[i - 1]
            if previous.segment == point.segment and point.at >= previous.at then
                -- A step-line shows how long each level lasted, then the instant it changed.
                line(x(previous.at), y(previous.level), x(point.at), y(previous.level), .2, .8, 1)
                line(x(point.at), y(previous.level), x(point.at), y(point.level), .2, .8, 1)
            end
        end
        panel.dotUsed = panel.dotUsed + 1
        local dot = panel.dotPool[panel.dotUsed]
        if not dot then
            dot = panel.child:CreateTexture(nil, "OVERLAY")
            panel.dotPool[panel.dotUsed] = dot
            table.insert(panel.graphObjects, dot)
        end
        dot:ClearAllPoints()
        dot:Show()
        dot:SetSize(5, 5)
        dot:SetPoint("TOPLEFT", x(point.at) - 2, -y(point.level) + 2)
        if point.kind == "baseline" then dot:SetColorTexture(1, .65, .2, 1)
        else dot:SetColorTexture(.2, .8, 1, 1) end
    end
    line(x(last.at), y(last.level), x(endAt), y(last.level), .2, .8, 1)
    panel.scroll:SetVerticalScroll(0)
end

function UI.refresh()
    if not panel or not panel:IsShown() then return end
    local character = getCharacter()
    if not character then return end
    H.init(character)
    hideGraph()
    panel.title:SetText(character.identity.name .. " — history and level progress")
    if mode == "graph" then graph(character); panel.status:SetText("Blue = level-up; orange = first observation. Gaps stay disconnected."); return end
    local rows = {}
    if mode == "logs" then
        for _, event in ipairs(character.history.events) do
            if category == "all" or event.kind == category then
                table.insert(rows, H.oslo(event.at) .. " · " .. event.kind
                    .. (event.data.synthetic and " [TEST]" or "") .. "\n"
                    .. "Event ID: " .. event.id .. "\nSelected groups: " .. H.serialize(event.group_ids or {}) .. "\nData: " .. H.serialize(event.data)
                    .. "\nStatus: collected locally; upload/delivery not confirmed in game.\n")
            end
        end
    elseif mode == "timing" then
        for _, item in ipairs(H.timing(character)) do
            table.insert(rows, "Level " .. item.level .. " → " .. item.next_level .. ": "
                .. H.duration(item.seconds) .. (item.partial and " (partial; tracking began during this level)" or " (recorded elapsed duration)")
                .. "\n" .. H.oslo(item.started_at) .. " → " .. H.oslo(item.finished_at) .. "\n")
        end
    else
        rows = {"Identity: " .. H.serialize(character.identity),
            "Selected group IDs: " .. H.serialize(character.group_ids or {}),
            "Sharing settings: " .. H.serialize(character.settings),
            "Current selected snapshot: " .. H.serialize(character.snapshot),
            "Snapshot observed at: " .. H.oslo(character.exported_at),
            "The companion reapplies privacy filters and uploads history in small batches.\n"
                .. "This is the addon's source data, not a receipt of HTTP or Discord delivery."}
    end
    local pages = math.max(1, math.ceil(#rows / PAGE_SIZE))
    page = math.max(1, math.min(page, pages))
    local selected = {}
    for i = (page - 1) * PAGE_SIZE + 1, math.min(page * PAGE_SIZE, #rows) do
        table.insert(selected, rows[i])
    end
    setText(#selected > 0 and table.concat(selected, "\n") or "No matching recorded history yet.")
    panel.status:SetText("Page " .. page .. "/" .. pages .. " · " .. #rows .. " records · Europe/Oslo. Scroll within each page.")
end

function UI.show(getter, selectedMode)
    getCharacter = getter
    if selectedMode then mode, page = selectedMode, 1 end
    if not panel then
        panel = CreateFrame("Frame", "WoWStatusHistoryWindow", UIParent)
        panel.graphObjects, panel.linePool, panel.fontPool, panel.dotPool = {}, {}, {}, {}
        panel.lineUsed, panel.fontUsed, panel.dotUsed = 0, 0, 0
        panel:SetSize(900, 620)
        panel:SetPoint("CENTER")
        panel:SetFrameStrata("DIALOG")
        panel:EnableMouse(true)
        panel:SetMovable(true)
        panel:RegisterForDrag("LeftButton")
        panel:SetScript("OnDragStart", panel.StartMoving)
        panel:SetScript("OnDragStop", panel.StopMovingOrSizing)
        local bg = panel:CreateTexture(nil, "BACKGROUND")
        bg:SetAllPoints()
        bg:SetColorTexture(.04, .04, .07, .98)
        panel.title = label(panel, "History", 24, -20, 850)
        local function tab(title, selected, x)
            button(panel, title, x, -55, 135, function() mode, page = selected, 1; UI.refresh() end)
        end
        tab("Event logs", "logs", 24)
        tab("Level graph", "graph", 169)
        tab("Level times", "timing", 314)
        tab("Export preview", "payload", 459)
        button(panel, "All / levels", 604, -55, 125, function()
            category = category == "all" and "level" or "all"
            mode, page = "logs", 1
            UI.refresh()
        end)
        panel.scroll = CreateFrame("ScrollFrame", nil, panel, "UIPanelScrollFrameTemplate")
        panel.scroll:SetPoint("TOPLEFT", 24, -100)
        panel.scroll:SetSize(822, 420)
        panel.child = CreateFrame("Frame", nil, panel.scroll)
        panel.child:SetSize(810, 420)
        panel.scroll:SetScrollChild(panel.child)
        panel.text = label(panel.child, "", 4, -4, 800)
        panel.text:SetJustifyV("TOP")
        panel.status = label(panel, "", 24, -535, 850)
        button(panel, "Previous page", 24, -573, 140, function() page = page - 1; UI.refresh() end)
        button(panel, "Next page", 174, -573, 140, function() page = page + 1; UI.refresh() end)
        button(panel, "Refresh", 324, -573, 100, UI.refresh)
        button(panel, "Close", 754, -573, 100, function() panel:Hide() end)
        table.insert(UISpecialFrames, "WoWStatusHistoryWindow")
    end
    panel:Show()
    UI.refresh()
end
