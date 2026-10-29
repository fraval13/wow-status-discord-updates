# Activity log and local history

Open **Activity log** with the minimap book, in addon settings, `/wstatus activity`, or `/wstatus journal`.
It shows scrollable cards with the same icons, accent colours and headings as live
popups. **All**, **Mine** and **Friends** filter the view. Hover a card for its full
text and stable event ID. New entries preserve your position when scrolling back.
The window recycles six row frames, so a long log does not create thousands of UI
objects. Catch-up entries keep their original timestamp and show the relay name.

Your own tracked announcements appear even if nobody is online to receive them.
Individual quest turn-ins, profession points and eligible armor equipment changes are recorded
privately, respecting character collection/profile choices. They do not create
friend notifications or enter peer sync. Previews and synthetic tests are excluded.
This records supported addon activity, not every action, chat message or keypress.

SavedVariables preserve the log on reload/logout. Up to 2,000 entries are kept,
with a separate 1,000-entry ceiling for private activity so it cannot consume the
entire shared-announcement cache. Rare/epic/legendary armor filters also apply to saved and synced loot; unknown
old loot is excluded unless its item metadata can be recovered. New installations
import up to 500 recent own
history events and the retained received-activity cache for local browsing. These
older entries are not newly advertised to peers.

## Catching up without a server

Every new announcement has a stable ID derived from client edition, normalized
character/realm identity, the saved character epoch and its event sequence. Relay
copies preserve that ID and the original time. Inventory fingerprints are only
transfer hints; full IDs are used for deduplication after validation.

Online group members exchange small inventories, request missing entries and
reassemble bounded addon-whisper fragments. Peers can forward retained copies,
so the original author need not be online. At login, the arriving client greets every available group member and both sides
request missing entries automatically. An already-online peer also pulls from
the arriving client. There is no manual button or periodic polling. Known IDs are skipped. Recovery
is quiet: it adds log cards and never replays old popup queues. A later live copy
of a recovered ID also does not replay its toast.

Sync covers the last seven days, bounded by the retained log and your group's
join time. It only exchanges records saved for that same group, with a peer
currently present in its channel roster. It does not route entries between
unrelated groups. Removing a group cancels its transfers and clears received
entries; disabling own fields/collection cancels pending publication of those
observations. Private personal activity is never offered.

This is an eventual catch-up cache, not a guaranteed archive or authenticated
ledger. Another updated group member with a saved copy must come online. Missing
copies, evictions and older events cannot be reconstructed. Relayed authorship is
a claim from the relay, labelled as such in the log. Already distributed copies
cannot be recalled from other computers. Whisper/realm/faction restrictions still
apply. Update friends' addons to enable the log-sync prefix.

## Raw history, graphs and timings

 and level line graph

Open the new window using the **History / graph** button in `/wstatus`, or:

```text
/wstatus logs
/wstatus graph
/wstatus times
```

This is your currently logged-in character's local addon history. Other people's
shared records remain accessible through Discord; there is no HTTP client or
server-history download inside WoW. Everything is written but still awaits actual
Classic Era/home validation. Nothing was run on the work computer.

## Scrollable logs

The **Event logs** tab shows collected events with Norwegian time, type, event ID,
and the event data. Scroll within a page; use Previous/Next for the complete local
history in pages of 75 records. The All/levels button filters the view. Refresh
updates the view explicitly so incoming events do not move the scroll position
while you are reading. Synthetic events show `[TEST]`.

The **Character details** tab shows identity, current sharing settings and the latest
selected snapshot. These are the addon's source records. The companion filters
again, splits history into small requests, and the service applies group posting
rules. A collected event is not necessarily an immediate Discord announcement.

The addon cannot confirm HTTP uploads or Discord deliveries. Logs explicitly say
**collected locally; upload/delivery not confirmed in game**. Confirm uploads in
the companion and deliveries in the service's outbox/JSON. This feature does not
write network receipts into addon files while WoW is running.

## Level on the vertical axis, time on the horizontal axis

The **Level graph** is a line graph, with no bars:

- Vertical axis: character level.
- Horizontal axis: elapsed clock time from the earliest retained timestamp.
- Horizontal line sections show time at a level; upward steps mark level-ups.
- Blue points mark real recorded level-up events; orange points mark baselines.
- Missing levels, backward clocks and tracking gaps start a disconnected segment.
- The final horizontal line ends at the latest observation, not a future prediction.

The **Level times** tab lists each measured transition. Consecutive real level-up
records give a complete elapsed duration: for example, the interval between reaching
level 12 and reaching level 13 measures time spent at level 12. This includes offline
hours. It is not an active `/played` duration, and enabling playtime is not required.

If you install or enable tracking partway through a level, its first measured
interval is **partial**. It is only a lower bound on the full time that level took.
A baseline never claims the character was created at that instant. Missing history
is not reconstructed from the current level. Synthetic test events do not add graph
points or level-duration records. Existing recorded level events from an older
version are migrated without inventing earlier times.

The graph is drawn with the client line API. If unavailable, the window gives a
clear fallback to the Level times tab. Client implementation reference:
[Blizzard's mirrored line API documentation](https://raw.githubusercontent.com/Gethe/wow-ui-source/classic/Interface/AddOns/Blizzard_APIDocumentationGenerated/SimpleLineAPIDocumentation.lua).
Forever compatibility remains unverified.

## Persistence and Norwegian time

The account-level SavedVariables record now retains a complete **consented** local
event history, alongside the recent 500-event buffer. The companion reads that
persistent history and uploads in batches of at most 100 events, so rolling-buffer
eviction no longer discards older retained events from later uploads. Existing
server event IDs suppress repeats. Events lost before upgrading cannot be restored.

Data still reaches disk on `/reload` or logout. Abrupt termination can lose records
that only existed in game memory. Back up SavedVariables while WoW is closed. There
is no automatic history truncation; as a defensive parsing limit the companion
accepts files up to 32 MiB and two million tokens. If you reach that limit, keep a
backup and request an archive/rotation update rather than deleting unuploaded data.

All displayed timestamps use Europe/Oslo independently of the computer's timezone,
including Norwegian summer/winter offsets. The Lua formatter uses modern European
DST rules for the game's era. Elapsed durations use absolute timestamps, so changing
between summer and winter time does not add or remove an hour of actual elapsed time.

The per-character JSON now includes `progression.level_timeline`:

```json
{
  "timezone": "Europe/Oslo",
  "time_basis": "elapsed_wall_clock_including_offline",
  "x_axis": "elapsed_seconds",
  "y_axis": "level",
  "points": [],
  "durations": []
}
```

Each point contains level, an Oslo timestamp, elapsed seconds, source, segment and
an event reference where available. Each duration identifies the level, next level,
start/end timestamps and whether it is partial. Partial intervals have
`elapsed_seconds: null` and `elapsed_lower_bound_seconds`; complete intervals have
`elapsed_seconds`. Later tools can plot the same line without scraping Discord.

## Privacy

Only enabled collection is retained. Turning off a field/category scrubs related
local history before export. Pausing sharing clears local event contents and level
tracking under the existing privacy policy; server-side pause also scrubs server
history. Disabling the level field or level collection clears graph observations
and removes related timeline data on upload. Privacy controls apply to older history
too. This feature does not silently retain hidden level data for the graph.

## Home acceptance

1. Upgrade the addon with WoW closed, preserving a backup of SavedVariables.
2. Enable sharing, level profile and level collection; open all four window tabs.
3. Observe a baseline, then two real consecutive level-ups. The first duration must
   be partial; the next duration must match the elapsed interval between level-ups.
4. Run `/wstatus test`: it must appear in logs as TEST and leave the graph unchanged.
5. Scroll a long history and navigate pages. Toggle logs/graph repeatedly; drawing
   regions are reused rather than accumulating on every refresh.
6. Reload/relog and restart the companion. History and graph must survive, uploads
   must deduplicate, and older history beyond the recent buffer must still upload.
7. Test a missing-level gap and clock rollback: the graph must not draw a line across it.
8. Disable level visibility or pause, export and upload: local graph and managed JSON
   timeline must be cleared. Previously posted Discord messages remain.
9. Compare Oslo summer/winter timestamp labels and confirm elapsed durations across
   a DST boundary remain absolute clock differences.

Authored tests cover these data/GUI behaviors with mocks and still need home execution.
