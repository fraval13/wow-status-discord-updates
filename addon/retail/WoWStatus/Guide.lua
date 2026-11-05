-- First-time setup guide and "Show me around" tour (#64).
-- The guide appears once on a brand-new account (WoWStatusDB.guide_pending)
-- and can be skipped; Options > Notification previews opens it again.
-- The tour fills the main window with sample friends and events. Sample
-- entries live only in this file's memory: they are never added to the
-- saved log, sent to the group, relayed or seen by the companion.
WoWStatusGuide = {}
local G = WoWStatusGuide
local frame, step
local sampleEntries

local STEPS = {
    {title="Welcome to WoW Status",
     text="WoW Status shares your milestones with friends inside the game: level-ups, first dungeon clears, "
        .. "new professions and more. They appear as popups and in a shared activity log. Everyone only needs this addon."},
    {title="Choose or join a group",
     text="Pick a group ID and give the same ID to your friends. Everyone with the same ID shares updates. "
        .. "Groups are saved for your whole account.",
     action={"Open Groups", function() SlashCmdList.WOWSTATUS("groups") end}},
    {title="Choose your announcements",
     text="Decide which milestones you share: levels, deaths, first zone visits, professions, dungeon clears and more. "
        .. "You can change this at any time.",
     action={"Open announcement options", function() SlashCmdList.WOWSTATUS("") end}},
    {title="You're all set",
     text="Click the minimap book to open the WoW Status window. Want to see what it looks like with friends? "
        .. "Show me around fills it with sample adventurers. Sample data is never saved or sent.",
     action={"Show me around", function() G.tour() end}},
}

local function finish()
    if type(WoWStatusDB) == "table" then WoWStatusDB.guide_pending = nil end
    if frame then frame:Hide() end
end

local function render()
    local data = STEPS[step]
    frame.title:SetText(data.title)
    frame.body:SetText(data.text)
    frame.progress:SetText("Step " .. step .. " of " .. #STEPS)
    frame.action:SetShown(data.action ~= nil)
    if data.action then frame.action:SetText(data.action[1]) end
    frame.back:SetShown(step > 1)
    frame.next:SetText(step == #STEPS and "Done" or "Next")
    frame.skip:SetShown(step < #STEPS)
end

local function button(text, x, width, fn)
    local widget = CreateFrame("Button", nil, frame, "UIPanelButtonTemplate")
    widget:SetPoint("BOTTOMLEFT", x, 18); widget:SetSize(width, 28); widget:SetText(text)
    widget:SetScript("OnClick", fn)
    return widget
end

function G.show()
    if not frame then
        frame = CreateFrame("Frame", "WoWStatusGuideFrame", UIParent)
        frame:SetSize(560, 300); frame:SetPoint("CENTER"); frame:SetFrameStrata("DIALOG")
        frame:EnableMouse(true); frame:SetMovable(true); frame:RegisterForDrag("LeftButton")
        frame:SetScript("OnDragStart", frame.StartMoving); frame:SetScript("OnDragStop", frame.StopMovingOrSizing)
        local background = frame:CreateTexture(nil, "BACKGROUND")
        background:SetAllPoints(); background:SetColorTexture(.025, .035, .065, .97)
        frame.progress = frame:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
        frame.progress:SetPoint("TOPRIGHT", -24, -24)
        frame.title = frame:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
        frame.title:SetPoint("TOPLEFT", 24, -20); frame.title:SetWidth(400); frame.title:SetJustifyH("LEFT")
        frame.body = frame:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
        frame.body:SetPoint("TOPLEFT", 24, -60); frame.body:SetWidth(512); frame.body:SetJustifyH("LEFT")
        frame.body:SetWordWrap(true)
        frame.action = CreateFrame("Button", nil, frame, "UIPanelButtonTemplate")
        frame.action:SetPoint("TOPLEFT", 24, -170); frame.action:SetSize(260, 30)
        frame.action:SetScript("OnClick", function() local a = STEPS[step].action; if a then a[2]() end end)
        frame.skip = button("Skip", 24, 110, finish)
        frame.back = button("Back", 290, 110, function() step = math.max(1, step - 1); render() end)
        frame.next = button("Next", 420, 116, function()
            if step == #STEPS then finish() else step = step + 1; render() end
        end)
        table.insert(UISpecialFrames, "WoWStatusGuideFrame")
    end
    step = 1
    render()
    frame:Show()
    return frame
end

-- Called once per load after the character is ready.
function G.check()
    if type(WoWStatusDB) == "table" and WoWStatusDB.guide_pending then G.show(); return true end
    return false
end

-- Sample adventurers for the tour. Built fresh each time, never stored.
local function samples()
    local now = WoWStatusSafe.now()
    local function entry(n, sender, kind, ago, fields)
        local e = {id="sample:" .. n, sender=sender, kind=kind, at=now - ago, groups={}, origin="live", sample=true}
        for key, value in pairs(fields) do e[key] = value end
        return e
    end
    return {
        entry(1, "Brannic-Sample", "level", 300, {level=42, text="Reached level 42!"}),
        entry(2, "Elowen-Sample", "dungeon", 1500, {text="First clear: The Deadmines"}),
        entry(3, "Brannic-Sample", "profession", 2400, {text="Mining: Artisan (300 max)"}),
        entry(4, "Tamsin-Sample", "death", 3600, {text="Died"}),
        entry(5, "Elowen-Sample", "mount", 5400, {text="First mount: Brown Horse"}),
        entry(6, "Tamsin-Sample", "zone", 7200, {text="Entered Stranglethorn Vale"}),
        entry(7, "Brannic-Sample", "level", 9000, {level=41, text="Reached level 41!"}),
    }
end

function G.sampleEntries() return sampleEntries end
function G.touring() return sampleEntries ~= nil end

function G.tour()
    finish()
    sampleEntries = samples()
    local page = WoWStatusMainWindow.show("overview")
    if WoWStatusMainFrame then
        if not WoWStatusMainFrame.tourHooked then
            WoWStatusMainFrame.tourHooked = true
            WoWStatusMainFrame:SetScript("OnHide", function() G.endTour() end)
        end
    end
    return page
end

function G.endTour()
    if not sampleEntries then return end
    sampleEntries = nil
    WoWStatusMainWindow.refresh("activity"); WoWStatusMainWindow.refresh("overview")
end
