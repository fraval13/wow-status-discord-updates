# Login burst: what a login sends (#188)

Issue #188 proposed staggering the work an addon does at login. Triage asked to
measure first and to change the timing only if the numbers show a problem. This
page holds those numbers and how to repeat them.

## How it is measured

`tests/test_login_burst.py` runs the whole addon in several Lua runtimes over an
in-memory whisper network with one shared clock. Every shown frame's `OnUpdate`
runs every quarter second, as the game runs them each frame, so the log, the
character list, equipment and live updates all keep their real pacing. Thora logs
out, her friends log level-ups while she is away and Mira equips a new epic item,
then Thora logs in again: a fresh runtime that keeps only her SavedVariables, with
`PLAYER_LOGIN` and `PLAYER_ENTERING_WORLD` fired. Everything she sends from that
moment counts, including what `PLAYER_LOGIN` itself sends.

To print the table below:

```sh
.venv/bin/python tests/test_login_burst.py
```

The figures are from the mocked clients. They show what the addon asks the game
to send, not what a live client, its chat throttle or a real realm does with it.

## Figures

| Scenario | Sent by the login, 0-10 s | Received by it, 0-10 s | Whole group, 0-10 s | First missed entry | All missed entries | Changed gear | Character list past the allowance in an instance, 0-120 s |
|---|---|---|---|---|---|---|---|
| 3 friends online, 22 entries missed | 28 (Chr 20, Log 8) | 51 (Chr 20, Log 31) | 79 | 3.5 s | 30.5 s | 27.0 s | 6 of 31 |
| 7 friends online, 22 entries missed | 31 (Chr 20, Log 11) | 52 (Chr 26, Log 26) | 83 | 4.5 s | 30.0 s | 61.0 s | 40 of 99 |
| 7 friends online, 70 entries missed | 38 (Chr 20, Log 18) | 57 (Chr 27, Log 30) | 95 | 4.5 s | 142.25 s | 61.0 s | 40 of 99 |

"Chr" is the character list prefix (`WoWStatusChr`: lists, quests, professions,
statistics, equipment), "Log" the log sync (`WoWStatusLog`). Live updates
(`WoWStatus`) send nothing at login. The friends' list, the log and the gear
already saved show at once, from SavedVariables; the times are for what changed
while Thora was away.

Eight friends logging in at the same moment: the whole group sends 275 messages
in the first ten seconds, 31 to 40 from each client, and the busiest client
receives 66.

## What the numbers say

- There is no burst to stagger. The log and the character list each send at most
  one whisper every half second, so a login sends at most two a second per prefix
  and at most 42 in its first ten seconds however large the group or the backlog.
  A larger backlog takes longer, it does not send faster.
  `tests/test_login_burst.py` fails if that pace is ever exceeded.
- Outside instances the game does not throttle addon whispers, so this pace costs
  nothing there (see the throttle notes in `docs/LIVE_POPUPS.md`).
- Inside an instance the game allows 10 messages per prefix, regained at 1 a
  second. The log already waits for that allowance. The character list does not:
  it keeps its pace of two a second and checks the game's answer only for
  equipment snapshots, so a login inside a dungeon with seven friends online
  would send about 40 list messages past the allowance in its first two minutes,
  and those would be lost until the next sync. That is a follow-up worth its own
  issue; it is not the login burst #188 describes, and a stagger would not fix it.
- Nothing is lost at login outside instances: every missed entry and the changed
  gear arrive, and caught-up entries stay quiet.

So, per triage, the login timing is left as it is.

## Repeating it in a live client

This is fraval13's check; the harness above is not a live client.

1. Type `/wstatus debug on`, then log out to the character screen and log in
   again, with friends online.
2. After a minute, `/reload` so the game writes SavedVariables.
3. In `WTF/Account/<account>/SavedVariables/WoWStatus.lua`, find the last
   `debug_log` line ending in `login`. Each line starts with the realm time in
   seconds. Count the lines in the ten seconds after it that start with
   `send ` (character list) or `log send ` (log); `live send` lines are live
   updates. A `log send` or `live send` line ending in `throttled` means the
   game asked to wait.
4. `/wstatus debug off`.

The debug log keeps the newest 500 lines and never names a group.
