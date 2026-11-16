"""Player-local display and calendar boundaries, independent of the test host."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from test_journal import actor


def stamp(iso):
    return int(datetime.fromisoformat(iso).timestamp())


def local_client(zone, now):
    lua = actor('Thora')
    local_zone = ZoneInfo(zone)

    def local_date(fmt, at):
        target = timezone.utc if fmt.startswith('!') else local_zone
        return datetime.fromtimestamp(at, target).strftime(fmt.removeprefix('!'))

    lua.globals().__local_date = local_date
    lua.globals().__now = stamp(now)
    lua.execute('function date(fmt, at) return __local_date(fmt, at or time()) end')
    return lua


def receive(lua, sender, at, level=10):
    return lua.eval('WoWStatusJournal.received')(lua.table_from({
        'sender': f'{sender}-TestRealm', 'nonce': sender.lower(), 'kind': 'level',
        'level': level, 'at': stamp(at), 'group_id': lua.eval('(next(character().group_ids))'),
    }))


@pytest.mark.parametrize('zone', ['Europe/Oslo', 'America/Los_Angeles', 'Asia/Tokyo'])
@pytest.mark.parametrize('at', ['2026-01-01T00:30:00+00:00', '2026-07-01T23:30:00+00:00'])
def test_local_display_follows_the_players_clock(zone, at):
    lua = local_client(zone, at)
    expected = datetime.fromtimestamp(stamp(at), ZoneInfo(zone))
    assert lua.eval('WoWStatusHistory.localTime(time())') == expected.strftime('%Y-%m-%d %H:%M')
    assert lua.eval('WoWStatusHistory.day(time())') == expected.strftime('%Y-%m-%d')


@pytest.mark.parametrize(('now', 'yesterday'), [
    ('2026-03-09T00:30:00-07:00', '2026-03-08'),  # 24 hours ago was March 7
    ('2026-11-01T23:30:00-08:00', '2026-10-31'),  # 24 hours ago was still Nov 1
    ('2027-01-01T00:30:00-08:00', '2026-12-31'),
    ('2024-03-01T00:30:00-08:00', '2024-02-29'),
    ('2100-03-01T00:30:00-08:00', '2100-02-28'),
])
def test_yesterday_is_a_calendar_day_across_dst_and_year_boundaries(now, yesterday):
    lua = local_client('America/Los_Angeles', now)
    assert lua.eval('WoWStatusHistory.day(time(), -1)') == yesterday


@pytest.mark.parametrize(('now', 'older'), [
    ('2026-03-09T00:30:00-07:00', '2026-03-08T12:00:00-07:00'),
    ('2026-11-01T23:30:00-08:00', '2026-10-31T12:00:00-07:00'),
])
def test_activity_times_today_and_yesterday_use_local_dates(now, older):
    lua = local_client('America/Los_Angeles', now)
    assert receive(lua, 'Mira', now)
    assert receive(lua, 'Bob', older)
    lua.execute('WoWStatusJournal.show()')
    log = lua.eval('WoWStatusActivityLog')
    assert len(log.entriesList) == 1 and log.entriesList[1].sender == 'Mira-TestRealm'
    assert log.dayButton.text == 'Today'
    assert log.rows[1].detail.text.startswith(now[:16].replace('T', ' '))
    # The local day can differ from Oslo's even when both observe DST.
    log.dayButton.OnClick(log.dayButton)
    calendar = lua.eval('WoWStatusCalendar')
    assert calendar.todayKey == now[:10]
    if older[:7] != now[:7]:
        calendar.previous.OnClick(calendar.previous)
    cell = next(c for c in calendar.cells.values() if c.key == older[:10])
    assert calendar.counts[older[:10]] == 1
    cell.OnClick(cell)
    assert log.dayButton.text == 'Yesterday'
    assert len(log.entriesList) == 1 and log.entriesList[1].sender == 'Bob-TestRealm'
    assert log.rows[1].detail.text.startswith(older[:16].replace('T', ' '))


@pytest.mark.parametrize(('zone', 'now', 'current', 'previous'), [
    ('America/Los_Angeles', '2026-03-09T00:30:00-07:00',
     ('2026-03-09', '2026-03-15'), ('2026-03-02', '2026-03-08')),
    ('America/Los_Angeles', '2026-11-01T23:30:00-08:00',
     ('2026-10-26', '2026-11-01'), ('2026-10-19', '2026-10-25')),
    ('Australia/Sydney', '2026-10-05T00:30:00+11:00',
     ('2026-10-05', '2026-10-11'), ('2026-09-28', '2026-10-04')),
    ('Europe/Oslo', '2026-03-30T00:30:00+02:00',
     ('2026-03-30', '2026-04-05'), ('2026-03-23', '2026-03-29')),
])
def test_week_navigation_keeps_local_monday_to_sunday_across_dst(zone, now, current, previous):
    lua = local_client(zone, now)
    assert lua.eval('WoWStatusFirsts.weekRange()') == current
    assert lua.eval('WoWStatusFirsts.weekRange(1)') == previous


def test_weekly_records_use_the_local_week_for_entry_membership():
    lua = local_client('America/Los_Angeles', '2026-11-02T00:30:00-08:00')
    assert receive(lua, 'Mira', '2026-11-01T23:45:00-08:00')  # Monday in Oslo
    assert receive(lua, 'Bob', '2026-11-02T00:15:00-08:00')
    lua.execute('''
        local group = next(character().group_ids)
        local current = WoWStatusFirsts.week(group)
        local previous = WoWStatusFirsts.week(group, 1)
        __this = table.concat(current, "\\n")
        __last = table.concat(previous, "\\n")
    ''')
    assert 'Bob' in lua.eval('__this') and 'Mira' not in lua.eval('__this')
    assert 'Mira' in lua.eval('__last') and 'Bob' not in lua.eval('__last')


def test_profile_overview_records_and_history_show_local_times():
    at = '2026-11-01T23:30:00-08:00'
    lua = local_client('America/Los_Angeles', at)
    lua.execute('WoWStatusHistory.oslo=function() error("display must use local time") end')
    assert receive(lua, 'Mira', at)
    expected = '2026-11-01 23:30'
    data = lua.eval('WoWStatusProfile.data({name="Mira-TestRealm", level=10})')
    assert expected in data.levels[1] and expected in data.recent[1]
    lua.execute('''
        WoWStatusDB.overview={since=time()-60}
        SlashCmdList.WOWSTATUS("overview")
    ''')
    assert '2026-11-01 23:29' in lua.eval('WoWStatusOverviewPage.heading.text')
    lua.eval('SlashCmdList.WOWSTATUS')('records')
    rows = lua.eval('WoWStatusRecordsPage.rows')
    assert any(expected in row.text for row in rows.values())
    lua.execute('''
        fire("PLAYER_LEVEL_UP",2)
        SlashCmdList.WOWSTATUS("logs")
    ''')
    panel = lua.eval('WoWStatusHistoryWindow')
    assert expected in panel.text.text
    assert 'Europe/Oslo' not in panel.text.text + panel.status.text
    # Display changes never rewrite saved event timestamps or export metadata.
    assert lua.eval('character().history.events[1].at') == stamp(at)
    assert lua.eval('character().history.timezone') == 'Europe/Oslo'
    lua.execute('__now=__now+60; fire("PLAYER_LEVEL_UP",3); SlashCmdList.WOWSTATUS("times")')
    assert expected in panel.text.text and '2026-11-01 23:31' in panel.text.text
    lua.eval('SlashCmdList.WOWSTATUS')('graph')
    labels = ' '.join(font.text for font in panel.fontPool.values())
    assert '2026-11-01 23:31' in labels and 'Europe/Oslo' not in labels
