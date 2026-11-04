"""Popups show only addon-produced text from group peers, a few per sender (issue #8)."""
import pytest
from test_addon import FRIEND_STUBS, STUBS, make_lua
from test_journal import actor, clock
from test_retail import retail_runtime

from wow_status.group_routing import group_key

CHANNEL = 'WStatus' + group_key('navsquad')


def hexed(text):
    return text.encode('utf-8').hex()


def popup_text(lua):
    return lua.eval('WoWStatusLevelPopup and WoWStatusLevelPopup.message.text or ""')


def joined(lua):
    lua.eval('WoWStatusGroups.update')('navsquad', '')
    return lua


def test_member_cannot_push_arbitrary_text_as_introduction():
    # The issue's reproduction, verbatim.
    receiver = actor('Mira')
    clock(receiver, 10)
    group = receiver.eval('function() for id in pairs(character().group_ids) do return id end end')()
    client = receiver.eval('WoWStatusAdapter.client_id')
    packet = f'{group} WSTATUS4 {client} introduction 1793000010 x-1 FREE GOLD - whisper me for 10k'
    receiver.eval('fire')('CHAT_MSG_ADDON', 'WoWStatus', packet, 'WHISPER', 'Stranger-TestRealm')
    shown = receiver.eval('WoWStatusLevelPopup and WoWStatusLevelPopup.message.text or ""')
    assert 'FREE GOLD' not in shown


# (kind, packet version, the text the addon itself produces, forged texts)
TEMPLATES = [
    ('mount', 4, 'First mount: Brown Horse',
     ['FREE GOLD - whisper me for 10k', 'First mount:  ', 'First mount ride recorded! FREE GOLD']),
    ('mount', 4, 'First mount ride recorded!', ['First mount']),
    ('reputation', 4, 'Exalted with Ironforge',
     ['FREE GOLD - whisper me for 10k', 'Friendly with Ironforge', 'Exalted with  ']),
    ('unlock', 4, 'Unlocked Defensive Stance', ['FREE GOLD - whisper me for 10k', 'Unlocked ']),
    ('pvp', 4, 'Promoted to Sergeant', ['FREE GOLD - whisper me for 10k', 'Reached honor level 5']),
    ('zone', 3, 'Entered Stranglethorn Vale', ['FREE GOLD whisper me for 10k', 'Entered ']),
    ('profession', 3, 'Learned Blacksmithing (Apprentice)', ['FREE GOLD whisper me', 'Learned  ']),
    ('profession', 3, 'Tailoring: Expert (225 max)', ['Tailoring: FREE GOLD (225 max)', 'FREE: GOLD']),
]


@pytest.mark.parametrize('kind, version, valid, forged', TEMPLATES)
def test_each_kind_accepts_only_its_template(kind, version, valid, forged):
    lua = joined(make_lua())
    lua.execute('__combat=true')  # Keep everything queued so the log shows what was accepted.
    receive = lua.eval('WoWStatusPopups.receive')

    def packet(text, nonce):
        body = text if version == 4 else hexed(text)
        return f'WSTATUS{version} classic-era {kind} 1793000000 {nonce} {body}'

    for i, text in enumerate(forged):
        assert not receive(packet(text, f'forged-{i}'), 'Eldrin-TestRealm', CHANNEL)
    assert lua.eval('#WoWStatusDB.popups.activity') == 0
    assert receive(packet(valid, 'real'), 'Eldrin-TestRealm', CHANNEL)
    assert lua.eval('WoWStatusDB.popups.activity[1].text') == valid
    # Forged text from a member raises the existing invalid-data warning first.
    lua.execute('__combat=false; WoWStatusPopups.tick()')
    assert popup_text(lua) == 'Eldrin is a really bad boy, shame on you!'
    lua.execute('function time() return 1793000007 end; WoWStatusPopups.tick()')
    assert popup_text(lua) == f'Eldrin — {valid}'


def test_retail_pvp_accepts_only_honor_levels_in_range():
    lua = retail_runtime()
    lua.eval('WoWStatusGroups.update')('navsquad', '')
    lua.execute('__combat=true')
    receive = lua.eval('WoWStatusPopups.receive')
    for i, text in enumerate(['Promoted to Sergeant', 'Reached honor level 0', 'Reached honor level 012',
                              'Reached honor level 10001', 'Reached honor level 5 FREE GOLD']):
        assert not receive(f'WSTATUS4 retail pvp 1793000000 bad-{i} {text}', 'Eldrin-TestRealm', CHANNEL)
    assert receive('WSTATUS4 retail pvp 1793000000 good Reached honor level 101', 'Eldrin-TestRealm', CHANNEL)
    assert lua.eval('#WoWStatusDB.popups.activity') == 1


MILESTONE_STUBS = '''
    __standing=5;__collected=false;__known={};__rank=0
    C_Reputation={GetNumFactions=function() return 1 end,
        GetFactionDataByIndex=function() return {name="Ironforge",reaction=__standing,factionID=47} end}
    C_MountJournal={GetMountIDs=function() return {1} end,
        GetMountInfoByID=function() return "Brown Horse",458,1,false,true,1,false,false,nil,false,__collected end}
    function IsSpellKnown(id) return __known[id]==true end
    function GetSpellInfo(id) return ({[71]="Defensive Stance",[2458]="Berserker Stance"})[id] end
    function UnitPVPRank() return __rank end
    function GetPVPRankInfo(rank) return rank>0 and "Sergeant" or "Unranked",rank end
'''


def test_milestones_from_a_real_sender_still_show():
    sender = joined(make_lua(STUBS + MILESTONE_STUBS))
    receiver = joined(make_lua(FRIEND_STUBS))
    sender.execute('''
        __standing=6;fire("UPDATE_FACTION")
        __collected=true;fire("NEW_MOUNT_ADDED",1)
        __known[71]=true;fire("SPELLS_CHANGED")
        __rank=6;fire("PLAYER_PVP_RANK_CHANGED")
        for i=1,8 do local now=1793000000+i; function time() return now end; WoWStatusPopups.tick() end
    ''')
    packets = [sender.eval(f'__sent[{i}].text') for i in range(1, sender.eval('#__sent') + 1)]
    assert len(packets) == 4
    for packet in packets:
        receiver.eval('fire')('CHAT_MSG_ADDON', 'WoWStatus', packet, 'WHISPER', 'Thora-TestRealm')
    texts = [receiver.eval(f'WoWStatusDB.popups.activity[{i}].text') for i in range(1, 5)]
    assert sorted(texts) == ['First mount: Brown Horse', 'Honored with Ironforge',
                             'Promoted to Sergeant', 'Unlocked Defensive Stance']
    assert receiver.eval('#WoWStatusJournal.entries()') == 4
    assert popup_text(receiver).startswith('Thora — ')
    assert receiver.eval('WoWStatusDB.popups.last_receive.state') == 'queued'


def test_sender_does_not_send_text_receivers_would_reject():
    lua = joined(make_lua())
    lua.execute('''
        local ids = {}
        for id in pairs(character().group_ids) do ids[id] = true end
        WoWStatusPopups.broadcast(character(), {id="pvp-1", kind="pvp", at=time(), group_ids=ids,
            data={text="Won a duel"}})
    ''')
    assert lua.eval('#__sent') == 0


def test_sender_outside_the_roster_is_held_then_rejected():
    lua = joined(make_lua(STUBS.replace('__peers = {"Eldrin-TestRealm"}', '__peers = {}')))
    receive = lua.eval('WoWStatusPopups.receive')
    assert not receive('WSTATUS2 classic-era LEVEL 3 1793000000 stranger-3', 'Stranger-TestRealm', CHANNEL)
    assert not receive(f'WSTATUS3 classic-era zone 1793000000 stranger-4 {hexed("Entered Elwynn Forest")}',
                       'Stranger-TestRealm', CHANNEL)
    assert lua.eval('WoWStatusDB.popups.last_receive.state') == 'verifying_sender'
    assert lua.eval('#WoWStatusDB.popups.activity') == 0
    assert lua.eval('#WoWStatusJournal.entries()') == 0
    lua.execute('function time() return 1793000016 end; WoWStatusPopups.tick()')
    assert lua.eval('WoWStatusDB.popups.last_receive.state') == 'rejected_unknown_sender'
    assert lua.eval('WoWStatusLevelPopup') is None
    assert lua.eval('#WoWStatusDB.popups.activity') == 0
    assert lua.eval('#WoWStatusJournal.entries()') == 0
    assert lua.eval('WoWStatusDB.popups.level_claims["stranger-testrealm"]') is None


def test_member_who_just_joined_is_shown_once_the_roster_lists_them():
    lua = joined(make_lua())
    receive = lua.eval('WoWStatusPopups.receive')
    assert not receive('WSTATUS4 classic-era introduction 1793000000 new-1 Joined the WoW Status group',
                       'Mira-TestRealm', CHANNEL)
    assert lua.eval('WoWStatusDB.popups.last_receive.state') == 'verifying_sender'
    lua.execute('WoWStatusPopups.tick()')
    assert lua.eval('WoWStatusLevelPopup') is None
    # The roster read completes a few seconds later and lists the new member.
    lua.execute('''
        table.insert(__peers,"Mira-TestRealm")
        function time() return 1793000005 end
        WoWStatusPopups.tick()
    ''')
    assert popup_text(lua) == 'Mira — Joined the WoW Status group'
    assert lua.eval('#WoWStatusJournal.entries()') == 1


def test_member_swap_with_same_roster_size_rereads_the_roster():
    lua = joined(make_lua())
    assert list(lua.eval('WoWStatusPopups.peers')(group_key('navsquad')).values()) == ['Eldrin-TestRealm']
    lua.execute('__peers={"Mira-TestRealm"}')  # Eldrin left and Mira joined: same count, cache still fresh.
    assert lua.eval('WoWStatusPopups.receive')('WSTATUS2 classic-era LEVEL 5 1793000000 mira-5',
                                               'Mira-TestRealm', CHANNEL)
    assert popup_text(lua) == 'Mira reached level 5!'


def test_one_sender_can_queue_only_four_updates():
    lua = joined(make_lua(STUBS.replace('__peers = {"Eldrin-TestRealm"}',
                                        '__peers = {"Eldrin-TestRealm","Mira-TestRealm"}')))
    lua.execute('__combat=true')
    receive = lua.eval('WoWStatusPopups.receive')
    for level in range(2, 8):
        accepted = receive(f'WSTATUS2 classic-era LEVEL {level} 1793000000 flood-{level}', 'Eldrin-TestRealm', CHANNEL)
        assert accepted is (level < 6)
    assert lua.eval('WoWStatusDB.popups.last_receive.state') == 'sender_queue_full'
    assert lua.eval('#WoWStatusDB.popups.activity') == 4
    # Another member is unaffected, and a rejected level can still be shown later.
    assert receive('WSTATUS2 classic-era LEVEL 9 1793000000 mira-9', 'Mira-TestRealm', CHANNEL)
    lua.execute('__combat=false; WoWStatusPopups.tick()')
    assert popup_text(lua) == 'Eldrin reached level 2!'
    assert receive('WSTATUS2 classic-era LEVEL 7 1793000000 flood-7b', 'Eldrin-TestRealm', CHANNEL)


def test_updates_waiting_for_the_roster_count_toward_the_sender_cap():
    lua = joined(make_lua(STUBS.replace('__peers = {"Eldrin-TestRealm"}', '__peers = {}')))
    receive = lua.eval('WoWStatusPopups.receive')
    for level in range(2, 8):
        receive(f'WSTATUS2 classic-era LEVEL {level} 1793000000 wait-{level}', 'Stranger-TestRealm', CHANNEL)
    assert lua.eval('WoWStatusDB.popups.last_receive.state') == 'rejected_unknown_sender'
    lua.execute('''
        __peers={"Stranger-TestRealm"}
        function time() return 1793000001 end
        WoWStatusPopups.tick()
    ''')
    assert lua.eval('#WoWStatusDB.popups.activity') == 4


@pytest.mark.parametrize('kind, text', [
    ('profession', 'Кузнечное дело: Journeyman (150 m...'),
    ('profession', 'Инженерное дело: Journ...'),
    ('profession', 'Инженерное дело: ...'),
    ('profession', 'Tailoring: New profession rank (? max)'),
    ('zone', 'Entered Les Tarides du Nord, très loin d’ici...'),
    ('loot', 'Equipped Robe of the Archmage'),
    ('loot', 'Looted Robe of the Archmage'),
    ('dungeon', 'First clear: The Deadmines'),
    ('quest', 'Completed 200 quests!'),
    ('death', 'Total deaths: 3'),
    ('introduction', 'Joined the WoW Status group'),
])
def test_valid_texts_include_cut_and_localized_forms(kind, text):
    lua = make_lua()
    assert lua.eval('WoWStatusJournal.validText')(kind, text) is True


@pytest.mark.parametrize('kind, text', [
    ('profession', 'Кузнечное дело: Journeyman (150 max) FREE GOLD'),
    ('profession', 'FREE GOLD whisper me for 10k gold now...'),
    ('profession', 'Tailoring: Grandmaster (450 max)'),
    ('loot', 'Equipped '),
    ('dungeon', 'First clear:'),
    ('quest', 'Completed many quests!'),
    ('mount', 'first mount: Brown Horse'),
    ('discovery', 'Anything'),
])
def test_invalid_texts_are_rejected(kind, text):
    lua = make_lua()
    assert lua.eval('WoWStatusJournal.validText')(kind, text) is False


def test_cut_russian_profession_rank_up_roundtrips():
    sender = joined(make_lua(STUBS + '''
        __cap=75
        function GetSpellInfo(id) if id==4036 then return "Инженерное дело" end end
        function GetNumSkillLines() return 1 end
        function GetSkillLineInfo() return "Инженерное дело",false,false,1,0,0,__cap end
    '''))
    receiver = joined(make_lua(FRIEND_STUBS))
    sender.execute('__cap=150;fire("SKILL_LINES_CHANGED")')
    packet = sender.eval('__sent[1].text')
    detail = bytes.fromhex(packet.rsplit(' ', 1)[1]).decode('utf-8')
    assert detail.endswith('...') and len(detail.encode()) <= 48
    receiver.eval('fire')('CHAT_MSG_ADDON', 'WoWStatus', packet, 'WHISPER', 'Thora-TestRealm')
    assert popup_text(receiver) == 'Thora — ' + detail
