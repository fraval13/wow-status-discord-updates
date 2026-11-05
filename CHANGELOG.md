# What's New

Player-facing release notes. The newest section is shown once in game after an
update (`/wstatus news` opens it again) and fills the homepage release panel.
`python scripts/whats_new.py` regenerates `addon/shared/WhatsNewData.lua` from this
file; run `python scripts/sync_addons.py` afterwards.

Rules: one `## <version>` heading per release, newest first, matching
`pyproject.toml` (the release pull request adds it). Each note is one `- ` line of
plain text, at most 120 characters, without `|` or markup. An optional
`## Unreleased` section collects notes for the next release and is not shipped.

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
