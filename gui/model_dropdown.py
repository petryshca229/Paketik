"""
gui/model_dropdown.py — Кастомный dropdown выбора модели AI
"""

from PyQt6.QtWidgets import QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QApplication
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QSize, QEvent, QTimer
from PyQt6.QtGui import QCursor

from .theme import C_CARD, C_BORDER, C_TEXT, C_ACCENT, C_MUTED, C_BG, scale


class ModelCard(QFrame):
    """Одна карточка модели в dropdown."""

    clicked = pyqtSignal(str, str, float)  # model_id, name, rating

    def __init__(self, model_id: str, name: str, rating: float, is_selected: bool, parent=None):
        super().__init__(parent)
        self._model_id = model_id
        self._name = name
        self._rating = rating
        self._is_selected = is_selected

        self._set_style(is_selected)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(scale(10), scale(6), scale(8), scale(6))
        layout.setSpacing(scale(6))

        if is_selected:
            check = QLabel("✓")
            check.setStyleSheet(f"color:{C_ACCENT}; font-weight:bold; font-size:{max(10,int(12*1))}pt;")
            layout.addWidget(check)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(
            f"color:{C_TEXT}; font-family:'Segoe UI'; font-size:{max(10,int(12*1))}pt;"
            f" background:transparent;"
        )
        name_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        layout.addWidget(name_lbl, stretch=1)

        stars_lbl = QLabel(self._stars_text())
        stars_lbl.setStyleSheet(
            f"color:#f7c948; font-size:{max(9,int(10*1))}pt; background:transparent;"
        )
        layout.addWidget(stars_lbl)

    def _set_style(self, is_selected: bool):
        bg = "#252550" if is_selected else "#1a1a32"
        self.setStyleSheet(
            f"QFrame {{ background:{bg}; border-radius:{scale(8)}px; padding:{scale(4)}px; }}"
            f"QFrame:hover {{ background:#1e1e44; }}"
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _stars_text(self) -> str:
        full = int(self._rating)
        half = (self._rating - full) >= 0.4
        empty = 5 - full - (1 if half else 0)
        s = "★" * full
        if half:
            s += "✦"
        s += "☆" * empty
        return s

    def enterEvent(self, event):
        self._set_style(False)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._set_style(self._is_selected)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._model_id, self._name, self._rating)
        super().mousePressEvent(event)


class ModelDropdown(QDialog):
    """
    Popup-диалог выбора модели AI.
    """

    model_selected = pyqtSignal(str, str, float)  # model_id, name, rating

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setModal(False)
        self._cards = []
        self._selector_widget = None
        self._filter_installed = False
        self._is_visible = False

        self._container = QFrame(self)
        self._container.setStyleSheet(
            f"QFrame {{ background:#131330; border:1px solid {C_BORDER};"
            f" border-radius:{scale(12)}px; padding:{scale(6)}px; }}"
        )
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(scale(2), scale(2), scale(2), scale(2))
        self._container_layout.setSpacing(scale(2))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._container)

    def build_from_models(self, models: list, current_id: str):
        """Перестроить меню из списка моделей."""
        while self._cards:
            w = self._cards.pop()
            w.hide()
            w.deleteLater()
        while self._container_layout.count():
            child = self._container_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not models:
            return

        for model_id, name, rating in models:
            is_sel = (model_id == current_id)
            card = ModelCard(model_id, name, rating, is_sel, self._container)
            card.clicked.connect(self._on_card_clicked)
            self._container_layout.addWidget(card)
            self._cards.append(card)

        self.adjustSize()

    def _on_card_clicked(self, model_id: str, name: str, rating: float):
        self.model_selected.emit(model_id, name, rating)
        self._hide_dropdown()

    def _install_filter(self):
        """Install event filter on app to detect outside clicks (deferred to avoid catching open-click)."""
        if self._filter_installed:
            return
        # Defer to avoid catching the same click that opened the dropdown
        QTimer.singleShot(50, self._do_install_filter)

    def _do_install_filter(self):
        if self._is_visible:
            self._filter_installed = True
            app = QApplication.instance()
            if app:
                app.installEventFilter(self)

    def _remove_filter(self):
        if self._filter_installed:
            self._filter_installed = False
            app = QApplication.instance()
            if app:
                app.removeEventFilter(self)

    def eventFilter(self, obj, event):
        """Close dropdown on any click outside."""
        if event.type() == QEvent.Type.MouseButtonPress:
            # Check if click is outside our dialog
            if not self.geometry().contains(QCursor.pos()):
                self._hide_dropdown()
        return super().eventFilter(obj, event)

    def _hide_dropdown(self):
        self._remove_filter()
        self._is_visible = False
        self.hide()

    def show_at_widget(self, widget: QWidget):
        """Показать dropdown под указанным виджетом, с учётом границ экрана."""
        if not widget or not widget.isVisible():
            return

        self._selector_widget = widget
        self.adjustSize()
        w = self.width()
        h = self.height()

        # Use bounding rect for reliable global positioning across scroll areas
        rect = widget.rect()
        global_top_left = widget.mapToGlobal(rect.topLeft())
        global_bottom_left = widget.mapToGlobal(rect.bottomLeft())

        screen = self.screen()
        sg = screen.availableGeometry()

        x = global_bottom_left.x()
        if x + w > sg.right():
            x = sg.right() - w
        if x < sg.left():
            x = sg.left()

        y = global_bottom_left.y()
        if y + h > sg.bottom() + 2:
            y = global_top_left.y() - h
        if y < sg.top():
            y = sg.top()

        self.move(x, y)
        self.show()
        self.activateWindow()
        self._is_visible = True
        self._install_filter()

    def hideEvent(self, event):
        self._remove_filter()
        super().hideEvent(event)

    def showEvent(self, event):
        self._install_filter()
        super().showEvent(event)


class ModelSelector(QFrame):
    """
    Кликабельная карточка выбора модели.
    При клике показывает ModelDropdown.
    """

    model_changed = pyqtSignal(str, str, float)  # model_id, name, rating

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_name = ""
        self._current_rating = 3.0
        self._current_id = ""

        self.setStyleSheet(
            f"QFrame {{ background:{C_CARD}; border:1px solid {C_BORDER};"
            f" border-radius:{scale(10)}px; padding:{scale(8)}px; }}"
            f"QFrame:hover {{ background:#14142a; }}"
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(scale(12), scale(8), scale(12), scale(8))
        layout.setSpacing(scale(6))

        self._name_lbl = QLabel("—")
        self._name_lbl.setStyleSheet(
            f"color:{C_TEXT}; font-family:'Segoe UI'; font-size:{max(10,int(12*1))}pt;"
            f" background:transparent;"
        )
        layout.addWidget(self._name_lbl, stretch=1)

        self._stars_lbl = QLabel("")
        self._stars_lbl.setStyleSheet(
            f"color:#f7c948; font-size:{max(9,int(10*1))}pt; background:transparent;"
        )
        layout.addWidget(self._stars_lbl)

        self._arrow_lbl = QLabel("▼")
        self._arrow_lbl.setStyleSheet(
            f"color:{C_MUTED}; font-size:{max(9,int(10*1))}pt; background:transparent;"
        )
        layout.addWidget(self._arrow_lbl)

        self._dropdown = ModelDropdown(self)
        self._dropdown.model_selected.connect(self._on_model_selected)

    def set_model(self, model_id: str, name: str, rating: float):
        self._current_id = model_id
        self._current_name = name
        self._current_rating = rating
        self._name_lbl.setText(name)
        self._update_stars(rating)

    def _update_stars(self, rating: float):
        full = int(rating)
        half = (rating - full) >= 0.4
        empty = 5 - full - (1 if half else 0)
        self._stars_lbl.setText("★" * full + ("✦" if half else "") + "☆" * empty)

    def _on_model_selected(self, model_id: str, name: str, rating: float):
        self.set_model(model_id, name, rating)
        self.model_changed.emit(model_id, name, rating)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dropdown.show_at_widget(self)
        super().mousePressEvent(event)

    def build_from_manager(self, license_manager):
        """Заполнить модели из license_manager."""
        models = license_manager.allowed_models
        current = license_manager.current_model
        self._dropdown.build_from_models(models, current)
        for m in models:
            if m[0] == current:
                self.set_model(current, m[1], m[2])
                break