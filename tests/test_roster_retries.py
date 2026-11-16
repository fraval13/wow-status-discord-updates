"""Roster sends retain throttled messages and still honor privacy on retry."""
import pytest
from test_journal import clock
from test_roster import level_of, pair, pump


def clients(op='P', result='3'):
    own, friend = pair()
    own.globals().__operation = op
    own.execute('''
        function UnitXP() return 375 end
        function UnitXPMax() return 1000 end
        character().progress.professions={{key="alchemy", skill=75, max_skill=150}}
        character().snapshot.quests_completed=247
        character().snapshot.quests_source="game_api"
        WoWStatusRoster.observe(character())
        WoWStatusRoster.changed()
        __tries={}
        Enum={SendAddonMessageResult={Success=0, AddonMessageThrottle=3,
            ChannelThrottle=8, AddOnMessageLockdown=11, TargetOffline=12}}
        local send=C_ChatInfo.SendAddonMessage
        C_ChatInfo.SendAddonMessage=function(prefix, text, kind, target)
            if prefix=="WoWStatusChr" and text:sub(1,2)==__operation.." " then
                __tries[#__tries+1]={text=text, target=target, at=__mono}
                if #__tries==1 or __always then return __firstResult() end
            end
            send(prefix, text, kind, target)
            return 0
        end
    ''')
    own.execute(f'function __firstResult() return {result} end')
    return own, friend


@pytest.mark.parametrize('op', ['C', 'O', 'P', 'R', 'S', 'Y'])
def test_every_roster_message_retries_after_a_game_throttle(op):
    own, friend = clients(op)
    sent = pump(own, friend, start=1)
    attempts = own.eval('__tries')
    assert len(attempts) == 2
    assert attempts[1].text == attempts[2].text
    assert attempts[1].target == attempts[2].target == 'Thora-TestRealm'
    assert attempts[2].at - attempts[1].at >= 2
    assert sum(text == attempts[1].text for text in sent) == 1
    if op == 'P':
        assert level_of(friend, 'Mira-TestRealm') == (1, 375)


@pytest.mark.parametrize('result', ['3', '8', '11', 'false'])
def test_xp_retries_for_each_wait_result_including_legacy_false(result):
    own, friend = clients(result=result)
    pump(own, friend, start=1)
    assert own.eval('#__tries') == 2
    assert level_of(friend, 'Mira-TestRealm') == (1, 375)


def wait_for_first_attempt(own):
    for at in range(1, 20):
        clock(own, at)
        own.eval('WoWStatusRoster.tick')()
        if own.eval('#__tries') == 1:
            return at
    pytest.fail('the selected roster message was never attempted')


@pytest.mark.parametrize('privacy', ['stop_sharing', 'hide_character'])
def test_an_xp_retry_is_cancelled_when_the_player_stops_sharing(privacy):
    own, friend = clients()
    at = wait_for_first_attempt(own)
    if privacy == 'stop_sharing':
        own.execute('WoWStatusRoster.setSharing(false)')
    else:
        own.execute('WoWStatusRoster.setHidden(character(), true)')
    sent = pump(own, friend, start=at+1)
    assert own.eval('#__tries') == 1
    assert not any(text.startswith('P ') for text in sent)


@pytest.mark.parametrize('privacy', ['hidden', 'left_group', 'professions_off'])
def test_send_time_privacy_is_rechecked_for_a_retried_profession_line(privacy):
    own, friend = clients('Y')
    at = wait_for_first_attempt(own)
    if privacy == 'hidden':
        own.execute('character().hide_from_list=true')
    elif privacy == 'left_group':
        own.execute('character().group_ids={}; WoWStatusDB.account_groups={}')
    else:
        own.execute('character().settings.fields.professions=false')
    sent = pump(own, friend, start=at+1)
    assert own.eval('#__tries') == 1
    assert not any(text.startswith('Y ') for text in sent)


def test_a_retried_quest_total_is_rebuilt_from_the_current_privacy_settings():
    own, friend = clients('O')
    at = wait_for_first_attempt(own)
    assert own.eval('__tries[1].text').endswith('247 game_api')
    own.execute('character().settings.fields.quests=false')
    sent = pump(own, friend, start=at+1)
    assert own.eval('#__tries') == 2
    assert own.eval('__tries[2].text').endswith('- -')
    assert not any('247' in text for text in sent if text.startswith('O '))


def test_a_legacy_client_returning_false_does_not_hold_the_queue_forever():
    own, friend = clients(result='false')
    own.execute('__always=true')
    sent = pump(own, friend, start=1)
    assert own.eval('#__tries') == 2
    assert not any(text.startswith('P ') for text in sent)
    assert any(text.startswith('R ') for text in sent)


@pytest.mark.parametrize('result', ['9', '12', 'error("send failed")'])
def test_final_send_failures_do_not_retry_or_block_the_remaining_queue(result):
    own, friend = clients(result=result)
    sent = pump(own, friend, start=1)
    assert own.eval('#__tries') == 1
    assert not any(text.startswith('P ') for text in sent)
    assert any(text.startswith('R ') for text in sent)
