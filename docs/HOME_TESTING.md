# Home testing checklist

This guide is for your personal gaming computer and later your own hosting server.
No tests or project processes were run on the work computer. No real keys are in
this repository. Do the keyless checks first; Discord can be connected afterwards.

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

The installer copies only this addon's three files. It refuses to overwrite an
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
Norwegian calendar window and one message per shared character, including those
with no recorded events. Collect level-ups with immediate announcements disabled:
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
  Keep the latest SavedVariables file; there is a 500-event rolling buffer per character.
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
