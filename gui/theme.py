"""
gui/theme.py — Цветовая палитра, стили, константы интерфейса Paketik 4.7.1
"""

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor, QFont, QPalette, QIcon, QPixmap, QPainter, QPen
from PyQt6.QtWidgets import QProxyStyle, QStyleFactory
from pathlib import Path

# ── Цветовая палитра ─────────────────────────────────────────────────────────
C_BG       = "#0b0b14"
C_PANEL    = "#10101c"
C_CARD     = "#16162a"
C_BORDER   = "#252540"
C_ACCENT   = "#7c6cf2"
C_ACCENT2  = "#5c9cf5"
C_GREEN    = "#3ddc97"
C_YELLOW   = "#f7c948"
C_RED      = "#e05c5c"
C_TEXT     = "#e8e8f2"
C_MUTED    = "#5a5a7a"
C_LOG_BG   = "#08080f"
GRAD_TOP   = "#1e1248"
GRAD_BOT   = "#0b0b18"
C_SURFACE  = "#0e0e1e"   # input fields, dropdowns

# ── Размеры ───────────────────────────────────────────────────────────────────
PANEL_W    = 380
LOG_W      = 400
SETTINGS_W = 300

# ── Settings persistence ─────────────────────────────────────────────────────
SETTINGS_FILE = Path.home() / ".paketik" / "settings.json"
DEFAULT_SETTINGS = {
    "font_family":    "Segoe UI Semibold",
    "font_size_base":  14,
    "scale":          1.0,
    # Громкость звуковых уведомлений (0..100). 0 = выключено.
    "vol_ai_error":     70,   # два таймаута/ошибки ИИ подряд
    "vol_test_done":    80,   # тест завершён
    "vol_error":        70,   # любая другая ошибка (не связана с ИИ)
    # Пропускать вопросы с картинками (сопоставление чертежей) — по умолчанию ВЫКЛ.
    "skip_image_questions": False,
}


def _load_settings() -> dict:
    try:
        if SETTINGS_FILE.exists():
            return {**DEFAULT_SETTINGS, **json.loads(SETTINGS_FILE.read_text())}
    except Exception:
        pass
    return dict(DEFAULT_SETTINGS)


def _save_settings(s: dict):
    try:
        import json
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2))
    except Exception:
        pass


import json as _json
_settings = _load_settings()


# ── UI-state persistence (открытые панели, последний профиль) ─────────────────
UI_STATE_FILE = Path.home() / ".paketik" / "ui_state.json"
DEFAULT_UI_STATE = {
    "settings_open": False,   # панель настроек по умолчанию закрыта
    "logs_open":     False,   # панель логов по умолчанию закрыта
    "last_profile":  "",      # последний выбранный профиль
}


def load_ui_state() -> dict:
    """Читает сохранённое состояние интерфейса (открытые панели, профиль)."""
    try:
        if UI_STATE_FILE.exists():
            return {**DEFAULT_UI_STATE, **_json.loads(UI_STATE_FILE.read_text(encoding="utf-8"))}
    except Exception:
        pass
    return dict(DEFAULT_UI_STATE)


def save_ui_state(state: dict):
    """Сохраняет состояние интерфейса между запусками."""
    try:
        UI_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        merged = {**DEFAULT_UI_STATE, **state}
        UI_STATE_FILE.write_text(
            _json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def scale(base: int) -> int:
    """Масштабирование размера."""
    return max(1, int(base * _settings["scale"]))


def app_font(rel: int = 0, weight: str = "normal") -> QFont:
    """Шрифт интерфейса."""
    size = max(8, int(_settings["font_size_base"] * _settings["scale"]) + rel)
    fam = _settings.get("font_family", "Segoe UI")
    f = QFont(fam, size)
    if weight == "bold":
        f.setBold(True)
    return f


def log_font(size: int = 12) -> QFont:
    """Моноширинный шрифт для логов."""
    return QFont("Consolas", int(size * _settings["scale"]))


# ── Progress bar color ───────────────────────────────────────────────────────
def progress_color(pct: float) -> str:
    """Цвет progress bar в зависимости от процента."""
    if pct < 0.6:
        t = pct / 0.6
        r = int(0x3d + (0xf7 - 0x3d) * t)
        g = int(0xdc + (0xc9 - 0xdc) * t)
        b = int(0x97 + (0x48 - 0x97) * t)
    else:
        t = (pct - 0.6) / 0.4
        r = int(0xf7 + (0xe0 - 0xf7) * t)
        g = int(0xc9 + (0x5c - 0xc9) * t)
        b = int(0x48 + (0x5c - 0x48) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


# ── Stylesheet builders ─────────────────────────────────────────────────────
def btn_accent(hover: str = None) -> str:
    return (
        f"QPushButton {{"
        f"  background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
        f"      stop:0 #8b7bff, stop:1 #6c5ce0);"
        f"  color:white; border:none;"
        f"  border-radius:{scale(10)}px; padding:{scale(8)}px {scale(16)}px;"
        f"  font-family:'Segoe UI'; font-size:{max(9,int(12*_settings['scale']))}pt;"
        f"  font-weight:bold;"
        f"}}"
        f"QPushButton:hover {{"
        f"  background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
        f"      stop:0 #9a8bff, stop:1 #7a6cf2); }}"
        f"QPushButton:disabled {{ background:#1e1e2e; color:#3a3a5a; }}"
    )


def btn_accent2(hover: str = None) -> str:
    return (
        f"QPushButton {{"
        f"  background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
        f"      stop:0 #6fb0ff, stop:1 #4a82e8);"
        f"  color:white; border:none;"
        f"  border-radius:{scale(10)}px; padding:{scale(8)}px {scale(16)}px;"
        f"  font-family:'Segoe UI'; font-size:{max(9,int(13*_settings['scale']))}pt;"
        f"  font-weight:bold;"
        f"}}"
        f"QPushButton:hover {{"
        f"  background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
        f"      stop:0 #7fbcff, stop:1 #5a92f5); }}"
        f"QPushButton:disabled {{ background:#1e1e2e; color:#3a3a5a; }}"
    )


def btn_save() -> str:
    return (
        f"QPushButton {{"
        f"  background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
        f"      stop:0 #1f4030, stop:1 #16301f);"
        f"  color:{C_GREEN}; border:1px solid #3a6e4a;"
        f"  border-radius:{scale(8)}px; padding:{scale(6)}px;"
        f"  font-family:'Segoe UI'; font-size:{max(9,int(11*_settings['scale']))}pt;"
        f"  font-weight:bold;"
        f"}}"
        f"QPushButton:hover {{"
        f"  background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
        f"      stop:0 #275438, stop:1 #1c3e28);"
        f"  border:1px solid {C_GREEN}; }}"
        f"QPushButton:disabled {{ background:#1a1a2a; color:#3a5a4a; border-color:#2a3a2a; }}"
    )


def btn_delete() -> str:
    return (
        f"QPushButton {{"
        f"  background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
        f"      stop:0 #46201f, stop:1 #331717);"
        f"  color:{C_RED}; border:1px solid #6e3a3a;"
        f"  border-radius:{scale(8)}px; padding:{scale(6)}px;"
        f"  font-family:'Segoe UI'; font-size:{max(9,int(11*_settings['scale']))}pt;"
        f"  font-weight:bold;"
        f"}}"
        f"QPushButton:hover {{"
        f"  background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
        f"      stop:0 #5a2826, stop:1 #3e1c1c);"
        f"  border:1px solid {C_RED}; }}"
        f"QPushButton:disabled {{ background:#1a1a2a; color:#5a3a3a; border-color:#3a2a2a; }}"
    )


def btn_pause() -> str:
    return (
        f"QPushButton {{"
        f"  background:#1e1808; color:{C_YELLOW}; border:1px solid #6a5800;"
        f"  border-radius:{scale(8)}px; padding:{scale(6)}px;"
        f"  font-family:'Segoe UI'; font-size:{max(9,int(11*_settings['scale']))}pt;"
        f"}}"
        f"QPushButton:hover {{ background:#2e2410; }}"
        f"QPushButton:disabled {{ background:#1e1e2e; color:#3a3a5a; border-color:#252540; }}"
    )


def btn_resume() -> str:
    return (
        f"QPushButton {{"
        f"  background:#0a1e10; color:{C_GREEN}; border:1px solid {C_GREEN};"
        f"  border-radius:{scale(8)}px; padding:{scale(6)}px;"
        f"  font-family:'Segoe UI'; font-size:{max(9,int(11*_settings['scale']))}pt;"
        f"}}"
        f"QPushButton:hover {{ background:#0e2e18; }}"
    )


def card_style() -> str:
    return (
        f"QFrame#card {{"
        f"  background:{C_CARD}; border:1px solid {C_BORDER};"
        f"  border-radius:{scale(13)}px;"
        f"}}"
    )


def section_label_style() -> str:
    return (
        f"color:{C_MUTED}; font-family:'Segoe UI'; font-weight:bold;"
        f" font-size:{max(8,int(10*_settings['scale']))}pt;"
        f" letter-spacing:0.5px;"
    )


def input_style() -> str:
    return (
        f"QLineEdit, QTextEdit {{"
        f"  background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
        f"      stop:0 #14142a, stop:1 #0e0e1e);"
        f"  color:{C_TEXT}; border:1px solid {C_BORDER};"
        f"  border-radius:{scale(8)}px; padding:{scale(8)}px;"
        f"  font-family:'Segoe UI'; font-size:{max(9,int(12*_settings['scale']))}pt;"
        f"  selection-background-color:{C_ACCENT};"
        f"}}"
        f"QLineEdit:hover, QTextEdit:hover {{ border:1px solid #3a3a60; }}"
        f"QLineEdit:focus, QTextEdit:focus {{ border:1px solid {C_ACCENT}; }}"
    )


def combo_style() -> str:
    return (
        f"QComboBox {{"
        f"  background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
        f"      stop:0 #1a1a30, stop:1 #131325);"
        f"  color:{C_TEXT}; border:1px solid {C_BORDER};"
        f"  border-radius:{scale(8)}px;"
        f"  padding:{scale(8)}px {scale(28)}px {scale(8)}px {scale(10)}px;"
        f"  font-family:'Segoe UI'; font-size:{max(9,int(12*_settings['scale']))}pt;"
        f"}}"
        f"QComboBox:hover {{"
        f"  border:1px solid {C_ACCENT};"
        f"  background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
        f"      stop:0 #22223e, stop:1 #181830);"
        f"}}"
        f"QComboBox:on {{ border:1px solid {C_ACCENT}; }}"
        f"QComboBox::drop-down {{"
        f"  subcontrol-origin: padding; subcontrol-position: center right;"
        f"  width:{scale(24)}px; border:none; margin-right:{scale(2)}px;"
        f"}}"
        # Стрелка, нарисованная средствами CSS (border-треугольник)
        f"QComboBox::down-arrow {{"
        f"  image:none; width:0; height:0;"
        f"  border-left:{scale(5)}px solid transparent;"
        f"  border-right:{scale(5)}px solid transparent;"
        f"  border-top:{scale(6)}px solid {C_MUTED};"
        f"  margin-right:{scale(8)}px;"
        f"}}"
        f"QComboBox::down-arrow:hover {{ border-top-color:{C_ACCENT}; }}"
        f"QComboBox QAbstractItemView {{"
        f"  background:{C_CARD}; color:{C_TEXT};"
        f"  border:1px solid {C_ACCENT};"
        f"  border-radius:{scale(8)}px; padding:{scale(4)}px;"
        f"  outline:none;"
        f"  selection-background-color:{C_ACCENT};"
        f"  selection-color:white;"
        f"}}"
        f"QComboBox QAbstractItemView::item {{"
        f"  padding:{scale(6)}px {scale(8)}px; border-radius:{scale(6)}px;"
        f"  min-height:{scale(22)}px;"
        f"}}"
        f"QComboBox QAbstractItemView::item:hover {{"
        f"  background:{C_BORDER};"
        f"}}"
    )


def log_style() -> str:
    return (
        f"QTextEdit {{"
        f"  background:{C_LOG_BG}; color:#9090b8;"
        f"  border:none; padding:{scale(8)}px;"
        f"  font-family:'Consolas'; font-size:{max(9,int(11*_settings['scale']))}pt;"
        f"  selection-background-color:{C_ACCENT};"
        f"}}"
    )


def progress_style() -> str:
    return (
        f"QProgressBar {{"
        f"  background:{C_BORDER}; border:none; border-radius:{scale(4)}px;"
        f"  height:{scale(7)}px; text-align:center;"
        f"  font-size:{max(8,int(9*_settings['scale']))}pt;"
        f"}}"
        f"QProgressBar::chunk {{ border-radius:{scale(4)}px; }}"
    )


def stat_cell_style() -> str:
    return (
        f"QFrame {{"
        # Без рамок на каждой ячейке — общая рамка рисуется вокруг всего блока.
        f"  background:#111124; border:none;"
        f"  border-radius:{scale(10)}px;"
        f"}}"
    )


# ── Иконки ───────────────────────────────────────────────────────────────────
_icon_cache = {}


def _load_icon(name: str, size: int = 18) -> QIcon:
    """Загружает иконку. Пробует res/icons/, затем assets/."""
    if name in _icon_cache:
        return _icon_cache[name]

    base = Path(__file__).parent.parent
    for subdir in ["res/icons", "assets"]:
        p = base / subdir / name
        if p.exists():
            try:
                pm = QPixmap(str(p))
                if not pm.isNull():
                    if pm.width() != size or pm.height() != size:
                        pm = pm.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)
                    ico = QIcon(pm)
                    if not ico.isNull():
                        _icon_cache[name] = ico
                        return ico
            except Exception:
                pass

    # Fallback: пустая прозрачная иконка
    empty = QPixmap(size, size)
    empty.fill(QColor(0, 0, 0, 0))
    _icon_cache[name] = QIcon(empty)
    return _icon_cache[name]


def _load_pixmap(name: str, size: int = 18) -> QPixmap:
    """Загружает QPixmap напрямую (минуя QIcon кэш)."""
    base = Path(__file__).parent.parent
    for subdir in ["res/icons", "assets"]:
        p = base / subdir / name
        if p.exists():
            try:
                pm = QPixmap(str(p))
                if not pm.isNull():
                    if pm.width() != size or pm.height() != size:
                        pm = pm.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)
                    return pm
            except Exception:
                pass
    empty = QPixmap(size, size)
    empty.fill(QColor(0, 0, 0, 0))
    return empty


# ── Настройка палитры приложения ─────────────────────────────────────────────
class _NoFocusRectStyle(QProxyStyle):
    """Fusion-стиль без рисования focus-прямоугольника.

    Именно PE_FrameFocusRect давал светлые (белые) линии вокруг кнопок при
    фокусе/наведении. Переопределяем drawPrimitive и пропускаем его.
    """
    def drawPrimitive(self, element, option, painter, widget=None):
        from PyQt6.QtWidgets import QStyle
        if element == QStyle.PrimitiveElement.PE_FrameFocusRect:
            return  # не рисуем обводку фокуса
        super().drawPrimitive(element, option, painter, widget)


def apply_dark_palette(app) -> None:
    """Устанавливает тёмную палитру для всего приложения."""
    app.setStyle(_NoFocusRectStyle(QStyleFactory.create("Fusion")))
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(C_BG))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(C_TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor(C_SURFACE))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(C_CARD))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(C_ACCENT))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(C_TEXT))
    palette.setColor(QPalette.ColorRole.Text, QColor(C_TEXT))
    palette.setColor(QPalette.ColorRole.Button, QColor(C_BORDER))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(C_TEXT))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(C_TEXT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(C_ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(C_TEXT))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(C_MUTED))
    app.setPalette(palette)

    # Глобально убираем светлую focus-обводку Fusion вокруг кнопок/полей —
    # именно она давала странные белые линии по краям кнопок.
    app.setStyleSheet(
        "QPushButton { outline: none; }"
        "QPushButton:focus { outline: none; }"
        "QToolButton { outline: none; }"
        "QComboBox { outline: none; }"
        "QComboBox:focus { outline: none; }"
        "QLineEdit:focus { outline: none; }"
        "QTextEdit:focus { outline: none; }"
        "QAbstractItemView { outline: none; }"
        "*:focus { outline: none; }"
    )
