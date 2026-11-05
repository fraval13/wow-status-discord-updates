For direct group-ID joining and two isolated Discord destinations, follow
[GROUPS.md](../docs/GROUPS.md), `wow-status@.service`, and `Caddyfile.groups.example`.
No Discord `/link` code is required in that flow. The single-instance linked
deployment instructions below remain available as a legacy option.

# Host setup (later, on your own server)

Nothing is deployed or started by this repository. One service represents one
Discord community. Use a separate database, port and process for another community.

The service binds to `127.0.0.1:8080` by default. Put it behind HTTPS before friends
connect. Do not expose the Python HTTP port directly to the internet.

## Manual setup on a Linux server

Install Python 3.11+ and Caddy using your host's supported installation method.
Create an unprivileged `wow-status` system user. Clone the repository into
`/opt/wow-status`, create its `.venv`, and install with:

```sh
/opt/wow-status/.venv/bin/python -m pip install /opt/wow-status
```

Create `/etc/wow-status.env` with the values from `.env.example`. Keep this file
readable only by root; systemd reads it before changing user. This program does
not automatically load `.env` files. Configure the actual guild and channel IDs.

Install `wow-status.service` into `/etc/systemd/system/`. The unit creates a
private persistent state directory under `/var/lib/wow-status`. Configure Caddy
using `Caddyfile.example` with your domain. Only the reverse proxy needs public
ports. Do not enable request-body or authorization-header logging.

After your home acceptance tests pass and you are ready for Discord delivery:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now wow-status
sudo journalctl -u wow-status -f
```

## Bot application

Create a Discord application and bot in the Developer Portal. Install it in your
server with `bot` and `applications.commands` scopes. Give it View Channel,
Send Messages and Embed Links in the target channel. Administrator and Message
Content intent are unnecessary. Server members need Use Application Commands.
Commands sync only into `DISCORD_GUILD_ID` when the bot starts. The configured
announcement channel must belong to that same server.

Give friends the public HTTPS service URL. Each friend invokes `/link` privately
and runs `wow-status link --url https://YOUR_HOST` on their gaming computer. Codes
are one-use and expire after ten minutes. No shared uploader secret is needed.
Each installation receives its own credential. Profiles and commands are scoped
to this single Discord community; commands respond ephemerally.

## Operations

Back up the SQLite database using SQLite's backup API or stop the service and
back up its entire state directory. Do not copy only the main database file while
WAL writes are active. Backups contain personal data and require restricted access.
Apply deletion requests to retained backups according to your own backup expiry
policy; restoring an old backup can restore deleted data and revoked credentials.

Stop the service before running operator tools against its database. A file lock
prevents concurrent service/operator processes from changing delivery state.

```sh
sudo systemctl stop wow-status
sudo -u wow-status /opt/wow-status/.venv/bin/wow-status outbox --db /var/lib/wow-status/service.sqlite3
# After checking Discord to see whether a message actually arrived:
sudo -u wow-status /opt/wow-status/.venv/bin/wow-status resolve --db /var/lib/wow-status/service.sqlite3 12 sent
# Use 'retry' only when you have confirmed no message arrived; 'discard' cancels it.
sudo systemctl start wow-status
```

Delivery IDs are visible in `outbox`. Interrupted sends, network timeouts and
Discord server errors become `uncertain` and require review. Known permissions
and request errors become `failed`. Discord's library handles rate limits; a
surfaced 429 is requeued. This prevents blind duplicate retries after an ambiguous
send. Exactly-once delivery across a network failure is not guaranteed. A network
or server error before the message was sent only requeues it for a minute. Any other
error is logged with its traceback, shown on `/health` as `delivery_retrying`, and
delivery restarts after a backoff. A post that failed before sending is set aside for
10 minutes, so the restart goes on with the next one; once its message may have been
sent it becomes `uncertain`. A recap that fails to render pauses that kind of recap
for 10 minutes.

A summary export whose remaining parts stop arriving for a week becomes `expired`, so
it no longer waits in the queue. Its events stay in the character's history, and the
character's next summary upload, including the missing parts, queues it again.
`resolve <id> retry` posts an expired announcement on its own.

`/privacy action:pause` removes queued posts, hides profiles and revokes all of that
member's upload credentials. The addon should also be paused. A send already in
flight may still finish. `/privacy action:delete confirm:True` removes service data
and credentials. Historical Discord announcements remain; ask a channel moderator
to remove those separately. New enrollment requires new linking and consent.

Consented event and snapshot history is retained until data deletion. The service
automatically synchronizes per-character JSON under `service-characters/` alongside
the database. Include these private files in backup/deletion handling. Every JSON
timestamp includes `Europe/Oslo` and an explicit offset. Daily recaps run at 00:05
Oslo time for the prior day; see [JSON and recap details](../docs/JSON_FORMAT.md). This service trusts
linked players' telemetry and does not verify account ownership with Battle.net.

Review ambiguous recap sends using `outbox`, then resolve by day and character:

```sh
# Service must be stopped. Use the actual day and character ID from outbox.
wow-status resolve-recap --db /var/lib/wow-status/service.sqlite3 --day YYYY-MM-DD --character-id CHARACTER_ID sent
```

Use `retry` only after verifying that the corresponding recap did not arrive.

Characters belong to the owner (a group enrollment or a Discord account) that
first uploaded them. Another owner takes one over only with the character's addon
claim secret and a newer export, so a player who lost their companion credentials
but kept SavedVariables recovers on their own. The old owner can't take it back
after that. Run these commands with the service stopped:

```sh
# Owner IDs, names and character counts, including owners whose uploads all got 409.
wow-status owners --db /var/lib/wow-status/service.sqlite3
# Someone else claimed it first: delete the character and its data. Its current
# owner can't claim it again; the real owner's next upload does, and their events
# are posted as new because the service never had them.
wow-status release-character --db /var/lib/wow-status/service.sqlite3 --name Thora --realm "Realm Name"
# The player's own character, stored before claim secrets existed, after they lost
# their credentials: move it with its history, so nothing is posted twice.
wow-status release-character --db /var/lib/wow-status/service.sqlite3 --character-id CHARACTER_ID --to-owner OWNER_ID
```

Several matches are listed with their IDs and owners; repeat with `--client` or
`--character-id`. After `--to-owner`, that owner's next upload binds its secret,
and the previous owner can't take it back. `--to-owner` refuses an owner who has
paused sharing. A release only bars the exact owner ID, so a squatter who enrolls
again can claim the character again before the real owner does; then move it with
`--to-owner` instead. To undo a release of a now-deleted character, run
`release-character --character-id CHARACTER_ID --to-owner OWNER_ID` for the barred owner.

## Friend-group behavior

`/link` remembers the member's server display name; `/nickname` sets an optional
preferred name. Discord IDs remain the ownership key. `/main` selects one owned
main, `/roster` shows everyone grouped by friend, and `/settings` is restricted to
Manage Server members. Default immediate posts are celebrations; routine collected
activity goes to combined daily reports. Weekly reports run Monday at 00:05 Oslo.
See [friends and recaps](../docs/FRIENDS_AND_RECAPS.md).

Grouped recap pages share a Discord message ID across their character delivery
rows. When reviewing an ambiguous page, inspect and resolve all affected character
rows consistently; retry only after verifying that the page did not arrive.
Weekly entries appear under `weekly` in `outbox` and use `resolve-weekly --week
YYYY-MM-DD --character-id CHARACTER_ID sent` (or `retry`/`discard`) with the same
stopped-service procedure. Privacy removal also scrubs pending weekly content.
