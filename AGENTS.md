# WoW Status — instructions for coding agents

These instructions apply to the whole repository. Read `README.md` before changing
behavior.
This file preserves context from the previous session; dated state below must
be checked against Git and the environment rather than assumed permanently true.

## Product and owner preferences

- In-game friend sharing is the primary product. Friends install only the addon
  and enter the same group ID. Do not require a desktop client or server for it.
- Discord/uploader/backend code is retained but hidden and disabled in the addon
  by `addon/shared/Features.lua` (`discord = false`). Keep it hidden unless the
  owner asks to restore it. The owner's two optional production groups are
  configured only on the server (`/etc/wow-character-status/groups.json`); do not
  remove their service routes. A group name is a shared secret (issue #1): never
  write a real group name or route key into the repository, issues, PRs or logs.
- Groups are account-wide; character preferences remain per character. Joining
  a group enables its ordinary sending/receiving without redundant opt-ins.
- Notifications queue, show one at a time, and can be dismissed by clicking.
  Do not restore the visible "click to dismiss" instruction.
- Preserve automatic, bounded, two-way login log sync with stable event IDs.
  Catch-up entries are quiet; do not replay old popups or duplicate announcements.
- Avoid spam: first recorded zone visits; each 100 completed quests; first
  profession learning and title promotions; first equip of eligible rare/epic/
  legendary armor per item ID. No ordinary quest-turn-in, skill-point, equipment
  change, or looting announcements. Keep milestone reports automatic, without
  free-text announcements or manual dungeon invitations/reports.
- Homepage style is nostalgic 2005-era WoW. The owner rejected both walking and
  lights-only animation experiments. Keep the original still illustration; do
  not restore videos, GIFs, animation assets or preview controls.
- Make reasonable implementation decisions and finish authorized work without
  repeatedly asking routine questions. Explain consequential choices and delivery
  limitations in the pull request description. Never claim a push/deployment succeeded
  unless verified. Do not send test Discord messages unless requested.

## Repository map

- `addon/shared/`: canonical shared Lua and textures.
- `addon/{vanilla,forever,tbc,retail}/WoWStatus/`: four self-contained distributions
  with edition-specific adapters and TOCs. Keep their shared files in sync.
- `Safe.lua`: public-value boundary; guard missing APIs and Retail secret values.
- `Groups.lua`, `Popups.lua`, `Journal.lua`: membership, live transport/queue and
  persistent log/login recovery. Retain bounded payloads, queues and validation.
- `Presentation.lua`, `Flavour.lua`, `Previews.lua`: themes, caption selection and
  local-only preview controls. Previewing must not send or record real progress.
- `docs/notification-flavour-text.md`: complete 1,300-line caption catalogue,
  100 for each of 13 preview categories. Match this with every `Flavour.lua` and
  the four banks in `website/flavour.js` when editing copy.
- `src/wow_status/`: preserved Python companion, ingestion, Discord and storage.
- `tests/`: Python tests and mocked Lua clients/transports. Mocks do not establish
  live game API availability, rendering or cross-realm delivery.
- `website/`: buildless static HTML/CSS/JS and locally served artwork/fonts.
- `scripts/build_homepage.py`: packages committed addon source into four ZIPs;
  fills website versions/sizes and publishes a checksummed release manifest.
  Each ZIP holds only the TOC, the files it lists and `Textures/*.tga`; other
  committed files are skipped. The build fails unless all four TOC versions
  equal the `pyproject.toml` version. Each build replaces its output folder as a
  whole, so no file of an earlier build survives.
- `.github/workflows/checks.yml`: Linux/Windows checks, packaging, deployment and
  public verification on `main` pushes; also supports manual dispatch. Actions are
  pinned by commit SHA, checkouts keep no token, and a failed public verification
  asks the receiver to roll back (issue #27; details in `deploy/SERVER.md`).
  `scripts/verify_homepage.py` compares the live site with the locally built
  `release.json` (`--manifest`) and checks each ZIP's entries against its TOC.
  `scripts/deploy_gate.py` lets a run deploy only while its commit is the tip of
  `main`, so an older run never deploys over a newer one.
- `deploy/SERVER.md`: current dedicated server deployment architecture, the private
  group configuration, and how to render the Caddyfile and rotate a group name.
  `deploy/README.md` also contains historical single-instance setup instructions.

## Current release and open handoff (1 November 2026)

- All four editions are version **0.14.13**; project version is in `pyproject.toml`.
  The packaged addon revision is in the live `downloads/release.json`.
- Latest completed feature: random flavour captions below popup facts and on
  activity-log cards. Event identity selects a varied line; its local saved copy
  remains stable. Previews and website demo draw randomly, avoiding immediate
  repeats. No caption/class metadata was added to transport packets.
- Death bank: 22 general roasts plus six for each of 13 classes. Class-specific
  jokes require public unit information identifying the sender (player/group/
  target/focus/mouseover); unknown classes use general jokes. Item `class_id`
  describes armor, NOT the player's class. Peers can have different caption
  choices when different class information is available.
- Latest verified static site release:
  `/srv/wow-status-homepage/releases/20261030T151554096730Z`.
  Public homepage/downloads: https://wow.frankvalde.com/ . Each `main` deploy
  verifies the live ZIPs against their hashes, TOCs, links and exact source
  revision; the deployed version is in the live `downloads/release.json`.
- Last validation: 270 full tests; 161 addon tests also under Lua 5.1; Ruff and
  whitespace checks passed. Browser checks passed at widths 1440/820/390/320;
  random demo-caption checks passed locally and live. The new in-game layout
  still needs the owner's live-client check. Do not describe mocks as that check.
- `docs/IMPLEMENTATION_STATUS.md` and older dated notes include historical
  versions/limitations. Use current source, README and newest decision entries
  when they disagree with old descriptions.
- GitHub pushes work again and every push to `main` runs the hosted
  "Checks and addon packages" workflow (Ubuntu and Windows `validate`, then
  `deploy`). Check that run's result on GitHub Actions before describing a
  release as validated or deployed; do not hunt for credentials. `deploy` shows
  as skipped when `deploy-gate` finds the run's commit is no longer the tip of
  `main` ("Deploy skipped" notice), so check that `deploy` ran, not just that the
  run is green. On a "Re-run failed jobs" attempt `deploy` fails on purpose; use
  "Re-run all jobs" to redeploy.
- Uncommitted work predating this feature remains: shared/all-edition
  `Minimap.lua` edits, Vanilla/Forever TOC `IconTexture` lines, `Textures/Logo.tga`
  files, and `assets/branding/`. These belong to separate branding work. Preserve
  them; do not discard, silently stage, overwrite or ship them as part of another
  task. Check `git status` and diffs first. A clean release worktree is useful
  for validation: the dirty branding state changes an older minimap-icon test.

## Editing and validation

Use Lua 5.1-compatible syntax in shared code. Keep adapter boundaries and missing/
restricted API guards. Do not attempt to bypass WoW networking or secret values.
Addon-only HTTPS/socket access is not available; in-game sharing uses the game's
allowed channel discovery and addon whisper transport. Realm/faction rules apply.

`python scripts/sync_addons.py` mirrors ALL Git-tracked shared Lua and textures into
all four editions, deleting tracked edition copies whose shared source is gone
(`--check` only reports). Untracked files are neither copied nor deleted, so `git add`
a new shared file first, and add a new edition-owned adapter file to `EDITIONS` in
the script. Inspect pending changes first: it can also propagate unrelated branding
work. With unrelated edits present, copy only task-owned files or use an isolated
worktree. Add new Lua files to each edition's TOC before consumers and update any
explicit test-harness load lists (`test_addon.py`, `test_forever.py`).

Versions: feature pull requests must NOT change the version. Several agents work
on separate issues at once, so per-feature bumps would conflict and pick the same
number. A release is its own small pull request that only changes the version
(see `scripts/sync_version.py` below) and adds release notes. Merging it
publishes the new number.

`requirements.txt` pins, by version and SHA-256, every package the server's
receiver installs (runtime dependencies plus the build backend). After changing
dependencies in `pyproject.toml`, run `python scripts/lock_requirements.py` (needs
`uv`); `tests/test_requirements_lock.py` fails while the two disagree.

Release notes live in `CHANGELOG.md` (newest `## <version>` first; it must match
`pyproject.toml`). After editing it run `python scripts/whats_new.py` and
`python scripts/sync_addons.py`: the addon's one-time What's New page and the
homepage release panel both come from it, and the homepage build fails when the
release version has no notes.

Development setup and ordinary checks:

```sh
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests
node --check website/app.js
node --check website/flavour.js
git diff --check
```

Windows decodes text with cp1252 unless told otherwise, so always pass
`encoding='utf-8'` to text I/O (`read_text`, `write_text`, `open` and friends, and
`subprocess` calls that decode output). CI runs pytest and the homepage
build with `PYTHONWARNDEFAULTENCODING=1` and `PYTHONWARNINGS=error::EncodingWarning`,
so any such call on a tested path fails, including in scripts that tests start as
subprocesses. `tests/test_text_encoding.py` also scans `src/`, `scripts/`, `deploy/`
and `tests/` statically for the common forms; it cannot see code inside string
literals. Reproduce locally
with `LC_ALL=C PYTHONWARNDEFAULTENCODING=1 PYTHONWARNINGS=error::EncodingWarning
python -X utf8=0 -m pytest -q`.

Use existing environments when available. Run checks appropriate to the change;
documentation-only changes need link/whitespace review, not a full runtime suite.
lupa's default runtime is a newer Lua (5.5 in lupa 2.8) but every WoW client runs
Lua 5.1, so also run `python -m pytest -q --lua=5.1` (in the venv) after addon changes.
The option (in `tests/conftest.py`) swaps `lupa` for `lupa.lua51` before tests import
it, prints how many tests started a Lua 5.1 runtime, and fails if none did. CI runs it on
Ubuntu and Windows after the default run.
Do not modify player SavedVariables to install or test a release. Back up addon
files before replacing a local game installation; keep account groups/logs intact.

## Packaging and deployment

See `website/README.md` and `deploy/SERVER.md` before publishing. Commit intended
addon source first: builds read addon files from Git, not the working tree;
website assets come from the working tree. Verify precisely what will ship.
The builder builds into a new folder and swaps it in only when complete, so a
rebuild drops deleted assets and a failed build leaves the earlier one in place.
It refuses an existing `--output` folder that is not an earlier build.

```sh
python scripts/build_homepage.py --addon-ref <full-commit-sha> --output dist/homepage-clean
python -m http.server 4173 --directory dist/homepage-clean --bind 127.0.0.1
```

The default publisher expects `dist/homepage` (see its CLI for other options), built
for the checkout's `HEAD` with everything it ships committed. Final
ZIPs must contain top-level `WoWStatus/` and all TOC-listed files. All four versions
must match. `downloads/release.json` records source revision and checksums; website
version and size labels are generated, not maintained manually. Update meaningful
release notes in `website/index.html` in the release pull request.

To change the version, edit `project.version` in `pyproject.toml` only, then run
`python scripts/sync_version.py` to write it into all four addon TOCs. Do not edit
the TOC `## Version:` lines by hand. `scripts/sync_version.py --check` reports drift
without changing files and runs in CI, so a half-finished bump fails the build before
`build_homepage.py` refuses to package mismatched versions. The script never chooses
a version number itself; releases stay deliberate.

Server: `root@193.243.189.202`. The previous session used the already-authorized
SSH agent at `/tmp/wow-forever-deploy-agent.sock`; this is ephemeral context, not a
credential or a promise that access survives a new session. Check access normally.
Never read/print private configuration or tokens to recover access.

With available authorized access and a built default output:

```sh
SSH_AUTH_SOCK=/tmp/wow-forever-deploy-agent.sock \
  python deploy/publish_homepage.py --host root@193.243.189.202
python scripts/verify_homepage.py --url https://wow.frankvalde.com \
  --revision <full-40-character-addon-commit-sha> \
  --manifest dist/homepage/downloads/release.json
```

Before contacting the host, the publisher refuses a build of another revision,
uncommitted or untracked `website/`, builder, Caddyfile renderer or
`deploy/install_homepage.py` files, a ZIP that does not match its
`release.json` checksum, and any stale, missing or changed file compared with a
fresh build it makes itself; it uploads that fresh build (issue #19). It renders the
Caddyfile's group routes from the committed template and the server's private
`groups.json` (`--dry-run` shows the Caddy diff and changes nothing). On the server,
`deploy/install_homepage.py` checks the upload's checksum, validates the candidate
Caddyfile outside the web root, atomically switches the static-site symlink and
reloads Caddy, keeping the newest five releases for rollback; a failure removes the
partial release and the upload. It holds the pipeline receiver's deployment lock
throughout, so it waits while a pipeline deploy runs, and refuses if that deploy
switched the site meanwhile. Website-only publishing
does not require restarting companion services. Verify public assets/downloads
and existing group health routes after deployment. Do not touch unrelated
`wow-forever-news` or `wow-forever-qa` services.

- Website root: `/srv/wow-status-homepage/current`.
- Python app releases: `/opt/wow-character-status/releases/`.
- Private configuration: `/etc/wow-character-status/` (do not expose).
- Group services: `wow-character-status@<instance>`, one localhost port each
  (18081 and 18082), routed from `/groups/<route key>/`. Instances, names and keys
  live only in the private `groups.json`; see `deploy/SERVER.md`.
- Unknown `/groups/` URLs must remain 404. Keep persistent per-group databases and
  archives separate. Do not restart bots or send messages for a static-site task.

Do not commit secrets, exported player data, SavedVariables, SQLite files or
private deployment archives. Respect `.gitignore`. Clearly report any remaining
Git push, live-client validation or deployment limitation in the final handoff.
