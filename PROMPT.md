# AI Prompt: Paketik 5.0 — PyQt6 GUI Rewrite

## Контекст

Есть проект Paketik 4.6 — приложение для AI-автоматического прохождения онлайн-тестов (uup.tigt.site).
Текущий GUI на Tkinter/CustomTkinter (1677 строк в gui.py).
Переписать GUI на **PyQt6** с встроенным браузером (`QWebEngineView`).

**Полный план архитектуры:** файл `SPEC.md` в этой же директории. ЧИТАЙ ЕГО ПЕРЕД НАЧАЛОМ.

---

## Что менять (и только это)

```
❌ НЕ ТРОГАТЬ:
  - agent.py       ( вся логика AI-агента — неприкасаема )
  - license_mgr.py ( лицензии/токены/Supabase — неприкасаем )
  - accounts.py     ( профили — неприкасаем )
  - config.py      ( все константы — неприкасаем )
  - utils.py       ( утилиты — неприкасаем )
  - assets/        ( PNG-иконки — неприкасаемы )

✅ НАПИСАТЬ С НУЛЯ:
  - main.py        ( адаптация под PyQt6)
  - gui/
      ├── theme.py          (.color constants, stylesheet builder)
      ├── widgets.py        ( StatCell, SectionHeader, GradientLabel )
      ├── left_panel.py    ( левая панель: Task + Auth + License + Controls + Session )
      ├── browser_panel.py ( QWebEngineView — браузер ВНУТРИ окна )
      ├── log_panel.py     ( QTextEdit readonly + журнал )
      ├── settings_panel.py ( настройки вида )
      ├── model_dropdown.py ( кастомный dropdown с моделями )
      ├── test_selector.py  ( диалог выбора теста )
      ├── main_window.py   ( QMainWindow, собирает всё вместе )
```

---

## Архитектура: Signals/Slots

Создай ОДИН файл `gui/signals.py`:

```python
from PyQt6.QtCore import QObject, Signal

class AgentSignals(QObject):
    """Thread-safe signals для общения Agent → GUI."""
    log_message    = Signal(str)
    status_update  = Signal(str)
    stats_update   = Signal(dict)   # {questions:, actions:, tokens:, errors:, time:}
    browser_ready  = Signal(str)    # ws_url когда браузер готов
    test_started   = Signal()
    test_finished  = Signal()
    error_occurred = Signal(str)
```

Агенту (agent.py) при инициализации передай объект этих сигналов.
Внутри agent.py НЕ меняй ничего кроме способа вызова callback'ов —
вместо `log_cb(msg)` делай `self.signals.log_message.emit(msg)`.

**agent.py менять МОЖНО** — но только для замены callback'ов на signals.
Всю остальную логику не трогай.

---

## theme.py

```python
C_BG      = "#0b0b14"
C_PANEL   = "#10101c"
C_CARD    = "#16162a"
C_BORDER  = "#252540"
C_ACCENT  = "#7c6cf2"
C_ACCENT2 = "#5c9cf5"
C_GREEN   = "#3ddc97"
C_YELLOW  = "#f7c948"
C_RED     = "#e05c5c"
C_TEXT    = "#e8e8f8"
C_MUTED   = "#5a5a7a"
C_LOG_BG  = "#08080f"

# progress bar gradient
def progress_color(pct: float) -> str:
    if pct < 0.6:
        t = pct / 0.6
        r = int(0x3d + (0xf7 - 0x3d)*t)
        g = int(0xdc + (0xc9 - 0xdc)*t)
        b = int(0x97 + (0x48 - 0x97)*t)
    else:
        t = (pct - 0.6) / 0.4
        r = int(0xf7 + (0xe0 - 0xf7)*t)
        g = int(0xc9 + (0x5c - 0xc9)*t)
        b = int(0x48 + (0x5c - 0x48)*t)
    return f"#{r:02x}{g:02x}{b:02x}"

# Stylesheet builder
def btn_style(bg: str, fg: str = "white", hover: str = None,
              border: str = None, radius: int = 8) -> str:
    b = border if border else bg
    h = hover if hover else bg
    return (
        f"QPushButton {{ background:{bg}; color:{fg}; "
        f"border:1px solid {b}; border-radius:{radius}px; "
        f"padding:4px 12px; font-family:'Segoe UI'; }}"
        f"QPushButton:hover {{ background:{h}; }}"
        f"QPushButton:disabled {{ background:#1e1e2e; color:#3a3a5a; border:1px solid #252540; }}"
    )

def card_style(bg: str = C_CARD, border: str = C_BORDER) -> str:
    return f"QFrame {{ background:{bg}; border:1px solid {border}; border-radius:13px; }}"

def section_label() -> str:
    return (
        f"QLabel {{ color:{C_ACCENT}; font-family:'Segoe UI'; "
        f"font-weight:bold; font-size:11pt; }}"
    )

def log_font(size: int = 12) -> QFont:
    return QFont("Segoe UI", size)
```

---

## LeftPanel Layout (детальный)

```
┌─────────────────────────────────┐
│ [ЗАДАЧА]  ← section label      │
│ ┌─────────────────────────────┐ │
│ │ QTextEdit (60px, multiline) │ │
│ └─────────────────────────────┘ │
│                                 │
│ [АВТОРИЗАЦИЯ]                   │
│ ┌─────────────────────────────┐ │
│ │ Логин:                     │ │
│ │ [QLineEdit placeholder]   │ │
│ │ Пароль:                    │ │
│ │ [QLineEdit password]       │ │
│ │ [Profile ▾]               │ │
│ │ [💾 Сохранить] [🗑 Удалить]  │ │
│ └─────────────────────────────┘ │
│                                 │
│ [ЛИЦЕНЗИЯ]                      │
│ ┌─────────────────────────────┐ │
│ │ [💚] Pro Edition            │ │
│ │ Действует до: 01.01.2026   │ │
│ │ 12 500 / 100 000 токенов   │ │
│ │ [████████░░░░░░░░░░] 12.5%  │ │
│ │ [XXXX-XXXX-XXXX-XXXX]      │ │
│ │ [   Активировать   ]      │ │
│ │ 🤖  Модель AI:            │ │
│ │ ┌─────────────────────────┐ │ │
│ │ │ DeepSeek V3.2  ★★★☆☆ ▼ │ │ │  ← кликабельная карточка
│ │ └─────────────────────────┘ │ │
│ └─────────────────────────────┘ │
│                                 │
│ [УПРАВЛЕНИЕ]                    │
│ ┌─────────────────────────────┐ │
│ │ [    ▶ Запустить браузер   ]│ │  ← pulse animation когда запущен
│ │ [   Пауза   ] [   Стоп   ] │ │
│ └─────────────────────────────┘ │
│                                 │
│ [СЕССИЯ]                        │
│ ┌───────────┬───────────┐       │
│ │ Вопросов  │ Действий  │       │
│ │   12      │   18      │       │
│ ├───────────┼───────────┤       │
│ │ Токенов   │ Остаток   │       │
│ │  4 820    │  15 180   │       │
│ ├───────────┼───────────┤       │
│ │ Время     │ Ошибок    │       │
│ │  00:05:42 │    0      │       │
│ └───────────┴───────────┘       │
└─────────────────────────────────┘
```

---

## browser_panel.py

**КРИТИЧНОЕ ТРЕБОВАНИЕ:** Браузер теста ВСТРОЕН в приложение через `QWebEngineView`.

```python
class BrowserPanel(QWebEngineView):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Загружаем TARGET_URL
        self.load(QUrl("https://uup.tigt.site/test/"))

    def inject_js(self, script: str):
        """Выполнить JS в контексте страницы."""
        self.page().runJavaScript(script)

    def get_dom_state(self) -> str:
        """
        Извлекает структурированные данные со страницы теста.
        То же самое что _capture_state() в agent.py, но через Qt JS.
        """
        script = """
        (() => {
            const q = document.getElementById('qst');
            const questionText = q ? q.innerText.trim() : '';
            const rows = document.querySelectorAll('tr.varanswer');
            const answers = [];
            for (let i = 0; i < rows.length; i++) {
                const row = rows[i];
                const td = row.querySelector('td[id^="rtext"]');
                const inp = row.querySelector('input');
                const text = td ? td.innerText.trim() : row.innerText.trim();
                const type = inp ? inp.type : 'unknown';
                const checked = inp ? inp.checked : false;
                answers.push('' + (i+1) + '. ' + (checked ? '[x]' : '[ ]') + '(' + type + ') ' + text);
            }
            const fields = [];
            const inps = document.querySelectorAll('input.inpas, input[type="text"]');
            for (let i = 0; i < inps.length; i++) {
                fields.push((inps[i].placeholder || 'field' + i) + '=' + (inps[i].value || ''));
            }
            const saveBtn = document.getElementById('SaveButton');
            const hasSave = saveBtn && saveBtn.offsetParent !== null;
            return questionText + '|||' + answers.join('\\n') + '|||' + fields.join('\\n') + '|||' + (hasSave ? 'SAVE_VISIBLE' : 'NO_SAVE');
        })()
        """
        future = QFuture()
        # Используй QWebEngineView.page().runJavaScript() с CallbackRunner
        # или RunJavaScript через QWebEnginePage.runJavaScript
        ...
```

**Примечание:** Agent управляет браузером через JS injection. BrowserPanel предоставляет методы `inject_js()` и `get_dom_state()` — агент вызывает их.

**SSL bypass:** перехвати `QWebEnginePageCertificateError` и вызови `.acceptCertificateError()`.

---

## main_window.py (скелет)

```python
class AppWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Paketik  {config.APP_VERSION}")
        self.resize(920, 720)
        self.setMinimumSize(900, 600)
        self._setup_ui()
        self._connect_signals()

        # Agent worker thread
        self._agent: Optional[TestAgent] = None
        self._agent_thread: Optional[QThread] = None
        self._agent_signals = AgentSignals()

    def _setup_ui(self):
        central = QSplitter(Qt.Orientation.Horizontal)
        self.left_panel = LeftPanel(self)
        self.browser_panel = BrowserPanel(self)
        self.log_panel = LogPanel(self)

        central.addWidget(self.left_panel)
        central.addWidget(self.browser_panel)
        central.addWidget(self.log_panel)
        central.setStretchFactor(0, 0)  # left fixed
        central.setStretchFactor(1, 1)  # browser stretches
        central.setStretchFactor(2, 0)  # log fixed

        # Widths
        self.left_panel.setFixedWidth(380)
        self.log_panel.setFixedWidth(400)

        self.setCentralWidget(central)
        self.status_bar_widget = StatusBar(self)
        self.setStatusBar(self.status_bar_widget)

    def _connect_signals(self):
        signals = self._agent_signals
        signals.log_message.connect(self.log_panel.append)
        signals.status_update.connect(self.status_bar_widget.set_text)
        signals.stats_update.connect(self.left_panel.update_stats)
```

---

## agent.py — адаптация

В `agent.py` в `__init__` добавь параметр:

```python
def __init__(self, ..., agent_signals=None):
    self._agent_signals = agent_signals
```

Замени все `log_cb(msg)` на:

```python
if self._agent_signals:
    self._agent_signals.log_message.emit(msg)
else:
    logger.info(msg)
```

Замени все `status_cb(s)` на:

```python
if self._agent_signals:
    self._agent_signals.status_update.emit(s)
```

Stats — через `stats_update.emit({...})`.

**Получение DOM из BrowserPanel:**

Создай метод-интерфейс. Agent принимает `browser_get_state_fn: Callable[[], str]` — callback который возвращает DOM-данные. BrowserPanel предоставляет `get_current_state()` → строку.

---

## model_dropdown.py

```python
class ModelDropdown(QMenu):
    """
    Кастомное меню выбора модели AI.
    Строит карточки на основе license_manager.allowed_models.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QMenu {{
                background-color: #131330;
                border: 1px solid #252540;
                border-radius: 12px;
                padding: 8px;
            }}
            QMenu::item {{
                background: transparent;
                color: #e8e8f2;
                padding: 8px 12px;
                border-radius: 6px;
            }}
            QMenu::item:selected {{
                background: #252550;
            }}
        """)
```

При клике на карточку — вызвать `license_manager.set_model(model_id)`, обновить текст на кнопке.

---

## test_selector.py

```python
class TestSelectorDialog(QDialog):
    """
    Модальное окно: пользователь выбирает тест из списка.
    """
    def __init__(self, tests: List[Dict], parent=None):
        super().__init__(parent)
        self.selected_test = None
        self.setWindowTitle("Выберите тест")
        self.setFixedSize(500, 550)
        # ... layout с карточками
```

Карточка теста:
```
┌────────────────────────────────────────┐
│ Тест: Основы электротехники            │
│ 📚 Электротехника                      │
│  90 мин   ❓ 50 вопросов   👤 И. Петров │
│                          [  Выбрать  ]│
└────────────────────────────────────────┘
```

---

## main.py (точка входа)

```python
import sys
from PyQt6.QtWidgets import QApplication
from gui.main_window import AppWindow
from gui.theme import C_BG

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setPalette(C_BG)  # базовая палитра
    app.setFont(QFont("Segoe UI", 10))
    w = AppWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
```

---

## requirements.txt (добавить)

```
# PyQt6 GUI
PyQt6>=6.7.0
PyQt6-WebEngine>=6.7.0
```

---

## PyInstaller (Paketik.spec)

```python
datas = [
    ("assets", "assets"),
    ("config.py", "."),    # без изменений
    ("agent.py", "."),
    ("license_mgr.py", "."),
    ("accounts.py", "."),
    ("utils.py", "."),
]

hiddenimports = [
    "license_mgr", "accounts", "config", "agent", "utils",
    "gui", "gui.theme", "gui.widgets", "gui.left_panel",
    "gui.browser_panel", "gui.log_panel", "gui.settings_panel",
    "gui.model_dropdown", "gui.test_selector", "gui.main_window",
    "PyQt6.QtCore", "PyQt6.QtGui", "PyQt6.QtWidgets",
    "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets",
]
```

---

## Порядок генерации (для AI-ассистента)

**ШАГ 1:** Прочитай `SPEC.md`. Прочитай все .py файлы (agent.py, license_mgr.py, accounts.py, config.py, utils.py).
**ШАГ 2:** Создай папку `gui/`. Напиши `gui/theme.py` (цвета, стили).
**ШАГ 3:** Напиши `gui/widgets.py` (StatCell, SectionHeader).
**ШАГ 4:** Напиши `gui/signals.py`.
**ШАГ 5:** Напиши `gui/left_panel.py`. Это самый большой файл — ~600-800 строк.
**ШАГ 6:** Напиши `gui/browser_panel.py`.
**ШАГ 7:** Напиши `gui/log_panel.py`.
**ШАГ 8:** Напиши `gui/model_dropdown.py`.
**ШАГ 9:** Напиши `gui/test_selector.py`.
**ШАГ 10:** Напиши `gui/settings_panel.py`.
**ШАГ 11:** Напиши `gui/main_window.py`.
**ШАГ 12:** Обнови `main.py` (вместо gui.App() → PyQt6 AppWindow).
**ШАГ 13:** Обнови `agent.py` (добавь agent_signals parameter, замени log_cb на signals).
**ШАГ 14:** Обнови `Paketik.spec` и `requirements.txt`.

---

## ВАЖНО

1. **Каждый файл — полный, рабочий код.** Никаких "здесь будет логика", никаких stubs. Всё имплементировать.
2. **Emoji РАБОТАЮТ в PyQt6.** Используй emoji прямо в тексте виджетов. DirectWrite рисует их правильно.
3. **Импорты агента:** agent.py, license_mgr.py, accounts.py, config.py, utils.py — импортируй как есть, без изменений в их коде.
4. **BrowserPanel ↔ Agent связь:** Agent НЕ импортирует BrowserPanel. Agent получает callback-функции для работы с браузером. Это separation of concerns.
5. **Thread safety:** Agent работает в QThread. Все GUI-обновления — через Signals (автоматически thread-safe в Qt).
6. **PNG-иконки:** загружай через `QPixmap` → `QIcon`:
   ```python
   def _icon(name: str, size=18) -> QIcon:
       path = Path(__file__).parent.parent / "assets" / name
       pm = QPixmap(str(path))
 	  return QIcon(pm.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio))
   ```
