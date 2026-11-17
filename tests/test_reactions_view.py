"""The recent Reactions page (#171): received and sent reactions, newest first."""
from pathlib import Path

import pytest
from test_addon import lupa
from test_client_compatibility import client_runtime
from test_gamepad import FRAMES
from test_journal import actor, clock, deliver_popup

ROOT = Path(__file__).parents[1]

# Thora levels up; Mira (in the group) whispers GZ! while Thora is away.
RECEIVE = '''
    __peers = {"Thora-TestRealm", "Mira-TestRealm", "Bob-TestRealm"}
    for id in pairs(character().group_ids) do WoWStatusPopups.peers(id) end
    for _ = 1, 3 do WoWStatusPopups.tick() end
    fire("PLAYER_LEVEL_UP", 2)
    fire("CHAT_MSG_WHISPER", "GZ!", "Mira-TestRealm")
'''


def own_level(lua):
    lua.execute('''
        for _, e in ipairs(WoWStatusJournal.entries()) do if e.owner and e.kind == "level" then __own = e end end
    ''')


def test_a_reaction_received_while_away_waits_on_the_page_and_is_counted_until_seen():
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute(RECEIVE)
    lua.execute('''
        local list = WoWStatusReactions.list()
        assert(#list == 1 and list[1].received and list[1].name == "Mira" and list[1].text == "GZ!")
        -- Not seen yet: the Activity page's button counts it.
        WoWStatusJournal.show()
        local button = WoWStatusActivityLog.reactionsButton
        assert(button.text == "Reactions (1)", button.text)
        assert(button.kind == "Button" and button.OnClick)
        button.OnClick(button)
        assert(WoWStatusMainWindow.active() == "reactions")
        local page = WoWStatusReactionsPage
        local row = page.rows[1]
        assert(row:IsShown() and row.line.text:find("GZ!", 1, true) and row.line.text:find("from Mira", 1, true), row.line.text)
        assert(row.about.text:find("level 2", 1, true), row.about.text)
        assert(row.new.text == "New")
        assert(not page.empty:IsShown())
        -- Seen now: the count goes, the mark stays for this visit.
        assert(WoWStatusReactions.unseen() == 0)
        WoWStatusReactions.render()
        assert(row.new.text == "New")
        -- Choosing the row opens its entry in the Activity log.
        row.OnClick(row)
        assert(WoWStatusMainWindow.active() == "activity")
        assert(WoWStatusActivityLog.reactionsButton.text == "Reactions")
        -- Next visit: no longer new.
        WoWStatusReactions.show()
        assert(WoWStatusReactionsPage.rows[1].new.text == "")
    ''')


def test_the_page_opens_by_command_and_says_when_there_is_nothing_yet():
    lua = actor('Thora')
    lua.execute('''
        SlashCmdList.WOWSTATUS("reactions")
        assert(WoWStatusMainWindow.active() == "reactions")
        assert(WoWStatusReactionsPage.empty:IsShown())
        local crumbs = WoWStatusMainWindow.crumbs()
        assert(crumbs[#crumbs].label == "Reactions")
        -- No tab of its own: the main window's tabs are full.
        for _, key in ipairs(WoWStatusMainWindow.pages()) do assert(key ~= "reactions") end
    ''')


def test_reactions_you_sent_are_listed_with_who_you_sent_them_to():
    own, friend = actor('Mira'), actor('Thora')
    friend.execute('WoWStatusPopups.CLICK_GUARD = 0')
    clock(own, 10)
    clock(friend, 10)
    own.eval('fire')('PLAYER_LEVEL_UP', 42)
    deliver_popup(own, friend)
    clock(friend, 25)
    friend.execute('''
        WoWStatusPopups.tick()
        local toast = WoWStatusLevelPopup
        toast.reactions[1].OnClick(toast.reactions[1])
        local list = WoWStatusReactions.list()
        assert(#list == 1 and not list[1].received and list[1].text == "GZ!")
        assert(list[1].at == time() and list[1].entry.reacted_at == time())
        -- What you sent is not counted as new.
        assert(WoWStatusReactions.unseen() == 0)
        WoWStatusReactions.show()
        local row = WoWStatusReactionsPage.rows[1]
        assert(row.line.text:find("You to Mira: ", 1, true) and row.line.text:find("GZ!", 1, true), row.line.text)
        assert(row.new.text == "")
    ''')


def test_markup_in_names_and_text_is_escaped_and_hidden_friends_are_left_out():
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute(RECEIVE)
    own_level(lua)
    lua.execute('''
        __own.reactions["eve-testrealm"] = {name="|cffff0000Eve|r", text="|TInterface\\\\Icons\\\\x:64|t", at=time() + 1}
        WoWStatusReactions.show()
        local row = WoWStatusReactionsPage.rows[1]
        assert(row.line.text:find("||TInterface", 1, true), row.line.text)
        assert(row.line.text:find("||cffff0000Eve||r", 1, true), row.line.text)
        assert(not row.line.text:find("from |c", 1, true))
        -- Hide completely (#169): gone from the page and the count, as from the log card.
        WoWStatusMutes.setCharacter("Eve-TestRealm", "hide")
        local list = WoWStatusReactions.list()
        assert(#list == 1 and list[1].name == "Mira")
    ''')


def test_the_page_is_bounded_and_newest_first():
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute(RECEIVE)
    own_level(lua)
    lua.execute('''
        for i = 1, 20 do
            __own.reactions["f" .. i] = {name="F" .. i, text="GZ!", at=time() + i}
        end
        for i = 1, 60 do
            table.insert(WoWStatusDB.journal.entries, {id="friend:" .. i, sender="Bob-TestRealm", kind="level",
                text="Reached level " .. i, at=time() - 100, shown_at=time() - 100 + i, reacted="GZ!",
                groups=__own.groups, client=__own.client, origin="live"})
        end
        local list = WoWStatusReactions.list()
        assert(#list == WoWStatusReactions.LIMIT, #list)
        for i = 2, #list do assert(list[i - 1].at >= list[i].at) end
        assert(list[1].name == "F20")
    ''')


@pytest.mark.parametrize('edition', ['vanilla', 'forever', 'tbc', 'retail'])
@pytest.mark.parametrize('language', ['en', 'nn'])
def test_the_page_opens_in_every_edition_and_language(edition, language):
    lua = client_runtime(edition)
    lua.execute(f'WoWStatusLocale.set("{language}")')
    lua.execute('''
        WoWStatusJournal.show()
        local button = WoWStatusActivityLog.reactionsButton
        assert(button.text == WoWStatusLocale.T("Reactions"))
        button.OnClick(button)
        assert(WoWStatusMainWindow.active() == "reactions")
        assert(WoWStatusReactionsPage:GetParent() == WoWStatusMainFrame.content)
        assert(WoWStatusReactionsPage.scroll.kind == "ScrollFrame")
        assert(WoWStatusReactionsPage.heading.text == WoWStatusLocale.T("Reactions"))
    ''')
    if language == 'nn':
        assert lua.eval('WoWStatusReactionsPage.heading.text') == 'Reaksjonar'
        assert lua.eval('WoWStatusLocale.T("You to")') == 'Du til'


def test_rows_are_reachable_with_a_controller():
    runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
    runtime.execute('unpack = unpack or table.unpack')
    runtime.execute(FRAMES)
    runtime.execute((ROOT / 'addon/shared/Gamepad.lua').read_text(encoding='utf-8'))
    runtime.execute('''
        main = window("WoWStatusMainFrame", 100, 100, 760, 560)
        WoWStatusMainWindow = {pages=function() return {"activity"} end, active=function() return "reactions" end,
            show=function() main:Show() end, hide=function() main:Hide() end, back=function() return false end,
            refresh=function() end}
        local methods=getmetatable(CreateFrame("Frame")).__index
        function methods:SetSize(w,h) if self.rect then self.rect[3],self.rect[4]=w,h end end
        function methods:SetText(text) self.text=text end
        function methods:CreateFontString() return CreateFrame("FontString",nil,self) end
        function methods:SetJustifyH() end
        function methods:SetWordWrap() end
        function methods:SetScrollChild(child) self.child=child end
        function methods:SetShown(value) self.visible=value end
        WoWStatusLocale={T=function(text) return text end,F=string.format}
        WoWStatusSafe={string=function(v) return type(v)=="string" and v or nil end,
            number=function(v) return type(v)=="number" and v or nil end}
        WoWStatusUI={text=function(parent) return CreateFrame("FontString",nil,parent) end,
            box=function(parent,w,h,kind) return CreateFrame(kind or "Frame",nil,parent) end}
        WoWStatusPresentation={theme=function() return nil,1,1,1,"Level up" end}
        WoWStatusHistory={oslo=function() return "2026-11-17 09:00" end}
        local entry={id="one",owner="me",kind="level",text="Reached level 2",at=10,
            reactions={mira={name="Mira",text="GZ!",at=20}}}
        WoWStatusJournal={entries=function() return {entry} end, visible=function() return true end,
            deathText=function(e) return e.text end, focus=function(id) __focused=id end}
        WoWStatusMainWindow.register=function(key,title,build,refresh) __build,__refresh=build,refresh end
    ''')
    runtime.execute((ROOT / 'addon/shared/Reactions.lua').read_text(encoding='utf-8'))
    runtime.execute('''
        local page=__build(main); page.visible=true; page.list.visible=true; page.scroll.visible=true
        __refresh(page)
        local row=page.rows[1]
        row.rect={130,400,680,44}
        local reached={}
        for _,control in ipairs(WoWStatusGamepad.controls(main,{main})) do reached[control]=true end
        assert(reached[row] and row.kind=="Button")
        WoWStatusGamepad.update()
        press("PADDDOWN")
        WoWStatusGamepad.setFocus(row);press("PAD1")
        assert(__focused=="one")
    ''')
