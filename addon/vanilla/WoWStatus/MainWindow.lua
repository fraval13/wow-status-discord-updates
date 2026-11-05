-- Main window with tabbed pages (#57). Modules add pages with
-- WoWStatusMainWindow.register(key, title, build, refresh); this file never
-- needs to change for a new page. build(parent) creates the page once inside
-- the content area and returns its frame; refresh(frame) runs whenever the page
-- is shown. The last page and the window position are saved account-wide in
-- WoWStatusDB.main_window. Plain buttons are used as tabs because tab templates
-- differ between the four clients.
WoWStatusMainWindow = {}
local M = WoWStatusMainWindow
local pages, order, window, active = {}, {}, nil, nil
M.WIDTH, M.HEIGHT, M.CONTENT_HEIGHT = 780, 680, 540
local TAB_WIDTH, TAB_GAP = 130, 8

local function saved()
    if type(WoWStatusDB) ~= "table" then return {} end
    if type(WoWStatusDB.main_window) ~= "table" then WoWStatusDB.main_window = {} end
    return WoWStatusDB.main_window
end

function M.has(key) return pages[key] ~= nil end
function M.pages() return order end
function M.active() return window and window:IsShown() and active or nil end

local function addTab(page, index)
    local tab = CreateFrame("Button", nil, window, "UIPanelButtonTemplate")
    tab:SetPoint("TOPLEFT", 24 + (index - 1) * (TAB_WIDTH + TAB_GAP), -52)
    tab:SetSize(TAB_WIDTH, 26); tab:SetText(page.title)
    tab:SetScript("OnClick", function() M.show(page.key) end)
    page.tab = tab
end

function M.register(key, title, build, refresh)
    if type(key) ~= "string" or pages[key] then return false end
    local page = {key=key, title=title, build=build, refresh=refresh}
    pages[key] = page
    table.insert(order, key)
    if window then addTab(page, #order) end
    return true
end

local function restorePosition()
    local position = saved().position
    window:ClearAllPoints()
    if type(position) == "table" and type(position.point) == "string" and type(position.x) == "number"
        and type(position.y) == "number" then
        window:SetPoint(position.point, UIParent, position.relative or position.point, position.x, position.y)
    else
        window:SetPoint("CENTER")
    end
end

local function create()
    window = CreateFrame("Frame", "WoWStatusMainFrame", UIParent)
    window:SetSize(M.WIDTH, M.HEIGHT); window:SetFrameStrata("FULLSCREEN_DIALOG")
    window:EnableMouse(true); window:SetMovable(true); window:RegisterForDrag("LeftButton")
    window:SetScript("OnDragStart", window.StartMoving)
    window:SetScript("OnDragStop", function(self)
        self:StopMovingOrSizing()
        if self.GetPoint then
            local point, _, relative, x, y = self:GetPoint(1)
            if type(point) == "string" and type(x) == "number" and type(y) == "number" then
                saved().position = {point=point, relative=relative, x=x, y=y}
            end
        end
    end)
    local background = window:CreateTexture(nil, "BACKGROUND")
    background:SetAllPoints(); background:SetColorTexture(.025, .035, .065, .98)
    window.background = background
    window.title = window:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
    window.title:SetPoint("TOPLEFT", 24, -20); window.title:SetText("WoW Status")
    window.content = CreateFrame("Frame", nil, window)
    window.content:SetPoint("TOPLEFT", 0, -86); window.content:SetSize(M.WIDTH, M.CONTENT_HEIGHT)
    -- The game's own close X, top right as on its windows; a plain "X" button if
    -- a client lacks the template.
    local ok, close = pcall(CreateFrame, "Button", nil, window, "UIPanelCloseButton")
    if not ok or not close then
        close = CreateFrame("Button", nil, window, "UIPanelButtonTemplate")
        close:SetSize(28, 28); close:SetText("X")
    end
    close:SetPoint("TOPRIGHT", -6, -6)
    close:SetScript("OnClick", function() window:Hide() end)
    window.close = close
    for index, key in ipairs(order) do addTab(pages[key], index) end
    table.insert(UISpecialFrames, "WoWStatusMainFrame")
    restorePosition()
    if WoWStatusTheme then WoWStatusTheme.attach(window, background) end
end

-- Open a page by key, or the last page used (Activity on first use).
function M.show(key)
    if not key or not pages[key] then key = saved().page end
    if not key or not pages[key] then key = pages.activity and "activity" or order[1] end
    if not key then return nil end
    if not window then create() end
    for _, other in ipairs(order) do
        local page = pages[other]
        if page.frame and other ~= key then page.frame:Hide() end
        if page.tab and page.tab.SetEnabled then page.tab:SetEnabled(other ~= key) end
    end
    local page = pages[key]
    if not page.frame and page.build then page.frame = page.build(window.content) end
    active = key
    saved().page = key
    local tour = WoWStatusGuide and WoWStatusGuide.touring() and " (sample tour, nothing here is real)" or ""
    window.title:SetText("WoW Status — " .. page.title .. tour)
    if page.frame then page.frame:Show() end
    if page.refresh then page.refresh(page.frame) end
    window:Show()
    return page.frame
end

function M.hide() if window then window:Hide() end end

-- Pages call this when their data changes; only a visible page redraws.
function M.refresh(key)
    local page = pages[key]
    if window and window:IsShown() and active == key and page and page.refresh then page.refresh(page.frame) end
end
