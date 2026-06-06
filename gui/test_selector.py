"""
gui/test_selector.py — Диалог выбора теста
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QScrollArea, QWidget,
    QLabel, QPushButton, QFrame, QGridLayout
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont

from .theme import (
    C_BG, C_PANEL, C_CARD, C_BORDER, C_ACCENT, C_TEXT, C_MUTED,
    C_ACCENT2, C_RED, C_GREEN, scale, btn_accent, btn_accent2, btn_delete,
    _load_icon, load_ui_state, save_ui_state,
)


class ManualHintDialog(QDialog):
    """Поясняющее окошко для кнопки «Выбрать самому».

    Кнопки: «Закрыть» и «Больше не показывать» (сохраняется в ui_state).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dont_show = False

        self.setWindowTitle("Ручной выбор теста")
        self.setModal(True)
        self.setMinimumWidth(scale(420))
        self.setStyleSheet(f"background:{C_BG};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(scale(20), scale(18), scale(20), scale(16))
        layout.setSpacing(scale(14))

        msg = QLabel(
            "У вас есть 15 секунд, чтобы открыть нужный тест в браузере вручную.\n\n"
            "Если за это время вы не выберете тест — ИИ приступит сам "
            "к тому тесту, который открыт на экране."
        )
        msg.setWordWrap(True)
        msg.setStyleSheet(
            f"color:{C_TEXT}; font-family:'Segoe UI'; font-size:{max(9,int(11*1))}pt;"
        )
        layout.addWidget(msg)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(scale(10))

        btn_close = QPushButton("Закрыть")
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setMinimumHeight(scale(36))
        btn_close.setStyleSheet(
            f"QPushButton {{ background:{C_ACCENT}; color:white; border:none;"
            f" border-radius:{scale(8)}px; padding:{scale(8)}px {scale(14)}px;"
            f" font-family:'Segoe UI'; font-size:{max(9,int(11*1))}pt; font-weight:bold; }}"
            f"QPushButton:hover {{ background:#6355d4; }}"
        )
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close, stretch=1)

        btn_never = QPushButton("Больше не показывать")
        btn_never.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_never.setMinimumHeight(scale(36))
        btn_never.setStyleSheet(
            f"QPushButton {{ background:{C_CARD}; color:{C_MUTED};"
            f" border:1px solid {C_BORDER};"
            f" border-radius:{scale(8)}px; padding:{scale(8)}px {scale(14)}px;"
            f" font-family:'Segoe UI'; font-size:{max(9,int(11*1))}pt; }}"
            f"QPushButton:hover {{ background:{C_BORDER}; color:{C_TEXT}; }}"
        )
        btn_never.clicked.connect(self._on_never)
        btn_row.addWidget(btn_never, stretch=1)

        layout.addLayout(btn_row)

    def _on_never(self):
        self._dont_show = True
        try:
            state = load_ui_state()
            state["dont_show_manual_hint"] = True
            save_ui_state(state)
        except Exception:
            pass
        self.accept()



class TestCard(QFrame):
    """Карточка одного теста."""

    clicked = pyqtSignal(dict)  # test dict

    def __init__(self, test: dict, parent=None):
        super().__init__(parent)
        self._test = test

        self.setStyleSheet(
            f"QFrame {{ background:{C_CARD}; border:1px solid {C_BORDER};"
            f" border-radius:{scale(10)}px; padding:{scale(4)}px; }}"
            f"QFrame:hover {{ border:1px solid {C_ACCENT}; }}"
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(scale(12), scale(10), scale(12), scale(10))
        layout.setSpacing(scale(4))

        # Name
        name = test.get("name", "—")
        lbl_name = QLabel(name)
        lbl_name.setWordWrap(True)
        lbl_name.setStyleSection = True
        lbl_name.setStyleSheet(
            f"color:{C_TEXT}; font-family:'Segoe UI'; font-weight:bold;"
            f" font-size:{max(10,int(12*1))}pt;"
        )
        layout.addWidget(lbl_name)

        # Subject
        subj = test.get("subject", "")
        if subj:
            lbl_subj = QLabel(f"Предмет: {subj}")
            lbl_subj.setStyleSection = True
            lbl_subj.setStyleSheet(
                f"color:{C_MUTED}; font-family:'Segoe UI'; font-size:{max(9,int(10*1))}pt;"
            )
            layout.addWidget(lbl_subj)

        # Meta info
        meta_parts = []
        if test.get("time_limit"):
            meta_parts.append(f"{test['time_limit']}")
        if test.get("questions"):
            meta_parts.append(f"{test['questions']} вопросов")
        if test.get("author"):
            meta_parts.append(f"{test['author']}")
        if test.get("date"):
            meta_parts.append(f"{test['date']}")
        if test.get("status"):
            meta_parts.append(f"{test['status']}")

        if meta_parts:
            lbl_meta = QLabel("   ".join(meta_parts))
            lbl_meta.setStyleSection = True
            lbl_meta.setStyleSheet(
                f"color:{C_MUTED}; font-family:'Segoe UI'; font-size:{max(8,int(9*1))}pt;"
            )
            layout.addWidget(lbl_meta)

        # Choose button
        btn = QPushButton("Выбрать")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton {{ background:{C_ACCENT2}; color:white; border:none;"
            f" border-radius:{scale(8)}px; padding:{scale(6)}px;"
            f" font-family:'Segoe UI'; font-size:{max(9,int(11*1))}pt; font-weight:bold; }}"
            f"QPushButton:hover {{ background:#4a82e0; }}"
        )
        btn.clicked.connect(lambda: self.clicked.emit(test))
        layout.addWidget(btn)

    def enterEvent(self, event):
        self.setStyleSheet(
            f"QFrame {{ background:{C_CARD}; border:1px solid {C_ACCENT};"
            f" border-radius:{scale(10)}px; padding:{scale(4)}px; }}"
        )
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setStyleSheet(
            f"QFrame {{ background:{C_CARD}; border:1px solid {C_BORDER};"
            f" border-radius:{scale(10)}px; padding:{scale(4)}px; }}"
        )
        super().leaveEvent(event)


class TestSelectorDialog(QDialog):
    """
    Модальный диалог: пользователь выбирает тест из списка.

    Поведение:
      • клик по карточке теста → этот тест выбран, ИИ открывает его;
      • кнопка «Выбрать самому» → пользователь сам откроет тест в браузере,
        ИИ просто продолжит с текущим открытым тестом;
      • если ничего не выбрано за AUTO_START_SECONDS секунд → ИИ приступает сам.
    """

    test_selected = pyqtSignal(dict)   # выбранный тест (пустой dict = «сам/таймаут»)

    AUTO_START_SECONDS = 15

    def __init__(self, tests: list, parent=None):
        super().__init__(parent)
        self._tests = tests
        self._selected_test: dict | None = None
        self._manual = False
        self._remaining = self.AUTO_START_SECONDS

        self.setWindowTitle("Выберите тест")
        self.setMinimumSize(scale(620), scale(560))
        self.resize(scale(660), scale(600))
        self.setModal(True)
        self.setStyleSheet(f"background:{C_BG};")

        # Center on parent
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
        hdr.setFixedHeight(scale(50))
        hdr_layout = QHBoxLayout(hdr)
        hdr_layout.setContentsMargins(scale(14), 0, scale(14), 0)

        lbl = QLabel("Доступные тесты")
        lbl.setStyleSheet(
            f"color:{C_ACCENT}; font-family:'Segoe UI'; font-weight:bold;"
            f" font-size:{max(10,int(14*1))}pt;"
        )
        hdr_layout.addWidget(lbl)
        hdr_layout.addStretch()

        # Обратный отсчёт авто-старта
        self._countdown_lbl = QLabel()
        self._countdown_lbl.setStyleSheet(
            f"color:{C_MUTED}; font-family:'Segoe UI'; font-size:{max(9,int(11*1))}pt;"
        )
        hdr_layout.addWidget(self._countdown_lbl)
        layout.addWidget(hdr)

        # Scroll area with test cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background:{C_BG}; border:none; }}
            QScrollBar:vertical {{
                background:{C_BORDER}; width:{scale(8)}px;
                border-radius:{scale(4)}px;
            }}
            QScrollBar::handle:vertical {{
                background:{C_ACCENT}; border-radius:{scale(4)}px;
                min-height:{scale(20)}px;
            }}
        """)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(scale(12), scale(8), scale(12), scale(8))
        scroll_layout.setSpacing(scale(6))

        for test in tests:
            card = TestCard(test, scroll_content)
            card.clicked.connect(self._on_test_clicked)
            scroll_layout.addWidget(card)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, stretch=1)

        # Footer: «Выбрать самому» + «Отмена»
        footer = QFrame()
        footer.setStyleSheet(f"background:{C_BG};")
        footer.setFixedHeight(scale(64))
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(scale(12), scale(8), scale(12), scale(8))
        footer_layout.setSpacing(scale(10))

        btn_manual = QPushButton("Выбрать самому")
        btn_manual.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_manual.setMinimumHeight(scale(38))
        btn_manual.setStyleSheet(
            f"QPushButton {{ background:{C_ACCENT}; color:white; border:none;"
            f" border-radius:{scale(8)}px; padding:{scale(8)}px {scale(14)}px;"
            f" font-family:'Segoe UI'; font-size:{max(9,int(11*1))}pt; font-weight:bold; }}"
            f"QPushButton:hover {{ background:#6355d4; }}"
        )
        btn_manual.setToolTip(
            "У вас есть 15 секунд: откройте нужный тест в браузере сами — "
            "ИИ продолжит с открытым тестом."
        )
        btn_manual.clicked.connect(self._on_manual_clicked)
        footer_layout.addWidget(btn_manual, stretch=2)

        btn_cancel = QPushButton("Отмена")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setMinimumHeight(scale(38))
        btn_cancel.setStyleSheet(
            f"QPushButton {{ background:{C_RED}; color:white; border:none;"
            f" border-radius:{scale(8)}px; padding:{scale(8)}px;"
            f" font-family:'Segoe UI'; font-size:{max(9,int(11*1))}pt; }}"
            f"QPushButton:hover {{ background:#a04040; }}"
        )
        btn_cancel.clicked.connect(self.reject)
        footer_layout.addWidget(btn_cancel, stretch=1)

        layout.addWidget(footer)

        # Таймер авто-старта
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)
        self._update_countdown()

    def _update_countdown(self):
        self._countdown_lbl.setText(
            f"ИИ приступит сам через {self._remaining}с"
        )

    def _tick(self):
        self._remaining -= 1
        if self._remaining <= 0:
            # Время вышло — ИИ приступает сам (как «Выбрать самому»)
            self._on_manual()
            return
        self._update_countdown()

    def _on_test_clicked(self, test: dict):
        self._timer.stop()
        self._selected_test = test
        self._manual = False
        self.test_selected.emit(test)
        self.accept()

    def _on_manual_clicked(self):
        """Клик по «Выбрать самому»: показываем подсказку (если не отключена)."""
        try:
            state = load_ui_state()
            suppressed = bool(state.get("dont_show_manual_hint"))
        except Exception:
            suppressed = False

        if not suppressed:
            # Пауза отсчёта, пока открыто поясняющее окно
            self._timer.stop()
            ManualHintDialog(self).exec()
        self._on_manual()

    def _on_manual(self):
        """Пользователь сам выберет тест в браузере / истёк таймаут."""
        self._timer.stop()
        self._selected_test = None
        self._manual = True
        self.test_selected.emit({})
        self.accept()

    def is_manual(self) -> bool:
        """True если пользователь выбрал «сам» или сработал авто-старт."""
        return self._manual

    def reject(self):
        """Отмена — гасим таймер авто-старта."""
        try:
            self._timer.stop()
        except Exception:
            pass
        super().reject()

    def get_selected(self) -> dict | None:
        return self._selected_test
