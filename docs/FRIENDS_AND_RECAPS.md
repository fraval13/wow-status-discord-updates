# Your Discord gang: people, characters and shared highlights

Your Discord identity links your characters together. Nobody needs to type a real
name into the addon. Everybody in the configured server can view the shared roster
and announcements; grouping adds context rather than separating your friends.

## How names work

1. Invoke `/link` in Discord. The bot remembers your Discord user ID and current
   server display name from that interaction.
2. Link your companion with the private code. Its uploads belong to that Discord ID.
3. Every opted-in character uploaded through that installation belongs to you.
4. Optionally use `/nickname name:Frank` if you prefer that name in updates.
5. `/nickname reset:True` switches back to your remembered Discord display name.

A custom nickname takes priority. Display names refresh when you use the bot's
commands; this version does not watch ordinary messages or nickname-change events.
A nickname is just a display label; matching names never grants character access.
The Discord user ID controls ownership. Multiple people may have the same nickname.
All real installations should link through Discord; local test owners without a
remembered name appear as "Linked friend".

For example, the group can see:

```text
Frank
  Thora — Main · level 24 Warrior
  Eldrin — Alt · level 12 Mage
Another friend
  Brunna — Main · level 22 Priest
```

Announcements identify the owner: "Frank’s Thora reached level 30!" Mention parsing
is disabled even if a nickname contains @everyone or another mention-like string.

## Main characters and alts

Use `/main name:Thora realm:YOUR_REALM` to choose your own main. Specify client too
if needed. This only accepts one of your linked characters; your others become alts.
The server enforces at most one main per friend. Choose a different `/main` later
to change it. Main/alt labels appear in profiles, roster, recaps and character JSON.

The addon also has a **Mark as my main** button. Its selection applies after export
and upload. A main explicitly selected in Discord takes priority over addon choices,
so older account exports cannot unexpectedly change it back.

## Roster and profession labels

`/roster` and `/characters` list the gang grouped by friend, with mains first and
last-upload times in Europe/Oslo. Large rosters paginate without dropping characters.
Character profiles and activities still resolve by name, realm and client.

For initial Classic testing, profession names can be **player-entered** rather than
assuming unvalidated skill APIs. Enable the profession profile checkbox, then use:

```text
/wstatus professions Alchemy, Herbalism
```

Export with `/reload` and upload. Those labels appear in the roster and are stored
with `source: "player_entered"`; they do not claim verified skill ranks or recipes.
Leave profession sharing unchecked to omit and scrub them. Automatic profession
skill/rank/recipe collection still needs actual client validation.

## One group recap

At **00:05 Europe/Oslo**, the daily report covers the previous Norwegian calendar
day. It combines characters under friend headings, puts brief highlights first,
and splits into bounded continuation messages only when the roster is too large.
Delivery state stays per character, so an interrupted multi-message report can be
reviewed without blindly replaying all characters. Everyone's full consented JSON
history remains separate and detailed.

Each character section includes its main/alt label, available level/class, recorded
event counts, an item highlight where available, and last-known export time. It
includes characters with no recorded activity without claiming they were offline.
A level or gear change inferred by comparing snapshots is explicitly marked as a
snapshot comparison. Actual level-up timestamps remain separate event records.
Synthetic `/wstatus test` events are labeled [TEST] and excluded from real daily and
weekly highlights while remaining in the JSON archive.

On **Monday at 00:05 Europe/Oslo**, a weekly adventures report covers the preceding
Monday–Sunday. It celebrates progress, introductions and item activity; it does not
rank friends by playtime. The same privacy, pagination and uncertain-send handling
applies. Daily/weekly reports contain no OpenAI calls.

## Group noise settings

Someone with **Manage Server** can use:

```text
/settings mode:celebrations level_interval:10 loot_quality:4
```

- `celebrations` (default): selected introductions, level milestones and notable
  loot can post immediately. Other collected activity appears in recaps.
- `daily_only`: disable immediate announcements; retain daily and weekly recaps.
- `all`: allow all the immediate categories each player has explicitly enabled.

The group's level interval and minimum loot quality combine conservatively with
each player's filters: both must allow a message. These settings never enable
private collection or make hidden fields visible. Tightening a policy cancels
queued messages that no longer qualify; relaxing it affects new events and does
not replay old celebrations. The command sets interval/quality to the values shown
(default 10 and 4 if omitted). Collection still retains every enabled event for
JSON and recap use, independently of those immediate posting filters.

## Friendlier companion

At home, after installing the Python package, run:

```sh
wow-status desktop
```

The optional desktop window lets you enter the service URL, paste a private `/link`
code, select only `WoWStatus.lua`, and start/stop uploading. It shows connection
status plus the latest export and upload timestamps in Norwegian time. It uses the
same private credentials/state as the command-line companion, and a lock prevents
both uploaders from using that state simultaneously. Tk support is required; use
the command line if your Python distribution does not include it. No compiled,
standalone installer is included in this version.

Stopping the desktop uploader does not delete server data. Use `/privacy` in Discord
for server-side pause/revocation or deletion. Uploaded histories, aliases and labels
are removed from the managed archive on deletion; old Discord posts and separately
copied exports/backups need separate removal.

## Context for later features

JSON now includes evidence/source labels, friend ownership, main/alt roles, client
build/interface metadata, and structured item references for joining loot to gear.
Snapshot comparisons never fabricate exact event times. Party/dungeon attribution
remains disabled until reliable client-specific evidence and sharing controls can
be validated at home. This version does not upload unconsenting party members.

All changes are written but untested. No application, GUI or tests were run on the
work computer. Use the home checklist and authored tests before group rollout.
