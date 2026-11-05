# In-game sharing acceptance tests (0.14.0)

Friends use the same group ID and updated addon. No separate application is
needed. Install the whole client folder and fully restart WoW for the new modules.

## Options and presentation

1. Open Options → AddOns → WoW Status. Confirm native settings backgrounds and
   readable controls, a short group-ID instruction, and Groups / Activity log /
   Preview toasts buttons. No separate Milestones or integration page is shown.
2. Confirm Announce first armor equips and Rare / Epic / Legendary equipment are checked
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
   manual character introduction or bottom character-card demonstration. A Joined
   the WoW Status group preview is available.

## First armor equips

Looting alone must create no event. Equip real items with public metadata. Gray/white/green armor, weapons of every
rarity, bags, recipes and trade materials must not appear as loot in either the
log or toast queue. Blue/purple/orange equippable Armor-class items qualify,
including shields, cloaks and jewelry. Uncached items wait briefly for item data;
unknown classifications never become assumed armor.

Check all three rarity choices individually, including clearing an existing rare
entry by unchecking Rare equipment. A friend's incoming armor and recovered
history must obey your selected rarities too. Older loot packets are ignored; first-equip packets use WSTATUS7 and include
class/slot/rarity metadata. Known valid saved armor can be upgraded
from retained local item links; other unclassified old loot is dropped.

Each qualifying item ID announces only its first recorded equip per character.
Unequip/re-equip, slot changes and reloads must stay silent. Equipment already
worn before tracking is seeded silently. Test uncached items removed before
metadata arrives: they must not announce. Individual quest turn-ins are omitted from the log; quest totals still update
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

Catch-up is bounded per member, so one member can't flood the log:

- A new hello from a member starts a pull at most once per 10 minutes (of game
  uptime, so changing the PC clock doesn't matter) in one group. Hellos within
  that time wait; one pull starts once the 10 minutes are up and any running
  pull from that member has ended, from its newest entries. A repeated hello is
  still quietly accepted, and a hello held back by a chat lockdown still counts
  when it arrives.
- In one login session, a client fetches at most 300 new entries from one
  member, and keeps at most 100 new entries naming any one other member as the
  sender. A member's own entries count only toward the 300. Fetching an entry
  again (for a second shared group, a retry, or the author's own copy that
  replaces a relay's claim) costs nothing and continues after the share is used.
  Other members, or the next login, provide the rest. One pull reads at most
  about 2,000 entries of a member's list, newest first; older ones would not
  outlast this log's own cap for received entries.
- Own entries and received entries are capped separately (2,000 each), so
  received traffic never evicts your own history.

To test: after a long absence in a busy group, log in with several members online
and check the log fills from all of them while your own cards stay.

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

## Popup senders and texts

A received update shows only when its sender is in the group's channel roster
(or posted in the group channel recently), as log sync already required. While
a roster whose member count changed reloads, members from the last complete
roster read still count, for up to two minutes after that read; log sync uses
the same membership. A member who joined moments ago can be missing from
the cached roster, so their update waits up to 60 seconds, longer than the
roster cache lasts; status shows `awaiting roster` and `verifying_sender`. After
that it is dropped (`rejected_unknown_sender`). Legacy channels still use the
trust list.

Each kind must match the texts the addon itself produces: `Joined the WoW Status
group`, `First mount: <name>` or `First mount ride recorded!`, `Honored/Revered/
Exalted with <faction>`, `Unlocked <spell>`, `Promoted to <rank>` (Retail:
`Reached honor level <n>`), `Entered <zone>`, `Learned <profession>`, a profession
rank-up, `Equipped <item>`, `First clear: <dungeon>`, `Completed <n> quests!` and
the death texts. Other texts are dropped and reported as invalid log data, as
before. Names inside a template are the sender's own localized game names and
cannot be checked on another client language.

One sender can have at most four updates queued or waiting; more are dropped
(`sender_queue_full`) until the queue drains. The log can still recover them
quietly in the next login sync. To test: have a friend whose roster entry is
visible send several milestones at once, and check that a fifth update while you
are in combat is not queued.

## Delivery in larger groups

An update is whispered to each peer of each group it belongs to, one whisper a
second. Three level-ups shared with three groups of 20 are 180 whispers, about
three minutes. Each update keeps going until it is 10 minutes old, and receivers
accept updates up to 10 minutes old, so every peer gets it. Before this, an update
was dropped after two minutes, part-way through its list. Older clients still
accept only two minutes, so a friend on an older version can miss a late whisper;
the next login sync still brings it into their log. The list of peers is taken
when an update starts sending. While it sends, the channel's member count is
checked every 10 seconds; when it changed, the roster is read again, peers not
yet listed are added, and a peer the new roster no longer lists has left and is
skipped (`remaining_peers_left` when that ends the list). A peer the game reports
offline is skipped quietly (`peer_offline`). A blocked send is reported in chat
once per update, not once per peer. At most 32 updates wait to be sent; past that
`/wstatus popup status` shows `send_queue_full` and login sync recovers the rest.

The game allows each addon prefix 10 messages, regained at 1 a second, and
answers a send past that with a throttle result. Whispers outside instances are
exempt. When a send is throttled, the same whisper goes to the same peer again
after 2, 4, 8, then every 16 seconds, instead of moving on to the next peer.
`/wstatus popup status` shows `throttled_retrying` meanwhile, and how many updates
are still sending. Login sync waits for that allowance inside an instance (up to
10 messages at once, then one a second) and resends a throttled packet the same
way. Outside instances it keeps its usual pace. An older client's plain `false` can
also mean throttled, so it is tried once more after 2 seconds
(`uncertain_retrying`). If that retry says `false` too, `false` counts as a plain
failure for the next minute, so a client that always says `false` is barely
slowed down.

To test (#25): inside a dungeon, have a friend log in after you have a few hundred
log entries, and check their log fills completely. With as many friends online as
you can gather, trigger several milestones at once and check every popup arrives.

## Relayed entries and event IDs

A catch-up entry is a claim by the member who relayed it; only a live update's
sender, or an author passing on their own entry, is authenticated by the game.
So a live update replaces a relayed entry that holds its event ID with other
content, and it still shows its popup. A relayed copy with the same content
keeps the update quiet, as before. Either way the log then holds the live copy,
all fields included, and a later relayed copy can't change it (not even extend a
text the live packet cut). This applies even when the popup itself is dropped,
for example when the sender's queue is full.
During login sync, a client also fetches the author's own copy of an entry that
only another member relayed, and the author's copy replaces or confirms it.

New event IDs end in a random part (`<epoch>-<sequence>-<8 hex digits>`), so a
relay can't claim a member's next ID before the event happens. Older clients'
IDs without it are still accepted, and events saved before keep their IDs.

The log names where a caught-up entry came from: `Caught up via <A>, passed on by
<B>`. B sent it to you, checked by your game; A sent it to B, checked by B's game
and reported by B in a `J2 V` message before the entry. A member never forwards
a name it could not check itself, so a dishonest relay can't hide behind someone
else on the next hop. When B saw it live or wrote it, the card says just
`Caught up via B`. Older versions ignore `V` and show the direct sender, as
before. To test: B catches up an entry from A (B was offline when it happened),
then C catches it up from B alone. C's log should say `Caught up via A, passed on
by B`.

## Timestamps and PC clocks

Updates are stamped with realm time (`GetServerTime()`), the same clock on every
member's PC, and received stamps are checked against it: a live update counts
when it is at most 120 seconds old and at most 300 seconds ahead. Before, both
sides used their own PC clock (`time()`), so two PCs whose clocks differed by
more than two minutes silently dropped each other's live updates. The sender's
queue limit (120 seconds) and the login sync checks use realm time as well, and
so do saved event, log, recap, export and group-join times. Short local timers
keep the PC clock. Each export also saves `clock_offset` (this PC's clock minus
realm time), and the companion on the same PC checks the export's stamps against
its clock minus that offset. An older companion doesn't read `clock_offset`, so
on a PC more than five minutes slow, update the companion together with the
addon.

Older clients still stamp their PC clock. Their updates count when the stamp fits
realm time or this PC's clock, so anything accepted before is still accepted.

A dropped stamp shows in `/wstatus popup status` as `rejected_stale` or
`rejected_future` on a `Last dropped:` line, with how far it was from realm time
and how long ago it happened. It is kept apart from `Last received:`, so it shows even when the sender's roster
entry has not loaded yet. A `Clock:` line says how far this PC's clock is from
realm time. To test: set one PC's clock three minutes ahead (without automatic
time sync) and send a level-up or milestone both ways; both popups should show. `/run print(time()-GetServerTime())` should print
about 180 on that PC and about 0 on the other.
