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
    -- Main window and Activity
    ["Overview"] = "Oversikt", ["Activity"] = "Aktivitet", ["Records"] = "Rekordar", ["Characters"] = "Figurar",
    [" (sample tour, nothing here is real)"] = " (prøvetur, ingenting her er ekte)",
    ["Showing:"] = "Viser:", ["From your achievements (date only)"] = "Frå bragdene dine (berre dato)",
    ["Your activity"] = "Di aktivitet", ["Caught up via"] = "Henta via", ["a group member"] = "eit gruppemedlem",
    ["passed on by"] = "vidaresendt av", ["Saved group update"] = "Lagra gruppeoppdatering",
    ["Live group update"] = "Direkte gruppeoppdatering", ["No activity yet"] = "Ingen aktivitet enno",
    ["Event ID:"] = "Hending-ID:",
    -- Characters page
    ["Not announced"] = "Ikkje kunngjort", ["Unnamed player"] = "Namnlaus spelar", ["you"] = "deg",
    ["character"] = "figur", ["characters"] = "figurar", ["Sync now"] = "Synk no", ["Sync (%d s)"] = "Synk (%d s)",
    ["Your characters"] = "Figurane dine", ["Other"] = "Andre",
    ["Nobody else seen in this group yet."] = "Ingen andre er sett i denne gruppa enno.",
    ["older version"] = "eldre versjon", ["older version or list sharing off"] = "eldre versjon eller listedeling av",
    ["Never met"] = "Aldri møtt", ["offline"] = "fråkopla", ["XP %d%%"] = "XP %d %%", ["Level %d"] = "Nivå %d",
    ["1 death"] = "1 dødsfall", ["%d deaths"] = "%d dødsfall", ["Groups:"] = "Grupper:",
    ["Listed"] = "Lista", ["Listed group"] = "Lista gruppe", ["Browse groups"] = "Bla i grupper", ["listed by"] = "lista av",
    ["Friends in your other groups can see this group under Browse groups and join it. Leave it off for a private group."] =
        "Vener i dei andre gruppene dine kan sjå denne gruppa under Bla i grupper og bli med. La det vere av for ei privat gruppe.",
    ["No listed groups yet. Friends list a group by ticking Listed on their Groups page."] =
        "Ingen lista grupper enno. Vener listar ei gruppe ved å krysse av for Lista på Grupper-sida si.",
    ["Equipped by"] = "Teke i bruk av",
    ["Day:"] = "Dag:", ["Today"] = "I dag", ["Yesterday"] = "I går", ["All days"] = "Alle dagar",
    ["Nothing yet today."] = "Ingenting enno i dag.", ["No activity on this day."] = "Ingen aktivitet denne dagen.",
    ["January"] = "januar", ["February"] = "februar", ["March"] = "mars", ["April"] = "april", ["May"] = "mai",
    ["June"] = "juni", ["July"] = "juli", ["August"] = "august", ["September"] = "september", ["October"] = "oktober",
    ["November"] = "november", ["December"] = "desember",
    ["Mo"] = "Må", ["Tu"] = "Ty", ["We"] = "On", ["Th"] = "To", ["Fr"] = "Fr", ["Sa"] = "La", ["Su"] = "Sø",
    ["1 kill"] = "1 drap", ["%d kills"] = "%d drap", ["Kills:"] = "Drap:", ["Gold:"] = "Gull:", ["Earned:"] = "Tent:",
    ["Played:"] = "Spelt:", ["Gold"] = "Gull", ["Gold earned"] = "Gull tent", ["Monsters killed"] = "Monster drepne",
    ["Played"] = "Spelt", ["Gold and gold earned"] = "Gull og gull tent",
    ["Click to see this character's activity."] = "Klikk for å sjå aktiviteten til figuren.",
    ["No characters yet."] = "Ingen figurar enno.", ["Share my character list"] = "Del figurlista mi",
    ["Hide this character from the list"] = "Gøym denne figuren frå lista",
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
    ["Decide which milestones you share: levels, deaths, first zone visits, professions, dungeon clears and more. You can change this at any time."] =
        "Bestem kva mål du deler: nivå, dødsfall, første besøk i område, yrke, fangehol og meir. Du kan endre dette når som helst.",
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
    ["Next theme"] = "Neste tema", ["Smaller"] = "Mindre", ["Larger"] = "Større",
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
    ["Announcements"] = "Kunngjeringar", ["Share my session recaps"] = "Del øktsamandraga mine",
    ["First-time equipment"] = "Utstyr første gong", ["Announce first armor equips"] = "Kunngjer første rustning",
    ["Rare equipment"] = "Sjeldan utstyr", ["Epic equipment"] = "Episk utstyr", ["Legendary equipment"] = "Legendarisk utstyr",
    ["Screenshots"] = "Skjermbilete", ["Screenshot on level up"] = "Skjermbilete ved nytt nivå",
    ["Screenshot on first dungeon clear"] = "Skjermbilete ved første fangehol", ["Hide interface in screenshots"] = "Gøym grensesnittet på skjermbileta",
    ["History / graph"] = "Historikk / graf", ["Deaths"] = "Dødsfall", ["First zone visit"] = "Første besøk i eit område",
    ["Every 100 quests"] = "Kvart 100. oppdrag", ["Profession milestones"] = "Yrkesmål", ["Dungeon / raid milestones"] = "Fangehol- og raidmål",
    ["Mount milestones"] = "Ridedyrmål", ["Reputation rank"] = "Omdøme-steg", ["Class ability unlock"] = "Ny klasseevne",
    ["PvP rank"] = "PvP-grad", ["Honor level"] = "Ærenivå",
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
    ["Character is not ready."] = "Figuren er ikkje klar.", ["Unsupported saved data version."] = "Ukjend versjon av lagra data.",
    ["Waiting for readable player identity. Collection will retry after loading/combat."] =
        "Ventar på at spelaridentiteten kan lesast. Prøver igjen etter lasting eller kamp.",
    ["Set the same group ID as your friends in Options > AddOns > WoW Status."] = "Bruk same gruppe-ID som venene dine i Innstillingar > AddOns > WoW Status.",
    ["Milestone choices are on the main WoW Status page."] = "Måla vel du på hovudsida til WoW Status.",
    ["Manual announcements have been removed. Milestones are detected automatically."] = "Manuelle kunngjeringar er fjerna. Måla blir oppdaga automatisk.",
    ["Screenshots are not available in this client."] = "Skjermbilete er ikkje tilgjengeleg i denne klienten.",
    ["A screenshot is already being taken."] = "Det blir alt teke eit skjermbilete.",
    ["Minimap button distance reset."] = "Avstanden til minikartknappen er tilbakestilt.",
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
    ["Language:"] = "Språk:", ["Reload"] = "Last på nytt", ["Reload to apply"] = "Last på nytt", ["What's new in WoW Status"] = "Nytt i WoW Status",
    ["Use /wstatus debug on or /wstatus debug off."] = "Bruk /wstatus debug on eller /wstatus debug off.",
    ["Debug log on. Type /reload to save it for reading."] = "Feilsøkingslogg på. Skriv /reload for å lagra han.",
    ["Debug log off."] = "Feilsøkingslogg av.",
    ["Use /wstatus language nn for Nynorsk or /wstatus language en for English."] =
        "Bruk /wstatus language nn for nynorsk eller /wstatus language en for engelsk.",
    -- Notifications
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
    ["Firsts"] = "Rekordar", ["Leaderboard"] = "Toppliste", ["Sort:"] = "Sorter:", ["Level"] = "Nivå",
    ["Character"] = "Figur", ["Nobody in this group yet. Members appear when their character list arrives."] =
        "Ingen i denne gruppa enno. Medlemer dukkar opp når figurlista deira kjem fram.",
    -- Death details
    ["killed by"] = "drepen av", ["Falling"] = "fall", ["Drowning"] = "drukning", ["Fatigue"] = "utmatting",
    ["Fire"] = "eld", ["Lava"] = "lava", ["Slime"] = "slim",
    -- Reactions
    ["from"] = "frå", ["Git Good"] = "Øv deg litt meir, så døyr du kanskje sjeldnare!", ["GZ!"] = "Eg ynskjer deg hjarteleg til lukke med det nye nivået!", ["F"] = "Eg tek av meg hjelmen og bøyer hovudet i sorg.",
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
    ["Your group"] = "Gruppa di", ["Latest records"] = "Nyaste rekordar",
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
    {"^First to reach level (%d+)(!?)$", "Først til nivå %1%2"},
    {"^Enjoy (.+)!$", "Kos deg i %1!"},
    {"^Language: (%a+)%. Type /reload to change every window%.$", function(name)
        return "Språk: " .. (name == "English" and "engelsk" or "nynorsk") .. ". Skriv /reload for å endre alle vindauga."
    end},
    {"^Theme: (%a+) · size (%d+)%%$", function(name, size)
        local themes = {Achievement="Bragd", Night="Natt", Journal="Dagbok", Faction="Fraksjon"}
        return "Tema: " .. (themes[name] or name) .. " · storleik " .. size .. " %"
    end},
    {"^Notification size %((%d+)–(%d+)%%%)$", "Varselstorleik (%1–%2 %%)"},
    {"^Notification size: (%d+)%%%.$", "Varselstorleik: %1 %%."},
    {"^You already shared WoW Status with (.+) in the last hour%.$", "Du har alt delt WoW Status med %1 den siste timen."},
    {"^The whisper to (.+) could not be sent%.$", "Kviskringa til %1 kunne ikkje sendast."},
    {"^Shared the WoW Status link with (.+)%.$", "Delte WoW Status-lenkja med %1."},
    {"^Minimap button distance set to (.+)%.$", "Avstanden til minikartknappen er sett til %1."},
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
