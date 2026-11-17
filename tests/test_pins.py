"""Pinned friends (#170): a star lifts a player or character to the top, locally."""
from pathlib import Path

from test_addon import lupa
from test_gamepad import FRAMES
from test_online_filter import cards, headings, online_only, page
from test_roster import pair, pump


def add_player(thora, line, pid, player_name, character):
    """Another player, announced through a copy of Mira's list line, with one offline character."""
    words = line.split(' ')
    words[2], words[3], words[4] = pid, player_name, character
    thora.eval('WoWStatusRoster.receive')(' '.join(words), 'Mira-TestRealm', 'WHISPER')


def crew():
    """Thora sees Frank (Mira, online), Bob (Bobby, offline) and Cid (Cidra, offline)."""
    mira, thora = pair()
    line = next(line for line in pump(mira, thora) if line.startswith('C '))
    add_player(thora, line, 'b0b0b0b0b0b0b0b0', 'Bob', 'Bobby-TestRealm')
    add_player(thora, line, 'c1dc1dc1dc1dc1dc', 'Cid', 'Cidra-TestRealm')
    return mira, thora, line


def players(lua):
    """Friend headings in page order, by player name."""
    order = []
    for text in headings(lua):
        for name in ('Frank', 'Bob', 'Cid'):
            if text.startswith(name + ' (') and name not in order:
                order.append(name)
    return order


def pin(lua, kind, name, on=True):
    return lua.eval('WoWStatusRoster.setPinned')(kind, name, on)


def star_of(lua, player):
    heads = page(lua).headers
    for i in range(1, len(heads) + 1):
        if heads[i].IsShown(heads[i]) and heads[i].text.text.startswith(player + ' ('):
            return heads[i].star
    return None


def test_pinned_players_lead_in_the_order_they_were_pinned():
    _, thora, _ = crew()
    page(thora)
    unpinned = players(thora)
    assert sorted(unpinned) == ['Bob', 'Cid', 'Frank']
    assert pin(thora, 'player', 'Cid') and pin(thora, 'player', 'Bob')
    assert players(thora)[:2] == ['Cid', 'Bob']
    pin(thora, 'player', 'Cid', False)
    assert players(thora)[0] == 'Bob'


def test_pinned_and_online_come_before_pinned_and_offline():
    _, thora, _ = crew()
    pin(thora, 'player', 'Cid')
    pin(thora, 'player', 'Frank')   # pinned later, but Mira is online
    assert players(thora) == ['Frank', 'Cid', 'Bob']


def test_a_pinned_character_leads_its_player_and_lifts_the_player():
    _, thora, line = crew()
    # Frank's second character, offline, under Mira's own player ID.
    words = line.split(' ')
    add_player(thora, line, words[2], 'Frank', 'Ghost-TestRealm')
    pin(thora, 'character', 'Bobby-TestRealm')
    assert players(thora)[0] == 'Bob'
    pin(thora, 'character', 'Ghost-TestRealm')
    sections = thora.eval('WoWStatusRoster.sections()')
    entries = [e for s in sections.values() if s.key not in ('you',) for e in s.entries.values()]
    frank = next(e for e in entries if e.name == 'Frank')
    assert frank.rows[1].name == 'Ghost-TestRealm'   # pinned card first, though offline
    # Both pinned; Frank has a character online, so Frank leads.
    assert [e.name for e in entries][:2] == ['Frank', 'Bob']


def test_pinning_changes_order_only_never_what_is_shown():
    _, thora, _ = crew()
    before = cards(thora)
    heads_before = sorted(headings(thora))
    pin(thora, 'player', 'Bob')
    pin(thora, 'character', 'Cidra-TestRealm')
    assert cards(thora) == before
    assert sorted(headings(thora)) == heads_before
    # With "Online only" the offline pinned players stay hidden: pins never show anyone.
    online_only(thora, True)
    assert 'Bobby-TestRealm' not in cards(thora) and 'Cidra-TestRealm' not in cards(thora)
    assert players(thora) == ['Frank']


def test_pins_are_saved_for_the_account_and_nothing_is_sent():
    mira, thora, _ = crew()
    sent = thora.eval('#__sent')
    pin(thora, 'player', 'Bob')
    pin(thora, 'character', 'Cidra-TestRealm')
    cidra = 'c:' + thora.eval('WoWStatusRoster.key("Cidra-TestRealm")')
    assert dict(thora.eval('WoWStatusDB.roster.pins').items()) == {'p:bob': 1, cidra: 2}
    # Saved in the account-wide table, not a character's settings.
    assert thora.eval('character().roster_pins') is None
    page(thora)
    # Pinning itself queued nothing; later ticks carry no pin.
    assert thora.eval('#__sent') == sent
    assert [line for line in pump(thora, mira) if 'pin' in line.lower()] == []
    # After /reload the saved table is read again as it was.
    assert thora.eval('WoWStatusRoster.pinned')('player', 'Bob') == 1
    assert thora.eval('WoWStatusRoster.pinned')('player', 'bob') == 1   # player names ignore case


def test_the_star_is_a_button_with_a_click_and_a_tooltip():
    _, thora, _ = crew()
    page(thora)
    star = star_of(thora, 'Bob')
    assert star is not None and star.kind == 'Button'
    assert star.OnClick is not None and star.OnEnter is not None
    star.OnClick(star)
    assert thora.eval('WoWStatusRoster.pinned')('player', 'Bob') is not None
    assert players(thora)[0] == 'Bob'
    star = star_of(thora, 'Bob')
    assert star.icon.alpha == 1
    thora.execute('WoWStatusRoster.STAR_REPEAT = 0')
    star.OnClick(star)
    assert thora.eval('WoWStatusRoster.pinned')('player', 'Bob') is None
    # Every friend card has its own star; your own cards and the "Not announced" heading do not.
    lines = page(thora).lines
    for i in range(1, len(lines) + 1):
        card = lines[i]
        if card.IsShown(card) and card.character:
            own = card.character.name == 'Thora-TestRealm'
            assert card.star.IsShown(card.star) is not own


def test_a_full_pin_list_lets_go_of_its_oldest_pin():
    _, thora, _ = crew()
    thora.execute('WoWStatusRoster.PIN_MAX = 2')
    assert pin(thora, 'player', 'Gone')   # someone no longer listed: no star to unpin them
    assert pin(thora, 'player', 'Bob')
    assert pin(thora, 'player', 'Cid')
    pinned = thora.eval('WoWStatusRoster.pinned')
    assert pinned('player', 'Gone') is None
    assert pinned('player', 'Bob') is not None and pinned('player', 'Cid') is not None


def test_a_quick_second_click_does_not_pin_whoever_moved_under_the_star():
    _, thora, _ = crew()
    page(thora)
    thora.execute('__mono = 500')
    star = star_of(thora, 'Bob')
    star.OnClick(star)
    star.OnClick(star)   # the same button, a moment later
    pinned = thora.eval('WoWStatusRoster.pinned')
    assert pinned('player', 'Bob') is not None
    assert pinned('player', 'Cid') is None and pinned('player', 'Frank') is None


def test_merged_headings_have_no_star_and_are_not_lifted():
    _, thora, _ = crew()
    thora.execute('''
        local group=next(character().group_ids)
        WoWStatusJournal.received({sender="Zed-TestRealm",nonce="1-1-zzzz",kind="level",level=5,at=time(),group_id=group})
    ''')
    page(thora)
    assert star_of(thora, 'Not announced') is None or not star_of(thora, 'Not announced').IsShown(star_of(thora, 'Not announced'))
    pin(thora, 'character', 'Zed-TestRealm')
    sections = thora.eval('WoWStatusRoster.sections()')
    names = [e.name for sec in sections.values() if sec.key != 'you' for e in sec.entries.values()]
    assert names.index('Not announced') > names.index('Bob')


def test_leaderboard_puts_pinned_players_first_only_when_chosen():
    _, thora, _ = crew()
    thora.execute('''
        for _, p in pairs(WoWStatusDB.roster.players) do
            for _, c in pairs(p.characters) do
                c.level = ({["Bobby-TestRealm"]=40, ["Cidra-TestRealm"]=30})[c.name] or 50
            end
        end
    ''')
    pin(thora, 'player', 'Cid')
    group = next(sec.key for sec in thora.eval('WoWStatusRoster.sections()').values() if sec.key != 'you')
    board = thora.eval('WoWStatusRoster.leaderboard')(group)
    pinned = [row.name for row in board.values() if row.pin is not None]
    assert pinned == ['Cidra-TestRealm']
    thora.eval('SlashCmdList.WOWSTATUS')('leaderboard')
    lb = thora.eval('WoWStatusLeaderboardPage')
    names = [lb.board[i].name.text for i in range(1, len(lb.board) + 1) if lb.board[i].IsShown(lb.board[i])]
    assert 'Cidra' not in names[0]
    box = lb.pinnedFirst
    assert box.kind == 'CheckButton' and box.OnClick is not None
    box.SetChecked(box, True)
    box.OnClick(box)
    assert thora.eval('WoWStatusDB.leaderboard.pinned_first') is True
    names_after = [lb.board[i].name.text for i in range(1, len(lb.board) + 1) if lb.board[i].IsShown(lb.board[i])]
    assert 'Cidra' in names_after[0]
    assert sorted(names_after) == sorted(names)   # nobody is left out


def test_overview_lists_pinned_friends_first():
    _, thora, _ = crew()
    thora.execute('''
        local group = next(character().group_ids)
        WoWStatusDB.overview = {since = time() - 100}
        WoWStatusJournal.received({sender="Cidra-TestRealm", nonce="1-1-aaaa", kind="level", level=5, at=time() - 50, group_id=group})
        WoWStatusJournal.received({sender="Bobby-TestRealm", nonce="1-2-aaaa", kind="level", level=6, at=time() - 10, group_id=group})
    ''')
    summary = thora.eval('WoWStatusOverview.summary(WoWStatusJournal.entries(), WoWStatusDB.overview.since)')
    assert [p.player for p in summary.values()][:2] == ['Bobby (Bob)', 'Cidra (Cid)']
    pin(thora, 'player', 'Cid')
    summary = thora.eval('WoWStatusOverview.summary(WoWStatusJournal.entries(), WoWStatusDB.overview.since)')
    assert [p.player for p in summary.values()][:2] == ['Cidra (Cid)', 'Bobby (Bob)']


def test_pin_texts_are_translated():
    _, thora, _ = crew()
    thora.execute('WoWStatusLocale.set("nn")')
    t = thora.eval('WoWStatusLocale.T')
    for text in ('Pinned first', 'Unpin', 'Pin this player to the top', 'Pin this character to the top'):
        assert t(text) != text


def test_the_stars_are_reachable_with_a_controller():
    root = Path(__file__).parents[1]
    runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
    runtime.execute('unpack = unpack or table.unpack')
    runtime.execute(FRAMES)
    runtime.execute((root / 'addon/shared/Gamepad.lua').read_text(encoding='utf-8'))
    runtime.execute('''
        main = window("WoWStatusMainFrame", 100, 100, 760, 560)
        WoWStatusMainWindow = {pages=function() return {"characters"} end, active=function() return "characters" end,
            show=function() main:Show() end, hide=function() main:Hide() end, back=function() return false end,
            refresh=function() end}
        local methods=getmetatable(CreateFrame("Frame")).__index
        function methods:SetSize(w,h) if self.rect then self.rect[3],self.rect[4]=w,h end end
        function methods:SetText(text) self.text=text end
        function methods:SetTexture(path) self.texture=path end
        function methods:CreateFontString() return CreateFrame("FontString",nil,self) end
        function methods:SetJustifyH() end
        function methods:SetScrollChild(child) self.child=child end
        function methods:SetShown(value) self.visible=value end
        function methods:SetAlpha(value) self.alpha=value end
        function methods:SetVertexColor() end
        function methods:SetAllPoints() end
        local function bar(parent) local b=CreateFrame("Frame",nil,parent); b.SetProgress=function() end; return b end
        WoWStatusLocale={T=function(text) return text end,F=string.format,lang=function() return "en" end}
        WoWStatusSafe={number=function(v) return type(v)=="number" and v or nil end}
        WoWStatusPopups={}
        WoWStatusAdapter={}
        WoWStatusUI={MUTED_CODE="|cff9d9d9d", text=function(parent) return CreateFrame("FontString",nil,parent) end,
            header=function(parent) return CreateFrame("FontString",nil,parent) end,
            box=function(parent,w,h,kind) return CreateFrame(kind or "Frame",nil,parent) end,
            levelBadge=function(parent) local b=CreateFrame("Frame",nil,parent); b.SetLevel=function() end; return b end,
            xpBar=bar, tint=function() end, money=function() return "" end,
            call=function() return false end, classColour=function() end}
        WoWStatusMainWindow.register=function(key,title,build) __build=build end
    ''')
    runtime.execute((root / 'addon/shared/Roster.lua').read_text(encoding='utf-8'))
    runtime.execute('''
        local R=WoWStatusRoster
        R.collapsed=function() return false end
        R.onlineOnly=function() return false end
        R.groups=function() return {} end
        R.together=function() return {level=20, range=3, online=0, inRange=0, rows={}} end
        R.portrait=function() end
        R.professionsOf=function() return {} end
        R.isUnreachable=function() return false end
        R.itemLevel=function() end
        R.pinned=function() return nil end
        R.sections=function() return {{key="g", title="Group", characters=1, online=1,
            entries={{name="Frank", pinnable=true, rows={{name="Mira-Realm", status="online", level=20}}}}}} end
        local page=__build(main); page.visible=true; page.list.visible=true
        R.render()
        local head, card = page.headers[1], page.lines[1]
        head.rect={120,400,680,26}; head.star.rect={780,400,18,18}
        card.rect={120,300,680,114}; card.star.rect={780,300,18,18}
        local reached={}
        for _,control in ipairs(WoWStatusGamepad.controls(main,{main})) do reached[control]=true end
        assert(reached[head.star], "heading star")
        assert(reached[card.star], "card star")
        assert(head.star.kind=="Button" and head.star.scripts.OnClick and head.star.scripts.OnEnter)
    ''')
