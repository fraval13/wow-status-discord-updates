# CurseForge listing and automatic uploads

The addon is published on CurseForge as one project with one file per edition.
After the one-time setup below, every release that `main` deploys to the
homepage is also uploaded to CurseForge by the `curseforge` job in
`.github/workflows/checks.yml` (`scripts/upload_curseforge.py`).

## Setup

The project is <https://www.curseforge.com/wow/addons/wow-status> (project ID
`1772945`, license All Rights Reserved). The GitHub repository variable
`CURSEFORGE_PROJECT_ID` is set to that ID.

Remaining one-time step for the owner:

1. In CurseForge author settings, open **API Tokens**
   (<https://www.curseforge.com/account/api-tokens>) and create a token. A Core
   API key from console.curseforge.com is a different key and is refused as
   "malformed" (HTTP 400).
2. Store it as the GitHub Actions secret `CURSEFORGE_API_TOKEN`, for example with
   `gh secret set CURSEFORGE_API_TOKEN` (it prompts for the value).
3. Upload the current release: **Actions → Checks and addon packages → Run
   workflow** on `main`, or merge the next pull request.

Without the token the job runs but uploads nothing and prints a notice. Without
the variable the job is skipped.

The listing's description, summary and categories are edited on CurseForge, not
here: the upload API only accepts files. Paste the text below into the project
settings after changing it.

## How uploads work

- Each ZIP is the homepage ZIP, built from the release commit: one top-level
  `WoWStatus/` folder, no version number in the folder name.
- Each file is tagged with the game version from its TOC `## Interface:`
  (`120105` → `12.1.5`). If CurseForge does not list that patch yet, the newest
  listed patch of the same `major.minor` is used, with a warning. If it lists
  nothing for the edition (possibly Forever, `1.60.x`), that edition is skipped
  with a warning; the homepage still offers it.
- The Forever file carries every spoken-reaction clip (about 300 MB): the job runs
  `scripts/voices.py bundle`, which adds the clips `VoiceData.lua` lists from the
  published `voice-pack` release and marks the build as bundled. The homepage's
  Forever ZIP stays small and uses the separate pack. If the pack lacks a clip the
  addon lists, the job stops before uploading anything; publish a newer pack and
  re-run it. CurseForge publishes no size limit; if it refuses the file, the job
  fails with its reason and the other editions are still uploaded.
- Display name: `WoW Status <version> (<edition>)`. Release type: `release`.
  Changelog: that version's lines from `CHANGELOG.md`.
- The job runs only after `deploy` succeeds. A file that fails fails the job.
  Re-running a job that did upload creates duplicate files, so delete those on
  CurseForge or re-run only after a failure.

## Listing

**Name:** WoW Status

**Summary** (short description):
See your friends' level-ups, deaths and big firsts pop up in game, cheer with one click, and compare in a group leaderboard.

**Categories:** Chat & Communication (main), Guild, Quests & Leveling, Achievements

**License:** chosen by the owner. The repository has no license file yet.

**Source / issues:** <https://github.com/fraval13/wow-status-discord-updates>
**Website:** <https://wow.frankvalde.com/>

**Description** (Markdown):

```markdown
# WoW Status

**Play together, even when you are not in the same zone.**

WoW Status brings your friends' big moments into your game. When someone dings,
dies, clears their first dungeon or gets their first mount, it pops up on your
screen, and you can cheer them on with one click.

No website, no account, no extra program. Everyone installs the addon and enters
the same **group ID**. That is all.

## Never miss a ding
- Level-ups and deaths
- First dungeon clears, first raid boss kills, first mount and first epic mount
- New zones, new professions, reputation ranks, class unlocks and PvP ranks
- Every 100 completed quests
- The first time someone equips rare, epic or legendary armor

Each moment gets its own notification with a cheeky caption. React with
**GZ!**, **F** or **Congrats!**, and your friend sees who cheered.

No spam: ordinary quests, loot and gear swaps stay quiet.

## Your group at a glance
- **Characters:** every friend's characters with level, XP, deaths, kills, gold
  and who is online right now
- **Leaderboard:** one per group, sorted by level, deaths or quests
- **Records:** who in the group reached each milestone first
- **Activity log:** everything that happened, filtered by person or type. Missed
  something while you were offline? It catches up quietly when you log in.

## Make it yours
- Session recaps of your evening
- Window themes, adjustable notification size and a compact group status line
- Optional screenshots on level-up and first dungeon clear
- English or Norwegian (Nynorsk)

## Getting started
1. Install WoW Status and log in.
2. Open **Options → AddOns → WoW Status → Groups**.
3. Enter the same group ID as your friends.

Keep your group ID private: anyone who knows it can join your group.

## Works on
Retail, Classic Era, TBC Anniversary and WoW Forever. Pick the file for your game.
```

Keep this description in step with `README.md` when features change. Do not put
a real group name in the listing.
