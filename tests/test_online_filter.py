"""The Characters page's "Online only" filter: it hides cards and nothing else."""
from test_roster import pair, pump


def page(lua):
    lua.eval('WoWStatusMainWindow.show')('characters')
    return lua.eval('WoWStatusCharactersPage')


def cards(lua):
    """Names on the cards shown right now."""
    shown, lines = [], page(lua).lines
    for i in range(1, len(lines) + 1):
        card = lines[i]
        if card.IsShown(card) and card.character:
            shown.append(card.character.name)
    return sorted(shown)


def headings(lua):
    texts, heads = [], page(lua).headers
    for i in range(1, len(heads) + 1):
        if heads[i].IsShown(heads[i]):
            texts.append(heads[i].text.text)
    return texts


def listed(lua):
    """Every character R.groups() knows, filter or not."""
    return sorted(r.name for g in lua.eval('WoWStatusRoster.groups()').values()
                  for r in g.rows.values())


def with_an_offline_alt(mira, thora):
    """Mira announces a second character that never appears in the channel."""
    line = next(line for line in pump(mira, thora) if line.startswith('C '))
    words = line.split(' ')
    words[4] = 'Ghost-TestRealm'
    thora.eval('WoWStatusRoster.receive')(' '.join(words), 'Mira-TestRealm', 'WHISPER')
    return 'Ghost-TestRealm'


def online_only(lua, enabled):
    lua.eval('WoWStatusRoster.setOnlineOnly')(enabled)


def test_online_only_hides_the_characters_that_are_not_online():
    mira, thora = pair()
    ghost = with_an_offline_alt(mira, thora)
    assert cards(thora) == [ghost, 'Mira-TestRealm', 'Thora-TestRealm']
    online_only(thora, True)
    assert cards(thora) == ['Mira-TestRealm', 'Thora-TestRealm']
    online_only(thora, False)
    assert cards(thora) == [ghost, 'Mira-TestRealm', 'Thora-TestRealm']


def test_a_heading_counts_only_the_cards_left_under_it():
    mira, thora = pair()
    with_an_offline_alt(mira, thora)
    assert any('Frank (2 characters)' in text for text in headings(thora))
    online_only(thora, True)
    assert any('Frank (1 character)' in text for text in headings(thora))


def test_a_player_with_nobody_online_loses_their_heading():
    mira, thora = pair()
    line = next(line for line in pump(mira, thora) if line.startswith('C '))
    words = line.split(' ')
    # Another player ID entirely, with one character that never appears in the channel.
    words[2], words[3], words[4] = 'abcdef0123456789', 'Ada2', 'Ghost-TestRealm'
    thora.eval('WoWStatusRoster.receive')(' '.join(words), 'Mira-TestRealm', 'WHISPER')
    assert any('Ada2' in text for text in headings(thora))
    online_only(thora, True)
    assert not any('Ada2' in text for text in headings(thora))
    assert 'Ghost-TestRealm' not in cards(thora)


def test_the_empty_page_says_which_of_the_two_it_is():
    _, thora = pair()
    assert page(thora).empty.text == 'No characters yet.'
    online_only(thora, True)
    assert page(thora).empty.text == 'Nobody is online right now.'


def test_the_choice_is_remembered_and_the_box_shows_it():
    _, thora = pair()
    assert thora.eval('WoWStatusRoster.onlineOnly()') is False
    online_only(thora, True)
    assert thora.eval('WoWStatusDB.roster.online_only') is True
    thora.eval('WoWStatusMainWindow.show')('overview')
    assert page(thora).onlineOnly.checked is True   # reopening keeps the choice


def test_the_filter_changes_no_list_and_hides_nothing_from_friends():
    mira, thora = pair()
    with_an_offline_alt(mira, thora)
    before = listed(thora)
    online_only(thora, True)
    # A profile opened from a card still finds an offline character's entry.
    assert listed(thora) == before
    assert thora.eval('WoWStatusDB.roster.share') is True
    # The filter is this client's own view: nothing about it is sent.
    assert [line for line in pump(thora, mira) if 'online' in line.lower()] == []


def test_the_control_is_a_checkbox_with_a_click_a_controller_can_reach():
    _, thora = pair()
    box = page(thora).onlineOnly
    assert box.kind == 'CheckButton'
    assert thora.eval('WoWStatusCharactersPage.onlineOnly.parent == WoWStatusCharactersPage') is True
    assert box.OnClick is not None          # a click handler, so the pad can press it
    box.SetChecked(box, True)
    box.OnClick(box)
    assert thora.eval('WoWStatusRoster.onlineOnly()') is True
