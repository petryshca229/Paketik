"""
gui/results_window.py — Окно с результатами теста (показывается после закрытия браузера)
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QWidget,
)
from PyQt6.QtCore import Qt

from .theme import (
    C_BG, C_PANEL, C_CARD, C_BORDER, C_ACCENT, C_TEXT, C_MUTED,
    C_GREEN, C_RED, scale,
)


class ResultsWindow(QDialog):
    """Окно итогов теста: верно/неверно, оценка, разбивка по темам."""

    def __init__(self, results: dict, parent=None):
        super().__init__(parent)
        self._results = results or {}

        self.setWindowTitle("Результаты теста")
        self.setMinimumSize(scale(460), scale(420))
        self.resize(scale(500), scale(520))
        self.setStyleSheet(f"background:{C_BG};")
        if parent:
            self.move(
                parent.x() + (parent.width() - self.width()) // 2,
                parent.y() + (parent.height() - self.height()) // 2,
            )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        hdr = QFrame()
        hdr.setStyleSheet(f"background:{C_PANEL};")
        hdr.setFixedHeight(scale(54))
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(scale(16), 0, scale(16), 0)
        title = QLabel("Результаты теста")
        title.setStyleSheet(
            f"color:{C_ACCENT}; font-family:'Segoe UI'; font-weight:bold;"
            f" font-size:{max(11,int(15*1))}pt;"
        )
        hl.addWidget(title)
        layout.addWidget(hdr)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background:{C_BG}; border:none; }}
            QScrollBar:vertical {{ background:{C_BORDER}; width:{scale(8)}px;
                border-radius:{scale(4)}px; }}
            QScrollBar::handle:vertical {{ background:{C_ACCENT};
                border-radius:{scale(4)}px; min-height:{scale(20)}px; }}
        """)
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(scale(16), scale(14), scale(16), scale(14))
        bl.setSpacing(scale(10))

        r = self._results
        # Заголовок теста
        if r.get("title"):
            bl.addWidget(self._line(r["title"], color=C_TEXT, bold=True, size=13))
        if r.get("discipline"):
            bl.addWidget(self._line(f"Дисциплина: {r['discipline']}", color=C_MUTED, size=10))

        # Карточка с основными цифрами
        card = self._card()
        cl = card.layout()
        self._add_stat(cl, "Всего вопросов", r.get("total", "—"), C_TEXT)
        self._add_stat(cl, "Введено ответов", r.get("answered", "—"), C_TEXT)
        self._add_stat(cl, "Верно", r.get("correct", "—"), C_GREEN)
        self._add_stat(cl, "Неверно", r.get("wrong", "—"), C_RED)
        bl.addWidget(card)

        # Оценка/заключение — крупно
        grade = r.get("grade", "")
        if grade:
            gcard = self._card()
            gl = gcard.layout()
            gv = QLabel(grade)
            gv.setWordWrap(True)
            gv.setStyleSheet(
                f"color:{C_GREEN}; font-family:'Segoe UI'; font-weight:bold;"
                f" font-size:{max(12,int(16*1))}pt; background:transparent; border:none;"
            )
            gl.addWidget(gv)
            bl.addWidget(gcard)

        # Разбивка по темам
        themes = r.get("themes") or []
        if themes:
            bl.addWidget(self._line("По темам:", color=C_MUTED, bold=True, size=11))
            for t in themes:
                tcard = self._card(pad=8)
                tl = tcard.layout()
                name = QLabel(str(t.get("name", "")))
                name.setWordWrap(True)
                name.setStyleSheet(
                    f"color:{C_TEXT}; font-family:'Segoe UI'; font-size:{max(8,int(10*1))}pt;"
                    f" background:transparent; border:none;"
                )
                tl.addWidget(name)
                row = QLabel(f"✅ {t.get('correct', 0)}    ❌ {t.get('wrong', 0)}")
                row.setStyleSheet(
                    f"color:{C_MUTED}; font-family:'Segoe UI'; font-size:{max(8,int(10*1))}pt;"
                    f" background:transparent; border:none;"
                )
                tl.addWidget(row)
                bl.addWidget(tcard)

        bl.addStretch()
        scroll.setWidget(body)
        layout.addWidget(scroll, stretch=1)

        # Footer
        footer = QFrame()
        footer.setStyleSheet(f"background:{C_BG};")
        footer.setFixedHeight(scale(60))
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(scale(16), scale(10), scale(16), scale(10))
        btn = QPushButton("Закрыть")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setMinimumHeight(scale(38))
        btn.setStyleSheet(
            f"QPushButton {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            f"  stop:0 #8b7bff, stop:1 #6c5ce0); color:white; border:none;"
            f"  border-radius:{scale(8)}px; padding:{scale(8)}px;"
            f"  font-family:'Segoe UI'; font-size:{max(9,int(11*1))}pt; font-weight:bold; }}"
            f"QPushButton:hover {{ background:#7a6cf2; }}"
        )
        btn.clicked.connect(self.accept)
        fl.addWidget(btn)
        layout.addWidget(footer)

    # ── helpers ──────────────────────────────────────────────────────────
    def _line(self, text: str, color=C_TEXT, bold=False, size=11) -> QLabel:
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        w = "bold" if bold else "normal"
        lbl.setStyleSheet(
            f"color:{color}; font-family:'Segoe UI'; font-weight:{w};"
            f" font-size:{max(8,int(size*1))}pt; background:transparent; border:none;"
        )
        return lbl

    def _card(self, pad: int = 12) -> QFrame:
        c = QFrame()
        c.setStyleSheet(
            f"QFrame {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            f"  stop:0 #16162a, stop:1 #111122); border:1px solid {C_BORDER};"
            f"  border-radius:{scale(10)}px; }}"
        )
        lay = QVBoxLayout(c)
        lay.setContentsMargins(scale(pad), scale(pad), scale(pad), scale(pad))
        lay.setSpacing(scale(4))
        return c

    def _add_stat(self, layout, label: str, value, color):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        l = QLabel(label)
        l.setStyleSheet(
            f"color:{C_MUTED}; font-family:'Segoe UI'; font-size:{max(8,int(10*1))}pt;"
            f" background:transparent; border:none;"
        )
        row.addWidget(l)
        row.addStretch()
        v = QLabel(str(value))
        v.setStyleSheet(
            f"color:{color}; font-family:'Segoe UI'; font-weight:bold;"
            f" font-size:{max(9,int(12*1))}pt; background:transparent; border:none;"
        )
        row.addWidget(v)
        layout.addLayout(row)
