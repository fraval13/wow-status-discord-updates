"""'Firsts' medals for the first player to reach a milestone (#65)."""
from test_journal import actor, clock, deliver_popup, mesh

ENTRY = '''
function put(id, sender, kind, at, fields)
    local e = {id=id, client=WoWStatusAdapter.client_id, sender=sender, kind=kind, at=at, text=kind, groups={}, origin="catchup"}
    for k, v in pairs(fields or {}) do e[k] = v end
    return e
end
'''


def holder(lua, key):
    return lua.eval(f'(function() local r = WoWStatusFirsts.compute(WoWStatusJournal.entries()); '
                    f'return r["{key}"] and r["{key}"].sender end)()')


def test_order_is_by_time_then_event_id():
    lua = actor('Thora')
    lua.execute(ENTRY)
    lua.execute('''
        local list = {
            put("b", "Bob-TestRealm", "level", 100, {level=10}),
            put("a", "Alice-TestRealm", "level", 100, {level=10}),
            put("c", "Cid-TestRealm", "level", 50, {level=20}),
            put("d", "Dee-TestRealm", "death", 70),
            put("e", "Eve-TestRealm", "death", 60),
            put("f", "Fay-TestRealm", "loot", 10, {quality=3, item_id=1, class_id=4, equip_loc="INVTYPE_CHEST"}),
            put("g", "Gus-TestRealm", "loot", 20, {quality=4, item_id=2, class_id=4, equip_loc="INVTYPE_CHEST"}),
            put("h", "Hal-TestRealm", "profession", 5, {text="Tailoring: Expert (225 max)"}),
            put("i", "Ivy-TestRealm", "profession", 9, {text="Mining: Artisan (300 max)"}),
        }
        local r = WoWStatusFirsts.compute(list)
        assert(r["level:10"].sender == "Alice-TestRealm")   -- tie: smaller ID
        assert(r["level:20"].sender == "Cid-TestRealm")
        assert(r.death.sender == "Eve-TestRealm")
        assert(r.epic.sender == "Gus-TestRealm")
        assert(r.artisan.sender == "Ivy-TestRealm")
        assert(r.dungeon == nil and r.mount == nil)
        -- The same entries in any order give the same result.
        local reversed = {}
        for i = #list, 1, -1 do table.insert(reversed, list[i]) end
        local again = WoWStatusFirsts.compute(reversed)
        for key, e in pairs(r) do assert(again[key].id == e.id) end
    ''')


def test_live_first_is_announced_once_after_its_update():
    own, friend = actor('Mira'), actor('Thora')
    clock(own, 10)
    clock(friend, 10)
    own.eval('fire')('PLAYER_DEAD')
    deliver_popup(own, friend)
    assert holder(friend, 'death') == 'Mira-TestRealm'
    headings = []
    for at in (11, 18, 25):
        clock(friend, at)
        friend.eval('WoWStatusPopups.tick')()
        headings.append(friend.eval('WoWStatusLevelPopup.heading.text'))
    assert headings == ['A FRIEND HAS FALLEN', 'A NEW FIRST!', 'A NEW FIRST!']
    assert friend.eval('WoWStatusLevelPopup.message:GetText()') == 'Mira — First in the group to die!'
    # The sender gets no popup for their own First.
    assert own.eval('WoWStatusLevelPopup') is None


def test_late_recovered_entry_takes_the_medal_quietly():
    clients = {'Mira': actor('Mira'), 'Thora': actor('Thora'), 'Eldrin': actor('Eldrin')}
    for lua in clients.values():
        clock(lua, 10)
    # Eldrin died first while Thora was not connected to him.
    clients['Eldrin'].eval('fire')('PLAYER_DEAD')
    clock(clients['Mira'], 20)
    clients['Mira'].eval('fire')('PLAYER_DEAD')
    deliver_popup(clients['Mira'], clients['Thora'])
    thora = clients['Thora']
    assert holder(thora, 'death') == 'Mira-TestRealm'
    before = thora.eval('#__frames')
    mesh(clients, start=30)
    assert holder(thora, 'death') == 'Eldrin-TestRealm'
    assert thora.eval('WoWStatusDB.firsts.holders.death') == thora.eval(
        '(function() for _, e in ipairs(WoWStatusJournal.entries()) do '
        'if e.sender == "Eldrin-TestRealm" and e.kind == "death" then return e.id end end end)()')
    # Recovered entries never announce.
    for at in range(40, 80, 7):
        clock(thora, at)
        thora.eval('WoWStatusPopups.tick')()
        assert 'Eldrin' not in (thora.eval('WoWStatusLevelPopup.message:GetText()') or '')
    assert before > 0


def test_existing_log_is_seeded_without_popups():
    lua = actor('Thora')
    lua.execute(ENTRY)
    lua.execute('''
        WoWStatusDB.firsts = nil
        table.insert(WoWStatusDB.journal.entries, put("x", "Bob-TestRealm", "death", time(), {origin="live"}))
        WoWStatusFirsts.update()
        assert(WoWStatusDB.firsts.initialized and WoWStatusDB.firsts.holders.death == "x")
        WoWStatusPopups.tick()
        assert(WoWStatusLevelPopup == nil)
    ''')


def test_records_page_lists_every_medal():
    lua = actor('Thora')
    lua.execute(ENTRY)
    lua.execute('''
        table.insert(WoWStatusDB.journal.entries, put("x", "Bob-TestRealm", "dungeon", 100, {text="First clear: The Deadmines"}))
        SlashCmdList.WOWSTATUS("records")
        assert(WoWStatusMainWindow.active() == "records")
        local rows = WoWStatusRecordsPage.rows
        assert(#rows == #WoWStatusFirsts.medals())
        local found
        for _, row in ipairs(rows) do
            if row.text:find("First dungeon clear", 1, true) then found = row.text end
        end
        assert(found:find("Bob", 1, true))
        assert(rows[1].text:find("nobody yet", 1, true))
    ''')
