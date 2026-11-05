# CurseForge listing and automatic uploads

The addon is published on CurseForge as one project with one file per edition.
After the one-time setup below, every release that `main` deploys to the
homepage is also uploaded to CurseForge by the `curseforge` job in
`.github/workflows/checks.yml` (`scripts/upload_curseforge.py`).

## One-time setup (project owner, logged in to CurseForge)

1. Go to <https://authors.curseforge.com/>, choose **Create project**, game
   **World of Warcraft**, and fill it in from the [listing](#listing) below.
   Upload `assets/branding/WoWStatus-curseforge.png` (400 × 400) as the avatar.
2. Submit it. CurseForge reviews new projects, which can take a few days.
3. Note the numeric **Project ID** from the project's page.
4. In CurseForge author settings, open **API Tokens** and create a token.
5. In GitHub, go to **Settings → Secrets and variables → Actions**:
   - **Secrets**: add `CURSEFORGE_API_TOKEN` with the token.
   - **Variables**: add `CURSEFORGE_PROJECT_ID` with the project ID.
6. Upload the current release: **Actions → Checks and addon packages → Run
   workflow** on `main`, or merge the next pull request.

Until `CURSEFORGE_PROJECT_ID` is set, the `curseforge` job is skipped.

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
