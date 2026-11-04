# Daily group character status — requested 4 November 2026

This is the requested replacement for frequent export summaries in the future
companion-only group relay. The [example](daily-status-example.md) uses fictional
characters. It is not evidence that automatic delivery is enabled.

## Contents

One daily report includes every known, consented character in that group, including
characters with no new activity yesterday. Show cumulative level and recorded
deaths as observed before today's 00:00 in Europe/Oslo. The report is a state of
the group at the cutoff, not a list of events or daily gains.

Display two separate lists: level descending, then deaths descending. Each row
includes both values. Use character name, realm and edition as deterministic
tie-breakers and disambiguate names across realms/editions. Do not combine a
player's alts. Mark older observations; an unavailable/private count is unknown,
not zero, and sorts after known values. Deaths are addon-recorded totals since
tracking began, not a claim of complete lifetime deaths.

## Trigger and cutoff

- On the first accepted upload after local midnight containing relevant
  observations/events from before the cutoff, prepare the report for yesterday.
  No upload means no new report. This replaces the legacy fixed 00:05 timer.
- For a report generated on 4 November, the cutoff is 4 November at 00:00 Oslo.
  Include known observations strictly before that instant, including earlier days.
  An event exactly at midnight belongs to the next report.
- Use observation/event times, not upload arrival time, to select data. An upload
  after midnight can contain both yesterday's and today's activity; today's
  progress must not leak into yesterday's standings. A current snapshot alone
  cannot establish the midnight state; retain dated observations and checkpoints.
- Freeze the group's report contents when preparing it. Persist a unique
  group/day key and delivery state before posting. Multiple companions, retries
  and service restarts must not create duplicate daily posts.
- Later uploads do not create a second post for that group/day. Their eligible
  observations contribute to the next cumulative report. Thus the first post
  includes data received by its generation time, not unknowable future uploads.
- Recheck consent before sending. Cancel/rebuild unsent content after withdrawal.
  Keep ambiguous sends held for review rather than blindly retrying them.
- Prefer one Discord message. For groups exceeding Discord's message/embed
  limits, preserve all characters in one daily report with labelled continuations;
  never silently truncate the roster.

## Integration status

The retained desktop companion, ingestion service and legacy daily scheduler
exist. The companion-only shared-journal relay, dated peer state/checkpoints and
this upload-triggered group-state report still require implementation. Do not
enable the old addon Discord options to implement this flow. Retain separate
navsquad/ronkalot routes and databases. No AI call is needed to sort or count.

`python scripts/send_status_preview.py --daily-status` renders the prepared
example locally. Adding `--send --group navsquad` explicitly posts that labelled
example using the existing private server configuration. It does not enroll
fictional characters, alter tracker data, or enable scheduled reports.
