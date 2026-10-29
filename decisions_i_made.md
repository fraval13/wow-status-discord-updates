# Decisions I made — 27 October 2026

## Quest log cleanup — 0.14.2

Removed individual quest-turn-in cards from the activity log and filtered existing
questprogress entries during loading/display. Quest completion totals, unique
turn-in tracking and each hundred-quest announcement remain unchanged. This is
included with the pending discovery fix in the same addon release.

## One-way discovery diagnostics — 0.14.2

The user's screenshot showed joined=true but discovered peers=0 and
waiting_for_group_peers. Local saved settings had sharing and level collection
on. This means the sending client had no destination, even though receiving a
friend's announcements worked. A settings reset alone does not establish why
the roster is empty.

- Hold the requested display-channel selection while asynchronous roster data
  loads, cache a complete list, then restore the earlier UI selection. Bound the
  wait and guard synchronous roster callback reentrancy.
- Learn peers from actual server-delivered normal chat in the selected group's
  custom channel as a five-minute fallback. This does not log arbitrary chat or
  turn it into announcements. An addon whisper claiming a group is deliberately
  insufficient for authorizing historical sync; existing roster/group scope is
  preserved. Group removal clears learned identities.
- Advanced /wstatus popup status now includes runtime version, realm/faction,
  discovered names, roster-loading state, target, last received/displayed event,
  queue length and combat state. Nothing is added to the normal log UI.
- Tests reproduce delayed roster data and the screenshot's empty-roster/working-
  chat case. Real two-client confirmation is still required after updating.
- User was given full-reset instructions: exit WoW, back up/rename account-wide
  SavedVariables/WoWStatus.lua and WoWStatus.lua.bak, restart and re-add groups.
  No saved data was deleted or reset by the agent.

Validation/delivery for 0.14.2: 224 tests passed; 121 addon tests also passed with
Lua 5.1. Ruff and whitespace checks passed. Tests cover asynchronous selection,
actual group-chat discovery without roster data, unrelated-channel isolation,
observed-peer expiry, and removal of both current and legacy single-quest cards.
Both client ZIPs include the changes; Vanilla is installed locally with previous
addon files backed up. SavedVariables were not reset. Backend is unchanged.
GitHub push remains dependent on SSH authentication.

## Click to dismiss — 0.14.1

Left- or right-click anywhere on a toast to dismiss it immediately. The next
queued notification becomes eligible on the next display tick. Dismissal never
removes activity-log entries or clears the rest of the queue. Toasts now show a
short Click to dismiss hint. No transport or roster changes are included.

## Armor-only loot and cleaner in-game UI — 0.14.0, 29 October

- Loot now requires rarity 3/4/5, item class Armor (4), a real item ID and an
  equippable armor slot. This includes jewelry/cloaks/shields; weapons, bags,
  recipes/materials and all lower rarities are excluded. Unknown item data waits
  briefly rather than guessing. The source event, raw/local log, incoming packet
  and peer-sync paths all apply the filter. Saved own loot is reclassified from
  retained item links where possible; unverifiable old loot is dropped.
- Interpreted the checkbox request as one Announce armor loot switch and three
  independent rarity choices, all initially on. These filter your received/logged
  loot too; sync requests include a rarity mask to avoid stalled unwanted offers.
  Equipment-change observations stay private and also require qualifying armor.
- Removed the activity subtitle and Catch up button. Login discovery greets every
  currently visible peer once; receiving a hello also queues a pull from the
  arriving member, so synchronization works both ways. No minute-by-minute sweep
  remains. Discovery allows time for channel rosters to populate; transfers are
  throttled, paginated through retained entries and get one bounded timeout retry.
  Group setup changes can also initiate discovery. Recovery stays quiet.
- Added a native minimap book button: left-click log, right-click Options, drag to
  position. It uses the game's book icon and tracking border, no downloaded asset
  or emoji slot. Its angle is saved account-wide.
- Main options now starts with only the shared-group-ID instruction. Milestones
  are on this page with simple announcement controls. Removed introduction
  controls/text and renamed Preview toast to Preview toasts. Groups instructions
  sit below Group ID. Native settings pages use the game's background instead of
  opaque custom panels. The standalone log/toasts retain their shared styling.
- Removed the bottom character-card demonstration from Notification previews.
- Discord is suspended behind `WoWStatusFeatures.discord = false` in Features.lua.
  Its code, server and companion remain. The page/commands are hidden and exports
  disabled for every saved character. Explicit opt-ins/enrollment are shadowed
  for restoration; changing the flag back restores them with a fresh sharing
  boundary. No service or historical Discord message was deleted. Current user
  documentation focuses on in-game sharing; legacy integration docs are retained.
- J2 sync records carry armor metadata; old loot-only text packets cannot bypass
  the new filter. All friends should update. Full WoW restart is required for the
  added Features/Loot/Minimap modules. Backend changes are not required.

Validation/delivery: 218 tests passed; 115 addon tests also passed under Lua 5.1.
Coverage includes item class/slot/rarity combinations, uncached data, old-loot
cleanup, selected-rarity catch-up, no visible integration text, minimap dragging,
all-peer login greetings, reverse pulls on already-online clients, no idle sweeps,
and an actual SavedVariables/companion export round trip proving suspension and
opt-in restoration. Ruff/whitespace checks passed. Both ZIPs are rebuilt and the
Vanilla installation on this computer is updated with its previous files backed
up. SavedVariables were not directly edited. No backend deployment is needed;
GitHub push still depends on working SSH authentication.

## Graphical log and decentralized catch-up — 0.13.0, 29 October

Added a persistent account activity log with the same visual theme function used
by live toasts. Six recycled scroll rows show icons, coloured headings, original
times and source information; All/Mine/Friends filters and hover details include
event IDs. Scroll position stays anchored while new entries arrive. Activity log
in settings and /wstatus activity or /wstatus journal open it; raw logs/graphs
remain available separately.

- Log own collected announcements plus private quest turn-ins, equipment changes
  and profession points. These detailed personal entries never notify or sync to
  friends. Existing character privacy/collection settings apply. Preview/synthetic
  samples remain excluded. This is tracked addon activity, not a full game audit.
- Stable announcement IDs combine client, normalized character/realm, saved epoch
  and sequence. Relays preserve full IDs and original timestamps. A matching live
  copy after recovery is also suppressed. Fingerprints only reduce transfer cost;
  validated full IDs determine duplicates.
- Online members exchange paginated inventories and request only missing entries.
  A third party can retain and relay announcements while the author is offline.
  Recovery goes quietly into the log, with the relay identified, not into popups.
- Synchronization is scoped to a saved group, after the receiver's join boundary,
  with current channel-roster peers. No cross-group forwarding or private-action
  transfer. Group removal clears received data/cancels queued work. Own privacy
  changes invalidate sessions and cancel pending payloads. Relayed authorship is
  player-reported, not cryptographic identity, and old distributed copies cannot
  be recalled from other computers.
- Keep 2,000 log entries, with private entries capped at 1,000. Sync at most seven
  days of retained announcements. Six IDs per inventory page, up to 20 pages per
  round, resumable offsets, two active groups and a 512-packet queue bound traffic.
  Send at most two log packets per second; defer combat. Missing/expired copies
  cannot be recovered, and a group member with a copy must come online.
- Import up to 500 recent own historical events plus retained received messages
  for local browsing only, avoiding publication of old/private backlog. Added
  Presentation.lua and Journal.lua to both complete addon folders. Corrected
  texture path escaping while extracting the shared presentation helper.
- No server or optional companion changes are needed for this in-game-only
  feature. Full WoW restart is required to load the new Lua files. Actual client
  API/channel behavior still needs a live multi-player check.

Validation/delivery: 196 tests passed; 93 addon/milestone/journal tests also passed
with Lua 5.1. Coverage includes offline-author relay, replay suppression, multiple
inventory pages, out-of-order/duplicate fragments, privacy cancellation, unrelated
groups/join boundaries, UI row reuse/scroll anchoring and bounded private storage.
Ruff and whitespace checks passed. Vanilla is installed locally with a backup;
both ZIPs include the new Lua modules. No backend deployment is required.
GitHub SSH authentication remains unavailable; commits need pushing from an
authenticated computer.

## Automatic announcements only — 0.12.1, 29 October

Removed discovery sharing, manual dungeon reports and the older free-text LFG
announcement path to keep friends' notifications focused on game progress.
Their fields, buttons, toggles and previews are gone; the old slash commands
explain that manual announcements were removed and queue nothing. Name/group
setup fields remain because they configure identity and destinations.

Dungeon announcements now come only from completion detection and include a game
instance ID/name in a WSTATUS5 packet. Older dungeon packets cannot distinguish
manual reports, so they are ignored along with all discovery/LFG packets. The
new per-character dungeon cache seeds from existing game-detected history,
excluding manual records. Clients without reliable completion APIs skip clears.

Removed types are also blocked by server validation and announcement eligibility,
including pending legacy deliveries. Existing received free-text activity cache
entries are cleared during initialization; old Discord messages are untouched.
This controls the standard addon paths, not cryptographic verification of peers.

Validation: 185 tests passed, including auto dungeon delivery, rejected old
packets, disabled commands/no milestone EditBoxes, and server rejection of old
manual reports. Updated Vanilla/Forever ZIPs and local installation are prepared;
GitHub push remains blocked by the previously observed SSH authentication issue.

## Friend milestones — 0.12.0, 29 October

Added first dungeon clears, first mount, major reputation promotions, selected
class ability unlocks, PvP rank promotions and voluntary discoveries. Explicitly
excluded dungeon invitations, as requested. Existing rarity-filtered loot remains
and has Rare + epic / Epic-only buttons under the new Milestones settings page.
All six new notifications use the existing FIFO queue and have local previews.

Decisions about evidence and spam:

- Existing observed progress is baselined silently on login. Milestone observations
  are per character; account group membership is unchanged.
- Dungeon completion requires a completion event or all recorded encounters killed
  after a successful encounter. An arbitrary boss is never called a full clear.
  A manual Record first clear control covers clients without a completion API;
  these records are labelled player-entered in stored data. Dungeons deduplicate
  by name. First means first recorded since using this addon, not reconstructed
  lifetime history.
- A supported mount journal detects first collection. Without it, announce the
  first *observed ride*, with that wording. Existing/late-loaded collections stay
  silent. Reputation announces Honored/Revered/Exalted; PvP requires an observed
  classic rank increase. New Forever-specific rank APIs are not invented.
- Class unlocks use a conservative list of first-rank spells, not every spell or
  training rank. Missing APIs do not crash startup or fabricate notifications.
- Discoveries are manually shared (120 bytes). Details stay hidden on the toast
  and in activity until the reader clicks Reveal discoveries. Reopening activity
  hides them again. This hides spoilers visually; it is not encryption.
- A bounded WSTATUS4 raw-text payload preserves full discovery text within a single
  addon whisper. Old clients retain existing notifications but must update for
  new milestone types. New event settings default on while Discord stays opt-in.
- Optional Discord validation, rendering and JSON archives support all six types.
  No new emoji uploads or slots are needed. No live test notification is sent.

Validation: 183 tests passed; the 80 addon/milestone tests also passed under Lua
5.1. Ruff and whitespace checks passed. Installable Vanilla/Forever ZIPs include
the new module. This computer's Vanilla addon is updated with a backup of the
previous files; SavedVariables are preserved. GitHub SSH authentication remains
unavailable, so the release is deployed directly through the existing receiver.

See docs/LIVE_POPUPS.md for controls, automatic API coverage and fallbacks.

## Clearer, queued in-game notifications — 0.11.0, 29 October

- Gold upward arrow for levels (bundled TGA converted from the generated Discord
  asset); friendly adventurer portrait for introductions. No Discord slots used.
- Equipment notifications and preview removed, old toggles disabled. Equipment
  observations can still update the private/shared profile as selected.
- Quest notifications are achievements at each hundred completed quests, not each
  turn-in. Totals remain current. A login or switch to a game-reported total sets
  a silent baseline; it does not replay old achievements.
- Profession notifications are title promotions based on increased rank caps
  (75/150/225/300), not individual points. Initial observations stay silent.
- All previews use the normal FIFO display queue. Each card keeps six seconds of
  reading time; distinct rapid level-ups no longer merge. Waiting accepted cards
  do not expire. Combat deferral and network deduplication remain. Queue bound is
  128 pending cards; a full preview queue reports that it needs time to drain.
- Optional Discord upload cards still summarize current totals/ranks, independent
  of in-game notification frequency. Server validation accepts new milestone
  payloads. Preview buttons reflect the new notifications.
- Validation: 165 tests passed; 62 addon tests also passed with Lua 5.1. Includes
  rapid preview clicks, distinct queued friend levels, quest boundaries/duplicates,
  silent equipment changes, profession promotions and milestone privacy.
- Install the whole updated addon folder and restart WoW to load the bundled
  arrow texture; restart the optional companion for its updated validator.

## Missing Options entry startup fix — 0.10.2, 29 October

Found an unguarded legacy `QUEST_QUERY_COMPLETE` registration in the new progress
collector. Clients that reject the removed event abort the main Lua file before
the event handler and slash commands are installed, so the Options page never
registers. Check C_EventUtils.IsEventValid where available, and protect the legacy
registration with pcall on older clients. Other event registrations stay strict.
Regression tests simulate rejecting clients with and without the validator and
verify initialization, settings registration and /wstatus remain functional.
This reproduces a possible cause; the running client's error has not been captured.
Installed the corrected Vanilla files and rebuilt both addon ZIPs. SavedVariables
are preserved. This addon-only fix needs no server deployment.

## Cleaner preview cards — 29 October

Removed TEST STATUS, EXAMPLE and the player-name example suffix from preview
Discord cards at the user's request. Preview character names still identify them.
The send script now supports Warlock, Warrior and Paladin with --class-name.
These previews still bypass tracker storage. Existing messages are left untouched.

## Race and male/female text — 0.10.1, 29 October

Status descriptions now include text such as `Male Human Warlock · Firemaw`.
Both adapters read UnitSex (2 = Male, 3 = Female); unknown values are omitted.
Race and sex share the existing race privacy checkbox, now labelled accordingly.
No new emojis or Discord slots are needed. Updated the local card preview and
example fixture. Validation: 159 tests passed, including privacy and API values.
Restart WoW and the optional companion to collect/upload the added observation.

## Level emoji correction — 29 October

Replaced the level-30 achievement badge with a generated gold upward arrow,
without numbers. Kept `wow_level` as the filename and Discord emoji name. Updated
its provenance in the manifest and prevented the download script from restoring
the old badge. Rebuilt the emoji ZIP. Existing Discord servers need to replace
their uploaded `wow_level` emoji; no bot redeployment is needed.

## Latest changes — quiet progress cards and previews (0.10.0, 29 October)

- Removed generated login/logout session notifications and duplicate zone notices
  on reload. The server now checks selected progress observations as well as real
  new events; timestamps and playtime increments alone cannot create a post.
- Replaced "since last upload" event counters with tidy Discord character cards:
  name/class, level, faction, optional supplied player name, XP progress, cumulative
  recorded deaths, completed quests, location and current/max profession ranks.
  Event preferences and field privacy still govern triggering and displayed data.
- Classic death totals are recorded observations, seeded from retained local death
  history, and labelled with their tracking start. They cannot reconstruct earlier
  deaths. Quest totals use game-reported completions where available, otherwise
  unique observed turn-ins with an explicit tracked-since label. Profession ranks
  are read from public skill APIs and never guessed from manual names.
- Added **Notification previews** as its own addon settings subpage, also available
  through `/wstatus previews`. It has one local-only button per toast type plus a
  full sample status-card window. Previews change no progress and send nothing.
- Downloaded 29 original WoW icons into `assets/discord-emojis/`. Their manifest
  records image URLs and sizes. The Alliance and Horde images were visually checked.
  Upload the JPEGs with their exact `wow_...` names; the bot uses them automatically
  and falls back to Unicode before upload. The ZIP is in `dist/`.
- The final requested example is a clearly labelled level-33 Alliance warlock with
  15 total recorded deaths, 37.5% XP, 236 completed quests, Stranglethorn Vale,
  an optional example player name, Tailoring 185/225 and Enchanting 150/225.
  It is rendered directly, not inserted into any tracker database. Sending the
  example is the final manual action after deployment and checks.
- Tests: 158 passed; 56 addon tests also passed with Lua 5.1. Checks cover unchanged
  reloads, XP-only changes, cumulative counters, skill ranks, privacy, emoji lookup
  and every preview. Live API observations still need your in-game check.
- This release adds Lua files. Restart WoW fully and restart the optional companion
  so both use the new collectors and schema. No extra app is needed for in-game use.

### Delivery status

- Code committed as `f6ae906` and deployed directly to the server. Both group
  services passed health checks on that revision; SQLite backups were saved first.
- Vanilla 0.10.0 is installed on this computer with the previous addon backed up.
  SavedVariables were preserved. Vanilla, Forever and emoji ZIPs are in `dist/`.
- GitHub push was attempted but rejected (`Permission denied (publickey)`).
  These local commits still need pushing from a computer with GitHub access.
- Final handoff action: send the explicitly requested fictional warlock card to
  navsquad using `scripts/send_status_preview.py --send --group navsquad` on the
  server. This bypasses tracker storage and is labelled TEST STATUS. The final
  response contains the Discord message link if delivery succeeds.

## Latest fix — automatic group updates (0.9.1)

Removed **Receive group updates** and **Send my updates** from the settings page.
Their refresh code looked for account-wide flags in the per-character settings
and could throw a Lua error, leaving the controls unchecked and preventing the
rest of the page from refreshing correctly.

Group membership now automatically enables sending and reception. Old false
values and legacy popup on/off commands cannot disable updates for a selected
group. Remove the group to leave it. Existing per-character sharing and event
privacy choices still apply to outgoing events; Discord remains separately opt-in.
Legacy channel users retain their old toggles outside the normal group flow.

Validation: 149 tests passed, including two simulated clients with both old flags
false and checks that the settings page refreshes every remaining checkbox. The
updated Vanilla addon and both ZIPs are installed/prepared locally. This change
needs no server update; the optional Discord summary service remains on 0.9.0.

## Latest decision — in-game sharing first, optional Discord summaries (0.9.0)

This supersedes the earlier companion-first setup below.

- Friends install only the addon and enter the same account-wide group ID.
  Sending and receiving in-game updates are enabled on this workflow's first
  upgrade; subsequent preferences persist. Paused characters stay paused.
- Shared channels discover members; supported addon whispers carry the event
  messages. Hidden addon messages are not sent over custom channels. The sender
  uses the actual channel roster and recipient identities supplied by WoW.
- Level-ups, introductions, qualifying loot, equipment changes, deaths, zone and
  session updates, and player-entered LFG messages can be shared in WoW. Local
  history and the received activity feed do not require a companion or server.
- Updates appear in an animated upper-middle toast: a large event icon, coloured
  accent, pulsing glow, slide/fade-in and six-second display. Sound is optional.
  **Preview toast** is available in settings; previews never count as real progress.
  The activity window retains up to 200 received updates and clears removed groups.
- Discord has its own visible settings subpage and defaults **off** for both new
  and upgraded characters. Opting in starts a new sharing window. In-game sharing
  and local collection continue when Discord is off. The enrollment bug from
  0.8.1–0.8.3 is fixed without treating local tracking as Discord consent.
- The optional uploader runs on the computer whose Discord-opted-in data is being
  shared. It uploads after the game saves on reload/logout/relog. No uploader is
  needed for the primary in-game feature.
- The bot posts one compact summary per account export, not one message per stored
  event. The server records an explicit chunk manifest and waits for the complete
  batch; retries are deduplicated. Characters and older unsent backlog are combined.
  A snapshot-only export is silent. Summary-mode characters do not also receive
  automatic daily/weekly reports. Synthetic tests are clearly marked separately.
- All enabled level-up events count in Discord summaries, including level 2;
  milestone intervals apply only to the legacy individual-event mode. The selected
  loot rarity filter still applies. Uncertain Discord sends are held for review.
- Native channel discovery and delivery still need a real two-player test on your
  current Vanilla client. Tests use two independent simulated clients and verify
  no companion or Discord opt-in is required. Realm/faction chat limits still apply.

Validation for 0.9.0: 147 tests passed, including two independent simulated game
clients, Discord opt-in/opt-out isolation, full export chunk manifests, summary
batch deduplication, privacy changes during delivery, and toast fade/icon behavior.
The 50 addon tests also passed using Lua 5.1. The installed Vanilla folder and both
ZIP packages were updated with backups; the previously opened companion was
stopped, and inspection of the current export confirmed zero enabled Discord
batches. No test messages were sent to Discord or through the live game client.

Delivery: implementation commit `7dd016b` was deployed through the existing project
receiver after consistent SQLite backups of both group databases. Both ronkalot
and navsquad report that revision healthy, and their summary-batch schema is present.
No unrelated services or gateway configuration were changed. GitHub push still
fails with `Permission denied (publickey)`, so the repository commits remain local
until GitHub SSH access is unlocked and `git push origin main` succeeds. The local
Vanilla install and both ZIPs in `dist/` contain the updated addon.

Testing checklist: install version 0.9.0 on both clients, restart WoW, add the same
group ID, inspect `/wstatus popup status`, preview the toast, and trigger a real
level-up or selected event. Check `/wstatus activity` on the other client. For
optional Discord, enable the separate checkbox, start the companion, export a
few events together, and verify exactly one summary and no duplicate on retry.

## Follow-up — 28 October 2026, addon 0.8.3

The group editor now has a single-line **Group ID** input and **Add** button.
Pressing Enter also adds the ID. Each selected group has its own **Remove** button.
Add and Remove save immediately for the entire account; there is no separate list
Save step to forget. The optional player name has its own **Save name** button.
The editor rejects blank/control-character IDs, duplicates and a ninth group, and
keeps the existing shared-ID matching and per-character history boundaries.
Long IDs show their complete text in a tooltip. Existing saved groups are retained.
Validation: 127 tests passed, including the Add/Remove editor, duplicate and limit
checks. The addon suite also passed under Lua 5.1. Version 0.8.3 is installed on
this computer, with a backup of the previous addon files.

Discord debugging found the navsquad bot connected and its service active, but
its database contained zero uploader enrollments, characters and events. This
computer had no companion configuration, and its on-disk export was still the old
level-1 character with no selected group. The new in-game state needs a `/reload`
or logout, followed by a companion upload. No character data or test messages were
sent during diagnosis.

I then configured this computer's companion with `https://wow.frankvalde.com`,
selected the account's addon SavedVariables file, and opened its desktop window.
It waits for **Start uploading**; no automatic upload was started. Run `/reload`
in WoW to export the new state and click **Start uploading** in that window to
continue the end-to-end check.

A second independent reason for no level-2 message is milestone filtering: both
the character and community defaults announce every 10 levels. To test every
level, set `/wstatus interval 1` in WoW and use Discord `/settings` with
`level_interval:1` (requires Manage Server). These live posting preferences were
not changed during the read-only server investigation.

## Follow-up — 28 October 2026, addon 0.8.2

You confirmed that the original 0.8.1 commit was pushed. The delivery notes below
describe the original work session; this follow-up fixes the two in-game issues
you subsequently reported.

- Replaced the 900-pixel, scaled-down sharing panel with a 600-pixel layout that
  scrolls vertically. Profile fields use two columns; event collection and Discord
  announcements use rows. Text uses a larger font and checkboxes stay 32 pixels.
  Settings pages no longer shrink controls when the settings container resizes.
- Build both settings pages while explicitly hidden, before category registration.
  Previously they relied on `OnShow` to create their content, although newly created
  WoW frames start shown. A first sidebar selection could therefore leave the page
  empty until it was hidden and shown again.
- Support the native canvas `OnRefresh` callback as well as the legacy `refresh`
  callback to update dimensions and frame drawing layers after WoW reparents the
  page. Resizing and refreshing preserve unsaved group edits.
- Expanded the regression test to simulate first opening Groups from the sidebar
  without an `OnShow` callback, and to check populated fields and unscaled controls.
- Full suite: 126 tests passed. The addon tests also pass under Lua 5.1. Real client
  rendering still needs your check after installing version 0.8.2 and reloading.

## Delivery status

The addon changes are implemented, tested and committed locally. **Pushing to
GitHub is blocked by authentication on this computer.** The configured
`github-home` SSH key requires a passphrase and is not loaded in an accessible
agent. Other available authentication did not grant repository access. There is
no configured GitHub CLI login or Git credential helper. I did not change keys or
repository permissions, and did not ask questions while you were away.

The push command, once GitHub SSH access is unlocked, is `git push origin main`.
If this Linux computer reports the system SSH configuration permissions error,
use `GIT_SSH_COMMAND='ssh -F /dev/null -i ~/.ssh/github-home' git push origin main`.
This can prompt for the key's passphrase. A different computer will not receive
this local commit through `git pull` until that push succeeds.

The installed Vanilla addon on this computer has been updated, and the previous
addon files were backed up under `state/addon-backups/20261027-235040/WoWStatus`.
SavedVariables were left intact. Local installable ZIPs are in
`dist/WoWStatus-vanilla.zip` and `dist/WoWStatus-forever.zip` (ignored build outputs).

## Settings live in the normal WoW menu

- Open **Options → AddOns → WoW Status** for character sharing settings.
- Its **Groups** subpage edits account-wide membership and your optional name.
- `/wstatus` and `/wstatus groups` open those same pages.
- Both pages scroll and resize to fit their settings container.
- The implementation supports the modern Settings API and the older
  InterfaceOptions API. Registration retries when Blizzard addons load later.
- Standalone windows remain as a fallback when neither settings API is available.

I used canvas categories so the existing character controls retain their behavior.
The API signatures were checked against the
[Classic UI source](https://github.com/Gethe/wow-ui-source/blob/classic/Interface/AddOns/Blizzard_Settings_Shared/Blizzard_Settings.lua).

## Why the group editor looked broken

The original group and sharing windows could remain visible together at the same
dialog layer, allowing sharing checkboxes and labels to overlap the group editor.
Moving one window did not fix the editor itself: its multiline EditBox also used
the single-line `InputBoxTemplate`.

Groups now has its own settings page. The standalone fallback hides the other
window, and the group field uses a plain multiline EditBox with an explicit font,
padding, a background and cursor scrolling. Enter inserts a new line. Saving
shows its result directly on the group page. Resizing does not overwrite unsaved
group edits. Embedded pages inherit their container's drawing layer and leave
Escape handling to WoW's settings window.

## Account groups, character checkboxes

- Group IDs and the optional player name are stored once for the WoW account.
- Saving the group list updates every saved character, including offline alts.
  New characters inherit it automatically.
- Existing per-character group lists are merged on the first upgraded login.
  The existing eight-group limit remains; if old lists together exceed eight,
  migration keeps a deterministic selection and prints a warning to review it.
- Each character keeps its own membership timestamps and level baseline. Existing
  timestamps are retained. Newly inherited groups start at the new join boundary,
  so old private history is not sent to a newly selected group.
- Removing a group removes it from every saved character. The companion applies
  remote withdrawals after `/reload` or logout exports the account file.
- Character sharing, profile fields, collection and announcement checkboxes remain
  per character. Existing choices, including paused characters, are preserved.
- Explicit legacy `/link` upload mode survives login. Saving the account group list
  explicitly switches all saved characters back to group routing.

Account-wide means one WoW account's SavedVariables file. It does not sync between
computers, different WoW accounts, or separate Vanilla and Forever installations.

## Defaults

For **new characters**, sharing and every checkbox under Profile fields, Store
events / daily recap, and Immediate announcements default to **on**.
Existing characters keep their saved checkbox choices; this update does not
silently reset them.

The introduction still needs **Confirm introduction**. The first initialization
does not queue a separate login-session announcement; subsequent logins/reloads
can queue session events when enabled. Existing filters remain level interval 10
and loot quality 4. Profession names and LFG text still require player input.
Experimental in-game popup send/receive preferences retain their separate opt-in
controls; these are distinct from sharing data through the companion.

No group is invented automatically. Use the configured `ronkalot` or `navsquad`
ID for the intended Discord destination. All selected data still requires the
local companion uploader and an export on `/reload` or logout.

## Validation and deployment

- Full test suite: **126 passed**, including menu registration, both addon
  editions, account inheritance/migration, removals, preserved character settings
  and group history boundaries.
- The addon tests also passed under Lua 5.1, in addition to Lupa's default runtime.
- Ruff passed for the changed Python test file; `git diff --check` passed.
- Both installable addon folders contain the synchronized shared Lua sources.
  Both addon versions are now **0.8.1**.
- Recovered server SSH access through the existing deployment agent. Both
  `wow-character-status` services are active and both loopback health endpoints
  reported healthy revision `bc7bd7f7b97567f93ffc95d4e0e8f7658ac373b9`.
- No server code update is required for this addon-only behavior. The normal
  GitHub checks/package/deployment workflow cannot run for this change until the
  commit is pushed. No Discord test message was sent.
- Real in-game rendering and interaction still need your check; mocked API tests
  cannot establish that the pages render correctly in the running client.

## Tomorrow's check

1. Ensure the local commit has been pushed before pulling it on another computer.
2. Install that computer's updated `addon/vanilla/WoWStatus` folder into the
   correct Classic Era `Interface/AddOns` directory, or use the addon ZIP from
   GitHub Actions once the push and checks succeed. Back up the old addon files;
   preserve `WTF/Account/.../SavedVariables/WoWStatus.lua`.
3. Restart WoW, log in, and open **Options → AddOns → WoW Status**. Check that the
   controls fit and the page scrolls. `/wstatus` should open the same page.
4. Open **Groups**. Enter an optional name and one destination per line. Save and
   confirm the success message. Check that typing, newlines and scrolling work.
5. Log into an alt on the same WoW account. The group list should match, while its
   character checkboxes remain independent. A new character starts with them on.
6. Confirm an introduction if needed, `/reload`, and run the companion with
   `https://wow.frankvalde.com` and this account's `WoWStatus.lua` export selected.
   Check the intended Discord channel. Merely opening the game does not upload.
