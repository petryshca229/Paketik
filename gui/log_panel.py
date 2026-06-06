"""
gui/log_panel.py — Панель журнала работы агента (QTextEdit readonly)
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, QScrollBar, QFrame
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QTextCursor, QFont

from .theme import (
    LOG_W,
    C_LOG_BG, C_ACCENT, C_MUTED, C_CARD, C_BORDER, C_TEXT, C_BG,
    scale, log_font, log_style, _load_icon,
)


class LogPanel(QWidget):
    """Правая панель: журнал логов агента."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # Минимальная ширина (а не фиксированная) — чтобы журнал растягивался
        # вместе с окном, а не оставался узкой колонкой.
        self.setMinimumWidth(LOG_W)
        from PyQt6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet(f"background:{C_BG};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        hdr = QFrame()
        hdr.setStyleSheet(f"background:#0d0d1e;")
        hdr.setFixedHeight(scale(38))
        hdr_layout = QHBoxLayout(hdr)
        hdr_layout.setContentsMargins(scale(14), 0, scale(10), 0)

        lbl = QPushButton("[Журнал]  Работа агента")
        lbl.setCursor(Qt.CursorShape.ArrowCursor)
        lbl.setDisabled(True)
        lbl.setStyleSection = True
        lbl.setStyleSheet(
            f"QPushButton {{ background:transparent; color:#7070a0; border:none;"
            f" font-family:'Segoe UI'; font-size:{max(9,int(11*1))}pt; font-weight:bold; }}"
            f"QPushButton:disabled {{ color:#7070a0; }}"
        )
        hdr_layout.addWidget(lbl)

        btn_clear = QPushButton("Очистить")
        btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clear.setFixedSize(scale(80), scale(24))
        btn_clear.setStyleSection = True
        btn_clear.setStyleSheet(
            f"QPushButton {{ background:{C_CARD}; color:{C_TEXT};"
            f" border-radius:{scale(6)}px; font-family:'Segoe UI'; font-size:{max(8,int(10*1))}pt; }}"
            f"QPushButton:hover {{ background:{C_BORDER}; }}"
        )
        btn_clear.clicked.connect(self._clear)
        hdr_layout.addWidget(btn_clear)

        layout.addWidget(hdr)

        # Log text area
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setStyleSheet(log_style())
        self._log.setFont(log_font(11))
        layout.addWidget(self._log)

        # Initial messages
        self.append("[OK] Paketik готов к работе")
        import config
        self.append(f"   Версия: {config.APP_VERSION}")
        self.append(f"   Сайт: {config.TARGET_URL}")
        self.append("─" * 22)

    @pyqtSlot(str)
    def append(self, message: str):
        """Добавить строку в лог с timestamp."""
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")

        # Цвет по префиксу
        color = "#9090b8"
        if message.startswith("[OK]") or message.startswith("[>]"):
           color = "#3ddc97"
        elif message.startswith("[!]") or message.startswith("❌"):
           color = "#e05c5c"
        elif message.startswith("[*]") or message.startswith("⚠"):
           color = "#f7c948"
        elif message.startswith("[i]") or message.startswith("ℹ"):
           color = "#5c9cf5"

        cursor = self._log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        # Timestamp
        ts_format = f'<span style="color:{C_MUTED}">[{ts}]</span> '
        # Strip emoji for colored rendering
        clean = self._strip_emoji(message)
        line_format = f'{ts_format}<span style="color:{color}">{clean}</span><br/>'

        self._log.insertHtml(line_format)
        self._log.verticalScrollBar().setValue(
            self._log.verticalScrollBar().maximum()
        )

    @staticmethod
    def _strip_emoji(text: str) -> str:
        """Убирает emoji-символы для HTML rendering."""
        import re
        # Remove emoji Unicode ranges
        return re.sub(
            r'['
            '\U0001F300-\U0001F9FF'
            '\U00002600-\U000026FF'
            '\U0001F000-\U0001F02F'
            '\U0001F0CF-\U0001F0FF'
            '\U00002300-\U000023FF'
            ']+',
            '',
            text
        )

    def _clear(self):
        self._log.clear()

    def set_font_size(self, size: int):
        self._log.setFont(log_font(size))