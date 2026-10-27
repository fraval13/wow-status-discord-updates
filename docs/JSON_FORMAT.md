# Structured character JSON

Machine-readable contract: [character.schema.json](character.schema.json).

The service automatically writes one private UTF-8 JSON file per character under
`state/service-characters/` by default (or `DATABASE_STEM-characters/` alongside
a custom service database).
Filenames use the stable internal character ID to avoid collisions, renames and
unsafe filesystem characters. Name, realm, client and GUID are inside the file.
SQLite is the transactional source of truth; JSON is its automatically synchronized,
readable archive. Startup regenerates files after an interrupted write. Back up
both with the service stopped or use a consistent database backup and regenerate.

Files have `schema_version: 1` and `timezone: "Europe/Oslo"`. Every date/time in the
JSON is an object with an offset-aware Norwegian ISO 8601 time, a Unix timestamp
for joining/sorting, and the named timezone. Oslo automatically uses +01:00 in
winter and +02:00 in summer. Norwegian midnight boundaries account for daylight
saving days lasting 23 or 25 hours. Unix timestamps are absolute instants; use
`iso` for local display and retain `timezone` when processing the data later.

Illustrative excerpt (not a real account export):

```json
{
  "schema_version": 1,
  "timezone": "Europe/Oslo",
  "character": {
    "id": "stable-character-id",
    "guid": "Player-123-0001",
    "name": "Thora",
    "realm": "Test Realm",
    "client": "classic-era",
    "discord_owner_id": "12345"
  },
  "progression": {
    "level_history": [
      {
        "event_id": "stable-level-event-id",
        "recorded_at": {
          "iso": "2026-10-27T20:15:00+01:00",
          "unix": 1793128500,
          "timezone": "Europe/Oslo"
        },
        "first_uploaded_at": {
          "iso": "2026-10-27T20:20:00+01:00",
          "unix": 1793128800,
          "timezone": "Europe/Oslo"
        },
        "data": {"level": 20, "maximum": false}
      }
    ]
  }
}
```

## Related records stay together

| Group | Contents |
| --- | --- |
| `character` | Stable identity, linked Discord owner, chosen friend display name and main/alt role |
| `sharing` | Current field, collection, announcement and filter choices |
| `profile.current` | Latest selected snapshot fields |
| `profile.snapshot_history` | Distinct selected exports, sharing choices at export, export/upload times |
| `enrollment.introductions` | Confirmed introduction event and timestamps |
| `progression.level_timeline` | Level/time line points, segments, baselines and complete/partial elapsed durations |
| `progression.level_history` | Every collected level-up, actual level and event/upload timestamps |
| `items.loot` | Collected self-loot item links and rarity |
| `items.equipment_changes` | Collected changes to equipped items |
| `activity` | Selected deaths, zones, addon lifecycle updates and LFG text |
| `weekly_recaps` | Monday–Sunday structured reports and delivery state |
| `daily_recaps` | Day, explicit Oslo window, preparation time, delivery status and structured summary |

A baseline snapshot is an observation, not proof of when a level was earned. Only
level-up events go into `level_history`. Events recorded before installing or
enabling collection cannot be reconstructed. Event IDs deduplicate retries and
persist across companion restarts. Introduction IDs are canonical on the server.
Gear and item events keep original links plus extracted `item_id`, `enchant_id`
and display names when available, so later tools can join loot to equipment. Client
build/interface metadata is preserved when provided by the addon.
All data is player-reported; the server records first upload time separately from
the player's game timestamp.

## Collection and posting are separate

The addon has separate columns for **Store events / daily recap** and **Immediate
announcements**. A stored level-up is retained even if it is not a milestone or
immediate level announcements are off. All collected self-loot with available
metadata is retained; the minimum rarity filters immediate messages. Checkboxes
for collection determine what is gathered and retained. Private profile fields
also constrain related events (for example, hidden level means no level history).

Only collect data the player consents to share. "Keep everything" means everything
collected under those settings, not hidden or disabled data. Disabling a field or
collection category removes its old stored content and cancels related queued
messages; empty internal deduplication markers prevent old events reappearing.
Pausing scrubs snapshot/event contents and revokes uploaders through Discord.
Deleting removes service records and the managed character file. Separately copied
exports, backups and existing Discord messages need their own deletion handling.
There is no automatic time expiry of consented history.

## Export for later tools

Stop the service before using the operator export command against its database:

```sh
wow-status export --db state/service.sqlite3 --directory private-export
```

The result contains one JSON file per character and a manifest with timezone and
file references. Export directories are private copies outside automatic deletion;
use a fresh directory each time so it cannot retain old files from earlier exports.
The archive includes personal data; do not commit it or publish it as a public site.

## Daily recaps

At **00:05 Europe/Oslo**, the bot prepares the previous local day's recap. Currently shared characters known by that day's end are combined under friend
headings in one group report, with continuation messages only when needed. This
includes characters with no recorded activity. It contains last-known profile, event counts,
level-up times and a bounded set of item/LFG highlights. Full records remain in JSON;
absence of uploaded events is not a claim that the player was offline or inactive.

The structured summary contains the exact `[midnight, next midnight)` window,
snapshot count, per-type event counts and full selected event data. Late uploads
from earlier dates are called out on their upload day. Uploads in the five-minute
midnight grace period are assigned to the preceding recap, avoiding double counting. If the bot was down,
the scheduler catches up in bounded batches after restart. Per-day/per-character
statuses prevent routine repeat recaps. Interrupted/ambiguous sends require the
same manual review as normal announcements. Pending recap content is rebuilt from
the latest privacy-filtered records before sending. Already posted recaps remain.

No OpenAI key is needed. The deterministic recap is fully supported by stored data;
an optional AI-written narrative could be added later with separate data-sharing
consent. This version sends no data to OpenAI.

Friend aliases, main/alt labels, source/evidence metadata and snapshot comparisons
are documented in [FRIENDS_AND_RECAPS.md](FRIENDS_AND_RECAPS.md). Weekly group reports
run Monday at 00:05 Oslo time. Synthetic test events remain archived but are excluded
from daily/weekly real-progress totals.

The addon retains full consented local history. The companion uploads it in batches
of 100 events; level observation metadata is separately validated and archived.
[In-game history](IN_GAME_HISTORY.md) describes graph axes and partial duration semantics.
