# WoW Status — in-game groups, optional Discord summaries

Friends install **only the WoW addon**, enter the same group ID, and receive each
other's updates inside the game. No desktop app, account, Discord bot or web
service is needed for in-game sharing.

Discord is a separate opt-in. Its optional companion uploads saved exports, and
the bot posts **one tidy character status card when meaningful progress changes**.
A reload by itself creates no notification.

## Start with the addon

1. Install `addon/vanilla/WoWStatus` into your Classic Era `Interface/AddOns`
   directory. Use `addon/forever/WoWStatus` for Forever instead. Install just one
   edition per client and restart WoW after installation.
2. Open **Options → AddOns → WoW Status**, or type `/wstatus`.
3. Open **Groups** (`/wstatus groups`). Enter a group ID and press **Add**. Give
   friends the same ID. It can be a name such as `navsquad`; in-game groups do not
   require registration on a server.
4. Joining a group automatically enables sending and receiving; there are no
   additional send/receive switches. Choose which events to collect locally and
   share in WoW. Each character keeps its own event and character privacy choices.
5. Open **Group activity** (`/wstatus activity`) to see received updates. Friends'
   updates appear as animated on-screen toasts with a large icon, event colours,
   a pulsing glow and text. They appear near the upper-middle of the screen for
   six seconds. Level-ups include levels 2, 3, etc. **Preview toast** in settings
   (`/wstatus popup test`) shows the style without sending a message.

Groups and your optional name are account-wide. **Add** and **Remove** save
immediately and affect all saved characters in that account. No `/reload` is
needed to apply in-game group changes. Local history is saved by the game on
reload/logout and remains available through `/wstatus logs`, `graph` and `times`.

The in-game messages cover level-ups, consented introductions, selected loot,
equipment changes, deaths, quest completions, profession skill-ups, zones and
player-entered LFG messages. Login/logout session notices are not generated.
They contain compact event details, not a full remote inventory or talent profile.
Loot uses the selected rarity threshold; level-up notifications do not use
Discord's old milestone interval.

## What to expect in WoW

The addon joins a custom channel derived from each group ID to discover its
members, then sends **addon whispers** to those members. It does not attempt
hidden addon messages over custom channels, which Classic restricts. A recipient
needs the addon and matching group ID to display the update.

Both players must be online and able to communicate within WoW's channel/whisper
rules. Do not assume cross-faction, cross-realm or cross-edition delivery. There
is no offline server mailbox or replay of missed in-game messages. The last 200
received updates are kept locally; activity from removed groups is cleared.
A shared ID is a membership choice, not verified identity or a password.

`/wstatus popup status` shows channel membership, discovered peers and the last
send attempt. A successful API call is not a delivery receipt. A local preview is
available with `/wstatus popup test`; previews and synthetic level tests are not
sent as real progress.

**Actual two-player validation is still required on the current client.** Tests
simulate both clients, but cannot establish live channel discovery, restrictions
or delivery. See [in-game testing](docs/LIVE_POPUPS.md).

## Optional Discord sharing

Leave it off if you only want in-game updates. Friends do not need Python or the
companion for the main addon functionality.

To also share one character in Discord:

1. Open **Options → AddOns → WoW Status → Discord (optional)**, or `/wstatus discord`.
2. Check **Also share this character to Discord** and choose the event categories.
   This is off by default, including when upgrading from the old workflow.
3. Install the optional Python companion on that computer (`python -m pip install
   -e .` from this repository) and run `wow-status desktop`.
4. Save the shared service URL, select only this account's
   `WTF/Account/.../SavedVariables/WoWStatus.lua`, and click **Start uploading**.
5. Play normally. `/reload`, logout or relog writes the saved data. The running
   companion uploads that export and the server posts an updated card if there is new permitted progress. Re-uploading it creates no duplicate summary; an export
   with no new announceable events is silent.

The card shows character name, class, level, faction, optional player name, XP
percentage, cumulative recorded deaths, completed quests, location and profession
ranks. Counts are totals, not "since last upload" deltas. Class/faction/profession
emojis are used when uploaded; the [emoji pack](assets/discord-emojis/README.md)
contains 29 matching files.

Open **Options → AddOns → WoW Status → Notification previews**, or
`/wstatus previews`, to try every notification and a local example status card.
Previews never send data or modify your character. Version 0.10.0 adds Lua files:
restart WoW completely and restart the optional companion after updating.
Large histories upload in chunks, but the bot waits for the complete account
export and combines the chunks and characters into one message. Summaries use
counts rather than dumping every item/event. Older unsent activity is folded into
the next completed summary. Ambiguous Discord sends are held for operator review
rather than automatically repeated. Automatic daily/weekly reports remain a
legacy mode; summary-mode characters do not additionally receive those reports.

Opting in starts a new sharing window; earlier private local events are not
backfilled. Turning Discord off does not stop in-game sharing. Export and upload
the opt-out to pause previously uploaded data, or use the companion's group
privacy controls for an immediate remote pause. Old Discord posts remain.

The deployed address is `https://wow.frankvalde.com`, with configured Discord
destinations `ronkalot` and `navsquad`. Other names work for in-game sharing but
need an operator mapping if you also want a Discord destination.

## Development and operations

Python 3.11+ is needed only for the optional uploader/service and development.
Both addon editions ship as self-contained folders. Shared Lua changes are copied
into both with `python scripts/sync_addons.py`.

```sh
python -m pip install -e ".[dev]"
python -m pytest -q
```

GitHub checks build Vanilla and Forever addon ZIPs and deploy the isolated service
instances. Server deployment never updates the addon folder on a friend's PC.

- [Decisions, validation and handoff](decisions_i_made.md)
- [Group IDs and optional Discord routing](docs/GROUPS.md)
- [Standalone addon editions](docs/ADDON_EDITIONS.md)
- [Local logs, graph and level times](docs/IN_GAME_HISTORY.md)
- [Optional server and pipeline](deploy/SERVER.md)
- [Optional JSON exports and archives](docs/JSON_FORMAT.md)
- [Remaining feature scope](docs/IMPLEMENTATION_STATUS.md)

No OpenAI key is needed. Character data is not sent to OpenAI. Telemetry is
player-reported, not Battle.net ownership verification. Dungeon completion,
quest chains, talents, profession recipe collection, mounts/pets, reputation and PvP
remain separate unimplemented collectors; they are not inferred from zone entry.

Milestones and voluntary discoveries are available under **WoW Status → Milestones**
(`/wstatus milestones`). All notification types can be tried under **Notification
previews**. See [in-game sharing](docs/LIVE_POPUPS.md) for detection and fallback
behavior. Dungeon invitations are not included.
