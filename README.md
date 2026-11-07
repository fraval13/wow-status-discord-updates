# WoW Status

**Homepage and addon downloads: [wow.frankvalde.com](https://wow.frankvalde.com/).**
The homepage source, build instructions and deployment notes are in
[website/README.md](website/README.md).

Share progress with friends inside WoW. Use the same group ID to receive queued
on-screen announcements and browse a persistent activity log. Notifications have
random flavour captions from [13 banks of 100 lines](docs/notification-flavour-text.md).
Each event keeps its caption in your log. Class-specific death jokes are used
only when WoW can identify the sender’s class; otherwise a general roast is used.

## Continuing development in a new session

Start with [AGENTS.md](AGENTS.md). It contains the repository map, product choices,
release workflow, deployment pointers and pending-work caveats.

Every merge to `main` prepares one minor-version increment, runs the tests, and
deploys matching homepage, addon downloads and group services. Re-running a release
keeps its existing version. The [public release manifest](https://wow.frankvalde.com/downloads/release.json)
records the published version and exact source revision
(see [deploy/SERVER.md](deploy/SERVER.md)). Live in-game checking of the
caption layout is pending. The homepage uses its original still artwork.

Some older status documents describe
historical releases; the current source and newest handoff notes take precedence.

## Start sharing

The addon groups the character list by player with
class portraits, adds window themes and a size setting, a first-time setup guide
and Show me around tour, session recaps, Firsts medals, and catches group history
up from friends. It also keeps live updates working when players' clocks disagree,
delivers every update to every member, and stops one player filling the activity
log. 0.14.13 sent updates and log sync during combat (WoW Forever could report
combat all the time, which stopped both). 0.14.12 added corrected Retail/Forever minimap
button placement, the dungeon API fix, clearer group-join wording, group warnings
for invalid log data, leaving removed group channels after `/reload`, and counting
a death once when the player releases their spirit.

1. Copy the appropriate `addon/vanilla/WoWStatus`, `addon/tbc/WoWStatus` (TBC Anniversary),
   `addon/retail/WoWStatus` (Retail), or `addon/forever/WoWStatus`
   folder into that client's `Interface/AddOns` directory. Complete ZIPs are in
   `dist/` after packaging. Restart WoW after updating.
2. Open **Options → AddOns → WoW Status → Groups** and add the same group ID as
   your friends. Groups are saved account-wide; character preferences are separate.
3. Click the minimap book to open the **WoW Status** window on its last page (the
   **Activity** tab at first), or use `/wstatus activity`. `/wstatus <page>` opens any
   tab directly; the window remembers its position.
   Right-click the book for Options; drag it to move it around the minimap.
4. To invite a friend who does not have the addon yet, right-click their name and
   choose **Share WoW Status** (clients with the modern menu), or type
   `/wstatus share <name>`. It whispers the download link, at most once per person
   per hour, and is never sent automatically.

Click a character card, then scroll below the recent activity and gear to see
their equipped items in a character-sheet layout. Hover a slot for the item's
full tooltip, including its enchant and random suffix. Available combat stats
appear underneath. The timestamp marks the last reported snapshot; stats can
include buffs. A visible unit can supply a live 3D model; offline characters use
their race portrait beside their saved equipment.

Friends fetch equipment when you open a profile, at most once a minute per
character. The owner needs the updated addon and must be online on one of their
characters to provide a snapshot. Previously received gear remains available
offline. Characters must log in with this version before their own gear can be
saved. **Character details → Equipment and combat stats** controls this sharing;
hidden characters and accounts with character-list sharing off do not send gear.
See [equipment profiles and live checks](docs/EQUIPMENT_PROFILES.md).

## Language

WoW Status is in English by default. Nynorsk is optional: choose it under
**Notifications → Language** in the settings, or type `/wstatus language nn`
(`/wstatus language en` switches back), then `/reload`. Windows, notifications, the
log, records and all 1,300 captions change; what players send each other stays
English, so friends can use different languages. Diagnostics (`/wstatus popup status`)
and the release notes stay English.

## Caption personalities

The funny line under each notification comes from a **Random** personality by
default: each notification picks one of the voices below, Classic included. Under
**Notifications → Caption personality** dropdown, or with `/wstatus personality <name>`, you can
stick to one voice instead: Classic, Wholesome, Epic bard, Grumpy veteran, Goblin
merchant, Christian, Condescending Christian, Dwarf, Jealous friend, Drama queen,
Secret agent or Middle-school legend.
Each has 300 captions per event, plus 30 death roasts for each class, in English and
Nynorsk. The choice is yours alone (friends can pick their own), applies to new
notifications, and captions already in your log keep their wording. See
`docs/caption-personalities/README.md` to edit or add one.

The same voices can also speak your **reactions**: the whisper a friend gets when you
click GZ!, F or Congrats! on their notification. These go out in your name, so they
have their own setting, the **Notifications → Reaction voice** dropdown or `/wstatus voice <name>`. The
default is the gentle **Wholesome** voice; you can also pick Random, **Classic** (the plain
GZ!/F/Congrats! texts) or any personality except Secret agent and Middle-school legend,
whose whispers are still to come. Each voice has 300 whispers for every reaction; the
button keeps its short label.

## Announcements

The main settings page controls levels, deaths, first recorded zone visits, each 100 completed
quests, new professions and profession title promotions, first dungeon clears, first raid boss kills, first mount,
reputation ranks, major class unlocks and PvP ranks. **Notifications** holds the popup
settings, with local samples below them. Notifications queue one at a time for six seconds each.

**Screenshots** (per character, all off by default) can take a picture about one
second after your own level-up or first dungeon clear, optionally with the interface
hidden (never in combat, where a normal screenshot is taken). Pictures stay in WoW's
`Screenshots` folder and are never uploaded. `/wstatus screenshot` takes one by hand.

**Announce first armor equips** has separate **Rare equipment**, **Epic equipment** and
**Legendary equipment** choices, all enabled by default. Only equippable items in
WoW's Armor class qualify, including armor, cloaks, shields and jewelry. Weapons,
bags, trade materials, recipes, common/uncommon and unclassified items are excluded.
The first recorded equip of each item ID announces once per character; looting,
re-equipping and moving the same item do not. Already-worn equipment is seeded
silently when first enabling tracking. The rarity choices also filter incoming
and recovered equipment announcements.

Joining a group automatically announces once per character per group and appears
in the log as **Joined the WoW Status group**. There are no free-text announcements or manual dungeon reports.
Successful raid encounters are recorded once per encounter ID. Raid milestones and
first epic mounts receive large banners and Firsts medals. Epic mounts are detected
conservatively on Classic-family clients: the addon must observe a new epic mount item in
your bags. Existing inventory establishes a quiet baseline, including items whose
information loads later. Class-quest mounts without items may be missed. Retail mounts scale with riding skill, so this detector stays
disabled there. The Dungeon / raid and Mount settings control these categories.

Session recaps stay private by default. Enable **Share my session recaps** for a
compact summary of your own recorded milestones, with fixed phrases and counts.
It respects your current announcement and character-detail choices. Friends need
a version supporting recap sharing to see it; older clients ignore the new events.
Recovery stays quiet, with the usual log bounds.

Dungeon completion requires a supported game completion signal; unsupported
clients skip it. See [in-game testing and coverage](docs/LIVE_POPUPS.md).

Malformed log data is rejected silently and never enters the activity log. The
group warning popup that earlier versions showed for it was removed after false
alarms in live play. See [invalid log data](docs/LOG_GUARD.md).

## Activity log and login sync

The scrollable log uses the same icons and colours as popups, with **All**, **Mine**
and **Friends** filters. Individual quest turn-ins are omitted; only hundred-quest
achievements appear. Detailed profession and equipment-change activity stays
private. Eligible announcements and requested equipment snapshots are exchanged
with group members according to the character's sharing settings.

At login, the addon greets available group members and both sides automatically
exchange missing announcement IDs. An already-online friend also recovers saved
entries from the arriving player. There is no periodic polling after the login
exchange completes. **Sync now** on the Characters page repeats it on request (once a
minute): it resends your character list, asks for everyone else's and catches up the
log, still limited to one catch-up per member every ten minutes. Recovery adds quiet log cards rather
than replaying old popups, and duplicate IDs do not create duplicate entries.

Someone with a saved copy must be online. Sync covers up to seven days after your
group join time, bounded by the retained log: 2,000 of your own entries (at most
1,000 of them private activity) and, separately, 2,000 received entries, so
received entries never push out your own. Each login session takes at most 300
caught-up entries from one member, at most 100 of them about any one other
member; the rest come from other members or the next login. Realm/faction/whisper
restrictions still apply.
Friends should update to the same release for login sync and armor metadata.

## Development

Canonical Lua is in `addon/shared`; run `python scripts/sync_addons.py` after edits
(`--check` reports differences without changing files). It mirrors Git-tracked
shared files only, so `git add` new shared files first.
Standalone client folders contain all required Lua and texture files. Client
adapters remain separate, and missing optional APIs are guarded.

Run `.venv/bin/pytest -q` and `.venv/bin/ruff check src tests` after installing the
project's development dependencies. Tests simulate clients and transport; real
in-game rendering and API availability still require checking.

- [Activity log, history and timings](docs/IN_GAME_HISTORY.md)
- [In-game acceptance tests](docs/LIVE_POPUPS.md)
- [Forever and Retail compatibility check](docs/CLIENT_COMPATIBILITY.md)
- [CurseForge listing and automatic uploads](docs/CURSEFORGE.md)
- [Implementation status](docs/IMPLEMENTATION_STATUS.md)
