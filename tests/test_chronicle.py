"""Labs: weekly chronicle (#241)."""
from test_journal import actor, clock
from test_week import plain, with_entries

WEEK = 7 * 86400


def setup(enabled=True):
    lua = actor('Thora')
    clock(lua, 10)
    group = lua.eval('(next(character().group_ids))')
    lua.execute('WoWStatusFeatures.init(WoWStatusDB)')
    if enabled:
        lua.execute('WoWStatusFeatures.set("chronicle", true)')
    return lua, group


def last_week(lua, group):
    return plain(lua.eval(f'WoWStatusFirsts.week("{group}", 1)')[0])


def test_the_chapter_tells_the_weeks_climb_deaths_and_zones():
    lua, group = setup()
    with_entries(lua, [
        ('Mira-TestRealm', '1-1-a', 'level', WEEK, '{level=11}'),
        ('Mira-TestRealm', '1-2-b', 'level', WEEK + 60, '{level=10}'),
        ('Nils-TestRealm', '1-3-c', 'level', WEEK + 120, '{level=5}'),
        ('Nils-TestRealm', '1-4-d', 'death', WEEK + 180, None),
        ('Nils-TestRealm', '1-5-e', 'zone', WEEK + 240, None),
    ])
    text = last_week(lua, group)
    assert 'Chronicle of the week' in text
    assert 'Mira climbed 2 levels, reaching level 11.' in text
    assert 'The group fell 1 time.' in text and '1 new place was explored.' in text


def test_written_once_a_week_and_never_from_later_log_changes():
    lua, group = setup()
    with_entries(lua, [('Mira-TestRealm', '1-1-a', 'level', WEEK, '{level=11}')])
    last_week(lua, group)
    with_entries(lua, [('Nils-TestRealm', '1-2-b', 'death', WEEK + 100, None)])
    assert 'The group fell' not in last_week(lua, group)
    assert lua.eval(f'WoWStatusDB.chronicles["{group}"].deaths') == 0


def test_a_hardcore_death_is_told_plainly_and_a_quiet_week_says_so():
    lua, group = setup()
    assert 'A quiet week. The road waits.' in last_week(lua, group)
    lua2, group2 = setup()
    with_entries(lua2, [('Mira-TestRealm', '1-1-a', 'death', WEEK, '{text="Died in Hardcore"}')])
    text = last_week(lua2, group2)
    assert 'A Hardcore character fell this week. We remember them.' in text
    assert 'The group fell' not in text


def test_off_by_default_and_not_added_to_this_week():
    lua, group = setup(False)
    with_entries(lua, [('Mira-TestRealm', '1-1-a', 'level', WEEK, '{level=11}')])
    assert 'Chronicle' not in last_week(lua, group)
    assert lua.eval('WoWStatusDB.chronicles') is None
    on, group_on = setup()
    assert 'Chronicle' not in plain(on.eval(f'WoWStatusFirsts.week("{group_on}", 0)')[0])
