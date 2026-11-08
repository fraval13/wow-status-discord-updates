"""Professions on the character list: the game's icons with each skill level under them."""
from test_roster import pair, pump

# What the game reported for this character, as Progress saves it.
PROFS = '''
    character().settings.fields.professions = true
    character().progress.professions = {
        {key="mining", skill=150, max_skill=300, name="Mining", source="game_api"},
        {key="blacksmithing", skill=225, max_skill=300, name="Blacksmithing", source="game_api"},
        {key="cooking", skill=75, max_skill=300, name="Cooking", source="game_api"},
    }
'''


def strip(lua, name):
    """(icon, skill text) for every profession slot shown on that character's card."""
    lua.eval('WoWStatusMainWindow.show')('characters')
    cards = lua.eval('WoWStatusCharactersPage.lines')
    for i in range(1, len(cards) + 1):
        card = cards[i]
        if card.IsShown(card) and card.character and name in card.character.name:
            shown = []
            for j in range(1, len(card.professions) + 1):
                slot = card.professions[j]
                if slot.icon.IsShown(slot.icon):
                    shown.append((slot.icon.texture, slot.skill.text))
            return shown
    return None


def lines(sent, op):
    return [line for line in sent if line.split(' ')[0] == op]


def test_a_friends_professions_reach_their_card_best_skill_first():
    mira, thora = pair()
    mira.execute(PROFS)
    sent = pump(mira, thora)
    assert lines(sent, 'Y') == [lines(sent, 'Y')[0]]   # one line, not one per profession
    assert lines(sent, 'Y')[0].endswith('mining:150:300,blacksmithing:225:300,cooking:75:300')
    assert strip(thora, 'Mira') == [
        ('Interface\\Icons\\Trade_BlackSmithing', '225'),
        ('Interface\\Icons\\Trade_Mining', '150'),
        ('Interface\\Icons\\INV_Misc_Food_15', '75'),
    ]


def test_your_own_card_shows_what_the_game_reported_here():
    mira, _ = pair()
    mira.execute(PROFS)
    assert strip(mira, 'Mira') == [
        ('Interface\\Icons\\Trade_BlackSmithing', '225'),
        ('Interface\\Icons\\Trade_Mining', '150'),
        ('Interface\\Icons\\INV_Misc_Food_15', '75'),
    ]


def test_nothing_is_shared_while_profession_sharing_is_off():
    mira, thora = pair()
    mira.execute(PROFS + 'character().settings.fields.professions = false')
    assert lines(pump(mira, thora), 'Y') == []
    assert strip(thora, 'Mira') == []


def test_player_entered_labels_never_travel():
    # /wstatus professions sets names by hand; only read skill ranks are shared.
    mira, thora = pair()
    mira.execute('''
        character().settings.fields.professions = true
        character().professions = {{name="Grandmaster Blacksmith", source="player_entered"}}
    ''')
    assert lines(pump(mira, thora), 'Y') == []
    assert strip(thora, 'Mira') == []


def crafted(sent, payload):
    head = lines(sent, 'Y')[0].split(' ')
    return ' '.join(head[:4] + [payload])


def receive(lua, text):
    return lua.eval('WoWStatusRoster.receive')(text, 'Mira-TestRealm', 'WHISPER')


def test_a_damaged_profession_line_is_refused_and_changes_nothing():
    mira, thora = pair()
    mira.execute(PROFS)
    sent = pump(mira, thora)
    good = strip(thora, 'Mira')
    for payload in ('sorcery:10:300',                      # not a profession this version knows
                    'mining:150',                          # missing the maximum
                    'mining:1500:300',                     # beyond the skill limit
                    'mining:150:0',                        # a maximum of zero
                    'Mining:150:300',                      # a name, not a key
                    ','.join(['mining:1:300'] * 7)):       # more than a character can have
        ok = receive(thora, crafted(sent, payload))
        assert ok is False, payload
        assert strip(thora, 'Mira') == good, payload


def test_a_queued_line_is_dropped_when_sharing_is_turned_off_first():
    mira, thora = pair()
    mira.execute(PROFS)
    mira.eval('WoWStatusRoster.tick')()
    mira.execute('character().settings.fields.professions = false')
    assert lines(pump(mira, thora), 'Y') == []
    assert strip(thora, 'Mira') == []
