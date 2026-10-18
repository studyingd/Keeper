"""Generate Keeper's application icons (keeper.ico / keeper.icns) from code.

Draws a dark navy rounded badge with a teal keyhole and saves a
multi-size .ico used for the window icon, the tray icon and the
Windows EXE file icon, plus a PNG-compressed .icns (up to 1024px) for
the macOS app bundle. The artwork is centred on the canvas with the
margin Apple's icon grid recommends (~10% per side), so the Dock tile
lines up with neighbouring macOS app icons. Run from anywhere:

    python scripts/make_icon.py
"""

import io
import struct
from pathlib import Path

from PIL import Image, ImageDraw

BACKGROUND = (22, 35, 58, 255)   # #16233a dark navy, matches the UI
ACCENT = (37, 196, 183, 255)     # #25c4b7 teal, matches the UI highlight
MASTER = 1024
ARTWORK = 824                    # Apple icon grid: artwork box inside the 1024 canvas
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
ICNS_LAYERS = (("ic11", 32), ("ic12", 64), ("ic07", 128), ("ic13", 256), ("ic14", 512), ("ic10", 1024))
OUTPUT = Path(__file__).resolve().parent.parent / "src" / "password_manager" / "assets" / "keeper.ico"


def draw_master() -> Image.Image:
    image = Image.new("RGBA", (MASTER, MASTER), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = 24
    draw.rounded_rectangle(
        [margin, margin, MASTER - margin, MASTER - margin],
        radius=220,
        fill=BACKGROUND,
        outline=ACCENT,
        width=36,
    )
    # Keyhole: circle plus a widening shaft, both in the accent colour.
    center_x = MASTER // 2
    circle_center_y, circle_radius = 396, 150
    draw.ellipse(
        [center_x - circle_radius, circle_center_y - circle_radius,
         center_x + circle_radius, circle_center_y + circle_radius],
        fill=ACCENT,
    )
    shaft_top = circle_center_y + circle_radius - 64
    draw.polygon(
        [
            (center_x - 62, shaft_top),
            (center_x + 62, shaft_top),
            (center_x + 132, 826),
            (center_x - 132, 826),
        ],
        fill=ACCENT,
    )
    return image


def fit_to_icon_grid(image: Image.Image) -> Image.Image:
    """Centre the artwork in Apple's 824x824 box inside the 1024 canvas."""
    artwork = image.crop(image.getchannel("A").getbbox())
    artwork = artwork.resize((ARTWORK, ARTWORK), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (MASTER, MASTER), (0, 0, 0, 0))
    offset = (MASTER - ARTWORK) // 2
    canvas.paste(artwork, (offset, offset), artwork)
    return canvas


def write_icns(image: Image.Image, path: Path) -> None:
    """Pack PNG-compressed layers into an .icns container without iconutil."""
    chunks = []
    for kind, size in ICNS_LAYERS:
        buffer = io.BytesIO()
        image.resize((size, size), Image.Resampling.LANCZOS).save(buffer, format="PNG")
        payload = buffer.getvalue()
        chunks.append(kind.encode("ascii") + struct.pack(">I", len(payload) + 8) + payload)
    body = b"".join(chunks)
    path.write_bytes(b"icns" + struct.pack(">I", len(body) + 8) + body)


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    master = fit_to_icon_grid(draw_master())
    master.save(OUTPUT, format="ICO", sizes=[(size, size) for size in SIZES])
    icns = OUTPUT.with_suffix(".icns")
    write_icns(master, icns)
    print(f"Wrote {OUTPUT} and {icns}")


if __name__ == "__main__":
    main()
