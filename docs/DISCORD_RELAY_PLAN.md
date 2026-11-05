# Private Discord relay requirements — 30 October 2026

The addon remains an in-game sharing tool. Keep `WoWStatusFeatures.discord=false`:
no Discord options page, checkbox, onboarding, commands or prompts in the addon.
The public homepage does not need a Discord setup flow either.

Only the people who choose to run the desktop companion need to configure the
optional relay. Its opt-in belongs in the companion, not the addon. Do not restore
the old per-character Discord settings to enable the new relay.

## Destinations

Retain the two existing private server destinations. Their group names and route
keys are shared secrets, kept only in the server's private configuration (see
[the server setup](../deploy/SERVER.md#private-group-configuration)), not in Git.

The relay should select only these two groups, and only when the uploader belongs
to the corresponding in-game group. Keep their uploads, summaries and Discord
destinations separate. Do not provision additional Discord routes. Other group
IDs remain valid for normal in-game sharing and are not Discord destinations.

The live gateway already has only these two upstream routes; unknown group routes
return 404. Preserve that routing while implementing the relay.

## Summary behavior

The owner's 4 November request replaces per-upload event summaries with a
once-daily cumulative character-status report. See [the current report rules](DAILY_STATUS_REPORT.md)
and [fictional example](daily-status-example.md).

- Opted-in companions upload the shared journal and dated character-state
  observations on reload/logout saves, including friends' permitted observations.
- Preserve original event IDs and observation times. Deduplicate per group and
  client edition, independently of which companion uploaded the observation.
- The first upload after Oslo midnight containing yesterday's data triggers one
  group/day report. Include all known consented characters with their cumulative
  level and recorded deaths before today's 00:00. Today's activity is excluded.
- Show separate level-descending and death-descending lists. Include both values
  for each character, mark stale/unknown observations and never invent zeros.
- Persist the frozen report and delivery state. Retries, other companions and
  later uploads must not create a second report for that day. No upload means
  no report; later data contributes to the next cumulative report.
- Compute values and ordering in code; AI wording is not required. Keep Discord
  message IDs and do not blindly resend ambiguous deliveries.
- Recovery depends on an online member retaining the relevant events. The relay
  cannot reconstruct unavailable history or bypass game communication rules.

## Implementation status

The daily cumulative group-state report is implemented and delivered from the
service (see [the report rules](DAILY_STATUS_REPORT.md)). Since #49 the companion
also uploads the shared journal: for every group an opted-in character already has
upload credentials for, the account log's level and death entries shared with that
group (friends' included) go to `POST /groups/<route>/v1/journal`, newest 500,
with original event IDs and times. The service keeps them in `journal_entries`,
deduplicated per group database and client edition whichever companion uploads
first. The report uses them as dated checkpoints (never lowering values) and lists
characters seen only this way with source `shared_journal`. A character that
uploads directly but is paused is withheld, including peers' entries about it.
Deleting an installation removes the entries it uploaded. Death totals come only
from entries that carry `Total deaths: N`. The existing addon switch continues to
disable the old exports; the relay remains a separate path with that switch off.
