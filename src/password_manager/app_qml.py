"""QML application entry: engine, controller wiring and single instance."""

from __future__ import annotations

import signal
import sys
from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from password_manager.app import _allow_console_interrupt, application_icon
from password_manager.controller import (
    DEFAULT_VAULT,
    VaultController,
    acquire_single_instance,
)
from password_manager.ui.fonts import ensure_fonts_loaded
from password_manager.ui.qml_icon_provider import GlowProvider, SvgIconProvider

QML_DIR = Path(__file__).parent / "qml"


def _activate(window) -> None:  # noqa: ANN001
    window.show()
    window.raise_()
    window.requestActivate()


def main() -> None:
    application = QApplication.instance() or QApplication(sys.argv)
    application.setApplicationName("Keeper")
    ensure_fonts_loaded()
    # 全局字体：QML 未显式指定 family 的文本（按钮/输入框/列表）都会继承它，
    # 避免和显式 Inter 标题混排造成的错位观感；中文按字形回退到系统 CJK 字体。
    from PySide6.QtGui import QFont

    application.setFont(QFont("Inter", 10))
    try:
        application.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    except (AttributeError, RuntimeError):
        pass
    QQuickStyle.setStyle("Basic")
    icon = application_icon()
    if not icon.isNull():
        application.setWindowIcon(icon)
    palette = QPalette()
    from password_manager.ui.theme import ACCENT, ACCENT_INK, BG, BG_DEEP, SURFACE, SURFACE_2, TEXT

    palette.setColor(QPalette.ColorRole.Window, QColor(BG))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor(BG_DEEP))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    application.setPalette(palette)

    instance, already_running = acquire_single_instance(DEFAULT_VAULT)
    if already_running:
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.information(None, "Keeper", "Keeper 已经在运行，已把它的窗口调到前台。")
        return

    controller = VaultController(DEFAULT_VAULT)
    engine = QQmlApplicationEngine()
    engine.addImageProvider("icons", SvgIconProvider())
    engine.addImageProvider("glow", GlowProvider())
    engine.rootContext().setContextProperty("controller", controller)
    engine.load(QUrl.fromLocalFile(str(QML_DIR / "Main.qml")))
    if not engine.rootObjects():
        print("QML 加载失败：", [error.toString() for error in engine.errors()], file=sys.stderr)
        sys.exit(1)
    window = engine.rootObjects()[0]

    controller.showWindowRequested.connect(lambda: _activate(window))
    controller.quitRequested.connect(application.quit)
    if instance is not None:
        instance.newConnection.connect(lambda: _activate(window))

    _allow_console_interrupt(application, window)
    window.show()
    sys.exit(application.exec())


if __name__ == "__main__":
    main()
