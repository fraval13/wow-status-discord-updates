"""What is shared (#152): the /wstatus privacy page, its guide step and the homepage section."""
import re
from pathlib import Path

from test_addon import lupa, make_lua
from test_gamepad import FRAMES, main_window

ROOT = Path(__file__).parents[1]


def statement_lines(lua):
    sections = lua.eval('WoWStatusPrivacy.SECTIONS')
    found = []
    for i in range(1, len(sections) + 1):
        section = sections[i]
        found.append(section[1])
        lines = section[2]
        found += [lines[j] for j in range(1, len(lines) + 1)]
    return found


def test_slash_command_opens_the_page_and_nothing_is_sent():
    lua = make_lua()
    lua.execute('''
        local sent = #__sent
        SlashCmdList.WOWSTATUS("privacy")
        assert(WoWStatusPrivacyFrame:IsShown())
        assert(WoWStatusPrivacyFrame.title.text == "What WoW Status shares")
        assert(#__sent == sent)
        local listed = false
        for _, name in ipairs(UISpecialFrames) do listed = listed or name == "WoWStatusPrivacyFrame" end
        assert(listed, "B / Escape closes the page")
        WoWStatusPrivacyFrame.close.OnClick(WoWStatusPrivacyFrame.close)
        assert(not WoWStatusPrivacyFrame:IsShown())
    ''')
    body = lua.eval('WoWStatusPrivacy.text()')
    for heading in ('What is sent', 'Who receives it', 'What stays on your computer', 'What is never sent',
                    'How to stop', 'What is kept'):
        assert heading in body


def test_the_guide_has_a_step_that_opens_the_page():
    lua = make_lua(guide=True)
    lua.execute('''
        local frame = WoWStatusGuideFrame
        for _ = 1, 3 do frame.next.OnClick(frame.next) end
        assert(frame.title.text == "What friends can see" and frame.progress.text == "Step 4 of 5")
        assert(frame.action.text == "What is shared")
        frame.action.OnClick(frame.action)
        assert(WoWStatusPrivacyFrame:IsShown())
    ''')


def test_every_line_has_nynorsk_and_the_page_follows_the_language():
    lua = make_lua()
    lua.execute('WoWStatusLocale.set("nn")')
    t = lua.eval('WoWStatusLocale.T')
    missing = [line for line in statement_lines(lua) if t(line) == line]
    for text in ('What friends can see', 'What is shared', 'What WoW Status shares'):
        if t(text) == text:
            missing.append(text)
    assert missing == []
    lua.execute('SlashCmdList.WOWSTATUS("privacy")')
    assert lua.eval('WoWStatusPrivacyFrame.title.text') == 'Kva WoW Status deler'
    assert 'Kva som aldri blir sendt' in lua.eval('WoWStatusPrivacyFrame.body.text')
    lua.execute('WoWStatusLocale.set("en"); SlashCmdList.WOWSTATUS("privacy")')
    assert lua.eval('WoWStatusPrivacyFrame.title.text') == 'What WoW Status shares'


def test_the_numbers_it_states_match_the_code():
    # A wrong reassurance is worse than none: the retention figure is the log's cap.
    journal = (ROOT / 'addon/shared/Journal.lua').read_text(encoding='utf-8')
    cap = int(re.search(r'local PREFIX, CAP, AGE, PAGE = "WoWStatusLog",(\d+),', journal).group(1))
    lua = make_lua()
    body = lua.eval('WoWStatusPrivacy.text()')
    unrouted = int(re.search(r'localOnly and private>(\d+)', journal).group(1))
    assert (f'newest {cap:,} of your own entries (at most {unrouted:,} of them sent to no group) '
            f'and {cap:,} received ones') in body
    # One saved file in every edition (plus the game's .bak copy of it).
    for edition in ('vanilla', 'tbc', 'retail', 'forever'):
        toc = (ROOT / f'addon/{edition}/WoWStatus/WoWStatus.toc').read_text(encoding='utf-8')
        saved = [line for line in toc.splitlines() if line.startswith('## SavedVariables')]
        assert saved == ['## SavedVariables: WoWStatusDB'], edition
    assert 'SavedVariables/WoWStatus.lua' in body and 'WoWStatus.lua.bak' in body


def test_the_page_is_reachable_with_a_controller():
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute('unpack = unpack or table.unpack')
    lua.execute(FRAMES)
    lua.execute((ROOT / 'addon/shared/Gamepad.lua').read_text(encoding='utf-8'))
    main_window(lua)
    lua.execute('''
        local methods=getmetatable(CreateFrame("Frame")).__index
        function methods:SetSize(w,h) self.rect[3],self.rect[4]=w,h end
        function methods:SetText(text) self.text=text end
        function methods:CreateFontString() return CreateFrame("FontString",nil,self) end
        function methods:CreateTexture() return CreateFrame("Texture",nil,self) end
        for _, name in ipairs({"SetJustifyH","SetJustifyV","SetWordWrap","SetWidth","SetHeight","SetPoint",
            "SetFrameStrata","EnableMouse","SetMovable","RegisterForDrag","SetAllPoints","SetColorTexture"}) do
            methods[name] = methods[name] or function() end
        end
        function methods:SetScrollChild(child) self.child=child end
        WoWStatusLocale={T=function(text) return text end,F=string.format}
        WoWStatusSafe={number=function(v) return type(v)=="number" and v or nil end,
            call=function(fn, ...) if type(fn)~="function" then return nil end local ok,v=pcall(fn, ...) return ok and v or nil end}
    ''')
    lua.execute((ROOT / 'addon/shared/Privacy.lua').read_text(encoding='utf-8'))
    lua.execute('''
        main:Hide()
        local frame=WoWStatusPrivacy.show()
        frame.rect={100,100,600,480}
        frame.close.rect={446,118,130,28}
        local reached={}
        for _,control in ipairs(WoWStatusGamepad.controls(frame,{frame})) do reached[control]=true end
        assert(reached[frame.close])
        WoWStatusGamepad.update()
        press("PAD2")
        assert(not frame:IsShown())
    ''')


def test_homepage_has_the_section_and_a_menu_link():
    html = (ROOT / 'website/index.html').read_text(encoding='utf-8')
    assert 'id="privacy"' in html and 'href="#privacy"' in html
    section = html[html.index('id="privacy"'):]
    section = section[:section.index('</section>')]
    for phrase in ('What is sent', 'Who receives it', 'What stays on your computer', 'What is never sent',
                   'How to stop', 'What is kept', '/wstatus privacy', 'SavedVariables/WoWStatus.lua'):
        assert phrase in section


def test_homepage_and_addon_say_the_same_thing():
    # One statement in two places: a change to one must reach the other (#152).
    import html as htmlmod
    page = (ROOT / 'website/index.html').read_text(encoding='utf-8')
    section = page[page.index('id="privacy"'):]
    section = section[:section.index('</section>')]
    items = [htmlmod.unescape(re.sub(r'<[^>]+>', '', item)) for item in re.findall(r'<(?:li|h3)>(.*?)</(?:li|h3)>', section)]
    items = [item.replace('’', "'").replace('“', '').replace('”', '') for item in items]
    lua = make_lua()
    assert items == statement_lines(lua)
