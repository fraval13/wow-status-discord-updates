-- Main window with tabbed pages (#57). Modules add pages with
-- WoWStatusMainWindow.register(key, title, build, refresh); this file never
-- needs to change for a new page. build(parent) creates the page once inside
-- the content area and returns its frame; refresh(frame) runs whenever the page
-- is shown. The last page and the window position are saved account-wide in
-- WoWStatusDB.main_window. Plain buttons are used as tabs because tab templates
-- differ between the four clients.
WoWStatusMainWindow = {}
local M = WoWStatusMainWindow
local T = WoWStatusLocale.T
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
    tab:SetSize(TAB_WIDTH, 26); tab:SetText(T(page.title))
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
    -- The game's gold dialog border around the window, as on its own windows.
    local border = CreateFrame("Frame", nil, window, BackdropTemplateMixin and "BackdropTemplate" or nil)
    border:SetPoint("TOPLEFT", -6, 6); border:SetPoint("BOTTOMRIGHT", 6, -6)
    if border.SetBackdrop then
        pcall(border.SetBackdrop, border, {edgeFile="Interface\\DialogFrame\\UI-DialogBox-Border", edgeSize=32})
    end
    window.border = border
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
    -- Back, and the breadcrumbs after the title: Home › Characters › Mira › Activity.
    window.back = CreateFrame("Button", nil, window, "UIPanelButtonTemplate")
    window.back:SetPoint("TOPRIGHT", -44, -16); window.back:SetSize(80, 24); window.back:SetText("< " .. T("Back"))
    window.back:SetScript("OnClick", function() M.back() end)
    window.crumbs = {}
    table.insert(UISpecialFrames, "WoWStatusMainFrame")
    restorePosition()
    if WoWStatusTheme then WoWStatusTheme.attach(window, background) end
end

-- Navigation like a browser: each step (a page, a profile, a character's
-- activity) is a state {page, profile, character}; Back returns to the one
-- before, and the breadcrumbs at the top lead to Home (the Overview), the page
-- and the character. Kept until the next /reload, at most 30 steps.
local history, state, restoring = {}, nil, false
local function same(a, b) return a and b and a.page == b.page and a.profile == b.profile and a.character == b.character end
function M.state() return state end
function M.go(next)
    if restoring or type(next) ~= "table" then return end
    if state and not same(state, next) then
        table.insert(history, state)
        if #history > 30 then table.remove(history, 1) end
    end
    state = next
    if M.path then M.path() end
end
-- Show a state without recording it (Back and the breadcrumbs).
local function apply(target)
    restoring = true
    if target.character and WoWStatusJournal then WoWStatusJournal.showCharacter(target.character)
    else
        M.show(target.page, true)
        if WoWStatusProfile then
            if target.profile then WoWStatusProfile.showByName(target.profile) else WoWStatusProfile.hide() end
        end
    end
    restoring = false
    state = target
    if M.path then M.path() end
end
function M.back()
    local previous = table.remove(history)
    if not previous then return false end
    apply(previous)
    return true
end
function M.open(target)
    if state and not same(state, target) then
        table.insert(history, state)
        if #history > 30 then table.remove(history, 1) end
    end
    apply(target)
end

-- Open a page by key, or the last page used (Activity on first use). quiet: the
-- caller records a more precise state itself.
function M.show(key, quiet)
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
    if page.frame then page.frame:Show() end
    if page.refresh then page.refresh(page.frame) end
    window:Show()
    if not quiet then
        if key == "characters" and WoWStatusProfile then WoWStatusProfile.hide() end
        M.go({page=key})
    end
    if M.path then M.path() end
    return page.frame
end

function M.hide() if window then window:Hide() end end

-- The breadcrumbs for the current state; every part but the last is a link.
function M.crumbs()
    local current = state or {page=active}
    local list = {{label=T("Home"), target={page="overview"}}}
    local function title(key) return pages[key] and T(pages[key].title) or key end
    if current.character then
        local name = current.character:match("^[^-]+") or current.character
        local fromProfile = history[#history] and history[#history].profile == current.character
        if fromProfile then
            list[#list + 1] = {label=title("characters"), target={page="characters"}}
            list[#list + 1] = {label=name, target={page="characters", profile=current.character}}
            list[#list + 1] = {label=title("activity")}
        else
            list[#list + 1] = {label=title("activity"), target={page="activity"}}
            list[#list + 1] = {label=name}
        end
    elseif current.profile then
        list[#list + 1] = {label=title("characters"), target={page="characters"}}
        list[#list + 1] = {label=current.profile:match("^[^-]+") or current.profile}
    elseif current.page and current.page ~= "overview" then
        list[#list + 1] = {label=title(current.page)}
    else
        list[1].target = nil -- Home is where you are.
    end
    list[#list].target = nil
    return list
end
function M.path()
    if not window then return end
    local list = M.crumbs()
    local tour = WoWStatusGuide and WoWStatusGuide.touring() and (" " .. T("(sample tour, nothing here is real)")) or ""
    window.title:SetText("WoW Status" .. tour)
    local x = 24 + (window.title.GetStringWidth and window.title:GetStringWidth() or 100) + 18
    for i, crumb in ipairs(list) do
        local link = window.crumbs[i]
        if not link then
            link = CreateFrame("Button", nil, window)
            link:SetSize(10, 20)
            link.label = link:CreateFontString(nil, "OVERLAY", "GameFontNormal")
            link.label:SetPoint("LEFT", 0, 0)
            link:SetScript("OnClick", function(self) if self.target then M.open(self.target) end end)
            link:SetScript("OnEnter", function(self) if self.target then self.label:SetTextColor(1, 1, 1) end end)
            link:SetScript("OnLeave", function(self) M.path() end)
            window.crumbs[i] = link
        end
        local text = (i > 1 and "›  " or "") .. tostring(crumb.label):gsub("|", "||")
        link.label:SetText(text)
        if crumb.target then link.label:SetTextColor(1, .82, 0) else link.label:SetTextColor(.85, .85, .85) end
        link.target = crumb.target
        local width = (link.label.GetStringWidth and link.label:GetStringWidth() or #text * 7) + 10
        link:SetWidth(width)
        link:ClearAllPoints(); link:SetPoint("TOPLEFT", x, -20)
        link:Show()
        x = x + width + 4
    end
    for i = #list + 1, #window.crumbs do window.crumbs[i]:Hide() end
    if window.back.SetEnabled then window.back:SetEnabled(#history > 0) end
end
M.history = function() return history end

-- Pages call this when their data changes; only a visible page redraws.
function M.refresh(key)
    local page = pages[key]
    if window and window:IsShown() and active == key and page and page.refresh then page.refresh(page.frame) end
end
