# Optional Discord export summaries (0.9.0)

Discord sharing is off by default and independent of in-game sharing. Opt in per
character with `/wstatus discord`. After `/reload`, logout or relog, the optional
running companion uploads the newly shared activity. The bot waits for every
chunk of an account export and sends one bounded summary, combining characters
and counting events instead of sending a stream of individual messages.

Retries do not repeat events or completed summaries. Empty exports are silent.
An incomplete upload waits for its remaining chunks; a later complete export can
absorb an older unsent backlog. Uncertain sends are held for review. Privacy is
rechecked after channel lookup and before sending. In summary mode every selected
level-up is counted, including level 2; old individual-message milestone filters
do not suppress summary counts. Loot still follows the chosen rarity filters.
Synthetic tests are explicitly labeled and excluded from real progress counts.

Automatic daily/weekly recaps remain available to legacy event-mode installations;
summary-mode characters are excluded so they do not receive duplicate scheduled
reports. The historical individual-event output documentation follows.

# Discord progress updates

Automatic posts use the destination server's unrestricted custom emojis named
`wow_new`, `wow_levelup`, `wow_loot`, `wow_gear`, `wow_death`, and `wow_recap`.
Missing/unavailable emojis fall back to standard Unicode. Each group resolves only
its own server's emojis. No privileged Discord intents are required.

Level updates show recorded location, observed level-up count for that character's
Oslo day, and timing when available:

- **Played** duration comes from the client's total `/played` minus time at the
  current level, compared with the previously recorded level's played boundary.
  It excludes offline time. Playtime sharing must be enabled. No previous boundary
  or skipped levels means no played duration is displayed.
- **Elapsed** duration comes from consecutive observations in the same tracking
  segment and includes offline time. A baseline observed midway through a level is
  marked partial. Gaps and paused tracking are not joined.
- The daily count means recorded events, rather than an inferred total. Late
  uploads keep the date the event happened, in `Europe/Oslo`.

Every tenth level gets a milestone embed; the adapter-reported cap gets a gold
level-cap embed. Existing personal and group announcement filters still apply.
No personal-best tracking or ranking is added.

Loot and equipment posts use rarity-coloured embeds when quality was recorded.
Classic Era item IDs link to Wowhead Classic. Forever IDs are displayed without an
external database link because no authoritative Forever item lookup is configured.
Names and original game links remain in the structured JSON. Unknown rarity is
labelled rather than guessed.

Daily recaps remain scheduled for 00:05 Europe/Oslo, grouped by player and character.
They show recorded level gains, deaths, notable loot, level timestamps and locations.
Played time is a **lower bound** from actual client samples inside that Oslo day or
complete recorded same-day level intervals. The larger lower bound is used to avoid
double-counting overlapping evidence. One sample alone establishes no duration.
No sample before midnight is attributed to the following day. Weekly summaries sum
these daily lower bounds. JSON retains the underlying evidence and explicit timezone.

Location and playtime remain optional; enable those profile fields in the addon
for richer output. Updating the addon is needed to capture event locations and
played durations; old events are not assigned the character's current location.
Disabling either field scrubs retained event metadata locally and on the service
at the next upload. Historical Discord messages already sent remain unchanged.

The new addon behavior still needs actual-client testing at home. CI uses mocked
Vanilla and Forever APIs; the work computer does not run the addon or test suite.

## Automatic abuse protection

Level caps are enforced by edition (currently 60 for Vanilla Classic and Forever)
for profiles, events and graph observations. Cap celebrations are calculated by the
server, never taken from a client-supplied flag. Reaching a level is deduplicated per
character, including when the event ID changes; real and explicitly synthetic test
observations are separate. Existing installations keep their credentials and ownership.

There are no speed checks, progression approval queues or manual onboarding approvals.
Existing high-level characters, skipped levels, offline uploads, old timestamps and
out-of-order level events remain supported within the existing export protocol.
An in-range fabricated claim cannot be distinguished from genuine gameplay without
an authoritative game-server source; these controls prevent abuse, not prove gameplay.

Discord announcements are durably queued, spaced at least 3 seconds apart per group
and 10 seconds apart per character. Queued work rotates between owners so one owner's
many characters cannot stay ahead of everyone else. Summary delivery gets a periodic
opportunity during continuous upload backlogs. Records and recap totals are retained
when Discord delivery waits; posting delays do not reject uploaded progression.

Resource budgets are deliberately generous and do not judge gameplay:

| Resource | Automatic limit |
| --- | --- |
| Upload requests | 600 per minute per owner/installation identity |
| Privacy requests | Separate 120 per minute per owner |
| Enrollment attempts | 30 per source IP per hour |
| New enrollments | 1,000 per group per day |
| New characters | 256 per owner and 2,000 per group per day |
| New events | 100,000 per owner and 1,000,000 per group per day |
| New serialized event/snapshot bytes | 200 MiB per owner and 2 GiB per group per day |
| Request body | 256,000 bytes; at most 500 events |

Resource windows use fixed UTC boundaries, independent of the Oslo gameplay calendar.
Budgets persist across service restarts. Retries of already stored events/snapshots
spend no additional growth budget. A growth-limited upload rolls back entirely and
returns HTTP 429 with Retry-After. The companion keeps SavedVariables unacknowledged
and automatically retries after that delay; another group continues independently.
Disabling sharing can still scrub data after a growth budget is exhausted. Privacy
controls have a separate request allowance. No retained history is automatically
pruned to enforce these budgets; ongoing disk usage still needs normal server capacity
monitoring and backups.

Production enables `--trust-proxy` only behind its loopback-only Caddy upstreams.
Caddy overwrites `X-WoW-Client-IP` with the actual TCP peer address; client-supplied
forwarding headers cannot choose their own enrollment-rate identity. Direct service
setups leave proxy trust disabled. User-provided URLs, invites, markdown and mentions
are neutralized in displayed text; item hyperlinks are constructed from numeric IDs
by the service.

In-game group popups continue to join automatically with no approval requirement.
Rapid distinct levels are queued/coalesced, not rejected for being too fast. Popup
queues are bounded to 128 pending senders/groups and recent level claims persist for
up to 512 sender identities, with at most the edition's 60 levels per sender. The
oldest sender is evicted when that bound is reached. Popups are transient notifications,
not a durable progress archive; saturation/expiry can still omit a notification, while
own-character upload history remains retained. A modified receiving addon can bypass
its own local popup protections.
