"""Reusable UI building blocks shared by the home page and dialogs."""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetItem,
)

from password_manager.generator import (
    GENERATED_PASSWORD_LENGTH,
    entropy_bits,
    generate_password,
    strength_label,
    strength_level,
)
from password_manager.ui.icons import icon
from password_manager.ui.motion import DUR_FAST, EASE_OUT, drop_shadow
from password_manager.ui.theme import (
    ACCENT,
    DANGER,
    OK,
    SURFACE_2,
    WARNING,
)

CHARSET_LABELS = (("digits", "数字 0-9"), ("letters", "英文 aA"), ("symbols", "符号 !@#"))


# ---------------------------------------------------------------------------
# Flow layout: pills wrap onto the next row instead of stretching.
# ---------------------------------------------------------------------------


class FlowLayout(QLayout):
    def __init__(self, parent: QWidget | None = None, margin: int = 0, spacing: int = 5) -> None:
        super().__init__(parent)
        self.setContentsMargins(margin, margin, margin, margin)
        self._spacing = spacing
        self._items: list[QWidgetItem] = []

    def addItem(self, item) -> None:  # type: ignore[override] # noqa: ANN001
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self) -> bool:  # type: ignore[override]
        return True

    def heightForWidth(self, width: int) -> int:  # type: ignore[override]
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:  # type: ignore[override]
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:  # type: ignore[override]
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # type: ignore[override]
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        margins = self.contentsMargins()
        effective = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x, y = effective.x(), effective.y()
        line_height = 0
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + self._spacing
            if next_x - self._spacing > effective.right() + 1 and line_height > 0:
                x = effective.x()
                y = y + line_height + self._spacing
                next_x = x + hint.width() + self._spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + margins.bottom()


# ---------------------------------------------------------------------------
# Card: shadow at rest, a deeper shadow (the hover "lift") on enter, and an
# optional widget revealed by an opacity fade (the demo's hover-actions).
# ---------------------------------------------------------------------------


class Card(QFrame):
    def __init__(self, parent: QWidget | None = None, *, reveal: QWidget | None = None, object_name: str = "card") -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        self._reveal = reveal
        self._reveal_effect: QGraphicsOpacityEffect | None = None
        self._shadow = drop_shadow(self, blur=18, dy=6, alpha=115)
        if reveal is not None:
            self._reveal_effect = QGraphicsOpacityEffect(reveal)
            self._reveal_effect.setOpacity(0.0)
            reveal.setGraphicsEffect(self._reveal_effect)
        self._hover_animations: list = []

    def _animate_shadow(self, blur: float, dy: float) -> None:
        for previous in self._hover_animations:
            previous.stop()
        self._hover_animations.clear()
        blur_animation = QPropertyAnimation(self._shadow, b"blurRadius", self)
        blur_animation.setDuration(DUR_FAST)
        blur_animation.setEndValue(blur)
        blur_animation.setEasingCurve(EASE_OUT)
        blur_animation.start()
        offset_animation = QPropertyAnimation(self._shadow, b"offset", self)
        offset_animation.setDuration(DUR_FAST)
        offset_animation.setEndValue(QPointF(0, dy))
        offset_animation.setEasingCurve(EASE_OUT)
        offset_animation.start()
        self._hover_animations = [blur_animation, offset_animation]

    def _animate_reveal(self, to: float) -> None:
        if self._reveal_effect is None:
            return
        animation = QPropertyAnimation(self._reveal_effect, b"opacity", self)
        animation.setDuration(DUR_FAST)
        animation.setEndValue(to)
        animation.setEasingCurve(EASE_OUT)
        animation.start()
        self._hover_animations.append(animation)

    def enterEvent(self, event) -> None:  # type: ignore[override] # noqa: ANN001
        self._animate_shadow(blur=34, dy=10)
        self._animate_reveal(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[override] # noqa: ANN001
        self._animate_shadow(blur=18, dy=6)
        self._animate_reveal(0.0)
        super().leaveEvent(event)


# ---------------------------------------------------------------------------
# Toast: transient notification anchored to the parent window's bottom-right.
# ---------------------------------------------------------------------------


class Toast(QLabel):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("toast")
        self.setWordWrap(False)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)
        parent.installEventFilter(self)

    def show_message(self, text: str, msecs: int = 2600) -> None:
        self.setText(text)
        self.adjustSize()
        self._reposition()
        target = self.pos()
        slide = QPropertyAnimation(self, b"pos", self)
        slide.setDuration(300)
        slide.setStartValue(target + QPoint(0, 14))
        slide.setEndValue(target)
        slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        slide.start()
        self._slide = slide
        self.show()
        self.raise_()
        self._timer.start(msecs)

    def _fade_out(self) -> None:
        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        fade = QPropertyAnimation(effect, b"opacity", self)
        fade.setDuration(300)
        fade.setStartValue(1.0)
        fade.setEndValue(0.0)
        fade.finished.connect(self.hide)
        fade.start()
        self._fade = fade

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        margin = 20
        self.move(
            parent.width() - self.width() - margin,
            parent.height() - self.height() - margin,
        )

    def eventFilter(self, watched, event) -> bool:  # type: ignore[override] # noqa: ANN001
        if event.type() == QEvent.Type.Resize and self.isVisible():
            self._reposition()
        return super().eventFilter(watched, event)


# ---------------------------------------------------------------------------
# Strength meter: four segments painted from level state, single data source.
# ---------------------------------------------------------------------------


class StrengthMeter(QWidget):
    """Four-segment strength bar; fills animate like the demo's scaleX transition."""

    LEVEL_COLORS = (QColor(DANGER), QColor(WARNING), QColor(ACCENT), QColor(OK))

    def __init__(self, parent: QWidget | None = None, *, compact: bool = False) -> None:
        super().__init__(parent)
        self._level = 0
        self._fill = 0.0
        self._compact = compact
        self.setFixedHeight(4 if compact else 5)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._animation: QVariantAnimation | None = None

    def set_level(self, level: int) -> None:
        level = max(0, min(4, level))
        if level == self._level:
            return
        self._level = level
        if self._animation is not None:
            self._animation.stop()
        animation = QVariantAnimation(self)
        animation.setDuration(500)
        animation.setStartValue(self._fill)
        animation.setEndValue(float(level))
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.valueChanged.connect(lambda value: (setattr(self, "_fill", float(value)), self.update()))
        animation.start()
        self._animation = animation

    def level(self) -> int:
        return self._level

    def set_bits(self, bits: float) -> None:
        self.set_level(strength_level(bits))

    def paintEvent(self, event) -> None:  # type: ignore[override] # noqa: ANN001
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        segment_count = 4
        gap = 4
        segment_width = max(1.0, (self.width() - gap * (segment_count - 1)) / segment_count)
        radius = self.height() / 2
        color = self.LEVEL_COLORS[self._level - 1] if self._level else QColor(SURFACE_2)
        painter.setPen(Qt.PenStyle.NoPen)
        for index in range(segment_count):
            x = index * (segment_width + gap)
            track = QRectF(x, 0, segment_width, self.height())
            painter.setBrush(QColor(SURFACE_2))
            painter.drawRoundedRect(track, radius, radius)
            filled = min(1.0, max(0.0, self._fill - index))
            if filled > 0:
                painter.setBrush(color)
                painter.drawRoundedRect(QRectF(x, 0, segment_width * filled, self.height()), radius, radius)


# ---------------------------------------------------------------------------
# Charset toggles: free selection with an enforced minimum of one set.
# ---------------------------------------------------------------------------


class CharSetToggles(QWidget):
    """Checkable 数字 / 英文 / 符号 pills; the last checked one stays on."""

    selection_changed = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        initial: tuple[str, ...] = ("digits", "letters", "symbols"),
    ) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(7)
        self._buttons: dict[str, QToolButton] = {}
        for key, text in CHARSET_LABELS:
            button = QToolButton()
            button.setObjectName("charToggle")
            button.setText(text)
            button.setCheckable(True)
            button.setChecked(key in initial)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(self._sync)
            self._buttons[key] = button
            row.addWidget(button)
        row.addStretch(1)
        self._apply_minimum_rule()

    def selected_keys(self) -> list[str]:
        return [key for key, _ in CHARSET_LABELS if self._buttons[key].isChecked()]

    def button(self, key: str) -> QToolButton:
        """Public accessor (used by tests and fine-grained styling)."""
        return self._buttons[key]

    def _apply_minimum_rule(self) -> None:
        keys = self.selected_keys()
        for key, button in self._buttons.items():
            # Only one set left: it is disabled so the pool can never be empty.
            button.setEnabled(not (len(keys) == 1 and key in keys))

    def _sync(self) -> None:
        if not self.selected_keys():
            # Unchecking the last set is refused: re-check the sender.
            sender = self.sender()
            if isinstance(sender, QToolButton):
                sender.setChecked(True)
        self._apply_minimum_rule()
        self.selection_changed.emit()


# ---------------------------------------------------------------------------
# Password generator panel (home page flavour).
# ---------------------------------------------------------------------------


class PasswordGenerator(Card):
    """Result, strength meter, charset toggles, length slider and generate."""

    password_generated = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)

        heading = QLabel("随机密码生成器")
        heading.setObjectName("h3")
        layout.addWidget(heading)

        result_row = QHBoxLayout()
        result_row.setSpacing(8)
        self.result = QLineEdit()
        self.result.setObjectName("genResult")
        self.result.setReadOnly(True)
        self.result.setPlaceholderText("生成的密码会显示在这里")
        result_row.addWidget(self.result, 1)
        self.copy_button = QToolButton()
        self.copy_button.setObjectName("iconButton")
        self.copy_button.setIcon(icon("copy"))
        self.copy_button.setToolTip("复制生成的密码（30 秒后自动清除）")
        result_row.addWidget(self.copy_button)
        layout.addLayout(result_row)

        strength_row = QHBoxLayout()
        strength_row.setSpacing(10)
        self.strength = StrengthMeter()
        strength_row.addWidget(self.strength, 1)
        self.strength_label = QLabel("—")
        self.strength_label.setFixedWidth(36)
        self.strength_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        strength_row.addWidget(self.strength_label)
        layout.addLayout(strength_row)

        controls = QHBoxLayout()
        controls.setSpacing(14)
        self.toggles = CharSetToggles()
        self.toggles.selection_changed.connect(self.generate_password)
        controls.addWidget(self.toggles)
        length_box = QHBoxLayout()
        length_box.setSpacing(9)
        length_label = QLabel("长度")
        length_label.setObjectName("muted")
        length_box.addWidget(length_label)
        self.length_slider = QSlider(Qt.Orientation.Horizontal)
        self.length_slider.setRange(1, 128)
        self.length_slider.setValue(GENERATED_PASSWORD_LENGTH)
        self.length_slider.setFixedWidth(140)
        self.length_slider.valueChanged.connect(self.generate_password)
        length_box.addWidget(self.length_slider)
        self.length_value = QLabel(str(GENERATED_PASSWORD_LENGTH))
        self.length_value.setObjectName("mono")
        length_box.addWidget(self.length_value)
        controls.addLayout(length_box)
        controls.addStretch(1)
        self.generate = QPushButton("生成密码")
        self.generate.setProperty("variant", "primary")
        self.generate.clicked.connect(self.generate_password)
        controls.addWidget(self.generate)
        layout.addLayout(controls)

    @property
    def length(self) -> QSlider:
        """Slider-based length control (the previous UI exposed a QLineEdit)."""
        return self.length_slider

    def selected_keys(self) -> list[str]:
        return self.toggles.selected_keys()

    def generate_password(self) -> None:
        keys = self.toggles.selected_keys()
        length = self.length_slider.value()
        password = generate_password("+".join(keys), length)
        self.result.setText(password)
        self.length_value.setText(str(length))
        bits = entropy_bits(length, keys)
        self.strength.set_bits(bits)
        self.strength_label.setText(strength_label(strength_level(bits)))
        self.password_generated.emit(password)


# ---------------------------------------------------------------------------
# Tag editor: pill flow + inline input + quick-pick suggestions.
# ---------------------------------------------------------------------------


class TagEdit(QWidget):
    """Free-form tag input with removable pills and suggested tags."""

    MAX_TAGS = 8

    tags_changed = Signal()

    def __init__(self, suggestions: list[str] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tags: list[str] = []
        self._suggestions = list(suggestions or [])
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(8)

        self.input_box = QFrame()
        self.input_box.setObjectName("tagBox")
        self.pill_layout = FlowLayout(spacing=5)
        self.input_box.setLayout(self.pill_layout)
        self.input = QLineEdit()
        self.input.setPlaceholderText("输入后回车添加")
        self.input.setFrame(False)
        self.input.setFixedHeight(26)
        self.input.setMinimumWidth(140)
        self.input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.input.returnPressed.connect(self.commit)
        self.input.installEventFilter(self)
        self.pill_layout.addWidget(self.input)
        column.addWidget(self.input_box)

        self._suggest_buttons: list[QToolButton] = []
        self._suggest_row: QHBoxLayout | None = None
        if self._suggestions:
            self._build_suggestions()

    def _build_suggestions(self) -> None:
        """(Re)build the quick-pick row from ``self._suggestions``."""
        if self._suggest_row is None:
            self._suggest_row = QHBoxLayout()
            self._suggest_row.setSpacing(6)
            self.layout().addLayout(self._suggest_row)
        while self._suggest_row.count():
            item = self._suggest_row.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.deleteLater()
        self._suggest_buttons = []
        for tag in self._suggestions:
            suggest = QToolButton()
            suggest.setObjectName("tagSuggest")
            suggest.setText(tag)
            suggest.setCheckable(True)
            suggest.setCursor(Qt.CursorShape.PointingHandCursor)
            suggest.clicked.connect(lambda _checked=False, name=tag: self.toggle_tag(name))
            self._suggest_buttons.append(suggest)
            self._suggest_row.addWidget(suggest)
        self._suggest_row.addStretch(1)
        for button in self._suggest_buttons:
            button.setChecked(button.text() in self._tags)

    def set_suggestions(self, suggestions: list[str]) -> None:
        self._suggestions = list(suggestions)
        self._build_suggestions()

    def tags(self) -> list[str]:
        return list(self._tags)

    def set_tags(self, tags: list[str]) -> None:
        seen: list[str] = []
        for raw in tags:
            tag = raw.strip()
            if tag and tag not in seen:
                seen.append(tag)
        self._tags = seen[: self.MAX_TAGS]
        self._render_pills()

    def toggle_tag(self, tag: str) -> None:
        tag = tag.strip()
        if not tag:
            return
        if tag in self._tags:
            self._tags.remove(tag)
        elif len(self._tags) < self.MAX_TAGS:
            self._tags.append(tag)
        self._render_pills()

    def commit(self) -> None:
        parts = [part.strip() for part in self.input.text().replace("，", ",").split(",") if part.strip()]
        added = False
        for part in parts:
            if part not in self._tags and len(self._tags) < self.MAX_TAGS:
                self._tags.append(part)
                added = True
        self.input.clear()
        if added:
            self._render_pills()

    def eventFilter(self, watched, event) -> bool:  # type: ignore[override] # noqa: ANN001
        if watched is self.input and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Backspace and not self.input.text() and self._tags:
                self._tags.pop()
                self._render_pills()
                return True
        return super().eventFilter(watched, event)

    def _render_pills(self) -> None:
        while self.pill_layout.count():
            item = self.pill_layout.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None and widget is not self.input:
                widget.deleteLater()
        for tag in self._tags:
            pill = QToolButton()
            pill.setObjectName("tagPill")
            pill.setText(tag)
            pill.setCursor(Qt.CursorShape.ArrowCursor)
            pill.setToolTip("点击移除标签")
            pill.clicked.connect(lambda _checked=False, name=tag: self.toggle_tag(name))
            self.pill_layout.addWidget(pill)
        self.pill_layout.addWidget(self.input)  # input stays at the flow's end
        for button in self._suggest_buttons:
            button.setChecked(button.text() in self._tags)
        self.tags_changed.emit()


__all__ = [
    "CHARSET_LABELS",
    "Card",
    "FlowLayout",
    "Toast",
    "StrengthMeter",
    "CharSetToggles",
    "PasswordGenerator",
    "TagEdit",
]
