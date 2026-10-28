# In-game group updates

This is the primary WoW Status sharing path. Friends need only the addon and the
same group ID. Discord and the companion are optional.

## Two-player acceptance test

Install version 0.9.0 on both clients and restart them. Use two characters that can
communicate through the same custom channel (normally the same realm and faction).
Do not run a companion for this test.

1. Both players open `/wstatus groups`, enter `navsquad`, and press **Add**.
2. In `/wstatus`, verify **Share this character**, **Receive group updates**,
   **Send my updates**, and the desired event's **Store locally / Share in WoW**
   checkboxes. Defaults are on. Discord remains off.
3. Both players run `/wstatus popup status`. Check that the group channel is joined
   and that its discovered peer count includes the other character. The count can
   include people without the addon; only matching addon clients display updates.
4. One player reaches level 2 or another real level. The other should receive an
   animated toast with a large icon, coloured accent and pulsing glow, plus an entry in `/wstatus activity` without `/reload`.
5. Try a selected death, zone or qualifying loot event. Events are compact text;
   full inventories and talent profiles are not transmitted.
6. Remove the group, try another event, and verify no further updates are accepted
   for that group. Previously received activity for it should disappear.
7. Turn off **Send my updates** and verify outbound updates stop while reception
   can remain enabled. Pausing the character also cancels queued outbound updates.
8. Test combat deferral and reconnects. A blocked/unavailable API must show a
   diagnostic state rather than claim confirmed delivery.

`/wstatus popup test` (or **Preview toast** in settings) previews the toast locally.
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

On the first upgrade to the in-game-primary workflow, send/receive preferences
are enabled once. Existing per-character sharing/privacy choices are retained;
subsequent send/receive changes persist. Discord is independently off by default.

Explicit legacy `/wstatus popup channel WStatusNAME` and per-character trust
commands remain available for testing old visible-channel installations. Normal
group sharing uses addon whispers and does not need this legacy setup.
