# What's New

Player-facing release notes. The newest section is shown once in game after an
update (`/wstatus news` opens it again) and fills the homepage release panel.
`python scripts/whats_new.py` regenerates `addon/shared/WhatsNewData.lua` from this
file; run `python scripts/sync_addons.py` afterwards.

Rules: one `## <version>` heading per release, newest first, matching
`pyproject.toml` (the pipeline prepares it on main). Each note is one `- ` line of
plain text, at most 120 characters, without `|` or markup. An optional
`## Unreleased` section collects notes for the next release and is not shipped.

## Unreleased

- The WoW Status window closes with an X in the top right corner
- Characters page: friends on older versions get their portrait, race and class from the game instead of a question mark

## 1.9.0

- The log no longer gets a card for every profession skill point; learning and promotions still show
- The First death record is now called First in the group to die, so it no longer looks like your first death
- Choose the notification size as a percentage in the notification settings (100% is the default)
- Zones you had already explored before installing are no longer announced as first visits
- The "is a really bad boy" warning is gone; invalid data is still ignored quietly

## 1.8.0

- New look: bordered cards, round level badges and XP bars on the Characters, Records, Activity and Overview pages
- Click a character to see only that character's activity
- Character cards show each friend's XP progress and the groups you share with them
- The Overview shows your own status, who is online in your group and the latest records

## 1.7.0

- WoW Forever: characters and log entries with only a first name, left by older versions, are removed
- No more "No player named ... is currently playing" messages from the addon's own whispers

## 1.6.0

- WoW Forever: the character list uses full names, and first-name-only entries like Edith or Unshaved are gone

## 1.5.0

- Report CurseForge errors clearly without echoing the token (#114)

## 1.4.0

- WoW Forever: your own updates no longer show up twice, once under your first name and once under your full name

## 1.3.0

- You no longer whisper yourself ("No player named ...") or count yourself as online in WoW Forever

## 1.2.0

- WoW Forever: updates, log sync and friend lists are sent again instead of waiting forever
- The online count no longer includes group members who have logged off

## 1.1.0

- Groups retired in 0.16.0 can be joined again; re-add the group name your friends use
- A refused group ID now says why, in chat and right under the input box

## 1.0.0

- WoW Status 1.0 is out, and new versions are now also published on CurseForge
- On Retail, the log now shows your earlier level-ups, dated from your level achievements
- Death announcements on Retail show your lifetime death total instead of deaths since installing
- The log now shows which level a character was at when you started using WoW Status
- Typing /wstatus during combat opens the addon's own settings window

## 0.17.0

- Recover history from before installation where the client allows it (#110)

## 0.16.0

- Previously exposed groups are retired; ask the group owner privately for the replacement name
- Old group channels are left automatically and cannot be re-added after updating
- Private gateway routing files keep restricted permissions when the website is published

## 0.15.0

- First successful raid boss kills and epic mount items earn big banners and Firsts medals
- Optional session recap sharing, off by default, with private activity choices respected
- Better Classic profession and mount detection, channel selection, and settings compatibility
- Each main update now prepares one minor release and publishes matching website downloads

## 0.14.14

- Character list grouped by player, with class portraits
- New themes and a size setting for the WoW Status windows
- First-time setup guide and a Show me around tour
- Session recaps are written to the activity log
- Firsts medals for the first player in the group to reach a milestone
- Group history now catches up from friends, including events from before you joined
- /wstatus minimap reports the button position, and the button sits further out
- Live updates keep working when players computer clocks disagree
- Every update reaches every group member, and throttled whispers are retried
- One player can no longer fill the activity log and push out your own entries
- Popups only accept text from known group members

## 0.14.13

- New WoW Status window with tabs: Overview, Activity and more
- Overview shows what your group did since you were last here
- Big banners for every 10th level and maximum level
- Click a popup to open it in the activity log; popups can be moved
- Optional group status line under the quest tracker
- Optional screenshots on level-up and first dungeon clear
- Share WoW Status with a friend: /wstatus share <name>
- This What's New page, shown once after each update (/wstatus news)
- Updates and log sync keep running during combat

## 0.14.12

- Retail and Forever minimap buttons sit in the right place
- Dungeon clears use the game's completion data correctly
- Clearer wording when you join a group
- Group warnings for invalid log data
- Removed group channels are left after /reload
- A death counts once when you release your spirit
