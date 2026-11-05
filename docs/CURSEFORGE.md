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
here. The text below is the current recommended listing; the original one
describes only Classic Era and armor loot.

## How uploads work

- Each ZIP is the homepage ZIP, built from the release commit: one top-level
  `WoWStatus/` folder, no version number in the folder name.
- Each file is tagged with the game version from its TOC `## Interface:`
  (`120105` → `12.1.5`). If CurseForge does not list that patch yet, the newest
  listed patch of the same `major.minor` is used, with a warning. If it lists
  nothing for the edition (possibly Forever, `1.60.x`), that edition is skipped
  with a warning; the homepage still offers it.
- Display name: `WoW Status <version> (<edition>)`. Release type: `release`.
  Changelog: that version's lines from `CHANGELOG.md`.
- The job runs only after `deploy` succeeds. A file that fails fails the job.
  Re-running a job that did upload creates duplicate files, so delete those on
  CurseForge or re-run only after a failure.

## Listing

**Name:** WoW Status

**Summary** (short description):
Share levels, deaths, first dungeon clears and other milestones with your friends in game, with a shared activity log.

**Categories:** Chat & Communication (main), Guild, Quests & Leveling, Achievements

**License:** chosen by the owner. The repository has no license file yet.

**Source / issues:** <https://github.com/fraval13/wow-status-discord-updates>
**Website:** <https://wow.frankvalde.com/>

**Description** (Markdown):

```markdown
# WoW Status

See your friends' progress in game. Everyone installs WoW Status and enters the
same **group ID**. There is no website, account or desktop program to set up.

## What it shares
- Level-ups, deaths (with a total) and every 100 completed quests
- First visits to new zones, new professions and profession title promotions
- First dungeon clears, first raid boss kills, first mount and first epic mount
- Reputation ranks, major class ability unlocks and PvP ranks
- The first time you equip rare, epic or legendary armor

Announcements appear one at a time as on-screen notifications with a random
flavour caption. Click one to dismiss it. Nothing is announced for ordinary
quest turn-ins, loot or gear swaps.

## Activity log
Open it from the minimap book or with `/wstatus activity`. It keeps your own
and your friends' milestones. When you log in, the addon quietly catches up on
what you missed from group members who are online, without replaying old
notifications.

Retail characters also get their earlier level-ups from their level
achievements, and their lifetime death count from the game's statistics.

## Also included
- Firsts medals: who in the group reached each milestone first
- Private session recaps, which you can choose to share
- Optional screenshots on level-up and first dungeon clear
- A character list grouped by player, with class portraits
- Window themes, a setup guide and a short tour

## Getting started
1. Install the addon and log in.
2. Open **Options → AddOns → WoW Status → Groups**.
3. Enter the same group ID as your friends.

Treat the group ID like a password: anyone who knows it can join the group.

## Editions
Retail, Classic Era and TBC Anniversary each have their own file. Install
the one for your game version.

Sharing uses WoW's own addon messages, so the usual realm and faction limits
apply.
```

Keep this description in step with `README.md` when features change. Do not put
a real group name in the listing.
