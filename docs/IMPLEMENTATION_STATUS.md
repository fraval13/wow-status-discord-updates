# Implementation and validation status

Written on October 27, 2026. All runtime validation is pending, because the owner
requested that no testing occur on the work computer. No project dependencies have
been installed there. No service has been deployed and no Discord messages sent.

## Current status: 0.10.0

In-game group sharing is the primary path. The optional Discord uploader requires
an independent per-character opt-in and produces complete-export summaries.
The full local suite passes 158 tests; the 56 addon tests also pass under Lua 5.1.
Menu rendering has had user testing, while the new two-player whisper transport
and animated toasts still need live client acceptance. Mocked clients do not
establish delivery on an actual realm. See [the current setup](../README.md) and
[in-game test checklist](LIVE_POPUPS.md).

Current cumulative deaths, completed quest counts, XP percentages and profession
ranks are implemented with unavailable/historical values explicitly labelled.

The implementation table below describes the earlier companion/server baseline.
Its original outstanding-validation labels are historical; the updated setup and
release decisions in [decisions_i_made.md](../decisions_i_made.md) take precedence.

| Area | Implemented in source | Still required |
| --- | --- | --- |
| Addon | Classic Era boundary, opt-in panel, selected profile, event export, introduction preview and confirmation | Actual client/build/locale validation |
| Introduction | Canonical character introduction ID on server, privacy-aware formatting, first-run preview | Real export/upload/Discord acceptance |
| Companion | Constrained data parser, limits, double privacy filtering, HTTPS, credentials, repeat suppression, retry from SavedVariables | Windows/macOS/Linux home execution |
| Service | SQLite, one-use links, ownership enforcement, stale-export rejection, authenticated uploads, request limits | Runtime and deployment checks |
| Discord | Guild-only slash commands, no message-content intent, safe mentions, persistent outbox, uncertain-send review | Bot token, guild/channel configuration, permissions tests |
| Privacy | Explicit consent, per-field/per-category controls, pause/revoke, deletion, history scrubbing, retention | Home acceptance, operator backup expiry policy |
| Packaging | Python CLI, addon installer, systemd and reverse-proxy examples | Install and deployment on chosen personal hosts |
| JSON history and daily recap | Per-character grouped JSON, complete collected level history, Oslo ISO offsets/timezone, DST-aware windows, 00:05 scheduler, late uploads and restart deduplication | Home history/privacy/recap acceptance |
| Tests | Parser/schema, store, HTTP flow, mocked Lua, bot registration and cancellation cases | Execute at home; manual-only GitHub workflow available |

No end-to-end success or current-client compatibility is claimed without executing
these checks. Lupa exercises mocked APIs only; actual game behavior is a separate
acceptance step. The TOC interface number must be taken from the installed game.

## Intentionally deferred client-dependent features

Dungeon completion and boss attribution, reliable multi-friend run grouping,
quest chains/attunements, talent profiles, profession recipes, mounts/pets,
reputation and PvP need explicit per-client evidence and in-game validation.
They are not currently collected. Inventory items are not inferred as fresh loot
on startup. First acquisition, watchlists, digests, optional role mentions and quiet
hours remain later enhancements. Loot metadata that is unavailable at the event
can currently be missed; no cache-retry collector is included in this first version.

The addon protects privacy at collection/export and both the companion and service
filter again. An addon-local pause reaches the server only after export/upload;
use Discord `/privacy` for immediate server-side revocation. Discord sends already
in flight cannot be recalled. Existing Discord posts and operator backups require
a separate removal/expiry process. Ownership is linked-user assertion, not Battle.net
verification. Daily recaps are deterministic; no OpenAI API calls are included. Consented history
has no automatic expiry and is archived in grouped per-character JSON files.

## Before enabling wider use

1. Execute the authored tests and the keyless local pipeline on a personal computer.
2. Validate the addon on the exact Classic Era build and locale.
3. Configure a private Discord test channel and validate linking, introductions,
   level/loot flows, privacy changes and uncertain-send handling.
4. Choose hosting, configure HTTPS and private backups, and onboard two friends.
5. Add a Forever adapter only when the client can be inspected and exercised.

Confirmed archive/recap requirements: retain every collected event independently
of immediate announcement filters, one JSON archive per character with grouped
records, actual level-up time plus upload time, explicit `Europe/Oslo` timezone
and ISO offset on every timestamp, and daily recaps at 00:05 Oslo time.


Friend-group improvements are also written and await home validation: Discord
names with optional self-service nicknames, main/alt ownership controls, paginated
roster, combined daily/weekly group reports, snapshot-change evidence, group noise
settings, optional Tk desktop uploader, player-entered profession labels, and
friend/role/source context in per-character JSON. Automatic party attribution and
profession skill collection still require actual client evidence and validation.

Scrollable in-game history, a step-line graph (level versus elapsed time), per-level
duration records, persistent local history upload batches and timezone-aware JSON
timeline data are written. Runtime/in-game validation remains pending at home.

Experimental in-game level popups are written: explicit receive/send consent,
visible custom-channel transport, trusted sender list, local friend labels, bounded
queues, deduplication, combat deferral and privacy cancellation. Client chat API
restrictions, cross-guild/faction/realm behavior and Forever support remain
unverified. No popup or communication tests have run on the work computer.

Direct group-ID membership is written: free-text one/many ID list in WoW, addon
name entry, deterministic route/channel keys, isolated service/database per group,
automatic credential enrollment without /link, scoped history and membership
withdrawals, companion privacy controls, and matching popup groups. No runtime or
in-game validation has been performed. Forever compatibility remains planned only.

The Vanilla and Forever packages now have separate complete folders and a shared
Python service. Group IDs use the same Unicode case-fold map in Lua and Python,
so capitalization does not create another group. GitHub checks run remotely, and
the deployment pipeline targets dedicated server paths/users/ports for `ronkalot`
and `navsquad`. No application or dependency installation runs on the work computer.
