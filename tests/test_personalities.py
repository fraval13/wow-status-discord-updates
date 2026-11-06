"""Caption personalities: generated banks, selection, saved captions and settings."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from test_addon import PERSONALITY_FILES, make_lua

ROOT = Path(__file__).parents[1]
KINDS = ('level', 'introduction', 'loot', 'death', 'zone', 'quest', 'profession_learned',
         'profession', 'dungeon', 'mount', 'reputation', 'unlock', 'pvp')


def builder():
    spec = importlib.util.spec_from_file_location('build_personalities', ROOT / 'scripts/build_personalities.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up while loading
    spec.loader.exec_module(module)
    return module


def test_generated_files_match_their_json_and_every_edition():
    build = builder()
    assert tuple(p.file for p in build.PERSONALITIES) == PERSONALITY_FILES[1:]
    assert build.CATEGORIES == KINDS
    for personality in build.PERSONALITIES:
        shared = ROOT / 'addon/shared' / personality.file
        assert shared.read_text(encoding='utf-8') == build.render(personality), personality.file
        for edition in ('vanilla', 'forever', 'tbc', 'retail'):
            assert (ROOT / 'addon' / edition / 'WoWStatus' / personality.file).read_bytes() == shared.read_bytes()
    for edition in ('vanilla', 'forever', 'tbc', 'retail'):
        toc = (ROOT / 'addon' / edition / 'WoWStatus/WoWStatus.toc').read_text(encoding='utf-8').split()
        start = toc.index('FlavourNN.lua')
        assert tuple(toc[start + 1:start + 1 + len(PERSONALITY_FILES)]) == PERSONALITY_FILES


def test_the_builder_rejects_broken_sources(tmp_path):
    build = builder()
    personality = build.PERSONALITIES[0]
    folder = tmp_path / personality.id
    folder.mkdir()
    rows = [{'en': f'Line {i}.', 'nn': f'Line {i} på nynorsk.'} for i in range(560)]
    tags = ['ANY'] * 170 + [token for token in build.CLASSES for _ in range(30)]
    deaths = [dict(row, tag=tag) for row, tag in zip(rows, tags)]
    rows = rows[:300]
    for kind in KINDS:
        data = deaths if kind == 'death' else rows
        (folder / f'{kind}.json').write_text(json.dumps(data), encoding='utf-8')
    assert 'register("wholesome"' in build.render(personality, tmp_path)
    broken = {
        'level': rows[:299],
        'loot': rows[:299] + [{'en': 'Line 0.', 'nn': 'Unik.'}],
        'zone': rows[:299] + [{'en': 'Has a "quote".', 'nn': 'Unik.'}],
        'death': [dict(row, tag='KNIGHT') for row in deaths],
        'death ': deaths[:530] + [dict(row, tag='ANY') for row in deaths[530:]],
        'quest': [dict(row, tag='ANY') for row in rows],
    }
    for kind, data in broken.items():
        kind = kind.strip()
        good = (folder / f'{kind}.json').read_text(encoding='utf-8')
        (folder / f'{kind}.json').write_text(json.dumps(data), encoding='utf-8')
        with pytest.raises(build.PersonalityError):
            build.render(personality, tmp_path)
        (folder / f'{kind}.json').write_text(good, encoding='utf-8')


def test_every_personality_has_paired_banks_of_300_and_30_deaths_per_class():
    lua = make_lua()
    lua.execute('''
        local P=WoWStatusPersonalities
        assert(#P.order==11 and P.order[1]=="random" and P.order[2]=="classic" and P.current()=="random")
        assert(#P.voices()==10 and P.voices()[1]=="classic" and not P.banks("random") and not P.banks("classic"))
        for i=3,#P.order do
            local en,nn=P.banks(P.order[i])
            local count=0
            for kind,bank in pairs(en) do
                count=count+1
                local size=kind=="death" and 560 or 300
                assert(#bank==size and #nn[kind]==size, kind)
                local tags={}
                for pos,line in ipairs(bank) do
                    -- Death lines keep the same class tag in both languages.
                    assert(line:match("^%[[A-Z]+%] ")==nn[kind][pos]:match("^%[[A-Z]+%] "))
                    local tag=line:match("^%[([A-Z]+)%] ")
                    if tag then tags[tag]=(tags[tag] or 0)+1 end
                end
                if kind=="death" then
                    assert(tags.ANY==170 and tags.PALADIN==30 and tags.EVOKER==30)
                end
            end
            assert(count==13)
        end
    ''')


def test_new_captions_use_the_chosen_personality_and_keep_it():
    lua = make_lua()
    lua.execute('''
        local F,P=WoWStatusFlavour,WoWStatusPersonalities
        local function strip(line) return (line:gsub("^%[[A-Z]+%] ","")) end
        assert(P.set("dwarf") and P.current()=="dwarf" and WoWStatusDB.personality=="dwarf")
        local en,nn=P.banks("dwarf")
        local item={kind="level",level=20,id="classic-era:eldrin-testrealm:1-1"}
        local caption=F.text(item)
        assert(item.flavour_personality=="dwarf" and caption==strip(en.level[item.flavour_pos]))
        assert(item.flavour==caption)
        -- A saved caption keeps its personality after the choice changes, and follows the language.
        P.set("classic")
        assert(WoWStatusDB.personality=="classic" and F.text(item)==caption)
        WoWStatusLocale.set("nn")
        assert(F.text(item)==strip(nn.level[item.flavour_pos]))
        -- A log entry keeps only the text: it is found again, in either language.
        assert(F.text({flavour=caption})==strip(nn.level[item.flavour_pos]))
        assert(F.text({flavour=strip(nn.level[item.flavour_pos])})==strip(nn.level[item.flavour_pos]))
        WoWStatusLocale.set("en")
        -- The same event draws the same line for the same personality.
        P.set("dwarf")
        assert(F.text({kind="level",level=20,id="classic-era:eldrin-testrealm:1-1"})==caption)
        -- Classic is unchanged: no personality is saved.
        P.set("classic")
        local classic={kind="level",level=20,id="classic-era:eldrin-testrealm:1-1"}
        F.text(classic)
        assert(classic.flavour_personality==nil and WoWStatusFlavour.banks.level[classic.flavour_pos]==classic.flavour)
        -- Random is the default, saved as no choice; an unknown saved choice falls back to it.
        assert(P.set("random") and WoWStatusDB.personality==nil and P.current()=="random")
        WoWStatusDB.personality="pirate"
        assert(P.current()=="random" and not P.set("pirate"))
    ''')


def test_personality_death_lines_respect_the_sender_class():
    lua = make_lua()
    lua.execute('''
        local F,P=WoWStatusFlavour,WoWStatusPersonalities
        P.set("goblin")
        local en=P.banks("goblin")
        local general,paladin={},{}
        for _,line in ipairs(en.death) do
            local tag,copy=line:match("^%[([A-Z]+)%] (.+)$")
            if tag=="ANY" then general[copy]=true;paladin[copy]=true end
            if tag=="PALADIN" then paladin[copy]=true end
        end
        function UnitName(unit) if unit=="party1" then return "Eldrin","TestRealm" end end
        function UnitClass() return "Paladin","PALADIN" end
        local specific=false
        for i=1,300 do
            assert(general[F.text({kind="death",sender="Unknown-TestRealm",nonce="1-"..i})])
            local copy=F.text({kind="death",sender="Eldrin-TestRealm",nonce="1-"..i})
            assert(paladin[copy]);if not general[copy] then specific=true end
        end
        assert(specific)
    ''')


def test_settings_button_cycles_and_previews_and_the_command_switches():
    lua = make_lua()
    lua.execute('WoWStatusPopups.CLICK_GUARD = 0')
    lua.execute('''
        local P=WoWStatusPersonalities
        WoWStatusPreviews.show()
        local panel=WoWStatusNotificationPreviews
        assert(panel.personality.text=="Caption personality: Random")
        panel.personalityNext.OnClick(panel.personalityNext)
        assert(P.current()=="classic" and panel.personality.text=="Caption personality: Classic")
        panel.personalityNext.OnClick(panel.personalityNext)
        assert(P.current()=="wholesome" and panel.personality.text=="Caption personality: Wholesome")
        assert(WoWStatusLevelPopup.detail.visible and #WoWStatusDB.journal.entries==0 and #__sent==0)
        for i=1,9 do panel.personalityNext.OnClick(panel.personalityNext) end
        assert(P.current()=="random")
        local said
        DEFAULT_CHAT_FRAME.AddMessage=function(_,message) said=message end
        SlashCmdList.WOWSTATUS("personality epic bard")
        assert(P.current()=="bard" and said:find("Caption personality: Epic bard.",1,true))
        SlashCmdList.WOWSTATUS("personality Dverg")
        assert(P.current()=="dwarf")
        SlashCmdList.WOWSTATUS("personality")
        assert(P.current()=="dwarf" and said:find("Goblin merchant",1,true))
        WoWStatusLocale.set("nn")
        WoWStatusPreviews.show()
        assert(panel.personality.text=="Personlegdom i kommentarane: Dverg")
    ''')


def test_the_agent_skill_is_mirrored_for_claude():
    # Codex and other agents read .agents/skills; Claude Code reads .claude/skills.
    source = ROOT / '.agents/skills/caption-personality'
    mirror = ROOT / '.claude/skills/caption-personality'
    names = sorted(path.name for path in source.iterdir())
    assert names == sorted(path.name for path in mirror.iterdir()) and 'SKILL.md' in names
    for name in names:
        assert (mirror / name).read_bytes() == (source / name).read_bytes(), name


def test_random_is_the_default_and_mixes_every_voice_per_event():
    lua = make_lua()
    lua.execute('''
        local F,P=WoWStatusFlavour,WoWStatusPersonalities
        assert(P.current()=="random")
        local seen,classic={},0
        for i=1,400 do
            local id="forever:eldrin-testrealm:"..i
            local item={kind="level",level=10,id=id}
            local caption=F.text(item)
            local voice=item.flavour_personality or "classic"
            seen[voice]=true
            if voice=="classic" then classic=classic+1 end
            -- The same event draws the same voice and line again (peers, reloads).
            local again={kind="level",level=10,id=id}
            assert(F.text(again)==caption and (again.flavour_personality or "classic")==voice)
            -- The saved caption keeps its voice when the choice changes.
            P.set("dwarf");assert(F.text(item)==caption);P.set("random")
        end
        local voices=0
        for _ in pairs(seen) do voices=voices+1 end
        assert(voices==10 and classic>0, voices)
        -- Previews draw a fresh voice and line each time.
        local captions={}
        for i=1,30 do captions[F.text({kind="level",level=10,preview=true})]=true end
        local count=0
        for _ in pairs(captions) do count=count+1 end
        assert(count>20)
    ''')
