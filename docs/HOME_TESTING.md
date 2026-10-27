# Home testing checklist

This guide is for your personal gaming computer and later your own hosting server.
No tests or project processes were run on the work computer. No real keys are in
this repository. Do the keyless checks first; Discord can be connected afterwards.

**New default flow:** [GROUPS.md](GROUPS.md) explains entering free-text group IDs
in WoW, automatic enrollment, two Discord destinations, and companion privacy controls.
The explicit `/link`/create-link examples below remain a legacy/keyless protocol
exercise, rather than a requirement for ID-only group membership.

## 1. Install the project at home

Clone the new repository into its own directory:

```sh
git clone https://github.com/fraval13/wow-status-discord-updates.git
cd wow-status-discord-updates
python -m venv .venv
```

Activate the environment:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```sh
# Linux/macOS
. .venv/bin/activate
```

Then install and run the authored checks:

```sh
python -m pip install -e ".[dev]"
python -m pytest
```

Record failures before continuing. These tests have not been run yet. There is
also a **Manual validation** workflow under the repository's Actions tab if you
want remote Windows/Linux checks; it only runs when manually requested.

## 2. Preview the synthetic fixture without keys

```sh
wow-status companion --saved-variables tests/fixtures/WoWStatus.lua --dry-run
```

Expect a Thora profile and introduction/level events. `zone="PRIVATE"` exists in
the fixture to prove that an unchecked field is stripped; it must not be printed.
Dry-run prints selected data locally, never uploads and never contacts Discord.
Do not paste real dry-run output publicly if it contains your character details.

## 3. Exercise the local service with no Discord connection

Before starting the service, create a local test enrollment code:

```sh
wow-status create-link --db state/home-test.sqlite3 --owner home-test
```

Keep the printed code private. It expires in ten minutes. Start the service in
that terminal:

```sh
wow-status serve --db state/home-test.sqlite3
```

In a second terminal, activate the same environment and redeem the code at the
hidden prompt. The HTTP exception is allowed only for loopback addresses:

```sh
wow-status link --url http://127.0.0.1:8080 --credentials state/home-credentials.json
wow-status companion --saved-variables tests/fixtures/WoWStatus.lua --credentials state/home-credentials.json --state state/home-upload.json --once
```

Run the upload command again: it should not create more events. Stop the service
with Ctrl+C, then inspect and simulate delivery:

```sh
wow-status outbox --db state/home-test.sqlite3
wow-status simulate --db state/home-test.sqlite3
wow-status simulate --db state/home-test.sqlite3
```

The first simulation should print one introduction and one level-10 announcement.
The second should print nothing. Simulation marks items `simulated`; it never
contacts Discord. Use a separate production database later so test identities and
simulated delivery state cannot affect real characters.

## 4. Install the addon into Classic Era

Confirm you are launching the intended **Classic Era/vanilla** client, not Retail
or another Classic expansion. This adapter explicitly checks the Classic Era
project ID. Forever will need a separate validated adapter later.

In game, obtain the interface number:

```text
/dump GetBuildInfo()
```

Use the **fourth** return value (the numeric interface version). Exit WoW before
copying addon files. Locate your actual Classic Era `Interface/AddOns` folder;
a typical installation uses `_classic_era_`, but use the real path on your computer.

```powershell
# Replace the path and interface number with your actual values.
python scripts/install_addon.py --addons-dir "C:\Games\World of Warcraft\_classic_era_\Interface\AddOns" --interface YOUR_INTERFACE_NUMBER
```

```sh
# Same installer works with your actual Linux/Wine/macOS path.
python scripts/install_addon.py --addons-dir "/your/game/_classic_era_/Interface/AddOns" --interface YOUR_INTERFACE_NUMBER
```

The installer copies only this addon's files. It refuses to overwrite an
existing WoWStatus addon directory. The interface argument changes addon metadata;
it does not make an incompatible API compatible. For updates, back up the existing
addon directory, remove it, and install again. Preserve SavedVariables separately.

Log in. The setup panel should appear with sharing off. Open it later using
`/wstatus`. Confirm the following:

- No introduction is queued before opting in and confirming the preview.
- Name, realm, client and GUID are required metadata for enrollment.
- Choose profile fields and announcement categories; leave sensitive options off.
- Enable sharing and press **Confirm introduction** only after reading the preview.
- Run `/wstatus test` to queue a synthetic level-10 event (requires the level field,
  level collection; immediate messages additionally require level announcements
  and a milestone interval that permits level 10).
- Run `/reload` to write the addon data to disk.

Locate **only** this file:

```text
WTF/Account/YOUR_ACCOUNT/SavedVariables/WoWStatus.lua
```

The addon uses account-level SavedVariables with per-character records. Do not
point the companion at an entire account directory or other addons' files. The
companion never executes this file as Lua.

```powershell
wow-status companion --saved-variables "C:\Games\World of Warcraft\_classic_era_\WTF\Account\YOUR_ACCOUNT\SavedVariables\WoWStatus.lua" --dry-run
```

Check the dry-run output for your selected fields only. New characters that never
opted in are omitted. A previously enrolled paused character exports an empty
snapshot and no events so the service can apply the pause. Continue using the local
test service and simulate with real exports if desired.

## 5. Connect Discord when the bot is ready

Follow [deploy/README.md](../deploy/README.md) for hosting, HTTPS, application setup
and server/channel permissions. Have a private test channel ready first.

For a local test using your own bot, set environment variables in a terminal;
these are placeholders, not actual credentials:

```powershell
$env:DISCORD_BOT_TOKEN = "YOUR_BOT_TOKEN"
$env:DISCORD_GUILD_ID = "YOUR_SERVER_ID"
$env:DISCORD_CHANNEL_ID = "YOUR_PRIVATE_CHANNEL_ID"
wow-status serve --db state/discord-test.sqlite3 --discord
```

```sh
# Linux/macOS: enter the token without putting it in shell history.
read -rs -p "Discord bot token: " DISCORD_BOT_TOKEN
export DISCORD_BOT_TOKEN
export DISCORD_GUILD_ID="YOUR_SERVER_ID"
export DISCORD_CHANNEL_ID="YOUR_PRIVATE_CHANNEL_ID"
wow-status serve --db state/discord-test.sqlite3 --discord
```

The program does not load `.env` automatically. systemd uses its EnvironmentFile
for hosted deployment. Never commit `.env`, paste tokens into issues or send them
in ordinary Discord chat. No OpenAI key is needed for this version.

In Discord, use `/link` in the configured server. Redeem the private code with
`wow-status link --url ...` using the service's HTTPS URL (or local loopback for a
single-computer local test). Then run the companion with the actual SavedVariables
path, without `--dry-run` or `--once`, to watch exports until Ctrl+C.

Use the same `--credentials` and `--state` values consistently for each installation.
The defaults are under your user's `.wow-status` folder. To watch multiple account
files, repeat `--saved-variables PATH`; all uploads use that installation's Discord
owner. Each friend should link their own companion under their own Discord account.

## 6. Structured JSON and daily recap

Uploads automatically maintain one JSON file per character in
`state/home-test-characters/` for the local test database, or
`state/discord-test-characters/` for the Discord test database. Related records are
grouped together. Each level-up has a recorded and first-uploaded timestamp with
`timezone: "Europe/Oslo"` and an explicit ISO UTC offset. Inspect those files locally.

The bot posts daily recaps at **00:05 Europe/Oslo**. It uses the previous day's
Norwegian calendar window and combines shared characters under friend headings,
including those with no recorded events. Long group reports paginate. Collect level-ups with immediate announcements disabled:
non-milestone levels should remain in JSON and the daily recap.

Stop the local test service before trying operator tools. Use an actual Oslo date
containing your own uploads (the synthetic fixture predates your home test):

```sh
wow-status recap --db state/home-test.sqlite3 --day YYYY-MM-DD
wow-status export --db state/home-test.sqlite3 --directory private-export
```

`recap` is a local simulation and marks that day's pending recaps simulated. Use a
test database, not production. Repeating it must not duplicate messages. Export
creates one JSON file per character plus a timezone-aware manifest. Confirm hidden
fields are absent from current and historical records. Retest after field disabling,
pause and deletion. Full format: [JSON_FORMAT.md](JSON_FORMAT.md).

## 7. In-game acceptance before broader use

- Confirm one introduction after first opt-in/export/upload. Reload, restart the
  companion and repeat the upload: no extra introductions or level messages.
- Test an existing character installing the addon: wording says joining the tracker,
  rather than claiming this character was just created.
- Test a real level-up at a selected milestone and a non-milestone level-up.
- Test self-loot above/below the rarity threshold and another player's loot. If item
  metadata is not cached yet, the current addon may skip that loot; record this case.
- Equip an item with gear sharing enabled; existing equipment on login is a baseline.
- Toggle off a field, export and upload: both current profile and stored related
  activity must lose it. Already posted Discord messages remain.
- Pause locally, export and upload: queued announcements must stop. For immediate
  server pause and token revocation use `/privacy action:pause` in Discord.
- Re-link and export current settings to resume. An already enrolled character must
  not reintroduce merely because it was paused or the addon was reinstalled.
- Test `/character` and `/activity` with duplicate names across realms; require a
  unique realm/client match and show export/upload timestamps honestly.
- Disconnect the uploader, export, then reconnect it: selected data should retry.
  Keep the latest SavedVariables file; the companion now uploads retained full history in batches beyond the recent 500-event buffer.
- Run `/privacy action:delete confirm:True`: profiles, queued events and credentials
  must disappear; previously issued credentials must be rejected.
- Test with two friends and separate Discord identities before inviting everyone.

Do not infer dungeon completion from entering/leaving an instance. Those collectors
are not implemented. Real dungeon evidence and Forever APIs remain later validation.

Record OS, client edition, build/interface number, locale and results in a GitHub
issue. Do not attach credentials or full real account folders. Synthetic fixtures,
redacted failure details and selected test-event output are enough.

Additional archive/recap checks: verify Norwegian summer and winter offsets, the
23/25-hour midnight windows, exactly one recap per day/character after restart,
late events counted in their assigned upload-day recap, and collection retained
when immediate announcements are disabled. These cases are authored in the test
suite and still need execution at home.


## Friend grouping, group reports and desktop acceptance

At home, run `wow-status desktop` to try the optional uploader window. Confirm
linking works with a private Discord code, the file picker selects only this addon,
status/timestamps update, Stop ends uploads, and closing waits for an in-flight
request. Check credentials stay out of messages and exports. CLI and desktop must
not run concurrently against the same upload state.

With two friends and at least two characters each, confirm:

- `/link` supplies each owner's server display name. `/nickname name:...` changes
  that person's labels only; reset restores the remembered Discord name.
- `/main` accepts only your own character and leaves one main per person. Addon
  exports cannot override an explicitly chosen Discord main.
- `/roster` groups the gang by owner, mains first, includes all shared characters
  across pages, and excludes paused characters.
- The daily recap combines characters under owner headings; large groups continue
  without dropping characters. Weekly recaps are due Monday at 00:05 Oslo time.
- Daily-only mode stores enabled events without immediate messages. Only Manage
  Server members can change community settings. Individual privacy stays enforced.
- Snapshot comparisons are labeled as inferred. Actual level-up times remain in
  JSON. Synthetic tests show [TEST] and do not count as real recap progress.
- Manually shared profession names are labeled player-entered and disappear from
  the roster and archive after disabling that profile field and uploading.
- Pause/deletion cancels pending daily and weekly report entries. Aliases/roles are
  removed on deletion, along with the managed character JSON files.

Offline weekly simulation (test database only, service stopped):

```sh
wow-status weekly --db state/home-test.sqlite3 --week YYYY-MM-DD
```

Choose an actual Monday date for a week containing your test uploads. Ambiguous
weekly sends are listed by `outbox` and can be resolved using `resolve-weekly`
with `--week`, `--character-id`, and `sent`, `retry`, or `discard`.


In-game history and line-graph checks are in [IN_GAME_HISTORY.md](IN_GAME_HISTORY.md).
Open `/wstatus logs`, `/wstatus graph`, and `/wstatus times` at home. Graph time is
elapsed clock time including offline hours; partial first intervals stay labeled.


Optional in-game level notifications have a separate two-friend checklist in
[LIVE_POPUPS.md](LIVE_POPUPS.md). First try the local `/wstatus popup test` preview
after enabling reception. The experimental transport uses visible custom-channel
messages and needs real client validation; it does not require service or bot keys.
