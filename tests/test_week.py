"""Records page: This week (per group, earlier weeks) and Fun records (high thresholds)."""
import re

from test_journal import actor, clock

DAY = 86400


def plain(lines):
    return re.sub(r'\|c[0-9a-f]{8}|\|r', '', '\n'.join(lines.values()))


def with_entries(lua, items):
    lua.execute('''
        __group = next(character().group_ids)
        function __put(sender, nonce, kind, at, extra)
            local e = {sender=sender, nonce=nonce, kind=kind, at=at, group_id=__group, text=kind=="death" and "Total deaths: 1" or nil}
            for k, v in pairs(extra or {}) do e[k] = v end
            WoWStatusJournal.received(e)
        end
    ''')
    for sender, nonce, kind, offset, extra in items:
        lua.execute(f'__put("{sender}", "{nonce}", "{kind}", WoWStatusSafe.now() - {offset}, {extra or "nil"})')


def test_this_week_lists_highlights_and_people_and_earlier_weeks():
    lua = actor('Thora')
    clock(lua, 10)
    with_entries(lua, [
        ('Mira-TestRealm', '1-1-a', 'level', 60, '{level=5}'),
        ('Mira-TestRealm', '1-2-b', 'level', 30, '{level=6}'),
        ('Bob-TestRealm', '1-3-c', 'death', 20, None),
        ('Bob-TestRealm', '1-4-d', 'level', 7 * DAY, '{level=9}'),   # the same weekday last week
    ])
    group = lua.eval('__group')
    text = plain(lua.eval(f'WoWStatusFirsts.week("{group}", 0)')[0])
    assert 'Most levels: Mira (2)' in text and 'Most deaths: Bob (1)' in text
    assert 'Mira: +2 levels' in text and 'Bob: 1 death' in text
    earlier = plain(lua.eval(f'WoWStatusFirsts.week("{group}", 1)')[0])
    assert 'Bob: +1 level' in earlier and 'Mira' not in earlier


def test_week_view_on_the_records_page():
    lua = actor('Thora')
    clock(lua, 10)
    with_entries(lua, [('Mira-TestRealm', '1-1-a', 'level', 60, '{level=5}')])
    lua.execute('''
        WoWStatusMainWindow.show("records")
        local page = WoWStatusRecordsPage
        page.viewWeek.OnClick(page.viewWeek)
        assert(page.heading.text:find("This week", 1, true))
        assert(page.textRows[1].text:find("Mira", 1, true))
        page.weekBack.OnClick(page.weekBack)
        assert(page.heading.text:find("Week", 1, true) and not page.heading.text:find("This week", 1, true))
    ''')


def test_fun_records_need_remarkable_numbers():
    lua = actor('Thora')
    clock(lua, 10)
    group = lua.eval('(next(character().group_ids))')
    # Three levels in one day: below the threshold of four.
    with_entries(lua, [('Mira-TestRealm', f'1-{i}-a', 'level', 100 + i, f'{{level={i + 1}}}') for i in range(3)])
    assert len(lua.eval(f'WoWStatusFirsts.funRecords("{group}")')) == 0
    with_entries(lua, [('Mira-TestRealm', '1-9-a', 'level', 50, '{level=9}')])
    lines = plain(lua.eval(f'WoWStatusFirsts.funRecords("{group}")'))
    assert 'Best evening: Mira — 4 levels' in lines


def test_this_week_orders_people_by_level_then_name():
    """A comparator that is not a strict ordering scrambled this list (#118)."""
    names = ['Alice', 'Bob', 'Cain', 'Dora', 'Eva', 'Finn', 'Gorm', 'Hild', 'Ivar', 'Jon',
             'Kira', 'Lars', 'Mira', 'Nils', 'Olav', 'Pia', 'Quin', 'Rolf', 'Siv', 'Tore']
    lua = actor('Thora')
    clock(lua, 10)
    items = []
    for i, name in enumerate(names):
        levels = (i * 7) % 5  # 0 to 4, deliberately mixed against the alphabet
        for n in range(levels):
            items.append((f'{name}-TestRealm', f'{i}-{n}-a', 'level', 60 + i, f'{{level={n + 2}}}'))
        if levels == 0:  # still listed, through a death
            items.append((f'{name}-TestRealm', f'{i}-d-a', 'death', 60 + i, None))
    with_entries(lua, items)
    group = lua.eval('__group')
    lines = plain(lua.eval(f'WoWStatusFirsts.week("{group}", 0)')[0]).splitlines()
    people = [line for line in lines if re.match(r'^[A-Z][a-z]+: ', line)]
    assert len(people) == len(names)
    got = []
    for line in people:
        match = re.match(r'^([A-Z][a-z]+): (?:\+(\d+) levels?)?', line)
        got.append((match[1], int(match[2]) if match[2] else 0))
    assert got == sorted(got, key=lambda person: (-person[1], person[0])), got
