# Forever compatibility audit — 29 October 2026

See the [4 November Forever/Retail check](CLIENT_COMPATIBILITY.md) for newer
source revisions, the dungeon API fix and current validation results.

Forever uses the modern/Mainline API family. It is not a Classic Era client with
an updated version label, nor does that make it interchangeable with Retail.
Our separate Forever addon targets interface 16001 and the Camelot project ID.

The [guide supplied by the user](https://classicwowforever.com/guides/wow-forever-addons-api-compatibility/)
was the starting point. Code/signatures were checked against Blizzard's client UI
and generated API documentation mirrored at Gethe/wow-ui-source, pinned to
`ca8368f2f2380cbe696854f7f2646387c278a61b` on the `forever` branch. The older
[captured client API](https://github.com/Thunderz96/forever-addon-kit/blob/main/data/forever_api.json)
was used only as an additional early-beta comparison; it cannot establish current
availability or in-game behavior.

| Area | Evidence and WoW Status behavior |
| --- | --- |
| Client detection | The client's [Camelot constants](https://github.com/Gethe/wow-ui-source/blob/ca8368f2f2380cbe696854f7f2646387c278a61b/Interface/AddOns/Blizzard_ProjectConstants/Camelot/ProjectConstants.lua) define project ID 18. Our existing adapter handles that, requires the 160xx interface family, and retains the earlier Mainline-project fallback. Retail and Classic Era remain separate. |
| Items and first equips | Uses `C_Item.GetItemInfo` / `GetItemInfoInstant`, with public-value checks and deferred item-data resolution. Signatures checked against [ItemDocumentation](https://github.com/Gethe/wow-ui-source/blob/ca8368f2f2380cbe696854f7f2646387c278a61b/Interface/AddOns/Blizzard_APIDocumentationGenerated/ItemDocumentation.lua). |
| Professions | Added `C_SkillInfo.GetSkillLineInfoByID`, reading its structure fields `name`, `rank`, `maxRank`, `isHeader`. Queries known profession skill IDs independently of collapsed headers. The previous path relied on globals; some early snapshots still exported profession globals, so their presence cannot be assumed either way. [SkillInfoDocumentation](https://github.com/Gethe/wow-ui-source/blob/ca8368f2f2380cbe696854f7f2646387c278a61b/Interface/AddOns/Blizzard_APIDocumentationGenerated/SkillInfoDocumentation.lua) is the signature source. |
| PvP ranks | Added Forever's rank-points faction 2800 through `C_MajorFactions.GetMajorFactionProgressionInfo`. Its `renownLevel` and localized rank text follow the client's own [PVPRankFrame](https://github.com/Gethe/wow-ui-source/blob/ca8368f2f2380cbe696854f7f2646387c278a61b/Interface/AddOns/Blizzard_UIPanels_Game/Camelot/PVPRankFrame.lua). Season changes establish a quiet baseline. The old Classic rank globals are retained for the Vanilla adapter only. |
| Group messages and catch-up | Uses `C_ChatInfo` addon whispers and its channel roster. Added the explicit realm-wide outgoing-message restriction check alongside messaging lockdown. [ChatInfoDocumentation](https://github.com/Gethe/wow-ui-source/blob/ca8368f2f2380cbe696854f7f2646387c278a61b/Interface/AddOns/Blizzard_APIDocumentationGenerated/ChatInfoDocumentation.lua) describes both controls. Existing throttling and secret-value handling remain. |
| Quest totals | Existing `C_QuestLog.GetAllCompletedQuestIDs` matches [QuestLogDocumentation](https://github.com/Gethe/wow-ui-source/blob/ca8368f2f2380cbe696854f7f2646387c278a61b/Interface/AddOns/Blizzard_APIDocumentationGenerated/QuestLogDocumentation.lua). Individual observations and hundred-quest milestones remain separate. |
| Major spell unlocks | Existing `C_Spell` and `C_SpellBook.IsSpellKnown` fallbacks match the modern [SpellBook documentation](https://github.com/Gethe/wow-ui-source/blob/ca8368f2f2380cbe696854f7f2646387c278a61b/Interface/AddOns/Blizzard_APIDocumentationGenerated/SpellBookDocumentation.lua). The curated gameplay spell IDs still require live Forever checks. |
| UI and restricted values | Uses the modern Settings categories when available. Secret/unreadable identity and values are omitted or deferred; they are not converted into strings or fabricated replacement values. Unknown optional events are guarded. |

## What this establishes

The basic design fits Forever: friends' progress, an activity log, notifications
and ordinary out-of-restriction addon messaging. The mock tests exercise client
detection, restricted identity, modern item calls, modern-only skill calls, PvP
rank changes/season resets and realm/chat restrictions. The character-switch
history fix applies to both addon editions.

This is an API/source audit and mocked testing, not live Forever acceptance. A
function's existence is not proof that its return value is available in every
situation. Communication must obey the client's realm/faction/instance/security
rules. A group ID cannot override them. Dungeon completion still requires a
supported authoritative completion signal. Vanilla and Forever intentionally do
not share messages with each other.

## Live check before calling Forever verified

1. Install the Forever ZIP in the correct client and verify it loads at login.
2. With two subscribed players, set the same group ID; test a level and first
   eligible armor equip out in the world. Confirm the remote popup and log.
3. Learn a profession, then a higher title; confirm its skill snapshot and events.
4. Test a PvP rank change; existing ranks should stay quiet on login.
5. Log out normally, restart and verify groups, settings and history persisted.
6. Switch one player to a new character. Confirm retained shared history and
   missing entries catch up, without replaying old notifications.
7. Compare allowed world/instance/combat behavior and `/wstatus popup status`.
   A blocked restriction state is not an invitation to bypass it.
