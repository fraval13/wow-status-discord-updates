# Discord progress updates

Automatic posts use the destination server's unrestricted custom emojis named
`wow_new`, `wow_levelup`, `wow_loot`, `wow_gear`, `wow_death`, and `wow_recap`.
Missing/unavailable emojis fall back to standard Unicode. Each group resolves only
its own server's emojis. No privileged Discord intents are required.

Level updates show recorded location, observed level-up count for that character's
Oslo day, and timing when available:

- **Played** duration comes from the client's total `/played` minus time at the
  current level, compared with the previously recorded level's played boundary.
  It excludes offline time. Playtime sharing must be enabled. No previous boundary
  or skipped levels means no played duration is displayed.
- **Elapsed** duration comes from consecutive observations in the same tracking
  segment and includes offline time. A baseline observed midway through a level is
  marked partial. Gaps and paused tracking are not joined.
- The daily count means recorded events, rather than an inferred total. Late
  uploads keep the date the event happened, in `Europe/Oslo`.

Every tenth level gets a milestone embed; the adapter-reported cap gets a gold
level-cap embed. Existing personal and group announcement filters still apply.
No personal-best tracking or ranking is added.

Loot and equipment posts use rarity-coloured embeds when quality was recorded.
Classic Era item IDs link to Wowhead Classic. Forever IDs are displayed without an
external database link because no authoritative Forever item lookup is configured.
Names and original game links remain in the structured JSON. Unknown rarity is
labelled rather than guessed.

Daily recaps remain scheduled for 00:05 Europe/Oslo, grouped by player and character.
They show recorded level gains, deaths, notable loot, level timestamps and locations.
Played time is a **lower bound** from actual client samples inside that Oslo day or
complete recorded same-day level intervals. The larger lower bound is used to avoid
double-counting overlapping evidence. One sample alone establishes no duration.
No sample before midnight is attributed to the following day. Weekly summaries sum
these daily lower bounds. JSON retains the underlying evidence and explicit timezone.

Location and playtime remain optional; enable those profile fields in the addon
for richer output. Updating the addon is needed to capture event locations and
played durations; old events are not assigned the character's current location.
Disabling either field scrubs retained event metadata locally and on the service
at the next upload. Historical Discord messages already sent remain unchanged.

The new addon behavior still needs actual-client testing at home. CI uses mocked
Vanilla and Forever APIs; the work computer does not run the addon or test suite.
