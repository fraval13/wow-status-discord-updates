-- Nynorsk texts for WoWStatusLocale (English text -> Nynorsk). Display only:
-- what players send each other stays English, and is translated when shown.
local W = WoWStatusLocale
local bank = W.register("nn", "Nynorsk", {}, nil, nil, "Bytt til nynorsk")
W.NN, W.PATTERNS = bank.exact, bank.patterns

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
    {"earned an achievement", "fekk ei bragd"}, {"(%d+) achievements", "%1 bragder"},
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
    ["Commands:"] = "Kommandoar:",
    ["Window pages:"] = "Vindaugssider:",
    ["Configure"] = "Set opp",
    ["Personal level countdown"] = "Personleg nedteljing til nivåmål",
    ["Show a private level and XP countdown in the status line."] = "Vis privat nedteljing i nivå og XP på statuslinja.",
    ["Levels left: %d (%.1f XP bars)"] = "Nivå att: %d (%.1f XP-linjer)",
    ["Levels left: %d"] = "Nivå att: %d",
    ["Target level: %d"] = "Målnivå: %d",
    ["No level goal"] = "Ingen nivåmål",
    ["Riding level"] = "Ridenivå",
    ["Level cap"] = "Maksnivå",
    ["Clear goal"] = "Fjern målet",
    ["Hardcore character (manual)"] = "Hardkjernefigur (manuelt)",
    ["Configure"] = "Set opp",
    ["Join a group to see its bingo card."] = "Bli med i ei gruppe for å sjå bingobrettet.",
    ["Next group"] = "Neste gruppe",
    ["Cannot open now: settings cannot be opened during combat. Try again after combat."] = "Kan ikkje opne no: innstillingane kan ikkje opnast i kamp. Prøv att etter kampen.",
    ["Cannot open now: WoW's addon settings are not ready. Try again shortly."] = "Kan ikkje opne no: tilleggsinnstillingane i WoW er ikkje klare. Prøv att om litt.",
    ["Cannot open now: WoW could not open settings. Try Options > AddOns > WoW Status."] = "Kan ikkje opne no: WoW kunne ikkje opne innstillingane. Prøv Options > AddOns > WoW Status.",
    -- Fixed facts
    ["Died"] = "Døydde", ["Died in Hardcore"] = "Døydde i hardkjernemodus",
    ["Joined the WoW Status group"] = "Vart med i WoW Status-gruppa",
    ["Joined the group"] = "Vart med i gruppa",
    ["First mount ride recorded!"] = "Første ridetur er registrert!",
    ["Shared an update"] = "Delte ei oppdatering",
    -- Main window and Activity
    ["Overview"] = "Oversikt", ["Activity"] = "Aktivitet", ["Records"] = "Rekordar", ["Characters"] = "Figurar",
    ["(sample tour, nothing here is real)"] = "(prøvetur, ingenting her er ekte)", ["Home"] = "Heim",
    ["Showing:"] = "Viser:", ["From your achievements (date only)"] = "Frå bragdene dine (berre dato)",
    ["Your activity"] = "Di aktivitet", ["Caught up via"] = "Henta via", ["a group member"] = "eit gruppemedlem",
    ["passed on by"] = "vidaresendt av", ["Saved group update"] = "Lagra gruppeoppdatering",
    ["Live group update"] = "Direkte gruppeoppdatering", ["No activity yet"] = "Ingen aktivitet enno",

    -- Characters page
    ["Not announced"] = "Ikkje kunngjort", ["Unnamed player"] = "Namnlaus spelar", ["you"] = "deg",
    ["character"] = "figur", ["characters"] = "figurar", ["Sync now"] = "Synk no", ["Sync (%d s)"] = "Synk (%d s)",
    ["Your characters"] = "Figurane dine", ["Other"] = "Andre",
    ["Nobody else seen in this group yet."] = "Ingen andre er sett i denne gruppa enno.",
    ["older version"] = "eldre versjon", ["older version or list sharing off"] = "eldre versjon eller listedeling av",
    ["Never met"] = "Aldri møtt", ["offline"] = "fråkopla", ["XP %d%%"] = "XP %d %%", ["Level %d"] = "Nivå %d",
    ["1 death"] = "1 dødsfall", ["%d deaths"] = "%d dødsfall", ["Groups:"] = "Grupper:",
    ["armor"] = "rustningar", ["quests"] = "oppdrag", ["deaths"] = "dødsfall", ["days"] = "dagar", ["levels"] = "nivå",
    ["level"] = "nivå", ["day"] = "dag",
    -- Deathless streaks (#164)
    ["Deathless streak"] = "Utan å døy", ["at least"] = "minst",
    ["without a death ends in"] = "utan å døy endar i", ["without a death ends here."] = "utan å døy endar her.",
    ["A week without a death!"] = "Ei veke utan å døy!",
    ["Deathless streak milestones (every 5 levels or week)"] = "Milepælar utan å døy (kvart 5. nivå eller kvar veke)",
    ["death"] = "dødsfall", ["zone"] = "område", ["zones"] = "område", ["This week"] = "Denne veka",
    ["Week"] = "Veke", ["Fun records"] = "Morosame rekordar", ["Most levels:"] = "Flest nivå:", ["Most deaths:"] = "Flest dødsfall:",
    ["Most explored:"] = "Mest utforska:", ["Most dangerous zone:"] = "Farlegaste område:",
    ["Longest deathless streak now:"] = "Lengst utan å døy no:",
    ["Longest deathless streak ever:"] = "Lengst utan å døy nokon gong:", ["Best evening:"] = "Beste kveld:", ["Most new gear:"] = "Mest ny rustning:",
    ["Fastest to maximum level:"] = "Raskast til høgste nivå:", ["hours"] = "timar", ["day"] = "dag",
    ["Group nemesis and deadliest zone"] = "Gruppefienden og farlegaste område",
    ["Records name who has killed the group most, and the zone it died in most this week."] = "Rekordane nemner kven som har teke flest av gruppa, og området der flest døydde denne veka.",
    ["Group nemesis:"] = "Gruppefiende:", ["Nemesis this week:"] = "Fiende denne veka:", ["Deadliest zone this week:"] = "Farlegaste område denne veka:",
    ["kill"] = "drap", ["kills"] = "drap",
    ["Who you played with"] = "Kven du spelte med",
    ["Your own log cards name the friends who were in your party at the milestone."] = "Dine eigne loggkort nemner venene som var i partyet ditt då det skjedde.",
    ["with"] = "med",
    ["Hype combo banner"] = "Kombo-banner",
    ["When friends hit milestones within ten minutes of each other, the banner says Combo x2, x3 and names them."] = "Når vener nådde milepålar med mindre enn ti minutt mellom, seier banneret Kombo x2, x3 og nemner dei.",
    ["COMBO"] = "KOMBO",
    ["Race a friend to a level"] = "Kappløp med ein ven til eit nivå",
    ["Pick a friend and a level (/wstatus race Name 40): the status line shows both of you, and a banner says who got there first. The friend is never told."] = "Vel ein ven og eit nivå (/wstatus race Namn 40): statuslinja viser dykk begge, og eit banner seier kven som kom fyrst. Venen får aldri vite det.",
    ["You won the race to level"] = "Du vann kappløpet til nivå", ["got to level"] = "nådde nivå", ["first"] = "fyrst",
    ["Race to"] = "Kappløp til", ["Race started."] = "Kappløpet er i gang.", ["Race cancelled."] = "Kappløpet er avbrote.",
    ["No race is running."] = "Inga kappløp går.", ["Usage: /wstatus race Name Level, or /wstatus race cancel"] = "Bruk: /wstatus race Namn Nivå, eller /wstatus race cancel",
    ["Turn on Race a friend on the Labs page first."] = "Slå på «Kappløp med ein ven» på Labs-sida fyrst.",
    ["No friend by that name in your activity log yet."] = "Ingen ven med det namnet i aktivitetsloggen enno.",
    ["Seasonal captions"] = "Sesongbildetekstar",
    ["During Hallow's End, Winter Veil, the Lunar Festival and Love is in the Air, a few captions turn festive."] = "Under Hallow's End, Vintervéen, månefestivalen og Love is in the Air vert nokre bildetekstar festlege.",
    ["Even the graveyard looks festive this Hallow's End."] = "Sjølv kyrkjegarden ser festleg ut denne Hallow's End.",
    ["Trick or treat? That was a trick."] = "Knask eller knep? Det der var knep.",
    ["Pumpkins everywhere, and now this."] = "Gresskar overalt, og no dette.",
    ["Merry Winter Veil, adventurer."] = "God Vintervé, eventyrar.",
    ["Even Greatfather Winter nodded at that."] = "Sjølv Vinterbestefar nikka til det der.",
    ["A gift worth unwrapping."] = "Ei gåve verd å pakke opp.",
    ["Happy Lunar Festival to you and your elders."] = "God månefestival til deg og dei eldre dine.",
    ["Fireworks fit this moment."] = "Fyrverkeri passar til denne stunda.",
    ["Fortune smiles on the Lunar Festival."] = "Lykka smiler på månefestivalen.",
    ["Love is in the Air, and so is this news."] = "Kjærleik er i lufta, og det same er denne nyheita.",
    ["Roses are red, milestones are blue."] = "Roser er raude, milepålar er blå.",
    ["Even the Love is in the Air crowd took notice."] = "Sjølv Love is in the Air-folket la merke til det.",
    ["Weekly group bingo card"] = "Vekentleg bingobrett for gruppa",
    ["A 5x5 card of group events for the week, filled in from the shared log and shown under This week."] = "Eit 5x5-brett med gruppehendingar for veka, fylt ut frå den delte loggen og vist under Denne veka.",
    ["Weekly bingo:"] = "Vekebingo:",
    ["Bingo!"] = "Bingo!",
    ["The weekly card has a full line."] = "Vekebrettet har ei full rad.",
    ["A level-up"] = "Eit nivåoppsteg",
    ["Three level-ups"] = "Tre nivåoppsteg",
    ["Five level-ups"] = "Fem nivåoppsteg",
    ["Ten level-ups"] = "Ti nivåoppsteg",
    ["A level-up after midnight"] = "Eit nivåoppsteg etter midnatt",
    ["A level-up before lunch"] = "Eit nivåoppsteg før lunsj",
    ["A level-up in the evening"] = "Eit nivåoppsteg på kvelden",
    ["Someone reaches level 20"] = "Nokon når nivå 20",
    ["Someone reaches level 40"] = "Nokon når nivå 40",
    ["Someone reaches level 60"] = "Nokon når nivå 60",
    ["Someone dies"] = "Nokon døyr",
    ["Three deaths"] = "Tre dødsfall",
    ["Five deaths"] = "Fem dødsfall",
    ["A new zone"] = "Eit nytt område",
    ["Three new zones"] = "Tre nye område",
    ["100 quests"] = "100 oppdrag",
    ["Two quest milestones"] = "To oppdragsmilepålar",
    ["A dungeon clear"] = "Eit fangehol rydda",
    ["Two dungeon clears"] = "To fangehol rydda",
    ["A raid boss"] = "Ein raidsjef",
    ["A mount"] = "Eit ridedyr",
    ["An epic mount"] = "Eit episk ridedyr",
    ["A new reputation standing"] = "Ny ryktestatus",
    ["A profession milestone"] = "Ein yrkesmilepæl",
    ["A PvP promotion"] = "Ei PvP-opprykking",
    ["A newly unlocked ability"] = "Ei nyoppnådd evne",
    ["An armor first"] = "Ein rustning-førstegong",
    ["Three armor firsts"] = "Tre rustning-førstegonger",
    ["A rare or better item"] = "Ein sjeldan gjenstand eller betre",
    ["An epic item"] = "Ein episk gjenstand",
    ["Someone new joins the group"] = "Nokon ny kjem med i gruppa",
    ["Two people active"] = "To personar aktive",
    ["Three people active"] = "Tre personar aktive",
    ["Five people active"] = "Fem personar aktive",
    ["Ten entries in the log"] = "Ti oppføringar i loggen",
    ["Twenty-five entries in the log"] = "Tjuefem oppføringar i loggen",
    ["Fifty entries in the log"] = "Femti oppføringar i loggen",
    ["A death and a level-up"] = "Eit dødsfall og eit nivåoppsteg",
    ["Four kinds of milestone"] = "Fire slags milepålar",
    ["Weekly chronicle"] = "Vekekrønike",
    ["A short chapter about last week's adventures, written once and shown under last week's list."] = "Eit kort kapittel om eventyra frå førre veke, skrive éin gong og vist under lista for førre veke.",
    ["Chronicle of the week"] = "Krønike for veka",
    ["A quiet week. The road waits."] = "Ei stille veke. Vegen ventar.",
    ["climbed"] = "steig",
    ["reaching level"] = "og nådde nivå",
    ["The group fell"] = "Gruppa fall",
    ["time"] = "gong",
    ["times"] = "gonger",
    ["A Hardcore character fell this week. We remember them."] = "Ein Hardcore-figur fall denne veka. Vi minnest han.",
    ["new place was explored."] = "nytt stad vart utforska.",
    ["new places were explored."] = "nye stader vart utforska.",
    ["Longest without dying:"] = "Lengst utan å døy:", ["Best evening:"] = "Beste kveld:", ["Most new gear:"] = "Mest ny rustning:",
    ["Most monsters killed:"] = "Flest monster drepne:", ["Richest:"] = "Rikast:",
    ["Nothing happened in this group this week."] = "Ingenting har skjedd i denne gruppa denne veka.",
    ["No fun records yet. They appear when someone does something remarkable."] = "Ingen morosame rekordar enno. Dei dukkar opp når nokon gjer noko utruleg.",
    ["Show activity"] = "Vis aktivitet", ["Invite to group"] = "Inviter til gruppe", ["Statistics"] = "Statistikk",
    ["Recent activity"] = "Siste aktivitet", ["Recent gear"] = "Nyleg rustning", ["Invites need them online."] = "Invitasjonar krev at dei er pålogga.",
    ["No level-ups in the log yet."] = "Ingen nye nivå i loggen enno.", ["No activity in the log yet."] = "Ingen aktivitet i loggen enno.",
    ["No new gear yet."] = "Ingen ny rustning enno.", ["invites you to join the group"] = "inviterer deg til å bli med i gruppa",
    ["Join"] = "Bli med", ["Decline"] = "Avslå", ["Click to open this character's profile."] = "Klikk for å opne profilen til figuren.",
    ["Invite sent."] = "Invitasjon sendt.", ["Not ready yet."] = "Ikkje klar enno.", ["That group is not in your list."] = "Den gruppa er ikkje i lista di.",
    ["They need to be online in a group you share."] = "Dei må vere pålogga i ei gruppe de deler.",
    ["They are already in all your groups."] = "Dei er alt med i alle gruppene dine.",
    ["Dungeons, mounts and honor kills"] = "Fangehol, ridedyr og æresdrap", ["Honorable kills"] = "Æresdrap",
    ["Dungeons cleared"] = "Fangehol klarte", ["Mounts"] = "Ridedyr",
    ["Online now:"] = "Pålogga no:", ["nobody"] = "ingen", ["Latest:"] = "Sist:",
    ["New since you last opened the log:"] = "Nytt sidan du sist opna loggen:",
    ["Sounds"] = "Lydar", ["New zones"] = "Nye område", ["Everything else"] = "Alt anna", ["None"] = "Ingen",
    ["Group joins"] = "Nye i gruppa", ["Big moments"] = "Store augneblinkar", ["Same as usual"] = "Som vanleg",
    ["Same as Everything else"] = "Som «Alt anna»",
    ["Soft chime"] = "Mjuk klokke", ["Level-up fanfare"] = "Nivåfanfare", ["Quest complete"] = "Oppdrag fullført",
    ["Ready check"] = "Klar-sjekk", ["Raid warning"] = "Raid-åtvaring", ["Alarm"] = "Alarm",
    ["Quiet mode: hold notifications in"] = "Stille modus: hald att varsel i", ["Battlegrounds"] = "Slagmarker", ["Raids"] = "Raid",
    ["Dungeons"] = "Fangehol",
    ["Quiet hours: hide friends' notifications by the clock"] = "Stille timar: gøym varsel frå vener etter klokka",
    ["From"] = "Frå", ["To"] = "Til", ["Earlier"] = "Tidlegare", ["Later"] = "Seinare",
    ["Quiet hours until"] = "Stille timar til", ["Same start and end: never quiet"] = "Lik start og slutt: aldri stille",
    ["Quiet hours on (local time):"] = "Stille timar på (lokal tid):", ["Quiet hours off:"] = "Stille timar av:",
    ["Usage: /wstatus quiethours [on | off | 22:00-07:00]"] = "Bruk: /wstatus quiethours [on | off | 22:00-07:00]",
    ["not reached"] = "ikkje nådd",
    ["Your live updates did not reach this character. Ask them to /reload, or check that you are on the same realm type."] =
        "Direkteoppdateringane dine nådde ikkje denne figuren. Be dei skrive /reload, eller sjekk at de er på same type rike.",
    ["Listed"] = "Lista", ["Listed group"] = "Lista gruppe", ["Browse groups"] = "Bla i grupper", ["listed by"] = "lista av",
    ["Share this group's name with my other groups"] = "Del namnet på denne gruppa med dei andre gruppene mine",
    ["Sharing this group's name with my other groups"] = "Deler namnet på denne gruppa med dei andre gruppene mine",
    ["Share this group's name?"] = "Dele namnet på denne gruppa?",
    ["Share the name"] = "Del namnet", ["Cancel"] = "Avbryt",
    ["Share this group's name with your other groups? Anyone with the name can join."] =
        "Dele namnet på denne gruppa med dei andre gruppene dine? Alle som kjenner namnet, kan bli med.",
    ["%d known friends are online in your other groups now. Others may receive it later."] =
        "%d kjende vener er pålogga i dei andre gruppene dine no. Andre kan få namnet seinare.",
    ["Turning this off later cannot take back a name already shared."] =
        "Om du slår dette av seinare, kan du ikkje ta tilbake eit namn som alt er delt.",
    ["Anyone with the name can join. Turning this off later cannot take back a name already shared."] =
        "Alle som kjenner namnet, kan bli med. Om du slår dette av seinare, kan du ikkje ta tilbake eit namn som alt er delt.",
    ["No shared group names yet. Friends can share a group's name from their Groups page."] =
        "Ingen delte gruppenamn enno. Vener kan dele namnet på ei gruppe frå Gruppesida si.",
    ["Pick a group ID and give the same ID to your friends. Everyone with the same ID shares updates. Groups are saved for your whole account. Keep the name private: sharing it with your other groups lets their members join too."] =
        "Vel ein gruppe-ID og gje den same ID-en til venene dine. Alle med same ID deler oppdateringar. Gruppene er lagra for heile kontoen din. Hald namnet privat: om du deler det med andre grupper, kan medlemene der òg bli med.",
    ["Friends in your other groups can see this group under Browse groups and join it. Leave it off for a private group."] =
        "Vener i dei andre gruppene dine kan sjå denne gruppa under Bla i grupper og bli med. La det vere av for ei privat gruppe.",
    ["No listed groups yet. Friends list a group by ticking Listed on their Groups page."] =
        "Ingen lista grupper enno. Vener listar ei gruppe ved å krysse av for Lista på Grupper-sida si.",
    ["Equipped by"] = "Teke i bruk av",
    ["Today"] = "I dag", ["Yesterday"] = "I går", ["All days"] = "Alle dagar",
    ["Nothing yet today."] = "Ingenting enno i dag.", ["No activity on this day."] = "Ingen aktivitet denne dagen.",
    ["January"] = "januar", ["February"] = "februar", ["March"] = "mars", ["April"] = "april", ["May"] = "mai",
    ["June"] = "juni", ["July"] = "juli", ["August"] = "august", ["September"] = "september", ["October"] = "oktober",
    ["November"] = "november", ["December"] = "desember",
    ["Mo"] = "Må", ["Tu"] = "Ty", ["We"] = "On", ["Th"] = "To", ["Fr"] = "Fr", ["Sa"] = "La", ["Su"] = "Sø",
    ["1 kill"] = "1 drap", ["%d kills"] = "%d drap", ["Kills:"] = "Drap:", ["Current:"] = "Noverande:", ["Earned:"] = "Tent:",
    ["Played:"] = "Spelt:", ["Gold"] = "Gull", ["Gold earned"] = "Gull tent", ["Monsters killed"] = "Monster drepne",
    ["Played"] = "Spelt", ["Gold and gold earned"] = "Gull og gull tent",
    ["Click to see this character's activity."] = "Klikk for å sjå aktiviteten til figuren.",
    ["No characters yet."] = "Ingen figurar enno.", ["Share my character list"] = "Del figurlista mi",
    ["Online only"] = "Berre pålogga", ["Nobody is online right now."] = "Ingen er pålogga no.",
    ["Nobody from this group is online right now."] = "Ingen frå denne gruppa er pålogga no.",
    ["Shows only the characters online right now. Nothing is hidden from your friends and no progress is lost."] =
        "Viser berre figurane som er pålogga no. Ingenting vert gøymt for venene, og ingen framgang går tapt.",
    ["Hide this character from the list"] = "Gøym denne figuren frå lista",
    ["Unpin"] = "Løys frå toppen", ["Pin this player to the top"] = "Fest denne spelaren øvst",
    ["Pin this character to the top"] = "Fest denne figuren øvst", ["Pinned first"] = "Festa først",
    ["Pinned friends come first on the Characters page, online before offline, in the order you pinned them. Only you see this; nothing is sent."] =
        "Festa vener kjem først på Figurar-sida, pålogga før fråkopla, i den rekkjefølgja du festa dei. Berre du ser dette; ingenting vert sendt.",
    ["Players you pinned on the Characters page lead the board. Nobody is left out."] =
        "Spelarar du har festa på Figurar-sida, leier lista. Ingen vert utelatne.",
    ["Sync with everyone online"] = "Synk med alle som er pålogga",
    ["Sends your character list, asks for theirs, looks up one friend's level with /who and catches up the activity log. Once a minute."] =
        "Sender figurlista di, ber om deira, slår opp nivået til éin ven med /who og hentar inn aktivitetsloggen. Éin gong i minuttet.",
    -- Classes
    ["Warrior"] = "Krigar", ["Paladin"] = "Paladin", ["Hunter"] = "Jeger", ["Rogue"] = "Tjuv", ["Priest"] = "Prest",
    ["Shaman"] = "Sjaman", ["Mage"] = "Magikar", ["Warlock"] = "Heksemeister", ["Druid"] = "Druide",
    ["Deathknight"] = "Dødsriddar", ["Monk"] = "Munk", ["Demonhunter"] = "Demonjeger", ["Evoker"] = "Påkallar",
    -- Races
    ["Human"] = "Menneske", ["Dwarf"] = "Dverg", ["Night Elf"] = "Nattalv", ["Gnome"] = "Gnom", ["Orc"] = "Ork",
    ["Scourge"] = "Udaud", ["Undead"] = "Udaud", ["Tauren"] = "Tauren", ["Troll"] = "Troll", ["Blood Elf"] = "Blodalv",
    ["Draenei"] = "Draenei", ["Goblin"] = "Goblin", ["Worgen"] = "Varulv", ["Pandaren"] = "Pandaren",
    ["Void Elf"] = "Tomromsalv", ["Nightborne"] = "Nattfødd", ["Dracthyr"] = "Dracthyr",
    -- Groups window
    ["More than 8 old groups found. Review your account group list."] = "Fann meir enn 8 gamle grupper. Sjå over gruppelista di.",
    ["Your groups — all characters on this account"] = "Gruppene dine — alle figurane på denne kontoen",
    ["Your name (optional)"] = "Namnet ditt (valfritt)", ["Save name"] = "Lagre namn", ["Group ID"] = "Gruppe-ID",
    ["Use the same ID as your friends.\nAdding or removing a group saves for all your characters."] =
        "Bruk same ID som venene dine.\nNår du legg til eller fjernar ei gruppe, gjeld det alle figurane dine.",
    ["That group is already in your list."] = "Den gruppa er alt i lista di.",
    ["You can add up to 8 groups. Remove one before adding another."] = "Du kan ha opptil 8 grupper. Fjern ei før du legg til ei ny.",
    ["Add"] = "Legg til", ["Remove"] = "Fjern", ["Close"] = "Lukk", ["Groups"] = "Grupper",
    ["No groups selected. Enter a group ID above and click Add."] = "Ingen grupper valde. Skriv ein gruppe-ID over og klikk Legg til.",
    ["These group names collide; choose a different name."] = "Desse gruppenamna kolliderer; vel eit anna namn.",
    ["Choose at most 8 group IDs."] = "Vel høgst 8 gruppe-ID-ar.",
    ["Use a name of up to 40 characters."] = "Bruk eit namn på høgst 40 teikn.",
    ["Groups saved for all characters."] = "Gruppene er lagra for alle figurane.",
    ["Enter one group ID of up to 80 characters."] = "Skriv éin gruppe-ID på høgst 80 teikn.",
    ["Use a non-empty group name of up to 80 characters, one per line."] = "Bruk eit gruppenamn på høgst 80 teikn, eitt per linje.",
    ["This exposed group is retired. Ask its owner privately for the replacement name."] =
        "Denne offentleggjorde gruppa er pensjonert. Spør eigaren privat om det nye namnet.",
    -- Setup guide
    ["Skip"] = "Hopp over", ["Back"] = "Tilbake", ["Next"] = "Neste", ["Done"] = "Ferdig", ["Step %d of %d"] = "Steg %d av %d",
    ["Welcome to WoW Status"] = "Velkomen til WoW Status",
    ["WoW Status shares your milestones with friends inside the game: level-ups, first dungeon clears, new professions and more. They appear as popups and in a shared activity log. Everyone only needs this addon."] =
        "WoW Status deler måla dine med vener inne i spelet: nye nivå, første fangehol, nye yrke og meir. Dei dukkar opp som varsel og i ein felles aktivitetslogg. Alle treng berre dette tillegget.",
    ["Choose or join a group"] = "Lag eller bli med i ei gruppe",
    ["Pick a group ID and give the same ID to your friends. Everyone with the same ID shares updates. Groups are saved for your whole account."] =
        "Vel ein gruppe-ID og gje same ID til venene dine. Alle med same ID deler oppdateringar. Gruppene blir lagra for heile kontoen.",
    ["Open Groups"] = "Opne Grupper", ["Choose your announcements"] = "Vel kva du vil kunngjere",
    ["Choose which milestones you share and see from friends: levels, deaths, first zone visits, professions, dungeon clears and more. You can change this at any time."] =
        "Vel kva mål du deler og ser frå vener: nivå, dødsfall, første besøk i område, yrke, fangehol og meir. Du kan endre dette når som helst.",
    ["Open announcement options"] = "Opne kunngjeringsval", ["You're all set"] = "No er du klar",
    ["Click the minimap book to open the WoW Status window. Want to see what it looks like with friends? Show me around fills it with sample adventurers. Sample data is never saved or sent."] =
        "Klikk på boka ved minikartet for å opne WoW Status-vindauget. Vil du sjå korleis det ser ut med vener? Vis meg rundt fyller det med eksempel-eventyrarar. Eksempeldata blir aldri lagra eller sende.",
    ["Show me around"] = "Vis meg rundt",
    -- History window
    ["History"] = "Historikk", ["All / levels"] = "Alle / nivå", ["Previous page"] = "Førre side",
    ["Next page"] = "Neste side", ["Refresh"] = "Oppdater", ["Event logs"] = "Hendingslogg",
    ["Level graph"] = "Nivågraf", ["Level times"] = "Nivåtider", ["Character details"] = "Figurdetaljar",
    -- Notification settings
    ["Notifications"] = "Varsel", ["Previews"] = "Førehandsvising", ["Choose a notification to preview it."] = "Vel eit varsel for å sjå korleis det ser ut.",
    ["Setup guide"] = "Oppsettsrettleiing", ["Unlock popup position"] = "Lås opp plasseringa av varsla",
    ["Reset popup position"] = "Tilbakestill plasseringa", ["Big banners for big moments"] = "Store banner for store augneblinkar",
    ["Reduce motion"] = "Mindre rørsle",
    ["Next theme"] = "Neste tema",
    ["Use the theme and size for popups too"] = "Bruk temaet og storleiken på varsla òg", ["Apply"] = "Bruk",
    ["Show the group status line"] = "Vis statuslinja for gruppa", ["Attach it under the quest tracker"] = "Fest henne under oppdragslista",
    ["Hide the status line in combat"] = "Gøym statuslinja i kamp", ["Hide the status line in dungeons and raids"] = "Gøym statuslinja i fangehol og raid",
    ["Level up"] = "Nytt nivå", ["First armor equip"] = "Første rustning på", ["Death"] = "Dødsfall",
    ["New location"] = "Ny stad", ["100 quests achievement"] = "100 oppdrag", ["Learn a profession"] = "Lær eit yrke",
    ["Profession title promotion"] = "Ny yrkestittel", ["Reputation promotion"] = "Nytt omdøme-steg",
    ["Major class unlock"] = "Stor klasseevne", ["PvP rank promotion"] = "Ny PvP-grad",
    ["PREVIEW — example character"] = "FØREHANDSVISING — eksempelfigur",
    -- Main settings page
    ["Set the same group ID as your friends to start sharing."] = "Bruk same gruppe-ID som venene dine for å byrje å dele.",
    ["Activity log"] = "Aktivitetslogg", ["Share my progress"] = "Del framgangen min",
    ["Announcements"] = "Kunngjeringar",
    ["Announcements — share and see"] = "Kunngjeringar – del og sjå",
    ["Share and see session recaps"] = "Del og sjå øktsamandrag",
    ["Share and see first armor equips"] = "Del og sjå første rustning", ["Share my session recaps"] = "Del øktsamandraga mine",
    ["First-time equipment"] = "Utstyr første gong", ["Announce first armor equips"] = "Kunngjer første rustning",
    ["Rare equipment"] = "Sjeldan utstyr", ["Epic equipment"] = "Episk utstyr", ["Legendary equipment"] = "Legendarisk utstyr",
    ["Screenshots"] = "Skjermbilete", ["Screenshot on level up"] = "Skjermbilete ved nytt nivå",
    ["Screenshot on first dungeon clear"] = "Skjermbilete ved første fangehol", ["Hide interface in screenshots"] = "Gøym grensesnittet på skjermbileta",
    ["History / graph"] = "Historikk / graf", ["Deaths"] = "Dødsfall", ["First zone visit"] = "Første besøk i eit område",
    ["Every 100 quests"] = "Kvart 100. oppdrag", ["Profession milestones"] = "Yrkesmål", ["Dungeon / raid milestones"] = "Fangehol- og raidmål",
    ["Mount milestones"] = "Ridedyrmål", ["Reputation rank"] = "Omdøme-steg", ["Class ability unlock"] = "Ny klasseevne",
    ["PvP rank"] = "PvP-grad", ["Honor level"] = "Ærenivå", ["Achievements"] = "Bragder",
    ["Level and XP"] = "Nivå og XP", ["Class"] = "Klasse", ["Race and male/female"] = "Rase og kjønn", ["Faction"] = "Fraksjon",
    ["Guild"] = "Laug", ["Equipment"] = "Utstyr", ["Location"] = "Stad", ["Played time"] = "Speletid", ["Professions"] = "Yrke",
    ["Total deaths"] = "Dødsfall totalt", ["Completed quests"] = "Fullførte oppdrag",
    -- Chat messages
    ["Notification queue is full; wait for previews to finish."] = "Varselkøen er full; vent til førehandsvisingane er ferdige.",
    ["In-game update blocked/uncertain; see /wstatus popup status."] = "Oppdateringa vart blokkert eller er usikker; sjå /wstatus popup status.",
    ["Usage: /wstatus share <character name>"] = "Bruk: /wstatus share <figurnamn>",
    ["Chat is restricted right now; try again later."] = "Chatten er avgrensa no; prøv igjen seinare.",
    ["Whispers are not available in this client."] = "Kviskring er ikkje tilgjengeleg i denne klienten.",
    ["Recent buffer is full; older events remain in History."] = "Bufferen er full; eldre hendingar ligg att i Historikk.",
    ["Character is not ready."] = "Figuren er ikkje klar.", ["Saved data is unreadable. WoW Status leaves it unchanged."] = "Dei lagra dataa kan ikkje lesast. WoW Status lèt dei vere som dei er.", ["Could not upgrade saved data (step %d). It will be tried again later."] = "Kunne ikkje oppgradere lagra data (steg %d). Det blir prøvd att seinare.",
    ["Waiting for readable player identity. Collection will retry after loading/combat."] =
        "Ventar på at spelaridentiteten kan lesast. Prøver igjen etter lasting eller kamp.",
    ["Set the same group ID as your friends in Options > AddOns > WoW Status."] = "Bruk same gruppe-ID som venene dine i Innstillingar > AddOns > WoW Status.",
    ["Milestone choices are on the main WoW Status page."] = "Måla vel du på hovudsida til WoW Status.",
    ["Manual announcements have been removed. Milestones are detected automatically."] = "Manuelle kunngjeringar er fjerna. Måla blir oppdaga automatisk.",
    ["Screenshots are not available in this client."] = "Skjermbilete er ikkje tilgjengeleg i denne klienten.",
    ["A screenshot is already being taken."] = "Det blir alt teke eit skjermbilete.",
    ["Minimap button distance reset."] = "Avstanden til minikartknappen er tilbakestilt.",
    ["Show the minimap button"] = "Vis minikartknappen",
    ["Minimap button hidden."] = "Minikartknappen er gøymd.",
    ["Minimap button shown."] = "Minikartknappen er synleg att.",
    ["Open it with /wstatus, or with the key binding under Key Bindings."]
        = "Opne han med /wstatus, eller med tastebindinga under Tastebindingar.",
    -- Labs: experimental features (#222)
    ["Labs"] = "Laben", ["Labs: experimental features"] = "Laben: eksperiment",
    ["Experiments in progress. Each one only changes things for you, and every one starts switched off."]
        = "Eksperiment under arbeid. Kvart av dei endrar berre ting for deg, og alle startar avslåtte.",
    ["No experiments in this version yet."] = "Ingen eksperiment i denne utgåva enno.",
    ["Turn all experiments off"] = "Slå av alle eksperiment",
    ["Search:"] = "Søk:", ["Clear"] = "Tøm",
    ["%d matches in the whole log"] = "%d treff i heile loggen",
    ["Nothing in the log matches that."] = "Ingenting i loggen passar med det.",

    -- Compare two characters (#160)
    ["Compare"] = "Samanlikn", ["Compare two"] = "Samanlikn to", ["Swap sides"] = "Byt side",
    ["Choose a character"] = "Vel ein figur",
    ["Choose two characters to put their numbers side by side."]
        = "Vel to figurar for å setje tala deira side om side.",
    ["Neither of them has shared any numbers yet."] = "Ingen av dei har delt tal enno.",
    ["not shared"] = "ikkje delt",
    ["XP into the level"] = "Røynsle inn i nivået",
    ["Played per level"] = "Spelt per nivå",

    -- Together: the group's combined totals (#167)
    ["Together"] = "Saman", ["No group"] = "Inga gruppe",
    ["Join a group to add your adventures up together."] = "Bli med i ei gruppe for å leggje eventyra saman.",
    ["Since you joined"] = "Sidan du blei med", ["Since"] = "Sidan",
    ["This week together:"] = "Denne veka saman:",
    ["Nothing added yet this week."] = "Ingenting lagt til denne veka enno.",
    ["Hours played"] = "Timar spelte", ["Levels between us"] = "Nivå mellom oss",
    ["Quests finished"] = "Oppdrag fullførte", ["Deaths survived"] = "Dødsfall overlevde",
    ["Monsters felled"] = "Udyr felte", ["Mounts earned"] = "Ridedyr vunne",
    ["Gold gathered"] = "Gull samla", ["Zones discovered"] = "Område funne",
    ["quest milestone"] = "oppdragsmål", ["quest milestones"] = "oppdragsmål",
    ["new zone"] = "nytt område", ["new zones"] = "nye område",
    ["dungeon"] = "fangehol", ["dungeons"] = "fangehol",
    -- Controller navigation and key bindings
    ["Open or close WoW Status"] = "Opne eller lukk WoW Status",
    ["Open the activity log"] = "Opne aktivitetsloggen",
    ["Dismiss the notification"] = "Lukk varselet",
    ["Hold the notification (while pressed)"] = "Hald varselet framme (medan tasten er nede)",
    ["Open or close the Overview page"] = "Opne eller lukk sida Oversikt",
    ["Open or close the Characters page"] = "Opne eller lukk sida Figurar",
    ["Open or close the Leaderboard page"] = "Opne eller lukk sida Toppliste",
    ["Open or close the Records page"] = "Opne eller lukk sida Rekordar",
    ["Controller navigation is off. Type /wstatus controller on to turn it on."] = "Kontrollnavigering er av. Skriv /wstatus controller on for å slå ho på.",
    ["Controller navigation steps aside for ConsolePort."] = "Kontrollnavigeringa viker for ConsolePort.",
    ["Controller navigation is on; it starts when gamepad support is enabled in the game's options."] = "Kontrollnavigering er på; ho startar når handkontroll er slått på i innstillingane til spelet.",
    ["Controller navigation is on: D-pad moves, A selects, B goes back, LB/RB change page, the right stick scrolls."] = "Kontrollnavigering er på: krossen flyttar, A vel, B går tilbake, LB/RB byter side, høgre stikke rullar.",
    ["Usage: /wstatus controller [on | off]"] = "Bruk: /wstatus controller [on | off]",
    ["Activity syncs automatically when group members log in."] = "Aktiviteten blir synka automatisk når gruppemedlemer loggar inn.",
    ["Sharing paused."] = "Delinga er sett på pause.", ["Filter updated."] = "Filteret er oppdatert.", ["Invalid filter value."] = "Ugyldig filterverdi.",
    ["Enable profession sharing first. Names are player-entered, not verified skill ranks."] =
        "Slå på yrkesdeling først. Namna er skrivne av spelaren, ikkje stadfesta ferdigheitsnivå.",
    ["Shared profession labels updated. /reload to export."] = "Delte yrkesnamn er oppdaterte. /reload for å eksportere.",
    -- /wstatus popup messages
    ["Group membership automatically enables updates. Remove a group in /wstatus groups to leave it."] =
        "Gruppemedlemskap slår på oppdateringar automatisk. Fjern ei gruppe i /wstatus groups for å forlate henne.",
    ["Popup reception enabled for your selected group IDs. Use /wstatus groups to choose them."] =
        "Mottak av varsel er slått på for dei valde gruppe-ID-ane dine. Bruk /wstatus groups for å velje dei.",
    ["Popup reception and broadcasts are off."] = "Mottak og sending av varsel er slått av.",
    ["Group IDs control popup channels. Edit /wstatus groups instead."] = "Gruppe-ID-ane styrer varselkanalane. Endre /wstatus groups i staden.",
    ["Use trust Character-Realm [optional friend label]."] = "Bruk trust Figur-Rike [valfritt vennenamn].",
    ["Trust list is full."] = "Lista over klarerte er full.",
    ["Join a group first, or use /wstatus popup on for a local preview."] =
        "Bli med i ei gruppe først, eller bruk /wstatus popup on for ei lokal førehandsvising.",
    ["Popup commands: on | off | send on/off | sound on/off | channel WStatusNAME"] =
        "Varselkommandoar: on | off | send on/off | sound on/off | channel WStatusNAMN",
    ["Trust: trust Character-Realm [friend label] | untrust Character-Realm. Test: test. Diagnostics: status."] =
        "Klarering: trust Figur-Rike [vennenamn] | untrust Figur-Rike. Test: test. Feilsøking: status.",
    ["Synthetic level 10 event requested; requires sharing, level field and level storage."] =
        "Testhending for nivå 10 er bede om; krev deling, nivåfelt og nivålagring.",
    ["Player: Alex (example)\nRace: Human · Male\nFaction: Alliance\nLevel: 33\nXP progress: 37.5% (15,000 / 40,000)\nTotal deaths: 15\nCompleted quests: 236\nLocation: Stranglethorn Vale\nTailoring: 185 / 225\nEnchanting: 150 / 225\n\nExample values only. Death totals are tracked from installation;\nolder deaths are unavailable on Classic Era."] =
        "Spelar: Alex (eksempel)\nRase: Menneske · Mann\nFraksjon: Alliance\nNivå: 33\nXP-framgang: 37,5 % (15 000 / 40 000)\nDødsfall totalt: 15\nFullførte oppdrag: 236\nStad: Stranglethorn Vale\nTailoring: 185 / 225\nEnchanting: 150 / 225\n\nBerre eksempelverdiar. Dødsfall blir talde frå installasjonen;\neldre dødsfall er ikkje tilgjengelege i Classic Era.",
    ["Legacy single-service upload selected. Only use with your own configured /link credentials."] =
        "Gammal enkeltteneste-opplasting er vald. Bruk berre med dine eigne /link-innloggingsdata.",
    -- Status line and minimap
    ["now"] = "no", ["hit"] = "nådde", ["Left-click: Activity log"] = "Venstreklikk: Aktivitetslogg",
    ["Right-click: Options"] = "Høgreklikk: Innstillingar", ["Drag to move"] = "Dra for å flytte",
    -- Language and What's new
    ["Caption personality:"] = "Personlegdom i kommentarane:", ["Caption personalities:"] = "Personlegdomar i kommentarane:",
    ["Next personality"] = "Neste personlegdom",
    ["Reaction voice:"] = "Røyst i reaksjonane:", ["Reaction voices:"] = "Røyster i reaksjonane:",
    -- Spoken reactions (Forever)
    ["Spoken reactions"] = "Opplesne reaksjonar", ["Read friends' reactions aloud"] = "Les opp reaksjonar frå vener",
    ["Always send a voiced reaction when one is available"] = "Send alltid ein reaksjon med røyst når det finst ein",
    ["Play a sample"] = "Spel av ei prøve", ["Minutes between spoken reactions:"] = "Minutt mellom opplesne reaksjonar:",
    ["Every reaction"] = "Kvar reaksjon", ["%d min"] = "%d min",
    ["Notification duration:"] = "Kor lenge varsla står:", ["Until dismissed"] = "Til du lukkar dei",
    ["%d seconds"] = "%d sekund", ["%d%%"] = "%d %%", ["Notifications now stay until dismissed."] = "Varsla står no til du lukkar dei.",
    ["Notifications now stay for %d seconds."] = "Varsla står no i %d sekund.",
    ["Notifications stay until dismissed."] = "Varsla står til du lukkar dei.",
    ["Notifications stay for %d seconds."] = "Varsla står i %d sekund.",
    ["Use /wstatus popuptime %d-%d, or 0 to keep notifications until dismissed (%d is the default)."] =
        "Bruk /wstatus popuptime %d-%d, eller 0 for å halde varsla til du lukkar dei (%d er standard).",
    ["Volume slider for voices:"] = "Volumkontroll for røystene:", ["Dialog"] = "Dialog",
    ["Sound effects"] = "Lydeffektar", ["Master (loudest)"] = "Hovudvolum (høgast)",
    ["Only Nynorsk reactions are read aloud. Voices are AI-generated (Google Gemini)."] =
        "Berre reaksjonar på nynorsk blir lesne opp. Røystene er laga med KI (Google Gemini).",
    ["Voice pack %d is installed."] = "Røystepakke %d er installert.",
    ["Every voice comes with this download; no voice pack is needed."] =
        "Alle røystene følgjer med denne nedlastinga; du treng inga røystepakke.",
    ["Spoken reaction test:"] = "Test av opplesen reaksjon:", ["A voice is already playing."] = "Ei røyst blir alt spelt av.",
    ["No recorded voice to test here. Spoken reactions are for WoW Forever."] =
        "Inga innspelt røyst å teste her. Opplesne reaksjonar finst berre i WoW Forever.",
    ["Voice pack: not installed. Install it to hear friends' reactions read aloud."] =
        "Røystepakke: ikkje installert. Installer han for å høyre reaksjonar frå vener lesne opp.",
    ["Get the full voice pack: copy this link into your browser, unzip it into Interface/AddOns and restart WoW."] =
        "Hent heile røystepakken: kopier lenkja inn i nettlesaren, pakk ho ut i Interface/AddOns og start WoW på nytt.",
    ["Next voice"] = "Neste røyst", ["Use /wstatus voice <name>."] = "Skriv /wstatus voice <namn>.", ["Use /wstatus personality <name>."] = "Skriv /wstatus personality <namn>.",
    ["Language:"] = "Språk:", ["Reload"] = "Last på nytt", ["Reload to apply"] = "Last på nytt", ["What's new in WoW Status"] = "Nytt i WoW Status",
    ["Use /wstatus debug on or /wstatus debug off."] = "Bruk /wstatus debug on eller /wstatus debug off.",
    ["Debug log on. Type /reload to save it for reading."] = "Feilsøkingslogg på. Skriv /reload for å lagra han.",
    ["Debug log off."] = "Feilsøkingslogg av.",
    ["Use /wstatus language nn for Nynorsk or /wstatus language en for English."] =
        "Bruk /wstatus language nn for nynorsk eller /wstatus language en for engelsk.",
    -- Notifications
    ["Quests (tracked)"] = "Oppdrag (spora)", ["tracked"] = "spora",
    ["Congratulate"] = "Gratuler", ["Pay respects"] = "Vis respekt", ["Tease a little"] = "Ert litt",
    ["Welcome them"] = "Ynsk velkomen", ["Celebrate the level"] = "Feir nivået", ["Wish a good journey"] = "Ynsk god tur",
    ["Congrats!"] = "Gratulerer!",
    ["Congrats on the new gear!"] = "Gratulerer med det nye utstyret!",
    ["Congrats on all those quests!"] = "Gratulerer med alle dei oppdraga!",
    ["Congrats on the new profession rank!"] = "Gratulerer med det nye yrkesnivået!",
    ["Congrats on the clear!"] = "Gratulerer med sigeren!", ["Congrats on the boss kill!"] = "Gratulerer med bossdrapet!",
    ["Congrats on the new mount!"] = "Gratulerer med det nye ridedyret!",
    ["Congrats on the epic mount!"] = "Gratulerer med det episke ridedyret!",
    ["Congrats on the new reputation!"] = "Gratulerer med det betre omdømet!",
    ["Congrats on the new ability!"] = "Gratulerer med den nye evna!",
    ["Congrats on the promotion!"] = "Gratulerer med opprykket!", ["Congrats on the record!"] = "Gratulerer med rekorden!", ["Welcome!"] = "Velkomen!", ["You whispered"] = "Du kviskra",
    -- Records
    ["No dungeon clear recorded yet."] = "Ingen rydding av fangehol er registrert enno.",
    ["Firsts in"] = "Rekordar i", ["Join a group to compete for records with your friends."] =
        "Bli med i ei gruppe for å kjempe om rekordar med venene dine.",
    ["before WoW Status, by"] = "før WoW Status, seinast", ["nobody yet"] = "ingen enno",
    ["No recaps yet. One is written after each play session."] = "Ingen samandrag enno. Eitt blir skrive etter kvar speleøkt.",
    ["Session recaps"] = "Øktsamandrag", ["A new record in"] = "Ein ny rekord i",
    ["First in the group to die"] = "Først i gruppa til å døy", ["First in the group to die!"] = "Først i gruppa til å døy!",
    ["First dungeon clear"] = "Første fangehol rydda", ["First dungeon clear!"] = "Første fangehol rydda!",
    ["First mount"] = "Første ridedyr", ["First mount!"] = "Første ridedyr!",
    ["First raid boss"] = "Første raidsjef", ["First raid boss!"] = "Første raidsjef!",
    ["First epic mount"] = "Første episke ridedyr", ["First epic mount!"] = "Første episke ridedyr!",
    ["First epic item"] = "Første episke gjenstand", ["First epic item!"] = "Første episke gjenstand!",
    ["First Artisan profession"] = "Første yrke på Kunstnar-nivå", ["First Artisan profession!"] = "Første yrke på Kunstnar-nivå!",
    -- Leaderboard
    ["Join a group to compare your characters with friends."] = "Bli med i ei gruppe for å samanlikne figurane dine med venene dine.",
    ["Firsts"] = "Rekordar", ["Leaderboard"] = "Toppliste", ["Sort:"] = "Sorter:", ["Level"] = "Nivå",
    ["Character"] = "Figur", ["Nobody in this group yet. Members appear when their character list arrives."] =
        "Ingen i denne gruppa enno. Medlemer dukkar opp når figurlista deira kjem fram.",
    -- Death details
    ["killed by"] = "drepen av", ["Falling"] = "fall", ["Drowning"] = "drukning", ["Fatigue"] = "utmatting",
    ["Fire"] = "eld", ["Lava"] = "lava", ["Slime"] = "slim",
    -- Reactions
    ["from"] = "frå", ["Git Good"] = "Øv deg litt meir, så døyr du kanskje sjeldnare!", ["GZ!"] = "Eg ynskjer deg hjarteleg til lukke med det nye nivået!", ["F"] = "Eg tek av meg hjelmen og bøyer hovudet i sorg.",
    -- Recent reactions (#171)
    ["Reactions"] = "Reaksjonar", ["New"] = "Ny", ["You to"] = "Du til",
    ["Reactions from friends to your updates, and the ones you sent. Choose one to see its update."] =
        "Reaksjonar frå vener på oppdateringane dine, og dei du sende. Vel éin for å sjå oppdateringa.",
    ["No reactions yet. When friends react to your updates, or you to theirs, they appear here."] =
        "Ingen reaksjonar enno. Når vener reagerer på oppdateringane dine, eller du på deira, dukkar dei opp her.",
    -- New version notice
    ["is available"] = "er tilgjengeleg", ["you have"] = "du har",
    ["Get it at wow.frankvalde.com; the CurseForge app can take a few hours."] =
        "Hent han på wow.frankvalde.com; CurseForge-appen kan bruke nokre timar.",
    ["Update available:"] = "Ny versjon tilgjengeleg:",
    -- Activity filters
    ["Type:"] = "Type:", ["Person:"] = "Person:", ["Level-ups"] = "Nye nivå", ["Deaths"] = "Dødsfall", ["Zones"] = "Område",
    ["Quests"] = "Oppdrag", ["Dungeons and raids"] = "Fangehol og raid", ["Mounts"] = "Ridedyr", ["Armor"] = "Rustning",
    ["Reputation"] = "Omdøme", ["Class abilities"] = "Klasseevner", ["PvP"] = "PvP", ["Joins"] = "Nye medlemer",
    ["Recaps"] = "Samandrag",
    -- Overview
    ["Your status is not available right now."] = "Statusen din er ikkje tilgjengeleg no.",
    ["You are level %d"] = "Du er på nivå %d", ["maximum level"] = "høgaste nivå",
    [" · %d%% of the way to level %d"] = " · %d %% av vegen til nivå %d", ["Maximum level"] = "Høgaste nivå",
    ["%d%% to level %d"] = "%d %% til nivå %d", ["Deaths:"] = "Dødsfall:", ["Quests:"] = "Oppdrag:",
    ["Join a group in Options to share with friends."] = "Bli med i ei gruppe under Innstillingar for å dele med vener.",
    ["online"] = "pålogga", ["group"] = "gruppe", ["groups"] = "grupper",
    ["Nobody else is online right now."] = "Ingen andre er pålogga no.",
    ["Since you were last here"] = "Sidan du var her sist",
    ["This summary starts after your next logout."] = "Samandraget startar etter at du loggar ut neste gong.",
    ["Nothing new from your group since you were last here."] = "Ikkje noko nytt frå gruppa di sidan du var her sist.",
    ["…and %d more lines in the Activity tab."] = "…og %d fleire linjer i Aktivitet-fana.",
    ["Your group"] = "Gruppa di", ["Latest records"] = "Nyaste rekordar",
    -- Not seen for a while (#172)
    ["Not seen for a while:"] = "Ikkje sett på ei stund:", ["more than %d days"] = "meir enn %d dagar",
    ["%d days"] = "%d dagar", ["%d more"] = "%d til", ["Off"] = "Av",
    ["Friends not seen for a while"] = "Vener som ikkje er sette på ei stund",
    ["List friends on the Overview after this many quiet days:"] = "Vis vener på Oversikt etter så mange stille dagar:",
    ["No records yet. The first to reach a milestone in your group earns it."] = "Ingen rekordar enno. Den første i gruppa som når eit mål, får han.", ["All"] = "Alle", ["Mine"] = "Mine", ["Friends"] = "Vener", ["Show all"] = "Vis alle",
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
    ["BATTLEGROUND WON!"] = "SLAGMARKA VANN!", ["BATTLEGROUND LOST"] = "SLAGMARKA TAPT", ["ACHIEVEMENT EARNED!"] = "NY BRAGD!",
    ["HONOR LEVEL UP!"] = "NYTT ÆRENIVÅ!", ["A NEW FIRST!"] = "EIN NY REKORD!",
    ["SESSION RECAP"] = "ØKTSAMANDRAG", ["QUEST COMPLETED"] = "OPPDRAG FULLFØRT",
    ["EQUIPMENT"] = "UTSTYR", ["TRACKING STARTED"] = "SPORING STARTA",
    ["MAXIMUM LEVEL!"] = "HØGASTE NIVÅ!",
    ["RARE ARMOR EQUIPPED!"] = "SJELDAN RUSTNING PÅ!", ["EPIC ARMOR EQUIPPED!"] = "EPISK RUSTNING PÅ!",
    ["LEGENDARY ARMOR EQUIPPED!"] = "LEGENDARISK RUSTNING PÅ!",
}, {
    {"^Reached level (%d+)!$", "Nådde nivå %1!"},
    {"^Congrats on level (%d+)!$", "Gratulerer med nivå %1!"},
    {"^reached level (%d+)!(.*)$", function(level, rest)
        return "nådde nivå " .. level .. "!" .. rest:gsub(" %((%d+) recorded level%-ups%)", " (%1 registrerte nivå)")
    end},
    {"^Total deaths: (%d+)$", "Dødsfall totalt: %1"},
    {"^Died — total tracked deaths: (%d+)$", "Døydde — dødsfall totalt: %1"},
    {"^Completed (%d+) quests!$", "Fullførte %1 oppdrag!"},
    {"^Entered (.+)$", "Kom til %1"},
    -- One line per finished battleground, instead of one per death in it.
    {"^Won (.+)$", "Vann %1"},
    {"^Lost (.+)$", "Tapte %1"},
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
    {"^Earned achievement: (.+)$", "Fekk bragda %1"},
    {"^Promoted to (.+)$", "Forfremja til %1"},
    {"^Reached honor level (%d+)$", "Nådde ærenivå %1"},
    {"^Equipped (.+)$", "Tok på %1"},
    {"^Looted (.+)$", "Plyndra %1"},
    {"^Tracking started at level (%d+)$", "Sporinga starta på nivå %1"},
    {"^First to reach level (%d+)(!?)$", "Først til nivå %1%2"},
    {"^Enjoy (.+)!$", "Kos deg i %1!"},
    {"^Language: (%a+)%. Type /reload to change every window%.$", function(name)
        return "Språk: " .. (name == "English" and "engelsk" or "nynorsk") .. ". Skriv /reload for å endre alle vindauga."
    end},
    {"^Theme: (.-) · size (%d+)%%$", function(name, size)
        local themes = {Achievement="Bragd", Night="Natt", Journal="Dagbok", Faction="Fraksjon",
            ["High contrast"]="Høg kontrast"}
        return "Tema: " .. (themes[name] or name) .. " · storleik " .. size .. " %"
    end},
    {"^Shown at (%d+)%% to fit the screen$", "Vist med %1 %% så det får plass på skjermen"},
    {"^Notification size %((%d+)–(%d+)%%%)$", "Varselstorleik (%1–%2 %%)"},
    {"^Notification size: (%d+)%%%.$", "Varselstorleik: %1 %%."},
    {"^You already shared WoW Status with (.+) in the last hour%.$", "Du har alt delt WoW Status med %1 den siste timen."},
    {"^The whisper to (.+) could not be sent%.$", "Kviskringa til %1 kunne ikkje sendast."},
    {"^Shared the WoW Status link with (.+)%.$", "Delte WoW Status-lenkja med %1."},
    {"^Minimap button distance set to (.+)%.$", "Avstanden til minikartknappen er sett til %1."},
    {"^(%d+) characters$", "%1 figurar"},
    {"^from (%d+) of (%d+)$", "frå %1 av %2"},
    {"^This addon folder targets (.+)%. Collection is disabled on this client%.$", "Denne tilleggsmappa er for %1. Innsamlinga er slått av i denne klienten."},
    {"^last seen (%d+)m ago$", "sist sett for %1 min sidan"},
    {"^last seen (%d+)h ago$", "sist sett for %1 t sidan"},
    {"^last seen (%d+)d ago$", "sist sett for %1 d sidan"},
    {"^v(%d+%.%d+%.%d+)$", "v%1"},
    -- Overview facts ("Since you were last here")
    {"^reached level (%d+)$", "nådde nivå %1"},
    {"^gained (%d+) levels %(now (%d+)%)$", "gjekk opp %1 nivå (no %2)"},
    {"^gained (%d+) levels$", "gjekk opp %1 nivå"},
    {"^cleared a dungeon$", "rydda eit fangehol"},
    {"^cleared (.+)$", "rydda %1"},
    {"^died in Hardcore$", "døydde i hardkjernemodus"},
    {"^(%d+) levels without a death!$", "%1 nivå utan å døy!"},
    {"^(%d+) weeks without a death!$", "%1 veker utan å døy!"},
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
    {"^earned an achievement$", "fekk ei bragd"},
    {"^earned (%d+) achievements$", "fekk %1 bragder"},
    {"^joined the group$", "vart med i gruppa"},
    {"^an update$", "ei oppdatering"},
    {"^(%d+) updates$", "%1 oppdateringar"},
    {"^Session recap: (.+)$", function(body) return "Øktsamandrag: " .. recap(body) end},
    {"^(This morning)(.+)$", function(a, b) return recap(a .. b) end},
    {"^(This afternoon)(.+)$", function(a, b) return recap(a .. b) end},
    {"^(Tonight)(.+)$", function(a, b) return recap(a .. b) end},

})

-- Armor headings by slot: the adjective follows the noun's gender and number
-- (masculine/feminine, neuter, plural): "SJELDAN RING", "SJELDANT SKJOLD", "SJELDNE HANSKAR".
do
    local ADJECTIVES = {RARE={"SJELDAN", "SJELDANT", "SJELDNE"}, EPIC={"EPISK", "EPISK", "EPISKE"},
        LEGENDARY={"LEGENDARISK", "LEGENDARISK", "LEGENDARISKE"}}
    local PIECES = {HELMET={"HJELM", 1}, NECKLACE={"HALSSMYKKE", 2}, SHOULDERS={"SKULDERPLATER", 3},
        SHIRT={"SKJORTE", 1}, CHESTPIECE={"BRYSTPANSAR", 2}, ROBE={"KJORTEL", 1}, BELT={"BELTE", 2},
        LEGGINGS={"BUKSER", 3}, BOOTS={"STØVLAR", 3}, BRACERS={"ARMVERN", 3}, GLOVES={"HANSKAR", 3},
        RING={"RING", 1}, TRINKET={"TALISMAN", 1}, CLOAK={"KAPPE", 1}, SHIELD={"SKJOLD", 2},
        ["OFF-HAND"]={"HANDGJENSTAND", 1}, TABARD={"VÅPENKJOLE", 1}, RELIC={"RELIKVIE", 1}, ARMOR={"RUSTNING", 1}}
    WoWStatusLocale.add({}, {{"^(%u+) ([%u%-]+) EQUIPPED!$", function(quality, piece)
        local adjective, noun = ADJECTIVES[quality], PIECES[piece]
        if adjective and noun then return adjective[noun[2]] .. " " .. noun[1] .. " PÅ!" end
    end}})
end

-- Nynorsk Classic reaction whispers: choose one line per notification, while
-- the button keeps its short action label. "{zone}" stands for the zone's name. A
-- friend's client links every line to its kind of event, in either language.
WoWStatusLocale.POOLS = {
    ["GZ!"] = {
        "Eg ynskjer deg hjarteleg til lukke med det nye nivået!",
        "Gratulerer! No er du endå litt farlegare.",
        "Endå eit nivå! Snart er du uovervinneleg.",
        "Hurra for deg og det nye nivået ditt!",
        "Sjå på deg, du veks så det knakar!",
        "Eit nivå til i boka. Godt jobba!",
        "Til lukke! Monstera skjelv allereie.",
        "Du har gått opp eit nivå! Eg er stolt av deg.",
        "Nytt nivå, nye moglegheiter. Til lukke!",
        "Opp og fram! Gratulerer med nivået.",
        "Det var på tide! Gratulerer.",
        "Du blir sterkare for kvar dag. Til lukke!",
        "Heile Azeroth jublar for det nye nivået ditt!",
        "Gratulerer! No kan du slå litt hardare.",
        "Eit steg nærare toppen. Godt gjort!",
        "Ding! Det høyrdest heilt hit.",
        "Hipp hipp hurra for det nye nivået!",
        "Du er ustoppeleg! Til lukke med nivået.",
        "Gratulerer! Ein kvilepause er velfortent no.",
        "Nivå opp! Det må feirast med ein brødbit.",
    },
    ["F"] = {
        "Eg tek av meg hjelmen og bøyer hovudet i sorg.",
        "Kvil i fred, tapre eventyrar. Vi sest ved ånda.",
        "Det var ein heltemodig død. Nesten.",
        "Eg tenner eit lys for deg i Stormwind.",
        "Du fall, men du fall med stil.",
        "Eit stille augneblink for den falne helten.",
        "Kroppen ligg der, men motet lever vidare.",
        "Det gjekk ikkje heilt etter planen, gjorde det vel?",
        "Søv godt. Vi hentar deg på kyrkjegarden.",
        "Ånda ventar på deg med opne armar.",
        "Inga skam i å døy. Berre litt.",
        "Du kjempa godt. Fienden kjempa betre.",
        "Eg syng ein sorgsong for deg i kveld.",
        "Rustninga di saknar deg alt.",
        "Det der var vondt å sjå på.",
        "Kondolerer. Reparasjonsrekninga blir stor.",
        "Ein liten død om dagen held legen borte.",
        "Vi gløymer deg aldri. I alle fall ikkje før middag.",
        "Respekt. Det var ein ærefull exit.",
        "Spring tilbake, helt. Liket ditt saknar deg.",
    },
    ["Enjoy"] = {
        "Kos deg i {zone}!",
        "God tur til {zone}!",
        "Ha det fint i {zone}!",
        "Pass deg for monstera i {zone}!",
        "Send eit postkort frå {zone}!",
        "{zone}? For ein vakker stad!",
        "Nyt utsikta i {zone}!",
        "Ta med deg ein suvenir frå {zone}!",
        "Eg har høyrt at {zone} er fint på denne tida av året.",
        "Ikkje gå deg vill i {zone}!",
        "Velkomen til {zone}, eventyrar!",
        "{zone} ventar på deg. God fornøying!",
        "Utforsk kvar krok av {zone}!",
        "Hugs kartet når du vandrar rundt i {zone}!",
        "Lukke til i {zone}!",
        "Måtte vegen gjennom {zone} vere trygg!",
        "Eg er misunneleg. {zone} står på lista mi!",
        "Finn skatten som gøymer seg i {zone}!",
        "Ha ein strålande tur i {zone}!",
        "Sei hei til alle i {zone} frå meg!",
    },
}

-- Character equipment snapshots and combat attributes.
W.add({
    ["Equipped gear"] = "Utstyr i bruk", ["Refresh gear"] = "Oppdater utstyr",
    ["Requesting equipment…"] = "Hentar utstyr…",
    ["Average item level"] = "Snittnivå på utstyr", ["Average item level:"] = "Snittnivå på utstyr:",
    ["XP unavailable"] = "XP ikkje tilgjengeleg",
    ["Combat attributes"] = "Kampeigenskapar", ["Last reported:"] = "Sist meldt:",
    ["Equipment sharing is off."] = "Deling av utstyr er slått av.",
    ["No snapshot yet. Their owner needs the latest addon and must be online to share it."] = "Inga lagra oversikt enno. Eigaren treng nyaste tillegg og må vere pålogga for å dele.",
    ["Hover an item for its full tooltip. Stats include buffs at the time recorded."] = "Hald musa over ein gjenstand for detaljar. Tala tek med styrkingar då dei vart lagra.",
    ["Live appearance"] = "Utsjånad no", ["Saved equipment · race portrait"] = "Lagra utstyr · raseportrett",
    ["Equipment and combat stats"] = "Utstyr og kamptal", ["Not available"] = "Ikkje tilgjengeleg",
    ["Empty"] = "Tom", ["Item"] = "Gjenstand", ["Health"] = "Helse", ["Mana"] = "Mana",
    ["Strength"] = "Styrke", ["Agility"] = "Smidigheit", ["Stamina"] = "Uthald",
    ["Intellect"] = "Intellekt", ["Spirit"] = "Ånd", ["Armor"] = "Rustning",
    ["Attack power"] = "Åtaksstyrke", ["Ranged attack power"] = "Avstandsstyrke",
    ["Spell power"] = "Tryllekraft", ["Bonus healing"] = "Ekstra læking",
    ["Melee critical strike"] = "Kritisk nærkampstreff", ["Spell critical strike"] = "Kritisk trylletreff",
    ["Dodge"] = "Unnviking", ["Parry"] = "Parering", ["Block"] = "Blokkering",
    ["Haste"] = "Hast", ["Mastery"] = "Meistring", ["Versatility"] = "Allsidigheit",
    ["Head"] = "Hovud", ["Neck"] = "Hals", ["Shoulders"] = "Skuldrer", ["Cloak"] = "Kappe",
    ["Chest"] = "Bryst", ["Shirt"] = "Skjorte", ["Tabard"] = "Våpenkjortel", ["Wrists"] = "Handledd",
    ["Hands"] = "Hender", ["Waist"] = "Liv", ["Legs"] = "Bein", ["Feet"] = "Føter",
    ["Finger 1"] = "Finger 1", ["Finger 2"] = "Finger 2", ["Trinket 1"] = "Prydgjenstand 1",
    ["Trinket 2"] = "Prydgjenstand 2", ["Main hand"] = "Hovudhand", ["Off hand"] = "Andre hand",
    ["Ranged / relic"] = "Avstand / relikvie", ["Ammunition"] = "Ammunisjon",
    ["Character visibility"] = "Synlege figurar",
    ["Characters shown to friends"] = "Figurar som venene ser",
    ["Untick bank alts to hide them from everyone's character list and leaderboard."] = "Fjern haken for å gøyme bankfigurar frå figurlista og topplista til alle.",
    -- Unit tooltip block (#183).
    ["Friends' tooltips"] = "Info når musa er over vener",
    ["Show WoW Status in group members' tooltips"] = "Vis WoW Status-info når musa er over gruppemedlemer",
    ["Values shown, top first:"] = "Verdiar som blir viste, den øvste først:", ["Move up"] = "Flytt opp",
    ["Level progress"] = "Nivåframgang",
    -- Muting one friend (#169)
    ["Mute"] = "Demp", ["Muted"] = "Dempa", ["Hidden"] = "Gøymd", ["muted"] = "dempa", ["hidden"] = "gøymd",
    ["Show popups"] = "Vis varsel", ["Log only"] = "Berre logg", ["Hide completely"] = "Gøym heilt",
    ["Unmute"] = "Opphev demping", ["Muted friends"] = "Dempa vener", ["this player"] = "denne spelaren",
    ["All characters of"] = "Alle figurane til", ["all characters"] = "alle figurar",
    ["Stop this friend's popups without leaving the group. Only you can see this; nothing is sent."] =
        "Stopp varsla frå denne venen utan å gå ut av gruppa. Berre du ser dette; ingenting blir sendt.",
    ["Muted friends stay in your groups. Log only keeps their updates in the log without popups; Hide completely also leaves them out of the log, records and leaderboard. Nothing is sent and they are never told."] =
        "Dempa vener blir verande i gruppene dine. «Berre logg» held oppdateringane deira i loggen utan varsel; «Gøym heilt» held dei òg utanfor loggen, rekordane og topplista. Ingenting blir sendt, og dei får aldri vite det.",
    ["Could not save: unmute someone in Muted friends first."] = "Kunne ikkje lagre: opphev ei demping i «Dempa vener» først.",
    ["Nobody is muted. Mute a friend from their profile on the Characters page."] =
        "Ingen er dempa. Demp ein ven frå profilen deira på Figurar-sida.",
})
-- Diagnostics page (#153). The report itself stays English.
W.add({
    ["Diagnostics"] = "Diagnostikk",
    ["1 error recorded since you last looked."] = "1 feil registrert sidan du sist såg.",
    ["%d errors recorded since you last looked."] = "%d feil registrerte sidan du sist såg.",
    ["No new errors since you last looked."] = "Ingen nye feil sidan du sist såg.",
    ["Copy this report into a bug report on GitHub or Discord. Nothing is sent automatically."] =
        "Kopier denne rapporten inn i ein feilrapport på GitHub eller Discord. Ingenting vert sendt av seg sjølv.",
    ["Select all"] = "Merk alt",
    ["Small blue squares = level-ups; large orange squares = first observation. Gaps stay disconnected."] =
        "Små blå ruter = nye nivå; store oransje ruter = første observasjon. Hol vert ikkje kopla saman.",
    ["Clear errors"] = "Tøm feillista",
    ["WoW Status errors recorded: %d. They can be read here once the character is ready."] =
        "Feil registrerte i WoW Status: %d. Dei kan lesast her når figuren er klar.",
})
-- "Play together now" on the Characters page (#156).
W.add({
    ["Play together now"] = "Spel saman no", ["%d within %d levels"] = "%d innanfor %d nivå", ["%d within 1 level"] = "%d innanfor 1 nivå",
    ["Level range: ±%d"] = "Nivåspenn: ±%d", ["Your level is not known yet."] = "Nivået ditt er ikkje kjent enno.",
    ["No friends who share their list are online right now."] = "Ingen vener som deler lista si, er pålogga no.",
    ["No online friends within your level range."] = "Ingen pålogga vener innanfor nivåspennet ditt.",
    ["Closest level first."] = "Nærast nivå først.",
    ["Whisper"] = "Kviskre", ["Invite"] = "Inviter", ["Invite to your group"] = "Inviter til gruppa di",
    ["Already in your group"] = "Alt i gruppa di", ["Different faction"] = "Anna fraksjon",
    ["Invite sent"] = "Invitasjon sendt",
    ["Only the group leader can invite"] = "Berre gruppeleiaren kan invitere",
    ["Your group is full"] = "Gruppa di er full",
})
-- What is shared (#152): the guide step and the /wstatus privacy page.
W.add({
    ["What friends can see"] = "Kva venene ser",
    ["Apart from whispers you click to send, WoW Status shares only with the members of your groups, through the game's own whispers. Nothing goes to a website or to the author. Read exactly what is shared, what stays on your computer and how to stop."] =
        "Utanom kviskringar du klikkar for å sende, deler WoW Status berre med medlemene i gruppene dine, gjennom kviskringane i sjølve spelet. Ingenting går til ei nettside eller til den som laga tillegget. Les nøyaktig kva som blir delt, kva som blir verande på maskina di, og korleis du stoppar det.",
    ["What is shared"] = "Kva som blir delt",
    ["What WoW Status shares"] = "Kva WoW Status deler",
    ["What is sent"] = "Kva som blir sendt",
    ["A note to each group you join, saying that you joined."] =
        "Ei melding til kvar gruppe du blir med i, om at du har blitt med.",
    ["The milestones your announcement choices allow: level-ups, deaths, first zone visits, every 100 quests, profession and dungeon milestones, mounts, reputation, class abilities, PvP rank, first armor equips, and session recaps if you tick them. A death also names what killed you, and where when Location is ticked."] =
        "Måla kunngjeringsvala dine tillèt: nye nivå, dødsfall, første besøk i eit område, kvart 100. oppdrag, yrkesmål, fangehol- og raidmål, ridedyr, omdøme, klasseevner, PvP-rang, første rustning du tek på, og øktsamandrag om du har kryssa av for dei. Eit dødsfall seier òg kva som drap deg, og kvar, når Stad er kryssa av.",
    ["Your character list: the name, race, sex, class, level and XP progress of each character shown to friends, when it reached each tenth level, the player name you chose, your main in each group once you pick one, a random player ID and your addon version. A hidden character's name is still sent, marked as hidden, so friends' lists leave it out, even after you stop sharing your list."] =
        "Figurlista di: namn, rase, kjønn, klasse, nivå og XP-framgang for kvar figur venene ser, når han nådde kvart tiande nivå, spelarnamnet du valde, hovudfiguren din i kvar gruppe når du har valt ein, ein tilfeldig spelar-ID og versjonen av tillegget. Namnet på ein gøymd figur blir likevel sendt, merkt som gøymd, så lista til venene utelèt han, òg etter at du har slutta å dele lista di.",
    ["The character details you tick: played time, professions with skill levels, completed quests, gold and gold earned, monsters killed, dungeons, mounts and honor kills, total deaths, and the gear you wear with its combat stats. Friends see them change as you play."] =
        "Figurdetaljane du kryssar av for: speletid, yrke med ferdigheitsnivå, fullførte oppdrag, gull og gull tent, monster drepne, fangehol, ridedyr og æresdrap, dødsfall totalt, og utstyret du har på deg med kamptala. Venene ser dei endre seg medan du spelar.",
    ["The name of a group you choose to share with your other groups, to their members. Anyone with the name can join; turning this off cannot take back a name already shared."] =
        "Namnet på ei gruppe du vel å dele med dei andre gruppene dine, til medlemene der. Alle med namnet kan bli med; å slå dette av kan ikkje ta tilbake eit namn som alt er delt.",
    ["Only when you click: a reaction whisper such as GZ!, the homepage link from Share WoW Status, or an invitation to a group, with its name, to the friend you invite."] =
        "Berre når du klikkar: ei reaksjonskviskring som GZ!, lenkja til heimesida frå Share WoW Status, eller ein invitasjon til ei gruppe, med namnet, til venen du inviterer.",
    ["Who receives it"] = "Kven som får det",
    ["The members of your groups. Updates travel as the game's own addon whispers to the members it finds in each group's chat channel, and friends who are online pass them on to members who were offline."] =
        "Medlemene i gruppene dine. Oppdateringane går som spelet sine eigne tilleggskviskringar til medlemene det finn i chattekanalen til kvar gruppe, og vener som er pålogga, sender dei vidare til medlemer som var avlogga.",
    ["Your log is part of this: when a member logs in, the group's entries from the last 7 days that you sent or received are offered to them."] =
        "Loggen din er ein del av dette: når ein medlem loggar inn, blir gruppeoppføringane frå dei siste 7 dagane som du sende eller fekk, tilbodne til han.",
    ["Anyone who enters the same group name becomes a member, so give it only to people you trust."] =
        "Alle som skriv inn same gruppenamn, blir medlem, så gje det berre til folk du stolar på.",
    ["Whispers you click to send go to the player you click on, who may not be in a group with you."] =
        "Kviskringar du klikkar for å sende, går til spelaren du klikkar på, som kanskje ikkje er i ei gruppe med deg.",
    ["Nothing goes to a website, to the author or to any server except the game's own, which carries every whisper."] =
        "Ingenting går til ei nettside, til den som laga tillegget eller til nokon tenar utanom spelet sin eigen, som ber alle kviskringar.",
    ["What stays on your computer"] = "Kva som blir verande på maskina di",
    ["Screenshots, your caption personality and reaction voice (a reaction you click is whispered in that voice), your notification and window settings, quiet hours, muted friends, and log entries that went to no group."] =
        "Skjermbilete, personlegdomen i kommentarane og røysta i reaksjonane (ein reaksjon du klikkar på, blir kviskra med den røysta), innstillingane for varsel og vindauge, stille timar, dempa vener, og loggoppføringar som ikkje gjekk til noka gruppe.",
    ["What is never sent"] = "Kva som aldri blir sendt",
    ["Chat you type or read, mail, bag contents, your guild (even with Guild ticked), and which quests you hand in."] =
        "Chat du skriv eller les, post, innhaldet i sekkene, lauget ditt (sjølv med Laug kryssa av) og kva oppdrag du leverer.",
    ["The only text you type that travels is your player name and the name of a group you list or invite someone to."] =
        "Den einaste teksten du skriv som blir sendt, er spelarnamnet ditt og namnet på ei gruppe du listar eller inviterer nokon til.",
    ["How to stop"] = "Korleis du stoppar det",
    ["Untick an announcement in Options to stop sharing it and seeing it from friends, including in log sync. Character details are separate. Race, sex, class, level and XP progress travel with your character list whatever you tick, and the Faction tick changes nothing, as your race shows your faction."] =
        "Fjern krysset for ei kunngjering i Innstillingar for å slutte å dele henne og sjå henne frå vener, òg ved logsynk. Figurdetaljar er eigne val. Rase, kjønn, klasse, nivå og XP-framgang følgjer figurlista di uansett kva du kryssar av for, og krysset for Fraksjon endrar ingenting, sidan rasen viser fraksjonen din.",
    ["Untick a character under Characters shown to friends: it leaves everyone's character list, leaderboard and gear view, but its announcements still go out, and a death's details carry your player ID."] =
        "Fjern krysset for ein figur under Figurar som venene ser: han forsvinn frå figurlista, topplista og utstyrsvisinga til alle, men kunngjeringane hans blir framleis sende, og detaljane om eit dødsfall har med spelar-ID-en din.",
    ["Untick Share my character list on the Characters page: your list, details and gear stop, and your friends are told to forget your list."] =
        "Fjern krysset for Del figurlista mi på sida Figurar: lista, detaljane og utstyret ditt stoppar, og venene dine får beskjed om å gløyme lista di.",
    ["Type /wstatus pause, or untick Share my progress, to stop this character's announcements. Its character list entry and most ticked details, such as gold, kills and gear, keep going until you hide it or untick them as above."] =
        "Skriv /wstatus pause, eller fjern krysset for Del framgangen min, for å stoppe kunngjeringane til denne figuren. Plassen hans i figurlista og dei fleste detaljane du har kryssa av for, som gull, drap og utstyr, held fram til du gøymer han eller fjernar kryssa som over.",
    ["Pausing deletes all of this character's own entries from your log and its whole History / graph, for good. Unticking an announcement or detail deletes the saved entries of that kind."] =
        "Pause slettar alle dei eigne oppføringane til denne figuren frå loggen din og heile Historikk / graf for han, for godt. Å fjerne krysset for ei kunngjering eller ein detalj slettar dei lagra oppføringane av det slaget.",
    ["Remove a group in /wstatus groups to leave it."] =
        "Fjern ei gruppe i /wstatus groups for å gå ut av ho.",
    ["What is kept"] = "Kva som blir teke vare på",
    ["Your log keeps the newest 2,000 of your own entries (at most 1,000 of them sent to no group) and 2,000 received ones."] =
        "Loggen din tek vare på dei 2000 nyaste av dine eigne oppføringar (høgst 1000 av dei som ikkje gjekk til noka gruppe) og 2000 mottekne.",
    ["Apart from screenshots, which are pictures in the game's Screenshots folder, everything WoW Status saves is in WTF/Account/<account>/SavedVariables/WoWStatus.lua, with the game's backup copy WoWStatus.lua.bak beside it. Removing the addon folder deletes neither; delete both files while the game is closed."] =
        "Utanom skjermbilete, som er bilete i Screenshots-mappa til spelet, ligg alt WoW Status lagrar, i WTF/Account/<konto>/SavedVariables/WoWStatus.lua, med reservekopien WoWStatus.lua.bak til spelet ved sida av. Å fjerne mappa til tillegget slettar ingen av dei; slett begge filene medan spelet er lukka.",
    ["Friends keep the updates they already received in their own log."] =
        "Venene dine beheld oppdateringane dei alt har fått, i sin eigen logg.",
})
-- Players ranking and mains on the Leaderboard (#200).
W.add({
    ["View:"] = "Vis:", ["Players"] = "Spelarar", ["Player"] = "Spelar", ["Main:"] = "Hovudfigur:",
    ["Automatic"] = "Automatisk", ["main"] = "hovudfigur", ["highest level, no main chosen"] = "høgast nivå, ingen hovudfigur vald",
    ["Alts:"] = "Andre figurar:", ["%d more"] = "%d til", ["You"] = "Du",
})

-- Shared group goals (#157).
W.add({
    ["Group goal"] = "Gruppemål", ["Group goal reached"] = "Gruppemålet nådd", ["GOAL REACHED!"] = "MÅLET ER NÅDD!",
    ["Goal…"] = "Mål …", ["Goal:"] = "Mål:", ["Goal reached!"] = "Målet er nådd!", ["Goal reached:"] = "Målet er nådd:",
    ["No group goal yet."] = "Ikkje noko gruppemål enno.",
    ["Join a group to share a goal with friends."] = "Bli med i ei gruppe for å dele eit mål med vener.",
    ["Join a group to set a goal."] = "Bli med i ei gruppe for å setje eit mål.",
    ["Everybody reaches level %d"] = "Alle når nivå %d",
    ["Everybody completes %d quests"] = "Alle fullfører %d oppdrag",
    ["%d completed quests together"] = "%d fullførte oppdrag saman",
    ["Everybody clears %d dungeons"] = "Alle ryddar %d fangehol",
    ["%d dungeon clears together"] = "%d fangehol rydda saman",
    ["Everybody plays %d hours"] = "Alle spelar %d timar",
    ["%d hours played together"] = "%d timar spelt saman",
    ["Everybody stays under %d deaths"] = "Alle held seg under %d dødsfall",
    ["Fewer than %d deaths together"] = "Færre enn %d dødsfall saman",
    ["Over the limit this time."] = "Over grensa denne gongen.", ["Not reached in time."] = "Ikkje nådd i tide.",
    ["%d of %d deaths"] = "%d av %d dødsfall", ["%d of %d"] = "%d av %d", ["%d of %d there"] = "%d av %d er i mål",
    ["1 day left"] = "1 dag att", ["%d days left"] = "%d dagar att", ["%d days"] = "%d dagar",
    ["Join a group first."] = "Bli med i ei gruppe først.",
    ["Your character is not ready yet."] = "Figuren din er ikkje klar enno.",
    ["Only the member who set this goal can change it."] = "Berre medlemen som sette dette målet, kan endre det.",
    ["Turn on sharing your character list to set a goal."] = "Slå på deling av figurlista di for å setje eit mål.",
    ["Change this goal from the character that set it."] = "Endre dette målet frå figuren som sette det.",
    ["Your group's goal is done. Well played, all of you."] = "Gruppa har nådd målet sitt. Godt spelt, alle saman.",
    ["Another year together in your WoW Status group. Well played!"] = "Eit år til saman i WoW Status-gruppa di. Godt spelt!",
    ["Measure:"] = "Kva det gjeld:", ["Shape:"] = "Form:", ["Target:"] = "Måltal:", ["Deadline:"] = "Frist:", ["none"] = "ingen",
    ["Everybody"] = "Alle", ["Together"] = "Saman", ["Dungeon clears"] = "Fangehol rydda",
    ["Played time (hours)"] = "Speletid (timar)", ["Deaths (fewer than)"] = "Dødsfall (færre enn)",
    ["Current goal:"] = "Mål no:", ["Set by"] = "Sett av", ["No goal in this group yet."] = "Ikkje noko mål i denne gruppa enno.",
    ["Only the member who sets a goal can change or clear it. Friends see it while your character list is shared."] =
        "Berre medlemen som set eit mål, kan endre eller fjerne det. Venene ser det så lenge figurlista di er delt.",
    ["Next group"] = "Neste gruppe", ["Set goal"] = "Set mål", ["Clear goal"] = "Fjern målet",
})
-- "Where we are" on the Characters page (#168).
W.add({
    ["Where we are"] = "Kvar vi er", ["1 friend"] = "1 ven", ["%d friends"] = "%d vener",
    ["1 zone"] = "1 område", ["%d zones"] = "%d område", ["your zone"] = "området ditt",
    ["just now"] = "akkurat no", ["%d min ago"] = "for %d min sidan", ["+%d more"] = "+%d til",
    ["+1 more zone"] = "+1 område til", ["+%d more zones"] = "+%d område til",
    ["Your zone first, then the newest report."] = "Området ditt først, så den nyaste meldinga.",
    ["No online friend has reported a zone in the last %d minutes."] =
        "Ingen pålogga ven har meldt eit område dei siste %d minutta.",
})
-- Local copy of the current Activity/Records view (#176).
W.add({
    ["Export"] = "Eksporter", ["Copy export"] = "Kopier eksport",
    ["Contains character and player names. Group names are removed. Check before sharing."] =
        "Inneheld figur- og spelarnamn. Gruppenamn er fjerna. Sjå gjennom før du deler.",
    ["CSV · UTC timestamps. Select all, then copy. Use Next page for the rest. Nothing is sent."] =
        "CSV · UTC-tidsstempel. Merk alt og kopier. Bruk Neste side for resten. Ingenting blir sendt.",
    ["Previous page"] = "Førre side", ["Next page"] = "Neste side",
    ["Page %d of %d · %d rows"] = "Side %d av %d · %d rader",
    ["Preparing export: %d rows"] = "Førebur eksport: %d rader",
    ["Export is no longer available."] = "Eksporten er ikkje tilgjengeleg lenger.",
    ["Cannot export safely with the current group names."] = "Kan ikkje eksportere trygt med gruppenamna som er i bruk.",
    ["Timestamp (UTC)"] = "Tidsstempel (UTC)", ["Category"] = "Kategori", ["Details"] = "Detaljar",
    ["Period start (local date)"] = "Periodestart (lokal dato)", ["Period end (local date)"] = "Periodeslutt (lokal dato)",
    ["Reached by this date"] = "Nådd innan denne datoen",
})

-- Registry-based display language selection (#154).
W.add({["Choose language"]="Vel språk", ["Use /wstatus language"]="Bruk /wstatus language"})
-- "When we play": the group's weekly pattern from the log (#158).
W.add({
    ["Those entries carry the time they happened, so any member can see a pattern in them. When we play "
        .. "on the Overview page does exactly that, from the log on their own computer: it sends nothing "
        .. "and asks nothing, and nobody is told you looked."] =
        "Desse oppføringane ber med seg tidspunktet dei hende, så kven som helst i gruppa kan sjå eit "
        .. "mønster i dei. Når vi spelar på Oversikt-sida gjer nett det, ut frå loggen på deira eigen "
        .. "maskin: det sender ingenting og spør om ingenting, og ingen får vita at du såg.",
    ["When we play"] = "Når vi spelar", ["usually"] = "som regel", ["not enough yet"] = "ikkje nok enno", ["(you)"] = "(du)",
    ["Mon"] = "mån", ["Tue"] = "tys", ["Wed"] = "ons", ["Thu"] = "tor", ["Fri"] = "fre",
    ["Sat"] = "lau", ["Sun"] = "sun",
    ["Mondays"] = "måndagane", ["Tuesdays"] = "tysdagane", ["Wednesdays"] = "onsdagane",
    ["Thursdays"] = "torsdagane", ["Fridays"] = "fredagane", ["Saturdays"] = "laurdagane",
    ["Sundays"] = "sundagane",
    ["Hours of the day"] = "Timane i døgnet",
    ["Click for the hours of the day."] = "Klikk for timane i døgnet.",
    ["seen on %d of the last %d"] = "sedd %d av dei siste %d",
    ["%d entries over %d days"] = "%d oppføringar over %d dagar",
    ["As far back as the log goes: since"] = "Så langt loggen rekk: sidan",
    ["Built only from the activity already in your log. Nothing is sent, and nobody is told you looked."] =
        "Bygd berre på aktiviteten som alt ligg i loggen din. Ingenting vert sendt, og ingen får vita at du såg.",
    ["No activity in the log yet. This fills in as you and your friends play."] =
        "Ingen aktivitet i loggen enno. Dette fyller seg etter kvart som du og venene dine spelar.",
})

W.add({["Start race"]="Start kappløp", ["Cancel race"]="Avbryt kappløp",
    ["since first recorded activity"]="sidan første registrerte aktivitet"})

W.add({["%d characters"]="%d figurar",
    ["Based on data from %d of %d characters"]="Byggjer på tal frå %d av %d figurar"})

-- Settings categories and calendar views in Together.
W.add({
    ["Settings category:"]="Innstillingskategori:",
    ["Sharing and milestones"]="Deling og milepælar", ["Help and tools"]="Hjelp og verktøy",
    ["Popups"]="Sprettoppvarsel", ["Appearance"]="Utsjånad",
    ["Text and language"]="Tekst og språk", ["Quiet hours"]="Stille timar",
    ["Sounds and voices"]="Lyd og stemmer",
    ["Daily"]="Dagleg", ["Weekly"]="Vekevis", ["Monthly"]="Månadleg",
    ["Yearly"]="Årleg", ["Total"]="Totalt", ["Period:"]="Periode:",
    ["Dates: from"]="Datoar: frå", ["to"]="til",
    ["Recorded milestones in your retained log. Older activity may be missing."]=
        "Registrerte milepælar i den lagra loggen din. Eldre aktivitet kan mangle.",
    ["Level-up milestones"]="Nivåmilepælar", ["Deaths recorded"]="Registrerte dødsfall",
    ["Quest milestones"]="Oppdragsmilepælar", ["Raid boss kills"]="Raidbossar felte",
    ["Armor first equips"]="Første rustningsbruk", ["Reputation milestones"]="Omdømemilepælar",
    ["Class unlocks"]="Klasseopplåsingar", ["PvP promotions"]="PvP-opprykk",
    ["Achievements earned"]="Bragder oppnådde", ["Zones explored"]="Område utforska",
})

W.add({
    ["%d players online"]="%d spelarar pålogga",
    ["Show friends on the map"]="Vis vener på kartet",
    ["Share my position"]="Del posisjonen min",
    ["Position received %d sec ago"]="Posisjon motteken for %d sek sidan",
    ["Your current map coordinates are shared automatically with members of your joined addon groups while you are online and Share my position is ticked (on by default). Named markers appear on the world map and nearby minimap without opening an addon window."]="Kartkoordinatane dine vert delte automatisk med medlemer i tilleggsgruppene dine medan du er pålogga og Del posisjonen min er kryssa av (på som standard). Namngjevne punkt vert viste på verdskartet og minikartet i nærleiken utan å opne eit tilleggsvindauge.",
    ["Untick Share my position under Sharing and milestones to stop sending this character's live map position. You can still see friends' markers. Character-list and Location settings are separate."]="Fjern haka for Del posisjonen min under Deling og milepålar for å slutte å sende kartposisjonen til denne figuren. Du kan framleis sjå punkta til venene dine. Figurlista og innstillinga Plassering er uavhengige.",
    ["Live map coordinates are not saved or relayed, and markers expire after 90 seconds without updates."]="Kartkoordinatar vert ikkje lagra eller sende vidare, og punkta forsvinn etter 90 sekund utan oppdateringar.",
})
