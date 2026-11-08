# Equipment on character profiles

The character profile scrolls below Level-ups, Recent activity and Recent gear
to a character-sheet layout: eight slots on either side of a portrait/model,
with weapons underneath. Classic-family clients also show ranged/relic and
ammunition slots. Hovering an equipped slot uses its full item string, preserving
enchants, gems and random suffixes. Item names/icons load from the local game
cache, with an item ID shown until the name is available.

The Combat attributes box shows public values the owner's client supplies:
health, mana, the five base attributes, armor, melee/ranged attack power, common
spell power and healing, melee/spell critical chance, dodge, parry, block, haste,
mastery and versatility. Unsupported or restricted values are shown as a dash.
These are observed stats, including buffs, rather than calculations from items.
Spell power/critical chance use the lowest common bonus across magic schools,
matching the character sheet. Melee critical chance is labelled separately.
Versatility includes the public rating and additional bonus.

The actual model is available for the player or a matching public target, focus,
mouseover or party unit. Offline characters use their race/sex portrait. This
release does not send appearance/customization data or reconstruct a character's
face, hairstyle or transmog from equipment IDs.

## Collection and privacy

Each character saves a snapshot on login and on equipment/stat changes (coalesced
to once a second), after loading/combat, and on logout. Other characters on the
same account keep their own last saved snapshots. The Equipment and combat stats
character-detail checkbox controls both capture and sharing. Turning it off
scrubs the local equipment snapshot. Character-list sharing and Hide this
character also gate responses; queued gear packets re-check those choices and
current group membership before sending. No gear changes become announcements.

Equipment is exchanged automatically on login, on Sync now, and when a member's
equipment changes. Opening a profile is no longer required. A short version
advertisement prompts a bounded snapshot request; rapid gear changes are
coalesced, and stat-only changes advertise at most once a minute. These are quiet
addon messages, not chat announcements or popups.

Friends can relay complete saved snapshots for offline owners, but only within
the group in which that snapshot was received. The cache holds up to 256 snapshots
or privacy tombstones. A newer owner revision wins over older data, irrespective
of relay arrival time; the revision and capture timestamp are preserved by relays.
Revisions are persistent per character under the owner's player ID. After an
owner resets that ID, capture time orders the different identities. A newer
advertisement supersedes older pending transfers. Incomplete snapshots keep the
previous complete display until the new one is ready.

Disabling sharing or hiding a character publishes a newer privacy state for
previously shared groups. Revocations are retained and relayed too, so an old
cached copy cannot restore withdrawn gear. An account's existing X withdrawal
also hides/quarantines its cache immediately, awaiting authoritative state.

## Average equipped item level

Both Retail and Forever's character-sheet code take the **second** return from
GetAverageItemLevel(). The first return includes bag gear. We read the public
second return on the owner and exchange it with the snapshot, so the game handles
weapon weighting, empty slots and other client-specific rules. We do not average
required character levels or guess an item level from rarity. Missing/restricted
values remain unavailable. The visible whole number is floored, matching the
character sheet; transmitted hundredths are truncated to preserve that floor.

Primary references:

- [Forever character sheet](https://github.com/Gethe/wow-ui-source/blob/forever/Interface/AddOns/Blizzard_UIPanels_Game/Camelot/PaperDollFrame.lua)
- [Retail character sheet](https://github.com/Gethe/wow-ui-source/blob/live/Interface/AddOns/Blizzard_UIPanels_Game/Mainline/PaperDollFrame.lua)
- [Forever item API, including actual item level](https://github.com/Gethe/wow-ui-source/blob/forever/Interface/AddOns/Blizzard_APIDocumentationGenerated/ItemDocumentation.lua)

The Characters page shows the value in each taller card, above its full-width
bottom XP bar. Maximum-level characters show a full bar; missing XP is labelled
unavailable. Overview shows the local character's equipped average. A live-client
comparison is still necessary; documentation and mocks do not establish values
on the owner's installed build.

## Transport and bounds

EquipmentSync.lua uses the existing WoWStatusChr whisper prefix and joined-group
membership checks. Older clients ignore its new operations and keep the original
D/E profile-request handshake. Background sync uses:

- J: request a group inventory (rate-limited per member/group).
- H: advertise owner ID, character, owner revision, capture time, privacy state
  and validated character identity. Inventories include scoped cached records.
- F: request a specific owner/character/revision from an available provider.
- T: send a requested snapshot part. Replies must match the request's token,
  group, provider ID and whisper sender. Only the complete advertised revision
  can be committed. Unsolicited, older, malformed or mismatched replies fail.

A background snapshot has 24 parts: timestamp, slots 0–19, two ten-stat blocks,
and equipped average item level. Slots distinguish empty (-) from unavailable
(?). Stats and item levels use bounded integers on the wire. Item strings retain
enchants/gems/suffixes; arbitrary hyperlinks and nonfinite values fail.

Up to four background requests can be active, with at most four providers per
record and 64 queued compact jobs. Inventories prioritize owned and newest gear.
Only a small packet window enters the shared queue (hard limit 256 packets);
responses precede inventory traffic. Group membership and own privacy are
rechecked when packets are sent. Metadata requests are limited to one per 15
seconds/member/group; explicit Sync now still has its one-minute cooldown.
Individual data responses are also rate-limited. In-progress work retries with
bounded requests and rotates providers, so a missing owner need not block a
cached relay. Idle synchronized gear does not poll periodically.

All packets are at most 250 bytes and use the existing half-second send interval.
Explicit game throttles/lockdown results use the existing 2/4/8/16-second backoff.
Transfers expire after three minutes; no-part requests can rotate providers after
30 seconds. Partial/reordered/duplicate data cannot replace newer complete data.
The original D/E protocol still has 23 parts and does not carry an average; older
peers require an update to share that field and use background sync.

## Owner's live-client checks

On each supported client, with two updated accounts in a test group:

1. Open your own profile and scroll to the bottom. Check the scrollbar, every
   equipment slot, empty off hand, rings/trinkets, and ranged/relic/ammo where
   supported. Ensure Back and breadcrumbs still work after scrolling.
2. Hover an enchanted or random-suffix item; compare the tooltip with C. Change
   equipment and reopen/refresh. Compare public stats with the character sheet
   under the same buffs. Check unavailable stats display a dash.
3. Log in with two updated accounts without opening profiles. Check gear arrives
   in the background. Change gear and confirm the other client updates; repeat
   with Sync now. Log the owner off and use a third updated account to recover
   the latest cached snapshot from a friend. Replay an older snapshot and check
   it cannot replace the newer one. No popup/log milestone should be generated.
4. Turn Equipment and combat stats off while a reply is pending; check no further
   gear arrives. Refresh after a minute and confirm the cache clears. Repeat with
   Hide this character and character-list sharing off. Leave the group during a
   transfer. Check no milestone, popup or journal entry is produced.
5. Compare the equipped average with GetAverageItemLevel()'s second return,
   including a two-handed weapon, a one-hander plus an off-hand, and empty slots.
   Check item level on Characters and Overview, the taller cards and full-width
   XP bar. In Nynorsk, verify a long popup caption remains directly below the
   fact text, with long reaction buttons below it.
6. Try combat/restricted values, missing item-cache data, an older peer, English
   and Nynorsk, the window sizes/themes, and a public live unit versus an offline
   portrait. Report any client-specific model/API or clipping issues.
