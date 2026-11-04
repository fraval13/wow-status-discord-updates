# Dedicated deployment on 193.243.189.202

This project uses independent paths and users:

- Code: `/opt/wow-character-status/releases/` and the `current` release symlink.
- Configuration: `/etc/wow-character-status/`, root-readable only.
- One service per group: `wow-character-status@<instance>.service`, user
  `wow-character-<instance>`, data `/var/lib/wow-character-<instance>` and its own
  loopback port (currently 18081 and 18082). Instance labels, group names and ports
  are private: they live only in `/etc/wow-character-status/groups.json` (see
  [private group configuration](#private-group-configuration)).
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
then create separate Vanilla, Forever, TBC Anniversary and Retail addon ZIP artifacts. Only passing checks
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

## Private group configuration

A group name is a shared secret (see [the group name is the password](../docs/GROUPS.md#the-group-name-is-the-password)),
and its route key is derived from it, so neither belongs in Git, in the workflow or
in GitHub Actions logs. The server keeps them in `/etc/wow-character-status/groups.json`
(owned by root, mode 0600):

```json
{
  "group-a": {"name": "<exact group name>", "port": 18081},
  "group-b": {"name": "<exact group name>", "port": 18082}
}
```

- The key (`group-a`) is the instance label: the systemd instance, the account
  `wow-character-<instance>`, the data directory, the `<instance>.env` file and the
  key in the Discord secret below. Use lowercase letters, digits and `-`, start with
  a letter, at most 18 characters. Do not use the group name as the label.
- `name` is the exact text members enter in WoW. The server accepts letters, digits,
  spaces, `.`, `_` and `-`, at most 80 characters, so it can go into a systemd
  environment file unchanged.
- `port` is the instance's loopback port. Names (ignoring case) and ports are unique.

The receiver restarts and health-checks exactly the instances listed there and
writes each `<instance>.env` from it on every deployment. Its output in the
Actions log names no group or instance. When a receiver from this revision finds no
`groups.json`, it creates one from the `<instance>.env` files the previous receiver
wrote, so the existing services keep their names, ports and data. Install a new
receiver as root from a checkout of the revision:
`install -o root -g root -m 0755 deploy/install_release.py /usr/local/sbin/wow-character-status-deploy`.
The gateway's group routes are rendered from the same file (see
[network access](#network-access-and-home-testing)).

## Discord settings, when you have created the bot/chats

Add one repository secret, `WOW_STATUS_DISCORD_CONFIG`, holding JSON keyed by the
instance labels in `groups.json`:

```json
{
  "group-a": {"bot_token": "...", "guild_id": "...", "channel_id": "..."},
  "group-b": {"bot_token": "...", "guild_id": "...", "channel_id": "..."}
}
```

One JSON secret keeps the labels out of the workflow file. Without it, a deployment
sends no Discord settings and the server keeps the ones it already has (the deploy
log shows a "Discord settings unchanged" warning). Empty or missing fields also keep
the server's existing values, so a later deployment never deletes a credential by
accident. Settings for an instance that is not in `groups.json` are ignored, and the
log says how many were. The workflow no longer reads the older per-group
`*_DISCORD_*` secrets and variables; delete them once their values are in the new secret.

Use the same new bot token for both groups if that bot is invited to two different
Discord servers. Guild IDs must differ when sharing a token. Alternatively use a
separate bot per group. No OpenAI key is required.

Invite using the `bot` and `applications.commands` scopes. Give the bot View Channel,
Send Messages, and Embed Links in the chosen destination. Members need Use
Application Commands. No Administrator permission or Message Content intent is
required. Paste tokens into GitHub secrets, not repository files or ordinary chat.

Until all three settings exist for a group, it runs ingestion only and does not
connect to Discord. Configure settings, then push another change or use **Re-run
all jobs** on the **Checks and addon packages** run for the current tip of `main`
once it has finished, to activate the bot. "Re-run failed jobs" fails `deploy`. A
run whose commit is no longer the tip of `main` also skips `deploy` (see
`scripts/deploy_gate.py`), so re-running an older run deploys nothing. Roll back by
reverting on `main`.

## Keeping production level with main

`deploy_gate.py` lets only the tip of `main` deploy, so an older commit never
publishes over a newer one. That keeps deploys ordered but does not catch up by
itself: while merges land faster than a run takes, every run stands aside, and if
the last commit's checks fail, nothing is left to publish the site.

The **Deploy convergence** workflow closes that gap. After each pipeline finishes
(and hourly as a backstop) it compares the tip of `main` with the `addon_revision`
the live site serves, and dispatches one more run for the tip when that is what it
takes. A tip whose own run failed is reported as a warning and never re-dispatched,
so a broken commit cannot make it loop; push a fix and the next run converges.

Its decision logic is `scripts/deploy_convergence.py`, which is pure and unit
tested; the workflow gathers the facts and acts on the verdict.

## Network access and home testing

The public companion address is **https://wow.frankvalde.com**. Its DNS A record
points to this server. Caddy terminates HTTPS on port 443, manages certificate
renewal, and redirects HTTP on port 80 to HTTPS. The two application ports remain
bound to localhost only. No request access log is enabled.

The deployed gateway configuration is rendered from `Caddyfile.production.template`
and the private `groups.json`: one `handle_path /groups/<route key>/*` route per
group to its loopback port, where the route key is
`wow-status group-key "<group name>"`. The rendered file is never committed.

The root address now hosts the addon homepage and all standalone ZIP downloads.
Static releases live in `/srv/wow-status-homepage/releases/`, with an atomic
`current` symlink. They are independent from the Python application releases.
See [homepage deployment](../website/README.md) for building and publishing the
site without restarting either application. `deploy/publish_homepage.py` validates
Caddy and retains the prior configuration/release for rollback.

Unknown groups return 404. Friends configure only the shared base address; the
companion derives routing keys from the names selected in WoW. At home:

```sh
wow-status configure --url https://wow.frankvalde.com
```

Homepage packaging now belongs to the same checks/deployment workflow. The runner
builds `dist/homepage` for its exact commit and includes it under `.deploy/HOMEPAGE`
in the private tar. The receiver validates manifest revision, all four ZIP checksums,
TOC contents and displayed version, then moves the public files out before
deleting `.deploy` credentials. After service health checks pass, the public
symlink points to that release's sealed `public-homepage` directory. No Caddy
configuration update or reload is needed on ordinary pipeline releases.

The extended root-owned receiver is installed separately from application code;
application archives cannot replace privileged scripts. Its fixed authority now
also covers `/srv/wow-status-homepage/current`, while its key/sudo restrictions
are unchanged. Earlier manual static releases remain available for rollback.

Caddy was installed separately through Debian's package manager. App deployments
do not modify its configuration or restart it. To change the gateway, as root on
the server (`-B` keeps Python from writing into the sealed release):

```sh
cd /opt/wow-character-status/current
.venv/bin/python -B deploy/render_caddyfile.py | diff -u /etc/caddy/Caddyfile -   # dry run
.venv/bin/python -B deploy/render_caddyfile.py --output /etc/caddy/Caddyfile.next
caddy validate --config /etc/caddy/Caddyfile.next --adapter caddyfile
cp -p /etc/caddy/Caddyfile /etc/caddy/Caddyfile.before-$(date -u +%Y%m%dT%H%M%SZ)
mv /etc/caddy/Caddyfile.next /etc/caddy/Caddyfile && systemctl reload caddy
```

`deploy/publish_homepage.py` renders the same routes from the server's `groups.json`
(or a local `--groups-config`); `--dry-run` prints the Caddy diff and changes
nothing. Its output contains route keys, so keep it private.
Certificates live in Caddy's persistent state, outside app releases. The generic
`Caddyfile.groups.example` remains available for other deployments.

External checks confirmed valid HTTPS and healthy responses from both group
`/health` routes, HTTP-to-HTTPS redirects, and rejection of unknown group routes.
No enrollment or character data was created by these read-only checks.

Root administration examples:

```sh
systemctl status 'wow-character-status@*'
journalctl -u wow-character-status@INSTANCE -n 30 --no-pager
curl --fail http://127.0.0.1:18081/health
curl --fail http://127.0.0.1:18082/health
```

Each `/health` reply also carries the bot's state: `"discord"` is `disabled` (no
Discord settings), `starting`, `ready`, `reconnecting` (discord.py is restoring a
dropped gateway), `delivery_retrying` (connected, but posting crashed) or
`retrying` (the session failed). The last two add `"discord_error"`, the exception
name plus Discord's HTTP status and error code. A Discord failure no longer stops
the service: ingestion and `/health` keep running, and a new bot session starts
after 30 s, doubling to every 10 minutes. A crash in posting restarts only the
delivery loop on the same schedule, so slash commands stay available. The deploy's
**Report Discord bot state** step warns when a group's bot is not `ready`.

### Discord bot not connected

```sh
curl -s http://127.0.0.1:18082/health          # navsquad; 18081 is ronkalot
journalctl -u wow-character-status@navsquad -n 50 --no-pager | grep -i discord
```

- `LoginFailure`: the token no longer works. Discord resets a token that is
  published (for example in a public repository) or that starts more than 1,000
  sessions in a day, and emails the bot owner. Reset it under Developer Portal >
  Bot, put it in the group's `*_DISCORD_BOT_TOKEN` secret, then use **Re-run all
  jobs** on the run for the tip of `main`.
- `Forbidden 403 50001` (Missing Access) or `NotFound 404 10004` (Unknown Guild):
  the bot was removed from the server, or the guild variable is wrong. Re-invite
  it with the `bot` and `applications.commands` scopes.
- `ClientConnectorError` or `TimeoutError`: the server cannot reach Discord; it
  reconnects by itself within 10 minutes of Discord coming back.
- `delivery_retrying` with any name (for example `OperationalError` or `KeyError`)
  is a crash while posting; the journal has its traceback.

### A group service does not start

If `curl` to the local port is refused and `systemctl status` shows restarts, the
process exits before it listens, so the cause is in its own state:

```sh
journalctl -u wow-character-status@navsquad --since "1 hour ago" --no-pager | tail -60
df -h /var/lib /opt; df -i /var/lib /opt         # ENOSPC, "database or disk is full"
fuser -v /var/lib/wow-character-navsquad/service.sqlite3.lock   # "Another process is using this database"
find /var/lib/wow-character-navsquad ! -user wow-character-navsquad -ls   # files a root tool created
ls /opt/wow-character-status/releases | wc -l    # every deploy, failed ones too, leaves a release
```

Fix ownership with `chown -R wow-character-navsquad: /var/lib/wow-character-navsquad`
after stopping the service. Old releases other than `current` can be deleted.

Do not print environment files or config.json while inspecting logs. For backups,
stop only these project services and copy their complete state directories, or use
SQLite's consistent backup API. Stop the appropriate service before operator tools
access its database. Secrets and data do not belong in Git.

Game behavior remains unverified until the actual game clients are exercised
at home. Remote mocked tests and HTTP health checks establish narrower guarantees.

## Rotating a group name

Removing a name from the repository does not make it secret again: earlier names and
keys stay in Git history, issue text and old Actions logs. Choosing a new name is the
fix. In-game sharing needs no server change: it moves as soon as members replace the
name in `/wstatus groups`. For the companion service, as root:

1. Choose a new name: long and unguessable, for example five or more random words
   (see [GROUPS.md](../docs/GROUPS.md#the-group-name-is-the-password)). Share it with
   the members privately, never in Git, issues, pull requests or logs.
2. Pick a new instance label that is not the name, for example `group-c`, and a free
   loopback port (the old service keeps its port until step 8). A service database
   belongs to one group and refuses another name, so the renamed group starts with a
   fresh database under the new label; the old data stays where it is.
3. Create the account: `useradd --system --user-group --create-home --home-dir
   /var/lib/wow-character-group-c --shell /usr/sbin/nologin wow-character-group-c`.
4. In `/etc/wow-character-status/groups.json`, remove the old entry and add
   `"group-c": {"name": "<new name>", "port": <free port>}`. The receiver from this
   revision must be installed (see [private group configuration](#private-group-configuration)).
5. If the group posts to Discord, move its entry in `WOW_STATUS_DISCORD_CONFIG` to
   the new label.
6. Deploy: push to `main`, or use **Re-run all jobs** on the run for the tip of
   `main`. The receiver writes `group-c.env`, then starts and health-checks the new service.
7. Render, check and install the Caddyfile (see [network access](#network-access-and-home-testing)).
   The old route then returns 404.
8. Stop the old service with `systemctl disable --now wow-character-status@OLD`, then
   back up or delete `/var/lib/wow-character-OLD` and `/etc/wow-character-status/OLD.env`.
9. Members replace the old group with the new name in `/wstatus groups`.
