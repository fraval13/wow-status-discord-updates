"""Hardcore realms (#163): a permanent death gets no roast, no count and no record."""
from test_addon import STUBS, make_lua
from test_journal import actor, clock, deliver_popup
from test_reactions import sent_whispers
from test_week import plain, with_entries

HARDCORE = 'C_GameRules = {IsHardcoreActive = function() return true end}'


def test_hardcore_needs_positive_evidence_from_the_client():
    lua = make_lua()
    lua.execute('''
        local P = WoWStatusProgress
        C_GameRules = nil; assert(P.hardcore() == false)
        C_GameRules = {}; assert(P.hardcore() == false)
        for _, answer in ipairs({false, 1, "true", 0}) do
            C_GameRules = {IsHardcoreActive = function() return answer end}
            assert(P.hardcore() == false, tostring(answer))
        end
        C_GameRules = {IsHardcoreActive = function() return nil end}; assert(P.hardcore() == false)
        C_GameRules = {IsHardcoreActive = function() error("restricted") end}; assert(P.hardcore() == false)
        C_GameRules = {IsHardcoreActive = function() return true end}; assert(P.hardcore() == true)
    ''')


def test_a_normal_death_is_unchanged():
    lua = make_lua()
    lua.eval('WoWStatusGroups.update')('dawnwatch', '')
    lua.eval('fire')('PLAYER_DEAD')
    assert lua.eval('character().snapshot.deaths') == 1
    assert lua.eval('WoWStatusJournal.entries()[1].text') == 'Total deaths: 1'
    hexed = 'Total deaths: 1'.encode().hex()
    assert lua.eval('__sent[1].text').endswith(' ' + hexed)


def test_hardcore_death_is_shared_with_its_own_text_and_not_counted():
    lua = make_lua()
    lua.eval('WoWStatusGroups.update')('dawnwatch', '')
    lua.execute(HARDCORE)
    lua.eval('fire')('PLAYER_DEAD')
    assert lua.eval('character().snapshot.deaths') == 0
    assert lua.eval('WoWStatusProgress.totalDeaths(character())') == 0
    assert lua.eval('WoWStatusJournal.entries()[1].text') == 'Died in Hardcore'
    packet = lua.eval('__sent[1].text')
    assert 'WSTATUS3 classic-era death' in packet
    assert packet.endswith(' ' + 'Died in Hardcore'.encode().hex())
    # The same death is not announced twice while the character stays dead.
    lua.eval('fire')('PLAYER_DEAD')
    assert lua.eval('#__sent') == 1
    # The death sharing switch still decides whether anything is recorded at all.
    lua.execute('character().death_latched = false; character().settings.collection.death = false')
    lua.eval('fire')('PLAYER_DEAD')
    assert lua.eval('#__sent') == 1


def hardcore_toast(language, reaction_voice='classic'):
    own, friend = actor('Mira'), actor('Thora')
    friend.execute('WoWStatusPopups.CLICK_GUARD = 0')
    friend.execute(f'WoWStatusLocale.set("{language}"); WoWStatusPersonalities.setReaction("{reaction_voice}")')
    clock(own, 10)
    clock(friend, 10)
    own.execute(HARDCORE)
    own.eval('fire')('PLAYER_DEAD')
    deliver_popup(own, friend)
    friend.eval('WoWStatusPopups.tick')()
    return friend


def test_friends_see_the_hardcore_death_without_caption_or_teasing():
    friend = hardcore_toast('en')
    friend.execute('''
        local toast = WoWStatusLevelPopup
        assert(toast:IsShown() and toast.item.kind == "death")
        assert(toast.message:GetText():find("Died in Hardcore", 1, true), toast.message:GetText())
        assert(not toast.detail:IsShown())
        assert(table.concat(WoWStatusPopups.reactions(toast.item), "|") == "F")
        assert(not toast.reactions[2] or not toast.reactions[2]:IsShown())
        toast.reactions[1].OnClick(toast.reactions[1])
        local e = WoWStatusJournal.entries()[1]
        assert(e.text == "Died in Hardcore" and WoWStatusFlavour.text(e) == "")
    ''')
    assert sent_whispers(friend) == [('F', 'Mira-TestRealm')]


def test_paying_respects_whispers_the_plain_line_in_any_voice_and_language():
    for language, expected in (('en', 'F'), ('nn', 'Eg tek av meg hjelmen og bøyer hovudet i sorg.')):
        for voice in ('classic', 'random', 'goblin'):
            friend = hardcore_toast(language, voice)
            friend.execute('local t = WoWStatusLevelPopup; t.reactions[1].OnClick(t.reactions[1])')
            assert sent_whispers(friend) == [(expected, 'Mira-TestRealm')], (language, voice)


def test_no_death_caption_can_be_drawn_for_a_hardcore_death():
    lua = make_lua()
    lua.execute('''
        local P = WoWStatusPersonalities
        local voices = P.voices()
        table.insert(voices, "random")
        function UnitName(unit) if unit == "party1" then return "Eldrin", "TestRealm" end end
        function UnitClass() return "Paladin", "PALADIN" end
        for _, lang in ipairs({"en", "nn"}) do
            WoWStatusLocale.set(lang)
            for _, voice in ipairs(voices) do
                P.set(voice)
                for i = 1, 40 do
                    local item = {kind="death", text="Died in Hardcore", sender="Eldrin-TestRealm", nonce="1-" .. i}
                    assert(WoWStatusFlavour.text(item) == "", voice .. " " .. lang)
                    -- An own event, before it has a text.
                    assert(WoWStatusFlavour.text({kind="death", data={hardcore=true}, id="x" .. i}) == "")
                    -- Ordinary deaths still get their roast.
                    assert(WoWStatusFlavour.text({kind="death", text="Died", sender="Eldrin-TestRealm", nonce="1-" .. i}) ~= "")
                end
            end
        end
    ''')


def test_older_texts_and_hardcore_text_are_valid_and_nothing_else():
    lua = make_lua()
    lua.execute('''
        local J = WoWStatusJournal
        assert(J.validText("death", "Died in Hardcore"))
        assert(J.validText("death", "Died") and J.validText("death", "Total deaths: 3"))
        assert(not J.validText("death", "Died in Hardcore!"))
        assert(WoWStatusLocale.NN["Died in Hardcore"] == "Døydde i hardkjernemodus")
    ''')


def test_hardcore_deaths_hold_no_records():
    lua = actor('Thora')
    clock(lua, 10)
    with_entries(lua, [
        ('Mira-TestRealm', '1-1-a', 'death', 50, '{text="Died in Hardcore"}'),
        ('Bob-TestRealm', '1-2-b', 'level', 40, '{level=5}'),
    ])
    group = lua.eval('__group')
    text = plain(lua.eval(f'WoWStatusFirsts.week("{group}", 0)')[0])
    assert 'Most deaths' not in text and 'Mira' not in text, text
    assert lua.eval('(function() local r = WoWStatusFirsts.compute(WoWStatusJournal.entries()); return r.death end)()') is None
    # An ordinary death afterwards takes the record as usual.
    with_entries(lua, [('Bob-TestRealm', '1-3-c', 'death', 30, None)])
    assert lua.eval('WoWStatusFirsts.compute(WoWStatusJournal.entries()).death.sender') == 'Bob-TestRealm'
    text = plain(lua.eval(f'WoWStatusFirsts.week("{group}", 0)')[0])
    assert 'Most deaths: Bob (1)' in text


def test_fun_records_leave_out_hardcore_deaths():
    lua = actor('Thora')
    clock(lua, 10)
    group = lua.eval('(next(character().group_ids))')
    lua.execute('''
        function WoWStatusJournal.details(e) return {zone="Duskwood"} end
    ''')
    with_entries(lua, [(f'Mira{i}-TestRealm', f'1-{i}-a', 'death', 100 + i, '{text="Died in Hardcore"}')
                       for i in range(6)])
    lines = plain(lua.eval(f'WoWStatusFirsts.funRecords("{group}")'))
    assert 'Most dangerous zone' not in lines and 'deathless' not in lines, lines


def test_a_session_recap_does_not_tally_a_hardcore_death():
    lua = make_lua(STUBS + '''
        __now = 1793000000
        function time() return __now end
    ''')
    lua.execute(HARDCORE)
    lua.execute('''
        fire("PLAYER_DEAD")
        assert(not character().session or not character().session.counts.death)
        WoWStatusRecaps.close(__now)
        for _, e in ipairs(WoWStatusJournal.entries()) do
            assert(e.kind ~= "recap" or not e.text:find("died", 1, true), e.text)
        end
    ''')



def test_overview_says_died_in_hardcore_instead_of_a_tally():
    lua = make_lua()
    lua.execute('''
        local entries = {
            {id="a", sender="Mira-TestRealm", kind="death", text="Died in Hardcore", at=200},
            {id="b", sender="Bob-TestRealm", kind="death", text="Total deaths: 4", at=210},
            -- Same short name on another realm: only the ordinary death is tallied.
            {id="c", sender="Cid-HcRealm", kind="death", text="Died in Hardcore", at=230},
            {id="d", sender="Cid-TestRealm", kind="death", text="Total deaths: 2", at=220},
        }
        local text = {}
        for _, p in ipairs(WoWStatusOverview.summary(entries, 100)) do text[#text + 1] = WoWStatusOverview.sentence(p) end
        text = table.concat(text, "\\n")
        assert(text:find("Mira died in Hardcore", 1, true) and text:find("Bob died once", 1, true), text)
        assert(text:find("Cid died once", 1, true), text)
        WoWStatusLocale.set("nn")
        assert(WoWStatusLocale.T("died in Hardcore") == "døydde i hardkjernemodus")
    ''')


def test_rebuilt_death_total_leaves_out_hardcore_deaths():
    lua = make_lua()
    lua.execute('''
        local c = {epoch="1700000000", history={events={
            {kind="death", data={hardcore=true}}, {kind="death", data={total_deaths=1}}}}}
        assert(WoWStatusProgress.totalDeaths(c) == 1)
    ''')
