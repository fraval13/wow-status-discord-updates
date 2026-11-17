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
    if type(WoWStatusDB) ~= "table" then return {seen_keys={}} end
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

local function isNew(at, id, seen, keys) return at > seen or (at == seen and not keys[id]) end
-- Realm time for a PC-clock stamp (shown_at), so it sorts among realm-time ones.
local function realm(at)
    local offset = S.clockOffset and S.clockOffset()
    return at and offset and at - offset or at
end

-- One pass over the log: every reaction you received on a visible entry and
-- every one you sent, unsorted; the newest received time and the reactions of
-- that second; and how many received are new against (seen, keys). Reactions
-- from a friend hidden with "Hide completely" (#169) are left out, as on the
-- log card. Received text is kept as it arrived; callers escape it.
local function collect(seen, keys)
    local list, newest, newestKeys, unseen, J = {}, 0, {}, 0, WoWStatusJournal
    if not J then return list, newest, newestKeys, unseen end
    for _, e in ipairs(J.entries()) do
        if type(e) == "table" and not e.sample then
            if e.owner and type(e.reactions) == "table" and next(e.reactions) and J.visible(e) then
                for key, r in pairs(e.reactions) do
                    if type(r) == "table" and S.string(r.text) and not (WoWStatusMutes and WoWStatusMutes.hidden(key)) then
                        local id, at = tostring(e.id) .. "|" .. tostring(key), S.number(r.at) or S.number(e.at) or 0
                        list[#list + 1] = {entry=e, received=true, id=id, name=S.string(r.name) or "?", text=r.text, at=at}
                        if at > newest then newest, newestKeys = at, {} end
                        if at == newest then newestKeys[id] = true end
                        if isNew(at, id, seen, keys) then unseen = unseen + 1 end
                    end
                end
            elseif not e.owner then
                local said = J.sentReaction(e)
                if said and J.visible(e) then
                    -- reacted_at is new; older reactions were sent while the notification was up.
                    list[#list + 1] = {entry=e, received=false, id=tostring(e.id), name=friendName(e), text=said,
                        at=S.number(e.reacted_at) or realm(S.number(e.shown_at)) or S.number(e.at) or 0}
                end
            end
        end
    end
    return list, newest, newestKeys, unseen
end
local function seenState()
    local data = state()
    return S.number(data.seen) or 0, data.seen_keys
end

-- {entry, received, id, name, text, at}, newest first, at most R.LIMIT, and
-- the newest received time and keys (for markSeen).
function R.list()
    local list, newest, newestKeys = collect(seenState())
    table.sort(list, function(a, b)
        if a.at ~= b.at then return a.at > b.at end
        return a.id > b.id
    end)
    for i = #list, R.LIMIT + 1, -1 do list[i] = nil end
    return list, newest, newestKeys
end

-- Received reactions not yet looked at, however many were sent since. Cached:
-- the Activity page asks on every redraw, including while scrolling. Log
-- changes clear it (R.changed); a few seconds' expiry covers hidden friends
-- changing with the roster.
local unseenCache, unseenAt
function R.unseen()
    local now = S.now()
    if unseenCache and unseenAt and now - unseenAt < 5 then return unseenCache end
    local _, _, _, count = collect(seenState())
    unseenCache, unseenAt = count, now
    return count
end

-- Everything received up to newest counts as looked at.
local function markSeen(newest, newestKeys)
    local data = state()
    local seen = S.number(data.seen) or 0
    if newest > seen then data.seen, data.seen_keys = newest, {} end
    if newest == data.seen then
        for id in pairs(newestKeys) do data.seen_keys[id] = true end
    end
    unseenCache, unseenAt = 0, S.now()
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

function R.render(seeAll)
    if not page then return end
    local list, newest, newestKeys = R.list()
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
    if seeAll or active() then markSeen(newest, newestKeys) end
end

-- The log changed (a reaction came or went, a mute, an entry aged out): count
-- again, and redraw the page while it is the one on screen.
function R.changed()
    unseenCache, unseenAt = nil, nil
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
    -- The "new" marks stay for this visit, measured from the visit before. A
    -- visit lasts while the window stays open (Back from an opened update keeps
    -- the marks), unless something new came in meanwhile.
    local window = WoWStatusMainFrame
    if not page.before or not (window and window:IsShown()) or R.unseen() > 0 then
        local seen, keys = seenState()
        local copy = {}
        for id in pairs(keys) do copy[id] = true end
        page.before = {seen=seen, keys=copy}
        page.scroll:SetVerticalScroll(0)
    end
    -- Shown now (the window may only appear after this): all of it is seen.
    R.render(true)
end

function R.show() return WoWStatusMainWindow.show("reactions") end

WoWStatusMainWindow.register("reactions", "Reactions", build, show, {tab=false})
