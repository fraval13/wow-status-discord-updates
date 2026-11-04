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

As of **5 November 2026**, all four downloads are **0.14.12**. Every merge to
`main` runs the tests and deploys the homepage, addon downloads and group
services (see [deploy/SERVER.md](deploy/SERVER.md)). Live in-game checking of the
caption layout is pending. The homepage uses its original still artwork.

Some older status documents describe
historical releases; the current source and newest handoff notes take precedence.

## Start sharing

The current release is **0.14.12**. It adds corrected Retail/Forever minimap
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

## Announcements

The main settings page controls levels, deaths, first recorded zone visits, each 100 completed
quests, new professions and profession title promotions, first dungeon clears, first mount,
reputation ranks, major class unlocks and PvP ranks. **Preview toasts** opens local
samples. Notifications queue one at a time for six seconds each.

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
Dungeon completion requires a supported game completion signal; unsupported
clients skip it. See [in-game testing and coverage](docs/LIVE_POPUPS.md).

Malformed log data can trigger a group warning naming its direct sender:
**"<character> is a really bad boy, shame on you!"** The popup identifies the
reporter, is rate-limited, and is never saved as activity or replayed through
history. This is a report about invalid data, not proof of cheating; a peer-only
addon cannot verify every plausible milestone. All recipients need 0.14.10 to
display these warnings. See [warning behavior and limits](docs/LOG_GUARD.md).

## Activity log and login sync

The scrollable log uses the same icons and colours as popups, with **All**, **Mine**
and **Friends** filters. Individual quest turn-ins are omitted; only hundred-quest
achievements appear. Detailed personal equipment and profession activity stays private; only eligible announcements are exchanged with group members.

At login, the addon greets available group members and both sides automatically
exchange missing announcement IDs. An already-online friend also recovers saved
entries from the arriving player. There is no manual catch-up button or periodic
polling after the login exchange completes. Recovery adds quiet log cards rather
than replaying old popups, and duplicate IDs do not create duplicate entries.

Someone with a saved copy must be online. Sync covers up to seven days after your
group join time, bounded by the retained log: 2,000 entries, including at most
1,000 private activity entries. Realm/faction/whisper restrictions still apply.
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
- [Implementation status](docs/IMPLEMENTATION_STATUS.md)
