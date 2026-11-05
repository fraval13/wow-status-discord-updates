"""History from before installation: start marker, level achievements, lifetime deaths.

Mocked client APIs only; the real achievement and statistic data still needs a
live-client check.
"""
from test_addon import STUBS, make_lua
from test_forever import forever_runtime
from test_retail import retail_runtime

# A deterministic clock that also converts date tables, as WoW's time() does.
CLOCK = '''
    local realTime=os.time
    function time(t) if t then return realTime(t) end return 1793000000 end
'''

# Level 10 and level 80 were earned by this character; level 20 by another
# warband character; ID 8 has an unexpected name, so its level is not trusted.
ACHIEVEMENTS = CLOCK + '''
    __achievements={
        [6]={"Level 10",true,3,15,24,true},
        [7]={"Level 20",true,4,1,24,false},
        [8]={"Explorer",true,5,1,24,true},
        [13]={"Level 80",true,9,30,25,true},
        [4826]={"Level 85",false,nil,nil,nil,true},
    }
    function GetAchievementInfo(id)
        local a=__achievements[id]
        if not a then return nil end
        return id,a[1],10,a[2],a[3],a[4],a[5],"desc",0,1,"",false,a[6]
    end
    __deaths="41"
    function GetStatistic(id) if id==60 then return __deaths end end
'''


def journal_ids(lua):
    return sorted(e['id'] for e in lua.eval('WoWStatusJournal.entries()').values())


def test_classic_records_where_tracking_started_without_logging_or_sending():
    lua = make_lua(STUBS.replace('__level = 1\n', '__level = 15\n'))
    lua.execute('''
        local start=character().tracking_start
        assert(start.level==15 and start.at<character().progress.started_at)
        assert(#WoWStatusJournal.entries()==0 and #__sent==0)
        WoWStatusJournal.show()
        local row=WoWStatusActivityLog.rows[1]
        assert(row.entry.kind=="tracking" and row:IsShown())
        assert(row.message.text:find("Tracking started at level 15",1,true))
        assert(row.detail.text:find("Your activity",1,true))
        local _,_,_,_,heading=WoWStatusPresentation.theme(row.entry)
        assert(heading=="TRACKING STARTED")
        -- Friends' entries only: no marker.
        WoWStatusActivityLog.filter="friends";WoWStatusJournal.show()
        assert(#WoWStatusActivityLog.entriesList==0)
        -- Without statistics, death totals stay "since installation".
        assert(character().progress.death_base==nil)
        fire("PLAYER_DEAD")
        assert(character().events[#character().events].data.total_deaths==1)
        assert(character().snapshot.deaths_lifetime==nil)
    ''')


def test_level_one_install_shows_no_marker():
    lua = make_lua()
    lua.execute('''
        assert(character().tracking_start.level==1)
        WoWStatusJournal.show()
        assert(#WoWStatusActivityLog.entriesList==0)
    ''')


def test_existing_install_starts_below_its_first_recorded_level_up():
    lua = make_lua(STUBS.replace('__level = 1\n', '__level = 30\n'))
    lua.execute('''
        local c=character()
        c.tracking_start=nil
        table.insert(c.history.events,1,{id="old-1",kind="level",at=1,data={level=13}})
        table.insert(c.history.events,{id="old-2",kind="level",at=2,data={level=14}})
        WoWStatusJournal.backfill(c,30)
        assert(c.tracking_start.level==12)
        local kept=c.tracking_start.at
        WoWStatusJournal.backfill(c,40)
        assert(c.tracking_start.level==12 and c.tracking_start.at==kept)
    ''')


def test_retail_imports_dated_level_achievements_quietly_and_lifetime_deaths():
    lua = retail_runtime(extra=ACHIEVEMENTS)
    assert journal_ids(lua) == ['achievement:retail:Player-123-0001:13', 'achievement:retail:Player-123-0001:6']
    lua.execute('''
        assert(#__sent==0 and character().tracking_start.level==89)
        for _,e in ipairs(WoWStatusJournal.entries()) do
            assert(e.imported=="achievement" and e.kind=="level" and e.owner and not next(e.groups))
            assert(e.text=="Reached level "..e.level.."!")
        end
        local ten
        for _,e in ipairs(WoWStatusJournal.entries()) do if e.level==10 then ten=e end end
        assert(date("%Y-%m-%d",ten.at)=="2024-03-15")
        -- Never a medal: friends' logs do not hold this history.
        assert(next((WoWStatusFirsts.compute(WoWStatusJournal.entries())))==nil)
        WoWStatusJournal.show()
        local found
        for _,row in ipairs(WoWStatusActivityLog.rows) do
            if row.entry and row.entry.imported then
                found=true
                assert(row.detail.text:find("From your achievements (date only)",1,true))
                assert(not row.detail.text:find(":",1,true))
            end
        end
        assert(found)
        -- Repeated backfills add nothing.
        WoWStatusJournal.backfill(character(),89)
        assert(#WoWStatusJournal.entries()==2)
        -- Lifetime deaths: the statistic at login plus deaths counted since.
        assert(character().snapshot.deaths_lifetime==41)
        __deaths="41"
        fire("PLAYER_DEAD")
        assert(character().events[#character().events].data.total_deaths==42)
    ''')


def test_retail_import_respects_level_privacy_and_joined_groups_get_nothing():
    lua = retail_runtime(extra=ACHIEVEMENTS)
    lua.execute('''
        WoWStatusGroups.update("dawnwatch","")
        __sent={}
        WoWStatusJournal.sync()
        for _,packet in ipairs(__sent) do assert(not packet.text:find("Reached level",1,true)) end
        character().settings.collection.level=false
        WoWStatusJournal.privacyChanged()
        assert(#WoWStatusJournal.entries()==0)
        WoWStatusJournal.backfill(character(),89)
        assert(#WoWStatusJournal.entries()==0)
    ''')


def test_untrusted_death_statistic_is_ignored():
    lua = retail_runtime(extra=ACHIEVEMENTS)
    lua.execute('''
        character().progress.deaths=5
        __deaths="3"
        WoWStatusProgress.initDeaths(character())
        assert(character().progress.death_base==nil and WoWStatusProgress.totalDeaths(character())==5)
        __deaths="--"
        WoWStatusProgress.initDeaths(character())
        assert(WoWStatusProgress.totalDeaths(character())==5)
    ''')


def test_forever_uses_the_import_only_when_its_client_has_the_api():
    without = forever_runtime(extra=CLOCK + '__level=40')
    without.eval('fire')('PLAYER_LOGIN')
    assert without.eval('character().tracking_start.level') == 40
    assert journal_ids(without) == []
    with_api = forever_runtime(extra=ACHIEVEMENTS + '__level=40')
    with_api.eval('fire')('PLAYER_LOGIN')
    assert journal_ids(with_api) == ['achievement:forever:Player-123-0001:6']
    assert with_api.eval('character().snapshot.deaths_lifetime') == 41
