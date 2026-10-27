# Forever version: implemented, in-game validation pending

There are now two standalone addons:

- `addon/vanilla/WoWStatus` for Vanilla Classic / Classic Era.
- `addon/forever/WoWStatus` for Forever / Camelot.

See [edition structure and installation](ADDON_EDITIONS.md). The shared companion
and service accept `classic-era` and `forever` uploads as separate character
identities. The Forever package includes its own adapter and TOC; it is more than
a metadata change to the Vanilla version. No addon was run on the work computer.

The Forever adapter is authored against:

- [Blizzard's mirrored Forever API documentation](https://github.com/Gethe/wow-ui-source/tree/forever/Interface/AddOns/Blizzard_APIDocumentationGenerated)
- [Camelot project constants](https://raw.githubusercontent.com/Gethe/wow-ui-source/forever/Interface/AddOns/Blizzard_ProjectConstants/Camelot/ProjectConstants.lua)
- [Unit API and level events](https://raw.githubusercontent.com/Gethe/wow-ui-source/forever/Interface/AddOns/Blizzard_APIDocumentationGenerated/UnitDocumentation.lua)
- [Modern item API](https://raw.githubusercontent.com/Gethe/wow-ui-source/forever/Interface/AddOns/Blizzard_APIDocumentationGenerated/ItemDocumentation.lua)
- [Chat API and restrictions](https://raw.githubusercontent.com/Gethe/wow-ui-source/forever/Interface/AddOns/Blizzard_APIDocumentationGenerated/ChatInfoDocumentation.lua)
- [Line drawing API](https://raw.githubusercontent.com/Gethe/wow-ui-source/forever/Interface/AddOns/Blizzard_APIDocumentationGenerated/SimpleLineAPIDocumentation.lua)

It detects the Forever client, uses modern item/chat calls, skips secret values,
waits for public player identity, and keeps edition identity in exports and popup
packets. The common UI, group routing, persisted history and level graph ship in
both folders. Documentation presence does not certify actual client behavior.

Still required at home:

1. Verify the installed Forever interface number and correct addon loading.
2. Prove SavedVariables survives reload, logout and a full client restart.
3. Confirm the player's GUID remains stable across sessions and is readable when
   collection starts. Do not bypass obfuscation/restrictions if it is unavailable.
4. Test real levels, loot metadata, equipment and optional profile fields.
5. Test scroll/edit/line UI behavior and group ID casing in the actual client.
6. Confirm channel joining and messaging, especially combat/instance restrictions
   and realm/faction reachability. A successful API call is not a delivery receipt.
7. Compare JSON histories for Vanilla and Forever and verify no identity mixing.

Mocked API tests, Python/server tests and deployment checks cannot prove these
in-game results. The implementation is available for testing, not advertised as
verified Forever compatibility. TBC support has not been added.
