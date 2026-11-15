"""Make the homepage's link preview image from its own artwork (issue #190).

Usage: python scripts/make_link_preview.py [--check]

Chat clients such as Discord show `og:image` as a large card only for a widely
supported format, so this writes `website/assets/link-preview.png` at 1200×630
from `adventure.webp`, `journal.webp` and the Cinzel font the page already ships.
It needs Pillow (in the dev extras). The deploy job builds the homepage with the
standard library alone, so the PNG is committed and the build only checks it;
`--check` and `tests/test_link_preview.py` fail when it no longer matches the
artwork, so a changed illustration cannot ship with a stale preview.
"""
import argparse
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'website/assets'
OUTPUT = ASSETS / 'link-preview.png'
SIZE = (1200, 630)
TITLE = 'WoW Status'
TAGLINE = ('Your friends’ adventures,', 'right inside World of Warcraft.')
EDITIONS = 'CLASSIC · TBC · RETAIL · FOREVER'
GOLD = (241, 201, 116)
PARCHMENT = (238, 226, 200)
# Decoders and resamplers may differ by a shade between Pillow and libwebp builds
# (Windows and Ubuntu CI), so --check allows a small average difference per channel.
TOLERANCE = 2.0


def render():
    width, height = SIZE
    art = Image.open(ASSETS / 'adventure.webp').convert('RGB')
    scaled = art.resize((round(art.width * height / art.height), height), Image.Resampling.LANCZOS)
    # The right of the illustration: the road, the gate and the three adventurers.
    image = scaled.crop((scaled.width - width, 0, scaled.width, height))
    # A dark band on the left, fading out, so the title reads over the valley.
    shade = Image.new('L', SIZE)
    shade.putdata([max(0, 215 - x * 215 // 640) for _ in range(height) for x in range(width)])
    image = Image.composite(Image.new('RGB', SIZE, (12, 14, 20)), image, shade)
    logo = Image.open(ASSETS / 'journal.webp').convert('RGB').resize((168, 168), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(image)
    draw.rectangle((58, 58, 58 + 168 + 11, 58 + 168 + 11), outline=(120, 92, 46), width=3)
    image.paste(logo, (64, 64))
    font = ASSETS / 'fonts/cinzel-latin.woff2'
    draw.text((64, 262), TITLE, font=ImageFont.truetype(font, 96), fill=GOLD,
              stroke_width=2, stroke_fill=(30, 20, 8))
    body = ImageFont.truetype(font, 38)
    for row, line in enumerate(TAGLINE):
        draw.text((66, 392 + row * 52), line, font=body, fill=PARCHMENT, stroke_width=1,
                  stroke_fill=(12, 14, 20))
    draw.text((66, 530), EDITIONS, font=ImageFont.truetype(font, 24), fill=GOLD)
    return image


def difference(first, second):
    """Average absolute difference per channel, 0 to 255."""
    return max(ImageStat.Stat(ImageChops.difference(first, second)).mean)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true', help='fail if the committed PNG is stale')
    args = parser.parse_args(argv)
    image = render()
    if args.check:
        try:
            committed = Image.open(OUTPUT).convert('RGB')
        except OSError:
            sys.exit(f'{OUTPUT.relative_to(ROOT)} is missing; run python scripts/make_link_preview.py')
        if committed.size != SIZE or difference(committed, image) > TOLERANCE:
            sys.exit(f'{OUTPUT.relative_to(ROOT)} is stale; run python scripts/make_link_preview.py')
        print(f'{OUTPUT.relative_to(ROOT)} matches the artwork')
        return
    image.save(OUTPUT, optimize=True)
    print(f'Wrote {OUTPUT.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
