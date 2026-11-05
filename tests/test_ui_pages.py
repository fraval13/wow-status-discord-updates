"""Main window pages: cards, level badges, XP bars, character filter and Forever names.

Mocked client APIs: these check behaviour and that every page draws, not the look
in a real client.
"""
import pytest
from test_client_compatibility import client_runtime
from test_roster import pair, pump


def test_friends_xp_arrives_and_shows_on_their_card():
    mira, thora = pair()
    mira.execute('function UnitXP() return 250 end function UnitXPMax() return 1000 end WoWStatusRoster.observe(character())')
    sent = pump(mira, thora)
    assert any(line.startswith('P ') and line.endswith(' 250') for line in sent)
    thora.eval('SlashCmdList.WOWSTATUS')('characters')
    cards = [thora.eval(f'WoWStatusCharactersPage.lines[{i}]') for i in range(1, thora.eval('WoWStatusCharactersPage.count') + 1)]
    mira_card = next(c for c in cards if 'Mira' in c.name.text)
    assert mira_card.xp.progress == 0.25 and mira_card.xp.label.text == 'XP 25%'


def test_clicking_a_character_shows_only_its_activity():
    mira, thora = pair()
    pump(mira, thora)
    thora.execute('''
        local group=next(character().group_ids)
        WoWStatusJournal.received({sender="Mira-TestRealm",nonce="1-1-aaaa",kind="level",level=5,at=time(),group_id=group})
        WoWStatusJournal.received({sender="Bob-TestRealm",nonce="1-2-bbbb",kind="level",level=6,at=time(),group_id=group})
        SlashCmdList.WOWSTATUS("characters")
        local card
        for i=1,WoWStatusCharactersPage.count do
            local c=WoWStatusCharactersPage.lines[i]
            if c.character and c.character.name=="Mira-TestRealm" then card=c end
        end
        card.OnClick(card)
        assert(WoWStatusMainWindow.active()=="activity")
        local list=WoWStatusActivityLog.entriesList
        assert(#list==1 and list[1].sender=="Mira-TestRealm")
        assert(WoWStatusActivityLog.showing.text:find("Mira",1,true) and WoWStatusActivityLog.showAll.visible)
        WoWStatusActivityLog.showAll.OnClick(WoWStatusActivityLog.showAll)
        assert(#WoWStatusActivityLog.entriesList==2)
    ''')


def test_cards_show_the_groups_you_share():
    mira, thora = pair()
    pump(mira, thora)
    rows = [r for g in thora.eval('WoWStatusRoster.groups()').values() for r in g.rows.values()]
    mira_row = next(r for r in rows if r.name == 'Mira-TestRealm')
    assert list(mira_row.groups.values()) == ['dawnwatch']


@pytest.mark.parametrize('edition', ['vanilla', 'forever', 'tbc', 'retail'])
def test_every_page_draws_on_every_edition(edition):
    lua = client_runtime(edition)
    lua.execute('''
        WoWStatusGroups.update("dawnwatch","")
        for _,key in ipairs({"overview","activity","records","characters"}) do
            assert(WoWStatusMainWindow.show(key))
        end
        assert(#WoWStatusRecordsPage.rows==#WoWStatusFirsts.medals())
        -- Nobody has died yet: that card is grey. (Level records can already be held:
        -- the simulated characters reached those levels before WoW Status.)
        local death
        for _, row in ipairs(WoWStatusRecordsPage.rows) do
            if row.text:find("to die", 1, true) then death = row end
        end
        assert(death.icon.path and death.icon.dimmed)
        assert(WoWStatusOverviewPage.you.badge.text.text~=nil)
        assert(WoWStatusOverviewPage.group.count.text:find("online",1,true))
        assert(WoWStatusOverviewPage.problem==nil, tostring(WoWStatusOverviewPage.problem))
    ''')


def test_overview_lists_everyone_online_and_fits_the_summary():
    from test_journal import actor
    lua = actor('Thora')
    lua.execute('''
        __peers={"Thora-TestRealm","Ann-TestRealm","Bob-TestRealm","Cid-TestRealm","Dee-TestRealm","Eve-TestRealm","Fay-TestRealm"}
        getmetatable(CreateFrame("Frame")).__index.SetHeight = function(self, h) self.height = h end
        WoWStatusDB.overview = {since = time() - 3600}
        local group = next(character().group_ids)
        WoWStatusJournal.received({sender="Ann-TestRealm",nonce="1-1-aaaa",kind="level",level=5,at=time(),group_id=group})
        WoWStatusMainWindow.show("overview")
        local page = WoWStatusOverviewPage
        local names = page.group.names.text
        for _, n in ipairs({"Ann","Bob","Cid","Dee","Eve","Fay"}) do assert(names:find(n, 1, true), n) end
        assert(not names:find("more", 1, true))
        -- Two summary lines: a compact box, not the full height.
        assert(#page.rows == 2 and page.since.height == 98, page.since.height)
        for i = 2, 30 do
            WoWStatusJournal.received({sender="Bob-TestRealm",nonce="2-"..i.."-bbbb",kind="death",text="Died",at=time(),group_id=group})
            WoWStatusJournal.received({sender="Cid"..i.."-TestRealm",nonce="3-"..i.."-cccc",kind="death",text="Died",at=time(),group_id=group})
        end
        WoWStatusMainWindow.show("overview")
        assert(page.since.height == 232)
    ''')
