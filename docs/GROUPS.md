# Add and remove account groups directly in WoW

No invitation link or Discord `/link` code is required for the group-ID flow.
Open **Options → AddOns → WoW Status → Groups**, use **Groups** in `/wstatus`, or type:

```text
/wstatus groups
```

Enter your name once (optional) and click **Save name**. Type one group ID into
the **Group ID** input and click **Add** (or press Enter). Repeat to add another.
Each selected group appears in a list with its own **Remove** button. Add and
Remove save immediately for every character on this account. For example, add
these two IDs separately:

```text
Weekend Crew
Old friends #2
```

The input accepts ordinary printable text, spaces, punctuation and Unicode, up to
80 characters per ID and eight groups per character. Leading/trailing whitespace
is trimmed. IDs ignore capitalization: `Weekend Crew` and `weekend crew` are the same.
A shared Unicode case-fold table keeps the game and service consistent. An empty
list means no group destination. Commas are ordinary characters inside a name;
add each group separately. Duplicate names are rejected without adding a second row.

Your two IDs send your selected character to both destinations; another friend
can enter only one. Group IDs and your name are saved once per WoW account and apply to all its
characters, including new characters. Character sharing, profile fields, collection
and announcement checkboxes remain independent for each character. New characters
default to all those sharing checkboxes enabled; saved character choices are preserved.
Account-wide means this client’s account SavedVariables file, not automatic syncing
between computers or between Vanilla and Forever installations. The name labels your characters
in both selected groups and is not verified against a Discord account. Without a
name, the service assigns a stable generic friend label for that installation.
Use the addon’s **Mark as my main** button for main/alt labels in ID-joined groups.

The companion needs the shared HTTPS service address once per installation. It
reads the chosen IDs on `/reload` or logout, enrolls automatically in those groups,
and saves private per-group upload credentials. Bot tokens are never entered into
WoW or sent to the companion. Keep a private backup of companion credentials:
losing them loses the installation’s ability to update/delete its existing group
characters and requires operator assistance to restore or reset ownership.

## How you connect each ID to Discord

For each group, run a separate service instance with its own database and Discord
guild/channel configuration. You can use separate bot applications, or the same bot invited to two different
Discord servers. Each instance ignores the other server’s interactions. Keep the
guild IDs distinct if sharing a bot; multiple group instances in the same guild
need a separate channel-aware command router and are not enabled by this setup. The destination
is selected by operator configuration; addon users never supply arbitrary webhook
URLs or Discord channel IDs in their uploads.

For example, create two environment files from `.env.example`:

```text
# Group one
DISCORD_GROUP_NAME="Weekend Crew"
DISCORD_BOT_TOKEN=YOUR_FIRST_BOT_TOKEN
DISCORD_GUILD_ID=FIRST_DISCORD_SERVER_ID
DISCORD_CHANNEL_ID=FIRST_DISCORD_CHANNEL_ID
WOW_STATUS_PORT=8081
```

```text
# Group two
DISCORD_GROUP_NAME="Old friends #2"
DISCORD_BOT_TOKEN=YOUR_SECOND_BOT_TOKEN
DISCORD_GUILD_ID=SECOND_DISCORD_SERVER_ID
DISCORD_CHANNEL_ID=SECOND_DISCORD_CHANNEL_ID
WOW_STATUS_PORT=8082
```

The program does not automatically load `.env`; use systemd EnvironmentFile or set
variables in each service’s environment. With those variables set separately:

```sh
wow-status serve --db state/crew-one/service.sqlite3 --port 8081 --discord
wow-status serve --db state/crew-two/service.sqlite3 --port 8082 --discord
```

Alternatively specify `--group "Weekend Crew"` explicitly. Set up the HTTPS gateway
using [Caddyfile.groups.example](../deploy/Caddyfile.groups.example). Its two routes
forward to the two separate instances. Obtain the internal route keys at home:

```sh
wow-status group-key "Weekend Crew"
wow-status group-key "Old friends #2"
```

Only the host operator handles those keys; friends enter the original free text
in WoW. Addon and companion derive the same compact key for URL paths and popup
channel names. This deterministic key is not a password hash. Names are also
checked by the receiving service, and reusing a database for a different group is
rejected. Unknown group IDs have no fallback destination and do not send anywhere.
Changing a name beyond capitalization creates a different ID; changing its capitalization does not.

Each instance’s archives and SQLite data remain separate. JSON records contain
only that destination’s group name/key, not the person’s complete group list.
No group receives another group’s roster, event targets, or recaps. Shared members
are intentionally copied to both only when their character selects both IDs.

## Joining without links means shared-ID access

Anyone who knows an ID and service address can enroll an uploader in that group.
This is the requested open-ID membership model, not verified Discord membership.
Use distinctive names and keep them within the relevant friend group. Private
installation tokens protect existing character ownership after enrollment; knowing
a group name does not reveal another installation’s token or grant its privacy
controls. Telemetry is still player-reported and not anti-cheat evidence.

You can map a known ID to a specific bot/chat. An unknown random name does not
create a Discord bot or automatically discover a destination. The operator must
configure that name first.

## Event history and leaving

Existing per-character group lists are merged once into the account list on upgrade
(up to eight groups, with a visible chat warning if old lists exceed that limit).
Existing membership timestamps remain unchanged; newly inherited groups get a new
join boundary so earlier history is not backfilled. Removing a group updates every
saved character in this account, including characters currently offline.

Only events captured for a selected ID at the time they happened are eligible for
that group. New groups receive current selected status, a consented enrollment
introduction, and future events; your earlier private logs are not backfilled.
Local full history remains available for your own graph under its existing sharing
controls. Level timeline points are restricted to the group’s observation window.

Removing an ID immediately stops its in-game broadcasts and popup acceptance.
After `/reload` and companion upload, a withdrawal hides that character and scrubs
its remote shared event/snapshot content in the removed group. Other selected
groups continue. If offline, server changes remain pending until the companion can
reach that group; keep its credentials until the withdrawal succeeds. Already
posted Discord messages remain. An initial in-flight send can still finish.

The companion remembers attempted memberships before sending, so a restart after
an ambiguous response still knows which destinations may need withdrawal. One
unreachable selected group does not authorize sending to another destination and
does not prevent attempts to the other selected groups.

For immediate remote privacy, stop uploading and choose the group in the companion:
**Pause group**, **Resume group**, or **Delete my group data**. Those controls affect
only your installation’s data in that group, not the other groups or other people.
Pause keeps the private credential for explicit resume; delete revokes it. Resume
requires a current export, and a restart watermark prevents automatic replay of
pre-pause/deletion history. After deleting, explicitly resume and export to enroll
again. Preserve local files/backups and Discord posts according to their own
removal policy.

CLI equivalents (use the internal key printed by `group-key`):

```sh
wow-status group-privacy --group GROUP_KEY pause
wow-status group-privacy --group GROUP_KEY resume
wow-status group-privacy --group GROUP_KEY delete
```

`/privacy`, `/nickname`, and `/main` in Discord still apply to optional legacy
Discord-linked installations. They cannot identify an ID-only owner as the current
Discord user; use the companion/addon controls described here. Advanced legacy
users can explicitly select `/wstatus groups legacy` with their direct-service
credentials. Saving an account group list switches all saved characters back to ID routing; there is no implicit
legacy fallback for an empty or unknown group list. `/roster`, profiles
and group announcements show ID-joined shared characters normally.

## Popup groups

The same list selects separate in-game custom channels. The addon attempts to join
them; actual client restrictions still need home validation. Enable reception with
`/wstatus popup on` and sending with `/wstatus popup send on` if desired. The list
itself is the group membership filter; you do not have to trust each alt separately.
Local optional friend labels are still possible. A packet received through both
selected groups produces one popup, not two. No peer events become your own progress.

Group channel names use compact keys, allowing spaces/punctuation in the entered
ID without putting those characters into channel names. Messages are still visible
ordinary channel messages; knowing a group name is not proof of Discord membership.
With an empty group list there is no default channel. The previous manually chosen
channel remains available only through explicit `popup channel ...` legacy setup.

## Home validation required

No application, addon, service or tests have run on the work computer. Authored
checks cover free-text key agreement between Lua/Python, one/two/zero group lists,
scoped event history, wrong-group headers/tokens, automatic enrollment, privacy,
and popup isolation. At home validate two independent Discord destinations, a
member of both groups, group removal while offline, partial network failures,
no-history-backfill, and the relevant in-game channel behavior before inviting friends.

The configured groups for this server are `ronkalot` and `navsquad`. Case variants
route to the same destination. Their Discord credentials/channel IDs can be supplied
later; group services stay separate.
