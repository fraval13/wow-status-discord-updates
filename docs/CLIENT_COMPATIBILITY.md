# Forever and Retail compatibility check — 4 November 2026

Both use the modern/Mainline API family, with edition-specific differences.
They should keep separate adapters and packages. This check covers source/API
contracts and simulated clients; live-game acceptance remains pending.

## Source checked

Downloaded the current branch revisions of Blizzard's client UI and generated
API documentation mirrored at Gethe/wow-ui-source:

| Edition | Mirrored build | Pinned source | Addon interface |
| --- | --- | --- | --- |
| Forever | 1.60.1 (70790) | [eac30af](https://github.com/Gethe/wow-ui-source/tree/eac30af597e5aaa43a60f6675ef5fdcea100375f) | 16001 |
| Retail | 12.1.5 (70783) | [297d7aa](https://github.com/Gethe/wow-ui-source/tree/297d7aaaa736f346b3e036f38ee088eaf7f8c07f) | 120105 |

The APIs used for addon whispers, channel roster names, item information,
completed quest IDs and spell-known checks have matching relevant signatures.
Their complete API surfaces differ; for example Forever has additional skill
and spellbook functions. No adapter merge or TOC-interface change is justified.

- Forever's owned skills use
  [C_SkillInfo.GetSkillLineInfoByID](https://github.com/Gethe/wow-ui-source/blob/eac30af597e5aaa43a60f6675ef5fdcea100375f/Interface/AddOns/Blizzard_APIDocumentationGenerated/SkillInfoDocumentation.lua).
  Retail's [ProfessionsBook](https://github.com/Gethe/wow-ui-source/blob/297d7aaaa736f346b3e036f38ee088eaf7f8c07f/Interface/AddOns/Blizzard_ProfessionsBook/Blizzard_ProfessionsBook.lua)
  uses GetProfessions/GetProfessionInfo. The addon retains these separate paths.
- Forever's [PvP UI](https://github.com/Gethe/wow-ui-source/blob/eac30af597e5aaa43a60f6675ef5fdcea100375f/Interface/AddOns/Blizzard_UIPanels_Game/Camelot/PVPRankFrame.lua)
  uses major-faction progression for faction 2800; Retail tracks Honor levels.
- The [chat API](https://github.com/Gethe/wow-ui-source/blob/297d7aaaa736f346b3e036f38ee088eaf7f8c07f/Interface/AddOns/Blizzard_APIDocumentationGenerated/ChatInfoDocumentation.lua)
  provides both realm outgoing-message restrictions and messaging lockdown.
  The existing adapters respect both, including unavailable/secret results.

## Fix and verification

Found a real dungeon-completion bug in shared code: GetInstanceLockTimeRemaining
returns `timeLeft, extending, encountersTotal, encountersCompleted`. We read the
second return (a boolean) as the count, silently disabling the boss-roster path.
Both editions have identical [InstanceDocumentation](https://github.com/Gethe/wow-ui-source/blob/297d7aaaa736f346b3e036f38ee088eaf7f8c07f/Interface/AddOns/Blizzard_APIDocumentationGenerated/InstanceDocumentation.lua).
Changed the reader to the third return in shared code and all four distributions,
and corrected the previously inaccurate test stub. An incomplete, absent or
restricted roster still produces no dungeon announcement.

Added simulated Forever/Retail peer checks for blocked outgoing messages,
resuming delivery, numeric send-result enums, two-way login catch-up, stable IDs,
duplicate suppression and quiet recovery. Added all-edition coverage keeping the
join notification once per character/group, now worded **Joined the WoW Status
group**, including the notification preview and website demo.

The subsequent [invalid-log warning feature](LOG_GUARD.md) adds bounded group
reports for selected rejected entries in all editions. All four source versions
and the Python project version are now **0.14.10**.

Validation: **289 tests passed** in an isolated checkout with the task changes;
**189 tests passed under Lua 5.1**. Ruff, JavaScript syntax and whitespace checks
passed. The ordinary checkout has a known minimap-icon assertion failure from
separate unfinished branding work; that work was preserved and excluded from the
isolated check. HTTP tests required local socket access outside the sandbox.

These are unreleased working-tree changes. No installed game files, SavedVariables,
public downloads, server services or Discord messages were changed.

## Remaining in-game acceptance

For each edition, install its matching package and use two players with the same
WoW Status group ID. Check startup/settings, the clarified join popup, one level
or eligible first armor equip, professions and the edition's PvP milestones.
Check a supported dungeon completion and verify that a single intermediate boss
does not announce a clear. Restart one client and confirm groups/history persist
and missing entries recover without replaying popups. Verify permitted messaging
in world/instance/combat contexts; the addon cannot override client restrictions.

Rendering, gameplay spell IDs and actual realm/faction delivery remain live-client
checks. See [the in-game checklist](LIVE_POPUPS.md) and the earlier
[Forever audit](FOREVER_COMPATIBILITY.md).
