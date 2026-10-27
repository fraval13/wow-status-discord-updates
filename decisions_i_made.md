# Decisions I made — 27 October 2026

## Delivery status

The addon changes are implemented, tested and committed locally. **Pushing to
GitHub is blocked by authentication on this computer.** The configured
`github-home` SSH key requires a passphrase and is not loaded in an accessible
agent. Other available authentication did not grant repository access. There is
no configured GitHub CLI login or Git credential helper. I did not change keys or
repository permissions, and did not ask questions while you were away.

The push command, once GitHub SSH access is unlocked, is `git push origin main`.
If this Linux computer reports the system SSH configuration permissions error,
use `GIT_SSH_COMMAND='ssh -F /dev/null -i ~/.ssh/github-home' git push origin main`.
This can prompt for the key's passphrase. A different computer will not receive
this local commit through `git pull` until that push succeeds.

The installed Vanilla addon on this computer has been updated, and the previous
addon files were backed up under `state/addon-backups/20261027-235040/WoWStatus`.
SavedVariables were left intact. Local installable ZIPs are in
`dist/WoWStatus-vanilla.zip` and `dist/WoWStatus-forever.zip` (ignored build outputs).

## Settings live in the normal WoW menu

- Open **Options → AddOns → WoW Status** for character sharing settings.
- Its **Groups** subpage edits account-wide membership and your optional name.
- `/wstatus` and `/wstatus groups` open those same pages.
- Both pages scroll and resize to fit their settings container.
- The implementation supports the modern Settings API and the older
  InterfaceOptions API. Registration retries when Blizzard addons load later.
- Standalone windows remain as a fallback when neither settings API is available.

I used canvas categories so the existing character controls retain their behavior.
The API signatures were checked against the
[Classic UI source](https://github.com/Gethe/wow-ui-source/blob/classic/Interface/AddOns/Blizzard_Settings_Shared/Blizzard_Settings.lua).

## Why the group editor looked broken

The original group and sharing windows could remain visible together at the same
dialog layer, allowing sharing checkboxes and labels to overlap the group editor.
Moving one window did not fix the editor itself: its multiline EditBox also used
the single-line `InputBoxTemplate`.

Groups now has its own settings page. The standalone fallback hides the other
window, and the group field uses a plain multiline EditBox with an explicit font,
padding, a background and cursor scrolling. Enter inserts a new line. Saving
shows its result directly on the group page. Resizing does not overwrite unsaved
group edits. Embedded pages inherit their container's drawing layer and leave
Escape handling to WoW's settings window.

## Account groups, character checkboxes

- Group IDs and the optional player name are stored once for the WoW account.
- Saving the group list updates every saved character, including offline alts.
  New characters inherit it automatically.
- Existing per-character group lists are merged on the first upgraded login.
  The existing eight-group limit remains; if old lists together exceed eight,
  migration keeps a deterministic selection and prints a warning to review it.
- Each character keeps its own membership timestamps and level baseline. Existing
  timestamps are retained. Newly inherited groups start at the new join boundary,
  so old private history is not sent to a newly selected group.
- Removing a group removes it from every saved character. The companion applies
  remote withdrawals after `/reload` or logout exports the account file.
- Character sharing, profile fields, collection and announcement checkboxes remain
  per character. Existing choices, including paused characters, are preserved.
- Explicit legacy `/link` upload mode survives login. Saving the account group list
  explicitly switches all saved characters back to group routing.

Account-wide means one WoW account's SavedVariables file. It does not sync between
computers, different WoW accounts, or separate Vanilla and Forever installations.

## Defaults

For **new characters**, sharing and every checkbox under Profile fields, Store
events / daily recap, and Immediate announcements default to **on**.
Existing characters keep their saved checkbox choices; this update does not
silently reset them.

The introduction still needs **Confirm introduction**. The first initialization
does not queue a separate login-session announcement; subsequent logins/reloads
can queue session events when enabled. Existing filters remain level interval 10
and loot quality 4. Profession names and LFG text still require player input.
Experimental in-game popup send/receive preferences retain their separate opt-in
controls; these are distinct from sharing data through the companion.

No group is invented automatically. Use the configured `ronkalot` or `navsquad`
ID for the intended Discord destination. All selected data still requires the
local companion uploader and an export on `/reload` or logout.

## Validation and deployment

- Full test suite: **126 passed**, including menu registration, both addon
  editions, account inheritance/migration, removals, preserved character settings
  and group history boundaries.
- The addon tests also passed under Lua 5.1, in addition to Lupa's default runtime.
- Ruff passed for the changed Python test file; `git diff --check` passed.
- Both installable addon folders contain the synchronized shared Lua sources.
  Both addon versions are now **0.8.1**.
- Recovered server SSH access through the existing deployment agent. Both
  `wow-character-status` services are active and both loopback health endpoints
  reported healthy revision `bc7bd7f7b97567f93ffc95d4e0e8f7658ac373b9`.
- No server code update is required for this addon-only behavior. The normal
  GitHub checks/package/deployment workflow cannot run for this change until the
  commit is pushed. No Discord test message was sent.
- Real in-game rendering and interaction still need your check; mocked API tests
  cannot establish that the pages render correctly in the running client.

## Tomorrow's check

1. Ensure the local commit has been pushed before pulling it on another computer.
2. Install that computer's updated `addon/vanilla/WoWStatus` folder into the
   correct Classic Era `Interface/AddOns` directory, or use the addon ZIP from
   GitHub Actions once the push and checks succeed. Back up the old addon files;
   preserve `WTF/Account/.../SavedVariables/WoWStatus.lua`.
3. Restart WoW, log in, and open **Options → AddOns → WoW Status**. Check that the
   controls fit and the page scrolls. `/wstatus` should open the same page.
4. Open **Groups**. Enter an optional name and one destination per line. Save and
   confirm the success message. Check that typing, newlines and scrolling work.
5. Log into an alt on the same WoW account. The group list should match, while its
   character checkboxes remain independent. A new character starts with them on.
6. Confirm an introduction if needed, `/reload`, and run the companion with
   `https://wow.frankvalde.com` and this account's `WoWStatus.lua` export selected.
   Check the intended Discord channel. Merely opening the game does not upload.
