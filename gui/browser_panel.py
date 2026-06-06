"""
gui/browser_panel.py — ЗАГЛУШКА (Paketik 4.7.1)

В версии 5.0 здесь был встроенный браузер на QWebEngineView, но он вызывал
зависание из-за конфликта с asyncio-loop агента (nodriver/CDP). В 4.7.1 мы
вернулись к старой схеме: nodriver открывает внешний Chrome, а здесь
оставлена пустая заглушка только для обратной совместимости импортов.

Если ничего больше не импортирует BrowserPanel — этот файл можно удалить.
"""

from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt6.QtCore import Qt


class _NullBrowserControl:
    """Заглушка интерфейса BrowserControl. Все методы — no-op."""

    def evaluate_async(self, script, callback=None):
        if callback:
            try:
                callback(None)
            except Exception:
                pass
        return None

    def is_alive(self) -> bool:
        return False


class BrowserPanel(QWidget):
    """
    Заглушка вместо встроенного браузера.

    Не наследуется от QWebEngineView и не подгружает PyQt6.QtWebEngineWidgets,
    что позволяет убрать зависимость PyQt6-WebEngine из requirements.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        msg = QLabel(
            "Браузер вынесен в отдельное окно Chrome.\n"
            "(встроенная панель отключена в Paketik 4.7.1)"
        )
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setStyleSheet("color:#888; font-family:'Segoe UI'; font-size:10pt;")
        layout.addWidget(msg)

    # Совместимость со старым API ----------------------------------------------

    def get_control(self) -> "_NullBrowserControl":
        return _NullBrowserControl()

    def setZoomFactor(self, zoom: float):
        # No-op — встроенного браузера нет
        pass

    def setUrl(self, url):
        pass

    def load(self, url):
        pass

    def reload(self):
        pass

    def back(self):
        pass

    def forward(self):
        pass
