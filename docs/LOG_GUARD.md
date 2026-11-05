# Invalid log data

**Since 1.9.0 the warning popup described below is removed.** Invalid incoming
data is still rejected before it enters the activity log, but nothing is shown
or sent: no popup, and no `J2 W` report to the group. Reports from older
versions are ignored. The owner asked for this after a friend received the
warning without doing anything wrong: versions can validate a few texts
differently, so a mixed group produced false accusations.

The rest of this page documents the removed 0.14.10 behaviour, for history.

---

# Invalid-log warnings — 0.14.10

Invalid incoming data is rejected before entering the activity log. Selected
clear violations also produce the owner's requested group-visible popup:

> Eldrin is a really bad boy, shame on you!

The heading says **INVALID LOG DATA REPORTED** and the detail identifies the
reporter. The accused name comes from the actual sender of the addon whisper,
including when that sender relays an entry claiming a different author. It is a
report of invalid data, not authenticated proof of deliberate cheating.

## Triggers

- Current-edition live level packets outside the edition's level bounds.
- Live packets containing forbidden control/markup characters, or injected
  free text in the fixed-format introduction/death categories.
- Requested catch-up entries with malformed field framing, invalid identity
  structure, impossible levels, forbidden text, a mismatched offered ID digest,
  or conflicting fragments. Level text must match the numeric level; introduction
  and death text must use their supported formats.

A warning requires a discovered member of the same group. Unsolicited catch-up
responses, wrong editions, unknown message types, stale packets, ordinary
duplicates, rate limits and disabled armor rarities remain quiet drops. Both old
and clarified group-join wording are accepted. Other existing filters remain.

## Delivery and bounds

Warnings use the existing game-approved addon whisper transport and the
`WoWStatusLog` prefix, with a bounded `J2 W` message containing the client, time
and direct sender's name. No arbitrary warning text travels over the network.
The receiving client constructs the fixed message and names the reporter using
the actual whisper sender. Both reporter and accused must be known group peers
(the receiving player can also be the accused).

Each client permits at most one warning per minute overall and one warning per
accused/group every ten minutes. Cooldown storage is bounded to 128 keys and
fan-out to 64 discovered peers. Queued reports expire after two minutes. Combat,
chat lockdown, paused sharing and group removal are respected. Receiving a report
never forwards it, preventing echo loops.

Warnings use the ordinary popup queue and click dismissal. They do not become
milestone events, activity-log entries, offline recovery data or Discord exports.
There is no manual warning command. Older addon versions ignore the new message;
all recipients must update to 0.14.10 to display it.

## Limits and testing

This is validation plus a shared warning, not a decoy honeypot or an anti-cheat
authority. A modified addon can fabricate a plausible milestone or a report.
The reporter remains visible and reports are bounded, but there is no cryptographic
proof of wrongdoing. The filter also does not claim to detect every unwanted word
inside legitimate game names or all fabricated progression.

Tests use simulated Lua clients only. They cover all four editions, live and
catch-up attacks, attribution to the direct relay instead of a forged author,
bounded group delivery, no persistence/echo, ordinary quiet drops, expiration,
pause and group removal. No warnings were sent to real players or Discord.
Actual in-game rendering and delivery remain to be checked.
