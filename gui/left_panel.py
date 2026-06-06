"""
gui/left_panel.py — Левая панель: Task + Auth + License + Controls + Session
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QLineEdit, QPushButton, QComboBox, QTextEdit,
    QScrollArea, QSizePolicy, QGridLayout, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QFont, QPainter, QLinearGradient, QColor

from .theme import (
    C_BG, C_PANEL, C_CARD, C_BORDER, C_ACCENT, C_TEXT, C_MUTED,
    C_ACCENT2, C_GREEN, C_YELLOW, C_RED, C_LOG_BG, C_SURFACE, GRAD_TOP, GRAD_BOT,
    scale, app_font, _load_settings, _save_settings, _load_pixmap,
    btn_accent, btn_accent2, btn_save, btn_delete, btn_pause, btn_resume,
    input_style, combo_style, _load_icon, section_label_style,
)
from .widgets import SectionHeader, CardFrame, StatGrid, GradientHeader, ProgressBar
from .model_dropdown import ModelSelector


class LeftPanel(QWidget):
    """
    Левая панель управления Paketik 4.7.1.
    Содержит: задача, авторизация, лицензия, управление, статистика.
    """

    # Сигналы наружу
    start_requested   = pyqtSignal()   # пользователь нажал "Запустить"
    stop_requested    = pyqtSignal()   # пользователь нажал "Стоп"
    pause_requested   = pyqtSignal()   # пользователь нажал "Пауза/Продолжить"
    activate_requested = pyqtSignal(str)  # ключ активации
    profile_save      = pyqtSignal(str, str, str)  # label, login, password
    profile_delete    = pyqtSignal(str)   # label
    profile_selected  = pyqtSignal(str)   # label
    test_sound        = pyqtSignal(str)   # скрытый тест звука: ai_error|test_done|error
    logo_clicked      = pyqtSignal()       # клик по логотипу — пасхалка

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{C_PANEL};")
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Scroll area для всего контента
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background:{C_PANEL}; border:none; }}
            QScrollBar:vertical {{
                background:{C_BORDER}; width:{scale(8)}px;
                border-radius:{scale(4)}px;
            }}
            QScrollBar::handle:vertical {{
                background:{C_BORDER}; border-radius:{scale(4)}px;
                min-height:{scale(20)}px;
            }}
            QScrollBar::handle:vertical:hover {{ background:{C_ACCENT}; }}
        """)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, scale(6), 0)
        content_layout.setSpacing(scale(2))

        # ── 1. Header gradient ───────────────────────────────────────────
        # Переписано с нуля: все QLabel прозрачные, чтобы за лого/текстом не было
        # чёрных квадратов (раньше метки получали непрозрачный фон от палитры).
        hdr = GradientHeader(content)
        hdr_layout = QVBoxLayout(hdr)
        hdr_layout.setContentsMargins(scale(20), scale(16), scale(20), scale(16))

        top_row = QHBoxLayout()
        top_row.setSpacing(scale(12))
        top_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Logo — крупнее, прозрачный фон, без рамки. Клик = пасхалка (звук).
        lbl_logo = QLabel()
        lbl_logo.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        lbl_logo.setStyleSheet("background: transparent; border: none;")
        logo_px = _load_pixmap("logo.png", scale(56))
        lbl_logo.setPixmap(logo_px)
        lbl_logo.setFixedSize(scale(56), scale(56))
        lbl_logo.setScaledContents(True)
        lbl_logo.setCursor(Qt.CursorShape.PointingHandCursor)
        # QLabel не имеет clicked — вешаем обработчик нажатия вручную.
        lbl_logo.mousePressEvent = lambda _e: self.logo_clicked.emit()
        top_row.addWidget(lbl_logo, 0, Qt.AlignmentFlag.AlignVCenter)

        # Title + subtitle
        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        title_col.setContentsMargins(0, 0, 0, 0)

        lbl_title = QLabel("Paketik")
        lbl_title.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        lbl_title.setStyleSheet(
            f"background: transparent; border: none; color:{C_ACCENT};"
            f" font-family:'Segoe UI'; font-weight:bold; font-size:{max(14,int(26*1))}pt;"
        )
        title_col.addWidget(lbl_title)

        # Скрытые тест-кнопки звуков поверх первых трёх букв "Pak".
        # Невидимые (прозрачные), без курсора-подсказки — секретные.
        self._sound_test_btns = []
        _snd_keys = ["ai_error", "test_done", "error"]
        _letter_w = scale(17)   # примерная ширина буквы при 26pt
        for i, _key in enumerate(_snd_keys):
            b = QPushButton(lbl_title)
            b.setGeometry(i * _letter_w, scale(2), _letter_w, scale(40))
            b.setFlat(True)
            b.setStyleSheet("QPushButton { background: transparent; border: none; }")
            b.setCursor(Qt.CursorShape.ArrowCursor)
            b.setToolTip("")  # без подсказки — скрытая
            b.clicked.connect(lambda _checked, k=_key: self.test_sound.emit(k))
            b.show()
            self._sound_test_btns.append(b)

        import config as _cfg
        self._lbl_subtitle = QLabel(f"Paketik {_cfg.APP_VERSION}")
        self._lbl_subtitle.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._lbl_subtitle.setStyleSheet(
            f"background: transparent; border: none; color:{C_MUTED};"
            f" font-family:'Segoe UI'; font-size:{max(9,int(11*1))}pt;"
        )
        title_col.addWidget(self._lbl_subtitle)
        top_row.addLayout(title_col)

        top_row.addStretch()

        # Header buttons
        self._btn_log = QPushButton()
        self._btn_log.setFixedSize(scale(28), scale(28))
        self._btn_log.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_log.setIcon(_load_icon("log.png", scale(18)))
        self._btn_log.setIconSize(QSize(scale(18), scale(18)))
        self._btn_log.setToolTip("Журнал")
        self._btn_log.setStyleSheet(
            f"QPushButton {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            f"      stop:0 #2a2a4a, stop:1 #1e1e36);"
            f" border:1px solid #34345a; border-radius:{scale(7)}px; }}"
            f"QPushButton:hover {{ background:{C_ACCENT}; border:1px solid {C_ACCENT}; }}"
        )
        self._btn_log.clicked.connect(self._on_toggle_log)
        top_row.addWidget(self._btn_log, 0, Qt.AlignmentFlag.AlignVCenter)

        self._btn_settings = QPushButton("⚙ Вид")
        self._btn_settings.setFixedSize(scale(72), scale(28))
        self._btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_settings.setStyleSheet(
            f"QPushButton {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            f"      stop:0 #2a2a4a, stop:1 #1e1e36); color:{C_TEXT};"
            f" border:1px solid #34345a; border-radius:{scale(7)}px;"
            f" font-family:'Segoe UI'; font-size:{max(8,int(10*1))}pt; }}"
            f"QPushButton:hover {{ background:{C_ACCENT}; border:1px solid {C_ACCENT};"
            f" color:white; }}"
        )
        self._btn_settings.clicked.connect(self._on_toggle_settings)
        top_row.addWidget(self._btn_settings, 0, Qt.AlignmentFlag.AlignVCenter)

        hdr_layout.addLayout(top_row)
        content_layout.addWidget(hdr)

        # ── 2. Task ──────────────────────────────────────────────────────
        # Блок «ЗАДАЧА» убран из интерфейса — задача неизменна и задаётся по
        # умолчанию. Скрытый QTextEdit оставлен, чтобы get_task_text() работал.
        self._task_edit = QTextEdit()
        self._task_edit.setText("Пройди тест, выбирая правильные ответы.")
        self._task_edit.hide()

        # ── 3. Auth ───────────────────────────────────────────────────────
        content_layout.addWidget(SectionHeader("АВТОРИЗАЦИЯ", "browser.png"))

        auth_card = CardFrame()
        auth_layout = auth_card.inner_layout()
        auth_layout.setContentsMargins(scale(14), scale(10), scale(14), scale(10))
        auth_layout.setSpacing(scale(6))

        self._auth_login = QLineEdit()
        self._auth_login.setPlaceholderText("Логин")
        self._auth_login.setStyleSheet(input_style())
        auth_layout.addWidget(QLabel("Логин:"))
        auth_layout.addWidget(self._auth_login)

        self._auth_password = QLineEdit()
        self._auth_password.setPlaceholderText("Пароль")
        self._auth_password.setEchoMode(QLineEdit.EchoMode.Password)
        self._auth_password.setStyleSheet(input_style())
        auth_layout.addWidget(QLabel("Пароль:"))
        auth_layout.addWidget(self._auth_password)

        # Profile selector
        self._auth_profile_var = "Новый профиль"
        self._auth_combo = QComboBox()
        self._auth_combo.setEditable(False)
        self._auth_combo.addItem("Новый профиль")
        self._auth_combo.setStyleSheet(combo_style())
        self._auth_combo.currentTextChanged.connect(self._on_profile_selected)
        auth_layout.addWidget(self._auth_combo)

        # Save/Delete row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(scale(6))

        self._btn_save_profile = QPushButton("💾 Сохранить")
        self._btn_save_profile.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_save_profile.setStyleSheet(btn_save())
        self._btn_save_profile.clicked.connect(self._on_save_profile)
        btn_row.addWidget(self._btn_save_profile)

        self._btn_del_profile = QPushButton("🗑 Удалить")
        self._btn_del_profile.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_del_profile.setDisabled(True)
        self._btn_del_profile.setStyleSheet(btn_delete())
        self._btn_del_profile.clicked.connect(self._on_delete_profile)
        btn_row.addWidget(self._btn_del_profile)

        auth_layout.addLayout(btn_row)
        content_layout.addWidget(auth_card)

        # ── 4. License ────────────────────────────────────────────────────
        content_layout.addWidget(SectionHeader("ЛИЦЕНЗИЯ", "sand_clock.png"))

        lic_card = CardFrame()
        lic_layout = lic_card.inner_layout()
        lic_layout.setContentsMargins(scale(14), scale(10), scale(14), scale(10))
        lic_layout.setSpacing(scale(6))

        # Key icon + plan
        key_row = QHBoxLayout()
        key_row.setSpacing(scale(8))

        self._lbl_key_icon = QLabel()
        self._lbl_key_icon.setPixmap(_load_pixmap("red_key.png", scale(20)))
        key_row.addWidget(self._lbl_key_icon)

        self._lbl_license_status = QLabel("Standard Edition")
        self._lbl_license_status.setStyleSection = True
        self._lbl_license_status.setStyleSheet(
            f"color:{C_RED}; font-family:'Segoe UI'; font-weight:bold;"
            f" font-size:{max(10,int(13*1))}pt;"
        )
        key_row.addWidget(self._lbl_license_status)
        key_row.addStretch()
        lic_layout.addLayout(key_row)

        self._lbl_expiry = QLabel("")
        self._lbl_expiry.setStyleSection = True
        self._lbl_expiry.setStyleSheet(
            f"color:{C_MUTED}; font-family:'Segoe UI'; font-size:{max(8,int(10*1))}pt;"
        )
        lic_layout.addWidget(self._lbl_expiry)

        self._lbl_token = QLabel("—")
        self._lbl_token.setStyleSection = True
        self._lbl_token.setStyleSheet(
            f"color:{C_ACCENT2}; font-family:'Segoe UI'; font-size:{max(9,int(11*1))}pt;"
        )
        lic_layout.addWidget(self._lbl_token)

        self._progress_bar = ProgressBar()
        lic_layout.addWidget(self._progress_bar)

        # License key entry
        self._entry_key = QLineEdit()
        self._entry_key.setPlaceholderText("XXXX-XXXX-XXXX-XXXX")
        self._entry_key.setStyleSheet(input_style())
        self._entry_key.returnPressed.connect(self._on_activate)
        lic_layout.addWidget(self._entry_key)

        self._btn_activate = QPushButton("Активировать")
        self._btn_activate.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_activate.setStyleSheet(btn_accent())
        self._btn_activate.clicked.connect(self._on_activate)
        lic_layout.addWidget(self._btn_activate)

        # Model selector — иконка task.png + текст вместо эмодзи
        model_row = QHBoxLayout()
        model_row.setSpacing(scale(6))
        model_row.setContentsMargins(0, 0, 0, 0)
        lbl_model_ico = QLabel()
        lbl_model_ico.setPixmap(_load_pixmap("task.png", scale(16)))
        lbl_model_ico.setFixedSize(scale(16), scale(16))
        lbl_model_ico.setScaledContents(True)
        lbl_model_ico.setStyleSheet("background: transparent; border: none;")
        model_row.addWidget(lbl_model_ico, 0, Qt.AlignmentFlag.AlignVCenter)
        lbl_model = QLabel("Модель AI:")
        lbl_model.setStyleSheet(
            f"color:{C_MUTED}; font-family:'Segoe UI'; font-size:{max(9,int(10*1))}pt;"
        )
        model_row.addWidget(lbl_model, 0, Qt.AlignmentFlag.AlignVCenter)
        model_row.addStretch()
        lic_layout.addLayout(model_row)

        self._model_selector = ModelSelector()
        self._model_selector.model_changed.connect(self._on_model_changed)
        lic_layout.addWidget(self._model_selector)

        content_layout.addWidget(lic_card)

        # ── 5. Controls ───────────────────────────────────────────────────
        content_layout.addWidget(SectionHeader("УПРАВЛЕНИЕ", None))

        ctrl_card = CardFrame()
        ctrl_layout = ctrl_card.inner_layout()
        ctrl_layout.setContentsMargins(scale(12), scale(10), scale(12), scale(10))
        ctrl_layout.setSpacing(scale(6))

        self._btn_start = QPushButton()
        self._btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_start.setStyleSheet(btn_accent2())
        self._btn_start.setFixedHeight(scale(52))
        self._btn_start.setIcon(_load_icon("play.png", scale(20)))
        self._btn_start.setIconSize(QSize(scale(20), scale(20)))
        self._btn_start.setText("  Запустить агента")
        self._btn_start.clicked.connect(self._on_start)
        ctrl_layout.addWidget(self._btn_start)

        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(scale(6))

        self._btn_pause = QPushButton()
        self._btn_pause.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_pause.setDisabled(True)
        self._btn_pause.setIcon(_load_icon("pause.png", scale(18)))
        self._btn_pause.setIconSize(QSize(scale(18), scale(18)))
        self._btn_pause.setText("  Пауза")
        self._btn_pause.setStyleSheet(btn_pause())
        self._btn_pause.clicked.connect(self._on_pause)
        ctrl_row.addWidget(self._btn_pause)

        self._btn_stop = QPushButton()
        self._btn_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_stop.setDisabled(True)
        self._btn_stop.setIcon(_load_icon("stop.png", scale(18)))
        self._btn_stop.setIconSize(QSize(scale(18), scale(18)))
        self._btn_stop.setText("  Стоп")
        self._btn_stop.setStyleSheet(
            f"QPushButton {{ background:#1e0808; color:{C_RED};"
            f" border:1px solid #6a1800; border-radius:{scale(8)}px;"
            f" padding:{scale(6)}px; font-family:'Segoe UI'; font-size:{max(9,int(11*1))}pt; }}"
            f"QPushButton:disabled {{ background:#1e1e2e; color:#3a3a5a; border-color:#252540; }}"
        )
        self._btn_stop.clicked.connect(self._on_stop)
        ctrl_row.addWidget(self._btn_stop)

        ctrl_layout.addLayout(ctrl_row)
        content_layout.addWidget(ctrl_card)

        # ── 6. Session Stats ─────────────────────────────────────────────
        content_layout.addWidget(SectionHeader("СЕССИЯ", "statistic.png"))

        self._stat_grid = StatGrid()
        content_layout.addWidget(self._stat_grid)

        content_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll)

        # Pulse timer
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._pulse_step)
        self._pulse_angle = 0.0
        self._pulse_running = False
        self._paused_state = False

    # ── License UI update ─────────────────────────────────────────────────────

    def update_license_ui(self, info: dict):
        """Обновляет UI лицензии из license_manager.get_summary()."""
        if info.get("active"):
            plan = info.get("plan", "Pro")
            color = {
                "Demo": C_MUTED, "Pro": C_ACCENT2, "Ultra": "#b06cf5", "Ultimate": C_GREEN
            }.get(plan, C_ACCENT2)

            self._lbl_license_status.setText(f"{plan} Edition")
            self._lbl_license_status.setStyleSheet(
                f"color:{color}; font-family:'Segoe UI'; font-weight:bold;"
                f" font-size:{max(10,int(13*1))}pt;"
            )
            self._lbl_subtitle.setText(f"{plan} edition")
            self._lbl_key_icon.setPixmap(_load_pixmap("green_key.png", scale(20)))

            expiry = info.get("expiry", "∞")
            self._lbl_expiry.setText(f"Действует до: {expiry}")
            bal = f"{info.get('balance', 0):,}".replace(",", " ")
            lim = f"{info.get('limit', 0):,}".replace(",", " ")
            self._lbl_token.setText(f"{bal} / {lim} токенов")

            pct = info.get("pct_used", 0) / 100
            self._progress_bar.set_progress(pct)
        else:
            self._lbl_license_status.setText("Standard Edition")
            self._lbl_license_status.setStyleSheet(
                f"color:{C_RED}; font-family:'Segoe UI'; font-weight:bold;"
                f" font-size:{max(10,int(13*1))}pt;"
            )
            self._lbl_key_icon.setPixmap(_load_pixmap("red_key.png", scale(20)))

        # Model selector
        try:
            from license_mgr import license_manager
            self._model_selector.build_from_manager(license_manager)
        except Exception:
            pass

    # ── Model selector ─────────────────────────────────────────────────────────

    def _on_model_changed(self, model_id: str, name: str, rating: float):
        try:
            from license_mgr import license_manager
            license_manager.set_model(model_id)
        except Exception:
            pass

    # ── Auth ─────────────────────────────────────────────────────────────────

    def refresh_profiles(self, labels: list):
        """Обновляет combo профилей."""
        current = self._auth_combo.currentText()
        self._auth_combo.clear()
        self._auth_combo.addItem("Новый профиль")
        for label in labels:
            self._auth_combo.addItem(label)
        if current in labels:
            self._auth_combo.setCurrentText(current)

    def current_profile(self) -> str:
        """Возвращает текущий выбранный профиль ('' если 'Новый профиль')."""
        value = self._auth_combo.currentText()
        return "" if value == "Новый профиль" else value

    def select_profile(self, label: str):
        """Выбирает профиль по имени, если он есть в списке."""
        for i in range(self._auth_combo.count()):
            if self._auth_combo.itemText(i) == label:
                self._auth_combo.setCurrentIndex(i)
                return

    def _on_profile_selected(self, value: str):
        if value == "Новый профиль":
            self._auth_login.clear()
            self._auth_password.clear()
            self._btn_del_profile.setDisabled(True)
        else:
            self.profile_selected.emit(value)
            self._btn_del_profile.setDisabled(False)

    def fill_profile(self, login: str, password: str):
        self._auth_login.setText(login)
        self._auth_password.setText(password)

    def _on_save_profile(self):
        label = self._auth_combo.currentText()
        login = self._auth_login.text().strip()
        password = self._auth_password.text()

        if label == "Новый профиль":
            # Диалог ввода названия
            from PyQt6.QtWidgets import QInputDialog
            new_label, ok = QInputDialog.getText(
                self, "Новый профиль", "Введите название профиля:",
                text=""
            )
            if not ok or not new_label.strip():
                return
            label = new_label.strip()
            self._auth_combo.addItem(label)
            self._auth_combo.setCurrentText(label)

        if not login:
            QMessageBox.warning(self, "Ошибка", "Введите логин.")
            return

        self.profile_save.emit(label, login, password)

    def _on_delete_profile(self):
        label = self._auth_combo.currentText()
        if label == "Новый профиль":
            return
        from PyQt6.QtWidgets import QMessageBox
        if QMessageBox.question(self, "Удалить профиль",
                               f"Удалить профиль '{label}'?",
                               QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                               ) == QMessageBox.StandardButton.Yes:
            self.profile_delete.emit(label)
            self._auth_combo.setCurrentText("Новый профиль")

    # ── License activation ───────────────────────────────────────────────────

    def _on_activate(self):
        key = self._entry_key.text().strip()
        if not key:
            QMessageBox.warning(self, "Нет ключа", "Введите лицензионный ключ.")
            return
        self.activate_requested.emit(key)

    def activation_result(self, ok: bool, msg: str):
        """Показать результат активации."""
        if ok:
            QMessageBox.information(self, "Лицензия", msg)
        else:
            QMessageBox.critical(self, "Ошибка активации", msg)

    # ── Controls ─────────────────────────────────────────────────────────────

    def _on_start(self):
        self.start_requested.emit()

    def _on_pause(self):
        self.pause_requested.emit()
        self._paused_state = not self._paused_state
        if self._paused_state:
            self._btn_pause.setIcon(_load_icon("play.png", scale(18)))
            self._btn_pause.setIconSize(QSize(scale(18), scale(18)))
            self._btn_pause.setText("  Продолжить")
            self._btn_pause.setStyleSheet(btn_resume())
        else:
            self._btn_pause.setIcon(_load_icon("pause.png", scale(18)))
            self._btn_pause.setIconSize(QSize(scale(18), scale(18)))
            self._btn_pause.setText("  Пауза")
            self._btn_pause.setStyleSheet(btn_pause())

    def _on_stop(self):
        self.stop_requested.emit()

    def start_pulse(self):
        self._pulse_running = True
        self._pulse_timer.start(33)  # ~30 fps — плавно

    def stop_pulse(self):
        self._pulse_running = False
        self._pulse_timer.stop()
        # Возвращаем обычный стиль кнопки запуска
        try:
            self._btn_start.setStyleSheet(btn_accent2())
        except Exception:
            pass

    def _pulse_step(self):
        if not self._pulse_running:
            return
        import math
        # Плавно вращаем фазу
        self._pulse_angle = (self._pulse_angle + 0.06) % (2 * math.pi)
        # Две смещённые по фазе синусоиды → «перелив» градиента
        t1 = 0.5 + 0.5 * math.sin(self._pulse_angle)
        t2 = 0.5 + 0.5 * math.sin(self._pulse_angle + 2.094)  # +120°

        def mix(c1, c2, t):
            return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))

        # Палитра зелёного перелива: тёмно-изумрудный → яркий мятный
        dark  = (0x12, 0x5a, 0x3a)
        mid   = (0x2e, 0x9c, 0x5e)
        bright= (0x4d, 0xe0, 0x8a)

        top = mix(dark, bright, t1)
        bot = mix(mid, dark, t2)
        c_top = f"#{top[0]:02x}{top[1]:02x}{top[2]:02x}"
        c_bot = f"#{bot[0]:02x}{bot[1]:02x}{bot[2]:02x}"
        try:
            self._btn_start.setStyleSheet(
                f"QPushButton {{"
                f" background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
                f"   stop:0 {c_top}, stop:0.5 {c_bot}, stop:1 {c_top});"
                f" color:white; border:none;"
                f" border-radius:{scale(10)}px; padding:{scale(8)}px {scale(16)}px;"
                f" font-family:'Segoe UI'; font-size:{max(9,int(13*1))}pt; font-weight:bold; }}"
            )
        except Exception:
            pass

    def set_running_state(self, running: bool):
        """Управление состоянием кнопок."""
        self._btn_start.setDisabled(running)
        self._btn_pause.setDisabled(not running)
        self._btn_stop.setDisabled(not running)

    # ── Header buttons ────────────────────────────────────────────────────────

    def _on_toggle_log(self):
        from .main_window import AppWindow
        if self.window():
            self.window().toggle_log_panel()

    def _on_toggle_settings(self):
        from .main_window import AppWindow
        if self.window():
            self.window().toggle_settings_panel()

    # ── Stats update ─────────────────────────────────────────────────────────

    def update_stats(self, stats: dict):
        """Обновляет статистику сессии."""
        self._stat_grid.update_stats(stats)

    def get_task_text(self) -> str:
        return self._task_edit.toPlainText().strip()

    def get_auth_credentials(self) -> tuple[str, str]:
        return (
            self._auth_login.text().strip(),
            self._auth_password.text(),
        )