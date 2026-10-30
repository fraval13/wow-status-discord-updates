"""Caption selection and presentation, without game or network access."""
import json
import re
from pathlib import Path

from test_addon import make_lua


def test_all_banks_have_100_lines_and_generated_editions_match():
    lua = make_lua()
    lua.execute('''
        local count=0
        for _,bank in pairs(WoWStatusFlavour.banks) do
            count=count+1;assert(#bank==100)
            local seen={}
            for _,line in ipairs(bank) do assert(not seen[line]);seen[line]=true end
        end
        assert(count==13)
    ''')
    project = Path(__file__).parents[1]
    catalogue = (project / 'docs/notification-flavour-text.md').read_text()
    web = (project / 'website/flavour.js').read_text()
    web_banks = json.loads(web.split(' = ', 1)[1].rstrip().removesuffix(';'))
    sections = re.findall(
        r'<a id="([\w-]+)"></a>\n## [^\n]+\n(.*?)(?=\n<a id=|\Z)',
        catalogue, re.S)
    for key, body in sections:
        expected = re.findall(r'^\d+\. (.+)$', body, re.M)
        actual = list(lua.globals().WoWStatusFlavour.banks[key.replace('-', '_')].values())
        assert actual == expected
        if key in web_banks:
            assert web_banks[key] == expected
    root = Path(__file__).parents[1] / 'addon'
    for edition in ('vanilla', 'forever', 'tbc', 'retail'):
        assert (root / edition / 'WoWStatus/Flavour.lua').read_bytes() == (
            root / 'shared/Flavour.lua').read_bytes()


def test_class_roasts_only_match_known_sender_not_armor_class():
    lua = make_lua()
    lua.execute('''
        local general,paladin={},{}
        for _,line in ipairs(WoWStatusFlavour.banks.death) do
            local tag,copy=line:match("^%[([A-Z]+)%] (.+)$")
            if tag=="ANY" then general[copy]=true;paladin[copy]=true end
            if tag=="PALADIN" then paladin[copy]=true end
        end
        function UnitName(unit) if unit=="party1" then return "Eldrin","TestRealm" end end
        function UnitClass() return "Paladin","PALADIN" end
        local specific=false
        for i=1,200 do
            local unknown={kind="death",sender="Unknown-TestRealm",class_id=2,nonce="1-"..i}
            assert(general[WoWStatusFlavour.text(unknown)])
            local known={kind="death",sender="Eldrin-TestRealm",nonce="1-"..i}
            local copy=WoWStatusFlavour.text(known)
            assert(paladin[copy]);if not general[copy] then specific=true end
        end
        assert(specific)
        function issecretvalue(value) return value=="Eldrin" or value=="PALADIN" end
        for i=1,50 do
            assert(general[WoWStatusFlavour.text({kind="death",sender="Eldrin-TestRealm",nonce="2-"..i})])
        end
    ''')


def test_event_draw_stable_across_reload_and_distinct_events_vary():
    lua = make_lua()
    lua.execute('''
        local f=WoWStatusFlavour
        local id="classic-era:eldrin-testrealm:100-7"
        local live={kind="level",level=33,sender="Eldrin-TestRealm",nonce="100-7"}
        local log={kind="level",level=33,id=id}
        assert(f.text(live)==f.text(log))
        assert(f.text(log)==f.text({kind="level",level=33,id=id}))
        local seen={};local count=0
        for i=1,200 do
            local line=f.text({kind="level",level=33,id=id..i})
            if not seen[line] then seen[line]=true;count=count+1 end
        end
        assert(count>50)
        local death={kind="death",sender="Eldrin-TestRealm",id=id}
        local first=f.text(death)
        function UnitName() return "Eldrin","TestRealm" end
        function UnitClass() return "Paladin","PALADIN" end
        assert(f.text(death)==first)
    ''')


def test_profession_banks_and_unknown_kinds():
    lua = make_lua()
    lua.execute('''
        local learned,promoted={},{}
        for _,line in ipairs(WoWStatusFlavour.banks.profession_learned) do learned[line]=true end
        for _,line in ipairs(WoWStatusFlavour.banks.profession) do promoted[line]=true end
        assert(learned[WoWStatusFlavour.text({kind="profession",text="Learned Inscription"})])
        assert(promoted[WoWStatusFlavour.text({kind="profession",text="Tailoring: Expert (225 max)"})])
        assert(WoWStatusFlavour.text({kind="professionprogress"})=="")
        assert(WoWStatusFlavour.text({kind="questprogress"})=="")
    ''')


def test_previews_randomize_locally_and_do_not_repeat_immediately():
    lua = make_lua()
    lua.execute('''
        WoWStatusPopups.preview("death")
        local first=WoWStatusLevelPopup.detail.text
        assert(first and first~="" and WoWStatusLevelPopup.detail.visible)
        assert(not first:find("%["))
        WoWStatusLevelPopup.OnMouseUp(WoWStatusLevelPopup,"LeftButton")
        WoWStatusPopups.preview("death")
        assert(WoWStatusLevelPopup.detail.text~=first)
        assert(#WoWStatusDB.journal.entries==0)
        assert(#WoWStatusDB.popups.activity==0 and #__sent==0)
    ''')


def test_live_popup_and_persistent_log_share_caption():
    lua = make_lua()
    lua.execute('''
        WoWStatusGroups.update("navsquad","")
        local group=next(character().group_ids)
        __channelNames={WoWStatusGroups.channel(group)}
        local packet="WSTATUS2 classic-era LEVEL 33 "..time().." 100-7"
        assert(WoWStatusPopups.receive(packet,"Eldrin-TestRealm",WoWStatusGroups.channel(group)))
        local entry=WoWStatusDB.journal.entries[1]
        assert(entry and entry.flavour==WoWStatusLevelPopup.detail.text)
        assert(entry.text=="Reached level 33!")
        WoWStatusJournal.show()
        local row=WoWStatusActivityLog.rows[1]
        assert(row.flavour.text==entry.flavour)
        WoWStatusJournal.show()
        assert(row.flavour.text==entry.flavour)
    ''')
