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
preceding release and its configuration, and deletes the failed release. SQLite
databases and managed JSON archives stay in persistent per-group directories.
Release archives containing private configuration are never published as
artifacts; configuration is removed before installing the code.

Hardening from issue #27:

- **Pinned actions, no stored token.** Every action in the workflows is pinned to a
  full commit SHA (the trailing comment names its tag; update both together), and
  every checkout sets `persist-credentials: false`. The deploy job runs no action
  besides checkout: it uses the runner image's own `python3`, because only
  standard-library scripts run there and they handle the deploy key and bot tokens.
- **A `production` environment.** The deploy job names it. GitHub creates it on first
  use with no rules, so the job keeps reading the repository secrets until you
  change that (see [what to do after merging](#after-merging-issue-27)).
- **Hash-locked dependencies.** The receiver installs `requirements.txt` with
  `pip --require-hashes --only-binary :all:`, then builds the project with
  `--no-deps --no-build-isolation --no-index`, so every package it installs, the
  build backend included, is pinned by version and SHA-256 and no unpinned tool
  runs. After changing dependencies in `pyproject.toml`, run
  `python scripts/lock_requirements.py` (needs [uv](https://docs.astral.sh/uv/));
  `--upgrade` moves every pin to the newest allowed version. CI installs the lock
  the receiver's way and runs `pip check`, and its tests run on the locked versions.
- **Pruning.** After a successful activation the receiver keeps the newest five
  releases (the live one among them), plus the one it replaced (the rollback target)
  and whichever one the homepage serves when those are older. Leftover `.incoming-*`
  folders from an interrupted run go too. Folders not named `<revision>-<time>` are
  never touched. A failed release is deleted at once.
- **One lock for both publishers.** The receiver and `deploy/install_homepage.py`
  hold `/opt/wow-character-status/deployment.lock` while they work, so a manual
  homepage publish and a pipeline deploy never switch `current` at the same time.
  Each waits up to ten minutes for the other. The publisher reads where `current`
  points when it inspects the host, and the install refuses if a deploy moved it
  since, so a publish that waited never replaces the site that deploy switched to.
  Nothing stops publishing an older checkout over a newer site, so publish from an
  up-to-date `main`. A deploy that had to wait first writes a line to its SSH
  connection once it gets the lock, and stops without changes if that fails, so a
  deploy whose job was cancelled meanwhile can't activate over a newer one.
- **Rollback when the public check fails.** If **Verify live homepage and all addon
  downloads** fails after a deploy, the next step sends the receiver
  `wow-status-rollback <commit>` instead of an archive. The receiver acts only if
  that commit's release and homepage are still live and the release and homepage
  it replaced are still installed: it rewrites the env files for the earlier
  revision, switches back, restarts and health-checks the services, then switches
  the homepage back. It changes nothing when a manual publish replaced the homepage
  since, because that alone explains the failed check. If the earlier release is
  not healthy, or the homepage can't be switched, the failed release stays live.
  Instances that deploy started for the first time are stopped and disabled, as a
  failed deploy does. Redeploying the live revision keeps the earlier rollback
  target. A rollback is tried only when the site answered with something other
  than this release (the verifier exits with status 4), not when it could not be
  reached (status 3) or the verifier itself failed, which a rollback would not fix.
  A refusal's reason is printed in the log. The job stays red either way, and
  **Deploy convergence** never re-dispatches a failed tip, so production stays on
  the earlier release until the next push.
- **Public file modes.** `install_homepage.py` resets file and folder modes after
  extracting (`0644`, folders `0755`) and creates folders under `umask 022`, so a
  build made under `umask 077` is still readable by Caddy (issue #19). The pipeline
  receiver ignores archive modes and sets them itself, as it did before.

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
  a letter, at most 18 characters; `build` and `deploy` are taken by the pipeline's
  own accounts. Do not use the group name as the label: labels can appear in the
  deploy log's bot warnings.
- `name` is the exact text members enter in WoW. The server accepts letters, digits,
  spaces, `.`, `_` and `-`, at most 80 characters, starting with a letter or digit, so
  it can go into a systemd environment file and command line unchanged.
- `port` is the instance's loopback port. Names (ignoring case) and ports are unique.

The receiver restarts and health-checks exactly the instances listed there and
writes each `<instance>.env` from it on every deployment. Its output in the
Actions log names no group or instance (it discards systemctl's output; use
`journalctl` on the server). When a receiver from this revision finds no
`groups.json`, it creates one from all `<instance>.env` files in the directory, which
the previous receiver wrote, so the existing services keep their names, ports and
data. Delete a retired instance's env file when you remove it from `groups.json`. Install a new
receiver as root from a checkout of the revision:
`install -o root -g root -m 0755 deploy/install_release.py /usr/local/sbin/wow-character-status-deploy`.
The gateway's group routes are rendered from the same file (see
[network access](#network-access-and-home-testing)).

## Discord settings, when you have created the bot/chats

Add one repository secret, `WOW_STATUS_DISCORD_CONFIG`, holding JSON keyed by the
instance labels in `groups.json`:

```json
{
  "group-a": {"bot_token": "...", "guild_id": "...", "channel_id": "...", "route": "..."},
  "group-b": {"bot_token": "...", "guild_id": "...", "channel_id": "...", "route": "..."}
}
```

`route` is optional: the group's route key (`wow-status group-key "<group name>"`).
The deploy's bot check uses it to reach that group's public `/health`. It is not sent
to the server. The deploy log masks every token and route.

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
site without restarting either application. `deploy/publish_homepage.py` checks
that the build is a fresh build of the checked-out commit before uploading it,
validates Caddy and retains the prior configuration/release for rollback.

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
install -o root -g caddy -m 0640 /etc/caddy/Caddyfile.next /etc/caddy/Caddyfile
systemctl reload caddy
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
**Report Discord bot state** step warns when a group's bot is not `ready`. Route keys
are private, so it checks only the instances that have a `route` in
`WOW_STATUS_DISCORD_CONFIG` (see [Discord settings](#discord-settings-when-you-have-created-the-botchats)),
and its warnings name the instance label.

### Discord bot not connected

```sh
curl -s http://127.0.0.1:PORT/health          # PORT and INSTANCE from groups.json
journalctl -u wow-character-status@INSTANCE -n 50 --no-pager | grep -i discord
```

- `LoginFailure`: the token no longer works. Discord resets a token that is
  published (for example in a public repository) or that starts more than 1,000
  sessions in a day, and emails the bot owner. Reset it under Developer Portal >
  Bot, put it in the group's `bot_token` in the `WOW_STATUS_DISCORD_CONFIG` secret,
  then use **Re-run all jobs** on the run for the tip of `main`.
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
journalctl -u wow-character-status@INSTANCE --since "1 hour ago" --no-pager | tail -60
df -h /var/lib /opt; df -i /var/lib /opt         # ENOSPC, "database or disk is full"
fuser -v /var/lib/wow-character-INSTANCE/service.sqlite3.lock   # "Another process is using this database"
find /var/lib/wow-character-INSTANCE ! -user wow-character-INSTANCE -ls   # files a root tool created
ls /opt/wow-character-status/releases | wc -l    # releases the receiver has kept (see Pipeline)
```

Fix ownership with `chown -R wow-character-INSTANCE: /var/lib/wow-character-INSTANCE`
after stopping the service. The receiver prunes old releases itself; a receiver
installed before issue #27 kept every release, failed ones too, and any of those
other than `current` can be deleted by hand.

Do not print environment files or config.json while inspecting logs. For backups,
stop only these project services and copy their complete state directories, or use
SQLite's consistent backup API. Stop the appropriate service before operator tools
access its database. Secrets and data do not belong in Git.

Game behavior remains unverified until the actual game clients are exercised
at home. Remote mocked tests and HTTP health checks establish narrower guarantees.

## After merging issue #27

The workflow side works at once. The server side needs the new receiver, which only
root can install (application deploys never replace privileged scripts):

```sh
cd /opt/wow-character-status/current   # once the first deploy of this revision is live
install -o root -g root -m 0755 deploy/install_release.py /usr/local/sbin/wow-character-status-deploy
```

Until then the old receiver keeps deploying as before, with these limits:

- It installs dependencies from the version ranges, not from `requirements.txt`.
- It never prunes releases or deletes failed ones.
- It does not wait for the lock: a deploy that starts while a manual homepage
  publish holds it fails at once (the publish itself does wait for a deploy).
- It cannot roll back. After a failed public check the rollback step fails with a
  "Not rolled back" error that names this section; the new release stays live.

The new receiver's first deploy builds the venv from the lock with wheels only. If a
package had no wheel for the server's Python, that deploy would fail before
activation and leave the running release untouched; the Actions log shows pip's error.

Optional: in **Settings > Environments > production**, set **Deployment branches and
tags** to `main` only, then move `WOW_STATUS_SSH_KEY`, `WOW_STATUS_KNOWN_HOSTS` and
`WOW_STATUS_DISCORD_CONFIG` (and the `WOW_STATUS_SSH_HOST` variable) from the
repository into the environment. Then only jobs that name the environment, on `main`,
can read them. Do not add required reviewers unless every deploy should wait for an
approval.

## Rotating a group name

The two previously exposed production names were rotated on 5 November 2026.
The old public routes are revoked and their units disabled; original databases
and a consistent pre-cutover backup are retained under root-only access. The
current receiver and private `groups.json` are installed. Active gateway routing
is root:caddy 0640, and group configuration is root-only 0600. Replacement names
were handed to the owner in a private local file, never GitHub or screenshots.
New addon versions retire the known compromised memberships automatically; group
members obtain the new names privately and join when next playing.


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
   the new label and set its `route` to the new route key.
6. Deploy: push to `main`, or use **Re-run all jobs** on the run for the tip of
   `main`. The receiver writes `group-c.env`, then starts and health-checks the new service.
7. Render, check and install the Caddyfile (see [network access](#network-access-and-home-testing)).
   The old route then returns 404. Keep the active Caddyfile owned by root:caddy
   with mode 0640: its paths contain private routing credentials. Rendered candidates
   are mode 0600; manual homepage publishing preserves the live file permissions.
8. Stop the old service with `systemctl disable --now wow-character-status@OLD`, then
   back up or delete `/var/lib/wow-character-OLD` and `/etc/wow-character-status/OLD.env`.
9. Members replace the old group with the new name in `/wstatus groups`.
