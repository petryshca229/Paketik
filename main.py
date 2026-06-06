"""
main.py — Точка входа Paketik 5.0 (PyQt6 Edition)
====================================================
Запускает GUI PyQt6 после инициализации логирования и проверки зависимостей.

Запуск:
    python main.py
"""

import sys
import os

# ── Подсказка для PyInstaller: глобальные импорты локальных модулей ──────────
import config
import utils
import license_mgr
import accounts
import agent
# ────────────────────────────────────────────────────────────────────────────

# ── Проверка версии Python ────────────────────────────────────────────────────
if sys.version_info < (3, 9):
    print("Требуется Python 3.9 или выше!")
    sys.exit(1)

# ── Проверка зависимостей ─────────────────────────────────────────────────────
REQUIRED = {
    "PyQt6":                    "PyQt6",
    "PyQt6.QtWebEngineWidgets":  "PyQt6-WebEngine",
    "nodriver":                 "nodriver",
    "httpx":                    "httpx",
    "PIL":                      "Pillow",
}

missing = []
for module, package in REQUIRED.items():
    try:
        __import__(module)
    except ImportError:
        missing.append(package)

if missing:
    print(f"Не установлены зависимости: {', '.join(missing)}")
    print(f"   Выполните: pip install {' '.join(missing)}")
    sys.exit(1)

# ── Инициализация логирования ──────────────────────────────────────────────────
from utils import setup_logging
from config import LOG_FILE, LOG_LEVEL

setup_logging(LOG_FILE, LOG_LEVEL)

import logging
logger = logging.getLogger(__name__)
logger.info("=" * 60)
logger.info("  Paketik 5.0 запускается (PyQt6)...")
logger.info("=" * 60)

# ── Запуск GUI PyQt6 ─────────────────────────────────────────────────────────
def main():
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QLocale
    from gui.theme import apply_dark_palette
    from gui.main_window import AppWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Paketik")
    app.setOrganizationName("Paketik")
    apply_dark_palette(app)
    QLocale.setDefault(QLocale(QLocale.Language.Russian, QLocale.Country.Russia))

    window = AppWindow()
    window.show()

    logger.info("Приложение запущено.")
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
