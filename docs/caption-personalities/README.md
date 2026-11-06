# Caption personalities

Optional voices for the flavour line under each notification and activity-log
card. Players pick one under **Options → AddOns → WoW Status → Notifications →
Next personality**, or with `/wstatus personality <name>` (English or Nynorsk
name). The choice is account-wide and presentation only: nothing about it is sent
to other players, so friends can each use a different personality.

**Random** (`random`, Nynorsk *Tilfeldig*) is the default and has no captions
of its own: each new caption picks one of the voices below, Classic included,
from the event's identity, so friends and reloads see the same voice for the
same event. **Classic** is the original bank (`docs/notification-flavour-text.md`,
`Flavour.lua`, `FlavourNN.lua`).

| Id | English | Nynorsk | Voice |
|---|---|---|---|
| `wholesome` | Wholesome | Hjartevarm | Warm, sincere, proud-friend cheering |
| `bard` | Epic bard | Episk skald | Over-the-top heroic saga narration |
| `veteran` | Grumpy veteran | Grinete veteran | Unimpressed old-timer, secretly proud |
| `goblin` | Goblin merchant | Goblinkremmar | Everything is a sales pitch |
| `christian` | Christian | Kristen | Warm, good-humoured faith, blessings and parables |
| `smug` | Condescending Christian | Nedlatande kristen | Holier-than-thou backhanded blessings; the joke is the smugness, never the faith |
| `dwarf` | Dwarf | Dverg | Ale, beards, forges and stone |
| `jealous` | Jealous friend | Sjalu venn | Petty, envious congratulations through gritted teeth |
| `drama` | Drama queen | Dramadronning | Every milestone is the most emotional event ever |

## Format

Each personality has a folder with one JSON file per caption category (the same
13 categories as Classic). A file is a list of exactly 300 pairs (`death.json`:
560, see below):

```json
[{"en": "English caption.", "nn": "Nynorsk caption."}]
```

Line *i* in Nynorsk is the Nynorsk version of line *i* in English, so a caption
reads as the same joke in either language and switches language with the
player's setting. Death lines also carry `"tag"`: `ANY` for any class, or a class
token (`PALADIN`, `MAGE`, …) for a class-specific line that is only drawn when the
sender's class is known. `death.json` has 170 `ANY` lines and 30 for each of the
13 classes. Lines are at most 90 characters, have no `"`, `\`, `|`,
tabs or newlines, and are unique within their file in each language.

## Editing

1. Edit the JSON.
2. `python scripts/build_personalities.py` regenerates `addon/shared/Flavour<Name>.lua`
   (`--check` reports stale or invalid files without writing).
3. `python scripts/sync_addons.py` copies them into the four editions.

To add a personality, add it to `PERSONALITIES` in the script, add its file to
each edition's TOC after `FlavourNN.lua` and to `PERSONALITY_FILES` in
`tests/test_addon.py`.

## How captions are chosen

A new notification draws from the current personality's bank (under Random,
from a voice picked per event), with the same
event-identity seed as Classic. The chosen line's personality, category and
position are saved with it, so a caption never changes when the player later
picks another personality; it only follows the language setting. Log entries that
keep only the caption text find their line again by its English or Nynorsk text.
