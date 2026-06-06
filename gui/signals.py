"""
gui/signals.py — Thread-safe signals для общения Agent → GUI
"""

from PyQt6.QtCore import QObject, pyqtSignal


class AgentSignals(QObject):
    """
    Сигналы для передачи данных из worker thread (Agent) в GUI thread.

    Все сигналы Qt автоматически thread-safe —
    Qt самостоятельно marshalsет вызовы через event loop.
    """

    log_message   = pyqtSignal(str)        # строка в журнал
    status_update = pyqtSignal(str)        # текст статус-бара
    stats_update  = pyqtSignal(dict)       # {questions, actions, tokens, errors, time_str}
    browser_ready = pyqtSignal(str)        # ws_url когда браузер готов
    tests_found   = pyqtSignal(list)       # список доступных тестов (для диалога выбора)
    test_started  = pyqtSignal()           # тест начат
    test_finished = pyqtSignal()           # тест завершён
    error_occurred = pyqtSignal(str)       # ошибка в агенте
    token_balance_update = pyqtSignal(int)  # обновление баланса токенов
    play_sound    = pyqtSignal(str)        # ключ звука: ai_error|test_done|error
    results_ready = pyqtSignal(dict)       # статистика результатов теста (для окна)
