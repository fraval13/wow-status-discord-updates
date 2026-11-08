# Automatic dungeon records

A dungeon record needs a confirmed completion while the addon is enabled.
Entering an instance, receiving loot, completing its quests or killing an
intermediate boss does not establish a clear. Earlier unrecorded runs cannot
reliably establish who earned a group's first-clear medal.

The addon accepts:

- `LFG_COMPLETION_REWARD` inside a party instance.
- A complete, public killed-encounter roster from the instance APIs.
- On Classic-family clients, `BOSS_KILL` or a successful `ENCOUNTER_END` for
  a known terminal encounter in that exact instance map.

The last path covers normal dungeons that do not supply the first two signals.
It uses numeric map/encounter pairs, so localized boss names do not matter.
Failed encounters, raid instances, different maps, unknown encounters and
restricted values cannot become a final-boss confirmation. A failed
`ENCOUNTER_END` is ignored even if the same fight later produces a valid
`BOSS_KILL`. Duplicate signals retain the existing first-clear-per-dungeon bound.

The Classic table covers Shadowfang Keep, Stockades, Deadmines, Wailing Caverns,
Razorfen Kraul, Blackfathom Deeps, Uldaman, Gnomeregan, Sunken Temple, Razorfen
Downs, Scarlet Monastery's four wings, Zul'Farrak, Lower/Upper Blackrock Spire,
Blackrock Depths, Scholomance, both Stratholme routes, Maraudon, Ragefire Chasm
and Dire Maul's three wings. Forever adds Excavation Site: Wetlands, Ruins of
Lordaeron and Hall of Thanes. Optional side bosses after the endpoint do not
replace it: Deadmines uses VanCleef, and Ruins of Lordaeron uses Rath'mael.
The game's instance name remains the deduplication key, so multiple wings
sharing a name produce one first-clear announcement, as before.

Retail retains its native completion/roster paths; the Classic endpoint table
does not apply to Retail's redesigned versions of the same maps. Unknown new
content keeps the native paths and needs a verified endpoint before joining
the explicit table. No combat-log access or secret-value workaround is used.

Sources checked on 8 November 2026:

- Blizzard's [Forever encounter event definitions](https://github.com/Gethe/wow-ui-source/blob/forever/Interface/AddOns/Blizzard_APIDocumentationGenerated/EncounterInfoDocumentation.lua)
  define `BOSS_KILL(encounterID, encounterName)` and `ENCOUNTER_END` with its
  success value.
- Blizzard's [instance API definitions](https://github.com/Gethe/wow-ui-source/blob/forever/Interface/AddOns/Blizzard_APIDocumentationGenerated/InstanceDocumentation.lua)
  define the instance map and lockout-roster returns.
- The client [DungeonEncounter table for Forever 1.60.1.70790](https://wago.tools/db2/DungeonEncounter?build=1.60.1.70790)
  and [Classic Era table](https://wago.tools/db2/DungeonEncounter?product=wow_classic_era)
  supply the numeric pairs in `Milestones.lua`. The endpoint list is explicit;
  the addon never assumes that the last row of an arbitrary roster is a final boss.

The mock checks cover terminal/intermediate bosses, instance and edition
boundaries, failed/duplicate/restricted signals, privacy and notification
transport. Live event availability and delivery still need owner checks. In a
supported normal dungeon, defeat an intermediate boss and then the endpoint:
only the latter should create one first-clear entry and fill the medal; its
matching `ENCOUNTER_END` or `BOSS_KILL` must not add another.
