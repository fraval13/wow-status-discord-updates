# WoW character logs and Discord bot — project plan

Status: initial implementation written; runtime and in-game validation pending.
Independent from the Forever news feed project. See
[implementation status](docs/IMPLEMENTATION_STATUS.md) and
[home testing guide](docs/HOME_TESTING.md).

## Goal

Let friends opt in to sharing character progress and celebrate milestones in Discord, regardless of guild membership. Provide slash commands for the latest uploaded character status.

## Architecture

WoW addon → local companion uploader → authenticated service and database → Discord bot.

- Addon: collects supported events and character snapshots, with per-character sharing controls.
- Companion: reads exported addon data and uploads only selected information.
- Service: validates uploads, stores profiles and events, applies filters, and deduplicates announcements.
- Discord bot: posts milestones and answers slash commands.

Each participating friend runs the addon and companion. One player's addon cannot reliably observe everything other friends do.

## First technical constraint to prove

Addons cannot directly send HTTP requests to Discord. The initial supported export uses SavedVariables, normally written on `/reload` or logout. A file watcher cannot see events that remain only in the game's memory.

Therefore the initial version provides delayed announcements and last-known status. Immediate notifications require a separate feasibility investigation; do not promise them or use memory reading, client injection, or gameplay automation as a workaround.

Offline delivery should queue locally and retry when connectivity returns. Abrupt game termination may lose events not yet saved to disk.

## Client strategy

Target Vanilla Classic / Classic Era for the initial pipeline test on the owner's home computer. The intended long-term target is WoW Forever, which is not yet
available to the owner. Confirm the exact installed Classic Era build and operating
system at home. Do not test or install dependencies on the work computer.

Classic testing proves collection, export, upload, and Discord delivery. It does not prove Forever compatibility. Keep client-specific event handling, item APIs, and addon metadata separate; verify Forever's actual APIs and event behavior in its client.

Treat all features below as candidates pending client validation. Dungeon completion and boss attribution may need client-specific rules, and entering or leaving an instance alone is not proof of completion.

## Sharing settings

For each character, provide three independent controls:

1. Share this character at all.
2. Which fields are visible through Discord status commands.
3. Which events produce automatic announcements.

Start sharing only after explicit setup. Include preview, pause-all-sharing, and deletion of uploaded character data. Support disabling a category and removing previously stored fields; deleting historical Discord announcements requires a separate policy.

### Character profile checkboxes

- Level, class, race, faction, realm, and guild.
- Equipped gear and enchants.
- Talents.
- Profession choices and skill levels.
- Last-known zone.
- Playtime.

Show a last-uploaded timestamp. Do not imply that last-known location or session state is live presence.

### First-run character introduction

On the first run of the addon for a character, offer to introduce that character
in the configured Discord chat. Queue the introduction only after the player
explicitly enables sharing and confirms the introduction preview. A character
that was already created before installing the addon is still eligible; describe
this as joining the tracker, not proof that the character was just created.

- Example: “A new adventurer joins: Thora — level 1 Dwarf Warrior on Realm!”
- Include only profile fields the player has chosen to share.
- Deliver after the first SavedVariables export and successful upload, normally
  following `/reload` or logout; first-run detection itself does not send HTTP.
- Use a stable per-character introduction event ID and persist delivery state so
  reloads, retries, companion restarts, and addon reinstalls do not routinely
  repeat the introduction. The service must retain the deduplication state needed
  for this behavior under the agreed retention/deletion policy.
- Existing characters also receive at most one introduction when first enrolled.
- Paused or unlinked characters must not deliver queued introductions. After data
  deletion, a later enrollment requires fresh consent and may introduce again.

### Announcement checkboxes

- One-time character introduction on first addon setup, after opt-in.

- Every level-up, selected milestones, and maximum level.
- Loot by minimum rarity; watched items; first acquisition.
- Newly equipped items, weapon changes, and equipment sets where supported.
- Dungeon starts, boss kills, completions, first completions, and participating friends.
- Selected quests, major quest chains, and attunement progress.
- Profession milestones, maximum skill, notable recipes, and crafted items.
- New mounts, companion pets, and reputation milestones.
- PvP honor/rank milestones, battleground wins, and notable rewards.
- Session start/end and last-known zone changes.
- Optional deaths, cause of death where available, and session summaries.
- Player-entered looking-for-group status and dungeon interests.

Suggested initial selections, presented during opt-in: level milestones, epic loot, dungeon completions, profession milestones, and mounts. Keep location, deaths, playtime, and session activity unchecked.

## Noise controls

- Minimum loot quality and item allowlists/exclusions.
- Level milestone interval.
- Individual messages or session digest per category.
- Only announce group runs involving registered friends.
- Group duplicate reports into one dungeon announcement when event evidence supports matching.
- Suppress duplicate uploads using stable event IDs and per-character sequences.
- Treat newly observed items as a baseline; do not announce existing inventory as fresh loot.
- Optional role mentions; leave mass mentions disabled.

## Discord commands

- `/character name:<name> realm:<realm>`: latest shared profile, gear, and upload timestamp.
- `/characters`: shared characters within this Discord community.
- `/activity character:<character>`: recent shared milestones.
- `/link`: securely associate a companion installation and character with a Discord user.
- `/privacy`: inspect sharing choices and request data removal.

Resolve duplicate character names using realm and client identity. Restrict profile visibility to the intended Discord community by default. Users can only change sharing and ownership settings for their own linked characters.

## Discord access

- A server owner or someone with **Manage Server** installs the app.
- Bot permissions: **View Channel**, **Send Messages**, and **Embed Links** in selected channels.
- Members need **Use Application Commands** where commands are offered.
- No Administrator permission is needed.
- Slash commands do not require reading ordinary chat messages or enabling the Message Content privileged intent.
- Phone alerts depend on members' Discord notification settings.

The bot can handle both announcements and commands; a separate webhook is unnecessary for this project.

## Data and security

- Never request Battle.net passwords or upload whole account folders.
- Upload only this addon's selected data, using revocable per-installation credentials over HTTPS.
- Read SavedVariables as data with a constrained parser; never execute its Lua contents in the companion.
- Validate event types, sizes, timestamps, ownership, and item metadata server-side.
- Keep bot tokens and uploader credentials out of source control and logs.
- Store client, realm, character identity, owner, sharing settings, snapshot timestamp, and event IDs.
- Choose event retention and deletion behavior before launch.
- Treat uploads as player-reported telemetry, not authoritative anti-cheat evidence.

## Implementation milestones

1. Confirm gaming OS, exact WoW client, addon installation path, and test Discord channel.
2. Create an addon with `/test`-style synthetic event support, real level-up capture, and SavedVariables export.
3. Build a companion with dry-run output, constrained parsing, stable IDs, and restart recovery.
4. Connect one character to the service and post a test announcement after `/reload`.
5. Add `/character` showing level, class, realm, and last upload time.
6. Add opt-in checkbox settings, pause, linking, data removal, and the one-time first-run character introduction.
7. Add loot filters and test with two friends; add dungeon detection only after validating event evidence.
8. Test Forever separately and adapt its client-specific APIs.
9. Investigate supported lower-latency exports if delayed announcements do not meet the group's needs.

## Acceptance checks

- First addon setup offers an introduction preview; after opt-in and export,
  exactly one introduction reaches the configured chat using only shared fields.
- Reloads, repeated uploads, restarts, and reinstalls do not repeat introductions
  while the service retains the character enrollment and deduplication state.
- Declining introduction or pausing/unlinking before delivery prevents the post.
- Synthetic and real level-up events reach the private channel after export.
- Reloading, companion restarts, and repeated uploads do not create routine duplicate announcements.
- An unchecked field is neither uploaded nor returned by commands.
- A paused or unlinked character stops generating new shared events.
- Commands show stale timestamps honestly and distinguish characters with identical names.
- Retries recover from network failures and Discord rate limits.
- A malformed SavedVariables file cannot execute code in the uploader.
- Two friends reporting one run do not produce duplicate completion messages when matching is reliable.

## Decisions still open

- Gaming operating systems and exact clients.
- Whether `/reload`/logout delivery is acceptable.
- Preferred default checkbox selections and milestone interval.
- Hosting/runtime and friend onboarding method.
- Character ownership verification and retention/deletion policy.
- Which dungeon events are reliable on each supported client.

## Structured history and daily recap (confirmed requirements)

- Automatically maintain one structured JSON file per character, grouping identity,
  selected profile snapshots, level history, loot/equipment, activity and daily recaps.
- Retain all collected, consented snapshot and event history until deletion. Storage
  controls are separate from immediate announcement controls; milestone and rarity
  filters apply to immediate messages without discarding enabled event history.
- Preserve actual level-up event time separately from first upload time. A first
  observed level is a baseline and must not fabricate historical level-up times.
- Use `Europe/Oslo` in every JSON file and each timestamp, with offset-aware
  ISO 8601 values that automatically reflect Norwegian summer/winter time.
- At the owner-approved time of **00:05 Europe/Oslo**, post the previous Norwegian
  day's recap covering every currently shared character known by that day's end.
  Include zero-event characters honestly, late uploads, per-kind counts and highlights.
- Keep the full detailed data in JSON for later use. Field/category disabling scrubs
  related historical data; deletion removes managed JSON and database records.
- See [JSON format](docs/JSON_FORMAT.md) for grouping, timestamp and export details.


## Friend-group improvements (approved)

Use the linked Discord member's server display name by default; offer `/nickname`
for a preferred label. Never require real-name input in the addon. Keep identity
and authorization tied to Discord user ID, independent of display name. Group the
roster and combined daily/weekly recaps by that owner. Support one main plus alts,
celebrations versus routine activity, snapshot progress labeled as inferred, a
friendly desktop uploader, and structured source metadata for later analysis.
See [friend-group behavior](docs/FRIENDS_AND_RECAPS.md) for the written implementation,
home acceptance checks, and still-deferred client-dependent context collection.

## In-game history and level graph (approved)

Add a scrollable, saved log of collected export events, an export preview, and a
line graph with level vertically and elapsed time horizontally. Record complete
consecutive level durations, label the first mid-level observation as partial, and
leave missing tracking segments disconnected. Preserve the graph source records
in character JSON with explicit Europe/Oslo metadata. In-game logs must not claim
confirmed network delivery. See [history details](docs/IN_GAME_HISTORY.md).

## Experimental in-game level popups (approved)

Add optional low-latency level notifications alongside the exported Discord path.
Use a manually joined custom channel, explicit outgoing sharing consent, trusted
actual game senders, duplicate/rate limits and combat deferral. Keep sound off by
default, never merge peer reports into the local character's graph, and respect
client chat restrictions. The first transport sends visible messages; actual
cross-guild/faction/realm and Forever compatibility must be established at home.
See [popup setup and acceptance](docs/LIVE_POPUPS.md).

## Direct group IDs (confirmed requirement)

Allow free text group IDs, one per line in WoW. Each character can select one or
several IDs, with two independent Discord destinations as the initial operator
setup. No /link step is required. Store per-installation credentials automatically;
use addon name entry because group-only membership does not verify Discord identity.
Only selected targets receive post-join events. Removing a group stops local popup
routing immediately and withdraws the shared character after export/upload.
See [group design, setup and limits](docs/GROUPS.md).
