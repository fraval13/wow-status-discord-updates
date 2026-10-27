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

The two HTTP ports bind to localhost only. No public HTTP listener, DNS or reverse
proxy is installed automatically. A public HTTPS hostname/gateway is still required
before home companions can connect over the internet. The group gateway example in
`Caddyfile.groups.example` needs this server's ports **18081/18082**, not the generic
8081/8082 examples. Configure HTTPS once a hostname is supplied. For private home
checks an owner-controlled SSH tunnel can forward these local ports instead.

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
