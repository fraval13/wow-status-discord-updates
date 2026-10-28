# WoW Progress emoji pack

Upload the 29 `.jpg` files to your Discord server under **Server Settings → Emoji**.
Keep each filename's name (without `.jpg`): the bot looks up these exact names.
JPEG is supported by Discord and every file is well under the 256 KB limit.

- Factions: `wow_alliance`, `wow_horde`.
- Classes: `wow_warlock`, `wow_warrior`, `wow_paladin`, `wow_hunter`, `wow_rogue`,
  `wow_priest`, `wow_shaman`, `wow_mage`, `wow_druid`.
- Status: `wow_player`, `wow_level`, `wow_xp`, `wow_deaths`, `wow_quests`, `wow_location`.
- Professions: `wow_alchemy`, `wow_blacksmithing`, `wow_enchanting`, `wow_engineering`,
  `wow_herbalism`, `wow_leatherworking`, `wow_mining`, `wow_skinning`, `wow_tailoring`,
  `wow_cooking`, `wow_first_aid`, `wow_fishing`.

The bot uses available server emojis automatically and falls back to standard
Unicode icons for missing names. No emoji IDs or credentials need to be pasted
into the repository. Its guild emoji cache updates when server emojis change.

`manifest.json` records the exact image sources and file sizes. Artwork is Blizzard
Entertainment game artwork, downloaded from Wowhead's static icon CDN. The pack
uses the original images without resizing or AI alterations. The matching blue
Alliance and red Horde banner icons have been visually checked.

To refresh the files, run `python scripts/download_discord_emojis.py` from this repo.
A ready-to-upload ZIP is also built locally at `dist/WoWStatus-discord-emojis.zip`.
