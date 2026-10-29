# In-game sharing acceptance tests (0.14.0)

Friends use the same group ID and updated addon. No separate application is
needed. Install the whole client folder and fully restart WoW for the new modules.

## Options and presentation

1. Open Options → AddOns → WoW Status. Confirm native settings backgrounds and
   readable controls, a short group-ID instruction, and Groups / Activity log /
   Preview toasts buttons. No separate Milestones or integration page is shown.
2. Confirm Announce armor loot and Rare / Epic / Legendary equipment are checked
   on new settings. All milestones are on the main page. Turning off a category
   stops your corresponding announcements; collection/profile choices still apply.
3. Groups shows account-wide IDs, with save/remove instructions below Group ID.
   Add/remove a group and verify another character inherits the list.
4. The minimap book opens the log with left-click and Options with right-click.
   Drag it and verify its saved position survives restart.
5. Activity log has only its title above the cards, with All / Mine / Friends /
   Close below. No technical subtitle or Catch up button is shown. Scroll back
   while new activity arrives and check that the viewed entry stays anchored.
6. Notification previews contains only toast choices and Close; there is no
   character introduction or bottom character-card demonstration.

## Armor-only loot

Use real game loot with public metadata. Gray/white/green armor, weapons of every
rarity, bags, recipes and trade materials must not appear as loot in either the
log or toast queue. Blue/purple/orange equippable Armor-class items qualify,
including shields, cloaks and jewelry. Uncached items wait briefly for item data;
unknown classifications never become assumed armor.

Check all three rarity choices individually, including clearing an existing rare
entry by unchecking Rare equipment. A friend's incoming armor and recovered
history must obey your selected rarities too. Older loot packets without item
class/slot/rarity metadata are ignored. Known valid saved armor can be upgraded
from retained local item links; other unclassified old loot is dropped.

Equipment-change observations remain private and use the same armor filter.
They do not create equipment-change announcements. Individual quest turn-ins are omitted from the log; quest totals still update
and hundred-quest achievements remain. Skill points can be recorded privately;
friends get new professions and profession title promotions.

## Automatic login exchange

1. Have A and B already in the group, each with some saved announcements the other
   lacks. Keep A online beyond its own login exchange, then log B in.
2. B greets every visible group peer once. Both A and B should acquire missing IDs,
   including A pulling from B, without a manual action or a wave of old popups.
3. With three or more members, check that the arriving client contacts all visible
   group peers, not just the first. Duplicate saved copies should remain one card.
4. After synchronization completes, idle for more than a minute and check that no
   periodic inventory sweep or repeated login hello occurs. A later player's
   login should trigger a new pairwise exchange with that player.
5. Verify offline-author relay: A announces to B, then logs out; a returning group
   member C should recover A's saved entry from B when C logs in.
6. Remove a group and check received entries/transfers disappear. Test another
   group's isolation, join-time cutoffs, privacy cancellation, combat deferral and
   reordered/duplicate fragments. Catch-up always remains log-only.

Roster discovery runs for a bounded startup/setup window while channels populate;
pending transfer jobs may take longer. One hello per peer/login initiates both
pull directions. Paginated sessions resume through the retained cache, with at
most two active pulls, rate-limited packets and one bounded timeout retry. This
is not a server mailbox: unavailable or evicted copies cannot be reconstructed.

The log prefix now uses J2, including armor metadata and requester rarity masks;
armor popups use WSTATUS6. Updated friends are required. Original stable event
IDs, group scope, timestamps and quiet duplicate handling are preserved. Relayed
authorship remains player-reported rather than cryptographically authenticated.

## Automatic milestone coverage

Dungeon clears require a game completion signal or a complete killed encounter
roster in a party instance. First mount uses collection APIs, or a first observed
ride with that wording on clients without the journal. Reputation announces new
Honored/Revered/Exalted highs. Class unlocks cover a conservative first-rank spell
list; PvP uses available classic rank APIs. Existing observations are baselined
silently at login. No unavailable data or completion is guessed.

Left- or right-click a popup to dismiss it. Its log entry remains, and the next
queued popup can appear on the next display tick.

If delivery is one-way, run `/wstatus popup status` on both clients after a real
qualifying update. Joined=true with zero discovered peers means no outgoing
recipient was found. Version 0.14.2 handles asynchronous roster loads and can
learn a peer from their normal chat in the shared custom channel. It does not
log that chat text. Paste the runtime, peers and last sent/received diagnostics
when reporting failures. A received addon whisper alone does not authorize
historical sync to its sender.

## Zone and Rogue changes (0.14.3)

Zone notifications now require a character's first recorded visit. Previous zone
history, the saved snapshot and the login zone seed a persistent visit set, so
upgrading/reloading or revisiting known zones stays quiet. Zone snapshots still
update normally. Visits predating addon tracking or made with location collection
off cannot be reconstructed. Update every sender to stop older clients' repeat
zone announcements.

Rogues track learning Poisons (spell 2842), replacing Pick Lock. Already-known
Poisons and relearning remain silent. Clicking a toast still dismisses it, but
the Click to dismiss footer is no longer shown.
