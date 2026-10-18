"""QML application entry: engine, controller wiring and single instance."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QUrl
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
    QQuickStyle.setStyle("Basic")
    icon = application_icon()
    if not icon.isNull():
        application.setWindowIcon(icon)
    # Fusion + dark palette + QSS for the QtWidgets surfaces the QML app still
    # shows (tray menu, message boxes); Qt Quick rendering is unaffected.
    from password_manager.ui.theme import apply_widget_chrome

    apply_widget_chrome(application)

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
        # In a windowed (console-less) build both std streams are None, so a
        # plain print is silently swallowed and the user sees a flash-crash
        # with nothing to act on. Show the failure in a dialog instead; the
        # stderr line remains for source runs and CI logs.
        details = "; ".join(error.toString() for error in engine.errors())
        if sys.stderr is not None:
            print("QML 加载失败：", details, file=sys.stderr)
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.critical(None, "Keeper", f"QML 界面加载失败，程序即将退出。\n\n{details}")
        sys.exit(1)
    window = engine.rootObjects()[0]

    controller.showWindowRequested.connect(lambda: _activate(window))
    controller.quitRequested.connect(application.quit)
    # Safety net for every exit path (including Qt.quit() and the last window
    # closing without a tray): lock the vault and wipe the clipboard one last
    # time. prepareQuit is idempotent, so a second call after the QML closing
    # handler is harmless.
    application.aboutToQuit.connect(controller.prepareQuit)
    if instance is not None:
        instance.newConnection.connect(lambda: _activate(window))

    _allow_console_interrupt(application, window)
    window.show()
    sys.exit(application.exec())


if __name__ == "__main__":
    main()
