# Homepage artwork

The optional `?motion=on` experiment uses `assets/adventure-motion.webm` with an
MP4 fallback. Source plates, exact generation prompts and render instructions
are documented in [the motion source README](../assets/website-motion/README.md).
The original still remains the default.

`assets/adventure.webp` is original artwork generated with the built-in
`image_gen` tool, then converted to WebP for the homepage. The original image is
retained in the session's generated-images directory. Final website asset:
`website/assets/adventure.webp`.

Prompt:

> Use case: stylized-concept. Asset type: ultra-wide masthead illustration for a World of Warcraft addon fansite inspired by 2005-2007 fantasy game websites. Original hand-painted high fantasy adventure landscape, rich brushwork and slightly grainy painted game manual artwork, not a modern photoreal render. Wide 3:1 composition: ancient dwarven stone gate and pine-covered mountainous valley at dusk, enormous snowy mountain cliffs in the distance, winding warm-lit road crossing a stone bridge, tiny three adventurers viewed from behind on right third (a dwarf warrior with shield, a robed elf mage with blue staff, and human hunter), a small warm lantern, purple twilight sky and distant golden settlement. The left half is mostly dark blue forest and atmospheric mountain valley with ample quiet dark space for website headline overlay. Edges dark and vignetted to blend into charcoal stone website. Palette deep midnight blue, moss green, warm old gold, copper and amber torchlight. Majestic, nostalgic, cozy feeling of beginning an MMO adventure with friends. The artwork fills the complete image, no frames, no UI, no letters, no typography, no logos, no watermark. Intended wide aspect 3:1, about 1536 by 512 or wider.

`assets/journal.webp` and `assets/favicon.png` are web exports of the project's
existing `assets/branding/WoWStatus-curseforge.png` logo. The original branding
files and separate addon branding changes are preserved.

Game icons under `assets/icons/` reuse the existing icon pack documented at
`assets/discord-emojis/README.md`. Blizzard game artwork is credited in the
homepage footer. The level arrow is original project artwork. The armor icon is Blizzard game
artwork served originally at `https://wow.zamimg.com/images/wow/icons/large/inv_chest_plate04.jpg`.

Cinzel is self-hosted from Google Fonts and distributed under the SIL Open Font
License in `assets/fonts/Cinzel-OFL.txt`. No third-party resources load at runtime.

Visual references: the user's [October 2007 archived WoW homepage](https://web.archive.org/web/20071007004046/http://www.worldofwarcraft.com/index.xml)
and the [Web Design Museum screenshot](https://www.webdesignmuseum.org/gallery/world-of-warcraft-in-2007).
The layout is original and uses no copied Blizzard website frame artwork.
