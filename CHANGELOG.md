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

- Armor headings name the piece: RARE RING EQUIPPED!, EPIC TRINKET EQUIPPED! (SJELDAN RING PÅ! in Nynorsk)
- Click a character card for their profile: stats, level-ups, recent activity and armor firsts
- Invite a friend to one of your groups from their profile; they get a Join / Decline popup
- Records: This week shows the week's highlights per group, with earlier weeks one click away
- Records: Fun records, only for remarkable feats like the most dangerous zone or the best evening
- Friends confirm live updates; one that never arrives is sent again, and the card says not reached
- Quiet mode (off by default): hold notifications in battlegrounds, raids or dungeons
- Pick a sound for level-ups, deaths, armor, new zones and the rest, or none
- The minimap button's tooltip shows who is online and a friend's latest news
- Honorable kills, dungeons cleared and mounts on character cards and profiles
- Armor tooltips show the full item with its suffix and enchant

## 1.24.0

- Legg til skillen git-commit for commit-meldingar

## 1.23.0

- The Overview calls your gold Current (Noverande in Nynorsk), next to Earned

## 1.22.0

- Caption personalities: pick a voice for the line under each notification in Notifications settings
- New default Random: every notification draws its caption from a random personality, Classic included
- Nine new personalities with 300 lines per event, from Wholesome and Epic bard to Jealous friend and Drama queen
- /wstatus personality <name> switches from chat; captions already in your log keep their wording

## 1.21.0

- Long activity-log lines end with "..." instead of wrapping; hover a card to read all of it (no event ID)
- In Nynorsk, GZ!, F and new-zone buttons pick one of 20 lines at random, and whisper what they show

## 1.20.0

- The day calendar and the filter menus are no longer hidden behind the window
- The day button simply says Today, Yesterday, a date or All days

## 1.19.0

- A new notification ignores clicks for 1.5 seconds; its buttons are greyed out and count down meanwhile
- Missed the reaction buttons? A friend's log card offers them for a minute after the notification
- Clicking a reaction button sends it and closes the notification
- Browse groups: tick Listed on a group to let friends in your other groups see and join it
- Settings opened in their own window (for example in combat) use your window theme too

## 1.18.0

- The activity log opens on today; a Day button opens a calendar to pick another day or all days
- Clicking a notification only dismisses it; it no longer opens the activity log
- In Nynorsk, F and Git Good are long lines too; long reaction buttons get their own row under the text
- Congrats say what for: "Congrats on the new gear!", "Congrats on level 30!" and more, also in Nynorsk
- Armor updates show the item's icon and coloured name; hover the notification or log card for its stats

## 1.17.0

- Leaderboard per group on the Records page: level, deaths and quests, with sorting
- Deaths show where you died, for you and friends; on Classic Era and TBC also what killed you
- Your log cards show who reacted with GZ!, F or Congrats!
- Filter the activity log by type and by person
- You are told when a friend runs a newer version of WoW Status
- Friends' levels stay current: log level-ups update the list, and Sync now looks a friend up with /who
- Gold, gold earned, kills and played time on the Overview and on character cards (hover for all)
- WoW Forever: friends' character lists are accepted again, so nobody stays in Not announced
- In Nynorsk, GZ! is now a full wish: Eg ynskjer deg hjarteleg til lukke med det nye nivået!
- The "Preview toasts" settings page is now called Notifications, with its settings first and the previews below them

## 1.16.0

- Optional Nynorsk: windows, notifications, the log, records and all captions, in settings or /wstatus language nn

## 1.15.0

- New default look: a solid dark brown window with a gold border, like the achievement window
- Notifications use the window theme by default (untick it in the notification settings)

## 1.14.0

- WoW Forever: friends on other internal realms are no longer listed twice on the Characters page

## 1.13.0

- WoW Forever: your full name is known at login, so friends get your character list right away

## 1.12.0

- Level records count levels reached before WoW Status or before joining, so late joiners no longer take them
- Records are kept per group, with a tab for each group on the Records page
- The floating status line can always be dragged; dragging it unpins it from the quest tracker
- Characters page: a section per group that you can open and close
- A friend in several of your groups gets each update once instead of once per group
- Overview: Your group lists everyone online with a scrollbar, and Since you were last here fits its lines

## 1.11.0

- Sync now on the Characters page refreshes lists and the log with everyone online, once a minute
- A changed player name reaches friends who are online straight away
- Everyone seen in your groups is listed on the Characters page, also friends on old versions
- The first dungeon clear icon shows a skull instead of a black square
- Character cards end with level and total deaths instead of the latest event
- WoW Forever: character lists are sent with full names, so fewer friends end up under Not announced
- The Characters page shows each friend's addon version in small grey text
- Notifications have reaction buttons that whisper the friend: GZ!, F or Git Good, Congrats!, Welcome! and Enjoy <zone>!
- A notification stays on screen while your mouse is over it
- Friends show with their player name too, like Unshaved Brittlebeard (Frank), in popups, the log and the overview

## 1.10.0

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
