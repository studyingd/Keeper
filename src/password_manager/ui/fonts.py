"""Application fonts bundled with the app.

Inter (body), Space Grotesk (display) and JetBrains Mono (credentials) are
the exact families the HTML demo uses; bundling their variable TTFs keeps the
offline promise - no network fetch, no system-font roulette. Chinese text
falls back to the platform CJK font per glyph, so the latin faces only carry
what they are good at.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtGui import QFontDatabase

FONT_DIR = Path(__file__).parent / "fonts"
BUNDLED_FONTS = ("Inter-Variable.ttf", "SpaceGrotesk-Variable.ttf", "JetBrainsMono-Variable.ttf")


@lru_cache(maxsize=1)
def ensure_fonts_loaded() -> bool:
    """Register the bundled fonts once; returns True when any family loaded."""
    loaded = False
    for name in BUNDLED_FONTS:
        path = FONT_DIR / name
        if path.exists() and QFontDatabase.addApplicationFont(str(path)) >= 0:
            loaded = True
    return loaded


def font_paths() -> list[Path]:
    """Absolute paths of the bundled font files (used by packaging specs)."""
    return [FONT_DIR / name for name in BUNDLED_FONTS if (FONT_DIR / name).exists()]
