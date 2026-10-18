"""Inline SVG icon set rendered through QtSvg.

Icons are Lucide-style 24x24 stroke paths; each is wrapped into an SVG with
the caller's stroke color, rasterized once per (name, color, size) and cached.
No icon font, no bundled binaries, no external files.
"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from password_manager.ui.theme import TEXT_MUTED

ICONS: dict[str, str] = {
    "shield-check": '<path d="M12 22s8-4 8-10V6l-8-3-8 3v6c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>',
    "lock": '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.35-4.35"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "server": '<rect x="2" y="3" width="20" height="7" rx="2"/><rect x="2" y="14" width="20" height="7" rx="2"/><path d="M6 6.5h.01M6 17.5h.01"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a15 15 0 0 1 0 18 15 15 0 0 1 0-18z"/>',
    "database": '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.66 3.58 3 8 3s8-1.34 8-3V5"/><path d="M4 12c0 1.66 3.58 3 8 3s8-1.34 8-3"/>',
    "terminal": '<path d="m4 17 6-6-6-6"/><path d="M12 19h8"/>',
    "monitor": '<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/>',
    "key": '<circle cx="8" cy="15" r="4"/><path d="m10.8 12.2 8.2-8.2M17 3h3v3M14 6l3 3"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.6-6 8-6s8 2 8 6"/>',
    "copy": '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    "eye": '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "eye-off": '<path d="M2 12s3.5-7 10-7c2.05 0 3.82.76 5.28 1.78M22 12s-3.5 7-10 7c-2.05 0-3.82-.76-5.28-1.78"/><path d="m3 3 18 18M9.9 9.9a3 3 0 0 0 4.2 4.2"/>',
    "external": '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><path d="M15 3h6v6M10 14 21 3"/>',
    "pencil": '<path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/>',
    "trash": '<path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/>',
    "chevron-up": '<path d="m18 15-6-6-6 6"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5M12 15V3"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "close": '<path d="M18 6 6 18M6 6l12 12"/>',
    "refresh": '<path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/>',
}

# Fallback for unknown names so a typo never renders a blank button.
_MISSING = '<circle cx="12" cy="12" r="9"/>'


@lru_cache(maxsize=256)
def icon(name: str, color: str = TEXT_MUTED, size: int = 64, stroke_width: float = 2.0) -> QIcon:
    """Return an icon for ``name`` tinted with ``color``, rasterized at ``size``."""
    body = ICONS.get(name, _MISSING)
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="{stroke_width}" stroke-linecap="round" stroke-linejoin="round">'
        f"{body}</svg>"
    )
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


def kind_icon_name(kind: str) -> str:
    """Map an entry kind onto its sidebar/header icon."""
    return {"server": "server", "application": "globe"}.get(kind, "globe")


def credential_icon_name(credential) -> str:  # noqa: ANN001 - avoids importing the model here
    """Pick a card glyph by credential kind, falling back to URL/database hints."""
    kind = getattr(credential, "kind", "custom")
    extra = getattr(credential, "extra", "") or ""
    if kind == "ssh":
        return "terminal"
    if kind == "rdp":
        return "monitor"
    if "http://" in extra or "https://" in extra:
        return "globe"
    lowered = extra.lower()
    return "database" if "mysql" in lowered or "sql" in lowered else "key"


__all__ = ["ICONS", "icon", "kind_icon_name", "credential_icon_name"]
