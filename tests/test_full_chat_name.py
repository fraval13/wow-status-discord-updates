"""WoW Forever: UnitName gives a first name, chat and rosters the full name.

Mocked client APIs; the live client showed own entries split between "Mine"
("Edith") and "Friends" ("Edith Aateigen").
"""
from test_addon import make_lua


def test_full_chat_name_is_learnt_from_the_roster_and_own_entries_are_merged():
    lua = make_lua()
    lua.execute('''
        WoWStatusGroups.update("dawnwatch","")
        local group=next(character().group_ids)
        __channelNames={WoWStatusGroups.channel(group)}
        fire("PLAYER_LEVEL_UP",5)
        local nonce=character().events[#character().events].nonce
        local own=WoWStatusJournal.entries()[1]
        assert(own.owner and own.sender=="Thora-TestRealm")
        -- A friend relays this level-up back, named as chat names this character.
        WoWStatusJournal.received({sender="Thora Stone-TestRealm",nonce=nonce,kind="level",level=5,
            at=own.at,group_id=group})
        assert(#WoWStatusJournal.entries()==2)
        -- The roster lists this character (by GUID) under its full name.
        __peers={"x","y"}
        C_ChatInfo.GetChannelRosterInfo=function(_, i)
            local list={{"Thora Stone",UnitGUID("player")},{"Eldrin",nil}}
            local item=list[i]
            if item then return item[1],false,false,item[2] end
        end
        WoWStatusPopups.peers(group)
        for _=1,3 do WoWStatusPopups.tick() end
        assert(character().chat_name=="Thora Stone")
        local entries=WoWStatusJournal.entries()
        assert(#entries==1)
        assert(entries[1].owner and entries[1].sender=="Thora Stone-TestRealm")
        assert(entries[1].id==WoWStatusJournal.eventID("Thora Stone-TestRealm",nonce))
        -- The same copy arriving again is recognised as this character's.
        WoWStatusJournal.received({sender="Thora Stone-TestRealm",nonce=nonce,kind="level",level=5,
            at=own.at,group_id=group})
        assert(#WoWStatusJournal.entries()==1)
        local peers=WoWStatusPopups.peers(group)
        assert(#peers==1 and peers[1]=="Eldrin")
        assert(WoWStatusPopups.isSelf("Thora Stone-TestRealm") and WoWStatusPopups.isSelf("Thora"))
        assert(WoWStatusPopups.characterName(character())=="Thora Stone-TestRealm")
        -- New entries use the full name from now on.
        fire("PLAYER_LEVEL_UP",6)
        assert(WoWStatusJournal.entries()[1].sender=="Thora Stone-TestRealm")
    ''')


def test_without_guids_the_one_member_named_like_you_is_you():
    lua = make_lua()
    lua.execute('''
        WoWStatusGroups.update("dawnwatch","")
        local group=next(character().group_ids)
        __peers={"Thora Stone","Eldrin"}
        WoWStatusPopups.peers(group)
        for _=1,3 do WoWStatusPopups.tick() end
        assert(character().chat_name=="Thora Stone")
        local peers=WoWStatusPopups.peers(group)
        assert(#peers==1 and peers[1]=="Eldrin")
    ''')


def test_two_members_named_like_you_teach_nothing():
    lua = make_lua()
    lua.execute('''
        WoWStatusGroups.update("dawnwatch","")
        local group=next(character().group_ids)
        __peers={"Thora Stone","Thora Vale","Eldrin"}
        WoWStatusPopups.peers(group)
        for _=1,3 do WoWStatusPopups.tick() end
        assert(character().chat_name==nil)
        assert(#WoWStatusPopups.peers(group)==3)
    ''')
