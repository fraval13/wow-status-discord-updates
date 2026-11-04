"""Retail API mocks for the separate 12.x client; not live-game certification."""
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from test_addon import STUBS, lupa

from wow_status.schema import ValidationError, validate

ROOT=Path(__file__).parents[1]


def retail_runtime(name='Thora',extra='', *, join_announcements=False):
    lua=lupa.LuaRuntime(encoding='utf-8', source_encoding='utf-8', unpack_returned_tuples=True)
    lua.execute(STUBS.replace('return "Thora" end',f'return "{name}" end')+'''
        WOW_PROJECT_MAINLINE=1;WOW_PROJECT_CAMELOT=18;WOW_PROJECT_ID=1
        __level=89;__honor=0
        function GetBuildInfo() return "12.1.5","70575","test",120105 end
        function UnitHonorLevel() return __honor end
        C_Item={GetItemInfo=GetItemInfo}
        GetItemInfo=nil;SendChatMessage=nil
        __secret={}
        function issecretvalue(v) return v==__secret end
    '''+extra)
    lua.globals().date=lambda fmt,at: datetime.fromtimestamp(at,timezone.utc).strftime(fmt.lstrip('!'))
    folder=ROOT/'addon/retail/WoWStatus'
    for line in (folder/'WoWStatus.toc').read_text(encoding='utf-8').splitlines():
        if line.strip() and not line.startswith('#'):
            lua.execute((folder/line.strip()).read_text(encoding='utf-8'))
    lua.eval('fire')('PLAYER_LOGIN')
    if not join_announcements:
        lua.execute('WoWStatusGroups.announce=nil')
    return lua


def test_retail_targets_12x_and_level_90_and_rejects_other_editions():
    lua=retail_runtime()
    lua.execute('''
        assert(character().identity.client=="retail")
        __level=90;fire("PLAYER_LEVEL_UP",90)
        assert(character().events[1].data.maximum and character().snapshot.level==90)
        __level=91;fire("PLAYER_LEVEL_UP",91)
        assert(#character().events==1 and WoWStatusAdapter.level()==nil)
        for _,id in ipairs({2,5,18,19}) do
            WOW_PROJECT_ID=id;assert(not WoWStatusAdapter.supported())
        end
        WOW_PROJECT_ID=1
        function GetBuildInfo() return "1.60.1","0","test",16001 end
        assert(not WoWStatusAdapter.supported())
    ''')


def test_retail_level_and_first_equip_roundtrip_have_separate_identity():
    own,friend=retail_runtime(),retail_runtime('Eldrin')
    for lua in (own,friend):
        lua.eval('WoWStatusGroups.update')('navsquad','')
    own.eval('fire')('PLAYER_LEVEL_UP',90)
    packet=own.eval('__sent[1].text')
    assert 'WSTATUS2 retail LEVEL 90' in packet
    friend.eval('fire')('CHAT_MSG_ADDON','WoWStatus',packet,'WHISPER','Thora-TestRealm')
    assert 'level 90!' in friend.eval('WoWStatusLevelPopup.message:GetText()')
    channel=friend.eval('function() for g in pairs(character().group_ids) do return WoWStatusGroups.channel(g) end end')()
    for client in ('classic-era','forever','tbc-anniversary'):
        assert not friend.eval('WoWStatusPopups.receive')(
            f'WSTATUS2 {client} LEVEL 60 1793000000 other','Thora-TestRealm',channel)
    own.execute('''
        __slot="|Hitem:123|h[Armor]|h";fire("PLAYER_EQUIPMENT_CHANGED",1)
        fire("PLAYER_EQUIPMENT_CHANGED",1)
        assert(#character().events==2 and character().events[2].data.first_equip)
        function time() return 1793000002 end
        WoWStatusPopups.tick()
    ''')
    packet=own.eval('__sent[2].text')
    assert 'WSTATUS7 retail loot' in packet
    friend.eval('fire')('CHAT_MSG_ADDON','WoWStatus',packet,'WHISPER','Thora-TestRealm')
    assert friend.eval('#WoWStatusJournal.entries()')==2


def test_retail_learns_owned_professions_without_classic_titles():
    lua=retail_runtime(extra='''
        __profession=false;__skill=1;__cap=100
        function GetProfessions() if __profession then return 1 end end
        function GetProfessionInfo(index) return "Inscription",1,__skill,__cap,1,0,773 end
        C_SkillInfo={GetSkillLineInfoByID=function() error("Classic skill query must not run") end}
    ''')
    lua.execute('''
        __profession=true;fire("SKILL_LINES_CHANGED")
        local event=character().events[1]
        assert(event.data.learned and not event.data.title)
        assert(WoWStatusPopups.eventText(event)=="Learned Inscription")
        assert(character().snapshot.professions[1].key=="inscription")
        __skill=2;fire("SKILL_LINES_CHANGED")
        __cap=150;fire("SKILL_LINES_CHANGED")
        assert(#character().events==1)
        assert(character().snapshot.professions[1].max_skill==150)
    ''')


def test_retail_honor_levels_support_values_over_100_and_stay_quiet_on_login():
    lua=retail_runtime(extra='__honor=100')
    lua.execute('''
        assert(#character().events==0)
        __honor=101;fire("HONOR_LEVEL_UPDATE")
        assert(#character().events==1)
        assert(character().events[1].data.text=="Reached honor level 101")
        fire("HONOR_LEVEL_UPDATE")
        assert(#character().events==1)
        __honor=__secret;fire("HONOR_LEVEL_UPDATE")
        assert(#character().events==1)
        assert(WoWStatusFeatures.discord==false)
    ''')


def test_retail_secret_identity_waits_and_message_restrictions_are_respected():
    lua=retail_runtime(extra='function UnitGUID() return __secret end')
    lua.execute('''
        assert(next(WoWStatusDB.characters)==nil)
        function UnitGUID() return "Player-retail" end
        fire("PLAYER_REGEN_ENABLED")
        assert(character().identity.guid=="Player-retail")
        C_ChatInfo.AreOutgoingAddonChatMessagesRestricted=function() return true end
        assert(WoWStatusAdapter.chatRestricted())
        C_ChatInfo.AreOutgoingAddonChatMessagesRestricted=function() return __secret end
        assert(WoWStatusAdapter.chatRestricted())
        C_ChatInfo.AreOutgoingAddonChatMessagesRestricted=function() return false end
        assert(not WoWStatusAdapter.chatRestricted())
        C_ChatInfo=nil
        assert(WoWStatusAdapter.chatRestricted() and WoWStatusAdapter.chatSender()==nil)
    ''')


def test_retail_protocol_accepts_90_and_rejects_91_and_keeps_character_namespaces(store,payload,clone):
    classic_id=store.ingest('owner',payload)['character_id']
    retail=clone(payload)
    retail['identity']['client']='retail'
    retail['snapshot']['level']=90
    retail['events'][1]['data']['level']=90
    assert validate(retail)['events'][1]['data']['maximum']
    assert store.ingest('owner',retail)['character_id']!=classic_id
    retail['events'][1]['data']['level']=91
    with pytest.raises(ValidationError):
        validate(retail)
    retail['settings'].setdefault('collection',dict(retail['settings']['announcements']))['pvp']=True
    retail['settings']['announcements']['pvp']=True
    retail['events']=[{'id':'honor','kind':'pvp','at':retail['exported_at'],
                       'data':{'text':'Reached honor level 101','rank':101}}]
    assert validate(retail)['events'][0]['data']['rank']==101


def test_retail_installer_selects_retail_folder(tmp_path):
    addons=tmp_path/'_retail_/Interface/AddOns'
    addons.mkdir(parents=True)
    command=[sys.executable,str(ROOT/'scripts/install_addon.py'),'--client','retail',
             '--addons-dir',str(addons),'--interface']
    assert subprocess.run([*command,'16001'],capture_output=True).returncode!=0
    subprocess.run([*command,'120105'],check=True,capture_output=True)
    assert (addons/'WoWStatus/Retail.lua').is_file()
    assert '## Interface: 120105' in (addons/'WoWStatus/WoWStatus.toc').read_text(encoding='utf-8')


def test_retail_previews_match_profession_and_honor_behavior():
    lua=retail_runtime()
    lua.execute('''
        WoWStatusPreviews.show()
        assert(WoWStatusNotificationPreviews.buttons.profession==nil)
        assert(WoWStatusNotificationPreviews.buttons.pvp:GetText()=="Honor level")
        WoWStatusPopups.preview("profession_learned")
        assert(WoWStatusLevelPopup.message:GetText():find("Learned Inscription",1,true))
        assert(not WoWStatusLevelPopup.message:GetText():find("Apprentice",1,true))
        WoWStatusPopups.preview("pvp")
        function time() return 1793000007 end
        WoWStatusPopups.tick()
        assert(WoWStatusLevelPopup.message:GetText():find("Reached honor level 101",1,true))
        assert(#character().events==0 and #__sent==0)
    ''')
