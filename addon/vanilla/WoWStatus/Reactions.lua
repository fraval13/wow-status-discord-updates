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

-- Account-wide: the newest received reaction looked at on the page (seen, in
-- realm time) and which ones of that same second (seen_keys), for the "new"
-- marks and the count on the Activity page's button.
local function state()
    if type(WoWStatusDB) ~= "table" then return {} end
    if type(WoWStatusDB.reactions) ~= "table" then WoWStatusDB.reactions = {} end
    local data = WoWStatusDB.reactions
    if type(data.seen_keys) ~= "table" then data.seen_keys = {} end
    return data
end

local function escape(text) return (tostring(text):gsub("|", "||")) end
local function friendName(e)
    local sender = S.string(e.sender) or "?"
    local shown = WoWStatusRoster and WoWStatusRoster.displayName and WoWStatusRoster.displayName(sender)
    return S.string(shown) or sender:match("^[^-]+") or sender
end

-- Calls fn(entry, key, reaction) for each reaction received on a visible log
-- entry. Reactions from a friend hidden with "Hide completely" (#169) are left
-- out, as on the log card.
local function eachReceived(fn)
    local J = WoWStatusJournal
    if not J then return end
    for _, e in ipairs(J.entries()) do
        if type(e) == "table" and e.owner and not e.sample and type(e.reactions) == "table" and J.visible(e) then
            for key, r in pairs(e.reactions) do
                if type(r) == "table" and S.string(r.text) and not (WoWStatusMutes and WoWStatusMutes.hidden(key)) then
                    fn(e, key, r)
                end
            end
        end
    end
end
local function receivedAt(e, r) return S.number(r.at) or S.number(e.at) or 0 end
local function isNew(at, id, seen, keys) return at > seen or (at == seen and not keys[id]) end

-- {entry, received, id, name, text, at}, newest first, at most R.LIMIT.
-- Received text is kept as it arrived; callers escape it.
function R.list()
    local list, J = {}, WoWStatusJournal
    if not J then return list end
    eachReceived(function(e, key, r)
        list[#list + 1] = {entry=e, received=true, id=tostring(e.id) .. "|" .. tostring(key),
            name=S.string(r.name) or "?", text=r.text, at=receivedAt(e, r)}
    end)
    for _, e in ipairs(J.entries()) do
        if type(e) == "table" and not e.owner and not e.sample and J.visible(e) then
            local said = J.sentReaction(e)
            if said then
                -- reacted_at is new; older reactions were sent while the notification was up.
                list[#list + 1] = {entry=e, received=false, id=tostring(e.id), name=friendName(e), text=said,
                    at=S.number(e.reacted_at) or S.number(e.shown_at) or S.number(e.at) or 0}
            end
        end
    end
    table.sort(list, function(a, b)
        if a.at ~= b.at then return a.at > b.at end
        return a.id > b.id
    end)
    for i = #list, R.LIMIT + 1, -1 do list[i] = nil end
    return list
end

-- Received reactions not yet looked at, however many were sent since. Cached:
-- the Activity page asks on every redraw, including while scrolling.
local unseenCache
function R.unseen()
    if unseenCache then return unseenCache end
    local data, count = state(), 0
    local seen, keys = S.number(data.seen) or 0, data.seen_keys
    eachReceived(function(e, key, r)
        if isNew(receivedAt(e, r), tostring(e.id) .. "|" .. tostring(key), seen, keys) then count = count + 1 end
    end)
    unseenCache = count
    return count
end

-- Everything received so far counts as looked at.
local function markSeen()
    local data = state()
    local seen = S.number(data.seen) or 0
    local newest = seen
    eachReceived(function(e, _, r) newest = math.max(newest, receivedAt(e, r)) end)
    if newest > seen then data.seen, data.seen_keys = newest, {} end
    eachReceived(function(e, key, r)
        if receivedAt(e, r) == data.seen then data.seen_keys[tostring(e.id) .. "|" .. tostring(key)] = true end
    end)
    unseenCache = 0
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

local function active()
    return page ~= nil and WoWStatusMainWindow.active and WoWStatusMainWindow.active() == "reactions"
end

function R.render()
    if not page then return end
    local list = R.list()
    local before = page.before or {seen=0, keys={}}
    for i, item in ipairs(list) do
        local row = rowFor(i)
        row:ClearAllPoints(); row:SetPoint("TOPLEFT", 0, -(i - 1) * R.ROW)
        if item.received then
            -- Shown as the log card shows it (J.reactionsText).
            row.line:SetText("|cffffd100" .. escape(T(item.text)) .. "|r " .. T("from") .. " " .. escape(item.name))
        else
            -- The words actually whispered, as sent.
            row.line:SetText(T("You to") .. " " .. escape(item.name) .. ": |cffffd100" .. escape(item.text) .. "|r")
        end
        local e = item.entry
        local _, _, _, _, heading = WoWStatusPresentation.theme(e)
        local fact = WoWStatusJournal.deathText and WoWStatusJournal.deathText(e) or e.text or ""
        row.about:SetText(WoWStatusHistory.oslo(item.at) .. " · " .. escape(T(heading or "")) .. ": " .. escape(fact))
        row.new:SetText(item.received and isNew(item.at, item.id, before.seen, before.keys) and T("New") or "")
        row.entry = e
        row:Show()
    end
    for i = #list + 1, #page.rows do page.rows[i].entry = nil; page.rows[i]:Hide() end
    page.list:SetHeight(math.max(1, #list * R.ROW))
    page.empty:SetShown(#list == 0)
    -- Looking at the page counts as having seen what is on it.
    if active() then markSeen() end
end

-- The log changed (a reaction came or went, a mute, an entry aged out): count
-- again, and redraw the page while it is the one on screen.
function R.changed()
    unseenCache = nil
    if active() then R.render() end
end

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
    local data, keys = state(), {}
    for id in pairs(state().seen_keys) do keys[id] = true end
    page.before = {seen=S.number(data.seen) or 0, keys=keys}
    page.scroll:SetVerticalScroll(0)
    R.render()
    -- Shown now (the window may only appear after this): all of it is seen.
    markSeen()
end

function R.show() return WoWStatusMainWindow.show("reactions") end

WoWStatusMainWindow.register("reactions", "Reactions", build, show, {tab=false})
