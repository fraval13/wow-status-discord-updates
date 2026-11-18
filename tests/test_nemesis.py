"""Labs: group nemesis and deadliest zone (#237)."""
from test_journal import actor, clock
from test_week import plain, with_entries

KILLERS = {'a': ('Hogger', 'Elwynn'), 'b': ('Hogger', 'Duskwood'), 'c': ('Hogger', 'Duskwood'),
           'd': ('Murloc', 'Duskwood'), 'e': ('Murloc', None), 'f': (None, 'Duskwood')}


def setup(enabled):
    lua = actor('Thora')
    clock(lua, 10)
    group = lua.eval('(next(character().group_ids))')
    lua.execute('WoWStatusFeatures.init(WoWStatusDB)')
    if enabled:
        lua.execute('WoWStatusFeatures.set("nemesis", true)')
    table = ','.join(f'{k}={{killer={"nil" if v[0] is None else repr(v[0])},zone={"nil" if v[1] is None else repr(v[1])}}}'
                     for k, v in KILLERS.items())
    lua.execute(f'''
        __d={{{table}}}
        function WoWStatusJournal.details(e) return __d[e.id:match("%-(%a)$")] end
    ''')
    return lua, group


def deaths(lua, entries):
    with_entries(lua, [(f'Mira-TestRealm', f'1-{i}-{k}', 'death', age, '{text="Died"}')
                       for i, (k, age) in enumerate(entries)])


def test_off_by_default_adds_nothing():
    lua, group = setup(False)
    deaths(lua, [('a', 100), ('b', 200), ('c', 300)])
    assert 'nemesis' not in plain(lua.eval(f'WoWStatusFirsts.funRecords("{group}")')).lower()


def test_counts_killers_and_zones_and_ignores_unknowns_and_hardcore():
    lua, group = setup(True)
    deaths(lua, [('a', 100), ('b', 200), ('c', 300), ('d', 400), ('e', 500), ('f', 600)])
    with_entries(lua, [('Mira-TestRealm', '1-9-a', 'death', 50, '{text="Died in Hardcore"}')])
    lines = plain(lua.eval(f'WoWStatusFirsts.funRecords("{group}")'))
    assert 'Group nemesis: Hogger — 3 kills' in lines, lines
    assert 'Deadliest zone this week: Duskwood — 4 deaths' in lines, lines


def test_ties_are_shown_together_and_old_deaths_leave_the_week():
    lua, group = setup(True)
    week = 20 * 86400
    deaths(lua, [('a', week), ('b', week), ('d', 100), ('d', 200)])
    lines = plain(lua.eval(f'WoWStatusFirsts.funRecords("{group}")'))
    assert 'Group nemesis: Hogger, Murloc — 2 kills' in lines, lines
    assert 'Nemesis this week: Murloc — 2 kills' in lines, lines
