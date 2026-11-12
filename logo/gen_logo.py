# pyright: reportMissingTypeStubs=false
# /// script
# requires-python = ">=3.14"
# dependencies = ["fonttools>=4.50"]
# ///
"""Generate the oxf1eece logo: a pixel-art ox in a sheep's fleece, and the OXF1EECE wordmark.

The name reads two ways: "ox fleece" and the hex literal 0xF1EECE. The mark draws
the first reading. An ox (brown head, horns, hooves, tail) wears a fleece that covers
its body, the way the tool dresses English words up in hexadecimal digits. The
wordmark carries the second reading. It is set in Silkscreen, whose O has the same
shape as its 0, so OXF1EECE also looks like the hex literal. The 1, the one letter
in the name that is really a digit (an l in disguise), is set in the ox's brown.
Read as a colour, #F1EECE is a cream close to undyed wool, so the fleece is
painted in the name itself.

The sprite is pixel data, not a drawing procedure. It was made by downsampling a
vector draft onto the 32x23 grid and then retouching it pixel by pixel. To change it,
edit SPRITE directly.

Usage:
    uv run logo/gen_logo.py          # icon + light/dark lockups (SVG)
    uv run logo/gen_logo.py --png    # also export PNG (rsvg-convert)
"""

import argparse
import shutil
import subprocess
from pathlib import Path
from typing import Protocol, cast

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

HERE = Path(__file__).parent


class Glyph(Protocol):
    """The part of a fontTools glyph-set entry used here (fontTools ships no types for it)."""

    width: int

    def draw(self, pen: object) -> None: ...


class Bounds(Protocol):
    """The part of fontTools' BoundsPen used here: (xMin, yMin, xMax, yMax), None if empty."""

    bounds: tuple[float, float, float, float] | None


# ── Palette ─────────────────────────────────────────────────
PALETTE = {
    "K": "#2B2B2B",  # outline
    "W": "#F1EECE",  # wool: the name itself, read as a colour
    "w": "#D8D1C2",  # wool curl
    "B": "#9A5B34",  # ox brown
    "D": "#6E3D22",  # dark brown: far legs, tail tuft, horn outline
    "H": "#E6C98A",  # horn
    "P": "#F3A9A0",  # muzzle, inner ear
    "N": "#9C4F4A",  # nostril
    "E": "#111111",  # eye
}

# ── Sprite ──────────────────────────────────────────────────
# 32x23, facing right; "." is transparent. The outline is 1px all round, so
# neighbouring rows of a diagonal touch only at corners.
SPRITE = [
    "........................D...D...",
    ".......................DHD.DHD..",
    "......................DHD.DHD...",
    ".........KKKKKKKKKK..DHHDDHHD...",
    "......KKKWWWWWWWWWWKDHHDDHHD....",
    "....KKWWWWWWWWWWWWWKKKKKKKKK....",
    "...KWWWWWWWWWWWWWWWWKBBBBBBKK...",
    "...KWWWWwWWWWWwWWWKKBBBBBBBBBK..",
    "..KWWWWwWwWWWwWwWKPPBBBBEBBBBK..",
    "..KWWWWWWWWWWWWWWWKDBBBBEBBBBK..",
    "..KWWwWWWWWwWWWWwWWKBBBBBBBKKKK.",
    "..KWwWwWWWwWwWWwWwWKBBBBBBKPPPPK",
    "..KWWWWWWWWWWWWWWWWWKBBBBBKPPNPK",
    "..KWWWWWwWWWWWwWWWWWWKBBBBKPPPPK",
    ".KKWWWWwWwWWWwWwWWWWWWKKKKKKKKK.",
    "KBKKWWWWWWWWWWWWWWWWWWWWWKK.....",
    "KBKKWWWWWWWwWWWWWwWWWWWWWK......",
    "KDKKKWWWWWwWwWWWwWwWWWWWKK......",
    "KDK.KKWWWWWWWWWWWWWWWWWWK.......",
    ".K...KKKWWWWWWWWWWWWWWKKK.......",
    "....KBBKDDK......KBBKDDK........",
    "....KBBKDDK......KBBKDDK........",
    "....KKKKKKK......KKKKKKK........",
]
SPRITE_W = len(SPRITE[0])
SPRITE_H = len(SPRITE)

# ── Wordmark ────────────────────────────────────────────────
FONT = HERE / "fonts" / "Silkscreen-Bold.ttf"
WORD = "OXF1EECE"
ACCENT_INDEX = WORD.index("1")
FONT_PIXEL = 125  # Silkscreen draws on a 125-unit pixel grid; caps are 5 pixels tall
CAP_PIXELS = 5
TEXT_SCALE = 2  # one wordmark pixel = 2 sprite pixels, so both share one grid
GAP = 2  # wordmark pixels between the icon and the text
THEMES = {
    # README pairs these via <picture>; only the text colours differ.
    "light": {"text": PALETTE["K"], "accent": PALETTE["B"]},
    # A lighter brown, to keep contrast on dark backgrounds.
    "dark": {"text": PALETTE["W"], "accent": "#C8875A"},
}

# ── Output size ─────────────────────────────────────────────
ICON_SIDE = 32  # square icon, in sprite pixels
DISPLAY_PX = {"icon": 8, "lockup": 4}  # screen px per sprite pixel in the SVG width/height


def sprite_rects(ox: int, oy: int) -> list[str]:
    """One <rect> per horizontal run of same-coloured pixels."""
    out: list[str] = []
    for y, row in enumerate(SPRITE):
        x = 0
        while x < SPRITE_W:
            c = row[x]
            run = 1
            while x + run < SPRITE_W and row[x + run] == c:
                run += 1
            if c != ".":
                out.append(
                    f'<rect x="{ox + x}" y="{oy + y}" width="{run}" height="1"'
                    f' fill="{PALETTE[c]}"/>'
                )
            x += run
    return out


def svg_doc(w: int, h: int, scale: int, body: list[str]) -> str:
    return "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}"'
            f' width="{w * scale}" height="{h * scale}" shape-rendering="crispEdges">',
            *(f"  {line}" for line in body),
            "</svg>",
            "",
        ]
    )


def generate_icon() -> str:
    """Square transparent icon; the sprite is centred vertically."""
    oy = (ICON_SIDE - SPRITE_H) // 2
    return svg_doc(ICON_SIDE, ICON_SIDE, DISPLAY_PX["icon"], sprite_rects(0, oy))


def wordmark_paths(
    font: TTFont, x0: float, baseline: float, theme: dict[str, str]
) -> tuple[list[str], float]:
    """Glyph outlines as <path>s on the sprite-pixel grid, and the last glyph's right edge."""
    glyphs = font.getGlyphSet()
    cmap = font.getBestCmap()
    if cmap is None:
        raise SystemExit(f"{FONT.name} has no Unicode cmap")
    scale = TEXT_SCALE / FONT_PIXEL
    paths: list[str] = []
    x = right = x0
    for i, ch in enumerate(WORD):
        glyph = cast(Glyph, glyphs[cmap[ord(ch)]])
        pen = SVGPathPen(glyphs)
        glyph.draw(TransformPen(pen, (scale, 0, 0, -scale, x, baseline)))
        fill = theme["accent"] if i == ACCENT_INDEX else theme["text"]
        paths.append(f'<path d="{pen.getCommands()}" fill="{fill}"/>')
        bounds = cast(Bounds, BoundsPen(glyphs))
        glyph.draw(bounds)
        if bounds.bounds is None:
            raise SystemExit(f"glyph for {ch!r} is empty")
        right = x + bounds.bounds[2] * scale
        x += glyph.width * scale
    return paths, right


def generate_lockup(theme: dict[str, str]) -> str:
    font = TTFont(FONT)
    cap = CAP_PIXELS * TEXT_SCALE
    baseline = (SPRITE_H + cap) // 2  # caps centred on the sprite, snapped to the grid
    paths, right = wordmark_paths(font, SPRITE_W + GAP * TEXT_SCALE, baseline, theme)
    width = round(right)
    return svg_doc(width, SPRITE_H, DISPLAY_PX["lockup"], sprite_rects(0, 0) + paths)


def svg_to_png(svg_path: Path, png_path: Path, scale: int) -> None:
    """Rasterise with rsvg-convert (librsvg) at `scale`x the SVG's declared size.

    An integer scale keeps every sprite pixel an exact square block.
    """
    if shutil.which("rsvg-convert") is None:
        raise SystemExit("rsvg-convert not found; install librsvg (e.g. `brew install librsvg`)")
    subprocess.run(
        ["rsvg-convert", "--zoom", str(scale), "--output", str(png_path), str(svg_path)],
        check=True,
    )
    print(f"  -> {png_path.name}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate the oxf1eece logo")
    ap.add_argument("--png", action="store_true", help="also export PNG via rsvg-convert")
    ap.add_argument("--scale", type=int, default=2, help="PNG scale factor (default: 2)")
    args = ap.parse_args()

    assets = {
        "ox_icon": generate_icon(),
        "ox_lockup_light": generate_lockup(THEMES["light"]),
        "ox_lockup_dark": generate_lockup(THEMES["dark"]),
    }
    for stem, svg in assets.items():
        svg_path = HERE / f"{stem}.svg"
        svg_path.write_text(svg)
        print(f"wrote {svg_path.name}")
        if args.png:
            svg_to_png(svg_path, svg_path.with_suffix(".png"), args.scale)


if __name__ == "__main__":
    main()
