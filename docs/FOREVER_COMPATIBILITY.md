# Forever compatibility: planned, not implemented or validated

As of October 27, 2026, this repository contains a Classic Era addon adapter. It
has no working Forever adapter, and the client guard deliberately disables
collection outside Classic Era. Python protocol validation also currently accepts
only the `classic-era` client identifier. A UI metadata change alone is insufficient.
No client or runtime tests have been run on the work computer.

The SavedVariables → companion → service → JSON → Discord architecture is reusable.
That does not prove Forever's export/loading behavior or any individual game API.
Actual Classic acceptance and Forever acceptance are separate tasks.

Useful references found during research:

- [Blizzard's mirrored Forever API documentation](https://github.com/Gethe/wow-ui-source/tree/forever/Interface/AddOns/Blizzard_APIDocumentationGenerated)
- [Forever chat API](https://raw.githubusercontent.com/Gethe/wow-ui-source/forever/Interface/AddOns/Blizzard_APIDocumentationGenerated/ChatInfoDocumentation.lua)
- [Forever line drawing API](https://raw.githubusercontent.com/Gethe/wow-ui-source/forever/Interface/AddOns/Blizzard_APIDocumentationGenerated/SimpleLineAPIDocumentation.lua)
- [Community-generated client API reference](https://atraeau.github.io/WoW-Addons/) and its [generation/source project](https://github.com/Atraeau/WoW-Addons)

The community-generated reference is useful evidence, not an official compatibility
certification. Documentation snapshots can change between beta and release. The
mirrored chat documentation explicitly exposes restrictions on communication; the
presence of a function does not mean that automatic popup transport will work in
every game context. Line API documentation suggests a possible graph implementation,
but does not validate this window in game.

A future port must verify:

1. Correct client detection and addon metadata for the installed Forever build.
2. Persistence and loading of account SavedVariables across reload, logout and cold start.
3. Availability, readability and stability of character GUID/realm identity and selected fields.
4. Real level, loot and equipment event behavior, including uncached item metadata.
5. Mainline item API use and any restricted/secret values before processing them.
6. Scroll/edit/line drawing UI behavior and Norwegian time formatting.
7. Channel joining and messaging restrictions, especially combat/instances and realm/faction reachability.
8. Explicit Forever client identity in uploads and separate acceptance from Classic records.

No source changes enabling Forever or TBC were made merely in response to the
compatibility questions. Development of the authorized group-ID feature continues
with the existing Classic Era boundary.
