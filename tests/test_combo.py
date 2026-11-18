"""Labs: hype combo banner (#236). Live updates only, built from what was received."""
from test_journal import actor, clock


def setup(enabled=True):
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute('WoWStatusFeatures.init(WoWStatusDB)')
    if enabled:
        lua.execute('WoWStatusFeatures.set("combo", true)')
    lua.execute('WoWStatusPopups.comboReset()')
    return lua


def note(lua, sender, at, kind='level'):
    return lua.eval(f'WoWStatusPopups.comboNote({{sender="{sender}-TestRealm",kind="{kind}"}}, {at})')


def test_three_milestones_within_ten_minutes_make_x3_and_name_everyone():
    lua = setup()
    assert note(lua, 'Mira', 1000) is None
    second = note(lua, 'Nils', 1100)
    assert second['count'] == 2 and second['names'] == 'Mira, Nils'
    third = note(lua, 'Olav', 1500)
    assert third['count'] == 3 and third['names'] == 'Mira, Nils, Olav'


def test_the_window_resets_after_ten_minutes_without_a_milestone():
    lua = setup()
    note(lua, 'Mira', 1000)
    note(lua, 'Nils', 1100)
    assert note(lua, 'Olav', 1100 + 601) is None  # a new combo starts at 1
    assert note(lua, 'Mira', 1100 + 650)['count'] == 2


def test_off_by_default_and_own_and_join_notes_do_not_count():
    off = setup(False)
    assert note(off, 'Mira', 1000) is None and note(off, 'Nils', 1010) is None
    lua = setup()
    assert note(lua, 'Mira', 1000, 'introduction') is None
    assert note(lua, 'Thora', 1010) is None
    assert note(lua, 'Nils', 1020) is None  # only one counted so far
