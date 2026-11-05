"""Character list grouped by player, with portraits (#59)."""
from test_journal import actor, clock

EXTRA = '''
    function UnitRace() return "Dwarf", "Dwarf" end
    function UnitSex() return 3 end
    RAID_CLASS_COLORS = {WARRIOR={colorStr="ffc79c6e"}}
'''


def person(name, player_name):
    lua = actor(name)
    lua.execute(EXTRA)
    # Test runtimes share one random seed; give each account its own player ID.
    pid = (name.encode().hex() * 8)[:16]
    lua.execute(f'WoWStatusDB.player_name = "{player_name}"; WoWStatusDB.roster.id = "{pid}"; WoWStatusRoster.observe(character())')
    return lua


def pump(sender, receiver, start=100):
    """Run the sender's roster ticks and deliver its roster whispers to the receiver."""
    before = sender.eval('#__sent')
    for step in range(20):
        sender.execute(f'__mono = {start + step}')
        sender.eval('WoWStatusRoster.tick')()
    name = sender.eval('WoWStatusAdapter.playerName()') + '-TestRealm'
    delivered = []
    for i in range(before + 1, sender.eval('#__sent') + 1):
        packet = sender.eval(f'__sent[{i}]')
        if packet['prefix'] == 'WoWStatusChr':
            delivered.append(packet['text'])
            receiver.eval('fire')('CHAT_MSG_ADDON', 'WoWStatusChr', packet['text'], 'WHISPER', name)
    return delivered


def pair():
    mira, thora = person('Mira', 'Frank'), person('Thora', 'Ada')
    for lua in (mira, thora):
        lua.execute('__peers={"Thora-TestRealm","Mira-TestRealm"}')
    return mira, thora


def test_characters_are_announced_once_per_member_and_grouped_by_player():
    mira, thora = pair()
    sent = pump(mira, thora)
    assert len(sent) == 1
    assert sent[0].split(' ')[0] == 'C' and sent[0].endswith('Mira-TestRealm Dwarf 3 WARRIOR 1')
    assert pump(mira, thora, start=200) == []  # not repeated to the same member
    groups = thora.eval('WoWStatusRoster.groups()')
    titles = [groups[i].title for i in range(1, len(groups) + 1)]
    assert 'Frank (1 character)' in titles and 'Ada (you) (1 character)' in titles
    thora.eval('SlashCmdList.WOWSTATUS')('characters')
    text = '\n'.join(thora.eval(f'WoWStatusCharactersPage.lines[{i}].text.text')
                     for i in range(1, thora.eval('WoWStatusCharactersPage.count') + 1))
    assert '|cffc79c6eMira|r   Warrior 1   online' in text


def test_accounts_with_the_same_player_name_are_merged():
    mira, thora = pair()
    other = person('Bob', 'frank')
    other.execute('__peers={"Thora-TestRealm","Bob-TestRealm"}')
    thora.execute('__peers={"Thora-TestRealm","Mira-TestRealm","Bob-TestRealm"}')
    pump(mira, thora)
    pump(other, thora)
    groups = thora.eval('WoWStatusRoster.groups()')
    frank = [groups[i] for i in range(1, len(groups) + 1) if groups[i].title.lower().startswith('frank')]
    assert len(frank) == 1 and len(frank[0].rows) == 2


def test_portraits_prefer_live_units_then_race_faces_then_silhouettes():
    lua = person('Thora', 'Ada')
    lua.execute('''
        __live = nil
        function SetPortraitTexture(texture, unit) texture.texture = "live:" .. unit end
        function UnitName(unit) if unit == "target" and __live then return __live end if unit == "player" then return "Thora" end end
        local t = CreateFrame("Frame"):CreateTexture()
        __live = "Mira"
        assert(WoWStatusRoster.portrait(t, "Mira-TestRealm", "Dwarf", 3) == "live" and t.texture == "live:target")
        __live = nil
        assert(WoWStatusRoster.portrait(t, "Mira-TestRealm", "Dwarf", 3) == "met")
        assert(t.texture == "Interface\\\\CharacterFrame\\\\TemporaryPortrait-Female-Dwarf")
        assert(WoWStatusRoster.portrait(t, "Mira-TestRealm") == "unknown")
        assert(t.texture == "Interface\\\\CharacterFrame\\\\TempPortrait")
        local methods = getmetatable(t).__index
        local original = methods.SetTexture
        function methods:SetTexture(path) if path:find("TempPortrait", 1, true) then return false end self.texture = path end
        assert(WoWStatusRoster.portrait(t, "Mira-TestRealm") == "unknown")
        assert(t.texture == "Interface\\\\Icons\\\\INV_Misc_QuestionMark")
        methods.SetTexture = original
    ''')


def test_bad_or_unauthorised_announcements_are_rejected():
    mira, thora = pair()
    pid = mira.eval('WoWStatusDB.roster.id')
    group = thora.eval('(function() for id in pairs(character().group_ids) do return id end end)()')
    receive = thora.eval('WoWStatusRoster.receive')
    good = f'C {group} {pid} Frank Mira-TestRealm Dwarf 3 WARRIOR 12'
    assert receive(good, 'Mira-TestRealm', 'WHISPER') is True
    for bad in (good.replace('WARRIOR', 'PIRATE'), good.replace(' 12', ' 999'), good.replace(' 3 ', ' 1 '),
                good.replace('Dwarf', 'Dw4rf'), good.replace('Mira-TestRealm', 'Mira|cff'), good.replace(pid, 'xyz'),
                good.replace(f'C {group}', 'C othergroup'), good + ' extra'):
        assert receive(bad, 'Mira-TestRealm', 'WHISPER') is False, bad
    assert receive(good, 'Stranger-TestRealm', 'WHISPER') is False
    assert receive(good, 'Mira-TestRealm', 'CHANNEL') is False


def test_hiding_a_character_and_turning_sharing_off():
    mira, thora = pair()
    pump(mira, thora)
    assert thora.eval('next(WoWStatusDB.roster.players)') is not None
    mira.execute('WoWStatusRoster.setHidden(character(), true)')
    assert pump(mira, thora, start=300) == []
    mira.execute('WoWStatusRoster.setHidden(character(), false); WoWStatusRoster.setSharing(false)')
    sent = pump(mira, thora, start=400)
    assert len(sent) == 1 and sent[0].startswith('X ')
    assert thora.eval('next(WoWStatusDB.roster.players)') is None
    mira.execute('WoWStatusRoster.setSharing(true)')
    assert len(pump(mira, thora, start=500)) == 1


def test_log_senders_without_a_list_show_as_never_met():
    lua = person('Thora', 'Ada')
    clock(lua, 10)
    lua.execute('''
        WoWStatusJournal.received({sender="Eldrin-TestRealm", nonce="a1", kind="level", level=8})
        local found
        for _, group in ipairs(WoWStatusRoster.groups()) do
            if group.title:find("Not announced", 1, true) then found = group.rows[1] end
        end
        assert(found and found.name == "Eldrin-TestRealm" and found.level == nil)
        assert(found.latest == "Reached level 8!")
    ''')


def test_full_names_with_spaces_are_announced_and_replace_first_name_entries():
    # WoW Forever: an older client announced "Mira"; the full name is "Mira Stone".
    mira, thora = pair()
    pump(mira, thora)
    mira.execute('character().chat_name = "Mira Stone"')
    mira.execute('WoWStatusRoster.changed()')
    sent = pump(mira, thora, start=300)
    assert sent and 'Mira_Stone-TestRealm' in sent[0]
    names = [r.name for g in thora.eval('WoWStatusRoster.groups()').values() for r in g.rows.values()]
    assert 'Mira Stone-TestRealm' in names and 'Mira-TestRealm' not in names


def test_a_first_name_entry_shows_as_its_one_known_full_name():
    mira, thora = pair()
    pump(mira, thora)
    thora.execute('WoWStatusPopups.notePeer(next(character().group_ids), "Mira Stone-TestRealm")')
    names = [r.name for g in thora.eval('WoWStatusRoster.groups()').values() for r in g.rows.values()]
    assert 'Mira Stone-TestRealm' in names and 'Mira-TestRealm' not in names
    assert names.count('Mira Stone-TestRealm') == 1
