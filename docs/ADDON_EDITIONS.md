# Two standalone game addons

The repository contains two folders that are ready to copy or package separately:

```text
addon/
  vanilla/WoWStatus/     Vanilla Classic / Classic Era
  forever/WoWStatus/     Forever / Camelot
  shared/               Maintainer source for common Lua features
```

Each installable `WoWStatus` folder contains all of its files. Install only the
folder for that game into that game's `Interface/AddOns` directory. Both use the
addon name `WoWStatus`, the `/wstatus` commands and `WoWStatus.lua` SavedVariables
filename. There is no dependency on the repository's shared directory at runtime.
Do not install both into the same AddOns directory or load one on the wrong client.

The Vanilla folder has `Vanilla.lua`; Forever has `Forever.lua`. Both include the
same group selector, logs, line graph, Norwegian dates, privacy controls and popup
module. `Safe.lua` excludes secret/restricted values before comparisons or exports.
Forever uses the documented Camelot client constant plus the 160xx interface band,
modern `C_Item.GetItemInfo`, and namespaced chat sending. It waits for readable
player identity instead of inventing a replacement GUID. Optional unreadable fields
are omitted, and unknown chat restriction state blocks a send.

The API-based Forever implementation is written; real client behavior, identity
stability, persistence and communication are still unverified. Neither addon has
been run on the work computer. GitHub/server checks cannot replace playing in the
actual clients. TBC remains outside these two editions.

## Install at home

Get the fourth value from `/dump GetBuildInfo()` in the selected game, exit WoW,
then use its actual number and path:

```sh
python scripts/install_addon.py --client vanilla --addons-dir "/YOUR/VANILLA/Interface/AddOns" --interface YOUR_INTERFACE_NUMBER
python scripts/install_addon.py --client forever --addons-dir "/YOUR/FOREVER/Interface/AddOns" --interface YOUR_INTERFACE_NUMBER
```

On Windows, pass the corresponding Windows game path in quotes. The installer
refuses an existing WoWStatus directory: back up addon files and SavedVariables
before removing the old addon folder for an upgrade. It also rejects interface
numbers outside the chosen edition's band, rather than enabling the wrong client.
The repository TOCs use source-snapshot defaults; the installed build is authoritative.

The companion/service remain one Python project. Each upload carries either
`classic-era` or `forever`; both are accepted and contribute separate character
identities, even if realm and GUID/name happen to match. Select the SavedVariables
file belonging to the game being tested, or repeat `--saved-variables` for both.

Live popups use `WSTATUS2` with the client identity, and ignore the other edition's
packets. The Vanilla version can read the previous experimental `WSTATUS1` format;
Forever does not assume that an unlabelled packet belongs to Forever.

## Maintaining shared features

Edit `addon/shared/*.lua`, then synchronize the two installable folders with:

```sh
python scripts/sync_addons.py
```

This copies source only. Adapters and TOCs stay separate. The authored test suite
checks that both packages contain the same shared files, and mocks both API families.
GitHub Actions produces separate Vanilla and Forever ZIP artifacts after checks.
