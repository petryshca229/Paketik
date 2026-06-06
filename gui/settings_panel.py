"""
gui/settings_panel.py — Панель настроек вида (шрифт, масштаб)
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame, QLabel,
    QSlider, QPushButton, QListWidget, QListWidgetItem, QFontDialog
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from .theme import (
    C_BG, C_PANEL, C_CARD, C_BORDER, C_ACCENT, C_TEXT, C_MUTED,
    scale, app_font, _load_settings, _save_settings, DEFAULT_SETTINGS,
)
from .theme import _settings
import config as _cfg


FONT_FAMILIES = [
    "Segoe UI Semibold", "Segoe UI", "Calibri",
    "Arial Rounded MT Bold", "Trebuchet MS", "Verdana",
]

SCALE_VALUES = [0.8, 0.9, 1.0, 1.1, 1.2, 1.4]


class SettingsPanel(QWidget):
    """Справа от левой панели — настройки масштаба и шрифта."""

    settings_changed = pyqtSignal()  # сигнал при изменении настроек
    browser_zoom_changed = pyqtSignal(float)  # новый zoom

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(300)
        self.setStyleSheet(f"background:#0e0e20;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(scale(14), scale(10), scale(14), scale(10))
        layout.setSpacing(scale(8))

        # Header
        hdr_lbl = QLabel("Настройки вида")
        hdr_lbl.setStyleSection = True
        hdr_lbl.setStyleSheet(
            f"color:{C_ACCENT}; font-family:'Segoe UI'; font-weight:bold;"
            f" font-size:{max(10,int(13*1))}pt; padding-bottom:{scale(8)}px;"
        )
        layout.addWidget(hdr_lbl)

        # Font size
        layout.addWidget(self._make_label("Размер шрифта", C_MUTED))
        size_row = QHBoxLayout()
        size_row.setSpacing(scale(6))

        btn_minus = QPushButton("−")
        btn_minus.setFixedSize(scale(34), scale(34))
        btn_minus.setStyleSheet(f"""
            QPushButton {{ background:{C_BORDER}; color:{C_TEXT};
            border:none; border-radius:{scale(8)}px;
            font-size:{max(14,int(18*1))}pt; font-weight:bold; }}
            QPushButton:hover {{ background:{C_ACCENT}; }}
        """)
        btn_minus.clicked.connect(lambda: self._adjust_size(-1))
        size_row.addWidget(btn_minus)

        self._size_lbl = QLabel(str(_settings["font_size_base"]))
        self._size_lbl.setStyleSection = True
        self._size_lbl.setStyleSheet(
            f"color:{C_TEXT}; font-family:'Segoe UI'; font-weight:bold;"
            f" font-size:{max(12,int(20*1))}pt; min-width:{scale(36)}px; alignment:AlignCenter;"
        )
        self._size_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        size_row.addWidget(self._size_lbl)

        btn_plus = QPushButton("+")
        btn_plus.setFixedSize(scale(34), scale(34))
        btn_plus.setStyleSheet(f"""
            QPushButton {{ background:{C_BORDER}; color:{C_TEXT};
            border:none; border-radius:{scale(8)}px;
            font-size:{max(14,int(18*1))}pt; font-weight:bold; }}
            QPushButton:hover {{ background:{C_ACCENT}; }}
        """)
        btn_plus.clicked.connect(lambda: self._adjust_size(+1))
        size_row.addWidget(btn_plus)

        layout.addLayout(size_row)

        # Font preview
        preview = QLabel("Aa Бб 0123")
        preview.setStyleSheet(
            f"background:{C_CARD}; color:{C_TEXT}; border:1px solid {C_BORDER};"
            f" border-radius:{scale(6)}px; padding:{scale(8)}px;"
            f" font-family:'Segoe UI'; font-size:{max(10,int(14*1))}pt;"
        )
        layout.addWidget(preview)
        self._preview = preview

        # Font family
        layout.addWidget(self._make_label("Шрифт", C_MUTED))
        font_list = QListWidget()
        font_list.setStyleSheet(f"""
            QListWidget {{ background:{C_CARD}; color:{C_TEXT};
            border:1px solid {C_BORDER}; border-radius:{scale(6)}px;
            font-size:{max(9,int(12*1))}pt; outline:none; }}
            QListWidget::item {{ padding:{scale(4)}px; }}
            QListWidget::item:selected {{ background:{C_ACCENT}; color:white; }}
        """)
        for i, fam in enumerate(FONT_FAMILIES):
            item = QListWidgetItem(fam)
            font_list.addItem(item)
            try:
                item.setFont(QFont(fam, max(9, int(12 * _settings["scale"]))))
            except Exception:
                pass
            if fam == _settings["font_family"]:
                font_list.setCurrentRow(i)
        font_list.currentRowChanged.connect(self._on_font_selected)
        self._font_list = font_list
        layout.addWidget(font_list, stretch=1)

        # Scale buttons
        layout.addWidget(self._make_label("Масштаб", C_MUTED))
        scale_grid = QGridLayout()
        scale_grid.setSpacing(scale(2))

        self._scale_btns: list[tuple[QPushButton, float]] = []
        for idx, val in enumerate(SCALE_VALUES):
            pct = int(val * 100)
            btn = QPushButton(f"{pct}%")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            active = abs(val - _settings["scale"]) < 0.05
            btn.setStyleSheet(
                f"QPushButton {{ background:{'#7c6cf2' if active else C_BORDER};"
                f" color:white; border:none; border-radius:{scale(6)}px;"
                f" padding:{scale(6)}px {scale(10)}px;"
                f" font-family:'Segoe UI'; font-size:{max(8,int(10*1))}pt; }}"
                f"QPushButton:hover {{ background:#6355d4; }}"
            )
            btn.clicked.connect(lambda checked, v=val: self._set_scale(v))
            scale_grid.addWidget(btn, idx // 3, idx % 3)
            self._scale_btns.append((btn, val))

        layout.addLayout(scale_grid)

        # Browser zoom
        layout.addWidget(self._make_label("Масштаб браузера", C_MUTED))
        zoom_row = QHBoxLayout()
        zoom_row.setSpacing(scale(6))

        self._browser_zoom = _cfg.BROWSER_ZOOM
        btn_zoom_minus = QPushButton("−")
        btn_zoom_minus.setFixedSize(scale(34), scale(34))
        btn_zoom_minus.setStyleSheet(f"""
            QPushButton {{ background:{C_BORDER}; color:{C_TEXT};
            border:none; border-radius:{scale(8)}px;
            font-size:{max(14,int(18*1))}pt; font-weight:bold; }}
            QPushButton:hover {{ background:{C_ACCENT}; }}
        """)
        btn_zoom_minus.clicked.connect(lambda: self._adjust_browser_zoom(-0.1))
        zoom_row.addWidget(btn_zoom_minus)

        self._zoom_lbl = QLabel(f"{int(self._browser_zoom * 100)}%")
        self._zoom_lbl.setStyleSection = True
        self._zoom_lbl.setStyleSheet(
            f"color:{C_TEXT}; font-family:'Segoe UI'; font-weight:bold;"
            f" font-size:{max(11,int(18*1))}pt; min-width:{scale(44)}px;"
        )
        self._zoom_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        zoom_row.addWidget(self._zoom_lbl)

        btn_zoom_plus = QPushButton("+")
        btn_zoom_plus.setFixedSize(scale(34), scale(34))
        btn_zoom_plus.setStyleSheet(f"""
            QPushButton {{ background:{C_BORDER}; color:{C_TEXT};
            border:none; border-radius:{scale(8)}px;
            font-size:{max(14,int(18*1))}pt; font-weight:bold; }}
            QPushButton:hover {{ background:{C_ACCENT}; }}
        """)
        btn_zoom_plus.clicked.connect(lambda: self._adjust_browser_zoom(+0.1))
        zoom_row.addWidget(btn_zoom_plus)
        layout.addLayout(zoom_row)

        # ── Звуковые уведомления ─────────────────────────────────────────
        layout.addWidget(self._make_label("Звуки уведомлений", C_ACCENT))

        self._vol_sliders: dict[str, QSlider] = {}
        self._vol_value_lbls: dict[str, QLabel] = {}
        sound_defs = [
            ("vol_ai_error",  "Ошибки ИИ"),
            ("vol_test_done", "Тест завершён"),
            ("vol_error",     "Прочие ошибки"),
        ]
        for key, title in sound_defs:
            layout.addLayout(self._make_volume_row(key, title))

        # ── Поведение ────────────────────────────────────────────────────
        layout.addWidget(self._make_label("Поведение", C_ACCENT))
        from .widgets import ToggleSwitch
        skip_row = QHBoxLayout()
        skip_row.setSpacing(scale(8))
        skip_row.setContentsMargins(0, 0, 0, 0)
        skip_lbl = QLabel("Пропускать вопросы с картинками")
        skip_lbl.setWordWrap(True)
        skip_lbl.setStyleSheet(
            f"color:{C_TEXT}; font-family:'Segoe UI'; font-size:{max(8,int(10*1))}pt;"
        )
        skip_row.addWidget(skip_lbl, stretch=1)
        self._chk_skip_images = ToggleSwitch(
            checked=bool(_settings.get("skip_image_questions", True))
        )
        self._chk_skip_images.toggled_changed.connect(self._on_skip_images_toggled)
        skip_row.addWidget(self._chk_skip_images, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(skip_row)

        # Apply / Reset
        btn_apply = QPushButton("Применить")
        btn_apply.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_apply.setStyleSheet(
            f"QPushButton {{ background:{C_ACCENT}; color:white; border:none;"
            f" border-radius:{scale(8)}px; padding:{scale(8)}px;"
            f" font-family:'Segoe UI'; font-size:{max(9,int(11*1))}pt; font-weight:bold; }}"
            f"QPushButton:hover {{ background:#6355d4; }}"
        )
        btn_apply.clicked.connect(self._apply)
        layout.addWidget(btn_apply)

        btn_reset = QPushButton("Сброс")
        btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_reset.setStyleSheet(
            f"QPushButton {{ background:{C_BORDER}; color:{C_MUTED}; border:none;"
            f" border-radius:{scale(8)}px; padding:{scale(6)}px;"
            f" font-family:'Segoe UI'; font-size:{max(8,int(10*1))}pt; }}"
            f"QPushButton:hover {{ background:#3a3a56; }}"
        )
        btn_reset.clicked.connect(self._reset)
        layout.addWidget(btn_reset)

        layout.addStretch()

    def _make_label(self, text: str, color: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSection = True
        lbl.setStyleSheet(f"color:{color}; font-family:'Segoe UI'; font-size:{max(9,int(10*1))}pt;")
        return lbl

    def _make_volume_row(self, key: str, title: str) -> QHBoxLayout:
        """Строка громкости звука: название + слайдер 0..100 + значение."""
        row = QHBoxLayout()
        row.setSpacing(scale(6))

        name = QLabel(title)
        name.setStyleSheet(
            f"color:{C_TEXT}; font-family:'Segoe UI'; font-size:{max(8,int(10*1))}pt;"
            f" min-width:{scale(96)}px;"
        )
        row.addWidget(name)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setMinimum(0)
        slider.setMaximum(100)
        slider.setValue(int(_settings.get(key, 70)))
        slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                height:{scale(5)}px; background:{C_BORDER};
                border-radius:{scale(2)}px;
            }}
            QSlider::sub-page:horizontal {{
                background:{C_ACCENT}; border-radius:{scale(2)}px;
            }}
            QSlider::handle:horizontal {{
                background:{C_TEXT}; width:{scale(13)}px;
                margin:-{scale(5)}px 0; border-radius:{scale(6)}px;
            }}
            QSlider::handle:horizontal:hover {{ background:{C_ACCENT}; }}
        """)
        row.addWidget(slider, stretch=1)

        val_lbl = QLabel(f"{slider.value()}")
        val_lbl.setStyleSheet(
            f"color:{C_MUTED}; font-family:'Segoe UI'; font-size:{max(8,int(10*1))}pt;"
            f" min-width:{scale(26)}px;"
        )
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(val_lbl)

        slider.valueChanged.connect(
            lambda v, k=key, lbl=val_lbl: self._on_volume_changed(k, v, lbl)
        )
        self._vol_sliders[key] = slider
        self._vol_value_lbls[key] = val_lbl
        return row

    def _on_volume_changed(self, key: str, value: int, lbl: QLabel):
        _settings[key] = int(value)
        lbl.setText(str(value))
        # Сохраняем сразу — чтобы громкость пережила перезапуск без «Применить».
        _save_settings(_settings)

    def _on_skip_images_toggled(self, checked: bool):
        _settings["skip_image_questions"] = bool(checked)
        _save_settings(_settings)

    def _adjust_size(self, delta: int):
        new = max(9, min(26, _settings["font_size_base"] + delta))
        _settings["font_size_base"] = new
        self._size_lbl.setText(str(new))
        self._update_preview()

    def _on_font_selected(self, row: int):
        if row >= 0:
            _settings["font_family"] = FONT_FAMILIES[row]
            self._update_preview()

    def _set_scale(self, val: float):
        _settings["scale"] = val
        for btn, v in self._scale_btns:
            active = abs(v - val) < 0.05
            btn.setStyleSheet(
                f"QPushButton {{ background:{'#7c6cf2' if active else C_BORDER};"
                f" color:white; border:none; border-radius:{scale(6)}px;"
                f" padding:{scale(6)}px {scale(10)}px;"
                f" font-family:'Segoe UI'; font-size:{max(8,int(10*1))}pt; }}"
                f"QPushButton:hover {{ background:#6355d4; }}"
            )
        self._update_preview()

    def _update_preview(self):
        size = max(9, int(14 * _settings["scale"]))
        fam = _settings.get("font_family", "Segoe UI")
        self._preview.setStyleSheet(
            f"background:{C_CARD}; color:{C_TEXT}; border:1px solid {C_BORDER};"
            f" border-radius:{scale(6)}px; padding:{scale(8)}px;"
            f" font-family:'{fam}'; font-size:{size}pt;"
        )
        self._size_lbl.setText(str(_settings["font_size_base"]))

    def _apply(self):
        _save_settings(_settings)
        try:
            import json
            settings_file = _cfg.APP_DATA_DIR + "/settings.json"
            data = {}
            try:
                with open(settings_file, "r") as f:
                    data = json.load(f)
            except Exception:
                pass
            data["browser_zoom"] = _cfg.BROWSER_ZOOM
            with open(settings_file, "w") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception:
            pass
        self.settings_changed.emit()

    def _adjust_browser_zoom(self, delta: float):
        new = max(0.25, min(2.0, round(self._browser_zoom + delta, 1)))
        self._browser_zoom = new
        self._zoom_lbl.setText(f"{int(new * 100)}%")
        _cfg.BROWSER_ZOOM = new
        self.browser_zoom_changed.emit(new)

    def _reset(self):
        # Мутируем словарь НА МЕСТЕ (не rebind), чтобы общая ссылка
        # theme._settings (её использует SoundManager) осталась актуальной.
        _settings.clear()
        _settings.update(DEFAULT_SETTINGS)
        _save_settings(_settings)
        self._size_lbl.setText(str(DEFAULT_SETTINGS["font_size_base"]))
        for btn, v in self._scale_btns:
            active = abs(v - DEFAULT_SETTINGS["scale"]) < 0.05
            btn.setStyleSheet(
                f"QPushButton {{ background:{'#7c6cf2' if active else C_BORDER};"
                f" color:white; border:none; border-radius:{scale(6)}px;"
                f" padding:{scale(6)}px {scale(10)}px;"
                f" font-family:'Segoe UI'; font-size:{max(8,int(10*1))}pt; }}"
                f"QPushButton:hover {{ background:#6355d4; }}"
            )
        # Сбрасываем слайдеры громкости
        for key, slider in getattr(self, "_vol_sliders", {}).items():
            slider.setValue(int(DEFAULT_SETTINGS.get(key, 70)))
        # Сбрасываем чекбокс пропуска картинок
        if hasattr(self, "_chk_skip_images"):
            self._chk_skip_images.setChecked(bool(DEFAULT_SETTINGS.get("skip_image_questions", True)))
        self._update_preview()
        self.settings_changed.emit()