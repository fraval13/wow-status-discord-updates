# Writing brief for a caption personality

Each notification shows a factual line ("Thora reached level 33!") and, under it,
one short **caption** in the chosen personality's voice. Write every caption as a
**pair**: an English line and a natural Nynorsk line carrying the same joke.

## Categories

| File | Shown when |
|---|---|
| `level` | a friend levels up |
| `introduction` | a friend joins the WoW Status group (a welcome) |
| `loot` | first equip of a rare, epic or legendary armor piece |
| `death` | a friend dies (general and class-specific lines) |
| `zone` | first visit to a zone |
| `quest` | each 100 completed quests |
| `profession_learned` | a profession learned for the first time |
| `profession` | a profession title promotion (Journeyman, Expert, Artisan…) |
| `dungeon` | first clear of a dungeon |
| `mount` | first mount (ground or flying) |
| `reputation` | a reputation milestone such as Exalted |
| `unlock` | a major class ability unlocked |
| `pvp` | a PvP rank or Honor milestone; fits Classic ranks and Retail Honor alike |

Counts and the death `tag` split are in `docs/caption-personalities/README.md`.
Class death lines play on that class's abilities and fantasy as playful
suggestions ("Maybe Ice Block next time?"), never as claims a spell was used.

## Voice

Define the personality in two or three sentences before writing: its attitude,
its favourite images and how it treats deaths. Every line stays in that voice.
When the voice is a caricature (smug, jealous, grumpy), the joke lands on the
character's own attitude, never on a real group, faith or person.

## Each line

- **Generic**: fits any level, zone, item, profession or rank of its category; the
  factual line carries names, numbers and facts.
- **Short**: one or two sentences, 25–65 characters (90 at most), ending in
  punctuation.
- **Varied**: each sentence frame a handful of times per file at most; vary
  openers and images across the file.
- **Original**: own wording only, rather than game dialogue, quest text or famous
  catchphrases.
- **Friendly**: suitable for all ages, free of slurs, sexual content and politics.
- **Plain text**: apostrophes are fine; the builder rejects `"`, `\`, `|`, tabs,
  newlines and a leading `[`.

## Nynorsk

Write idiomatic Nynorsk (*ikkje, eg, dei, kva, korleis, fekk, nivå, oppdrag,
ridedyr, fangehol, omdøme*) and adapt idioms rather than translating word for word.
Common gaming loanwords (raid, PvP, loot, XP, tank, heal) stay English. After
each file, scan the `nn` lines for Bokmål forms (*jeg, ikke, hva, også, -ene*
plurals of masculine nouns) and fix them. Flag the Nynorsk for a native
speaker's review in the pull request.

## Working method

Write one category at a time and run
`python scripts/build_personalities.py --check --only <id>` after each, fixing
what it reports. The work is done when the only report left is that the
personality's Lua file is stale.
For many personalities at once, give each its own agent with this brief, the
personality's voice and its `id`, so they write in parallel into separate folders.
