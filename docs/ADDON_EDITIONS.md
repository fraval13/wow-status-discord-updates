# Three standalone game addons

The repository contains three folders that are ready to copy or package separately:

```text
addon/
  vanilla/WoWStatus/     Vanilla Classic / Classic Era
  forever/WoWStatus/     Forever / Camelot
  tbc/WoWStatus/         Burning Crusade Classic Anniversary
  shared/               Maintainer source for common Lua features
```

Each installable `WoWStatus` folder contains all of its files. Install only the
folder for that game into that game's `Interface/AddOns` directory. All use the
addon name `WoWStatus`, the `/wstatus` commands and `WoWStatus.lua` SavedVariables
filename. There is no dependency on the repository's shared directory at runtime.
Do not install different editions into the same AddOns directory or load one on the wrong client.

The adapters are `Vanilla.lua`, `Forever.lua`, and `TBC.lua`. All include the
same account-wide group selector, logs, line graph, Norwegian dates, privacy controls and popup
module. `Safe.lua` excludes secret/restricted values before comparisons or exports.
Forever uses the documented Camelot client constant plus the 160xx interface band,
modern `C_Item.GetItemInfo`, and namespaced chat sending. It waits for readable
player identity instead of inventing a replacement GUID. Optional unreadable fields
are omitted, and unknown chat restriction state blocks a send.

The API-based Forever implementation is written; real client behavior, identity
stability, persistence and communication are still unverified. Neither addon has
been run on the work computer. GitHub/server checks cannot replace playing in the
actual clients. The TBC Anniversary build targets interface 20506 (2.5.6),
project ID 5, and level 70. It includes Jewelcrafting and Master profession titles.
It does not report Vanilla-style honor-rank promotions in TBC.

## Install at home

Get the fourth value from `/dump GetBuildInfo()` in the selected game, exit WoW,
then use its actual number and path:

```sh
python scripts/install_addon.py --client vanilla --addons-dir "/YOUR/VANILLA/Interface/AddOns" --interface YOUR_INTERFACE_NUMBER
python scripts/install_addon.py --client forever --addons-dir "/YOUR/FOREVER/Interface/AddOns" --interface YOUR_INTERFACE_NUMBER
python scripts/install_addon.py --client tbc --addons-dir "/YOUR/WOW/_anniversary_/Interface/AddOns" --interface 20506
```

On Windows, pass the corresponding Windows game path in quotes. The installer
refuses an existing WoWStatus directory: back up addon files and SavedVariables
before removing the old addon folder for an upgrade. It also rejects interface
numbers outside the chosen edition's band, rather than enabling the wrong client.
The repository TOCs use source-snapshot defaults; the installed build is authoritative.

The companion/service remain one Python project. Each upload carries `classic-era`, `forever`, or `tbc-anniversary`; all are accepted and contribute separate character
identities, even if realm and GUID/name happen to match. Select the SavedVariables
file belonging to the game being tested, or repeat `--saved-variables` for both.

Live popups use `WSTATUS2` with the client identity, and ignore the other edition's
packets. The Vanilla version can read the previous experimental `WSTATUS1` format;
Forever does not assume that an unlabelled packet belongs to Forever.

Settings are available in **Options → AddOns → WoW Status**, with a **Groups**
subpage. Slash commands open the same pages. On clients without a supported
settings menu API, the standalone windows remain available.

## Maintaining shared features

Edit `addon/shared/*.lua`, then synchronize the three installable folders with:

```sh
python scripts/sync_addons.py
```

This copies source only. Adapters and TOCs stay separate. The authored test suite
checks that both packages contain the same shared files, and mocks each edition’s API paths.
GitHub Actions produces separate Vanilla, Forever and TBC Anniversary ZIP artifacts after checks.


## TBC client-source evidence

Anniversary metadata and behavior were checked against Blizzard's mirrored UI
source on `classic_anniversary`, revision
`68e0a2ec559d9761dfc4e7f864c3944f9d758a49` (2.5.6 build 70577).
The [TBC client constants](https://github.com/Gethe/wow-ui-source/blob/68e0a2ec559d9761dfc4e7f864c3944f9d758a49/Interface/AddOns/Blizzard_FrameXMLBase/TBC/Constants.lua)
identify `WOW_PROJECT_BURNING_CRUSADE_CLASSIC=5` and level 70. The installer accepts
205xx interfaces and checks the project at runtime. Confirm your own client's
fourth `GetBuildInfo()` result if its interface changes.

TBC keeps its group logs and messages separate from Vanilla and Forever even
when players use the same group ID or character name. Discord remains hidden.
API/mocked tests are not a substitute for a two-player test in the actual client.
