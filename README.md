# WoW Status

Share progress with friends inside WoW. Use the same group ID to receive queued
on-screen announcements and browse a persistent activity log.

## Start sharing

1. Copy the appropriate `addon/vanilla/WoWStatus` or `addon/forever/WoWStatus`
   folder into that client's `Interface/AddOns` directory. Complete ZIPs are in
   `dist/` after packaging. Restart WoW after updating.
2. Open **Options → AddOns → WoW Status → Groups** and add the same group ID as
   your friends. Groups are saved account-wide; character preferences are separate.
3. Click the minimap book to open **Activity log**, or use `/wstatus activity`.
   Right-click the book for Options; drag it to move it around the minimap.

## Announcements

The main settings page controls levels, deaths, first recorded zone visits, each 100 completed
quests, profession title promotions, first dungeon clears, first mount,
reputation ranks, major class unlocks and PvP ranks. **Preview toasts** opens local
samples. Notifications queue one at a time for six seconds each.

**Announce armor loot** has separate **Rare equipment**, **Epic equipment** and
**Legendary equipment** choices, all enabled by default. Only equippable items in
WoW's Armor class qualify, including armor, cloaks, shields and jewelry. Weapons,
bags, trade materials, recipes, common/uncommon and unclassified items are excluded.
The same rarity choices filter the log, incoming loot and recovered entries.

There are no free-text announcements, introductions or manual dungeon reports.
Dungeon completion requires a supported game completion signal; unsupported
clients skip it. See [in-game testing and coverage](docs/LIVE_POPUPS.md).

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

Canonical Lua is in `addon/shared`; run `python scripts/sync_addons.py` after edits.
Standalone client folders contain all required Lua and texture files. Client
adapters remain separate, and missing optional APIs are guarded.

Run `.venv/bin/pytest -q` and `.venv/bin/ruff check src tests` after installing the
project's development dependencies. Tests simulate clients and transport; real
in-game rendering and API availability still require checking.

- [Activity log, history and timings](docs/IN_GAME_HISTORY.md)
- [In-game acceptance tests](docs/LIVE_POPUPS.md)
- [Implementation status](docs/IMPLEMENTATION_STATUS.md)
- [Decisions and handoff notes](decisions_i_made.md)
