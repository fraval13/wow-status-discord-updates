# In-game group updates

This is the primary WoW Status sharing path. Friends need only the addon and the
same group ID. Discord and the companion are optional.

## Two-player acceptance test

Install version 0.10.0 on both clients and restart them. Use two characters that can
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
buttons for level-up, introduction, loot, equipment, death, zone, quest, profession
and LFG toasts, plus a structured status-card example. Every preview is local only.
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
