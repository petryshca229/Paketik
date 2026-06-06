"""
gui/widgets.py — Переиспользуемые виджеты Paketik 4.7.1
"""

from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGridLayout, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, pyqtProperty
from PyQt6.QtGui import QPainter, QColor, QLinearGradient, QGradient

from .theme import (
    C_CARD, C_BORDER, C_ACCENT, C_TEXT, C_MUTED, C_GREEN, C_YELLOW, C_RED,
    C_ACCENT2, C_PANEL, GRAD_TOP, GRAD_BOT, scale, app_font, stat_cell_style,
    section_label_style, btn_accent, btn_accent2, btn_save, btn_delete,
    btn_pause, btn_resume, _load_pixmap, card_style,
)


# ── SectionHeader ─────────────────────────────────────────────────────────────
class SectionHeader(QFrame):
    """Заголовок секции: иконка + текст."""

    def __init__(self, title: str, icon_name: str = None, parent=None):
        super().__init__(parent)
        self.setStyleSection = True
        layout = QHBoxLayout(self)
        layout.setContentsMargins(scale(18), scale(14), scale(12), scale(2))
        layout.setSpacing(scale(6))

        if icon_name:
            ico = _load_pixmap(icon_name, scale(15))
            lbl_ico = QLabel()
            lbl_ico.setPixmap(ico)
            layout.addWidget(lbl_ico)

        lbl = QLabel(title)
        lbl.setStyleSection = True
        lbl.setStyleSheet(section_label_style())
        layout.addWidget(lbl)
        layout.addStretch()


# ── CardFrame ────────────────────────────────────────────────────────────────
class CardFrame(QFrame):
    """Карточка с фоном C_CARD и border."""

    def __init__(self, parent=None, padding: int = 12):
        super().__init__(parent)
        self.setObjectName("card")
        self.setStyleSheet(card_style())
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(scale(1), scale(1), scale(1), scale(1))
        self._layout.setSpacing(scale(2))
        self._inner = QFrame()
        self._inner.setStyleSheet(f"background:{C_CARD}; border-radius:{scale(12)}px;")
        inner_layout = QVBoxLayout(self._inner)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        self._layout.addWidget(self._inner)

    def inner(self) -> QFrame:
        """Возвращает внутренний фрейм для добавления виджетов."""
        return self._inner

    def inner_layout(self) -> QVBoxLayout:
        return self._inner.layout()


# ── StatCell ────────────────────────────────────────────────────────────────
class StatCell(QFrame):
    """Одна ячейка статистики: label + value."""

    def __init__(self, label: str, color: str = C_ACCENT, parent=None):
        super().__init__(parent)
        self._color = color
        # Матовая плашка с лёгким градиентом и едва заметной подсветкой
        # цвета показателя по нижней кромке.
        self.setStyleSheet(
            f"QFrame {{"
            f"  background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            f"      stop:0 #1a1a30, stop:1 #121223);"
            f"  border:1px solid #20203a;"
            f"  border-bottom:2px solid {color};"
            f"  border-radius:{scale(9)}px;"
            f"}}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(scale(10), scale(7), scale(10), scale(7))
        layout.setSpacing(scale(1))

        self._label = QLabel(label)
        self._label.setStyleSheet(
            f"background:transparent; border:none; color:{C_MUTED};"
            f" font-family:'Segoe UI'; font-size:{max(8,int(9*1))}pt;"
            f" letter-spacing:0.3px;"
        )
        layout.addWidget(self._label)

        self._value = QLabel("—")
        self._value.setStyleSheet(
            f"background:transparent; border:none; color:{color};"
            f" font-family:'Segoe UI'; font-weight:bold; font-size:{max(9,int(18*1))}pt;"
        )

        # Масштабирование через property
        self._scale_val = 1.0
        layout.addWidget(self._value)

    def set_text(self, text: str):
        self._value.setText(text)

    def set_color(self, color: str):
        self._color = color
        self._value.setStyleSheet(
            f"background:transparent; border:none; color:{color};"
            f" font-family:'Segoe UI'; font-weight:bold; font-size:{max(9,int(18*self._scale_val))}pt;")


# ── StatGrid ─────────────────────────────────────────────────────────────────
class StatGrid(QFrame):
    """Сетка 2×3 статистики сессии."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # Общая матовая подложка с лёгким градиентом и рамкой вокруг блока.
        self.setObjectName("statgrid")
        self.setStyleSheet(
            f"QFrame#statgrid {{"
            f"  background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            f"      stop:0 #141426, stop:1 #0e0e1c);"
            f"  border:1px solid {C_BORDER};"
            f"  border-radius:{scale(13)}px; }}"
        )
        layout = QGridLayout(self)
        layout.setContentsMargins(scale(10), scale(10), scale(10), scale(10))
        layout.setHorizontalSpacing(scale(8))
        layout.setVerticalSpacing(scale(8))

        definitions = [
            ("Вопросов",  C_ACCENT),
            ("Действий",  C_ACCENT2),
            ("Токенов",   C_MUTED),
            ("Остаток",   C_GREEN),
            ("Время",     C_GREEN),
            ("Ошибок",    C_RED),
        ]

        self._cells: list[StatCell] = []
        for idx, (label, color) in enumerate(definitions):
            row = idx // 2
            col = idx % 2
            cell = StatCell(label, color)
            layout.addWidget(cell, row, col)
            self._cells.append(cell)

    def update_stats(self, stats: dict):
        """Обновляет все ячейки из словаря stats."""
        mapping = {
            "questions": 0,
            "actions":   1,
            "tokens":    2,
            "balance":   3,
            "time":      4,
            "errors":    5,
        }
        for key, idx in mapping.items():
            val = stats.get(key, "—")
            if key == "tokens":
                val = f"{val:,}".replace(",", " ") if isinstance(val, int) else str(val)
            elif key == "balance":
                val = f"{val:,}".replace(",", " ") if isinstance(val, int) else str(val)
            self._cells[idx].set_text(str(val))


# ── GradientHeader ───────────────────────────────────────────────────────────
class GradientHeader(QFrame):
    """Заголовок с gradient fill."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._top = GRAD_TOP
        self._bot = GRAD_BOT
        self.setMinimumHeight(scale(100))
        self.setMaximumHeight(scale(120))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        # Fill first to cover any anti-aliased edges before gradient
        painter.fillRect(rect, QColor(self._top))
        gradient = QLinearGradient(0, 0, 0, rect.height())
        gradient.setColorAt(0, QColor(self._top))
        gradient.setColorAt(1, QColor(self._bot))
        painter.fillRect(rect, gradient)
        super().paintEvent(event)


# ── ProgressBar ───────────────────────────────────────────────────────────────
class ProgressBar(QFrame):
    """Кастомный progress bar с градиентным цветом."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pct = 0.0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._bar = QFrame()
        self._bar.setFixedHeight(scale(7))
        self._bar.setStyleSheet(f"background:{C_BORDER}; border-radius:{scale(4)}px;")
        self._fill = QFrame(self._bar)
        self._fill.setFixedHeight(scale(7))
        self._fill.move(0, 0)
        layout.addWidget(self._bar)

    def set_progress(self, pct: float):
        self._pct = max(0.0, min(1.0, pct))
        w = int(self._bar.width() * self._pct)
        if w > 0:
            from .theme import progress_color
            self._fill.setFixedWidth(w)
            self._fill.setStyleSheet(
                f"background:{progress_color(self._pct)}; "
                f"border-radius:{scale(4)}px;"
            )
        else:
            self._fill.setFixedWidth(0)

    def resizeEvent(self, event):
        self.set_progress(self._pct)
        super().resizeEvent(event)


# ── ToggleSwitch ──────────────────────────────────────────────────────────────
from PyQt6.QtCore import pyqtSignal, QPropertyAnimation, QEasingCurve, QRectF


class ToggleSwitch(QPushButton):
    """Овальный тумблер (switch) с анимированным бегунком."""

    toggled_changed = pyqtSignal(bool)

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._w = scale(44)
        self._h = scale(24)
        self.setFixedSize(self._w, self._h)
        self.setStyleSheet("QPushButton { background: transparent; border: none; }")
        # 0.0 = выкл (слева), 1.0 = вкл (справа)
        self._pos = 1.0 if checked else 0.0
        self.setChecked(checked)
        self._anim = QPropertyAnimation(self, b"knob_pos", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.clicked.connect(self._on_clicked)

    def _on_clicked(self):
        self._animate_to(self.isChecked())
        self.toggled_changed.emit(self.isChecked())

    def _animate_to(self, on: bool):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def setChecked(self, on: bool):
        super().setChecked(on)
        self._pos = 1.0 if on else 0.0
        self.update()

    def get_knob_pos(self) -> float:
        return self._pos

    def set_knob_pos(self, v: float):
        self._pos = v
        self.update()

    knob_pos = pyqtProperty(float, fget=get_knob_pos, fset=set_knob_pos)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0, 0, self._w, self._h)
        radius = self._h / 2.0

        # Цвет дорожки: интерполяция серый → акцент
        off = QColor(C_BORDER)
        on = QColor(C_ACCENT)
        t = self._pos
        track = QColor(
            int(off.red()   + (on.red()   - off.red())   * t),
            int(off.green() + (on.green() - off.green()) * t),
            int(off.blue()  + (on.blue()  - off.blue())  * t),
        )
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(r, radius, radius)

        # Бегунок
        margin = scale(3)
        knob_d = self._h - margin * 2
        x_left = margin
        x_right = self._w - margin - knob_d
        x = x_left + (x_right - x_left) * self._pos
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(x, margin, knob_d, knob_d))
        p.end()
