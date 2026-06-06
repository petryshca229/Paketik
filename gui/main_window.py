"""
gui/main_window.py — Главное окно Paketik 4.7.1 (QMainWindow)

Изменения по сравнению с 5.0:
  • Убрана встроенная BrowserPanel (QWebEngineView) — она вызывала зависание
    из-за конфликта между Qt event loop и asyncio-loop агента (nodriver/CDP).
  • Агент теперь запускается БЕЗ use_gui_browser / browser_control — как в 4.7,
    nodriver поднимает внешний Chrome и работает через CDP. Это рабочий путь.
  • Центральная область заменена на LogPanel (всегда видимый) — окно теперь
    компактнее, пользователь видит прогресс/логи агента и отдельное окно Chrome.
"""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QSplitter, QLabel, QPushButton, QStatusBar, QScrollArea
)
from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QFont, QPainter, QColor, QLinearGradient, QKeyEvent, QIcon

from .theme import (
    C_BG, C_PANEL, C_CARD, C_BORDER, C_ACCENT, C_TEXT, C_MUTED,
    C_GREEN, C_YELLOW, C_RED, C_LOG_BG, LOG_W, scale,
    apply_dark_palette, load_ui_state, save_ui_state,
)
from .left_panel import LeftPanel
from .log_panel import LogPanel
from .settings_panel import SettingsPanel
from .signals import AgentSignals

import threading
import config


class StatusBarWidget(QStatusBar):
    """Кастомный статус-бар с LED-индикатором."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"background:#08080f; color:{C_MUTED}; border-top:1px solid {C_BORDER};"
        )
        self.setFixedHeight(scale(28))

        # LED indicator
        self._led_canvas = QFrame()
        self._led_canvas.setFixedSize(scale(10), scale(10))
        self._led_canvas.setStyleSheet(
            f"background:{C_MUTED}; border-radius:{scale(5)}px;"
        )
        self._led_timer = QTimer(self)
        self._led_timer.timeout.connect(self._blink)
        self._led_state = True

        self._status_lbl = QLabel("Готов к работе")
        self._status_lbl.setStyleSheet(
            f"color:{C_MUTED}; font-family:'Segoe UI'; font-size:{max(8, int(10 * 1))}pt;"
        )

        self._author_lbl = QLabel("By Kaban4ik")
        self._author_lbl.setStyleSheet(
            f"color:#1e1e30; font-family:'Segoe UI'; font-size:{max(7, int(9 * 1))}pt;"
        )

        self.addWidget(self._led_canvas)
        self.addWidget(self._status_lbl, stretch=1)
        self.addPermanentWidget(self._author_lbl)

    def set_status(self, text: str):
        self._status_lbl.setText(text)

    def set_running(self, running: bool):
        color = C_GREEN if running else C_MUTED
        self._led_canvas.setStyleSheet(
            f"background:{color}; border-radius:{scale(5)}px;"
        )
        if running:
            self._led_timer.start(600)
        else:
            self._led_timer.stop()
            self._led_canvas.setStyleSheet(
                f"background:{C_MUTED}; border-radius:{scale(5)}px;"
            )

    def _blink(self):
        self._led_state = not self._led_state
        color = C_GREEN if self._led_state else "#1a3a2a"
        self._led_canvas.setStyleSheet(
            f"background:{color}; border-radius:{scale(5)}px;"
        )


class AppWindow(QMainWindow):
    """
    Главное окно Paketik 4.7.1.

    Layout: [LeftPanel] [SettingsPanel?] [LogPanel (всегда)] + StatusBar.
    Встроенного браузера нет — nodriver открывает Chrome отдельным окном.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Paketik")
        # Окно теперь компактнее, т.к. браузер вынесен в отдельный процесс.
        # Минимальную ширину НЕ фиксируем большой — окно должно ужиматься до
        # ширины левой панели, когда логи/настройки скрыты (иначе пустые поля).
        self.resize(820, 720)
        self.setMinimumHeight(600)
        self.setStyleSheet(f"background:{C_BG};")

        # Window icon — use PNG
        from pathlib import Path
        ico_path = Path(__file__).parent.parent / "res" / "icons" / "logo.png"
        if ico_path.exists():
            self.setWindowIcon(QIcon(str(ico_path)))

        # Сохранённое состояние интерфейса (открытые панели, последний профиль)
        self._ui_state = load_ui_state()
        # Пока идёт инициализация — НЕ перезаписываем сохранённое состояние
        # (заполнение combo профилей шлёт сигналы, которые иначе затёрли бы его).
        self._restoring_ui = True

        # Состояние панелей и агента
        self._settings_visible = False
        self._logs_visible = False
        self._agent = None
        self._agent_thread = None

        self._agent_signals = AgentSignals()

        # Менеджер звуковых уведомлений
        from .sound_manager import SoundManager
        self._sound_manager = SoundManager()

        # Насильно инициализируем demo-режим если лицензия неактивна
        from license_mgr import license_manager
        if not license_manager.is_active:
            pass  # _init_demo уже вызывается в __init__ LicenseManager

        self._setup_ui()
        self._connect_signals()

        # Initial license UI (после setup_ui, лицензия уже инициализирована)
        self._refresh_license_ui()
        self._refresh_profiles()

        # Восстанавливаем сохранённое состояние интерфейса
        self._apply_ui_state()

        # Stats update timer
        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._update_stats)
        self._stats_timer.start(2000)

    # ── UI setup ─────────────────────────────────────────────────────────────

    def _setup_ui(self):
        # Central widget
        central = QFrame()
        central_layout = QHBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        # Left panel — width relative to screen, capped
        screen = self.screen()
        available_w = screen.availableGeometry().width()
        left_w = min(440, max(320, int(available_w * 0.26)))
        self._left_w = left_w
        self._left_panel = LeftPanel(self)
        self._left_panel.setFixedWidth(left_w)
        self._left_panel.start_requested.connect(self._on_start)
        self._left_panel.stop_requested.connect(self._on_stop)
        self._left_panel.pause_requested.connect(self._on_pause)
        self._left_panel.activate_requested.connect(self._on_activate)
        self._left_panel.profile_save.connect(self._on_profile_save)
        self._left_panel.profile_delete.connect(self._on_profile_delete)
        self._left_panel.profile_selected.connect(self._on_profile_selected)
        self._left_panel.test_sound.connect(self._on_play_sound)
        self._left_panel.logo_clicked.connect(self._on_logo_clicked)

        # Settings panel (slides in between LeftPanel и LogPanel)
        self._settings_panel = SettingsPanel(self)
        self._settings_panel.hide()
        self._settings_panel.settings_changed.connect(self._on_settings_changed)
        # browser_zoom_changed сигнал больше ничего не делает (нет встроенного браузера),
        # но подключаем чтобы не падало если SettingsPanel его испускает
        if hasattr(self._settings_panel, "browser_zoom_changed"):
            self._settings_panel.browser_zoom_changed.connect(self._on_browser_zoom_changed)

        central_layout.addWidget(self._left_panel)
        central_layout.addWidget(self._settings_panel)

        # Log panel — по умолчанию скрыта, состояние восстанавливается из ui_state
        self._log_panel = LogPanel(self)
        self._log_panel.setMinimumWidth(LOG_W)
        self._log_panel.hide()
        central_layout.addWidget(self._log_panel, stretch=1)

        self.setCentralWidget(central)

        # Status bar
        self._status_bar = StatusBarWidget(self)
        self.setStatusBar(self._status_bar)

    def _connect_signals(self):
        signals = self._agent_signals
        signals.log_message.connect(self._log_panel.append)
        signals.status_update.connect(self._status_bar.set_status)
        signals.stats_update.connect(self._left_panel.update_stats)
        signals.tests_found.connect(self._show_test_selector)
        signals.test_finished.connect(self._on_test_finished)
        signals.error_occurred.connect(self._on_agent_error)
        signals.play_sound.connect(self._on_play_sound)
        signals.results_ready.connect(self._on_results_ready)

    @pyqtSlot(str)
    def _on_play_sound(self, key: str):
        """Проигрывает звук уведомления в GUI-потоке."""
        try:
            self._sound_manager.play(key)
        except Exception:
            pass

    @pyqtSlot(dict)
    def _on_results_ready(self, results: dict):
        """Получили статистику теста — показываем окно ПОСЛЕ закрытия браузера.

        Агент шлёт сигнал ~за 3с до закрытия браузера; откладываем показ,
        чтобы окно появилось уже после того, как Chrome закрылся.
        """
        self._pending_results = dict(results or {})
        QTimer.singleShot(4500, self._show_results_window)

    def _show_results_window(self):
        results = getattr(self, "_pending_results", None)
        if not results:
            return
        self._pending_results = None
        try:
            from .results_window import ResultsWindow
            dlg = ResultsWindow(results, self)
            dlg.exec()
        except Exception as exc:
            self._agent_signals.log_message.emit(f"[!] Окно результатов: {exc}")

    def _on_logo_clicked(self):
        """Клик по логотипу — случайная звуковая пасхалка."""
        try:
            self._sound_manager.play_easter_egg()
        except Exception:
            pass

    # ── Actions ──────────────────────────────────────────────────────────────

    def _on_start(self):
        if self._agent:
            # Уже работает — игнорируем повторный клик
            return

        from agent import TestAgent
        login, password = self._left_panel.get_auth_credentials()
        task_text = self._left_panel.get_task_text()

        # Лицензия / токены
        try:
            from license_mgr import license_manager
            if not license_manager.is_active:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Нет лицензии", "Активируйте лицензию.")
                return
            info = license_manager.get_summary()
            if info.get("balance", 0) <= 0:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Токены", "Токены исчерпаны.")
                return
        except Exception:
            pass

        # Браузер: путь к исполняемому файлу + user_data_dir определяет агент сам
        # (через utils.find_browser_executable / utils.get_user_data_dir внутри nodriver-ветки).
        # Сброс состояния выбора теста для нового запуска
        self._available_tests = []
        self._selected_test = None
        self._test_selection_lock = threading.Lock()

        # Никакого use_gui_browser / browser_control — это и было причиной зависания в 5.0.
        self._agent = TestAgent(
            browser_ws_url=None,
            user_data_dir=None,
            browser_executable=None,
            log_cb=lambda msg: self._agent_signals.log_message.emit(msg),
            status_cb=lambda s: self._agent_signals.status_update.emit(s),
            task_description=task_text,
            login=login,
            password=password,
            agent_signals=self._agent_signals,
            tests_cb=self._on_tests_found,
            get_selected_test=self._get_selected_test,
            use_gui_browser=False,      # ← внешний Chrome через nodriver, как в 4.7
            browser_control=None,
        )

        # TestAgent.start() сам создаёт asyncio.new_event_loop() и блокирует
        # поток через run_until_complete. Используем ПРОСТОЙ threading.Thread, а
        # не QThread: TestAgent создан в GUI-потоке и не перенесён через
        # moveToThread(), поэтому QThread.started.connect(agent.start) исполнял бы
        # start() обратно в GUI-потоке (queued connection) и вешал весь интерфейс.
        self._agent_thread = threading.Thread(
            target=self._agent.start, daemon=True, name="PaketikAgent"
        )
        self._agent_thread.start()

        self._status_bar.set_running(True)
        self._left_panel.set_running_state(True)
        self._left_panel.start_pulse()
        self._agent_signals.log_message.emit("[*] Paketik запущен!")

    def _on_stop(self, wait: bool = False):
        if self._agent:
            try:
                self._agent.stop()
            except Exception as exc:
                self._agent_signals.log_message.emit(f"[!] Ошибка остановки: {exc}")
        # agent.stop() отменяет async-задачу; поток выходит из run_until_complete,
        # после чего finally в start() закрывает браузер.
        thread = self._agent_thread
        if wait and thread is not None:
            try:
                # Ждём, пока поток агента закроет браузер и завершится (до 10с).
                thread.join(timeout=10.0)
            except Exception:
                pass
        self._agent_thread = None
        self._agent = None
        self._status_bar.set_running(False)
        self._left_panel.set_running_state(False)
        self._left_panel.stop_pulse()
        self._agent_signals.log_message.emit("[i] Агент остановлен")

    def _on_pause(self):
        if self._agent:
            if not getattr(self._agent, "_pause_flag", False):
                self._agent.pause()
                self._agent_signals.log_message.emit("[*] Пауза")
            else:
                self._agent.resume()
                self._agent_signals.log_message.emit("[>] Продолжаем")

    def _on_activate(self, key: str):
        try:
            from license_mgr import license_manager
            ok, msg = license_manager.activate(key)
            self._left_panel.activation_result(ok, msg)
            self._refresh_license_ui()
        except Exception as exc:
            self._left_panel.activation_result(False, str(exc))

    def _on_profile_save(self, label: str, login: str, password: str):
        try:
            from accounts import account_manager
            account_manager.save_profile(label, login, password)
            self._refresh_profiles()
            self._agent_signals.log_message.emit(f"[OK] Профиль '{label}' сохранён")
        except Exception as exc:
            self._agent_signals.log_message.emit(f"[!] Ошибка сохранения: {exc}")

    def _on_profile_delete(self, label: str):
        try:
            from accounts import account_manager
            account_manager.delete_profile(label)
            self._refresh_profiles()
            self._agent_signals.log_message.emit(f"[i] Профиль '{label}' удалён")
        except Exception as exc:
            self._agent_signals.log_message.emit(f"[!] Ошибка удаления: {exc}")

    def _on_profile_selected(self, label: str):
        if label == "Новый профиль":
            self._left_panel.fill_profile("", "")
            self._persist_ui_state()
            return
        try:
            from accounts import account_manager
            profile = account_manager.get_profile(label)
            if profile:
                self._left_panel.fill_profile(profile["login"], profile["password"])
        except Exception:
            pass
        # Запоминаем выбранный профиль для следующего запуска
        self._persist_ui_state()

    def _on_test_finished(self):
        self._agent_signals.log_message.emit("[OK] Тест завершён!")
        self._status_bar.set_running(False)
        self._left_panel.set_running_state(False)
        self._left_panel.stop_pulse()

    # ── Выбор теста ────────────────────────────────────────────────────────────

    def _on_tests_found(self, tests: list):
        """Вызывается из потока агента — пробрасываем список в GUI-поток."""
        self._available_tests = list(tests or [])
        # tests_found — Qt-сигнал, безопасно маршалится в GUI-поток.
        self._agent_signals.tests_found.emit(self._available_tests)

    def _get_selected_test(self):
        """Вызывается из потока агента (опросом) — возвращает выбранный тест."""
        with self._test_selection_lock:
            return self._selected_test

    @pyqtSlot(list)
    def _show_test_selector(self, tests: list):
        """Показывает диалог выбора теста (в GUI-потоке)."""
        if not tests:
            self._agent_signals.log_message.emit("[!] Список тестов пуст")
            return
        from .test_selector import TestSelectorDialog
        dlg = TestSelectorDialog(tests, self)
        result = dlg.exec()
        if dlg.is_manual():
            # Пользователь выберет тест сам в браузере (или истёк авто-старт).
            with self._test_selection_lock:
                self._selected_test = {"manual": True}
            self._agent_signals.log_message.emit(
                "[i] Ручной режим: откройте тест сами — ИИ приступит."
            )
        elif result and dlg.get_selected():
            chosen = dlg.get_selected()
            with self._test_selection_lock:
                self._selected_test = chosen
            self._agent_signals.log_message.emit(
                f"[OK] Выбран тест: {chosen.get('name', '?')}"
            )
        else:
            # Отмена — останавливаем агента.
            self._agent_signals.log_message.emit("[i] Выбор теста отменён")
            self._on_stop()

    @pyqtSlot(str)
    def _on_agent_error(self, msg: str):
        self._agent_signals.log_message.emit(f"[!] {msg}")
        # Звук на любую ошибку агента, не связанную с ИИ
        try:
            self._sound_manager.play("error")
        except Exception:
            pass

    def _on_settings_changed(self):
        self._agent_signals.log_message.emit(
            "[i] Настройки применены. Перезапустите для полного эффекта."
        )

    def _on_browser_zoom_changed(self, zoom: float):
        # No-op: встроенного браузера больше нет. Оставлено для совместимости
        # с SettingsPanel, который может всё ещё испускать сигнал.
        self._agent_signals.log_message.emit(
            f"[i] Zoom браузера = {zoom:.2f} (применится в Chrome через Ctrl+/–)"
        )

    # ── Panel toggles ─────────────────────────────────────────────────────────

    def toggle_log_panel(self):
        self._logs_visible = not self._logs_visible
        self._log_panel.setVisible(self._logs_visible)
        self._adjust_window_width()
        self._persist_ui_state()

    def toggle_settings_panel(self):
        self._settings_visible = not self._settings_visible
        if self._settings_visible:
            self._settings_panel.show()
            self._settings_panel.setFixedWidth(300)
        else:
            self._settings_panel.hide()
        self._adjust_window_width()
        self._persist_ui_state()

    def _adjust_window_width(self):
        """Подгоняет ширину окна точно под видимые панели (без пустого места)."""
        try:
            width = getattr(self, "_left_w", 360)
            if self._settings_visible:
                width += 300            # фиксированная ширина SettingsPanel
            if self._logs_visible:
                width += LOG_W          # фиксированная ширина LogPanel
            # Минимальная ширина окна = ширина видимых панелей.
            self.setMinimumWidth(width)
            self.setMaximumWidth(width if not self._logs_visible else 16777215)
            self.resize(width, self.height())
        except Exception:
            pass

    # ── UI-state persistence ───────────────────────────────────────────────────

    def _apply_ui_state(self):
        """Восстанавливает открытые панели и последний профиль из ui_state.json."""
        state = getattr(self, "_ui_state", {}) or {}

        # Панель настроек
        if state.get("settings_open"):
            self._settings_visible = False  # toggle инвертирует → станет True
            self.toggle_settings_panel()

        # Панель логов
        if state.get("logs_open"):
            self._logs_visible = False
            self.toggle_log_panel()

        # Последний выбранный профиль
        last_profile = state.get("last_profile", "")
        if last_profile:
            try:
                self._left_panel.select_profile(last_profile)
            except Exception:
                pass

        # Подгоняем размер окна под итоговый набор видимых панелей
        self._adjust_window_width()

        # Восстановление завершено — снимаем блокировку и фиксируем итоговое
        # состояние (на случай если что-то изменилось при выборе профиля).
        self._restoring_ui = False
        self._persist_ui_state()

    def _persist_ui_state(self):
        """Сохраняет текущее состояние интерфейса между запусками."""
        if getattr(self, "_restoring_ui", False):
            return  # во время восстановления не трогаем файл
        try:
            last_profile = ""
            if hasattr(self._left_panel, "current_profile"):
                last_profile = self._left_panel.current_profile()
            self._ui_state = {
                "settings_open": bool(self._settings_visible),
                "logs_open":     bool(self._logs_visible),
                "last_profile":  last_profile,
            }
            save_ui_state(self._ui_state)
        except Exception:
            pass

    # ── Refresh ──────────────────────────────────────────────────────────────

    def _refresh_license_ui(self):
        try:
            from license_mgr import license_manager
            info = license_manager.get_summary()
            self._left_panel.update_license_ui(info)
        except Exception:
            pass

    def _refresh_profiles(self):
        try:
            from accounts import account_manager
            labels = account_manager.labels
            self._left_panel.refresh_profiles(labels)
        except Exception:
            pass

    def _update_stats(self):
        try:
            from utils import session_stats
            from license_mgr import license_manager
            info = license_manager.get_summary()
            self._left_panel.update_stats({
                "questions": session_stats.questions_answered,
                "actions":   session_stats.actions_total,
                "tokens":    session_stats.tokens_spent,
                "balance":   info.get("balance", 0),
                "time":      session_stats.elapsed_str(),
                "errors":    session_stats.errors,
            })
            self._left_panel.update_license_ui(info)
        except Exception:
            pass

    # ── Close ────────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        # Сохраняем состояние интерфейса (открытые панели, профиль) на следующий запуск.
        self._persist_ui_state()
        # При закрытии приложения ждём, пока агент закроет браузер,
        # чтобы не оставить висеть процесс Chrome.
        self._on_stop(wait=True)
        event.accept()
