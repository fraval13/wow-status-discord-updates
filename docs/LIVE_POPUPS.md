# In-game group updates

This is the primary WoW Status sharing path. Friends need only the addon and the
same group ID. Discord and the companion are optional.

## Two-player acceptance test

Install version 0.12.1 on both clients and restart them. Use two characters that can
communicate through the same custom channel (normally the same realm and faction).
Do not run a companion for this test.

1. Both players open `/wstatus groups`, enter `navsquad`, and press **Add**.
2. Joining the group automatically enables sending and receiving. In `/wstatus`,
   check the character's sharing and the desired event's **Store locally / Share
   in WoW** options. These are separate from the removed send/receive switches.
   Discord remains independently opt-in.
3. Both players run `/wstatus popup status`. Check that the group channel is joined
   and that its discovered peer count includes the other character. The count can
   include people without the addon; only matching addon clients display updates.
4. One player reaches level 2 or another real level. The other should receive an
   animated toast with a large icon, coloured accent and pulsing glow, plus an entry in `/wstatus activity` without `/reload`.
5. Try a selected death, quest completion, profession skill-up, zone or qualifying loot event. Events are compact text;
   full inventories and talent profiles are not transmitted.
6. Remove the group, try another event, and verify no further updates are accepted
   for that group. Previously received activity for it should disappear.
7. Verify saved `receive=false` / `broadcast=false` values from older versions do
   not block updates after joining a group. Remove the group to leave it. Character
   pause and event privacy settings still cancel corresponding outbound updates.
8. Test combat deferral and reconnects. A blocked/unavailable API must show a
   diagnostic state rather than claim confirmed delivery.

`/wstatus previews` opens the **Notification previews** settings page, with separate
buttons for level-up, introduction, loot, death, zone, 100-quest achievements,
profession title promotions and automatic milestone toasts, plus a structured status-card example. Every preview is local only.
`/wstatus popup test` remains a shortcut for the original local level-up preview.
Toasts fade/slide in near the upper-middle of the screen, stay for six seconds and
fade out. They do not print normal event updates to chat. Sound is off by default;
`/wstatus popup sound on` enables it. `/wstatus test` records a
synthetic test event locally. Neither sends a fake level-up to friends.

## Transport and boundaries

The custom channel is for discovery. The addon reads its roster with the game
APIs and sends registered `WoWStatus` addon messages over **WHISPER**, with a group
key in the envelope. It never sends hidden addon messages over custom channels.
The recipient accepts only selected group IDs and its own client edition, using
the sender identity supplied by WoW. Packets have bounded size, freshness windows,
queues and deduplication; duplicate group routes do not repeat a level-up.

The native API signatures are checked against Blizzard's extracted
[ChatInfo documentation](https://github.com/Gethe/wow-ui-source/blob/classic/Interface/AddOns/Blizzard_APIDocumentationGenerated/ChatInfoDocumentation.lua)
and [channel roster implementation](https://github.com/Gethe/wow-ui-source/blob/classic/Interface/AddOns/Blizzard_Channels/ChannelRoster.lua).
Realm/faction communication rules, restrictions, delayed rosters and client
compatibility still require actual game validation. There is no delivery receipt
or offline replay. Send attempts are paced and expire after two minutes. Queued
notifications defer during combat and expire after ten minutes. Up to 200 received
updates are retained in the local activity feed.

Since 0.9.1, group membership alone controls group sending and reception. Old
popup send/receive flags and legacy on/off commands do not disable selected groups.
Remove a group to stop its updates. Character and per-event privacy choices are
retained. Legacy flags still apply only to explicitly chosen legacy channels.
Discord remains independently off by default.

Explicit legacy `/wstatus popup channel WStatusNAME` and per-character trust
commands remain available for testing old visible-channel installations. Normal
group sharing uses addon whispers and does not need this legacy setup.

Reloads/logins/logout and unchanged zone-loading events do not generate updates.
Real progress events and newly observed XP/counters/ranks still update the selected
status. Death counters are cumulative recorded totals rather than per-session deltas.

## Notification rules (0.11.0)

- Level-ups use the bundled gold upward arrow. Introductions use a friendly
  adventurer portrait instead of the severed-head item icon. Quest milestones use
  a quest achievement icon; professions use the matching trade icon when known.
- Equipment changes update the profile silently and have no notification setting
  or preview. Existing saved equipment notification preferences are disabled.
- Quests still count individually, but in-game notifications appear at 100, 200,
  300, etc. Counts reported by WoW take precedence; otherwise locally tracked
  completions are used. Login and changes in count source establish silent
  baselines, so historical achievements are not replayed.
- Profession points still update the profile. In-game notifications require an
  increased profession rank cap: Apprentice 75, Journeyman 150, Expert 225,
  Artisan 300. Ordinary skill points and initial observations are silent.
- Real notifications and previews share a FIFO queue. Each card displays for six
  seconds with a short gap. Distinct level-ups are not merged. Combat defers
  display. Accepted queued cards do not expire while waiting; up to 128 can wait.
  Duplicate network messages are still ignored. Previews never enter the activity
  feed or tracker data. Group removal cancels that group's pending messages.
- Discord remains a progress-card summary on upload; it can include updated
  quest totals and profession points. These milestone rules govern in-game toasts.

## Automatic friend milestones (0.12.1)

**Milestones** is a settings subpage (`/wstatus milestones`) with an explanation
of automatic detection and the existing rare/epic loot filter buttons. There are
no free-text announcement fields. Notification previews cover every supported
type and are local only. Existing progress is baselined silently at login.

- **First dungeon clear:** requires a game completion event or a complete killed
  encounter roster after a successful boss encounter in a party instance, with
  a valid instance ID and name. An arbitrary boss kill is insufficient. Clients
  without a reliable completion API skip the announcement. Each dungeon is
  recorded once per character. Previously recorded game-detected clears seed
  the new cache; old manual reports do not.
- **First mount:** collection-based on a first acquisition when supported. Existing
  and late-loading collections stay silent. Clients without the journal announce
  **First mount ride recorded!** on the first observed ride, once per character.
- **Reputation:** new high-water standings of Honored, Revered and Exalted.
  Points within a standing, initial observations and recovering old ranks are silent.
- **Class unlocks:** a curated set of first-rank spells, including forms, pets,
  stances, Ghost Wolf, Tame Beast, Shadowform, Redemption, Pick Lock and mage
  teleports/portals. Existing/relearned spells stay silent. Missing APIs skip
  detection; this does not cover every new Forever-specific ability.
- **PvP:** increases in the classic rank exposed by UnitPVPRank/GetPVPRankInfo;
  no kill spam and no guessed promotions when those APIs are unavailable.
- **Rare/epic loot:** uses the existing rarity filter. Milestones offers Rare + epic
  and Epic-only buttons; the selected threshold also includes higher rarities.

Discovery sharing, manual dungeon reports and free-text LFG announcements are
removed, including their previews and old slash commands. New clients ignore
legacy discovery/LFG packets and the old dungeon format that allowed manual
reports. Dungeon packets now use WSTATUS5 with an instance ID and name; other
automatic milestone types retain WSTATUS4. Friends should update their addons.
Old free-text entries are removed from the in-game activity cache; historical
Discord messages are not edited. Server validation and pending-delivery checks
also ignore removed manual event types and player-entered dungeon reports.

These checks constrain the normal addon's announcement paths; addon messages
remain player-reported data, as with the rest of the protocol. No extra Discord
emoji slots are required. Restart/reload WoW and restart an optional companion
for the updated event handling. Live Forever API behavior still needs checking.

## Persistent graphical log and peer catch-up (0.13.0)

`/wstatus activity` now opens the graphical **Activity log**; `/wstatus journal`
is an alias. Local announcements and received updates share stable IDs across
log copies. Private quest, equipment and skill-point observations are logged
without broadcasting. Previews remain local samples and are not logged.

The `WoWStatusLog` prefix carries group-scoped paginated inventories, missing-ID
requests and bounded fragments. Requests require current membership and a roster
peer, valid request tokens, bounded counts and freshness/join-time checks. Full
records are length-prefixed data and hex fragments; no remote Lua is evaluated.
A request offers six IDs per page, at most 20 pages per round, and resumes later.
At most two groups actively request at once. Outbound traffic is limited to two
packets per second and deferred in combat; requests, fragments and queues expire
or have fixed bounds. Catch-up is log-only and does not trigger popup display.

For acceptance testing, have A announce a level to B while C is absent. Log A out,
bring C online (already a member of the group), and press **Catch up** on C. It
should recover A's entry from B once, with its original time/ID, without a popup.
Repeat sync and check duplicates, another group's isolation, group removal,
privacy changes and scrolling while new activity arrives. Also check a client
with no peers: its own log must keep working.

See [Activity log and history](IN_GAME_HISTORY.md) for retention and limitations.
