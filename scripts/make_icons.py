"""
scripts/make_icons.py — generate simple placeholder app icons.

Creates the PNGs the PWA needs (app icon at 192/512, a maskable variant with
extra padding for Android, and an Apple touch icon). They're a rounded-square
in the app's accent colour with a small paper-plane glyph — clean and neutral.

Run from the project root:
    python scripts/make_icons.py

Feel free to replace the generated files with your own artwork later; just keep
the same filenames and sizes.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

# Where to write the icons.
ICON_DIR = Path(__file__).resolve().parent.parent / "static" / "icons"

# Colours (match the app's light theme + indigo accent).
# The icon is an indigo tile with a white glyph — reads well on any home screen.
BG = (255, 255, 255, 255)      # white glyph colour
ACCENT = (79, 110, 247, 255)   # accent #4f6ef7


def _rounded_square(size: int, radius_ratio: float, fill) -> Image.Image:
    """Return an RGBA image with a filled rounded square centred on transparency."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    radius = int(size * radius_ratio)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=fill)
    return img


def _draw_plane(draw: ImageDraw.ImageDraw, size: int, color) -> None:
    """Draw a minimalist paper-plane triangle in the centre."""
    # A simple stylised paper plane using two triangles.
    cx, cy = size / 2, size / 2
    s = size * 0.26
    # Main body (arrowhead pointing up-right).
    draw.polygon(
        [(cx - s, cy + s), (cx + s, cy - s), (cx + s * 0.15, cy + s * 0.15)],
        fill=color,
    )
    # Small fold (a lighter accent could go here; keep it one colour for simplicity).
    draw.polygon(
        [(cx - s, cy + s), (cx + s * 0.15, cy + s * 0.15), (cx - s * 0.15, cy + s * 0.55)],
        fill=color,
    )


def make_icon(size: int, maskable: bool = False) -> Image.Image:
    """Compose one icon at the given size."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    if maskable:
        # Maskable icons get cropped to various shapes, so fill the WHOLE square
        # with the accent colour (full bleed) and centre the white glyph inside
        # the safe zone. Any crop still shows a clean indigo tile.
        img.paste(Image.new("RGBA", (size, size), ACCENT), (0, 0))
        _draw_plane(ImageDraw.Draw(img), size, BG)
    else:
        tile = _rounded_square(size, 0.22, ACCENT)
        img.alpha_composite(tile)
        _draw_plane(ImageDraw.Draw(img), size, BG)

    return img


def main() -> None:
    ICON_DIR.mkdir(parents=True, exist_ok=True)

    outputs = {
        "icon-192.png": make_icon(192),
        "icon-512.png": make_icon(512),
        "maskable-512.png": make_icon(512, maskable=True),
        "apple-touch-icon.png": make_icon(180),
    }
    for name, img in outputs.items():
        path = ICON_DIR / name
        img.save(path, "PNG")
        print(f"  ✓ {path.relative_to(ICON_DIR.parent.parent)}")

    print(f"\n✅ Wrote {len(outputs)} icons to {ICON_DIR}")


if __name__ == "__main__":
    main()
