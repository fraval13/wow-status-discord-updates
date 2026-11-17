"""'Where we are' (#168): online friends grouped by the zone they last reported."""
from pathlib import Path

from test_addon import lupa
from test_gamepad import FRAMES
from test_play_together import friend, online, setup

ROOT = Path(__file__).parents[1]


def report(lua, sender, zone, ago=0, nonce=None, kind='zone'):
    """A friend's log entry, `ago` seconds old: a first visit, or a death with its zone."""
    nonce = nonce or f'n{abs(hash((sender, zone, ago, kind))) % 10**8}'
    text = f'Entered {zone}' if kind == 'zone' else 'Died'
    lua.execute(f'''WoWStatusJournal.received({{sender="{sender}", nonce="{nonce}", kind="{kind}", text="{text}",
        at=WoWStatusSafe.now() - {ago}, group_id=next(character().group_ids)}})''')
    if kind == 'death':
        lua.execute(f'WoWStatusJournal.setDetails(WoWStatusJournal.eventID("{sender}", "{nonce}"), "{zone}", nil)')


def where(lua):
    data = lua.eval('WoWStatusRoster.whereWeAre()')
    return data, [(z.zone, [m.name for m in z.members.values()]) for z in data.zones.values()]


def friends(*names_levels):
    _, thora, words = setup()
    for name in names_levels:
        friend(thora, words, name, 20)
    online(thora, *names_levels)
    return thora


def test_one_row_per_zone_your_zone_first_then_the_newest():
    thora = friends('Mira-TestRealm', 'Bo-TestRealm', 'Cy-TestRealm', 'Di-TestRealm')
    report(thora, 'Mira-TestRealm', 'Duskwood', ago=300)
    report(thora, 'Bo-TestRealm', 'Duskwood', ago=60)
    report(thora, 'Cy-TestRealm', 'Westfall', ago=30)
    report(thora, 'Di-TestRealm', 'Dun Morogh', ago=600)   # the harness puts Thora in Dun Morogh
    data, rows = where(thora)
    assert data.here == 'Dun Morogh' and data.people == 4 and data.count == 3
    assert rows == [('Dun Morogh', ['Di-TestRealm']), ('Westfall', ['Cy-TestRealm']),
                    ('Duskwood', ['Bo-TestRealm', 'Mira-TestRealm'])]
    assert data.zones[1].here is True and data.zones[2].here is False
    duskwood = data.zones[3]
    assert [m.age for m in duskwood.members.values()] == [60, 300]


def test_reports_older_than_fifteen_minutes_are_left_out_not_shown_as_current():
    thora = friends('Mira-TestRealm', 'Bo-TestRealm')
    report(thora, 'Mira-TestRealm', 'Duskwood', ago=15 * 60)
    report(thora, 'Bo-TestRealm', 'Westfall', ago=15 * 60 + 1)
    assert where(thora)[1] == [('Duskwood', ['Mira-TestRealm'])]
    # Only the newest report counts: an older, fresher-looking zone is not used instead.
    report(thora, 'Mira-TestRealm', 'Elwynn Forest', ago=16 * 60, nonce='old')
    assert where(thora)[1] == [('Duskwood', ['Mira-TestRealm'])]
    thora.execute('function time() return __now + 120 end')
    assert where(thora)[1] == []


def test_a_death_reports_where_it_happened():
    thora = friends('Mira-TestRealm')
    report(thora, 'Mira-TestRealm', 'Duskwood', ago=500)
    report(thora, 'Mira-TestRealm', 'Darkshire Cemetery', ago=20, kind='death')
    assert where(thora)[1] == [('Darkshire Cemetery', ['Mira-TestRealm'])]


def test_only_online_listed_characters_the_viewer_may_see():
    _, thora, words = setup()
    group, pid = words[1], words[2]
    friend(thora, words, 'Away-TestRealm', 20)
    report(thora, 'Mira-TestRealm', 'Duskwood')
    report(thora, 'Away-TestRealm', 'Duskwood')
    # A log sender who never shared a list.
    report(thora, 'Eldrin-TestRealm', 'Duskwood')
    online(thora, 'Mira-TestRealm', 'Eldrin-TestRealm')
    assert where(thora)[1] == [('Duskwood', ['Mira-TestRealm'])]
    # Mira hides the character from the list: it leaves the view too.
    thora.eval('WoWStatusRoster.receive')(f'Z {group} {pid} Mira-TestRealm 1 1', 'Mira-TestRealm', 'WHISPER')
    assert where(thora)[1] == []


def test_a_friend_who_shares_no_zone_never_appears():
    # Without zone sharing a friend's client sends no first visits and no death
    # zone, so nothing reaches this log; a death without a zone stays out.
    thora = friends('Mira-TestRealm')
    report(thora, 'Mira-TestRealm', 'Duskwood', ago=10, nonce='d1', kind='level')
    thora.execute('''WoWStatusJournal.received({sender="Mira-TestRealm", nonce="d2", kind="death", text="Died",
        at=WoWStatusSafe.now(), group_id=next(character().group_ids)})''')
    assert where(thora)[1] == []


def test_the_section_shows_zones_names_and_ages_and_folds():
    thora = friends('Mira-TestRealm', 'Bo-TestRealm')
    report(thora, 'Mira-TestRealm', 'Dun Morogh', ago=30)
    report(thora, 'Bo-TestRealm', 'Duskwood', ago=7 * 60 + 10)
    thora.eval('WoWStatusMainWindow.show')('characters')
    page = thora.eval('WoWStatusCharactersPage')
    assert page.whereHead.text.text == 'Where we are   |cff9d9d9d2 friends, 2 zones|r'
    assert page.whereNote.text == 'Your zone first, then the newest report.'
    assert page.where[1].zone.text == 'Dun Morogh |cff40ff40(your zone)|r'
    assert page.where[1].members.text == '|cffc79c6eMira|r |cff9d9d9d(just now)|r'
    assert page.where[2].zone.text == 'Duskwood'
    assert page.where[2].members.text.endswith('|cff9d9d9d(7 min ago)|r')
    # It sits between "Play together now" and the character sections.
    assert page.togetherHead.text.text.startswith('Play together now')
    assert page.sections[1].text.text == 'Your characters'
    head = page.whereHead
    head.OnClick(head)
    assert thora.eval('WoWStatusRoster.collapsed("where")') is True
    assert not page.where[1].IsShown(page.where[1]) and not page.whereNote.IsShown(page.whereNote)
    head.OnClick(head)
    assert page.where[2].IsShown(page.where[2])


def test_an_empty_view_says_why():
    thora = friends('Mira-TestRealm')
    thora.eval('WoWStatusMainWindow.show')('characters')
    page = thora.eval('WoWStatusCharactersPage')
    assert page.whereNote.text == 'No online friend has reported a zone in the last 15 minutes.'
    assert not page.where or not any(page.where[i].IsShown(page.where[i]) for i in range(1, len(page.where) + 1))


def test_a_crowded_zone_names_four_and_counts_the_rest():
    names = [f'F{chr(97 + i)}-TestRealm' for i in range(8)]
    thora = friends(*names)
    for i, name in enumerate(names):
        report(thora, name, 'Ironforge', ago=i)
    thora.eval('WoWStatusMainWindow.show')('characters')
    text = thora.eval('WoWStatusCharactersPage.where[1].members.text')
    assert text.count('(') == 4 and text.endswith('+4 more')


def test_ages_move_on_and_old_reports_drop_while_the_page_is_open():
    thora = friends('Mira-TestRealm')
    report(thora, 'Mira-TestRealm', 'Duskwood', ago=14 * 60)
    thora.eval('WoWStatusMainWindow.show')('characters')
    page = thora.eval('WoWStatusCharactersPage')
    assert page.where[1].IsShown(page.where[1])
    thora.execute('function time() return __now + 90 end')
    for step in range(0, 30, 5):
        thora.execute(f'__mono = 3000 + {step}')
        thora.eval('WoWStatusRoster.tick')()
    assert not page.where[1].IsShown(page.where[1])
    assert page.whereHead.text.text.endswith('0 friends, 0 zones|r')


def test_nothing_is_sent_for_it():
    thora = friends('Mira-TestRealm')
    report(thora, 'Mira-TestRealm', 'Duskwood')
    before = thora.eval('#__sent')
    thora.eval('WoWStatusMainWindow.show')('characters')
    thora.eval('WoWStatusRoster.whereWeAre')()
    assert thora.eval('#__sent') == before


def test_nynorsk_labels():
    thora = friends('Mira-TestRealm')
    report(thora, 'Mira-TestRealm', 'Dun Morogh', ago=125)
    thora.execute('WoWStatusLocale.set("nn")')
    thora.eval('WoWStatusMainWindow.show')('characters')
    page = thora.eval('WoWStatusCharactersPage')
    assert page.whereHead.text.text == 'Kvar vi er   |cff9d9d9d1 ven, 1 område|r'
    assert page.where[1].zone.text == 'Dun Morogh |cff40ff40(området ditt)|r'
    assert page.where[1].members.text.endswith('(for 2 min sidan)|r')


def test_the_heading_is_reachable_with_a_controller():
    runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
    runtime.execute('unpack = unpack or table.unpack')
    runtime.execute(FRAMES)
    runtime.execute((ROOT / 'addon/shared/Gamepad.lua').read_text(encoding='utf-8'))
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
        function methods:SetColorTexture() end
        WoWStatusLocale={T=function(text) return text end,F=string.format}
        WoWStatusSafe={now=function() return 0 end}
        WoWStatusJournal={entries=function() return {} end, details=function() end, zoneRevision=0}
        WoWStatusPopups={}
        WoWStatusUI={text=function(parent) return CreateFrame("FontString",nil,parent) end,
            call=function() return false end, classColour=function() end, MUTED_CODE="|cff9d9d9d"}
        WoWStatusMainWindow.register=function(key,title,build) __build=build end
    ''')
    runtime.execute((ROOT / 'addon/shared/Roster.lua').read_text(encoding='utf-8'))
    runtime.execute('''
        local R=WoWStatusRoster
        R.collapsed=function() return false end
        R.onlineOnly=function() return false end
        R.groups=function() return {} end
        R.sections=function() return {} end
        R.together=function() return {range=3, online=0, inRange=0, rows={}} end
        R.whereWeAre=function() return {people=1, count=1, zones={{zone="Duskwood", at=0, here=false,
            members={{name="Mira-Realm", class="WARRIOR", at=0, age=0}}}}} end
        local page=__build(main); page.visible=true; page.list.visible=true
        R.render()
        local head=page.whereHead
        head.rect={124,480,680,26}
        local reached={}
        for _,control in ipairs(WoWStatusGamepad.controls(main,{main})) do reached[control]=true end
        assert(reached[head], "heading not reachable")
        assert(head.kind=="Button" and head.scripts.OnClick)
    ''')


def test_more_zones_than_rows_say_how_many_are_left_out():
    names = [f'F{chr(97 + i)}-TestRealm' for i in range(10)]
    thora = friends(*names)
    for i, name in enumerate(names):
        report(thora, name, f'Zone {i}', ago=i)
    data, rows = where(thora)
    assert data.count == 10 and data.more == 2 and len(rows) == 8
    thora.eval('WoWStatusMainWindow.show')('characters')
    page = thora.eval('WoWStatusCharactersPage')
    assert page.where[9].zone.text == '|cff9d9d9d+2 more zones|r' and page.where[9].IsShown(page.where[9])


def test_an_unread_zone_is_no_place_and_a_death_without_a_zone_moves_nobody():
    thora = friends('Mira-TestRealm', 'Bo-TestRealm')
    report(thora, 'Mira-TestRealm', 'a new zone', ago=10)
    report(thora, 'Mira-TestRealm', 'Duskwood', ago=300, nonce='older')
    # A death without its zone says nothing about where they are: the first visit stands.
    report(thora, 'Bo-TestRealm', 'Westfall', ago=300, nonce='b1')
    thora.execute('''WoWStatusJournal.received({sender="Bo-TestRealm", nonce="b2", kind="death", text="Died",
        at=WoWStatusSafe.now() - 5, group_id=next(character().group_ids)})''')
    assert where(thora)[1] == [('Westfall', ['Bo-TestRealm'])]


def test_a_stamp_far_in_the_future_is_left_out():
    thora = friends('Mira-TestRealm', 'Bo-TestRealm')
    report(thora, 'Mira-TestRealm', 'Duskwood', ago=-1800)
    report(thora, 'Bo-TestRealm', 'Westfall', ago=-120)
    assert where(thora)[1] == [('Westfall', ['Bo-TestRealm'])]


def test_redraws_only_when_an_age_changes_or_a_report_arrives():
    thora = friends('Mira-TestRealm', 'Bo-TestRealm')
    thora.eval('WoWStatusMainWindow.show')('characters')
    thora.execute('''
        __renders = 0
        local render = WoWStatusRoster.render
        WoWStatusRoster.render = function(...) __renders = __renders + 1; return render(...) end
    ''')

    def ticks(start, seconds=0):
        if seconds:
            thora.execute(f'function time() return __now + {seconds} end')
        for step in range(0, 30, 5):
            thora.execute(f'__mono = {start} + {step}')
            thora.eval('WoWStatusRoster.tick')()
    ticks(4000, 600)
    assert thora.eval('__renders') == 0          # nothing to show: no minute redraws
    report(thora, 'Mira-TestRealm', 'Duskwood', ago=30)
    ticks(4100, 600)
    assert thora.eval('__renders') == 1
    assert thora.eval('WoWStatusCharactersPage.where[1].members.text').endswith('(just now)|r')
    ticks(4200, 625)                             # still under a minute old
    assert thora.eval('__renders') == 1
    ticks(4300, 631)
    assert thora.eval('__renders') == 2
    assert thora.eval('WoWStatusCharactersPage.where[1].members.text').endswith('(1 min ago)|r')


def test_late_death_details_and_older_reports_redraw_and_a_folded_heading_stays_current():
    thora = friends('Mira-TestRealm', 'Bo-TestRealm')
    thora.eval('WoWStatusMainWindow.show')('characters')
    page = thora.eval('WoWStatusCharactersPage')
    thora.execute('''WoWStatusJournal.received({sender="Mira-TestRealm", nonce="m1", kind="death", text="Died",
        at=WoWStatusSafe.now() - 20, group_id=next(character().group_ids)})''')
    report(thora, 'Bo-TestRealm', 'x', ago=0, nonce='b9', kind='level')  # a newer, unrelated entry
    thora.execute('WoWStatusJournal.setDetails(WoWStatusJournal.eventID("Mira-TestRealm", "m1"), "Duskwood", nil)')

    def ticks(start):
        for step in range(0, 30, 5):
            thora.execute(f'__mono = {start} + {step}')
            thora.eval('WoWStatusRoster.tick')()
    ticks(5000)
    assert page.where[1].zone.text == 'Duskwood'
    head = page.whereHead
    head.OnClick(head)
    thora.execute('function time() return __now + 900 end')
    ticks(5100)
    assert head.text.text.endswith('0 friends, 0 zones|r')


def test_play_together_uses_the_same_fifteen_minutes():
    _, thora, words = setup()
    friend(thora, words, 'Mira-TestRealm', 20)
    online(thora, 'Mira-TestRealm')
    report(thora, 'Mira-TestRealm', 'Duskwood', ago=16 * 60)
    assert thora.eval('WoWStatusRoster.together().rows[1].zone') is None
    report(thora, 'Mira-TestRealm', 'Westfall', ago=60, nonce='new')
    assert thora.eval('WoWStatusRoster.together().rows[1].zone') == 'Westfall'


def test_a_relays_catch_up_claim_places_nobody():
    thora = friends('Mira-TestRealm')
    report(thora, 'Mira-TestRealm', 'Duskwood', ago=300)
    thora.execute('''table.insert(WoWStatusDB.journal.entries, 1, {id="relay-claim", sender="Mira-TestRealm",
        kind="zone", text="Entered Stormwind City", at=WoWStatusSafe.now() - 5, groups={}, origin="catchup",
        via="Bo-TestRealm"})''')
    assert where(thora)[1] == [('Duskwood', ['Mira-TestRealm'])]


def test_an_older_clients_pc_clock_stamp_still_counts():
    thora = friends('Mira-TestRealm')
    # Realm time runs 20 minutes ahead of this PC; the friend stamped by a PC clock.
    thora.execute('function GetServerTime() return time() + 1200 end')
    thora.execute('''WoWStatusJournal.received({sender="Mira-TestRealm", nonce="pc1", kind="zone",
        text="Entered Duskwood", at=time() - 120, group_id=next(character().group_ids)})''')
    data, rows = where(thora)
    assert rows == [('Duskwood', ['Mira-TestRealm'])]
    assert data.zones[1].members[1].age == 120


def test_removing_log_entries_redraws_the_view():
    thora = friends('Mira-TestRealm')
    before = thora.eval('WoWStatusJournal.zoneRevision')
    thora.eval('WoWStatusJournal.privacyChanged')()
    thora.eval('WoWStatusJournal.groupsChanged')()
    assert thora.eval('WoWStatusJournal.zoneRevision') == before + 2


def test_zone_text_is_read_the_same_way_everywhere():
    thora = friends('Mira-TestRealm')
    zone_of = thora.eval('WoWStatusJournal.zoneOf')
    entry = thora.eval('function(text) return {kind="zone", text=text} end')
    assert zone_of(entry('Entered Duskwood ')) == 'Duskwood'
    assert zone_of(entry('Entered a new zone')) is None
    assert zone_of(entry('Reached level 5!')) is None
