"""Motion helpers: layered shadows and the animation curves from the demo.

QSS has no box-shadow, transform or transition, so the demo's visual motion
is rebuilt here with QGraphicsDropShadowEffect + QPropertyAnimation:

* shadow tokens  → drop_shadow() blur/offset/color pairs
* hover lift     → Card animates its shadow on enter/leave
* spring dialogs → dialog_spring() scales the window geometry with OutBack
* toast / fades  → fade_widget(), slide up + fade out
"""

from __future__ import annotations

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QDialog, QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QWidget

from password_manager.ui.theme import ACCENT, SHADOW_BASE

# Demo: cubic-bezier(0.22, 1, 0.36, 1) / cubic-bezier(0.34, 1.56, 0.64, 1)
EASE_OUT = QEasingCurve.Type.OutCubic
EASE_SPRING = QEasingCurve.Type.OutBack
DUR_FAST = 150
DUR_BASE = 250
DUR_SLOW = 400


def shadow_color(alpha: int) -> QColor:
    r, g, b = (int(SHADOW_BASE[i : i + 2], 16) for i in (1, 3, 5))
    return QColor(r, g, b, alpha)


def drop_shadow(
    widget: QWidget,
    *,
    blur: int = 18,
    dy: int = 6,
    alpha: int = 115,
    color: str | QColor | None = None,
) -> QGraphicsDropShadowEffect:
    """Apply (and return) a tinted layered-look shadow to ``widget``."""
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, dy)
    effect.setColor(QColor(color) if color is not None else shadow_color(alpha))
    widget.setGraphicsEffect(effect)
    return effect


def glow(widget: QWidget, *, blur: int = 20, dy: int = 4, alpha: int = 80, color: str = ACCENT) -> QGraphicsDropShadowEffect:
    """Accent glow used under primary buttons, tiles and checked type cards."""
    return drop_shadow(widget, blur=blur, dy=dy, alpha=alpha, color=color)


def fade_widget(widget: QWidget, *, start: float = 0.0, end: float = 1.0, duration: int = DUR_BASE, on_finished=None) -> None:
    """Fade a widget's opacity (the widget must not already own an effect)."""
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    effect.setOpacity(start)
    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(duration)
    animation.setStartValue(start)
    animation.setEndValue(end)
    animation.setEasingCurve(EASE_OUT)
    if on_finished is not None:
        animation.finished.connect(on_finished)
    animation.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
    widget._fade_animation = animation  # keep a reference alive


def dialog_spring(dialog: QDialog, *, duration: int = 340) -> None:
    """Scale the dialog in from 94% with a spring overshoot (demo dialogIn)."""
    dialog.setWindowOpacity(0.0)
    final = dialog.frameGeometry()
    center = final.center()
    start = QRectF(0, 0, final.width() * 0.94, final.height() * 0.94)
    start.moveCenter(center)
    dialog.setGeometry(start.toRect())
    geometry_animation = QPropertyAnimation(dialog, b"geometry", dialog)
    geometry_animation.setDuration(duration)
    geometry_animation.setStartValue(start.toRect())
    geometry_animation.setEndValue(final)
    geometry_animation.setEasingCurve(EASE_SPRING)
    geometry_animation.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
    opacity_animation = QPropertyAnimation(dialog, b"windowOpacity", dialog)
    opacity_animation.setDuration(DUR_BASE)
    opacity_animation.setStartValue(0.0)
    opacity_animation.setEndValue(1.0)
    opacity_animation.setEasingCurve(EASE_OUT)
    opacity_animation.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
    dialog._spring_geometry = geometry_animation
    dialog._spring_opacity = opacity_animation


def pulse_forever(widget: QWidget, *, duration: int = 2400, low: float = 0.45) -> None:
    """The vault-status dot's breathing loop (demo `@keyframes pulse`)."""
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(duration)
    animation.setStartValue(1.0)
    animation.setKeyValueAt(0.5, low)
    animation.setEndValue(1.0)
    animation.setLoopCount(-1)
    animation.setEasingCurve(QEasingCurve.Type.InOutSine)
    animation.start()
    widget._pulse_animation = animation


__all__ = [
    "DUR_BASE",
    "DUR_FAST",
    "DUR_SLOW",
    "EASE_OUT",
    "EASE_SPRING",
    "dialog_spring",
    "drop_shadow",
    "fade_widget",
    "glow",
    "pulse_forever",
    "shadow_color",
]
