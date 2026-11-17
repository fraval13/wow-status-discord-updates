# Login burst: what a login sends (#188)

Issue #188 proposed staggering the work an addon does at login. Triage asked to
measure first and to change the timing only if the numbers show a problem. This
page holds those numbers and how to repeat them.

## How it is measured

`tests/test_login_burst.py` runs the whole addon in several Lua runtimes over an
in-memory whisper network with one shared clock. Every shown frame's `OnUpdate`
runs every quarter second, as the game runs them each frame, and `C_Timer`
tickers run when due, so the log, the character list, equipment and live
updates all keep their real pacing. Thora logs
out, her friends log level-ups while she is away and Mira equips a new epic item,
then Thora logs in again: a fresh runtime that keeps only her SavedVariables, with
`PLAYER_LOGIN` and `PLAYER_ENTERING_WORLD` fired. Everything she sends from that
moment counts, including what `PLAYER_LOGIN` itself sends.

To print the table below:

```sh
.venv/bin/python tests/test_login_burst.py
```

The script runs on Lua 5.1, the game's Lua, with each client's random numbers
seeded, so it prints the same figures on every run. (Newer Lua reorders tables
from run to run, which moves the slower figures by a few seconds.)
The figures are from the mocked clients. They show what the addon asks the game
to send, not what a live client, its chat throttle or a real realm does with it.

## Figures

| Scenario | Sent by the login, 0-10 s | Received by it, 0-10 s | Whole group, 0-10 s | First missed entry | All missed entries | Changed gear | Character list past the allowance in an instance, 0-120 s |
|---|---|---|---|---|---|---|---|
| 3 friends online, 22 entries missed | 28 (Chr 20, Log 8) | 51 (Chr 20, Log 31) | 79 | 3.5 s | 30.5 s | 27.0 s | 6 of 31 |
| 7 friends online, 22 entries missed | 31 (Chr 20, Log 11) | 52 (Chr 26, Log 26) | 83 | 4.5 s | 30.0 s | 61.0 s | 40 of 99 |
| 7 friends online, 106 entries missed | 38 (Chr 20, Log 18) | 57 (Chr 27, Log 30) | 95 | 4.5 s | 171.5 s | 61.0 s | 40 of 99 |

"Chr" is the character list prefix (`WoWStatusChr`: lists, quests, professions,
statistics, equipment), "Log" the log sync (`WoWStatusLog`). Live updates
(`WoWStatus`) send nothing at login. The friends' list, the log and the gear
already saved show at once, from SavedVariables; the times are for what changed
while Thora was away. "Missed" counts every entry a friend wrote while she was
away, whether or not it reached the other friends.

Eight friends logging in at the same moment: the whole group sends 275 messages
in the first ten seconds, 31 to 40 from each client, and the busiest client
receives 66.

## What the numbers say

- There is no burst to stagger. The log and the character list each send at most
  one whisper every half second, so a login sends at most two a second per prefix
  and at most 42 in its first ten seconds however large the group or the backlog.
  Live updates are not paced that way, but a login sends none of its own; it
  only answers each live update a friend sends it with one acknowledgement.
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
- Aside, not about login: in the 106-entry run (a level-up every two seconds
  for three and a half minutes) the friends who stayed online end up with only
  about 70 of those entries each, while Thora's login brings her all 106. That
  is live delivery between online friends, not the login, and is left for a
  separate look; their own next login sync should bring the rest.

So, per triage, the login timing is left as it is.

## Repeating it in a live client

This is fraval13's check; the harness above is not a live client.

1. Type `/wstatus debug on`, then log out to the character screen and log in
   again, with friends online.
2. After about 20 seconds, log out to the character screen again: the game
   writes SavedVariables then. (A `/reload` also counts as a login and adds a
   `login` line of its own.)
3. Open `WTF/Account/<account>/SavedVariables/WoWStatus.lua` and find the
   `debug_log` list. The game writes each entry as a quoted string with a
   comment after it, such as `"1793000000 login", -- [12]`; the number is the
   computer's clock in whole seconds. Find the last entry whose text is
   `login`, and in the ten seconds after it count:
   - entries starting `send ` (character list). They are written just before
     the send and do not show its result; an equipment snapshot the game
     throttles is sent, and written, again later.
   - entries starting `log send ` (log sync), leaving out those ending in
     `throttled`: that try was refused and the packet is written again when
     it goes out. One ending in `uncertain` (an older client's plain `false`)
     is tried once more after two seconds, so it may be counted twice.

   `live send` entries are live updates, which a login does not send.
4. `/wstatus debug off`.

The debug log keeps the newest 500 lines and never names a group. With seven
friends online a login writes about 60 lines in its first ten seconds, so 20
seconds stays well inside that; a much longer wait can push the `login` line
out.
