"""Make the homepage's link preview image from its own artwork (issue #190).

Usage: python scripts/make_link_preview.py [--check]

Chat clients such as Discord show `og:image` as a large card only for a widely
supported format, so this writes `website/assets/link-preview.jpg` at 1200×630
from `adventure.webp`, `journal.webp` and the Cinzel font the page already ships.
JPEG keeps the painted image near 270 KB, where some chat clients drop larger
previews. It needs Pillow (in the dev extras). The deploy job builds the homepage
with the standard library alone, so the JPEG is committed and the build only checks
it; `--check` and `tests/test_link_preview.py` fail when it no longer matches what
this script draws, so a changed illustration, logo, font or preview text below
cannot ship with a stale image. The preview's own text is set here, not taken from
the page's tags.
"""
import argparse
import io
import sys
from pathlib import Path

from build_homepage import LINK_PREVIEW
from build_homepage import LINK_PREVIEW_SIZE as SIZE
from PIL import Image, ImageChops, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'website/assets'
OUTPUT = ROOT / 'website' / LINK_PREVIEW.lstrip('/')
QUALITY = 90
TITLE = 'WoW Status'
TAGLINE = ('Your friends’ adventures,', 'right inside World of Warcraft.')
EDITIONS = 'CLASSIC · TBC · RETAIL · FOREVER'
GOLD = (241, 201, 116)
PARCHMENT = (238, 226, 200)
# Decoders, resamplers and JPEG encoders may differ by a few shades between builds
# (Windows and Ubuntu CI), so --check ignores small per-pixel differences but allows
# only a handful of clearly changed pixels; one changed letter changes hundreds.
SHADE = 32
CHANGED_PIXELS = 40


def render():
    width, height = SIZE
    art = Image.open(ASSETS / 'adventure.webp').convert('RGB')
    scaled = art.resize((round(art.width * height / art.height), height), Image.Resampling.LANCZOS)
    # The right of the illustration: the road, the gate and the three adventurers.
    image = scaled.crop((scaled.width - width, 0, scaled.width, height))
    # A dark band on the left, fading out by x = 640, so the title reads over the valley.
    row = bytes(max(0, 215 - x * 215 // 640) for x in range(width))
    shade = Image.frombytes('L', (width, 1), row).resize(SIZE, Image.Resampling.NEAREST)
    image = Image.composite(Image.new('RGB', SIZE, (12, 14, 20)), image, shade)
    logo = Image.open(ASSETS / 'journal.webp').convert('RGB').resize((168, 168), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(image)
    draw.rectangle((58, 58, 58 + 168 + 11, 58 + 168 + 11), outline=(120, 92, 46), width=3)
    image.paste(logo, (64, 64))
    def font(size):
        # BASIC layout: Raqm is only present on some builds (not the Windows wheels)
        # and places glyphs differently, which would make --check platform dependent.
        return ImageFont.truetype(ASSETS / 'fonts/cinzel-latin.woff2', size,
                                  layout_engine=ImageFont.Layout.BASIC)
    draw.text((64, 262), TITLE, font=font(96), fill=GOLD,
              stroke_width=2, stroke_fill=(30, 20, 8))
    body = font(38)
    for number, line in enumerate(TAGLINE):
        draw.text((66, 392 + number * 52), line, font=body, fill=PARCHMENT, stroke_width=1,
                  stroke_fill=(12, 14, 20))
    draw.text((66, 530), EDITIONS, font=font(24), fill=GOLD)
    return image


def encode(image):
    data = io.BytesIO()
    # Baseline, no metadata: the same input gives the same bytes on one Pillow build.
    image.save(data, 'JPEG', quality=QUALITY, optimize=True)
    return data.getvalue()


def changed_pixels(first, second):
    """How many pixels differ by more than SHADE in some channel."""
    difference = ImageChops.difference(first, second)
    mask = Image.merge('RGB', [band.point(lambda value: 255 if value > SHADE else 0)
                               for band in difference.split()]).convert('L').point(lambda value: 255 if value else 0)
    return mask.histogram()[255]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true', help='fail if the committed preview is stale')
    args = parser.parse_args(argv)
    data = encode(render())
    name = OUTPUT.relative_to(ROOT).as_posix()
    if args.check:
        try:
            committed = Image.open(OUTPUT).convert('RGB')
        except OSError:
            sys.exit(f'{name} is missing; run python scripts/make_link_preview.py')
        fresh = Image.open(io.BytesIO(data)).convert('RGB')
        if committed.size != SIZE or changed_pixels(committed, fresh) > CHANGED_PIXELS:
            sys.exit(f'{name} is stale; run python scripts/make_link_preview.py')
        print(f'{name} matches the artwork')
        return
    OUTPUT.write_bytes(data)
    print(f'Wrote {name}')


if __name__ == '__main__':
    main()
