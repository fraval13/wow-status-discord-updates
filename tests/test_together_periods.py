"""Together calendar views use visible, retained milestones; never snapshot deltas."""
import pytest
from test_client_compatibility import client_runtime
from test_local_time import local_client, stamp
from test_together import crafted
from test_week import with_entries


@pytest.mark.parametrize(('zone', 'now', 'period', 'expected'), [
    ('America/Los_Angeles', '2026-11-02T00:30:00-08:00', 'daily', ('2026-11-02', '2026-11-02')),
    ('America/Los_Angeles', '2026-11-01T23:30:00-08:00', 'weekly', ('2026-10-26', '2026-11-01')),
    ('Europe/Oslo', '2026-03-30T01:30:00+02:00', 'weekly', ('2026-03-30', '2026-04-05')),
    ('Europe/Oslo', '2024-02-20T12:00:00+01:00', 'monthly', ('2024-02-01', '2024-02-29')),
    ('Europe/Oslo', '2100-02-20T12:00:00+01:00', 'monthly', ('2100-02-01', '2100-02-28')),
    ('Asia/Tokyo', '2027-01-01T00:30:00+09:00', 'yearly', ('2027-01-01', '2027-12-31')),
])
def test_periods_follow_local_calendar_dates(zone, now, period, expected):
    lua = local_client(zone, now)
    assert lua.eval('WoWStatusTogether.periodRange')(period) == expected
    assert lua.eval('WoWStatusTogether.periodRange("total")') is None


def rows_for(lua, group, period):
    result = lua.eval('WoWStatusTogether.activity')(group, period)
    return {row['caption']: row['total'] for row in result['rows'].values()}


def test_daily_weekly_monthly_and_yearly_count_only_their_own_events():
    now = '2026-11-19T12:00:00+01:00'
    lua = local_client('Europe/Oslo', now)
    group = crafted(lua)
    for i, at in enumerate(('2026-11-19T09:00:00+01:00', '2026-11-17T09:00:00+01:00',
                            '2026-11-03T09:00:00+01:00', '2026-10-01T09:00:00+02:00',
                            '2025-12-31T09:00:00+01:00')):
        with_entries(lua, [('Mira-TestRealm', f'level-{i}', 'level', stamp(now)-stamp(at), '{level=40}')])
    sent = lua.eval('#__sent')
    for period, expected in [('daily', '1'), ('weekly', '2'), ('monthly', '3'), ('yearly', '4')]:
        rows = rows_for(lua, group, period)
        assert rows['Level-up milestones'] == expected
        assert 'Hours played' not in rows and 'Gold gathered' not in rows
    assert lua.eval('#__sent') == sent
    assert lua.eval('WoWStatusTogether.totals')(group)['rows'][1]['caption'] == 'Hours played'


def test_periods_respect_group_visibility_and_exclude_imports_and_future_entries():
    lua = local_client('Europe/Oslo', '2026-11-19T12:00:00+01:00')
    group = crafted(lua)
    with_entries(lua, [('Mira-TestRealm', 'allowed', 'level', 60, '{level=40}'),
                       ('Eldrin-TestRealm', 'hidden', 'level', 50, '{level=30}'),
                       ('Bob-TestRealm', 'muted', 'level', 40, '{level=20}'),
                       ('Mira-TestRealm', 'other', 'level', 30, '{level=41}')])
    lua.execute('''
        WoWStatusRoster.hiddenNames=function() return {[WoWStatusRoster.key("Eldrin-TestRealm")]=true} end
        WoWStatusMutes.setCharacter("Bob-TestRealm","hide")
        local entries=WoWStatusJournal.entries()
        for _,e in ipairs(entries) do if e.id:find("other",1,true) then e.groups={other=true} end end
        entries[#entries+1]={id="sample",sender="Mira-TestRealm",kind="level",at=time()-10,sample=true,groups={[__group]=true}}
        entries[#entries+1]={id="import",sender="Mira-TestRealm",kind="level",at=time()-10,imported=true,groups={[__group]=true}}
        entries[#entries+1]={id="future",sender="Mira-TestRealm",kind="level",at=time()+60,groups={[__group]=true}}
    ''')
    assert rows_for(lua, group, 'daily')['Level-up milestones'] == '1'


def test_recovered_events_use_the_original_date_and_zones_are_counted_once():
    lua = local_client('Europe/Oslo', '2026-11-19T12:00:00+01:00')
    group = crafted(lua)
    with_entries(lua, [('Mira-TestRealm', 'one', 'zone', 60, '{text="Entered Duskwood"}'),
                       ('Thora-TestRealm', 'two', 'zone', 50, '{text="Entered Duskwood"}'),
                       ('Mira-TestRealm', 'three', 'quest', 40, '{text="Completed 100 quests!"}')])
    lua.execute('for _,e in ipairs(WoWStatusJournal.entries()) do e.origin="catchup" end')
    rows = rows_for(lua, group, 'daily')
    assert rows['Zones explored'] == '1' and rows['Quest milestones'] == '1'


@pytest.mark.parametrize('edition', ['vanilla', 'forever', 'tbc', 'retail'])
def test_period_dropdown_and_clear_coverage_wording_in_every_edition(edition):
    lua = client_runtime(edition)
    lua.eval('WoWStatusGroups.update')('Synthetic period example', '')
    crafted(lua)
    lua.execute('''
        WoWStatusLocale.set("nn")
        WoWStatusTogether.show()
        local page=WoWStatusTogetherPage
        assert(page.period:GetText():find("Totalt",1,true))
        assert(page.tiles[1].note:GetText()=="Byggjer på tal frå 2 av 3 figurar")
        assert(page.scroll.kind=="ScrollFrame")
        page.period.OnClick(page.period)
        local menu=WoWStatusUI.menuFrame
        assert(#menu.items==5)
        for _,row in ipairs(menu.rows) do if row.value=="daily" then row.OnClick(row) end end
        assert(page.period:GetText():find("Dagleg",1,true))
        assert(page.since:GetText():find("Datoar: frå",1,true))
        assert(page.week:GetText():find("Eldre aktivitet kan mangle",1,true))
        assert(page.tiles[1].caption:GetText()=="Nivåmilepælar")
        assert(page.tiles[1].note:GetText()=="")
    ''')
