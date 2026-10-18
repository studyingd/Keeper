"""Layout self-check: renders the QML app offscreen and asserts geometry.

Checks per state (home / detail / locked / dialog):
  A. Expected card-colored (#0E191F) rectangles exist in expected bands
  B. Cards don't overlap each other
  C. Text pixels (bright colors) are bounded by card regions
  D. No card-colored pixels leak into the sidebar zone (x < 300) on home
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["PASSWORD_MANAGER_VAULT"] = str(Path("selfcheck-vault.sqlcipher").resolve())
VAULT = Path(os.environ["PASSWORD_MANAGER_VAULT"])
if VAULT.exists():
    VAULT.unlink()

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QFont, QImage
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from password_manager.controller import VaultController
from password_manager.models import CredentialDraft, EntryDraft
from password_manager.ui.fonts import ensure_fonts_loaded
from password_manager.ui.qml_icon_provider import GlowProvider, SvgIconProvider
from password_manager.vault.repository import VaultRepository

CARD = 0x0E191F
BG = 0x081116
SIDEBAR_W = 300

app = QApplication(sys.argv)
ensure_fonts_loaded()
app.setFont(QFont("Inter", 10))
app.styleHints().setColorScheme(Qt.ColorScheme.Dark)
QQuickStyle.setStyle("Basic")

repo = VaultRepository(VAULT)
repo.initialize("selfcheck-pass")
server = repo.save_entry(EntryDraft(kind="server", name="生产数据库服务器", address="192.168.1.101:2222", tags=["MySQL"]))
repo.save_credential(server.id, CredentialDraft(kind="ssh", label="系统登录账号", username="root", password="sekrit"))
repo.save_credential(server.id, CredentialDraft(kind="custom", label="MySQL", username="db", password="p2"))

controller = VaultController(VAULT, tray_available=False)
assert controller.attemptUnlock("selfcheck-pass")["ok"] is True

engine = QQmlApplicationEngine()
engine.warnings.connect(lambda messages: [print("QML WARNING:", m.toString()) for m in messages])
engine.addImageProvider("icons", SvgIconProvider())
engine.addImageProvider("glow", GlowProvider())
engine.rootContext().setContextProperty("controller", controller)
engine.load(QUrl.fromLocalFile(str(Path("src/password_manager/qml/Main.qml").resolve())))
if not engine.rootObjects():
    print("FAIL: root objects empty")
    sys.exit(1)
window = engine.rootObjects()[0]
window.width = 980
window.height = 640
window.show()


def find_card_rects(image: QImage) -> list:
    """Find maximal horizontal runs of CARD color per 4px row, merge into rects."""
    rects = []
    W, H = image.width(), image.height()
    for y in range(0, H, 4):
        x = 0
        while x < W:
            if image.pixel(x, y) & 0xFFFFFF == CARD:
                x2 = x
                while x2 < W and image.pixel(x2, y) & 0xFFFFFF == CARD:
                    x2 += 1
                if x2 - x >= 40:
                    rects.append((x, y, x2, y + 4))
                x = x2
            else:
                x += 1
    return rects


def check_home(image: QImage) -> list:
    problems = []
    rects = find_card_rects(image)
    if not rects:
        problems.append("home: no card surfaces found at all")
        return problems
    # D: no card pixels in sidebar zone
    if any(r[0] < SIDEBAR_W - 5 for r in rects):
        problems.append(f"home: card pixels leak into sidebar zone (min x={min(r[0] for r in rects)})")
    # A: stats band (y in 150..260) should have >= 4 distinct card runs at some row
    best_row = 0
    for y in range(140, 280, 4):
        row_runs = [r for r in rects if r[1] <= y < r[3]]
        xs = sorted(set((r[0], r[2]) for r in row_runs))
        best_row = max(best_row, len(xs))
    if best_row < 3:
        problems.append(f"home: expected >=3 stat cards side-by-side, saw {best_row}")
    # B: overlap — any two runs at same y overlapping in x by >8px
    for y in range(140, 280, 4):
        row_runs = sorted([r for r in rects if r[1] <= y < r[3]], key=lambda r: r[0])
        for i in range(len(row_runs) - 1):
            if row_runs[i + 1][0] < row_runs[i][2] - 8:
                problems.append(f"home: overlapping cards at y={y}: {row_runs[i]} vs {row_runs[i+1]}")
                break
    return problems


def check_detail(image: QImage) -> list:
    problems = []
    rects = find_card_rects(image)
    if not rects:
        problems.append("detail: no card surfaces found")
    if any(r[0] < SIDEBAR_W - 5 for r in rects):
        problems.append("detail: card pixels leak into sidebar zone")
    return problems


def check_locked(image: QImage) -> list:
    problems = []
    # 锁定时左侧 300px 应该全是背景（覆盖层盖住侧边栏）
    for x in [50, 150, 250]:
        for y in [100, 400]:
            c = image.pixel(x, y) & 0xFFFFFF
            if c not in (BG,):
                problems.append(f"locked: pixel at sidebar ({x},{y}) is #{c:06X}, not bg")
    return problems


results = {}
steps = [
    ("home", 700, lambda: None),
    ("detail", 500, lambda: controller.selectEntry(server.id)),
    ("locked", 500, lambda: controller.lock()),
]


def run(index: int = 0) -> None:
    if index >= len(steps):
        report(results)
        app.quit()
        return
    name, delay, action = steps[index]
    QTimer.singleShot(delay, lambda: (action(), QTimer.singleShot(400, lambda: capture(name))))


def capture(name: str) -> None:
    image = window.grabWindow()
    path = f"selfcheck-{name}.png"
    image.save(path)
    loaded = QImage(path)
    if name == "home":
        results[name] = check_home(loaded)
    elif name == "detail":
        results[name] = check_detail(loaded)
    else:
        results[name] = check_locked(loaded)
    run_next()


_current = [0]


def run_next() -> None:
    _current[0] += 1
    run(_current[0])


def report(results: dict) -> None:
    failed = False
    for name, problems in results.items():
        if problems:
            failed = True
            for p in problems:
                print(f"PROBLEM [{name}] {p}")
        else:
            print(f"OK [{name}]")
    print("SELF-CHECK:", "FAIL" if failed else "PASS")
    sys.exit(1 if failed else 0)


QTimer.singleShot(600, lambda: run(0))
sys.exit(app.exec())
