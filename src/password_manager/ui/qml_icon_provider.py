"""QQuickImageProvider that renders the shared SVG icon set for QML.

URL scheme: ``image://icons/<name>#<rrggbb>`` (the color's alpha byte, if the
engine serializes one, is ignored). The renderer and its pixmap cache reuse
the exact paths from ui.icons, so widgets and QML never drift apart.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap, QRadialGradient
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtSvg import QSvgRenderer

from password_manager.ui.icons import ICONS

_STROKE_WIDTH = 2.0


class GlowProvider(QQuickImageProvider):
    """image://glow/<color>/<alpha> — a true radial gradient sprite.

    The demo's background glows are localized radial-gradient ellipses
    (700px falloff), not tinted circles; painting those in pure QML would
    need concentric hacks, so the falloff is rendered here once and cached.
    """

    COLORS = {
        "teal": (0x0A, 0x3A, 0x42, 90),   # demo: oklch(0.24 0.045 210 / 0.35)
        "blue": (0x00, 0x25, 0x2B, 115),  # demo: oklch(0.20 0.040 200 / 0.45)
    }

    def __init__(self) -> None:
        super().__init__(QQuickImageProvider.ImageType.Pixmap)
        self._cache: dict[tuple[str, int, int], QPixmap] = {}

    def requestPixmap(self, identifier: str, size, requested) -> QPixmap:
        parts = identifier.split("/")
        name = parts[0] if parts else "teal"
        edge = requested.width() if requested.width() > 0 else 512
        height = requested.height() if requested.height() > 0 else edge
        key = (name, edge, height)
        if key in self._cache:
            return self._cache[key]
        r, g, b, alpha = self.COLORS.get(name, self.COLORS["teal"])
        image = QImage(edge, height, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        gradient = QRadialGradient(QPointF(edge / 2, height / 2), max(edge, height) / 2)
        gradient.setColorAt(0.0, QColor(r, g, b, alpha))
        gradient.setColorAt(0.55, QColor(r, g, b, alpha // 2))
        gradient.setColorAt(1.0, QColor(r, g, b, 0))
        painter.fillRect(image.rect(), gradient)
        painter.end()
        pixmap = QPixmap.fromImage(image)
        self._cache[key] = pixmap
        return pixmap


class SvgIconProvider(QQuickImageProvider):
    def __init__(self) -> None:
        super().__init__(QQuickImageProvider.ImageType.Pixmap)
        self._cache: dict[tuple[str, str, int, int], QPixmap] = {}

    def requestPixmap(self, identifier: str, size, requested) -> QPixmap:
        try:
            return self._render(identifier, size, requested)
        except Exception:  # noqa: BLE001 - surface provider bugs to the console
            import traceback

            traceback.print_exc()
            return QPixmap()

    def _render(self, identifier: str, size, requested) -> QPixmap:
        name, _, color = identifier.partition("#")
        color = (color or "8D9BA3").lstrip("#")
        if len(color) == 8:  # Qt may serialize "#aarrggbb"
            color = color[2:]
        edge = requested.width() if requested.width() > 0 else 24
        height = requested.height() if requested.height() > 0 else edge
        # 按显示尺寸直接抗锯齿渲染：不超采样不缩小，细笔画最锐利。
        key = (name, color, edge, height)
        if key in self._cache:
            pixmap = self._cache[key]
        else:
            body = ICONS.get(name, ICONS.get("globe", ""))
            svg = (
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
                f'stroke="#{color}" stroke-width="{_STROKE_WIDTH}" stroke-linecap="round" '
                f'stroke-linejoin="round">{body}</svg>'
            )
            renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
            image = QImage(edge, height, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            renderer.render(painter)
            painter.end()
            pixmap = QPixmap.fromImage(image)
            self._cache[key] = pixmap
        if size is not None:
            size.setWidth(pixmap.width())
            size.setHeight(pixmap.height())
        return pixmap



__all__ = ['SvgIconProvider', 'GlowProvider']
