"""Quiet quest totals between milestones, including privacy and offline alts."""
import pytest
from test_profile import open_profile
from test_roster import pair, pump


def reported(lua, total):
    lua.execute(f'''
        __completed={total}
        C_QuestLog={{GetAllCompletedQuestIDs=function()
            local ids={{}}; for id=1,__completed do ids[id]=id end; return ids
        end}}
        fire("QUEST_LOG_UPDATE")
    ''')


def row(lua, name):
    return next(r for group in lua.eval('WoWStatusRoster.groups()').values()
                for r in group.rows.values() if r.name == name)


def board(lua, name):
    return next(r for r in lua.eval('WoWStatusRoster.leaderboard(next(character().group_ids))').values()
                if r.name == name)


def test_exact_counts_replace_milestones_and_update_an_open_profile_quietly():
    mira, thora = pair()
    reported(mira, 247)
    sent = pump(mira, thora)
    assert any(line.endswith('Mira-TestRealm 247 game_api') for line in sent if line.startswith('O '))
    thora.execute('''
        WoWStatusJournal.received({sender="Mira-TestRealm",nonce="1-1-a",kind="quest",
            text="Completed 200 quests!",at=time(),group_id=next(character().group_ids)})
    ''')
    assert board(thora, 'Mira-TestRealm').quests == 247
    view = open_profile(thora, 'Mira')
    assert 'Quests:|r 247' in ' '.join(c.text for c in view.stats.cells.values())
    view.scroll.SetVerticalScroll(view.scroll, 120)
    reported(mira, 248)
    sent = pump(mira, thora, start=130)
    assert sum(line.startswith('O ') for line in sent) == 1
    assert row(thora, 'Mira-TestRealm').quests == 248
    assert board(thora, 'Mira-TestRealm').quests == 248
    assert 'Quests:|r 248' in ' '.join(c.text for c in view.stats.cells.values())
    assert view.scroll.GetVerticalScroll(view.scroll) == 120
    assert mira.eval('#character().events') == 0
    assert not any(line.startswith('O ') for line in pump(mira, thora, start=160))


def test_unique_turnins_update_locally_and_send_at_most_once_per_thirty_seconds():
    mira, thora = pair()
    pump(mira, thora)
    mira.execute('fire("QUEST_TURNED_IN", 1); fire("QUEST_TURNED_IN", 1)')
    assert row(mira, 'Mira-TestRealm').quests == 1
    assert board(mira, 'Mira-TestRealm').quests == 1
    assert not any(line.startswith('O ') for line in pump(mira, thora, start=110))
    assert row(thora, 'Mira-TestRealm').quests == 0
    sent = pump(mira, thora, start=130)
    assert sum(line.startswith('O ') for line in sent) == 1
    assert row(thora, 'Mira-TestRealm').quests == 1
    assert mira.eval('#character().events') == 0


def test_field_privacy_is_rechecked_after_a_total_was_queued():
    mira, thora = pair()
    reported(mira, 247)
    pump(mira, thora)
    reported(mira, 248)
    mira.execute('__restricted=true; __mono=130; WoWStatusRoster.tick()')
    mira.execute('character().settings.fields.quests=false; __restricted=false')
    sent = pump(mira, thora, start=131)
    quest_packets = [line for line in sent if line.startswith('O ')]
    assert quest_packets and all(line.endswith('- -') for line in quest_packets)
    assert row(thora, 'Mira-TestRealm').quests is None
    assert row(thora, 'Mira-TestRealm').quests_source == 'private'
    assert board(thora, 'Mira-TestRealm').quests is None


@pytest.mark.parametrize('privacy', ['hidden', 'sharing', 'left'])
def test_queued_counts_do_not_send_after_withdrawing_a_character_or_group(privacy):
    mira, thora = pair()
    pump(mira, thora)
    reported(mira, 247)
    mira.execute('__restricted=true; __mono=130; WoWStatusRoster.tick()')
    actions = {
        'hidden': 'WoWStatusRoster.setHidden(character(),true)',
        'sharing': 'WoWStatusRoster.setSharing(false)',
        'left': 'WoWStatusGroups.update("", "")',
    }
    mira.execute(actions[privacy] + '; __restricted=false')
    assert not any(line.startswith('O ') for line in pump(mira, thora, start=131))


def test_offline_alts_keep_their_own_saved_total_in_lists_and_sync():
    mira, thora = pair()
    reported(mira, 247)
    mira.execute('''
        local alt=WoWStatusHistory.copy(character())
        alt.identity.name,alt.identity.guid="Ivy","Player-123-Ivy"
        alt.chat_name=nil
        alt.snapshot.quests_completed=83
        alt.snapshot.quests_source="tracked_since"
        WoWStatusDB.characters.alt=alt
    ''')
    assert board(mira, 'Ivy-TestRealm').quests == 83
    pump(mira, thora)
    assert row(thora, 'Ivy-TestRealm').quests == 83
    assert row(thora, 'Ivy-TestRealm').quests_source == 'tracked_since'
    assert board(thora, 'Mira-TestRealm').quests == 247
    thora.execute('''
        WoWStatusLocale.set("nn")
        SlashCmdList.WOWSTATUS("records")
        WoWStatusRecordsPage.viewBoard.OnClick()
    ''')
    quest_labels = [r.quests.text for r in thora.eval('WoWStatusRecordsPage.board').values()]
    assert '83 (spora)' in quest_labels and '247' in quest_labels


@pytest.mark.parametrize('value', ['-1 game_api', '1.5 game_api', '1e2 game_api',
                                  '1000000000000 game_api', '12 invented', '- game_api', '12 -'])
def test_invalid_totals_are_rejected_without_overwriting_a_good_count(value):
    mira, thora = pair()
    reported(mira, 247)
    pump(mira, thora)
    group = mira.eval('(next(character().group_ids))')
    pid = mira.eval('WoWStatusDB.roster.id')
    result = thora.eval('WoWStatusRoster.receive')(
        f'O {group} {pid} Mira-TestRealm {value}', 'Mira-TestRealm', 'WHISPER')
    assert result is False or result[0] is False
    assert row(thora, 'Mira-TestRealm').quests == 247


def test_zero_is_a_known_count_and_secret_values_do_not_leave_the_client():
    mira, thora = pair()
    pump(mira, thora)
    assert row(thora, 'Mira-TestRealm').quests == 0
    mira.execute('''
        __secret={}
        function issecretvalue(value) return value==__secret end
        character().snapshot.quests_completed=__secret
        assert(WoWStatusRoster.questLine(character())=="- -")
    ''')


def test_a_full_send_queue_eventually_delivers_to_every_member_without_repeats():
    mira, thora = pair()
    pump(mira, thora)
    mira.execute('''
        WoWStatusGroups.update("dawnwatch\\nExample Second Group", "Frank")
        WoWStatusRoster.init(WoWStatusDB,character())
        -- Isolate the quiet total queue from full-list and equipment work.
        WoWStatusRoster.scan=function() end
        WoWStatusRoster.statsLine=function() end
        WoWStatusEquipmentSync=nil
        WoWStatusPopups.peers=function()
            local names={};for n=1,200 do names[n]="Friend"..n.."-TestRealm" end;return names
        end
    ''')
    reported(mira, 247)
    before = mira.eval('#__sent')
    mira.execute('''
        for tick=300,900 do
            __mono=tick
            WoWStatusRoster.tick()
            assert(WoWStatusRoster.equipmentQueueSize()<=256)
        end
    ''')
    packets = [p for i, p in mira.eval('__sent').items()
               if i > before and p.prefix == 'WoWStatusChr' and p.text.startswith('O ')]
    assert len(packets) == 400
    assert len({(p.text.split()[1], p.target) for p in packets}) == 400
    assert all(len(p.text.encode()) <= 250 for p in packets)
