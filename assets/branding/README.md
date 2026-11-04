# WoW Status logo

- `WoWStatus-logo.png`: original generated artwork.
- `WoWStatus-curseforge.png`: 400 × 400 PNG for the project avatar.
- `../../addon/shared/Textures/Logo.tga`: 256 × 256 uncompressed RGB game texture.

Both addon editions use the texture in their TOC IconTexture metadata and minimap
button. Run `python scripts/sync_addons.py` after updating the canonical texture.
Restart WoW after installing the updated addon folder. Live display needs an
in-game check.

Created with the built-in image generation tool using this prompt:

> Use case: logo-brand. Create one square logo icon for WoW Status, a fantasy game addon for sharing friend milestones and an activity journal. Subject: a bold open adventure journal with a single rising gold star above the pages, suggesting shared progress. Polished hand-painted fantasy inventory icon, simple strong silhouette, rich dark background, luminous readable highlights, restrained ornament. Centered composition filling the square with modest safe margin, recognizable at 32 pixels. No text, letters, watermark, existing game logos, or mockup. Deliver a single square image.
