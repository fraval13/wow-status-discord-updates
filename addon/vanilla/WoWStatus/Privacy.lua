-- "What is shared" (#152): a plain statement of what WoW Status sends, to whom,
-- what stays on this computer and how to stop. Opened from the setup guide and
-- with /wstatus privacy. Display only: nothing here sends, saves or changes a
-- setting. Every sentence describes the code as it is; when sharing changes,
-- change this page (and the homepage's "What you share" section) with it.
WoWStatusPrivacy = {}
local PV = WoWStatusPrivacy
local T = WoWStatusLocale.T
local frame

-- Each section: a heading and its bullet lines, each line translated on its own.
PV.SECTIONS = {
    {"What is sent",
     {"The milestones your announcement choices allow: level-ups, deaths, first zone visits, every 100 "
        .. "quests, profession and dungeon milestones, mounts, reputation, class abilities, PvP rank, first "
        .. "armor equips, and session recaps if you tick them. A death also names what killed you, and where "
        .. "when Location is ticked.",
      "Your character list: the name, race, sex, class, level and XP progress of each character shown to "
        .. "friends, when it reached each tenth level, the player name you chose, a random player ID and your "
        .. "addon version. A hidden character's name is still sent, marked as hidden, so friends' lists leave it "
        .. "out, even after you stop sharing your list.",
      "The character details you tick: played time, professions with skill levels, completed quests, gold "
        .. "and gold earned, monsters killed, dungeons, mounts and honor kills, total deaths, and the gear you "
        .. "wear with its combat stats. Friends see them change as you play.",
      "The name of a group you tick as Listed, to the members of your other groups.",
      "Only when you click: a reaction whisper such as GZ!, the homepage link from Share WoW Status, or an "
        .. "invitation to a group, with its name, to the friend you invite."}},
    {"Who receives it",
     {"The members of your groups. Updates travel as the game's own addon whispers to the members it finds "
        .. "in each group's chat channel, and friends who are online pass them on to members who were offline.",
      "Anyone who enters the same group name becomes a member, so give it only to people you trust.",
      "Whispers you click to send go to the player you click on, who may not be in a group with you.",
      "Nothing goes to a website, to the author or to any server except the game's own, which carries every "
        .. "whisper."}},
    {"What stays on your computer",
     {"Screenshots, your caption personality and reaction voice (a reaction you click is whispered in that "
        .. "voice), your notification and window settings, quiet hours, muted friends and your saved log."}},
    {"What is never sent",
     {"Chat you type or read, mail, bag contents, your guild (even with Guild ticked), and which quests you "
        .. "hand in.",
      "The only text you type that travels is your player name and the name of a group you list or invite "
        .. "someone to."}},
    {"How to stop",
     {"Untick an announcement, or one of the character details listed above, in Options. Class, race and "
        .. "level travel with your character list, so unticking them there does not stop them.",
      "Untick a character under Characters shown to friends: it leaves everyone's character list, "
        .. "leaderboard and gear view.",
      "Untick Share my character list on the Characters page: your list, details and gear stop, and your "
        .. "friends are told to forget your list.",
      "Type /wstatus pause, or untick Share my progress, to stop this character's announcements. Its "
        .. "character list entry and ticked details keep going until you hide it or untick them as above.",
      "Remove a group in /wstatus groups to leave it."}},
    {"What is kept",
     {"Your log keeps the newest 2,000 of your own entries (at most 1,000 of them sent to no group) and "
        .. "2,000 received ones.",
      "Apart from screenshots, which are pictures in the game's Screenshots folder, everything WoW Status "
        .. "saves is in WTF/Account/<account>/SavedVariables/WoWStatus.lua, with the game's backup copy "
        .. "WoWStatus.lua.bak beside it. Removing the addon folder deletes neither; delete both files while the "
        .. "game is closed.",
      "Friends keep the updates they already received in their own log."}},
}

-- The whole statement as shown, in the chosen language.
function PV.text()
    local lines = {}
    for _, section in ipairs(PV.SECTIONS) do
        if #lines > 0 then lines[#lines + 1] = " " end
        lines[#lines + 1] = "|cffffd100" .. T(section[1]) .. "|r"
        for _, line in ipairs(section[2]) do lines[#lines + 1] = "• " .. T(line) end
    end
    return table.concat(lines, "\n")
end

local function build()
    frame = CreateFrame("Frame", "WoWStatusPrivacyFrame", UIParent)
    frame:SetSize(600, 480); frame:SetPoint("CENTER"); frame:SetFrameStrata("FULLSCREEN_DIALOG")
    frame:EnableMouse(true); frame:SetMovable(true); frame:RegisterForDrag("LeftButton")
    frame:SetScript("OnDragStart", frame.StartMoving); frame:SetScript("OnDragStop", frame.StopMovingOrSizing)
    local background = frame:CreateTexture(nil, "BACKGROUND")
    background:SetAllPoints(); background:SetColorTexture(.025, .035, .065, .97)
    frame.title = frame:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
    frame.title:SetPoint("TOPLEFT", 24, -20); frame.title:SetWidth(540); frame.title:SetJustifyH("LEFT")
    frame.scroll = CreateFrame("ScrollFrame", nil, frame, "UIPanelScrollFrameTemplate")
    frame.scroll:SetPoint("TOPLEFT", 24, -56); frame.scroll:SetSize(526, 360)
    frame.child = CreateFrame("Frame", nil, frame.scroll); frame.child:SetSize(510, 1)
    frame.scroll:SetScrollChild(frame.child)
    frame.body = frame.child:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    frame.body:SetPoint("TOPLEFT", 0, 0); frame.body:SetWidth(500)
    frame.body:SetJustifyH("LEFT"); frame.body:SetJustifyV("TOP"); frame.body:SetWordWrap(true)
    frame.close = CreateFrame("Button", nil, frame, "UIPanelButtonTemplate")
    frame.close:SetPoint("BOTTOMRIGHT", -24, 18); frame.close:SetSize(130, 28)
    frame.close:SetScript("OnClick", function() frame:Hide() end)
    table.insert(UISpecialFrames, "WoWStatusPrivacyFrame")
end

function PV.show()
    if not frame then build() end
    -- Texts are set on every opening, so a language change shows at once.
    frame.title:SetText(T("What WoW Status shares"))
    frame.close:SetText(T("Close"))
    frame.body:SetText(PV.text())
    local S = WoWStatusSafe
    frame.child:SetHeight(math.max(1, (S.number(S.call(frame.body.GetStringHeight, frame.body)) or 0) + 8))
    frame:Show()
    return frame
end
