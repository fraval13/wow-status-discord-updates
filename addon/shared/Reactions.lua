-- Recent reactions (#171): the reactions friends whispered about your updates
-- and the ones you sent them, newest first, so coming back from a raid shows
-- what you missed. A main-window page without a tab, opened from the Activity
-- page (or /wowstatus reactions). It only reads what the log already keeps
-- (e.reactions on your entries, e.reacted/e.whispered on friends'), so it is
-- bounded like the log: reactions go when their entry ages out. Choosing a row
-- opens that entry in the Activity log.
WoWStatusReactions = {}
local R = WoWStatusReactions
local S = WoWStatusSafe
local T = WoWStatusLocale.T
R.LIMIT, R.ROW = 50, 48
local page

-- Account-wide: when the page was last looked at, for the "new" marks and the
-- count on the Activity page's button.
local function state()
    if type(WoWStatusDB) ~= "table" then return {} end
    if type(WoWStatusDB.reactions) ~= "table" then WoWStatusDB.reactions = {} end
    return WoWStatusDB.reactions
end

local function escape(text) return (tostring(text):gsub("|", "||")) end
local function friendName(e)
    local sender = S.string(e.sender) or "?"
    local shown = WoWStatusRoster and WoWStatusRoster.displayName and WoWStatusRoster.displayName(sender)
    return S.string(shown) or sender:match("^[^-]+") or sender
end

-- {entry, received, name, text, at}, newest first, at most R.LIMIT. Reactions
-- from a friend hidden with "Hide completely" (#169) are left out, as on the
-- log card. Reaction text is kept as received; callers escape it.
function R.list()
    local list, J = {}, WoWStatusJournal
    if not J then return list end
    for _, e in ipairs(J.entries()) do
        if type(e) == "table" and not e.sample and J.visible(e) then
            if e.owner and type(e.reactions) == "table" then
                for key, r in pairs(e.reactions) do
                    if type(r) == "table" and S.string(r.text) and not (WoWStatusMutes and WoWStatusMutes.hidden(key)) then
                        list[#list + 1] = {entry=e, received=true, name=S.string(r.name) or "?", text=r.text,
                            at=S.number(r.at) or S.number(e.at) or 0}
                    end
                end
            elseif not e.owner then
                local said = S.string(e.whispered) or (S.string(e.reacted) and T(e.reacted))
                if said then
                    -- reacted_at is new; older reactions were sent while the notification was up.
                    list[#list + 1] = {entry=e, received=false, name=friendName(e), text=said,
                        at=S.number(e.reacted_at) or S.number(e.shown_at) or S.number(e.at) or 0}
                end
            end
        end
    end
    table.sort(list, function(a, b)
        if a.at ~= b.at then return a.at > b.at end
        return tostring(a.entry.id) .. a.name > tostring(b.entry.id) .. b.name
    end)
    for i = #list, R.LIMIT + 1, -1 do list[i] = nil end
    return list
end

-- Received reactions newer than the last look at the page.
function R.unseen()
    local seen, count = S.number(state().seen) or 0, 0
    for _, item in ipairs(R.list()) do
        if item.received and item.at > seen then count = count + 1 end
    end
    return count
end

-- "Reactions" or "Reactions (3)" for the Activity page's button.
function R.buttonLabel()
    local count = R.unseen()
    return count > 0 and (T("Reactions") .. " (" .. count .. ")") or T("Reactions")
end

local function rowFor(index)
    local UI = WoWStatusUI
    local row = page.rows[index]
    if row then return row end
    row = UI.box(page.list, 680, R.ROW - 4, "Button")
    row:SetScript("OnClick", function(self)
        if self.entry and WoWStatusJournal then WoWStatusJournal.focus(self.entry.id) end
    end)
    row.line = UI.text(row, "GameFontHighlight", 12, -7, 560); row.line:SetWordWrap(false)
    row.about = UI.text(row, "GameFontHighlightSmall", 12, -26, 650); row.about:SetWordWrap(false)
    row.new = UI.text(row, "GameFontNormal", 580, -7, 88, "RIGHT")
    page.rows[index] = row
    return row
end

function R.render()
    if not page or not page:IsShown() then return end
    local list = R.list()
    local before = page.before or 0
    for i, item in ipairs(list) do
        local row = rowFor(i)
        row:ClearAllPoints(); row:SetPoint("TOPLEFT", 0, -(i - 1) * R.ROW)
        local said = "|cffffd100" .. escape(T(item.text)) .. "|r"
        if item.received then
            row.line:SetText(said .. " " .. T("from") .. " " .. escape(item.name))
        else
            row.line:SetText(T("You to") .. " " .. escape(item.name) .. ": " .. said)
        end
        local e = item.entry
        local _, _, _, _, heading = WoWStatusPresentation.theme(e)
        local fact = WoWStatusJournal.deathText and WoWStatusJournal.deathText(e) or e.text or ""
        row.about:SetText(WoWStatusHistory.oslo(item.at) .. " · " .. escape(T(heading or "")) .. ": " .. escape(fact))
        row.new:SetText(item.received and item.at > before and T("New") or "")
        row.entry = e
        row:Show()
    end
    for i = #list + 1, #page.rows do page.rows[i].entry = nil; page.rows[i]:Hide() end
    page.list:SetHeight(math.max(1, #list * R.ROW))
    page.empty:SetShown(#list == 0)
    -- Looking at the page counts as having seen what is on it.
    local newest = list[1] and list[1].at or 0
    local data = state()
    if newest > (S.number(data.seen) or 0) then data.seen = newest end
end

-- A reaction came in or went out: redraw the page if it is open.
function R.redraw() if page and page:IsShown() then R.render() end end

local function build(parent)
    local UI = WoWStatusUI
    page = CreateFrame("Frame", "WoWStatusReactionsPage", parent); page:SetAllPoints(parent)
    page.heading = UI.text(page, "GameFontNormalLarge", 24, -12, 680)
    page.heading:SetText(T("Reactions"))
    page.intro = UI.text(page, "GameFontHighlightSmall", 24, -36, 680)
    page.intro:SetText(T("Reactions from friends to your updates, and the ones you sent. Choose one to see its update."))
    page.scroll = CreateFrame("ScrollFrame", nil, page, "UIPanelScrollFrameTemplate")
    page.scroll:SetPoint("TOPLEFT", 24, -60); page.scroll:SetSize(710, 470)
    page.list = CreateFrame("Frame", nil, page.scroll); page.list:SetSize(686, 1)
    page.scroll:SetScrollChild(page.list)
    page.empty = UI.text(page.list, "GameFontDisable", 0, -6, 660)
    page.empty:SetText(T("No reactions yet. When friends react to your updates, or you to theirs, they appear here."))
    page.rows = {}
    return page
end

local function show()
    if not page then return end
    -- The "new" marks stay for this visit, measured from the visit before.
    page.before = S.number(state().seen) or 0
    page.scroll:SetVerticalScroll(0)
    R.render()
end

function R.show() return WoWStatusMainWindow.show("reactions") end

WoWStatusMainWindow.register("reactions", "Reactions", build, show, {tab=false})
