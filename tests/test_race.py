"""Labs: race a friend to a level (#238). Local only; nothing is sent."""
from test_journal import actor, clock
from test_week import with_entries


def setup(enabled=True):
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute('WoWStatusFeatures.init(WoWStatusDB)')
    if enabled:
        lua.execute('WoWStatusFeatures.set("race", true)')
    lua.execute('__notices={}; local n=WoWStatusPopups.notice; WoWStatusPopups.notice=function(i) table.insert(__notices,i.text); return true end')
    return lua


def friend_level(lua, level, age):
    with_entries(lua, [('Mira-TestRealm', f'7-{level}-a', 'level', age, f'{{level={level}}}')])


def start(lua, name='mira', target=40):
    return lua.eval(f'(function() local ok, why = WoWStatusStatusLine.raceStart("{name}", {target}); return ok end)()')


def test_progress_is_shown_and_survives_a_reload():
    lua = setup()
    friend_level(lua, 37, 500)
    assert start(lua) is True
    assert lua.eval('WoWStatusStatusLine.raceText()').startswith('Race to 40: you ')
    assert 'Mira 37' in lua.eval('WoWStatusStatusLine.raceText()')
    # A reload keeps WoWStatusDB: the race is read from it again.
    assert lua.eval('WoWStatusStatusLine.race().target') == 40


def test_friend_getting_there_first_ends_the_race_with_a_banner():
    lua = setup()
    friend_level(lua, 38, 500)
    assert start(lua)
    friend_level(lua, 40, 100)
    assert lua.eval('WoWStatusStatusLine.raceText()') is None
    assert lua.eval('WoWStatusStatusLine.race()') is None
    assert lua.eval('__notices[1]') == 'Mira got to level 40 first!'


def test_reaching_it_yourself_first_wins():
    lua = setup()
    friend_level(lua, 38, 500)
    assert start(lua)
    lua.execute('__level=40; fire("PLAYER_LEVEL_UP",40)')
    assert lua.eval('WoWStatusStatusLine.raceText()') is None
    assert lua.eval('__notices[1]') == 'You won the race to level 40!'


def test_off_by_default_unknown_friend_and_cancel():
    off = setup(False)
    friend_level(off, 37, 500)
    assert start(off) is False and off.eval('WoWStatusStatusLine.race()') is None
    lua = setup()
    assert start(lua, 'nobody') is False
    friend_level(lua, 37, 500)
    assert start(lua, 'mira', 1) is False
    assert start(lua) and lua.eval('WoWStatusStatusLine.raceCancel()') is True
    assert lua.eval('WoWStatusStatusLine.race()') is None


def test_a_friend_who_left_the_group_ends_the_race_quietly():
    lua = setup()
    friend_level(lua, 37, 500)
    assert start(lua)
    lua.execute('WoWStatusJournal.visible=function() return false end')
    assert lua.eval('WoWStatusStatusLine.raceText()') is None
    assert lua.eval('WoWStatusStatusLine.race()') is None and lua.eval('#__notices') == 0
