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
send. Exactly-once delivery across a network failure is not guaranteed.

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
