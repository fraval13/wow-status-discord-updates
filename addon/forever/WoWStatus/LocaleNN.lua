-- Nynorsk texts for WoWStatusLocale (English text -> Nynorsk). Display only:
-- what players send each other stays English, and is translated when shown.
local W = WoWStatusLocale

-- Profession titles and reputation ranks inside facts.
local TITLES = {Apprentice="Lærling", Journeyman="Svein", Expert="Ekspert", Artisan="Kunstnar",
    Master="Meister", Grand_Master="Stormeister", Illustrious="Gjeten", Zen="Zen"}
local function title(word) return TITLES[(word:gsub(" ", "_"))] or word end

-- Phrases in session recaps, longest first so "new zones" wins over "zones".
local RECAP = {
    {"This morning", "I dag tidleg"}, {"This afternoon", "I ettermiddag"}, {"Tonight", "I kveld"},
    {"went from (%d+) to (%d+)", "gjekk frå %1 til %2"}, {"reached level (%d+)", "nådde nivå %1"},
    {"died once", "døydde éin gong"}, {"died twice", "døydde to gonger"}, {"died (%d+) times", "døydde %1 gonger"},
    {"discovered a new zone", "fann eit nytt område"}, {"discovered (%d+) new zones", "fann %1 nye område"},
    {"reached a profession milestone", "nådde eit yrkesmål"}, {"(%d+) profession milestones", "%1 yrkesmål"},
    {"got a first mount", "fekk sitt første ridedyr"}, {"got a first epic mount", "fekk sitt første episke ridedyr"},
    {"defeated a first raid boss", "felte ein første raidsjef"}, {"defeated (%d+) first raid bosses", "felte %1 første raidsjefar"},
    {"equipped a new item", "tok på ein ny gjenstand"}, {"equipped (%d+) new items", "tok på %1 nye gjenstandar"},
    {"passed another 100 quests", "passerte nye 100 oppdrag"},
    {"gained a reputation rank", "steig eitt omdøme-steg"}, {"(%d+) reputation ranks", "%1 omdøme-steg"},
    {"unlocked a class ability", "låste opp ei klasseevne"}, {"(%d+) class ability unlocks", "%1 klasseevner låste opp"},
    {"earned a PvP promotion", "vart forfremja i PvP"}, {"(%d+) PvP promotions", "%1 PvP-forfremjingar"},
    {"cleared ", "rydda "}, {" and ", " og "},
    {"Now level (%d+) with (%d+) deaths in total", "No nivå %1 med %2 dødsfall totalt"},
    {"(%d+) level ups?", "%1 nivå"}, {"(%d+) dungeon clears?", "%1 fangehol rydda"},
    {"(%d+) raid boss kills?", "%1 raidsjefar felte"}, {"(%d+) deaths?", "%1 dødsfall"},
    {"(%d+) profession milestones?", "%1 yrkesmål"}, {"(%d+) first mounts?", "%1 første ridedyr"},
    {"(%d+) epic mounts?", "%1 episke ridedyr"}, {"(%d+) first equips?", "%1 nye gjenstandar"},
    {"(%d+) new zones?", "%1 nye område"}, {"(%d+) quest milestones?", "%1 oppdragsmål"},
    {"(%d+) reputation ranks?", "%1 omdøme-steg"}, {"(%d+) class unlocks?", "%1 klasseevner"},
    {"(%d+) PvP promotions?", "%1 PvP-forfremjingar"},
}
local function recap(text)
    for _, rule in ipairs(RECAP) do text = text:gsub(rule[1], rule[2]) end
    return text
end

W.add({
    -- Fixed facts
    ["Died"] = "Døydde",
    ["Joined the WoW Status group"] = "Vart med i WoW Status-gruppa",
    ["Joined the group"] = "Vart med i gruppa",
    ["First mount ride recorded!"] = "Første ridetur er registrert!",
    ["Shared an update"] = "Delte ei oppdatering",
    -- Popup headings
    ["LEVEL UP!"] = "NYTT NIVÅ!", ["FIRST EQUIP!"] = "FØRSTE GONG PÅ!",
    ["A FRIEND HAS FALLEN"] = "EIN VEN HAR FALLE", ["ON THE MOVE"] = "PÅ FARTEN",
    ["FRIEND UPDATE"] = "NYTT FRÅ EIN VEN", ["QUEST ACHIEVEMENT!"] = "OPPDRAGSBRAGD!",
    ["PROFESSION PROMOTION!"] = "YRKESFORFREMJING!", ["PROFESSION LEARNED!"] = "NYTT YRKE!",
    ["PROFESSION PROGRESS"] = "YRKESFRAMGANG", ["WELCOME, ADVENTURER!"] = "VELKOMEN, EVENTYRAR!",
    ["INVALID LOG DATA REPORTED"] = "UGYLDIG LOGGDATA", ["FIRST DUNGEON CLEAR!"] = "FØRSTE FANGEHOL RYDDA!",
    ["FIRST RAID BOSS!"] = "FØRSTE RAIDSJEF!", ["FIRST EPIC MOUNT!"] = "FØRSTE EPISKE RIDEDYR!",
    ["A NEW ADVENTURE!"] = "EIT NYTT EVENTYR!", ["REPUTATION MILESTONE!"] = "OMDØMEMÅL!",
    ["CLASS ABILITY UNLOCKED!"] = "NY KLASSEEVNE!", ["PVP PROMOTION!"] = "PVP-FORFREMJING!",
    ["HONOR LEVEL UP!"] = "NYTT ÆRENIVÅ!", ["A NEW FIRST!"] = "EIN NY REKORD!",
    ["SESSION RECAP"] = "ØKTSAMANDRAG", ["QUEST COMPLETED"] = "OPPDRAG FULLFØRT",
    ["EQUIPMENT"] = "UTSTYR", ["TRACKING STARTED"] = "SPORING STARTA",
    ["MAXIMUM LEVEL!"] = "HØGASTE NIVÅ!",
    ["RARE ARMOR EQUIPPED!"] = "SJELDAN RUSTNING PÅ!", ["EPIC ARMOR EQUIPPED!"] = "EPISK RUSTNING PÅ!",
    ["LEGENDARY ARMOR EQUIPPED!"] = "LEGENDARISK RUSTNING PÅ!",
}, {
    {"^Reached level (%d+)!$", "Nådde nivå %1!"},
    {"^reached level (%d+)!(.*)$", function(level, rest)
        return "nådde nivå " .. level .. "!" .. rest:gsub(" %((%d+) recorded level%-ups%)", " (%1 registrerte nivå)")
    end},
    {"^Total deaths: (%d+)$", "Dødsfall totalt: %1"},
    {"^Died — total tracked deaths: (%d+)$", "Døydde — dødsfall totalt: %1"},
    {"^Completed (%d+) quests!$", "Fullførte %1 oppdrag!"},
    {"^Entered (.+)$", "Kom til %1"},
    {"^Learned (.-) %((.+)%)$", function(name, rank) return "Lærte " .. name .. " (" .. title(rank) .. ")" end},
    {"^Learned (.+)$", "Lærte %1"},
    {"^(.-): (.-) %((%d+) max%)$", function(name, rank, max) return name .. ": " .. title(rank) .. " (maks " .. max .. ")" end},
    {"^First clear: (.+)$", "Første gjennomføring: %1"},
    {"^First raid boss: (.+)$", "Første raidsjef: %1"},
    {"^First epic mount: (.+)$", "Første episke ridedyr: %1"},
    {"^First mount: (.+)$", "Første ridedyr: %1"},
    {"^Honored with (.+)$", "Æra hos %1"},
    {"^Revered with (.+)$", "Vørd hos %1"},
    {"^Exalted with (.+)$", "Opphøgd hos %1"},
    {"^Unlocked (.+)$", "Låste opp %1"},
    {"^Promoted to (.+)$", "Forfremja til %1"},
    {"^Reached honor level (%d+)$", "Nådde ærenivå %1"},
    {"^Equipped (.+)$", "Tok på %1"},
    {"^Looted (.+)$", "Plyndra %1"},
    {"^Tracking started at level (%d+)$", "Sporinga starta på nivå %1"},
    -- Overview facts ("Since you were last here")
    {"^reached level (%d+)$", "nådde nivå %1"},
    {"^gained (%d+) levels %(now (%d+)%)$", "gjekk opp %1 nivå (no %2)"},
    {"^gained (%d+) levels$", "gjekk opp %1 nivå"},
    {"^cleared a dungeon$", "rydda eit fangehol"},
    {"^cleared (.+)$", "rydda %1"},
    {"^died once$", "døydde éin gong"},
    {"^died (%d+) times$", "døydde %1 gonger"},
    {"^discovered a new zone$", "fann eit nytt område"},
    {"^discovered (%d+) new zones$", "fann %1 nye område"},
    {"^a profession milestone$", "eit yrkesmål"},
    {"^(%d+) profession milestones$", "%1 yrkesmål"},
    {"^got a first mount$", "fekk sitt første ridedyr"},
    {"^equipped a new item$", "tok på ein ny gjenstand"},
    {"^equipped (%d+) new items$", "tok på %1 nye gjenstandar"},
    {"^a new reputation rank$", "eitt nytt omdøme-steg"},
    {"^(%d+) new reputation ranks$", "%1 nye omdøme-steg"},
    {"^a class ability unlock$", "ei ny klasseevne"},
    {"^(%d+) class ability unlocks$", "%1 nye klasseevner"},
    {"^a PvP promotion$", "ei PvP-forfremjing"},
    {"^(%d+) PvP promotions$", "%1 PvP-forfremjingar"},
    {"^joined the group$", "vart med i gruppa"},
    {"^an update$", "ei oppdatering"},
    {"^(%d+) updates$", "%1 oppdateringar"},
    {"^Session recap: (.+)$", function(body) return "Øktsamandrag: " .. recap(body) end},
    {"^(This morning)(.+)$", function(a, b) return recap(a .. b) end},
    {"^(This afternoon)(.+)$", function(a, b) return recap(a .. b) end},
    {"^(Tonight)(.+)$", function(a, b) return recap(a .. b) end},
})
