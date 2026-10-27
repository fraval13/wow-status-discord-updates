# Dedicated deployment on 193.243.189.202

This project uses independent paths and users:

- Code: `/opt/wow-character-status/releases/` and the `current` release symlink.
- Configuration: `/etc/wow-character-status/`, root-readable only.
- `ronkalot`: `wow-character-status@ronkalot.service`, user `wow-character-ronkalot`,
  data `/var/lib/wow-character-ronkalot`, loopback port **18081**.
- `navsquad`: `wow-character-status@navsquad.service`, user `wow-character-navsquad`,
  data `/var/lib/wow-character-navsquad`, loopback port **18082**.
- Build account: `wow-character-build`; builds/installations run without root.
- Deployment SSH account: `wow-character-deploy`, with a dedicated forced-command
  key and a sudo rule for only this project's root-owned release receiver.

The existing `wow-forever-news` and `wow-forever-qa` services and their files are
outside this deployment's paths and restart list. The workflow does not use a root
SSH key. The one-time bootstrap installs only this project's users, directories,
receiver, sudo rule and systemd template. Later deployments do not rewrite units
or privileged scripts; changing those requires an explicit root maintenance step.

## Pipeline

Pushes to `main` run Python/protocol/Lua-mock checks remotely on Linux and Windows,
then create separate Vanilla and Forever addon ZIP artifacts. Only passing checks
allow the deployment job. PRs run checks without deployment secrets.

The deploy job transfers tracked source plus private configuration through pinned
SSH. The receiver rejects unsafe archive paths/links, builds a fresh venv as the
build user, seals the release read-only, activates it, restarts only the two project
services and checks both local health endpoints. Failed activation restores the
preceding release. SQLite databases and managed JSON archives stay in persistent
per-group directories. Release archives containing private configuration are never
published as artifacts; configuration is removed before installing the code.

GitHub repository settings already have the dedicated `WOW_STATUS_SSH_KEY` and
`WOW_STATUS_KNOWN_HOSTS` secrets and `WOW_STATUS_SSH_HOST` variable. These contain no
Discord or OpenAI credentials. The private SSH key only permits this project's
release operation, with forwarding and interactive shell disabled.

## Discord settings, when you have created the bot/chats

For each group add the following repository settings:

| Group | Private secret | Repository variables |
| --- | --- | --- |
| ronkalot | `RONKALOT_DISCORD_BOT_TOKEN` | `RONKALOT_DISCORD_GUILD_ID`, `RONKALOT_DISCORD_CHANNEL_ID` |
| navsquad | `NAVSQUAD_DISCORD_BOT_TOKEN` | `NAVSQUAD_DISCORD_GUILD_ID`, `NAVSQUAD_DISCORD_CHANNEL_ID` |

Use the same new bot token in both secrets if that bot is invited to two different
Discord servers. Guild IDs must differ when sharing a token. Alternatively use a
separate bot per group. No OpenAI key is required.

Invite using the `bot` and `applications.commands` scopes. Give the bot View Channel,
Send Messages, and Embed Links in the chosen destination. Members need Use
Application Commands. No Administrator permission or Message Content intent is
required. Paste tokens into GitHub secrets, not repository files or ordinary chat.

Until all three settings exist for a group, it runs ingestion only and does not
connect to Discord. Configure settings and re-run **Checks and addon packages**
on `main` (or push another change) to activate the bot. Nonempty GitHub settings
update the server's private config; omitted settings preserve existing private
values, avoiding accidental credential deletion on later deployments.

## Network access and home testing

The public companion address is **https://wow.frankvalde.com**. Its DNS A record
points to this server. Caddy terminates HTTPS on port 443, manages certificate
renewal, and redirects HTTP on port 80 to HTTPS. The two application ports remain
bound to localhost only. No request access log is enabled.

The deployed gateway configuration is tracked in `Caddyfile.production`:

| Group | URL prefix | Private upstream |
| --- | --- | --- |
| ronkalot | `/groups/19e32befc180a1cfdea5c3/` | `127.0.0.1:18081` |
| navsquad | `/groups/466f79683c7465bc3a5ba0/` | `127.0.0.1:18082` |

Unknown groups return 404. Friends configure only the shared base address; the
companion derives routing keys from the names selected in WoW. At home:

```sh
wow-status configure --url https://wow.frankvalde.com
```

Caddy was installed separately through Debian's package manager. App deployments
do not modify its configuration or restart it. To change the gateway, copy the
tracked production file to `/etc/caddy/Caddyfile`, validate it with
`caddy validate --config /etc/caddy/Caddyfile`, then `systemctl reload caddy`.
Certificates live in Caddy's persistent state, outside app releases. The generic
`Caddyfile.groups.example` remains available for other deployments.

External checks confirmed valid HTTPS and healthy responses from both group
`/health` routes, HTTP-to-HTTPS redirects, and rejection of unknown group routes.
No enrollment or character data was created by these read-only checks.

Root administration examples:

```sh
systemctl status wow-character-status@ronkalot wow-character-status@navsquad
journalctl -u wow-character-status@ronkalot -n 30 --no-pager
curl --fail http://127.0.0.1:18081/health
curl --fail http://127.0.0.1:18082/health
```

Do not print environment files or config.json while inspecting logs. For backups,
stop only these project services and copy their complete state directories, or use
SQLite's consistent backup API. Stop the appropriate service before operator tools
access its database. Secrets and data do not belong in Git.

Game behavior remains unverified until the two actual addon clients are exercised
at home. Remote mocked tests and HTTP health checks establish narrower guarantees.
