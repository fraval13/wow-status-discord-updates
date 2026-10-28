# In-game group updates

This is the primary WoW Status sharing path. Friends need only the addon and the
same group ID. Discord and the companion are optional.

## Two-player acceptance test

Install version 0.12.0 on both clients and restart them. Use two characters that can
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
profession title promotions and LFG toasts, plus a structured status-card example. Every preview is local only.
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

## Friend milestones (0.12.0)

**Milestones** is a new settings subpage (`/wstatus milestones`). Notification
previews include every new type. Collection and in-game send controls remain
per character; existing progress is silently baselined at login.

- **First dungeon clear:** automatic from LFG completion, or a successful boss
  encounter with a complete, killed encounter roster in a party instance. A boss
  kill by itself is insufficient. When those APIs are unavailable, enter the name
  after a clear and choose **Record first clear**, or `/wstatus dungeon <name>`.
  It records each dungeon once per character, since installation. Manual reports
  retain `source=player_entered`; no dungeon invitation feature was added.
- **First mount:** collection-based when the mount journal reports a first
  acquisition. Existing and late-loading collections stay silent. Clients without
  the journal announce **First mount ride recorded!** on the first observed ride;
  acquisition cannot be reconstructed there. Either path runs only once.
- **Reputation:** new high-water standings of Honored, Revered and Exalted. Initial
  observations, reputation points within a standing, and recovering an old rank
  are silent. Collapsed/unavailable factions are not guessed or expanded.
- **Class unlocks:** a curated set of first-rank class spells, including druid
  forms, warlock pets, major stances, Ghost Wolf, Tame Beast, Shadowform,
  Redemption, Pick Lock and mage city teleports/portals. Existing spells and
  relearning are silent. This is not a universal detector of new Forever-specific
  abilities; unsupported spell APIs disable detection safely.
- **PvP:** increases in the classic rank exposed by UnitPVPRank/GetPVPRankInfo.
  No kill spam. If Forever exposes no compatible rank API, no promotion is guessed.
- **Rare/epic loot:** uses the existing loot notification/filter. Milestones now
  offers **Rare + epic loot** and **Epic loot only** buttons; existing filters are
  preserved. The threshold also includes higher rarities.
- **Discoveries:** manually share up to 120 UTF-8 bytes through the settings field
  or `/wstatus discover <text>`. The toast hides details. Group activity hides
  details until **Reveal discoveries** is clicked; reopening hides them again.
  Details are still transmitted to selected groups and saved in the activity feed.

New milestones use bounded `WSTATUS4` plain-text addon payloads so full discovery
text fits inside a single whisper. They retain the same membership, sender,
client, freshness and deduplication checks. Older versions should be upgraded to
receive the new types. No new Discord emojis are needed. Optional Discord upload
supports the new events and continues posting structured character summaries.

Install the complete addon folder, restart WoW, and restart an optional companion
so it loads the new event validator. Mocked API tests cover behavior; actual
Forever API availability and presentation require checking in the running game.
