# Animated masthead experiment

Source artwork: `website/assets/adventure.webp`. The original still is unchanged.
The built-in image_gen tool produced the two edited source plates below.
WebP conversion used ffmpeg; SVG composition and Chromium rendering add motion.

- `background.webp`: background plate with the three travelers removed.
- `travelers.webp`: transparent 4×2 sheet of eight walking poses.
- Final web assets: `website/assets/adventure-motion.webm` (VP9) and
  `website/assets/adventure-motion.mp4` (H.264), silent 12-second loops,
  1440×480 at 20 fps. These are video rather than a large GIF.

The travelers walk in place rather than advancing through the scene. The camera
stays fixed, sky drifts slightly, pine branches ripple and gate light flickers.
This is a painted sprite animation experiment rather than full cinematic motion.

## Rebuild

Serve the repository root on localhost:4174, and start Chromium with its remote
debugging port on localhost:9228. Then run:

```sh
node scripts/motion/render.mjs
sh scripts/motion/encode.sh
```

`scripts/motion/scene.html` contains the composition. Intermediate PNG frames go
to ignored `dist/motion-frames/`. These source plates are not published.

## Generation prompts

Background plate:

> Use case: precise-object-edit. Edit target: the attached original painted fantasy landscape. Create a clean background plate for a subtle animated website masthead. Change ONLY the three small adventurers in the lower-right foreground: remove the dwarf with shield, the purple-robed elf and blue staff, and the hooded human archer, including just their cast shadows, and reconstruct the stone path behind them. Preserve the original landscape, gate, castle, bridge, pine trees, mountain silhouettes, sky, lighting, viewpoint, framing and all other objects as exactly as possible. The gate fire and lanterns must remain. Original aspect ratio 3:1, 2172x724; retain this composition without zooming or cropping. Do not add any new characters, objects, letters, borders or watermark. Match the same rich hand-painted early fantasy game art.

Walking sheet:

> Use case: stylized-concept. Reference image: the attached landscape establishes the exact character designs, rear-view camera angle, painted art style and warm sunset light. Deliver a transparent-background WALK-CYCLE SPRITE SHEET of ONLY its three foreground adventurers walking together, seen from behind: short stout dwarf on the left with a round shield on his back and brown-red armor, tall slender purple-robed elf mage in the middle holding a small glowing blue staff, hooded dark green human hunter with bow/quiver on the right. Arrange EXACTLY 8 animation frames in a regular 4-column by 2-row grid, no gutters, on one canvas. Every cell must show the SAME three characters in the SAME arrangement, proportions, outfits and scale, with feet at the same common baseline and generous transparent margins on all sides. Camera and framing fixed. The 8 consecutive poses are one smooth complete walking-in-place cycle: distinct alternating leg and arm positions, slight natural torso bob, small robe/cloak flutter. The trio should look forward away from the camera in every frame and never turn sideways. The animation should look like a restrained hand-painted isometric fantasy adventure game, not chibi, not pixel art, not cartoon. NO scenery, ground, cast shadow, labels, letters, frame numbers, panel borders, glow enclosing the figures, props other than their existing equipment, or watermark. Actual transparent alpha background required. Output aspect 2:1, ideally 2048x1024 (each cell 512x512). Eight cells, exactly 4 across and 2 down.

Original generated PNGs are retained in
`/home/fraval/.codex/generated_images/01a17f81-840d-7742-b3b1-36e4a0bd4126/`:
`exec-028418e0-9f87-4ff6-bc67-5125ccb6bbf0.png` and
`exec-f3d86053-8471-45a0-a825-4a9918bdc785.png`, respectively.
