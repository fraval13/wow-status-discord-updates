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

Friends fetch one snapshot when a profile opens or Refresh gear is clicked,
at most once a minute per character. An online character on the owner's account
can answer for an offline alt that previously logged in with the new addon.
Receivers retain completed snapshots across logout and character-list refreshes.
The date displayed is the snapshot's capture time, not the time it was opened.
There is no periodic equipment broadcast and no remote Inspect request.

## Transport and bounds

Uses the existing WoWStatusChr whisper prefix and joined-group membership checks.
Older clients ignore the new operations. All words are bounded; packets are at
most 250 bytes and use the roster's existing half-second send interval.
Explicit game throttles/lockdown results use the existing 2/4/8/16-second
backoff. Queued equipment traffic expires after three minutes; permanent errors
do not create an unbounded retry loop.

- D group playerID character requestID requests a character's snapshot.
- E group playerID character requestID part value replies to that request.
- Request IDs are eight hexadecimal digits. Responses must match the requested
  account, sending character, group, target character and request ID.
- A snapshot has 23 parts: t (capture time), slots 0–19, and a/b (ten stats each).
  Slots carry a validated item string, - (empty), or ? (unavailable).
  Stats are fixed fields, with percentages in integer hundredths and - for
  unavailable values. Arbitrary hyperlinks and nonfinite/oversized numbers fail.
- x clears a snapshot when sharing is off; n means no saved snapshot exists yet.
- Eight requests can be pending, each for at most three minutes. Requests and
  replies are rate-limited per character/member; response rate-limit state is
  bounded to 128 entries. New equipment traffic cannot grow the roster queue
  beyond 256 packets. Each request stages only one bounded snapshot.
- The receiver commits a new snapshot only after all 23 unique validated parts
  arrive. Duplicate/reordered parts are harmless; incomplete/expired transfers
  leave the previous snapshot intact. No journal event or popup is generated.

API references: Blizzard's generated [unit API documentation](https://github.com/Gethe/wow-ui-source/blob/live/Interface/AddOns/Blizzard_APIDocumentationGenerated/UnitDocumentation.lua)
and [character-sheet code](https://github.com/Gethe/wow-ui-source/blob/live/Interface/AddOns/Blizzard_UIPanels_Game/Mainline/PaperDollFrame.lua).
Calls use Safe.lua and skip unavailable, failing or secret values; mocks do not
establish live game availability.

## Owner's live-client checks

On each supported client, with two updated accounts in a test group:

1. Open your own profile and scroll to the bottom. Check the scrollbar, every
   equipment slot, empty off hand, rings/trinkets, and ranged/relic/ammo where
   supported. Ensure Back and breadcrumbs still work after scrolling.
2. Hover an enchanted or random-suffix item; compare the tooltip with C. Change
   equipment and reopen/refresh. Compare public stats with the character sheet
   under the same buffs. Check unavailable stats display a dash.
3. Open the friend's profile and let the transfer finish. Verify all items and
   stats belong to that character. Repeat for an offline alt while its owner is
   online. Log the owner off and reopen the cached snapshot.
4. Turn Equipment and combat stats off while a reply is pending; check no further
   gear arrives. Refresh after a minute and confirm the cache clears. Repeat with
   Hide this character and character-list sharing off. Leave the group during a
   transfer. Check no milestone, popup or journal entry is produced.
5. Try combat/restricted values, missing item-cache data, an older peer, English
   and Nynorsk, the window sizes/themes, and a public live unit versus an offline
   portrait. Report any client-specific model/API or clipping issues.
