"""Design tokens and the global QSS stylesheet.

Every color here is the *exact* OKLCH→sRGB conversion of the token with the
same name in docs/ui-redesign-demo.html (see scripts/oklch_convert.py for the
math), so the Qt build renders the same palette the HTML demo does. Layered
CSS shadows become QGraphicsDropShadowEffect parameters (see ui/motion.py);
gradients that QSS can express are inlined below.
"""

# --- surfaces & neutrals (hue 235) ---
BG_DEEP = "#050B10"
BG = "#081116"
SURFACE = "#0E191F"
SURFACE_2 = "#142027"
BORDER = "#223039"
BORDER_SOFT = "#1A262D"
BORDER_STRONG = "#334550"
SIDEBAR_TOP = "#0F1B22"
SIDEBAR_BOTTOM = "#0A141A"
BTN_HOVER = "#1B2831"
ROW_HOVER = "#18262E"
ROW_SELECTED = "#082E38"
MENU_BG = "#17252D"
TOAST_BG = "#16242C"

# --- text ---
TEXT = "#E6ECF0"
TEXT_MUTED = "#8D9BA3"
TEXT_FAINT = "#6B767E"

# --- accent (hue 185) ---
ACCENT = "#51D2C4"
ACCENT_STRONG = "#73E3D5"
ACCENT_DEEP = "#003038"
ACCENT_INK = "#00191D"

# --- semantic ---
OK = "#59D38C"
WARNING = "#E7B643"
DANGER = "#FF645F"

# --- shadow / glow source colors (demo: oklch(0.10 0.02 235) tinted) ---
SHADOW_BASE = "#000408"
GLOW_TEAL = "#00252B"   # demo: oklch(0.24 0.045 210) at 35% alpha
GLOW_BLUE = "#001B1D"   # demo: oklch(0.20 0.040 200) at 45% alpha

# --- alpha composites used across QSS ---
def _rgba(hex_color: str, alpha: int) -> str:
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r}, {g}, {b}, {alpha})"


ACCENT_DIM = _rgba(ACCENT, 36)          # 14%
ACCENT_BORDER = _rgba(ACCENT, 115)      # 45%
ACCENT_GLOWBORDER = _rgba(ACCENT, 89)   # 35%
DANGER_DIM = _rgba(DANGER, 31)          # 12%
ROW_HOVER_A = _rgba(ROW_HOVER, 178)     # 70%
ROW_SELECTED_A = _rgba(ROW_SELECTED, 140)  # 55%
TOAST_BG_A = _rgba(TOAST_BG, 245)

MONO_FAMILY = '"JetBrains Mono", "Cascadia Mono", Consolas, "Courier New", monospace'
BODY_FAMILY = '"Inter", "Noto Sans SC", "Segoe UI Variable", "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif'
DISPLAY_FAMILY = '"Space Grotesk", "Inter", "Noto Sans SC", "Segoe UI Variable", sans-serif'

STYLESHEET = f"""
QWidget {{ color: {TEXT}; font-family: {BODY_FAMILY}; font-size: 13px; }}
QMainWindow {{ background: {BG}; }}
QDialog {{ background: {BG}; }}
QWidget#workspace {{ background: {BG}; }}
QStackedWidget#pages, QWidget#emptyPage, QWidget#lockedPage, QWidget#detailPage {{ background: transparent; }}

/* ---------- 侧边栏（垂直渐变） ---------- */
QFrame#sidebar {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {SIDEBAR_TOP}, stop:1 {SIDEBAR_BOTTOM});
    border-right: 1px solid {BORDER_SOFT};
}}
QFrame#vaultStatus {{ background: {BG_DEEP}; border: 1px solid {BORDER_SOFT}; border-radius: 10px; }}
QLabel#statusDot {{ background: {OK}; border-radius: 3px; max-width: 6px; max-height: 6px; }}
QLabel#brandName {{ font-family: {DISPLAY_FAMILY}; font-size: 16px; font-weight: 700; }}
QLabel#brandSub {{ color: {TEXT_FAINT}; font-size: 11px; }}
QLabel#groupLabel {{ color: {TEXT_FAINT}; font-size: 11px; font-weight: 600; background: transparent; }}

QToolButton#tile {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {ACCENT_DEEP}, stop:1 {SURFACE});
    border: 1px solid {ACCENT_GLOWBORDER}; border-radius: 15px;
}}
QToolButton#tileSmall {{ background: {SURFACE_2}; border: 1px solid {BORDER_SOFT}; border-radius: 9px; }}
QToolButton#brandMark {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {ACCENT_STRONG}, stop:1 {ACCENT});
    border: none; border-radius: 10px;
}}

/* ---------- 通用按钮 ---------- */
QPushButton {{ background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 10px; padding: 9px 16px; font-weight: 600; }}
QPushButton:hover {{ background: {BTN_HOVER}; border-color: {BORDER_STRONG}; }}
QPushButton:pressed {{ background: {BG_DEEP}; }}
QPushButton:focus {{ border: 1px solid {ACCENT}; }}
QPushButton:disabled {{ background: {BG_DEEP}; color: {TEXT_FAINT}; border-color: {BORDER_SOFT}; }}
QPushButton[variant="primary"] {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #7EE7D9, stop:1 #4BCFC4);
    color: {ACCENT_INK}; border: 1px solid #4BCFC4; font-weight: 700;
}}
QPushButton[variant="primary"]:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #87F7E9, stop:1 #62E2D5);
    border-color: #62E2D5;
}}
QPushButton[variant="primary"]:disabled {{ background: {SURFACE}; color: {TEXT_FAINT}; border-color: {BORDER_SOFT}; }}
QPushButton[variant="danger"] {{ background: {SURFACE_2}; color: {DANGER}; border: 1px solid {_rgba(DANGER, 90)}; }}
QPushButton[variant="ghost"] {{ background: transparent; border: 1px solid transparent; color: {TEXT_MUTED}; }}
QPushButton[variant="ghost"]:hover {{ color: {TEXT}; background: {SURFACE_2}; }}

/* 图标按钮 */
QToolButton#iconButton {{ background: transparent; border: 1px solid transparent; border-radius: 8px; padding: 3px; }}
QToolButton#iconButton:hover {{ background: {SURFACE_2}; border-color: {BORDER}; }}
QToolButton#iconButton:pressed {{ background: {BG_DEEP}; }}
QToolButton#iconButton:disabled {{ background: transparent; border-color: transparent; }}
QToolButton#iconButton[flat="true"] {{ border: none; }}
QToolButton#iconButton[bordered="true"] {{ background: {SURFACE_2}; border: 1px solid {BORDER}; }}
QToolButton#iconButton[danger="true"]:hover {{ background: {DANGER_DIM}; border-color: {_rgba(DANGER, 90)}; }}

/* 筛选 chips / 字符集勾选 / 标签快捷点选（胶囊） */
QToolButton#chip, QToolButton#charToggle, QToolButton#tagSuggest {{
    background: {BG_DEEP}; color: {TEXT_MUTED}; border: 1px solid {BORDER_SOFT};
    border-radius: 14px; padding: 6px 14px; font-weight: 600; font-size: 12px;
}}
QToolButton#chip:hover, QToolButton#charToggle:hover, QToolButton#tagSuggest:hover {{ border-color: {BORDER_STRONG}; color: {TEXT}; }}
QToolButton#chip:checked, QToolButton#charToggle:checked, QToolButton#tagSuggest:checked {{
    background: {ACCENT_DIM}; color: {ACCENT}; border-color: {ACCENT_BORDER};
}}
QToolButton#chip:disabled, QToolButton#charToggle:disabled {{ color: {TEXT_FAINT}; border-color: {BORDER_SOFT}; background: {BG_DEEP}; }}

/* 新增资产对话框的类型卡片 */
QToolButton#typeCard {{
    background: {BG_DEEP}; border: 2px solid {BORDER_SOFT}; border-radius: 14px;
    padding: 12px 16px; font-size: 14px; font-weight: 700; text-align: left;
}}
QToolButton#typeCard:hover {{ border-color: {BORDER_STRONG}; }}
QToolButton#typeCard:checked {{
    border-color: {ACCENT};
    background: qlineargradient(x1:0, y1:0, x2:0.4, y2:1, stop:0 {ACCENT_DEEP}, stop:0.7 {BG_DEEP});
}}

/* 标签胶囊 / 标签输入框 */
QToolButton#tagPill {{
    background: {ACCENT_DIM}; color: {ACCENT}; border: 1px solid {ACCENT_BORDER};
    border-radius: 12px; padding: 2px 7px 2px 11px; font-size: 12px; font-weight: 600;
}}
QToolButton#tagPill:hover {{ border-color: {ACCENT}; }}
QFrame#tagBox {{ background: {BG_DEEP}; border: 1px solid {BORDER_SOFT}; border-radius: 10px; padding: 5px 10px; }}

/* ---------- 文本 ---------- */
QLabel {{ background: transparent; }}
QLabel#eyebrow {{ color: {ACCENT}; font-size: 11px; font-weight: 700; }}
QLabel#muted {{ color: {TEXT_MUTED}; }}
QLabel#faint {{ color: {TEXT_FAINT}; }}
QLabel#error {{ color: {DANGER}; }}
QLabel#h1 {{ font-family: {DISPLAY_FAMILY}; font-size: 27px; font-weight: 700; }}
QLabel#h2 {{ font-family: {DISPLAY_FAMILY}; font-size: 20px; font-weight: 700; }}
QLabel#h3 {{ font-family: {DISPLAY_FAMILY}; font-size: 15px; font-weight: 700; }}
QLabel#statNum {{ font-family: {DISPLAY_FAMILY}; font-size: 30px; font-weight: 700; }}
QLabel#mono {{ font-family: {MONO_FAMILY}; }}
QLabel#hchip {{ background: {SURFACE}; border: 1px solid {BORDER_SOFT}; border-radius: 12px; padding: 3px 11px; color: {TEXT_MUTED}; font-size: 12px; }}
QLabel#hchip[mono="true"] {{ font-family: {MONO_FAMILY}; color: {TEXT}; font-size: 11px; }}
QLabel#hchip[tag="true"] {{ color: {ACCENT}; border-color: {ACCENT_BORDER}; background: {ACCENT_DIM}; }}
QLabel#miniTag {{ color: {TEXT_FAINT}; border: 1px solid {BORDER_SOFT}; border-radius: 10px; padding: 0px 7px; font-size: 10px; }}
QLabel#entryCount {{ color: {TEXT_FAINT}; background: {SURFACE_2}; border: 1px solid {BORDER_SOFT}; border-radius: 10px; padding: 1px 7px; font-size: 11px; font-weight: 600; }}
QLabel#toast {{ background: {TOAST_BG_A}; border: 1px solid {BORDER_STRONG}; border-radius: 10px; padding: 10px 16px; color: {TEXT}; font-weight: 500; }}

/* ---------- 输入控件 ---------- */
QLineEdit {{ background: {BG_DEEP}; border: 1px solid {BORDER_SOFT}; border-radius: 10px; padding: 10px 13px; selection-background-color: {ACCENT}; selection-color: {ACCENT_INK}; }}
QLineEdit:focus {{ border: 1px solid {ACCENT}; }}
QLineEdit:disabled {{ background: {SURFACE}; color: {TEXT_FAINT}; }}
QLineEdit::placeholder {{ color: {TEXT_FAINT}; }}
QLineEdit[mono="true"] {{ font-family: {MONO_FAMILY}; }}
QLineEdit#genResult {{ font-family: {MONO_FAMILY}; font-size: 16px; font-weight: 600; padding: 12px 14px; }}

QSlider::groove:horizontal {{ height: 4px; background: {SURFACE_2}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {TEXT}; width: 14px; height: 14px; margin: -6px 0; border-radius: 7px; }}
QSlider::handle:horizontal:hover {{ background: {ACCENT_STRONG}; }}
QSlider::handle:horizontal:disabled {{ background: {BORDER_STRONG}; }}

QRadioButton {{ spacing: 8px; }}
QRadioButton::indicator {{ width: 16px; height: 16px; border-radius: 9px; border: 2px solid {BORDER_STRONG}; background: {BG_DEEP}; }}
QRadioButton::indicator:checked {{ border-color: {ACCENT}; background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5, stop:0.55 {ACCENT}, stop:0.6 {BG_DEEP}); }}

/* ---------- 卡片与列表 ---------- */
QFrame#card {{ background: {SURFACE}; border: 1px solid {BORDER_SOFT}; border-radius: 16px; }}
QFrame#card[accent="true"] {{ border-left: 3px solid {ACCENT}; }}
QFrame#statCard {{ background: {SURFACE}; border: 1px solid {BORDER_SOFT}; border-radius: 16px; }}
QFrame#dialogSurface {{
    background: {SURFACE}; border: 1px solid {BORDER};
    border-top: 1px solid rgba(255, 255, 255, 26); border-radius: 20px;
}}

QListWidget {{ background: transparent; border: none; outline: none; padding: 0 6px; }}
QListWidget::item {{ border-radius: 12px; margin: 1px 0; }}
QListWidget::item:hover {{ background: {ROW_HOVER_A}; }}
QListWidget::item:selected {{ background: {ROW_SELECTED_A}; border-left: 3px solid {ACCENT}; }}
QListWidget::item:focus {{ outline: none; }}
QWidget#entryItem {{ background: transparent; }}

/* ---------- 结构 ---------- */
QSplitter::handle {{ background: {BORDER_SOFT}; }}
QSplitter::handle:hover {{ background: {BORDER_STRONG}; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget#qt_scrollarea_viewport {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; min-height: 28px; border-radius: 5px; }}
QScrollBar::handle:vertical:hover {{ background: {BORDER_STRONG}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QStatusBar {{ background: {SURFACE}; color: {TEXT_MUTED}; border-top: 1px solid {BORDER_SOFT}; }}
QMessageBox {{ background: {MENU_BG}; }}
QToolTip {{ background: {SURFACE_2}; color: {TEXT}; border: 1px solid {BORDER_STRONG}; padding: 5px; }}
"""
