"""The Labs bingo board draws and fills locally from the shared journal."""
from test_journal import actor


def test_weekly_bingo_is_deterministic_fills_and_opens_from_labs():
    lua = actor('Thora')
    lua.execute("""
        local B, F, J = WoWStatusBingo, WoWStatusFeatures, WoWStatusJournal
        local id = next(character().group_ids)
        local first, last = WoWStatusFirsts.weekRange()
        local nextWeek = WoWStatusFirsts.weekRange(-1)
        local board, same, nextBoard = B.draw(id, first), B.draw(id, first), B.draw(id, nextWeek)
        local seen, different = {}, false
        assert(#board == 25)
        for i, square in ipairs(board) do
            assert(square == same[i] and not seen[square])
            seen[square], different = true, different or square ~= nextBoard[i]
        end
        assert(different)
        J.visible = function(e) return not e.hidden end
        local at = WoWStatusSafe.now()
        local entries = {
            {id="a", sender="Ada-TestRealm", kind="level", level=20, groups={[id]=true}, at=at},
            {id="b", sender="Bee-TestRealm", kind="level", level=20, groups={[id]=true}, at=at-1, hidden=true},
            {id="c", sender="Cat-TestRealm", kind="level", level=20, groups={[id]=true}, at=at-8*86400},
            {id="d", sender="Dot-TestRealm", kind="level", level=20, groups={}, at=at-1},
        }
        local filled = B.fill({{"level"}}, id, first, last, entries)
        assert(filled[1] == entries[1])
        assert(not B.won(filled))
        assert(B.won({true,true,true,true,true}))
        assert(B.won({[1]=true,[7]=true,[13]=true,[19]=true,[25]=true}))
        assert(B.won({[5]=true,[9]=true,[13]=true,[17]=true,[21]=true}))

        SlashCmdList.WOWSTATUS("labs")
        local row = WoWStatusLabsPage.rows[1]
        assert(row.id == "weeklyBingo" and not row.configure)
        row:SetChecked(true); row.OnClick(row)
        row.configure.OnClick(row.configure)
        local page = WoWStatusMainWindow.show("bingo")
        assert(#page.cells == 25 and WoWStatusMainWindow.active() == "bingo")
        assert(not WoWStatusMainWindow.pages().bingo)
        page.cells[1].OnClick(page.cells[1])
        assert(page.detail:GetText() ~= "")
    """)


def test_weekly_bingo_announces_new_win_once_and_catchup_stays_quiet():
    lua = actor('Thora')
    lua.execute("""
        local B, F, J = WoWStatusBingo, WoWStatusFeatures, WoWStatusJournal
        local id = next(character().group_ids)
        local at = WoWStatusSafe.now()
        local entries, board, notices = {}, {}, 0
        J.visible = function() return true end
        J.entries = function() return entries end
        B.draw = function() return board end
        WoWStatusPopups.notice = function(item)
            assert(item.text == "Bingo!" and item.kind == "first")
            notices = notices + 1
        end
        F.set("weeklyBingo", true)
        local function add(level, origin)
            local entry = {id=tostring(level), level=level, kind="level", sender="Ada-TestRealm",
                origin=origin, groups={[id]=true}, at=at}
            entries[#entries+1] = entry
            B.update(entry)
        end
        for level = 1, 5 do
            board[level] = {"level", "", function(e) return e.level == level end}
        end
        add(1, "catchup")
        add(2, "mine")
        add(3, "live")
        add(4, "live")
        assert(notices == 0)
        add(5, "live")
        add(6, "live")
        assert(notices == 1)
        at = at + 7 * 86400
        WoWStatusSafe.now = function() return at end
        entries = {}
        for level = 1, 5 do add(level, "catchup") end
        add(6, "live")
        assert(notices == 1)
    """)
