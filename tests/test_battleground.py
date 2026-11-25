"""Battlegrounds report their result, not every death inside them."""
import pytest
from test_journal import actor, clock, deliver_popup

BG = '''
__instance, __winner, __bg = nil, nil, "Warsong Gulch"
function IsInInstance() return __instance ~= nil, __instance end
function GetBattlefieldWinner() return __winner end
function GetInstanceInfo() return __bg, __instance end
function UnitFactionGroup() return "Alliance" end
function kinds()
    local list = {}
    for _, e in ipairs(character().events) do list[#list + 1] = e.kind end
    return table.concat(list, ",")
end
'''


def player(name='Mira'):
    lua = actor(name)
    lua.execute(BG)
    clock(lua, 10)
    return lua


def test_deaths_in_a_battleground_or_arena_are_neither_announced_nor_counted():
    lua = player()
    lua.eval('fire')('PLAYER_DEAD')
    assert lua.eval('kinds()') == 'death'          # Out in the world, as before.
    before = lua.eval('WoWStatusProgress.totalDeaths(character())')
    for where in ('pvp', 'arena'):
        lua.execute(f'__instance = "{where}"; character().death_latched = false')
        lua.eval('fire')('PLAYER_DEAD')
    assert lua.eval('kinds()') == 'death'          # Still only the first one.
    assert lua.eval('WoWStatusProgress.totalDeaths(character())') == before
    # A death back in the open world is announced again.
    lua.execute('__instance = nil; character().death_latched = false')
    lua.eval('fire')('PLAYER_DEAD')
    assert lua.eval('kinds()') == 'death,death'


def test_a_finished_battleground_is_reported_once_with_its_name():
    lua = player()
    lua.execute('__instance = "pvp"')
    lua.eval('fire')('UPDATE_BATTLEFIELD_STATUS')   # Mid-match: no winner yet.
    assert lua.eval('kinds()') == ''
    lua.execute('__winner = 1')                     # 1 is Alliance, so a win.
    for _ in range(3):
        lua.eval('fire')('UPDATE_BATTLEFIELD_STATUS')
    assert lua.eval('kinds()') == 'battleground'    # The event repeats; we do not.
    event = lua.eval('character().events[1]')
    assert event.data.won is True and event.data.name == 'Warsong Gulch'
    assert lua.eval('WoWStatusPopups.eventText')(event) == 'Won Warsong Gulch'
    # Leaving clears the latch, and the next match is reported on its own terms.
    lua.execute('__instance, __winner = nil, nil')
    lua.eval('fire')('UPDATE_BATTLEFIELD_STATUS')
    lua.execute('__instance, __winner, __bg = "pvp", 0, "Arathi Basin"')
    lua.eval('fire')('UPDATE_BATTLEFIELD_STATUS')
    assert lua.eval('kinds()') == 'battleground,battleground'
    lost = lua.eval('character().events[2]')
    assert lost.data.won is False
    assert lua.eval('WoWStatusPopups.eventText')(lost) == 'Lost Arathi Basin'


def test_the_result_reaches_a_friend_and_reads_as_a_battleground():
    own, friend = player('Mira'), player('Thora')
    own.execute('__instance, __winner = "pvp", 1')
    own.eval('fire')('UPDATE_BATTLEFIELD_STATUS')
    deliver_popup(own, friend)
    friend.execute('''
        __text = nil
        for _, e in ipairs(WoWStatusJournal.entries()) do
            if e.kind == "battleground" then __text = e.text end
        end
        local item = {kind="battleground", text="Won Warsong Gulch", sender="Mira-TestRealm"}
        local _, _, _, _, won = WoWStatusPresentation.theme(item)
        item.text = "Lost Arathi Basin"
        local _, _, _, _, lost = WoWStatusPresentation.theme(item)
        __headings = won .. " / " .. lost
        -- This kind has no caption bank, so the line under it is empty. The
        -- harness clock sits inside Hallow's End, and seasonal captions apply to
        -- every kind but death, so the holiday is stubbed away to see that.
        WoWStatusFlavour.holiday = function() return nil end
        __caption = WoWStatusFlavour.text(item)
    ''')
    assert friend.eval('__text') == 'Won Warsong Gulch'
    assert friend.eval('__headings') == 'BATTLEGROUND WON! / BATTLEGROUND LOST'
    assert friend.eval('__caption') == ''


SCORES = '''
__ready, __requests = true, 0
function RequestBattlefieldScoreData() __requests=__requests+1 end
function GetNumBattlefieldScores() return __ready and 3 or 0 end
function GetBattlefieldScore(i)
    if i==1 then return "Mira-OtherRealm",99,99,99,99,1,"Dwarf","Warrior","WARRIOR",999,999 end
    if i==2 then return "Stranger",98,98,98,98,0,"Orc","Warrior","WARRIOR",998,998 end
    return "Mira-TestRealm",12,40,3,250,1,"Dwarf","Warrior","WARRIOR",123456,7890
end
'''
EXPECTED = 'Won Warsong Gulch (KB 12, HK 40, deaths 3, honor 250, dmg 123456, heal 7890)'


def scoreboard_player():
    lua = player()
    lua.execute(SCORES)
    return lua


def finish(lua):
    lua.execute('__instance, __winner = "pvp", 1; fire("UPDATE_BATTLEFIELD_STATUS")')


def test_final_scoreboard_uses_only_our_own_row_and_keeps_one_result():
    lua = scoreboard_player()
    lua.execute('__instance="pvp"; fire("PLAYER_DEAD");fire("UPDATE_BATTLEFIELD_SCORE")')
    assert lua.eval('__requests') == 0
    assert lua.eval('kinds()') == ''
    finish(lua)
    for event in ('UPDATE_BATTLEFIELD_STATUS', 'UPDATE_BATTLEFIELD_SCORE', 'PVP_MATCH_COMPLETE'):
        lua.eval('fire')(event)
    assert lua.eval('kinds()') == 'battleground'
    assert lua.eval('__requests') == 1
    stats = lua.eval('character().events[1].data.stats')
    assert dict(stats) == dict(killing_blows=12, honorable_kills=40, deaths=3,
                               honor=250, damage=123456, healing=7890)
    assert lua.eval('WoWStatusPopups.eventText(character().events[1])') == EXPECTED
    assert lua.eval('WoWStatusProgress.totalDeaths(character())') == 0


def test_scoreboard_stats_reach_friends_popup_log_and_quiet_catchup():
    from test_journal import mesh
    own, friend, late = scoreboard_player(), player('Thora'), player('Eldrin')
    finish(own)
    deliver_popup(own, friend)
    assert friend.eval('WoWStatusLevelPopup.message.text') == 'Mira — Won Warsong Gulch'
    detail = friend.eval('WoWStatusLevelPopup.detail.text')
    assert detail == 'Killing blows: 12 · HK: 40 · Deaths: 3\nHonor: 250 · Damage: 123456 · Healing: 7890'
    assert friend.eval('WoWStatusJournal.entries()[1].text') == EXPECTED
    friend.execute('''
        local methods=getmetatable(WoWStatusLevelPopup).__index
        function methods:SetMaxLines(value) self.maxLines=value end
        SlashCmdList.WOWSTATUS("activity")
        assert(WoWStatusActivityLog.rows[1].flavour.maxLines==2)
    ''')
    assert friend.eval('WoWStatusActivityLog.rows[1].flavour.text') == detail
    late.eval('WoWStatusJournal.sync')()
    mesh({'Thora': friend, 'Eldrin': late})
    assert late.eval('WoWStatusJournal.entries()[1].text') == EXPECTED
    assert late.eval('WoWStatusJournal.entries()[1].id') == friend.eval('WoWStatusJournal.entries()[1].id')
    assert late.eval('WoWStatusLevelPopup') is None
    friend.execute('WoWStatusLocale.set("nn"); WoWStatusJournal.redraw()')
    shown = friend.eval('WoWStatusActivityLog.rows[1].flavour.text')
    assert 'Drap: 12' in shown and 'Dødsfall: 3' in shown and 'Skade: 123456' in shown and 'Læking: 7890' in shown


def test_delayed_scoreboard_has_a_bounded_wait_and_missing_fields_are_unknown():
    lua = scoreboard_player()
    lua.execute('__ready=false')
    finish(lua)
    assert lua.eval('kinds()') == ''
    clock(lua, 12)
    lua.execute('__ready=true;fire("UPDATE_BATTLEFIELD_SCORE")')
    assert lua.eval('kinds()') == 'battleground'
    assert lua.eval('WoWStatusJournal.entries()[1].text') == EXPECTED
    assert lua.eval('__requests') == 1
    # A later match with no readable scoreboard still gets its plain result.
    lua.execute('__instance=nil;fire("PLAYER_ENTERING_WORLD");__ready=false')
    finish(lua)
    clock(lua, 16)
    lua.eval('WoWStatusBattlegrounds.update')()
    assert lua.eval('kinds()') == 'battleground,battleground'
    assert lua.eval('WoWStatusPopups.eventText(character().events[2])') == 'Won Warsong Gulch'
    lua.execute('__ready=true;fire("UPDATE_BATTLEFIELD_SCORE")')
    assert lua.eval('kinds()') == 'battleground,battleground'


def test_leaving_before_the_scoreboard_arrives_keeps_one_result_and_resets():
    lua = scoreboard_player()
    lua.execute('__ready=false')
    finish(lua)
    lua.execute('__instance=nil;fire("PLAYER_ENTERING_WORLD")')
    assert lua.eval('kinds()') == 'battleground'
    lua.execute('__ready=true')
    finish(lua)
    assert lua.eval('kinds()') == 'battleground,battleground'


def test_modern_scoreboard_guards_secret_missing_and_bad_values():
    lua = scoreboard_player()
    lua.execute('''
        __secret={}
        function issecretvalue(value) return rawequal(value,__secret) end
        C_PvP={GetScoreInfoByPlayerGuid=function(guid)
            assert(guid==UnitGUID("player"))
            return {killingBlows=0,honorableKills=__secret,deaths=2,honorGained=-1,
                damageDone=__secret,healingDone=0/0}
        end}
    ''')
    finish(lua)
    assert lua.eval('kinds()') == ''
    clock(lua, 14)
    lua.eval('WoWStatusBattlegrounds.update')()
    assert dict(lua.eval('character().events[1].data.stats')) == dict(killing_blows=0, deaths=2)
    text = lua.eval('WoWStatusJournal.entries()[1].text')
    assert text == 'Won Warsong Gulch (KB 0, HK -, deaths 2, honor -, dmg -, heal -)'
    assert lua.eval('WoWStatusJournal.validText')("battleground", text)


def test_pvp_choice_stops_sharing_receiving_and_recovering_scoreboard_results():
    own, friend = scoreboard_player(), player('Thora')
    friend.execute('character().settings.in_game.pvp=false')
    finish(own)
    deliver_popup(own, friend)
    assert friend.eval('#WoWStatusJournal.entries()') == 0
    assert friend.eval('WoWStatusLevelPopup') is None
    own.execute('__instance=nil;fire("PLAYER_ENTERING_WORLD");character().settings.in_game.pvp=false;__sent={}')
    finish(own)
    assert own.eval('#__sent') == 0


def test_score_text_is_bounded_without_cutting_numbers_or_utf8_names():
    lua = player()
    data = lua.table_from(dict(name='É' * 40, won=True, stats=lua.table_from(dict(
        killing_blows=99999, honorable_kills=99999, deaths=99999, honor=9999999,
        damage=9999999999999, healing=9999999999999))))
    text = lua.eval('WoWStatusBattlegrounds.text')(data)
    assert len(text.encode('utf-8')) <= 120
    assert '9999999999999' in text and text.endswith('9999999999999)')
    assert lua.eval('WoWStatusJournal.validText')('battleground', text)
    for bad in (text.replace('KB 99999', 'KB 100000'), text.replace('HK 99999', 'HK -2'),
                text.replace('deaths 99999', 'deaths 099999'), text[:-2], text + ' FREE GOLD'):
        assert not lua.eval('WoWStatusJournal.validText')('battleground', bad)


@pytest.mark.parametrize('edition', ['vanilla', 'tbc', 'forever', 'retail'])
def test_each_edition_can_read_public_scoreboard_totals(edition):
    from test_addon import STUBS, make_lua
    from test_forever import forever_runtime
    from test_retail import retail_runtime
    from test_tbc import tbc_runtime
    if edition == 'vanilla':
        lua = make_lua(STUBS.replace('return "Thora" end', 'return "Mira" end'))
    elif edition == 'tbc':
        lua = tbc_runtime('Mira')
    elif edition == 'forever':
        lua = forever_runtime('Mira')
        lua.eval('fire')('PLAYER_LOGIN')
    else:
        lua = retail_runtime('Mira')
    lua.execute(BG + SCORES + '''
        C_PvP={GetScoreInfoByPlayerGuid=function(guid)
            assert(guid==UnitGUID("player"))
            return {killingBlows=12,honorableKills=40,deaths=3,honorGained=250,
                damageDone=123456,healingDone=7890}
        end}
    ''')
    finish(lua)
    assert lua.eval('kinds()') == 'battleground'
    assert lua.eval('WoWStatusJournal.entries()[1].text') == EXPECTED


def test_bad_or_missing_scoreboard_apis_leave_a_plain_result_without_errors():
    lua = scoreboard_player()
    lua.execute('''
        function GetNumBattlefieldScores() error("not available") end
        C_PvP={GetScoreInfoByPlayerGuid=function() error("restricted") end}
        function RequestBattlefieldScoreData() error("not available") end
    ''')
    finish(lua)
    clock(lua, 14)
    lua.eval('WoWStatusBattlegrounds.update')()
    assert lua.eval('WoWStatusJournal.entries()[1].text') == 'Won Warsong Gulch'
