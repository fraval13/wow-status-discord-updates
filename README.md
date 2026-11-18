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
(see [deploy/SERVER.md](deploy/SERVER.md)). The current version is
`project.version` in `pyproject.toml`; release notes are in `CHANGELOG.md`.
The homepage uses its original still artwork.

Superseded plans and dated audits are kept in [docs/history](docs/history/README.md);
the current source and this README take precedence over them.

## Start sharing

The addon groups the character list by player with
class portraits, adds window themes and a size setting, a first-time setup guide
and Show me around tour, session recaps, Firsts medals, and catches group history
up from friends. It also keeps live updates working when players' clocks disagree,
delivers every update to every member, and stops one player filling the activity
log. Updates and log sync also run during combat, because WoW Forever could
report combat all the time and that stopped both. See `CHANGELOG.md` for what
each release changed.

1. Copy the appropriate `addon/vanilla/WoWStatus`, `addon/tbc/WoWStatus` (TBC Anniversary),
   `addon/retail/WoWStatus` (Retail), or `addon/forever/WoWStatus`
   folder into that client's `Interface/AddOns` directory. Complete ZIPs are in
   `dist/` after packaging. Restart WoW after updating.
   Players can instead install it with the CurseForge app
   (<https://www.curseforge.com/wow/addons/wow-status>), which keeps it updated
   for the games it manages;
   the homepage offers both routes.
2. Open **Options → AddOns → WoW Status → Groups** and add the same group ID as
   your friends. Groups are saved account-wide; character preferences are separate.
3. Click the minimap book to open the **WoW Status** window on its last page (the
   **Activity** tab at first), or use `/wstatus activity`. `/wstatus <page>` opens any
   tab directly; the window remembers its position.
   Right-click the book for Options; drag it to move it around the minimap.
   To keep the minimap clear, untick **Show the minimap button** under
   **Options → AddOns → WoW Status → Notifications**, or type `/wstatus minimap hide`
   (`show` brings it back). The slash commands and the key bindings keep working
   while it is hidden.
4. To invite a friend who does not have the addon yet, right-click their name and
   choose **Share WoW Status** (clients with the modern menu), or type
   `/wstatus share <name>`. It whispers the download link, at most once per person
   per hour, and is never sent automatically.
5. `/wstatus privacy` (also a step in the setup guide) shows in plain words what is
   sent, to whom, what stays on the computer and how to stop. The homepage's
   **What stays private** section says the same; `tests/test_privacy.py` keeps the two
   identical, so change both together whenever what is shared changes.

Keep your group name private: anyone who knows it can join. **Share this group's
name with my other groups** hands it to friends in those groups, who can find it
under **Browse groups**. The first time, a confirmation shows the known online
recipient count; offline members may learn it later. Turning sharing off cannot
take back copies already shared. Removing a group clears its sharing choice.

Click a character card, then scroll below the recent activity and gear to see
their equipped items in a character-sheet layout. Hover a slot for the item's
full tooltip, including its enchant and random suffix. Available combat stats
appear underneath. The timestamp marks the last reported snapshot; stats can
include buffs. A visible unit can supply a live 3D model; offline characters use
their race portrait beside their saved equipment.

Equipment syncs in the background at login and with **Sync now**. Changing gear
quietly tells your group that a newer snapshot is available; friends fetch it
without opening a profile. Online friends can also relay saved gear for an
offline owner, within the group where it was shared. The owner's saved revision
and capture time determine freshness, so an old relay never replaces newer data
and incomplete transfers never replace a complete snapshot.

The character list and Overview show the game's average **equipped** item level
when available; bag gear and required character level are not substituted.
Character cards have more room and a full-width XP bar along the bottom.
**Character details → Equipment and combat stats** controls sharing. Hidden
characters and accounts with character-list sharing off do not send gear.
Both sides need the updated addon for background sync; older clients keep the
original profile-open request. Characters must log in with the gear feature
before their own equipment can be saved. Previously received gear remains
available offline.
See [equipment profiles and live checks](docs/EQUIPMENT_PROFILES.md).

Character profiles, card tooltips and the quests ranking show each character's
latest shared completed-quest count, including saved counts for offline alts.
Changed totals sync quietly at most once every 30 seconds, and with the character
list at login or Sync now. Both players need the updated addon for exact counts;
older clients retain their last 100-quest milestone. Counts marked **tracked**
include only quests recorded by the addon when the game cannot provide completed
quest history. **Character details → Completed quests** controls sharing.

**Leaderboard** (**Toppliste** in Nynorsk) has its own tab in the main window,
alongside Records and Characters, or opens with `/wstatus leaderboard`. Choose a
group and sort by level, deaths, completed quests or played time. **View: Players**
ranks one row per player by their main character, with their alts listed under it;
**View: Characters** is the ranking by character. **Main** picks your main for the
chosen group (one per group, shared with its members); until you choose, your
highest-level shown character is used and is marked as a default, not a choice.
A hidden character is never a main. **Records** holds Firsts,
This week and Fun records.

**Deathless streaks** count the levels and days since a character last died, up to
their newest log entry, worked out from the activity log on each client; nothing
extra is sent. Fun records show
the longest current streak and the longest ever, a character's profile shows its
current one, and the log marks a death that ends a streak of 5 levels or a week.
A streak older than the kept log reads "at least". A character's streak is shown
only while **Character details → Total deaths** is shared. **Notifications →
Deathless streak milestones** (off by default) adds a quiet notice every 5 levels
or week without a death, counted from a death the log has seen.

In **Settings → WoW Status → Characters shown to friends**, untick any of your
saved characters to hide bank alts from everyone's character list, Overview and
leaderboard. Tick them again to restore them. Offline alts can be managed without
logging into them; saved progress and activity history stay intact. Updates reach
online friends automatically and others at the next character-list sync while
someone on your account is online. Everyone needs the updated addon to respect
these settings. The Characters page has a **Character visibility** shortcut.
Played time uses the latest shared total; **Character details → Played time**
controls whether it is shared.

## Language

WoW Status is in English by default. Nynorsk is optional: choose it under
**Notifications → Language** in the settings, or type `/wstatus language nn`
(`/wstatus language en` switches back), then `/reload`. Windows, notifications, the
log, records and all 1,300 captions change; what players send each other stays
English, so friends can use different languages. Diagnostics (`/wstatus popup status`)
and the release notes stay English.

## Diagnostics and bug reports

When WoW Status itself raises a Lua error, it keeps a copy: the last 10 errors from
its own files, each with its stack, the addon version, edition, client build, the
page that was open and the UTC time, saved so they survive a `/reload` and logging
out (a client crash loses errors since the last `/reload`; the game saves only then).
Errors from other addons are ignored, and the game's error frame, BugSack and other
error displays still get every error as before. `/wstatus errors` (or **Options →
Diagnostics**) opens the Diagnostics page: one report to copy into a bug report, with
the memory use, log size and how many groups are joined (a count, never a name).
Group names and character names are replaced by `<group>` and `<name>`. Nothing is
sent anywhere; **Clear errors** empties the list. The report stays English.

## Labs: experimental features

Anything experimental lives on its own page, switched off: `/wstatus labs`, or
**Options → Labs: experimental features**. Each row is one experiment with a name,
a one-line description and a tick, and the page says plainly that an experiment only
changes things for the player who turns it on. **Turn all experiments off** clears
them in one click.

A feature module registers itself with `WoWStatusFeatures.register(id, label,
description)` and asks `WoWStatusFeatures.enabled(id)` before it builds a frame,
registers an event or sends anything, so an experiment that is off leaves no trace.
The toggles are saved account-wide in `WoWStatusDB.labs`, and only a saved `true`
counts: a missing, renamed or malformed value reads as off, and an id that no module
registered can never be switched on. Nothing about an experiment is shared with
other players. The `discord` flag in `Features.lua` stays code-only and is not
listed on the page. A version that ships no experiments says so.

## Compare two characters

**Compare two** on the Leaderboard, or `/wstatus compare [name]`, puts two
characters' numbers side by side: level and XP into it, quests, deaths, monsters
killed, dungeons cleared, mounts, honorable kills, played time — and **played per
level**, which answers whether somebody is faster or just playing more. The better
side of each row is marked and the gap is given as a number; more playing is not
treated as better than less, so that row has no winner.

Everything comes from the roster the client already holds: no new traffic and no new
sharing settings. Only characters you can already see on the Characters page can be
picked, so a hidden bank alt stays out. A value its owner never shared reads *not
shared* rather than `0`, a measure neither of them shared is left out, and each
column says how fresh its data is.

## Controller

With gamepad support switched on in the game's own options, WoW Status windows
can be used with a controller. While a window is open, the **D-pad** moves a gold
highlight between its buttons and fields, **A** presses, **X** right-clicks, **B**
leaves a text field, closes a menu, goes Back or closes the window, **LB/RB** change
page in the main window and the **right stick** scrolls lists. The highlight shows
on the first controller press and hides again when you use the mouse. Other
buttons still reach the game, and in combat the window lets go of the controller
completely. Typing (a group ID) still needs a keyboard or the on-screen keyboard
of a handheld such as the Steam Deck.

Under **Key Bindings → AddOns → WoW Status** you can put *Open or close WoW Status*,
*Open the activity log*, *Dismiss the notification* and *Hold the notification* on
controller or keyboard buttons, and one binding each for the Overview, Characters,
Leaderboard and Records pages: it opens the window on that page and closes it when
that page is already showing. None is bound until you choose, and the page bindings
do nothing in combat. While *Hold the notification* is pressed, the shown
notification stays and does not count down, as it does when the mouse rests on it
(a hold lasts at most a minute). While the window is open, navigation uses the
D-pad, A, B, X, LB and RB, so a page binding on one of those opens its page but
cannot close it; B goes back, then closes the window. With the ConsolePort addon
loaded, WoW Status leaves navigation to ConsolePort. `/wstatus controller off`
turns navigation off (`on` turns it back on);
`/wstatus controller` shows its state.

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
default is the gentle **Wholesome** voice; you can also pick any of the eleven personalities,
Random or **Classic** (the plain GZ!/F/Congrats! texts). Each voice has 300
whispers for every reaction; the button keeps its short label. In Nynorsk,
buttons describe the action: **Vis respekt**, **Ert litt**, **Gratuler**,
**Feir nivået**, **Ynsk god tur** or **Ynsk velkomen**. The whispered message
still comes from the selected reaction voice.

## Announcements

The main settings page controls levels, deaths, first recorded zone visits, each 100 completed
quests, new professions and profession title promotions, first dungeon clears, first raid boss kills, first mount,
reputation ranks, major class unlocks and PvP ranks. **Notifications** holds the popup
settings, with local samples below them. Notifications queue one at a time, six seconds
each by default; **Notification duration** (or `/wstatus popuptime <seconds>`) sets 3 to 20
seconds, or keeps each one until it is dismissed (`0`). **Reduce motion** stops
notifications sliding in, fading out and pulsing their glow: they appear and disappear at
once, big banners included.

**Achievements** (Retail only, off until you tick it) shares a fixed list of
achievements as you earn them: continent exploration, exalted reputation counts,
mount collection counts, profession ranks and dungeon meta achievements (level
achievements are left out, since the level-up is announced already). Only the
achievement's ID is sent; each friend's game supplies the name and icon, and an ID
that is not on the list (or unknown to that client) is ignored. At most five go out
live per session (later ones still reach friends' logs quietly), at most ten per
friend are shown per session, and one already earned on another character of your
account is not announced again. The
list is `WoWStatusAchievements.LIST` in `addon/shared/Achievements.lua`.

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

Dungeon completion requires a supported game signal. Classic-family clients
also recognize known final bosses when no complete encounter roster is available;
intermediate bosses do not count. Earlier unrecorded clears cannot reconstruct
the group's first-clear record. See [dungeon recording](docs/DUNGEON_RECORDING.md)
and [in-game testing and coverage](docs/LIVE_POPUPS.md).

Malformed log data is rejected silently and never enters the activity log. The
group warning popup that earlier versions showed for it was removed after false
alarms in live play. See [invalid log data](docs/history/LOG_GUARD.md) for the
removed warning.

## Activity log and login sync

The scrollable log uses the same icons and colours as popups, with **All**, **Mine**
and **Friends** filters and a **Search** box. Searching looks through the card text,
the character name, the player name and a death's zone and killer, ignoring case and
accents (so `aerie` finds `Ærie Peak`), and it reaches past the day picker into the
whole log. It combines with the type and person filters; **Clear** and **Show all**
end it, and nothing about a search is remembered after a `/reload`. Individual quest turn-ins are omitted; only hundred-quest
achievements appear. Detailed profession and equipment-change activity stays
private. Eligible announcements and requested equipment snapshots are exchanged
with group members according to the character's sharing settings.

At login, the addon greets available group members and both sides automatically
exchange missing announcement IDs. An already-online friend also recovers saved
entries from the arriving player. There is no periodic polling after the login
exchange completes. **Sync now** on the Characters page repeats it on request (once a
minute): it resends your character list, asks for everyone else's and catches up the
log, and refreshes group equipment, still limited to one log catch-up per member every ten minutes. Recovery adds quiet log cards rather
than replaying old popups, and duplicate IDs do not create duplicate entries.

Someone with a saved copy must be online. Sync covers up to seven days after your
group join time, bounded by the retained log: 2,000 of your own entries (at most
1,000 of them private activity) and, separately, 2,000 received entries, so
received entries never push out your own. Each login session takes at most 300
caught-up entries from one member, at most 100 of them about any one other
member; the rest come from other members or the next login. Realm/faction/whisper
restrictions still apply.
Friends should update to the same release for login sync and armor metadata.

## Taking part

[`CONTRIBUTING.md`](CONTRIBUTING.md) says how to report a bug, how to run the
checks and what a pull request has to get right (all four editions, controller
support, Nynorsk strings, no version bump). Security problems go through
[`SECURITY.md`](SECURITY.md) privately, never a public issue. A group ID is a
shared secret: never paste a real one into an issue, a log or a screenshot.

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
- [What a login sends](docs/LOGIN_BURST.md)
- [CurseForge listing and automatic uploads](docs/CURSEFORGE.md)
- [Historical plans and audits](docs/history/README.md)
