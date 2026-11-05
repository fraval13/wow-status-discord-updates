"""Session recaps in the activity log (#66)."""
from test_addon import STUBS, make_lua

RECAP = STUBS + '''
__now = 1793000000
function time() return __now end
function GetInstanceInfo() return "The Deadmines","party",1,"Normal",5,false,false,36 end
function GetInstanceLockTimeRemaining() return 0,false,1,1 end
function GetInstanceLockTimeRemainingEncounter() return "Boss",1,true end
function recaps()
    local found = {}
    for _, e in ipairs(WoWStatusJournal.entries()) do if e.kind == "recap" then table.insert(found, e) end end
    return found
end
'''


def relogin(lua, after):
    """Log out and, `after` seconds later, run the login step again on the saved character."""
    lua.execute(f'fire("PLAYER_LOGOUT"); __now = __now + {after}; WoWStatusRecaps.init(character())')
    return lua


def test_logout_and_later_login_writes_one_recap():
    lua = make_lua(RECAP)
    lua.execute('''
        character().session.start_level = 38
        fire("PLAYER_LEVEL_UP", 39); fire("PLAYER_LEVEL_UP", 40); fire("PLAYER_LEVEL_UP", 41)
        fire("LFG_COMPLETION_REWARD")
        fire("PLAYER_DEAD"); fire("PLAYER_ALIVE"); fire("PLAYER_DEAD")
        __now = __now + 3600
    ''')
    assert lua.eval('#recaps()') == 0
    later = relogin(lua, 7200)
    entries = later.eval('recaps()')
    assert len(entries) == 1
    text = entries[1].text
    assert text.endswith(': Thora went from 38 to 41, cleared The Deadmines, died twice.'), text
    assert text.split(':')[0] in ('Tonight', 'This morning', 'This afternoon')
    assert entries[1].owner and not later.eval('next(recaps()[1].groups)')
    assert entries[1].flavour


def test_reload_continues_the_session_without_a_recap():
    lua = make_lua(RECAP)
    lua.execute('fire("PLAYER_LEVEL_UP", 5)')
    again = relogin(lua, 20)
    assert again.eval('#recaps()') == 0
    assert again.eval('character().session.counts.level') == 1
    again.execute('fire("PLAYER_LEVEL_UP", 6)')
    final = relogin(again, 3600)
    assert final.eval('#recaps()') == 1
    assert 'reached level 6' in final.eval('recaps()[1].text') or 'went from' in final.eval('recaps()[1].text')
    # Another login does not write it again.
    assert relogin(final, 3600).eval('#recaps()') == 1


def test_nothing_happened_means_no_recap():
    lua = make_lua(RECAP)
    assert relogin(lua, 7200).eval('#recaps()') == 0


def test_thirty_idle_minutes_end_the_session():
    lua = make_lua(RECAP)
    lua.execute('''
        fire("PLAYER_DEAD")
        __now = __now + 1700; WoWStatusRecaps.tick(); assert(#recaps() == 0)
        __now = __now + 200; WoWStatusRecaps.tick(); assert(#recaps() == 1)
        assert(recaps()[1].text:find("Thora died once", 1, true))
        assert(character().session == nil)
        fire("PLAYER_ALIVE"); fire("PLAYER_DEAD")
        assert(character().session.counts.death == 1)
    ''')


def test_recaps_are_private_and_never_shared():
    lua = make_lua(RECAP)
    lua.execute('''
        local sent = #__sent
        fire("PLAYER_DEAD")
        WoWStatusRecaps.close(__now)
        assert(#recaps() == 1)
        for i = sent + 1, #__sent do assert(not __sent[i].text:find("recap", 1, true)) end
        -- A recap claimed by someone else is never accepted into the log.
        WoWStatusJournal.received({sender="Bob-TestRealm", nonce="x1", kind="recap", text="Tonight: Bob won"})
        assert(#recaps() == 1)
    ''')


def test_records_page_shows_recaps():
    lua = make_lua(RECAP)
    lua.execute('''
        fire("PLAYER_DEAD"); WoWStatusRecaps.close(__now)
        SlashCmdList.WOWSTATUS("records")
        local text = {}
        for _, row in ipairs(WoWStatusRecordsPage.recaps) do table.insert(text, row.text or "") end
        assert(table.concat(text, "\\n"):find("Thora died once", 1, true))
    ''')
