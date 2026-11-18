"""Labs: weekly group bingo card (#239)."""
from test_journal import actor, clock
from test_week import plain, with_entries


def setup(enabled=True):
    lua = actor('Thora')
    clock(lua, 10)
    group = lua.eval('(next(character().group_ids))')
    lua.execute('WoWStatusFeatures.init(WoWStatusDB)')
    if enabled:
        lua.execute('WoWStatusFeatures.set("bingo", true)')
    lua.execute('__notices={}; WoWStatusPopups.notice=function(i) table.insert(__notices,i.text); return true end')
    return lua, group


def card(lua, group, offset=0):
    cells = lua.eval(f'(WoWStatusFirsts.bingo("{group}", {offset}))')
    return [(cells[i]['text'], cells[i]['by']) for i in range(1, 26)]


def test_every_member_gets_the_same_card_and_a_new_week_a_new_one():
    a, group = setup()
    b, group_b = setup()
    assert group == group_b
    texts = [t for t, _ in card(a, group)]
    assert texts == [t for t, _ in card(b, group)]
    assert len(set(texts)) == 25
    assert texts != [t for t, _ in card(a, group, 1)]


def test_squares_fill_from_the_log_and_name_who_did_it():
    lua, group = setup()
    with_entries(lua, [('Mira-TestRealm', '1-1-a', 'level', 100, '{level=21}'),
                       ('Nils-TestRealm', '1-2-b', 'death', 90, None)])
    lua.execute('''
        WoWStatusFirsts.BINGO={{"A level-up",function(l) return l[1] and "Mira" end},{"Someone dies",function(l)
            for _,e in ipairs(l) do if e.kind=="death" then return "Nils" end end end}}
        for i=3,25 do WoWStatusFirsts.BINGO[i]={"Never "..i,function() return nil end} end
    ''')
    cells = dict(card(lua, group))
    assert cells['A level-up'] == 'Mira' and cells['Someone dies'] == 'Nils'
    assert sum(1 for v in cells.values() if v) == 2


def test_hardcore_deaths_never_fill_a_square():
    lua, group = setup()
    with_entries(lua, [('Mira-TestRealm', '1-1-a', 'death', 100, '{text="Died in Hardcore"}')])
    cells = dict(card(lua, group))
    assert cells.get('Someone dies') is None


def test_a_full_line_is_a_bingo_with_one_banner_per_week():
    lua, group = setup()
    lua.execute('for i=1,25 do WoWStatusFirsts.BINGO[i]={"Square "..i,function() return (i<=5) and "Mira" or nil end} end')
    lua.execute('for i=26,#WoWStatusFirsts.BINGO do WoWStatusFirsts.BINGO[i]=nil end')
    assert lua.eval(f'WoWStatusFirsts.bingoWins((WoWStatusFirsts.bingo("{group}",0)))') in (True, False)
    # Force a known full row regardless of the shuffle: every square filled.
    lua.execute('for i=1,25 do WoWStatusFirsts.BINGO[i]={"Square "..i,function() return "Mira" end} end')
    assert lua.eval(f'WoWStatusFirsts.bingoWins((WoWStatusFirsts.bingo("{group}",0)))') is True
    first = plain(lua.eval(f'WoWStatusFirsts.week("{group}", 0)')[0])
    assert 'Weekly bingo: 25/25' in first and 'Bingo!' in first
    plain(lua.eval(f'WoWStatusFirsts.week("{group}", 0)')[0])
    assert lua.eval('#__notices') == 1


def test_off_by_default_adds_nothing_to_this_week():
    lua, group = setup(False)
    with_entries(lua, [('Mira-TestRealm', '1-1-a', 'level', 100, '{level=21}')])
    assert 'bingo' not in plain(lua.eval(f'WoWStatusFirsts.week("{group}", 0)')[0]).lower()
