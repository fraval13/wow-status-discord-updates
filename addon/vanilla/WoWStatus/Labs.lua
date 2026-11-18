-- The Labs page (#222): one row per experiment, every one off until the player
-- switches it on. Nothing here is shared, sent or recorded; an experiment that
-- is off builds no frames and registers no events, because its own module asks
-- WoWStatusFeatures.enabled(id) before doing anything.
WoWStatusLabs = {}
local L = WoWStatusLabs
local F = WoWStatusFeatures
local page, registered
local ROW = 72
local function text(parent, font, x, y, width)
    local line = parent:CreateFontString(nil, "OVERLAY", font)
    line:SetPoint("TOPLEFT", x, y); line:SetWidth(width); line:SetJustifyH("LEFT")
    return line
end
local function render()
    if not page then return end
    local T = WoWStatusLocale.T
    local items = F.experiments()
    page.empty:SetShown(#items == 0)
    page.child:SetHeight(math.max(360, #items * ROW))
    for i, item in ipairs(items) do
        local row = page.rows[i]
        if not row then
            row = CreateFrame("CheckButton", nil, page.child, "UICheckButtonTemplate")
            row:SetPoint("TOPLEFT", 4, -(i - 1) * ROW)
            row:SetSize(32, 32)
            row.label = text(row, "GameFontNormalLarge", 38, -6, 600)
            row.description = text(row, "GameFontHighlightSmall", 38, -30, 490)
            row:SetScript("OnClick", function(self)
                F.set(self.id, self:GetChecked() and true or false)
                render()
            end)
            page.rows[i] = row
        end
        row.id = item.id
        row.label:SetText(T(item.label))
        row.description:SetText(item.description and T(item.description) or "")
        local enabled = F.enabled(item.id)
        row:SetChecked(enabled)
        if enabled and item.configure then
            if not row.configure then
                row.configure = CreateFrame("Button", nil, row, "UIPanelButtonTemplate")
                row.configure:SetPoint("TOPLEFT", 544, -6)
                row.configure:SetSize(100, 26)
            end
            row.configure:SetText(T("Configure"))
            row.configure:SetScript("OnClick", item.configure)
            row.configure:Show()
        elseif row.configure then
            row.configure:Hide()
        end
        row:Show()
    end
    for i = #items + 1, #page.rows do page.rows[i]:Hide() end
    WoWStatusUI.call(page.allOff, "SetEnabled", F.anyEnabled())
end
L.render = render
local function build(parent)
    local T = WoWStatusLocale.T
    page = CreateFrame("Frame", "WoWStatusLabsPage", parent); page:SetAllPoints(parent)
    page.heading = text(page, "GameFontNormalLarge", 24, -12, 730)
    page.heading:SetText(T("Labs"))
    page.hint = text(page, "GameFontHighlight", 24, -40, 730)
    page.hint:SetText(T("Experiments in progress. Each one only changes things for you, and every one starts switched off."))
    page.scroll = CreateFrame("ScrollFrame", nil, page, "UIPanelScrollFrameTemplate")
    page.scroll:SetPoint("TOPLEFT", 24, -78); page.scroll:SetSize(706, 400)
    page.child = CreateFrame("Frame", nil, page.scroll); page.child:SetSize(686, 360)
    page.scroll:SetScrollChild(page.child)
    page.empty = text(page.child, "GameFontHighlightLarge", 4, -24, 640)
    page.empty:SetText(T("No experiments in this version yet."))
    page.rows = {}
    page.allOff = CreateFrame("Button", nil, page, "UIPanelButtonTemplate")
    page.allOff:SetPoint("TOPLEFT", 24, -488); page.allOff:SetSize(260, 26)
    page.allOff:SetText(T("Turn all experiments off"))
    page.allOff:SetScript("OnClick", function() F.allOff(); render() end)
    return page
end
-- No tab: the tab row is full, so /wstatus labs and the Options button open it.
-- Registered once the main window's file has loaded, as Diagnostics does.
local function register()
    if registered or type(WoWStatusMainWindow) ~= "table" then return end
    registered = WoWStatusMainWindow.register("labs", "Labs", build, render, {tab = false}) and true
end
function L.show()
    register()
    if WoWStatusMainWindow then return WoWStatusMainWindow.show("labs") end
    return false
end
L.register = register
