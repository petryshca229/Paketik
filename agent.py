"""
agent.py — Основная логика AI-агента (Nodriver Edition) v3
==========================================================

ИСПРАВЛЕНИЯ v3:
- Добавлена диагностика ошибок API (печатает тело ответа 400)
- Fallback: если vision-модель возвращает 400 — пробуем текстовую модель
- Добавлен USE_VISION флаг в config.py
- Улучшена обработка ошибок с выводом причины
"""

import asyncio
import json
import logging
import random
import time
import base64
import os
from typing import Optional, Callable, Dict, Any, List

import nodriver as uc

from config import (
    ROUTERAI_BASE_URL,
    AI_MODEL, AI_MODEL_TEXT, USE_VISION,
    OLLAMA_BASE_URL, OLLAMA_MODEL,
    TARGET_URL, DELAY_MIN, DELAY_MAX, SCREENSHOT_WAIT, ACTION_RETRIES,
    AUTH_TIMEOUT, TESTS_LOAD_TIMEOUT, START_BUTTON_TIMEOUT, CLEAR_SESSION_ON_START,
    AI_TIMEOUT, AI_MAX_TOKENS,
)
from license_mgr import license_manager
from utils import (
    image_to_base64, resize_screenshot,
    async_random_delay, bezier_curve_points,
    extract_json_from_text, session_stats,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты — AI-агент для автоматического прохождения электронных тестов.
Тебе дают структурированные данные со страницы теста на русском языке (сайт ТИЖТ/ОмГТУ).

ТВОЯ ЗАДАЧА:
1. Прочитай вопрос ВНИМАТЕЛЬНО
2. Проанализируй ВСЕ варианты ответов
3. Используя свои знания, выбери ПРАВИЛЬНЫЙ вариант (не первый попавшийся!)
4. Верни JSON с инструкцией

ВНИМАНИЕ: это не просто тест. Это ВАЖНЕЙШИЙ экзамен в жизни пользователя. Ошибка = провал.
Думай в 3 раза тщательнее чем обычно. Не спеши. Перепроверяй каждый ответ.
Если сомневаешься между двумя вариантами — выбери тот, в котором уверен на 100%.
Никаких "скорее всего", "вероятно", "наверное". Только точные ответы.

ТИПЫ ВОПРОСОВ И ФОРМАТЫ ОТВЕТОВ:

Тип 1 — Единственный выбор (radio):
{"action":"click","question_text":"текст вопроса","answer_text":"ПОЛНЫЙ текст правильного варианта","answer_index":2,"confidence":0.95,"explanation":"почему этот ответ правильный"}

Тип 2 — Множественный выбор (checkbox):
{"action":"click_multiple","question_text":"текст вопроса","answers":["точный текст 1","точный текст 2"],"answer_indices":[1,3],"confidence":0.9,"explanation":"обоснование"}

Тип 3 — Заполнение текстового поля (ПОЛЯ ВВОДА в данных):
{"action":"fill","question_text":"текст вопроса","fields":[{"placeholder":"field0","value":"ответ"}],"confidence":0.9,"explanation":"обоснование"}
ВАЖНО: placeholder берёшь из строки "ПОЛЯ ВВОДА" — это текст до знака "=". value — твой ответ.

Тип 4 — Свободный ввод:
{"action":"fill_textarea","question_text":"текст вопроса","value":"развёрнутый ответ","confidence":0.85,"explanation":"обоснование"}

Тип 5 — Drag-and-drop:
{"action":"drag_and_drop","question_text":"текст вопроса","pairs":[{"source":"плашка","target":"цель"}],"confidence":0.8,"explanation":"обоснование"}

Тип 6 — Сохранить ответ:
{"action":"click_save","explanation":"нажать СОХРАНИТЬ ОТВЕТ"}

Тип 7 — Модальное окно:
{"action":"click_modal_confirm","button_text":"ПРИСТУПИТЬ К ВЫПОЛНЕНИЮ","explanation":"закрыть модал"}

Тип 8 — Тест завершён:
{"action":"test_complete","explanation":"все вопросы отвечены"}

Тип 9 — Ожидание загрузки:
{"action":"wait","explanation":"ожидание загрузки вопроса","confidence":0.99}

Тип 10 — Сопоставление (соедини текст слева с картинкой/блоком справа):
{"action":"connect_match","pairs":[{"left_id":"a_1","right_id":"b_2"},{"left_id":"a_2","right_id":"b_1"},{"left_id":"a_3","right_id":"b_3"}],"confidence":0.8,"explanation":"обоснование"}
ВАЖНО для connect_match: left_id и right_id бери ТОЧНО как в данных (a_1, b_2 ...). Покрой ВСЕ левые блоки ровно по одной паре. Если справа картинки — смотри на скриншот и сопоставляй по смыслу. Если не уверен — ставь confidence ниже 0.5.

ПРАВИЛА:
- Возвращай ТОЛЬКО валидный JSON, без ```json``` и без лишнего текста
- answer_text — ТОЧНАЯ копия текста варианта из списка
- Если уже выбран ответ [x] — возвращай click_save
- Если СТАТУС ПОЛЕЙ: все заполнены — возвращай click_save (не fill!)
- Если КНОПКА СОХРАНИТЬ: видна — возвращай click_save
- Если вопрос не отображён (СОСТОЯНИЕ: страница переходит) — верни action:wait
- НЕ ищи кнопку "ПРИСТУПИТЬ" если тест уже идёт и есть вопрос на экране
- НИКОГДА не используй next_question
- Для fill: placeholder = имя поля из "ПОЛЯ ВВОДА" (левая часть до "="), value = твой ответ
- **КРИТИЧЕСКИ ВАЖНО**: всегда указывай answer_index (номер варианта по порядку, начиная с 1). Это САМЫЙ надёжный способ кликнуть правильный ответ. answer_text — вспомогательный, для отладки и визуальной проверки.

КРИТИЧЕСКИ ВАЖНО ДЛЯ ТЕКСТОВЫХ ОТВЕТОВ (fill / fill_textarea):
- СТРОГО ОДИН вариант в поле value — ЗАПРЕЩЕНО писать "X или Y", "X or Y", "X / Y"
- Выбери ОДИН наилучший вариант и напиши только его
- Если ответ является законченным предложением — первое слово с ЗАГЛАВНОЙ буквы, в конце ТОЧКА или ?
- Если ответ — одно слово или словоформа — строчными буквами (если не имя собственное)
"""


class GUISelectStub:
    """Stub для элемента, найденного через JS querySelector."""

    def __init__(self, identifier):
        self._id = identifier

    async def click(self):
        """Stub: клик по элементу."""
        pass


class GUIPanelStub:
    """
    Stub-обёртка над BrowserControl.
    evaluate() → cid → queue → GUI thread → callback → polling get_result()
    """

    def __init__(self, ctrl):
        self._ctrl = ctrl

    async def evaluate(self, script: str) -> str:
        """Async evaluate: queue → GUI thread → polling."""
        cid = self._ctrl.evaluate_async(script)

        for _ in range(200):
            res = self._ctrl.get_result(cid)
            if res is not None:
                return res
            await asyncio.sleep(0.05)

        return ""

    async def send(self, cdp_msg):
        """Stub: эмулируем основные CDP-команды через JS."""
        try:
            cls_name = cdp_msg.__class__.__name__

            if 'InsertText' in cls_name:
                text = getattr(cdp_msg, 'text', '')
                if text:
                    safe = text.replace("\\", "\\\\").replace("'", "\\'")
                    await self.evaluate(f"""
                    (() => {{
                        const el = document.activeElement;
                        if (el) {{
                            const d = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
                            if (d && d.set) d.set.call(el, '{safe}');
                            else el.value = '{safe}';
                            el.dispatchEvent(new InputEvent('input', {{bubbles:true, inputType:'insertText', data:'{safe}'}}));
                            el.dispatchEvent(new Event('change', {{bubbles:true}}));
                        }}
                    }})()
                    """)

            elif hasattr(cdp_msg, 'type_'):
                t = cdp_msg.type_
                if t in ('keyDown', 'keyUp'):
                    key = getattr(cdp_msg, 'key', '')
                    if key == 'Tab':
                        await self.evaluate("(function(){ var el=document.activeElement; if(el && el.blur) el.blur(); })()")
                    elif key == 'Enter' or key == 'Return':
                        await self.evaluate("(function(){ var el=document.activeElement; if(el) el.blur(); })()")

            elif hasattr(cdp_msg, 'button'):
                x = getattr(cdp_msg, 'x', 0)
                y = getattr(cdp_msg, 'y', 0)
                await self.evaluate(f"""
                (() => {{
                    var el = document.elementFromPoint({x}, {y});
                    if (el) {{ el.click(); el.dispatchEvent(new Event('click',{{bubbles:true}})); }}
                }})()
                """)
        except Exception:
            pass

    @property
    def url(self) -> str:
        try:
            return self._ctrl.tab_url() or ""
        except Exception:
            return ""

    async def select(self, selector: str, timeout: float = 3.0):
        """Stub: ищем элемент по selector через JS."""
        script = f"""
        (() => {{
            const el = document.querySelector('{selector}');
            if (el) return 'FOUND:' + el.tagName;
            return 'NOT_FOUND';
        }})()
        """
        res = await self.evaluate(script)
        if res and res.startswith("FOUND:"):
            return GUISelectStub(res)
        raise Exception(f"Element not found: {selector}")

    async def find(self, text: str, best_match: bool = True, timeout: float = 3.0):
        """Stub: ищем элемент с текстом."""
        return GUISelectStub("FOUND:A")

    async def close(self):
        """Stub: ничего не делает."""
        pass

    async def save_screenshot(self, path: str):
        """Stub: скриншот через QPixmap — пропускаем."""
        self._log(f"[Skip] screenshot: {path}")


def _get_active_api_key() -> str:
    """Возвращает текущий API-ключ из license_manager."""
    try:
        from license_mgr import license_manager as _lm
        key = _lm.api_key
        if key:
            return key
    except Exception:
        pass
    return ""

def _get_active_model() -> str:
    """Возвращает текущую выбранную модель из license_manager или config."""
    try:
        from license_mgr import license_manager as _lm
        return _lm.current_model
    except Exception:
        from config import AI_MODEL
        return AI_MODEL


class TestAgent:
    """Главный класс AI-агента (Nodriver Edition v3)."""

    def __init__(
        self,
        browser_ws_url: Optional[str] = None,
        user_data_dir: Optional[str] = None,
        browser_executable: Optional[str] = None,
        use_ollama: bool = False,
        log_cb: Optional[Callable[[str], None]] = None,
        status_cb: Optional[Callable[[str], None]] = None,
        task_description: str = "",
        subject: str = "",
        theme: str = "",
        # ── Новые параметры для автоматизации ──────────────────────────
        login: str = "",
        password: str = "",
        tests_cb: Optional[Callable[[List[Dict]], None]] = None,
        get_selected_test: Optional[Callable[[], Optional[Dict]]] = None,
        agent_signals = None,
        # ── Режим встроенного браузера ─────────────────────────────
        use_gui_browser: bool = False,
        browser_control = None,
    ):
        self.browser_ws_url      = browser_ws_url
        self.user_data_dir       = user_data_dir
        self.browser_executable  = browser_executable
        self.use_ollama          = use_ollama
        self.log_cb              = log_cb or (lambda msg: logger.info(msg))
        self.status_cb           = status_cb or (lambda msg: None)
        self._agent_signals      = agent_signals  # PyQt6 AgentSignals thread-safe
        self.task_description    = task_description
        self.subject             = subject
        self.theme               = theme
        self.login               = login
        self.password            = password
        self.tests_cb            = tests_cb
        self.get_selected_test   = get_selected_test
        self.use_gui_browser     = use_gui_browser
        self.browser_control     = browser_control
        self._selected_test_name = ""   # заполняется после выбора теста
        self._selected_test_id   = ""
        self._manual_test_mode   = False  # пользователь сам открывает тест

        self._stop_flag     = False
        self._pause_flag    = False
        self._browser       = None
        self._tab           = None
        self._consecutive_timeouts = 0  # для rate limiting
        self._loop          = None
        self._main_task     = None
        self._is_matching   = False  # текущий вопрос — сопоставление (картинки)
        self._matching_nodes = {}    # {"left":[{id,text}], "right":[{id}]}

    def start(self):
        """Запускает агента в новом asyncio event loop (неблокирующий).

        Использует run_until_complete вместо run_forever — когда _run_loop
        завершается, цикл останавливается и поток выходит чисто.
        """
        self._stop_flag = False
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._main_task = self._loop.create_task(self._run_loop())
        try:
            self._loop.run_until_complete(self._main_task)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.exception("Ошибка в _run_loop: %s", exc)
        finally:
            # Гарантированно закрываем браузер при ЛЮБОМ выходе из _run_loop
            # (нормальный возврат, return по ошибке, отмена task через stop()).
            try:
                self._loop.run_until_complete(self._cleanup_browser())
            except Exception as exc:
                logger.warning("Ошибка при закрытии браузера: %s", exc)
            try:
                self._loop.run_until_complete(self._loop.shutdown_asyncgens())
            except Exception:
                pass
            self._loop.close()
            self._log("👋 Браузер закрыт, агент завершён.")

    def stop(self):
        """Останавливает агента и закрывает браузер (вызывается из GUI-потока)."""
        self._stop_flag = True
        self._pause_flag = False  # снимаем паузу чтобы цикл мог завершиться
        # Прерываем любой долгий await (AI, sleep, …) — событийный цикл
        # завершится и поток выйдет из run_until_complete.
        loop = getattr(self, "_loop", None)
        task = getattr(self, "_main_task", None)
        if loop is not None and task is not None:
            try:
                if not loop.is_closed():
                    loop.call_soon_threadsafe(task.cancel)
            except Exception:
                pass

    def pause(self):
        self._pause_flag = True
        logger.info("⏸ Агент на паузе")

    def resume(self):
        self._pause_flag = False
        logger.info("▶ Агент продолжает работу")
        self._log("▶ Агент продолжает работу")

    async def _run_loop(self):
        """Главный async цикл."""
        self._log("🚀 Агент запускается...")
        self._status("Подключение к браузеру...")

        try:
            await self._connect_browser()
        except Exception as exc:
            self._log(f"❌ Не удалось подключиться к браузеру: {exc}")
            logger.exception("Ошибка подключения")
            return

        # ── Автоматическая авторизация ─────────────────────────────────
        if self.login and self.password:
            try:
                await self._perform_login()
            except Exception as exc:
                self._log(f"❌ Авторизация не удалась: {exc}")
                logger.exception("Ошибка авторизации")
                return
        else:
            self._log("ℹ️ Логин/пароль не заданы — пропускаю автовход")

        # ── Ожидание страницы тестов ───────────────────────────────────
        try:
            await self._wait_for_tests_page(TESTS_LOAD_TIMEOUT)
        except Exception as exc:
            self._log(f"❌ Не удалось дождаться страницы тестов: {exc}")
            return

        # ── Парсинг доступных тестов ────────────────────────────────────
        tests = []
        try:
            tests = await self._parse_available_tests()
            if tests:
                self._log(f"📋 Найдено {len(tests)} тестов:")
                for t in tests:
                    self._log(f"   • {t.get('name', '?')} — {t.get('subject', '')} "
                              f"({t.get('time_limit', 'без лимита')}, "
                              f"{t.get('questions', '?')} вопросов)")
                if self.tests_cb:
                    self.tests_cb(tests)
            else:
                self._log("⚠️ Тесты не найдены на странице")
        except Exception as exc:
            self._log(f"⚠️ Ошибка парсинга тестов: {exc}")

        # ── Тесты не найдены: даём пользователю 15с открыть тест самому ───
        if not tests:
            await self._manual_open_countdown(15)
            self._manual_test_mode = True
            # Пропускаем диалог выбора — сразу идём решать открытый тест
        # ── Ожидание выбора теста пользователем ─────────────────────────
        elif self.get_selected_test:
            self._log("⏳ Ожидание выбора теста...")
            self._status("Выберите тест...")
            try:
                await self._wait_for_test_selection()
            except Exception as exc:
                self._log(f"❌ Ожидание выбора теста прервано: {exc}")
                return

        if self.get_selected_test or self._manual_test_mode:

            if getattr(self, "_manual_test_mode", False):
                # Ручной режим: пользователь сам откроет тест в браузере.
                # ИИ продолжает с тем тестом, который сейчас на экране.
                self._log("👤 Ручной режим: открой нужный тест сам — ИИ приступит.")
                self._status("Открой тест сам — ИИ ждёт...")
            else:
                test_name = self._selected_test_name
                self._log(f"🎯 Выбран тест: {test_name}")

                # Также сохраняем ID теста для точного клика по tr#test{ID}
                sel = self.get_selected_test()
                if sel and sel.get("id"):
                    self._selected_test_id = sel["id"]
                    self._log(f"   🔢 ID теста: {self._selected_test_id}")

                # ── Открытие выбранного теста ───────────────────────────────
                try:
                    await self._open_selected_test(test_name)
                except Exception as exc:
                    self._log(f"❌ Не удалось открыть тест: {exc}")
                    return

                # ── Нажатие "ПРИСТУПИТЬ К ВЫПОЛНЕНИЮ" ─────────────────────
                try:
                    await self._click_start_test_button()
                except Exception as exc:
                    self._log(f"❌ Не удалось нажать кнопку старта: {exc}")
                    return
        else:
            self._log("⚠️ tests_cb не передан — пропускаю выбор теста")

        self._log("✅ Начинаю прохождение теста...")

        # ── Основной цикл прохождения теста (существующий код) ────────
        session_stats.reset()
        step = 0
        _stall_action = None
        _stall_count  = 0
        _STALL_LIMIT  = 3

        if await self._is_test_in_progress():
            self._log("ℹ️ Тест уже начат — сразу приступаю к вопросам")
        else:
            self._log("ℹ️ Тест ещё не начат — ищу кнопку старта")

        while not self._stop_flag:
            # ── Пауза — ждём без закрытия браузера ───────────────────────────
            while self._pause_flag and not self._stop_flag:
                await asyncio.sleep(0.5)
            if self._stop_flag:
                break

            step += 1
            self._log(f"{'─'*22}")
            self._log(f"📸 Шаг {step}: анализируем экран...")
            self._status(f"Шаг {step} — анализ")

            try:
                # ── Авто-стоп: детектируем страницу результатов ──────
                try:
                    _res_detected = await self._tab.evaluate("""
                    (() => {
                        const body = document.body ? document.body.innerText : '';
                        return body.includes('РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ') ||
                               body.includes('СТАТИСТИКА ОТВЕТОВ') ||
                               body.includes('ЗАКРЫТЬ РЕЗУЛЬТАТЫ') ||
                               document.querySelector('.test-results, #results, .results-page') !== null;
                    })()
                    """)
                    if _res_detected:
                        self._log("🏁 Обнаружена страница результатов — тест завершён!")
                        self._status("Тест завершён ✅")
                        # Парсим статистику ДО закрытия браузера
                        await self._emit_test_results()
                        self._play_sound("test_done")
                        # Даём звуку доиграть до закрытия браузера/завершения
                        await asyncio.sleep(3.0)
                        break
                except Exception:
                    pass

                screenshot_bytes, page_html = await self._capture_state()

                # ── Пропуск вопросов с картинками (если включено в настройках) ──
                if self._is_matching and self._should_skip_images():
                    self._log("🖼️ Вопрос с картинками — пропускаю (включено в настройках).")
                    skipped = await self._skip_current_question()
                    if skipped:
                        await async_random_delay(1.0, 2.0)
                        continue
                    # Если пропустить не вышло — решаем как обычно (vision)
                    self._log("   ⚠️ Не удалось пропустить — решаю вопрос.")

                self._log("🤖 Отправляем в AI...")

                # ── Rate limiting: backoff при таймаутах ──────────────────────
                if self._consecutive_timeouts >= 3:
                    backoff = min(self._consecutive_timeouts * 5.0, 30.0)
                    self._log(f"⚠️ Rate limit: пауза {backoff:.0f}с после 3+ таймаутов")
                    for _ in range(int(backoff)):
                        if self._stop_flag:
                            break
                        while self._pause_flag:
                            await asyncio.sleep(0.5)
                        await asyncio.sleep(1.0)

                try:
                    ai_response = await asyncio.wait_for(
                        self._ask_ai(screenshot_bytes, page_html), timeout=AI_TIMEOUT
                    )
                    # Успех — сбрасываем счётчик
                    self._consecutive_timeouts = 0
                except asyncio.TimeoutError:
                    self._consecutive_timeouts += 1
                    self._log(f"⚠️ AI запрос завис (>AI_TIMEOUTс), пропускаю шаг "
                             f"(таймауты подряд: {self._consecutive_timeouts})")
                    # Звук при двух (и более) таймаутах/ошибках ИИ подряд
                    if self._consecutive_timeouts >= 2:
                        self._play_sound("ai_error")
                    await async_random_delay(3.0, 6.0)
                    continue

                if not ai_response:
                    self._consecutive_timeouts += 1
                    self._log("⚠️ AI не вернул ответ, ожидаем...")
                    if self._consecutive_timeouts >= 2:
                        self._play_sound("ai_error")
                    await async_random_delay(2.0, 4.0)
                    continue

                action = ai_response.get("action", "unknown")
                conf   = ai_response.get("confidence", 0)
                expl   = ai_response.get("explanation", "")

                self._log(f"🎯 Действие: [{action}]  уверенность: {conf:.0%}")
                if expl:
                    self._log(f"   ℹ️  {expl}")

                # ── Детектор зависания ─────────────────────────────────
                if action == _stall_action and float(conf) == 0.0:
                    _stall_count += 1
                    if _stall_count >= _STALL_LIMIT:
                        self._log(f"🔄 Зависание: «{action}» ×{_stall_count}. Ждём загрузку...")
                        _stall_count = 0
                        await self._wait_for_next_question(max_wait=20.0)
                        continue
                else:
                    _stall_action = action if float(conf) == 0.0 else None
                    _stall_count  = 1 if float(conf) == 0.0 else 0

                done = await self._execute_action(ai_response)
                if done:
                    self._log("🏁 Тест завершён!")
                    self._status("Тест завершён ✅")
                    await self._emit_test_results()
                    self._play_sound("test_done")
                    # Даём звуку доиграть до закрытия браузера/завершения
                    await asyncio.sleep(3.0)
                    break

                # Считаем вопросы только для реальных ответов (не wait/next_question)
                _answer_actions = {"click", "click_multiple", "fill",
                                   "fill_textarea", "drag_and_drop", "connect_match",
                                   "click_save"}
                if action in _answer_actions:
                    session_stats.questions_answered += 1
                session_stats.actions_total += 1
                self._log(f"📊 {session_stats.summary()}")
                await async_random_delay()

            except asyncio.CancelledError:
                break
            except Exception as exc:
                session_stats.errors += 1
                self._log(f"⚠️ Ошибка на шаге {step}: {exc}")
                logger.exception("Ошибка на шаге %d", step)
                self._play_sound("error")
                await async_random_delay(2.0, 5.0)

        self._log("👋 Агент остановлен.")
        self._status("Остановлен")

    async def _cleanup_browser(self):
        """Закрывает браузер, запущенный nodriver'ом.

        Вызывается из start() в finally — гарантирует, что Chrome не останется
        висеть после остановки агента или закрытия приложения.
        Не трогает внешний браузер (browser_ws_url) и GUI-режим — там процессом
        управляет не агент.
        """
        browser = getattr(self, "_browser", None)
        # Внешний/встроенный браузер мы не запускали — не закрываем его процесс.
        if browser is None or self.use_gui_browser or self.browser_ws_url:
            self._tab = None
            self._browser = None
            return
        try:
            # Browser.stop() — синхронный: рвёт соединение и убивает процесс Chrome.
            browser.stop()
            self._log("   🧹 Браузер nodriver остановлен")
        except Exception as exc:
            logger.warning("Не удалось остановить браузер штатно: %s", exc)
            # Грубый fallback: убиваем процесс напрямую.
            try:
                proc = getattr(browser, "_process", None)
                if proc is not None:
                    proc.kill()
            except Exception:
                pass
        finally:
            self._tab = None
            self._browser = None
        # Даём процессу время умереть, чтобы освободить профиль (user_data_dir).
        try:
            await asyncio.sleep(0.5)
        except Exception:
            pass

    async def _connect_browser(self):
        """Подключается к уже запущенному браузеру (CDP) или запускает новый через nodriver."""

        if self.use_gui_browser:
            # ── Режим GUI-браузера: используем BrowserPanel напрямую ─────
            self._log("🌐 Используем встроенный браузер приложения.")
            self._browser = None
            self._tab = GUIPanelStub(self.browser_control)
            await asyncio.sleep(0.5)
            return

        if self.browser_ws_url:
            # ── Режим: браузер уже открыт GUI — подключаемся по CDP ──────────
            import urllib.request
            # Извлекаем host:port из ws-URL  (ws://127.0.0.1:9222 или ws://127.0.0.1:9222/...)
            ws = self.browser_ws_url.rstrip("/")
            # host:port без схемы
            host_port = ws.replace("ws://", "").replace("wss://", "").split("/")[0]
            host, port_str = (host_port.split(":") + ["9222"])[:2]
            port = int(port_str)

            self._log(f"🔌 Подключение к браузеру на {host}:{port}...")
            # nodriver умеет подключаться к уже запущенному Chrome
            config = uc.Config(
                host=host,
                port=port,
                headless=False,
                browser_args=[],
            )
            self._browser = await uc.Browser.create(config=config)
            # Ищем вкладку с нужным URL
            await asyncio.sleep(1.5)
            self._tab = await self._browser.get(TARGET_URL)
            await asyncio.sleep(2.0)
            self._log(f"📄 Вкладка: {TARGET_URL}")
        else:
            # ── Режим: запускаем браузер сами через nodriver ─────────────────
            self._log("🌐 Запуск браузера...")
            kwargs: dict = {
                "headless": False,
                "browser_args": [
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-popup-blocking",
                    "--start-maximized",
                    "--ignore-certificate-errors",
                    "--ignore-ssl-errors",
                    "--allow-insecure-localhost",
                    "--disable-web-security",
                ],
            }
            if self.browser_executable and os.path.exists(self.browser_executable):
                kwargs["browser_executable_path"] = self.browser_executable
                self._log(f"   Путь: {self.browser_executable}")
            if self.user_data_dir:
                kwargs["user_data_dir"] = self.user_data_dir
                self._log(f"   Профиль: {self.user_data_dir}")

            # Запуск браузера и навигация с общим таймаутом — чтобы зависший
            # старт Chrome не вешал приложение навсегда.
            try:
                self._browser = await asyncio.wait_for(uc.start(**kwargs), timeout=60.0)
                self._tab = await asyncio.wait_for(
                    self._browser.get(TARGET_URL), timeout=30.0
                )
            except asyncio.TimeoutError:
                raise RuntimeError(
                    "Браузер не запустился за 60с. Возможно, остался висеть "
                    "процесс Chrome с тем же профилем (user_data_dir) — закройте "
                    "все окна Chrome и попробуйте снова."
                )
            await asyncio.sleep(3.0)
            self._log(f"📄 Открыт URL: {self._tab.url}")

        await self._ensure_correct_tab()

    async def _ensure_correct_tab(self):
        """
        Проверяет что _tab указывает на реальную страницу теста, а не на SSL-ошибку.
        Если текущая вкладка — страница ошибки, ищет правильную среди всех вкладок
        и переключается на неё (или обходит SSL через CDP).
        """
        # Пробуем обойти SSL-предупреждение через CDP (нажать "Продолжить")
        try:
            await self._tab.evaluate("""
            (() => {
                // Кнопка "Продолжить на сайт (небезопасно)" на странице SSL-ошибки Chrome
                const btn = document.getElementById('proceed-link') ||
                            document.getElementById('details-button');
                if (btn) { btn.click(); return true; }
                return false;
            })()
            """)
            await asyncio.sleep(1.5)
        except Exception:
            pass

        # Проверяем текущий заголовок
        try:
            title = await asyncio.wait_for(
                self._tab.evaluate("document.title"), timeout=5.0
            )
            if title and ("ошибка" not in str(title).lower() and "error" not in str(title).lower()):
                self._log(f"   ✅ Вкладка корректна: «{title}»")
                return
        except Exception:
            pass

        # Ищем правильную вкладку среди всех открытых
        self._log("   🔍 Ищем правильную вкладку (SSL-ошибка на текущей)...")
        try:
            targets = self._browser.targets
            for target in targets:
                url = getattr(target, 'url', '') or ''
                title = getattr(target, 'title', '') or ''
                tab_type = getattr(target, 'type_', '') or ''
                if (TARGET_URL.split('/')[2] in url and
                        tab_type == 'page' and
                        'ошибка' not in title.lower() and
                        'error' not in title.lower()):
                    self._log(f"   ✅ Найдена нужная вкладка: «{title}» — переключаюсь")
                    self._tab = await self._browser.get(TARGET_URL, new_tab=False)
                    await asyncio.sleep(2.0)
                    return
        except Exception as e:
            self._log(f"   ⚠️ Поиск вкладок: {e}")

        # Последний резерв — открыть новую вкладку
        self._log("   🆕 Открываю новую вкладку для обхода SSL...")
        try:
            self._tab = await self._browser.get(TARGET_URL, new_tab=True)
            await asyncio.sleep(3.0)
            # Снова пробуем нажать "Продолжить"
            try:
                await self._tab.evaluate("""
                (() => {
                    const btn = document.getElementById('proceed-link') ||
                                document.getElementById('details-button');
                    if (btn) { btn.click(); return true; }
                    // Иногда нужно сначала показать детали
                    const det = document.getElementById('details-button');
                    if (det) { det.click(); }
                    setTimeout(() => {
                        const proc = document.getElementById('proceed-link');
                        if (proc) proc.click();
                    }, 500);
                    return false;
                })()
                """)
                await asyncio.sleep(2.0)
            except Exception:
                pass
            self._log(f"   📄 Новая вкладка: {self._tab.url}")
        except Exception as e:
            self._log(f"   ⚠️ Не удалось открыть новую вкладку: {e}")

    # ── Автоматизация: авторизация ───────────────────────────────────────────

    async def _clear_browser_session(self):
        """Очищает cookies и localStorage перед авторизацией."""
        self._log("🧹 Очищаю сессию браузера...")
        try:
            await self._tab.evaluate("""
            (async () => {
                // Очищаем cookies через document cookie API
                document.cookie.split(";").forEach(c => {
                    const eqPos = c.indexOf("=");
                    const name = eqPos > -1 ? c.substr(0, eqPos).trim() : c.trim();
                    document.cookie = name + "=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/";
                });
                // Очищаем localStorage / sessionStorage
                try { localStorage.clear(); } catch(e) {}
                try { sessionStorage.clear(); } catch(e) {}
                return true;
            })()
            """)
            self._log("   ✅ Сессия очищена")
        except Exception as exc:
            self._log(f"   ⚠️ Ошибка очистки сессии: {exc}")

    async def _wait_for_login_page(self, timeout: float = AUTH_TIMEOUT) -> bool:
        """Ждёт появления формы авторизации.

        Страница авторизации и страница тестов — один URL (/test/).
        На странице авторизации есть div#logindiv и input#userpassword.
        """
        self._log("🔍 Ищу страницу авторизации...")
        deadline = time.monotonic() + timeout
        iter_count = 0
        while time.monotonic() < deadline and not self._stop_flag:
            iter_count += 1
            try:
                result = await asyncio.wait_for(self._tab.evaluate("""
                (() => {
                    const hasLoginForm = document.getElementById('logindiv') !== null;
                    const hasPasswordField = document.getElementById('userpassword') !== null;
                    const hasLoginInput = document.querySelector('input[ulg="uname"]') !== null;
                    return hasLoginForm || hasPasswordField || hasLoginInput;
                })()
                """), timeout=5.0)
                if result:
                    self._log("   ✅ Страница авторизации найдена")
                    return True
            except asyncio.TimeoutError:
                if iter_count == 1:
                    self._log("   ⚠️ evaluate() зависло (>5с) — пропускаю")
            except Exception as exc:
                if iter_count <= 2:
                    self._log(f"   ⚠️ evaluate error: {type(exc).__name__}: {exc}")
            await asyncio.sleep(0.5)
        self._log(f"   ⚠️ Страница авторизации не найдена за {timeout:.0f}с")
        return False

    async def _fill_credential_field(self, field_type: str, value: str) -> bool:
        """Заполняет поле логина или пароля.

        field_type: 'login' или 'password'
        Селекторы точные для uup.tigt.site:
          - login:   input[ulg="uname"]
          - password: input#userpassword
        """
        safe_val = value.replace("\\", "\\\\").replace("'", "\\'")

        if field_type == "password":
            selector = 'input#userpassword'
        else:
            selector = 'input[ulg="uname"]'

        # ── Стратегия 1: nodriver send_keys ────────────────────────────────
        try:
            inp = await self._tab.select(selector, timeout=3.0)
            if inp:
                await inp.click()
                await asyncio.sleep(0.2)
                await inp.clear()
                await inp.send_keys(value)
                self._log(f"   ✅ Заполнено {field_type} через send_keys")
                return True
        except Exception as e1:
            self._log(f"   ⚠️ send_keys ({selector}): {e1}")

        # ── Стратегия 2: JS — очищаем и заполняем ─────────────────────────
        js = f"""
        (() => {{
            const inp = document.querySelector('{selector}');
            if (!inp) return {{ok: false, reason: 'not_found'}};

            // Очищаем предзаполненное значение (например login='31958')
            inp.focus();
            inp.select();
            try {{
                // Множественные Backspace/Delete для очистки
                for (let i = 0; i < 30; i++) {{
                    inp.dispatchEvent(new KeyboardEvent('keydown', {{key: 'Backspace', bubbles: true}}));
                    inp.dispatchEvent(new KeyboardEvent('keypress', {{key: 'Backspace', bubbles: true}}));
                    inp.dispatchEvent(new KeyboardEvent('keyup', {{key: 'Backspace', bubbles: true}}));
                }}
            }} catch(e) {{}}
            inp.value = '';

            // Устанавливаем новое значение
            try {{
                const setter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value').set;
                setter.call(inp, '{safe_val}');
            }} catch(e) {{
                inp.value = '{safe_val}';
            }}
            inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
            inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
            inp.dispatchEvent(new Event('blur', {{ bubbles: true }}));
            return {{ok: true, found: inp.id || inp.name || inp.placeholder, finalValue: inp.value}};
        }})()
        """
        try:
            result = await asyncio.wait_for(self._tab.evaluate(js), timeout=5.0)
            parsed = self._parse_js_result(result)
            ok = parsed.get("ok", False)
            found = parsed.get("found", "")
            self._log(f"   {'✅' if ok else '❌'} Заполнено {field_type}: {found}")
            return ok
        except Exception as exc:
            self._log(f"   ❌ Ошибка заполнения {field_type}: {exc}")
            return False

    async def _click_login_button(self) -> bool:
        """Кликает по кнопке 'Войти'.

        На uup.tigt.site кнопка — это <a class='t_btn_login' onclick='loginpost()'>
        """
        self._log("🔘 Ищу кнопку 'Войти'...")

        # ── Стратегия 1: nodriver click на <a class='t_btn_login'> ───────────
        try:
            btn = await self._tab.select('a.t_btn_login', timeout=3.0)
            if btn:
                await btn.click()
                self._log("   ✅ Кнопка 'Войти' нажата (nodriver)")
                return True
        except Exception as e1:
            self._log(f"   ⚠️ nodriver click: {e1}")

        # ── Стратегия 2: JS click ─────────────────────────────────────────
        js = """
        (() => {
            // Точный селектор: <a class='t_btn_login' onclick='loginpost()'>
            const btn = document.querySelector('a.t_btn_login');
            if (btn) {
                btn.scrollIntoView({block: 'center'});
                btn.click();
                return {ok: true, method: 't_btn_login'};
            }
            // Резервно: ссылка с onclick содержащим loginpost
            const allLinks = [...document.querySelectorAll('a[onclick*="loginpost"]')];
            if (allLinks.length > 0) {
                allLinks[0].scrollIntoView({block: 'center'});
                allLinks[0].click();
                return {ok: true, method: 'onclick_loginpost'};
            }
            return {ok: false, reason: 'button_not_found'};
        })()
        """
        try:
            result = await asyncio.wait_for(self._tab.evaluate(js), timeout=5.0)
            parsed = self._parse_js_result(result)
            ok = parsed.get("ok", False)
            self._log(f"   {'✅' if ok else '❌'} Кнопка 'Войти': {parsed.get('method', '')}")
            return ok
        except Exception as exc:
            self._log(f"   ❌ Ошибка клика: {exc}")
            return False

    async def _check_logged_in(self) -> bool:
        """Проверяет, авторизован ли пользователь (уже есть аккаунт в браузере).

        Возвращает True если авторизован (нужен выход).
        """
        try:
            result = await asyncio.wait_for(self._tab.evaluate("""
            (() => {
                const hasLoginForm = document.getElementById('logindiv') !== null;
                const userBlock = document.querySelector('.logintable');
                const logoutLink = document.querySelector('a[href*="logout"]');
                const usernameEl = document.querySelector('font[style*="font-weight: bold"]');
                return {
                    isLoggedIn: !hasLoginForm && (logoutLink !== null || userBlock !== null),
                    username: usernameEl ? usernameEl.innerText.trim() : '',
                    logoutHref: logoutLink ? logoutLink.href : ''
                };
            })()
            """), timeout=5.0)
            parsed = self._parse_js_result(result) if isinstance(result, dict) else {}
            return parsed.get("isLoggedIn", False)
        except Exception as exc:
            self._log(f"   ⚠️ Ошибка проверки статуса: {exc}")
            return False

    async def _logout(self):
        """Выходит из аккаунта через стабильную ссылку /?action=logout.

        Шаги:
        1) пробуем клик по ссылке выхода на странице,
        2) fallback — открываем URL /?action=logout напрямую,
        3) ждём появления формы логина.
        """
        self._log("🚪 Выхожу из аккаунта...")

        # 1. Пробуем клик по ссылке выхода, если она есть на странице
        try:
            await asyncio.wait_for(self._tab.evaluate("""
            (() => {
                const a = document.querySelector('a[href="action=logout"], a[href="?action=logout"], a[href*="action=logout"], a[href*="/logout"]');
                if (!a) return {ok:false, mode:'no_link'};
                a.scrollIntoView({block:'center'});
                a.click();
                return {ok:true, mode:'click'};
            })()
            """), timeout=5.0)
        except Exception as exc:
            self._log(f"   ⚠️ click logout: {exc}")

        # 2. Fallback: открываем URL выхода напрямую
        try:
            url = TARGET_URL.rstrip("/") + "/?action=logout"
            if getattr(self, "_browser", None) is not None:
                self._tab = await self._browser.get(url, new_tab=False)
            else:
                await self._tab.evaluate(f"window.location.href = '{url}';")
            self._log("   🔄 Logout URL открыт напрямую")
            await asyncio.sleep(1.5)
        except Exception as exc:
            self._log(f"   ⚠️ get(logout): {exc}")

        # 3. Дожидаемся формы логина
        if await self._wait_for_login_page(timeout=AUTH_TIMEOUT):
            self._log("   ✅ Форма логина загружена")
        else:
            self._log("   ⚠️ Форма логина не появилась — продолжаем")

    async def _perform_login(self):
        """Главный метод авторизации: проверка → выход → очистка → заполнение → вход."""
        self._log("🔐 Начинаю авторизацию...")
        self._status("Авторизация...")

        # ── Шаг 0: проверяем — возможно уже авторизован чужым аккаунтом ─────
        if await self._check_logged_in():
            self._log("   ℹ️ Браузер уже авторизован — выхожу из аккаунта")
            await self._logout()
            # _logout() уже вызывает _wait_for_login_page — просто пауза
            await asyncio.sleep(1.0)

        # Очистка cookies/localStorage — только если не было выхода
        if CLEAR_SESSION_ON_START and not await self._check_logged_in():
            await self._clear_browser_session()

        if not await self._wait_for_login_page():
            raise RuntimeError("Страница авторизации не найдена")

        await asyncio.sleep(0.3)

        if not await self._fill_credential_field("login", self.login):
            raise RuntimeError("Не удалось заполнить поле логина")
        await asyncio.sleep(0.5)

        if not await self._fill_credential_field("password", self.password):
            raise RuntimeError("Не удалось заполнить поле пароля")
        await asyncio.sleep(0.3)

        if not await self._click_login_button():
            raise RuntimeError("Не удалось нажать кнопку 'Войти'")

        self._log("   ⏳ Жду перехода на страницу тестов...")
        await asyncio.sleep(2.5)
        self._log("   ✅ Авторизация выполнена")

    async def _wait_for_tests_page(self, timeout: float = TESTS_LOAD_TIMEOUT) -> bool:
        """Ждёт загрузки страницы со списком тестов.

        Проверяет: table#testlisttable присутствует и содержит строки данных.
        Три стратегии поиска строк: tr.data → tr[id^="test"] → любые tr с td.
        """
        self._log("🔍 Ищу страницу тестов...")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and not self._stop_flag:
            try:
                parsed = await self._eval_json("""
                (() => {
                    const table = document.getElementById('testlisttable');
                    if (!table) return {ok: false, reason: 'no_table'};
                    const trData = table.querySelectorAll('tr.data').length;
                    const trId = table.querySelectorAll('tr[id^="test"]').length;
                    const allRows = table.querySelectorAll('tr').length;
                    const hasData = trData > 0 || trId > 0 || (allRows > 1 && table.querySelector('tr.data, tr[id^="test"], tbody tr:not(.head)') !== null);
                    return {
                        ok: true,
                        loaded: hasData,
                        rows: trData > 0 ? trData : trId > 0 ? trId : allRows - 1,
                        debug: {
                            trData: trData,
                            trId: trId,
                            total: allRows,
                            tableVisible: table.offsetParent !== null || table.querySelector('td') !== null
                        }
                    };
                })()
                """, timeout=5.0) or {}
                if parsed.get("ok") and parsed.get("loaded"):
                    debug = parsed.get("debug", {})
                    count = parsed.get("rows", 0)
                    self._log(f"   ✅ Страница тестов загружена "
                              f"(tr.data={debug.get('trData', 0)}, "
                              f"tr[id^='test']={debug.get('trId', 0)}, "
                              f"всего={debug.get('total', 0)})")
                    return True
                else:
                    debug = parsed.get("debug", {})
                    if debug:
                        self._log(f"   ⏳ жду... (total={debug.get('total', 0)}, "
                                  f"trData={debug.get('trData', 0)}, "
                                  f"trId={debug.get('trId', 0)})")
            except asyncio.TimeoutError:
                pass
            except Exception as exc:
                self._log(f"   ⚠️ evaluate: {exc}")
            await asyncio.sleep(0.5)
        self._log(f"   ⚠️ Страница тестов не найдена за {timeout:.0f}с")
        return False

    async def _parse_available_tests(self) -> List[Dict]:
        """Парсит таблицу доступных тестов на странице.

        Раньше парсили outerHTML через RegExp — на больших таблицах это
        могло подвисать. Теперь вытаскиваем данные структурировано прямо
        из DOM через JS — быстро и стабильно.
        """
        self._log("📋 Парсинг списка тестов...")

        js = r"""
        (() => {
            const table = document.getElementById('testlisttable');
            if (!table) return { ok:false, reason:'no_table', tests:[] };
            const rows = [...table.querySelectorAll('tr[id^="test"]')];
            const tests = [];
            const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
            for (const row of rows) {
                const id = row.id || '';
                const tds = row.querySelectorAll('td');
                if (!id || tds.length < 6) continue;

                const td1raw = tds[1] ? tds[1].innerText : '';
                let name = '';
                let subject = '';
                let time_limit = '';
                for (const line of td1raw.split(/\n+/).map(clean)) {
                    const lc = line.toLowerCase();
                    if (!name && lc.startsWith('тест:')) name = clean(line.replace(/^тест:\s*/i, ''));
                    if (!subject && lc.startsWith('дисциплина:')) subject = clean(line.replace(/^дисциплина:\s*/i, ''));
                    if (!time_limit && lc.includes('время')) time_limit = line;
                }

                const status = clean(tds[2] ? tds[2].innerText : '');
                const qText = clean(tds[3] ? tds[3].innerText : '');
                const qMatch = qText.match(/\d+/);
                const questions = qMatch ? parseInt(qMatch[0], 10) : 0;
                const date = clean(tds[4] ? tds[4].innerText : '');
                const author = clean(tds[5] ? tds[5].innerText : '');

                if (name && name !== 'Без названия') {
                    tests.push({
                        id,
                        name,
                        subject,
                        time_limit: time_limit || 'Не ограничено',
                        status,
                        questions,
                        date,
                        author,
                        attempts: 0,
                    });
                }
            }
            return { ok:true, tests, count: tests.length };
        })()
        """

        try:
            parsed = await self._eval_json(js, timeout=10.0) or {}
            tests = parsed.get("tests") or []
            if tests:
                self._log(f"   ✅ Извлечено {len(tests)} тестов")
                for t in tests[:30]:
                    self._log(f"      • [{t.get('id')}] {t.get('name')} — {t.get('subject')} "
                              f"({t.get('questions')} вопр., {t.get('date')}, {t.get('author')})")
                if len(tests) > 30:
                    self._log(f"      … и ещё {len(tests) - 30} тестов")
                return tests

            self._log(f"   ⚠️ Тесты не найдены (reason={parsed.get('reason', '')})")
            return []
        except Exception as exc:
            self._log(f"   ⚠️ Парсинг тестов: {exc}")
            return []

    async def _manual_open_countdown(self, seconds: int = 15):
        """Тесты не найдены — даём пользователю время открыть тест самому.

        Отсчитывает `seconds` секунд (с логом и статусом), затем ИИ приступит
        к тому тесту, который пользователь открыл в браузере вручную.
        Прерывается, если нажат стоп.
        """
        self._log(f"🕒 Тесты не найдены автоматически. Открой нужный тест сам — "
                  f"ИИ приступит через {seconds}с.")
        for left in range(seconds, 0, -1):
            if self._stop_flag:
                return
            # Пауза не задерживает остановку
            while self._pause_flag and not self._stop_flag:
                await asyncio.sleep(0.3)
            self._status(f"Открой тест сам — ИИ приступит через {left}с")
            if left % 5 == 0 or left <= 3:
                self._log(f"   ⏳ {left}с...")
            await asyncio.sleep(1.0)
        self._log("▶️ Время вышло — приступаю к открытому тесту.")

    async def _wait_for_test_selection(self):
        """Ждёт выбора теста пользователем в GUI (опросом)."""
        self._log("⏳ Ожидание выбора теста пользователем...")
        deadline = time.monotonic() + 300.0   # 5 минут максимум
        while time.monotonic() < deadline and not self._stop_flag:
            if self.get_selected_test:
                selected = self.get_selected_test()
                if selected and selected.get("manual"):
                    # Пользователь выберет тест сам в браузере (или истёк
                    # таймаут авто-старта) — открытие теста пропускаем.
                    self._selected_test_name = ""
                    self._manual_test_mode = True
                    return
                if selected and selected.get("name"):
                    self._selected_test_name = selected["name"]
                    return
            await asyncio.sleep(0.5)
        raise RuntimeError("Таймаут ожидания выбора теста (5 мин)")

    async def _open_selected_test(self, test_name: str):
        """Открывает тест вызовом settestshow() напрямую.

        Использует onclick-функцию сайта: settestshow(NUMBER).
        Это стабильнее чем row.click() (не зависит от overlay/pointer-events).
        """
        self._log(f"🎯 Открываю тест: {test_name}")

        # Извлекаем номер теста из ID (например "test3001776045742" → 3001776045742)
        test_num = None
        if hasattr(self, '_selected_test_id') and self._selected_test_id:
            try:
                test_num = int(self._selected_test_id.replace("test", ""))
                self._log(f"   🔢 Номер теста: {test_num}")
            except Exception:
                self._log(f"   ⚠️ Не удалось извлечь номер из {self._selected_test_id}")

        # ── Стратегия 1: вызов settestshow(NUMBER) — самый надёжный ───────
        if test_num:
            js = f"""
            (() => {{
                if (typeof settestshow !== 'function') {{
                    return {{ok: false, reason: 'fn_missing'}};
                }}
                settestshow({test_num});
                return {{ok: true, num: {test_num}}};
            }})()
            """
            try:
                result = await asyncio.wait_for(self._tab.evaluate(js), timeout=5.0)
                parsed = self._parse_js_result(result)
                if parsed.get("ok"):
                    self._log(f"   ✅ settestshow({test_num}) вызван")
                    await asyncio.sleep(1.5)
                    return
                else:
                    self._log(f"   ⚠️ settestshow не найден: {parsed.get('reason', '')}")
            except Exception as exc:
                self._log(f"   ⚠️ Ошибка settestshow: {exc}")

        # ── Стратегия 2: eval onclick-атрибута ────────────────────────────
        if hasattr(self, '_selected_test_id') and self._selected_test_id:
            js = f"""
            (() => {{
                const row = document.getElementById('{self._selected_test_id}');
                if (!row) return {{ok: false, reason: 'row_not_found'}};
                const onclick = row.getAttribute('onclick') || '';
                if (onclick) {{ eval(onclick); return {{ok: true, onclick: onclick}}; }}
                return {{ok: false, reason: 'no_onclick'}};
            }})()
            """
            try:
                result = await asyncio.wait_for(self._tab.evaluate(js), timeout=5.0)
                parsed = self._parse_js_result(result)
                if parsed.get("ok"):
                    self._log(f"   ✅ eval: {parsed.get('onclick', '')}")
                    await asyncio.sleep(1.5)
                    return
            except Exception as exc:
                self._log(f"   ⚠️ eval onclick: {exc}")

        # ── Стратегия 3: row.click() как fallback ──────────────────────────
        safe_name = test_name.replace("\\", "\\\\").replace("'", "\\'")
        js = f"""
        (() => {{
            const rows = [...document.querySelectorAll('tr[id^="test"]')];
            for (const row of rows) {{
                const txt = (row.textContent || '').toLowerCase();
                if (txt.includes('{safe_name.toLowerCase()}')) {{
                    row.scrollIntoView({{block: 'center'}});
                    row.click();
                    return {{ok: true, method: 'row_click', id: row.id}};
                }}
            }}
            return {{ok: false, reason: 'not_found'}};
        }})()
        """
        try:
            result = await asyncio.wait_for(self._tab.evaluate(js), timeout=5.0)
            parsed = self._parse_js_result(result)
            if parsed.get("ok"):
                self._log(f"   ✅ Открыто: {parsed.get('id', '')}")
                await asyncio.sleep(1.5)
            else:
                self._log(f"   ❌ Тест не найден")
        except Exception as exc:
            self._log(f"   ❌ Ошибка: {exc}")

    async def _click_start_test_button(self):
        """Ищет 'ПРИСТУПИТЬ К ВЫПОЛНЕНИЮ', затем отвечает 'Да' на модал 'Готовы?'."""
        self._log("▶️ Ищу кнопку 'ПРИСТУПИТЬ К ВЫПОЛНЕНИЮ'...")

        # ── Шаг 1: поиск и клик по кнопке старта ─────────────────────────
        clicked_start = False
        deadline = time.monotonic() + START_BUTTON_TIMEOUT
        while time.monotonic() < deadline and not self._stop_flag:
            try:
                result = await asyncio.wait_for(self._tab.evaluate("""
                (() => {
                    const allBtns = [...document.querySelectorAll('button, input[type="button"], a')];
                    for (const btn of allBtns) {
                        const txt = (btn.textContent || btn.value || '').toLowerCase();
                        if (txt.includes('приступить') && txt.includes('выполнению')) {
                            btn.scrollIntoView({block: 'center'});
                            btn.click();
                            return {ok: true, text: btn.textContent.trim()};
                        }
                    }
                    return {ok: false};
                })()
                """), timeout=5.0)
                parsed = self._parse_js_result(result)
                if parsed.get("ok"):
                    self._log(f"   ✅ Нажата: '{parsed.get('text', '')}'")
                    clicked_start = True
                    await asyncio.sleep(1.0)
                    break
            except Exception:
                pass
            await asyncio.sleep(0.5)

        if not clicked_start:
            self._log("   ⚠️ Кнопка 'ПРИСТУПИТЬ К ВЫПОЛНЕНИЮ' не найдена")

        # ── Шаг 2: модалка подтверждения (jQuery Alerts) ──────────────────
        # Кнопка «ДА» на сайте — это div#popup_yes, а не <button>.
        self._log("🔔 Ищу модал подтверждения (popup_yes)...")
        modal_deadline = time.monotonic() + 15.0
        while time.monotonic() < modal_deadline and not self._stop_flag:
            # Быстрый путь: jQuery Alerts confirm (popup_yes / popup_no)
            try:
                res = await asyncio.wait_for(self._tab.evaluate("""
                (() => {
                    const visible = (el) => !!el && (el.offsetParent !== null) && getComputedStyle(el).display !== 'none';
                    const container = document.getElementById('popup_container');
                    const overlay = document.getElementById('popup_overlay');
                    const yes = document.getElementById('popup_yes');
                    const modalVisible = visible(container) || visible(overlay);
                    if (!modalVisible) return {ok:false, reason:'no_modal'};
                    if (!yes) return {ok:false, reason:'no_popup_yes'};
                    yes.scrollIntoView({block:'center', inline:'center'});
                    yes.click();
                    yes.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view: window}));
                    const stillVisible = visible(document.getElementById('popup_container')) || visible(document.getElementById('popup_overlay'));
                    if (!stillVisible) return {ok:true, mode:'popup_yes'};
                    const r = yes.getBoundingClientRect();
                    return {ok:false, reason:'still_visible', x:r.left + r.width/2, y:r.top + r.height/2};
                })()
                """), timeout=5.0)
                parsed = self._parse_js_result(res) if isinstance(res, dict) else {}
                if parsed.get("ok"):
                    self._log("   ✅ Нажата 'ДА' (popup_yes)")
                    await asyncio.sleep(2.0)
                    return
                if parsed.get("reason") == "still_visible" and "x" in parsed and "y" in parsed:
                    # JS-клик не закрыл модал — добиваем физическим кликом через CDP
                    await self._cdp_mouse_click(int(parsed["x"]), int(parsed["y"]))
                    self._log("   ✅ Нажата 'ДА' (CDP click popup_yes)")
                    await asyncio.sleep(2.0)
                    return
            except Exception:
                pass

            # Сначала делаем скриншот для отладки
            try:
                await self._tab.save_screenshot("_modal_debug.png")
            except Exception:
                pass

            # ── Fallback: общий поиск кнопки "ДА" (на случай другого модала) ──
            try:
                result = await asyncio.wait_for(self._tab.evaluate("""
                (() => {
                    const normalize = s => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    const docText = normalize(document.body.innerText || '');

                    // Проверяем что модал вообще на странице
                    const hasModal = docText.includes('запускаете') ||
                                     docText.includes('готовы') ||
                                     docText.includes('приступить');

                    // Ищем ВСЕ кнопки "ДА" на странице
                    const allBtns = document.querySelectorAll('button, input[type="button"], a');
                    const candidates = [];
                    for (const btn of allBtns) {
                        const t = normalize(btn.innerText || btn.value || '');
                        if (t === 'да') {
                            candidates.push(btn);
                        }
                    }

                    if (candidates.length === 0) {
                        return {ok: false, reason: 'no_da_button', modal: hasModal, totalBtns: allBtns.length,
                                sampleText: docText.substring(0, 200)};
                    }

                    // Кликаем первую кнопку "ДА" если модал на странице
                    if (hasModal) {
                        candidates[0].scrollIntoView({block: 'center'});
                        candidates[0].click();
                        return {ok: true, text: 'ДА', count: candidates.length, modal: true};
                    }

                    // Модала нет — возможно уже закрыт
                    return {ok: false, reason: 'no_modal', count: candidates.length,
                            sampleText: docText.substring(0, 200)};
                })()
                """), timeout=5.0)
                parsed = self._parse_js_result(result) if isinstance(result, dict) else {}
                reason = parsed.get("reason", "")
                modal_text = parsed.get("sampleText", "")[:200]

                if parsed.get("ok"):
                    self._log(f"   ✅ Нажата 'ДА' (кандидатов: {parsed.get('count', 1)})")
                    await asyncio.sleep(2.0)
                    return
                else:
                    if reason == "no_modal":
                        self._log(f"   ℹ️ Модала нет на странице ({reason})")
                        return  # Модал уже закрыт — всё ок
                    elif reason == "no_da_button":
                        self._log(f"   ⏳ Модал: {'есть' if parsed.get('modal') else 'нет'}, "
                                  f"кнопок 'ДА' нет (всего {parsed.get('totalBtns', 0)})")
                        self._log(f"   📋 Текст страницы: {modal_text}")
                    else:
                        self._log(f"   ⏳ {reason}")
            except Exception as exc:
                self._log(f"   ⚠️ evaluate: {exc}")
            await asyncio.sleep(0.5)

        self._log("   ⚠️ Модал не нашли за 15с")

    async def _capture_state(self):
        """Скриншот + HTML страницы."""
        await asyncio.sleep(SCREENSHOT_WAIT)

        # Проверяем что не застряли на SSL-ошибке
        try:
            title = await asyncio.wait_for(
                self._tab.evaluate("document.title"), timeout=4.0
            )
            if title and ("ошибка" in str(title).lower() or "error" in str(title).lower()):
                self._log("   ⚠️ Обнаружена SSL-ошибка на вкладке — пытаемся обойти...")
                await self._ensure_correct_tab()
        except Exception:
            pass

        self._structured_state = None
        self._is_matching = False
        self._matching_nodes = {}

        # Пробуем закрыть модальное окно ошибки если оно появилось
        try:
            await self._tab.evaluate("""
            (() => {
                // Сайт ТИЖТ показывает ошибку в div.ui-dialog или через alert
                const closeBtn = document.querySelector(
                    '.ui-dialog button, .modal button, button.ui-button, ' +
                    'a[onclick*="close"], button[onclick*="close"], ' +
                    '#errorDialog button, .error-dialog button'
                );
                if (closeBtn) { closeBtn.click(); return; }
                // Кнопка ЗАКРЫТЬ по тексту
                const allBtns = document.querySelectorAll('button, input[type=button], a.button');
                for (const b of allBtns) {
                    const t = (b.textContent || b.value || '').trim().toLowerCase();
                    if (t === 'закрыть' || t === 'ok' || t === 'ок') { b.click(); return; }
                }
            })()
            """)
        except Exception:
            pass

        # Пробуем вытащить структурированные данные через JS
        try:
            raw = await asyncio.wait_for(self._tab.evaluate("""
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
                    answers.push('' + (i+1) + '. ' + (checked ? '[x]' : '[ ]') + ' (' + type + ') ' + text);
                }
                const fields = [];
                let filledCount = 0;
                const inps = document.querySelectorAll('input.inpas, input[type="text"]:not([type="hidden"])');
                for (let i = 0; i < inps.length; i++) {
                    const val = inps[i].value || '';
                    const ph = inps[i].placeholder || inps[i].name || ('field' + i);
                    fields.push(ph + '=' + val);
                    if (val.trim().length > 0) filledCount++;
                }
                const saveBtn = document.getElementById('SaveButton');
                const hasSave = saveBtn && saveBtn.offsetParent !== null;
                const fillStatus = fields.length > 0
                    ? (filledCount === fields.length ? 'ALL_FILLED' : filledCount > 0 ? 'PARTIAL' : 'EMPTY')
                    : '';

                // Извлекаем предмет и тему из левой панели
                let discipline = '';
                let theme = '';
                const leftText = document.body.innerText || '';
                const discMatch = leftText.match(/Дисциплин[а-я]*[:\\s]+([^\\n]+)/i);
                if (discMatch) discipline = discMatch[1].trim();
                const themeEl = document.querySelector('.question-theme, .qtheme, #qtheme');
                if (themeEl) theme = themeEl.innerText.trim();
                // Запасной вариант: «Тема:» в тексте страницы
                if (!theme) {
                    const tMatch = leftText.match(/Тема[:\\s]+([^\\n]+)/i);
                    if (tMatch) theme = tMatch[1].trim();
                }

                // ── Сопоставление (matching/connect): td.node (слева) + td.nodet (справа)
                let matching = '';
                const lefts = document.querySelectorAll('td.node');
                const rights = document.querySelectorAll('td.nodet');
                if (lefts.length > 0 && rights.length > 0) {
                    const L = [];
                    for (const td of lefts) {
                        L.push({ id: td.id || '', text: (td.innerText || '').replace(/\\s+/g,' ').trim() });
                    }
                    const R = [];
                    for (const td of rights) {
                        const img = td.querySelector('img');
                        R.push({ id: td.id || '', has_image: !!img,
                                 img_src: img ? (img.getAttribute('src') || '') : '' });
                    }
                    try { matching = JSON.stringify({ left: L, right: R }); } catch(e) { matching = ''; }
                }

                return questionText + '|||' + answers.join('\\n') + '|||' + fields.join('\\n') + '|||' + (hasSave ? 'SAVE_VISIBLE' : 'NO_SAVE') + '|||' + fillStatus + '|||' + discipline + '|||' + theme + '|||' + matching;
            })()
            """), timeout=5.0)
            if isinstance(raw, str) and '|||' in raw:
                parts = raw.split('|||')
                question     = parts[0].strip()
                answers_str  = parts[1].strip() if len(parts) > 1 else ''
                fields_str   = parts[2].strip() if len(parts) > 2 else ''
                save_visible = parts[3].strip() if len(parts) > 3 else ''
                fill_status  = parts[4].strip() if len(parts) > 4 else ''
                # Авто-определённые предмет и тема со страницы
                page_discipline = parts[5].strip() if len(parts) > 5 else ''
                page_theme      = parts[6].strip() if len(parts) > 6 else ''
                matching_str    = parts[7].strip() if len(parts) > 7 else ''
                # Обновляем self.subject/theme только если не заданы вручную
                if page_discipline and not self.subject:
                    self.subject = page_discipline
                if page_theme and not self.theme:
                    self.theme = page_theme

                # ── Сопоставление (matching): текст слева ↔ картинки справа ──
                if matching_str:
                    try:
                        m = json.loads(matching_str)
                        lefts = m.get("left") or []
                        rights = m.get("right") or []
                        if lefts and rights:
                            self._is_matching = True
                            self._matching_nodes = {"left": lefts, "right": rights}
                            mlines = [f"ВОПРОС: {question}"]
                            mlines.append("ТИП: СОПОСТАВЛЕНИЕ (соедини текст слева с картинкой справа).")
                            mlines.append("ЛЕВЫЕ БЛОКИ (текст):")
                            for L in lefts:
                                mlines.append(f"  {L.get('id','')}: {L.get('text','')}")
                            mlines.append("ПРАВЫЕ БЛОКИ (картинки-чертежи, смотри на скриншоте по порядку сверху вниз):")
                            for i, R in enumerate(rights, 1):
                                mlines.append(f"  {R.get('id','')}: картинка №{i}")
                            mlines.append("ВЕРНИ action:connect_match с парами {left_id,right_id}, "
                                          "покрыв ВСЕ левые блоки. Сопоставляй по смыслу чертежа.")
                            self._structured_state = '\n'.join(mlines)
                            self._log(f"   🔗 Вопрос-сопоставление: {len(lefts)} ↔ {len(rights)} (картинки)")
                    except Exception as _e:
                        logger.debug("matching parse: %s", _e)

                if question and not self._is_matching:
                    lines = [f"ВОПРОС: {question}"]
                    if answers_str:
                        lines.append("ВАРИАНТЫ ОТВЕТОВ:")
                        lines.append(answers_str)
                    if fields_str:
                        lines.append("ПОЛЯ ВВОДА:")
                        lines.append(fields_str)
                        if fill_status == 'ALL_FILLED':
                            lines.append("СТАТУС ПОЛЕЙ: все заполнены — верни action:click_save")
                        elif fill_status == 'PARTIAL':
                            lines.append("СТАТУС ПОЛЕЙ: заполнены частично")
                        else:
                            lines.append("СТАТУС ПОЛЕЙ: пусто — заполни (action:fill)")
                    if save_visible == 'SAVE_VISIBLE':
                        lines.append("КНОПКА СОХРАНИТЬ: видна — верни action:click_save")
                    self._structured_state = '\n'.join(lines)
                    self._log(f"   📋 Вопрос: {question[:60]}")
        except Exception as e:
            logger.debug("structured extract: %s", e)

        # Fallback: outerHTML
        page_html = ""
        if not self._structured_state:
            try:
                page_html = await asyncio.wait_for(
                    self._tab.evaluate("document.documentElement.outerHTML"),
                    timeout=10.0
                )
                if not isinstance(page_html, str):
                    page_html = ""
            except Exception:
                page_html = ""

        screenshot_bytes = await self._take_screenshot()
        return screenshot_bytes, page_html

    def _extract_relevant_html(self, page_html: str) -> str:
        """Извлекает релевантную часть HTML — вопрос и варианты ответов."""
        if hasattr(self, '_structured_state') and self._structured_state:
            result = self._structured_state
            self._structured_state = None
            return result
        return (
            "СОСТОЯНИЕ: страница переходит между вопросами или загружается.\n"
            "Вопрос ещё не отображён.\n"
            "Верни: {\"action\":\"wait\",\"explanation\":\"ожидание загрузки\",\"confidence\":0.99}"
        )

    async def _take_screenshot(self) -> bytes:
        """Скриншот через CDP или save_screenshot."""
        try:
            result = await self._tab.send(
                uc.cdp.page.capture_screenshot(format_="png", quality=80)
            )
            if result:
                img_bytes = base64.b64decode(result)
                return resize_screenshot(img_bytes, max_width=1280)
        except Exception as e:
            logger.warning("CDP screenshot: %s", e)

        try:
            path = "temp_ss.png"
            await self._tab.save_screenshot(path)
            with open(path, "rb") as f:
                data = f.read()
            os.remove(path)
            return resize_screenshot(data, max_width=1280)
        except Exception as e:
            logger.warning("save_screenshot: %s", e)

        return b""

    async def _ask_ai(self, screenshot_bytes: bytes, page_html: str, retry: int = 0) -> Optional[Dict]:
        """
        Запрос к AI.
        
        Стратегия:
        1. Если USE_VISION=True и есть скриншот → пробуем vision-модель
        2. Если vision даёт 400 → fallback на текстовую модель (только HTML)
        3. При любой ошибке → повторяем до ACTION_RETRIES раз
        """
        html_snippet = self._extract_relevant_html(page_html)

        # ── Контекстная подсказка для AI ─────────────────────────────────
        ctx_parts = []
        if self.subject:
            ctx_parts.append(f"Предмет: {self.subject}")
        if self.theme:
            ctx_parts.append(f"Тема: {self.theme}")
        if self.task_description:
            ctx_parts.append(f"Задача: {self.task_description}")
        if ctx_parts:
            ctx_parts.append(
                "ВАЖНО: Все текстовые ответы давай на языке предмета. "
                "Если предмет — иностранный язык, отвечай на том языке. "
                "Используй знание предмета и темы для точных ответов."
            )
        task_hint = ("\nКОНТЕКСТ ТЕСТА:\n" + "\n".join(ctx_parts)) if ctx_parts else ""

        # Ранняя проверка ключа — иначе httpx падает с 'Illegal header value Bearer '
        # на каждой попытке, и пользователь видит лишь «AI не вернул ответ».
        if not self.use_ollama and not _get_active_api_key():
            self._log("   ❌ API-ключ RouterAI пуст — проверьте активацию лицензии "
                      "(не удалось расшифровать ключ).")
            return None

        try:
            if self.use_ollama:
                return await self._call_ollama(screenshot_bytes, html_snippet, task_hint)
            else:
                # Vision принудительно для вопросов-сопоставлений с картинками —
                # без изображения такой вопрос решить нельзя (даже при USE_VISION=False).
                want_vision = (USE_VISION or self._is_matching) and screenshot_bytes
                if want_vision:
                    result = await self._call_routerai_vision(screenshot_bytes, html_snippet, task_hint)
                    if result is not None:
                        return result
                    # Vision не сработал — пробуем текстовый (для matching сработает fallback «по порядку»)
                    self._log("   ⚠️ Vision-модель недоступна, пробуем текстовый режим...")

                # Текстовый fallback (только HTML)
                return await self._call_routerai_text(html_snippet, task_hint)

        except Exception as exc:
            logger.warning("AI ошибка (попытка %d): %s", retry + 1, exc)
            if retry < ACTION_RETRIES:
                await asyncio.sleep(2.0)
                return await self._ask_ai(screenshot_bytes, page_html, retry + 1)
            return None

    def _parse_ai_raw(self, raw: str, finish: str, source: str) -> Optional[Dict]:
        """Парсит сырой текст ответа модели в JSON, диагностируя обрезку.

        finish — finish_reason от API ("stop", "length", ...).
        source — "Vision" / "Text" для логов.
        """
        # Модель упёрлась в лимит токенов — ответ почти наверняка обрезан
        if finish == "length":
            self._log(f"   ✂️ {source}: ответ обрезан по лимиту токенов "
                      "(finish_reason=length). Пробую восстановить JSON...")

        result = extract_json_from_text(raw)
        if result is not None:
            return result

        preview = (raw or "").strip().replace("\n", " ")[:300]
        self._log(f"   ❌ {source}: ответ ИИ не распознан как JSON. Сырой ответ: «{preview}»")
        if finish == "length":
            self._log("   💡 Похоже на обрезку — модель пишет слишком длинно. "
                      "answer_index важнее answer_text.")
        return None

    async def _call_routerai_vision(self, screenshot_bytes: bytes, html_snippet: str, task_hint: str) -> Optional[Dict]:
        """
        Вызов RouterAI с Vision (изображение + текст).
        Возвращает None если модель не поддерживает vision (400 ошибка).
        """
        import httpx

        b64 = image_to_base64(screenshot_bytes)

        text_part = f"Данные со страницы теста:\n{html_snippet}" if html_snippet else "Анализируй скриншот теста."
        if getattr(self, "_is_matching", False):
            text_part += (
                "\n\nЭТО ВОПРОС-СОПОСТАВЛЕНИЕ С КАРТИНКАМИ. На скриншоте слева — текстовые "
                "блоки, справа — чертежи (картинки) по порядку сверху вниз. Сопоставь КАЖДЫЙ "
                "левый блок с правильным чертежом по смыслу. Верни action:connect_match с "
                "парами {left_id,right_id}, используя id ровно как в данных (a_1, b_2 и т.д.). "
                "Покрой ВСЕ левые блоки.\nВерни ТОЛЬКО JSON."
            )
        else:
            text_part += f"\n{task_hint}\n\nВАЖНО: answer_text должен быть ПОЛНЫМ текстом варианта ответа из списка, а не одним словом.\nВерни ТОЛЬКО JSON."

        user_content = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"},
            },
            {
                "type": "text",
                "text": text_part,
            },
        ]

        payload = {
            "model": _get_active_model(),
            "max_tokens": AI_MAX_TOKENS,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_content},
            ],
        }
        headers = {
            "Authorization": f"Bearer {_get_active_api_key()}",
            "Content-Type":  "application/json",
        }

        async with httpx.AsyncClient(timeout=AI_TIMEOUT) as client:
            resp = await client.post(
                f"{ROUTERAI_BASE_URL}/chat/completions",
                json=payload,
                headers=headers,
            )

        if resp.status_code == 400:
            # Выводим причину ошибки для диагностики
            try:
                err_body = resp.json()
                self._log(f"   ℹ️ Vision API ответ: {err_body}")
            except Exception:
                self._log(f"   ℹ️ Vision API 400: {resp.text[:200]}")
            return None  # Сигнал для fallback на текст

        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]
        raw = choice["message"]["content"]
        finish = choice.get("finish_reason", "")

        usage = data.get("usage", {})
        inp, out = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
        session_stats.add_ai_call(inp, out)
        self._log(f"   💬 Vision токены: {inp} in / {out} out  (модель: {_get_active_model()})")

        return self._parse_ai_raw(raw, finish, "Vision")

    async def _call_routerai_text(self, html_snippet: str, task_hint: str) -> Optional[Dict]:
        """
        Вызов RouterAI только с текстом (HTML страницы).
        Не требует vision-модели.
        """
        import httpx

        user_content = (
            f"Анализируй HTML теста и определи вопрос + правильный ответ.\n\n"
            f"HTML страницы:\n```html\n{html_snippet}\n```\n"
            f"{task_hint}\n\n"
            "Верни ТОЛЬКО JSON с действием."
        )

        payload = {
            "model": _get_active_model(),
            "max_tokens": AI_MAX_TOKENS,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_content},
            ],
        }
        headers = {
            "Authorization": f"Bearer {_get_active_api_key()}",
            "Content-Type":  "application/json",
        }

        async with httpx.AsyncClient(timeout=AI_TIMEOUT) as client:
            resp = await client.post(
                f"{ROUTERAI_BASE_URL}/chat/completions",
                json=payload,
                headers=headers,
            )

        if resp.status_code != 200:
            try:
                err_body = resp.json()
                self._log(f"   ❌ Text API ошибка {resp.status_code}: {err_body}")
            except Exception:
                self._log(f"   ❌ Text API ошибка {resp.status_code}: {resp.text[:200]}")
            resp.raise_for_status()

        data = resp.json()
        choice = data["choices"][0]
        raw = choice["message"]["content"]
        finish = choice.get("finish_reason", "")

        usage = data.get("usage", {})
        inp, out = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
        session_stats.add_ai_call(inp, out)
        self._log(f"   💬 Text токены: {inp} in / {out} out  (модель: {_get_active_model()})")

        return self._parse_ai_raw(raw, finish, "Text")

    async def _call_ollama(self, screenshot_bytes: bytes, html_snippet: str, task_hint: str) -> Optional[Dict]:
        """Вызов локальной Ollama."""
        import httpx

        user_content: Any = (
            f"Анализируй тест. HTML:\n```\n{html_snippet}\n```{task_hint}\nВерни ТОЛЬКО JSON."
        )

        # Если Ollama поддерживает vision — добавляем изображение
        if screenshot_bytes:
            b64 = image_to_base64(screenshot_bytes)
            user_content = [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                {"type": "text", "text": f"HTML:\n```\n{html_snippet}\n```{task_hint}\nВерни ТОЛЬКО JSON."},
            ]

        payload = {
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_content},
            ],
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=AI_TIMEOUT * 2) as client:
            resp = await client.post(f"{OLLAMA_BASE_URL}/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()

        return extract_json_from_text(data["choices"][0]["message"]["content"])

    async def _execute_action(self, action_data: Dict) -> bool:
        """Диспетчер действий. Returns True если тест завершён."""
        action = action_data.get("action", "")
        if action == "test_complete":
            return True

        handlers = {
            "click":               self._action_click,
            "click_multiple":      self._action_click_multiple,
            "fill":                self._action_fill,
            "fill_textarea":       self._action_fill_textarea,
            "drag_and_drop":       self._action_drag_and_drop,
            "connect_match":       self._action_connect_match,
            "click_save":          self._action_click_save,
            "next_question":       self._action_next_question,
            "click_modal_confirm": self._action_modal_confirm,
            "wait":                self._action_wait,
        }

        h = handlers.get(action)
        if h:
            await h(action_data)
        else:
            self._log(f"⚠️ Неизвестное действие: {action}")

        return False

    def _parse_js_result(self, result) -> dict:
        """Парсит результат evaluate — может быть dict или list-of-lists от CDP."""
        if isinstance(result, dict):
            return result
        if isinstance(result, list):
            parsed = {}
            for item in result:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    key = item[0]
                    val = item[1]
                    if isinstance(val, dict) and 'value' in val:
                        parsed[key] = val['value']
                    else:
                        parsed[key] = val
            if parsed:
                return parsed
        return {"ok": False, "reason": "unknown_format"}

    async def _eval_json(self, js_body: str, timeout: float = 10.0):
        """Выполняет JS и возвращает результат как нативный Python-объект.

        nodriver.evaluate() с return_by_value=False отдаёт CDP deep-serialized
        структуру (list-of-pairs), из-за чего вложенные объекты/массивы (напр.
        список тестов) не превращаются в обычные dict/list. Поэтому JS должен
        вернуть строку, а мы оборачиваем выражение в JSON.stringify и парсим
        результат через json.loads — строки сериализуются корректно всегда.

        js_body — выражение, которое возвращает значение (например IIFE
        "(() => {{ ... return {{...}}; }})()").
        """
        wrapped = f"JSON.stringify(({js_body}))"
        raw = await asyncio.wait_for(self._tab.evaluate(wrapped), timeout=timeout)
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except Exception:
                return None
        # На случай если nodriver всё же вернул нативный объект
        if isinstance(raw, (dict, list)):
            return self._parse_js_result(raw) if isinstance(raw, list) else raw
        return None

    async def _click_by_index(self, index: int, input_type: str = "radio") -> bool:
        """Кликает по input в N-й строке tr.varanswer (1-based index)."""
        js = f"""
        (() => {{
            const rows = document.querySelectorAll('tr.varanswer');
            const idx = {index - 1};
            if (idx < 0 || idx >= rows.length) return {{ok: false, reason: 'out_of_range', total: rows.length}};
            const row = rows[idx];
            const inp = row.querySelector('input[type="{input_type}"]') || row.querySelector('input');
            if (!inp) return {{ok: false, reason: 'no_input_in_row'}};
            try {{ if (window.$ && window.$.fn && window.$.fn.iCheck) {{ $(inp).iCheck('check'); return {{ok: true, method: 'icheck_idx'}}; }} }} catch(e) {{}}
            inp.scrollIntoView({{block: 'center'}});
            inp.click();
            if (!inp.checked) inp.checked = true;
            inp.dispatchEvent(new Event('change', {{bubbles: true}}));
            return {{ok: true, method: 'index_click'}};
        }})()
        """
        try:
            raw = await self._tab.evaluate(js)
            result = self._parse_js_result(raw)
            self._log(f"   🔢 Index click [{index}]: {result}")
            if result.get("ok"):
                return True
        except Exception as e:
            self._log(f"   ⚠️ Index click error: {e}")
        return False

    async def _click_input_near_text(self, text: str, input_type: str = "radio") -> bool:
        """Находит текст ответа на странице и кликает по <input> в том же <tr>."""
        safe_text = text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ")
        safe_type = input_type.replace('"', '\\"')
        js = f"""
        (() => {{
            const searchText = '{safe_text}'.trim().toLowerCase();
            const inputType = "{safe_type}";
            const rows = document.querySelectorAll('tr.varanswer');
            let bestMatch = null;
            let bestLen = Infinity;
            for (const row of rows) {{
                const td = row.querySelector('td[id^="rtext"]');
                const cellText = td ? td.innerText.trim().toLowerCase() : row.innerText.trim().toLowerCase();
                if (cellText.includes(searchText) || searchText.includes(cellText)) {{
                    if (cellText.length < bestLen) {{
                        bestLen = cellText.length;
                        bestMatch = row;
                    }}
                }}
            }}
            if (!bestMatch) {{
                for (const row of rows) {{
                    const cellText = row.innerText.trim().toLowerCase();
                    if (cellText.includes(searchText) || searchText.includes(cellText)) {{
                        bestMatch = row;
                        break;
                    }}
                }}
            }}
            if (!bestMatch) return {{ok: false, reason: 'no_match', count: rows.length}};
            const inp = bestMatch.querySelector('input[type="' + inputType + '"]') || bestMatch.querySelector('input');
            if (!inp) return {{ok: false, reason: 'no_input'}};
            try {{ if (window.$ && window.$.fn && window.$.fn.iCheck) {{ $(inp).iCheck('check'); return {{ok: true, method: 'icheck'}}; }} }} catch(e) {{}}
            inp.scrollIntoView({{block: 'center'}});
            inp.click();
            if (!inp.checked) inp.checked = true;
            inp.dispatchEvent(new Event('change', {{bubbles: true}}));
            inp.dispatchEvent(new Event('click', {{bubbles: true}}));
            return {{ok: true, method: 'js_click'}};
        }})()
        """
        try:
            raw = await self._tab.evaluate(js)
            result = self._parse_js_result(raw)
            self._log(f"   🔍 JS result: {result}")
            if result.get("ok"):
                self._log(f"   ✅ Кликнул input ({result.get('method')})")
                return True
            else:
                self._log(f"   ⚠️ input не найден для «{text[:40]}» reason={result.get('reason')}")
        except Exception as e:
            self._log(f"   ⚠️ JS клик ошибка: {e}")
        return False

    async def _action_click(self, data: Dict) -> None:
        text = data.get("answer_text", "")
        index = data.get("answer_index")
        self._log(f"🖱️  Клик: «{text}» (index={index})")
        clicked = False
        # 1. Попытка по индексу — самый надёжный способ
        if index and isinstance(index, int):
            clicked = await self._click_by_index(index, "radio")
        # 2. Попытка по тексту
        if not clicked and text:
            clicked = await self._click_input_near_text(text, "radio")
        # 3. Fallback через nodriver find
        if not clicked:
            el = await self._find_by_text(text)
            if el:
                await self._human_click(el)
                clicked = True
            else:
                self._log(f"   ⚠️ Не найден: {text!r}")
        # Авто-сохранение после успешного клика
        if clicked:
            await async_random_delay(0.5, 1.0)
            await self._auto_save()

    async def _action_click_multiple(self, data: Dict) -> None:
        answers = data.get("answers", [])
        indices = data.get("answer_indices", [])
        self._log(f"☑️  Множественный выбор: {answers} (indices={indices})")
        clicked_any = False
        # По индексам
        if indices:
            for idx in indices:
                if isinstance(idx, int) and await self._click_by_index(idx, "checkbox"):
                    clicked_any = True
                    await async_random_delay(0.4, 0.9)
        # По тексту (если индексы не сработали)
        if not clicked_any:
            for ans in answers:
                if await self._click_input_near_text(ans, "checkbox"):
                    clicked_any = True
                    await async_random_delay(0.4, 0.9)
                    continue
                el = await self._find_by_text(ans)
                if el:
                    await self._human_click(el)
                    clicked_any = True
                    await async_random_delay(0.4, 0.9)
                else:
                    self._log(f"   ⚠️ Не найден: {ans!r}")
        # Авто-сохранение после выбора
        if clicked_any:
            await async_random_delay(0.5, 1.0)
            await self._auto_save()

    async def _action_fill(self, data: Dict) -> None:
        fields = data.get("fields", [])
        self._log(f"⌨️  Заполнение {len(fields)} поля(ей)")
        any_filled = False
        for i, fi in enumerate(fields):
            value       = fi.get("value", "")
            placeholder = fi.get("placeholder", "")
            self._log(f"   ✏️ Поле {i+1} [{placeholder}]: «{value}»")
            filled = await self._js_fill_input(i, placeholder, value)
            if filled:
                any_filled = True
                await async_random_delay(0.3, 0.6)
            else:
                self._log(f"   ⚠️ Поле {i+1} не заполнено — пробуем send_keys")
        if any_filled:
            await self._wait_and_save()

    async def _js_fill_input(self, index: int, placeholder: str, value: str) -> bool:
        """
        Заполняет input:
        1. JS ищет поле БЕЗ фильтра offsetParent и ставит фокус
        2. CDP Input.insertText — реальный ввод в сфокусированное поле
        3. Tab через CDP — снимает фокус → сайт показывает SaveButton
        """
        safe_ph = placeholder.replace("\\", "\\\\").replace("'", "\\'").lower()

        # Шаг 1: JS фокусирует поле
        focus_js = f"""
        (() => {{
            const all = [
                ...document.querySelectorAll('input.inpas'),
                ...document.querySelectorAll('input[type="text"]'),
                ...document.querySelectorAll('textarea'),
                ...document.querySelectorAll('input:not([type="hidden"]):not([type="radio"]):not([type="checkbox"]):not([type="submit"]):not([type="button"])'),
            ];
            const seen = new Set();
            const inputs = all.filter(el => {{ if (seen.has(el)) return false; seen.add(el); return el.type !== 'hidden'; }});

            let target = null;
            if ('{safe_ph}') {{
                // Собираем ВСЕ поля с совпадающим placeholder/name/id
                const matched = inputs.filter(el => (el.placeholder||el.name||el.id||'').toLowerCase().includes('{safe_ph}'));
                // Берём N-й по счёту (для случая двух одинаковых полей)
                target = matched[{index}] || matched[0];
            }}
            if (!target) target = inputs[{index}] || inputs[0];
            if (!target) return {{ok: false, reason: 'no_input', total: inputs.length}};

            target.removeAttribute('readonly');
            target.removeAttribute('disabled');
            target.scrollIntoView({{block: 'center'}});
            target.click();
            target.focus();
            target.select();
            target.value = '';
            target.dispatchEvent(new Event('input', {{bubbles: true}}));
            return {{ok: true, id: target.id || target.name || target.placeholder || String({index})}};
        }})()
        """
        try:
            raw = await self._tab.evaluate(focus_js)
            result = self._parse_js_result(raw)
            if not result.get("ok"):
                self._log(f"   ⚠️ JS фокус: {result.get('reason')} (полей: {result.get('total', 0)})")
                return False
            self._log(f"   🎯 Поле найдено: {result.get('id')}")
        except Exception as e:
            self._log(f"   ⚠️ JS фокус: {e}")
            return False

        await asyncio.sleep(0.15)

        # Шаг 2: CDP insertText — настоящий браузерный ввод
        try:
            await self._tab.send(uc.cdp.input_.insert_text(text=value))
            await asyncio.sleep(0.15)
            self._log(f"   ✅ CDP insertText OK: «{value}»")
        except Exception as e:
            self._log(f"   ⚠️ CDP insertText: {e} — JS fallback")
            safe_val = value.replace("\\", "\\\\").replace("'", "\\'")
            try:
                await self._tab.evaluate(f"""
                (() => {{
                    const el = document.activeElement;
                    if (el) {{
                        const d = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
                        if (d && d.set) d.set.call(el, '{safe_val}'); else el.value = '{safe_val}';
                        el.dispatchEvent(new InputEvent('input', {{bubbles:true, inputType:'insertText', data:'{safe_val}'}}));
                        el.dispatchEvent(new Event('change', {{bubbles:true}}));
                    }}
                }})()
                """)
            except Exception as e2:
                self._log(f"   ⚠️ JS-setter: {e2}")
                return False

        # Шаг 3: Tab — снимает фокус, сайт показывает SaveButton
        await self._press_tab()
        return True

    async def _press_tab(self) -> None:
        """Tab через CDP — снимает фокус с поля (blur/focusout → SaveButton)."""
        try:
            await self._tab.send(uc.cdp.input_.dispatch_key_event(
                type_="keyDown", key="Tab", code="Tab",
                windows_virtual_key_code=9, native_virtual_key_code=9,
            ))
            await asyncio.sleep(0.05)
            await self._tab.send(uc.cdp.input_.dispatch_key_event(
                type_="keyUp", key="Tab", code="Tab",
                windows_virtual_key_code=9, native_virtual_key_code=9,
            ))
            await asyncio.sleep(0.2)
        except Exception as e:
            logger.debug("_press_tab: %s", e)
            try:
                await self._tab.evaluate("""
                (() => { if (document.activeElement && document.activeElement !== document.body)
                    document.activeElement.blur(); })()
                """)
                await asyncio.sleep(0.15)
            except Exception:
                pass

    async def _cdp_mouse_click(self, x: int, y: int) -> None:
        """Физический клик мышью через CDP."""
        try:
            await self._tab.send(uc.cdp.input_.dispatch_mouse_event(
                type_="mousePressed", x=x, y=y,
                button=uc.cdp.input_.MouseButton.LEFT, click_count=1,
            ))
            await asyncio.sleep(0.05)
            await self._tab.send(uc.cdp.input_.dispatch_mouse_event(
                type_="mouseReleased", x=x, y=y,
                button=uc.cdp.input_.MouseButton.LEFT, click_count=1,
            ))
        except Exception as e:
            logger.warning("_cdp_mouse_click (%d,%d): %s — JS fallback", x, y, e)
            try:
                await self._tab.evaluate("(() => { const b=document.getElementById('SaveButton'); if(b) b.click(); })()")
            except Exception:
                pass

    async def _wait_and_save(self, max_wait: float = 12.0) -> bool:
        """
        После ввода текста:
        1. Снимаем фокус (blur) — сайт должен показать SaveButton
        2. Ждём фиксированные 1.2с (без обращения к AI!)
        3. Кликаем по SaveButton физически через CDP
        4. Если кнопка не появилась — Ctrl+S
        """
        self._log("   ⏳ Ждём кнопку СОХРАНИТЬ после ввода...")

        # Blur — снимаем фокус с поля ввода
        try:
            await self._tab.evaluate("""
            (() => { const el=document.activeElement;
              if(el && el!==document.body){ el.blur(); el.dispatchEvent(new Event('focusout',{bubbles:true})); }
            })()
            """)
        except Exception:
            pass

        # Ждём появления кнопки (опрос каждые 300мс, максимум max_wait)
        start = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start < max_wait:
            if self._stop_flag:
                return False
            # Во время паузы не таймаутим — просто ждём снятия паузы
            if self._pause_flag:
                await asyncio.sleep(0.5)
                continue
            await asyncio.sleep(0.3)
            try:
                rect_raw = await self._tab.evaluate("""
                (() => {
                    const btn = document.getElementById('SaveButton');
                    if (!btn) return null;
                    const r = btn.getBoundingClientRect();
                    return {visible: btn.offsetParent!==null || r.width>0,
                            x: Math.round(r.left+r.width/2), y: Math.round(r.top+r.height/2),
                            w: Math.round(r.width), h: Math.round(r.height)};
                })()
                """)
                rect = self._parse_js_result(rect_raw) if rect_raw else {}
                if rect and rect.get("visible") and rect.get("w", 0) > 0:
                    cx, cy = rect["x"], rect["y"]
                    self._log(f"   🖱️ Кликаем по SaveButton ({cx},{cy})")
                    await self._cdp_mouse_click(cx, cy)
                    await asyncio.sleep(0.3)
                    self._log("   💾 Сохранено ✅")
                    await self._wait_for_next_question()
                    return True
            except Exception as e:
                logger.debug("_wait_and_save poll: %s", e)

        # Финальный резерв: Ctrl+S
        self._log("   ⚠️ SaveButton не появилась — Ctrl+S")
        try:
            await self._tab.send(uc.cdp.input_.dispatch_key_event(
                type_="keyDown", key="s", code="KeyS", modifiers=2,
                windows_virtual_key_code=83, native_virtual_key_code=83,
            ))
            await asyncio.sleep(0.05)
            await self._tab.send(uc.cdp.input_.dispatch_key_event(
                type_="keyUp", key="s", code="KeyS", modifiers=2,
                windows_virtual_key_code=83, native_virtual_key_code=83,
            ))
            self._log("   ⌨️ Ctrl+S отправлен")
            await asyncio.sleep(1.0)
        except Exception as e:
            logger.warning("Ctrl+S: %s", e)
        return await self._auto_save()

    async def _wait_for_next_question(self, max_wait: float = 30.0) -> bool:
        """Ждёт появления следующего вопроса после сохранения."""
        self._log("   ⏳ Ждём следующий вопрос...")
        start = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start < max_wait:
            if self._stop_flag:
                return False
            if self._pause_flag:
                await asyncio.sleep(0.5)
                continue
            await asyncio.sleep(1.0)
            try:
                raw = await asyncio.wait_for(self._tab.evaluate("""
                (() => {
                    const q       = document.getElementById('qst');
                    const vars    = document.querySelectorAll('tr.varanswer');
                    const inpas   = document.querySelectorAll('input.inpas');
                    const text    = q ? q.innerText.trim() : '';
                    return text.length > 5 || vars.length > 0 || inpas.length > 0;
                })()
                """), timeout=5.0)
                if raw:
                    self._log("   ✅ Вопрос загружен")
                    await asyncio.sleep(0.5)
                    return True
            except Exception:
                pass
        self._log(f"   ⚠️ Таймаут ожидания ({max_wait:.0f}с)")
        return False

    async def _action_wait(self, data: Dict) -> None:
        """Ожидаем загрузки следующего вопроса."""
        self._log("⏳ Ожидание загрузки вопроса...")
        await self._wait_for_next_question()

    async def _action_fill_textarea(self, data: Dict) -> None:
        value = data.get("value", "")
        self._log(f"📝 Свободный ответ: «{value[:60]}»")
        # Единая логика с _action_fill: JS фокус → CDP insertText → Tab → SaveButton
        filled = await self._js_fill_input(0, "", value)
        if filled:
            await self._wait_and_save()
        else:
            self._log("   ⚠️ Поле ввода не найдено")

    async def _action_drag_and_drop(self, data: Dict) -> None:
        pairs = data.get("pairs", [])
        self._log(f"🔀 Drag-and-drop: {len(pairs)} пар(ы)")
        for pair in pairs:
            src_el = await self._find_by_text(pair.get("source", ""))
            tgt_el = await self._find_by_text(pair.get("target", ""))
            if src_el and tgt_el:
                try:
                    await src_el.drag_to(tgt_el)
                    self._log("   ✅ Перетащено")
                except Exception:
                    await self._js_drag(src_el, tgt_el)
                await async_random_delay(0.5, 1.2)
            else:
                self._log("   ⚠️ Элементы не найдены")

    async def _click_node_by_id(self, node_id: str) -> bool:
        """Кликает по td-узлу сопоставления по id (вызывает его onclick).

        Сначала пробуем el.click() (вызовет setconnectstart/setconnectend),
        если узел не среагировал — физический CDP-клик по центру.
        """
        if not node_id:
            return False
        safe = node_id.replace("'", "\\'")
        try:
            rect_raw = await self._tab.evaluate(f"""
            (() => {{
                const el = document.getElementById('{safe}');
                if (!el) return null;
                el.scrollIntoView({{block:'center'}});
                try {{ el.click(); }} catch(e) {{}}
                const r = el.getBoundingClientRect();
                return {{ ok:true, x: Math.round(r.left+r.width/2), y: Math.round(r.top+r.height/2) }};
            }})()
            """)
            rect = self._parse_js_result(rect_raw) if rect_raw else {}
            if rect.get("ok"):
                # Дублируем физическим кликом для надёжности (сайт ведёт varconnectionlist)
                try:
                    await self._cdp_mouse_click(rect.get("x", 0), rect.get("y", 0))
                except Exception:
                    pass
                return True
        except Exception as exc:
            logger.debug("_click_node_by_id(%s): %s", node_id, exc)
        return False

    async def _action_connect_match(self, data: Dict) -> None:
        """Сопоставление: кликаем левый блок → правый, для всех пар, затем СОХРАНИТЬ.

        Если пары от ИИ кривые/неполные/неуверенные — соединяем по порядку
        (a_1→b_1, a_2→b_2, ...), беря реальные id из DOM (self._matching_nodes).
        """
        nodes = getattr(self, "_matching_nodes", {}) or {}
        lefts = nodes.get("left") or []
        rights = nodes.get("right") or []
        left_ids = [L.get("id", "") for L in lefts if L.get("id")]
        right_ids = [R.get("id", "") for R in rights if R.get("id")]

        if not left_ids or not right_ids:
            self._log("   ⚠️ Сопоставление: нет узлов на странице — пропускаю")
            return

        pairs = data.get("pairs", []) or []
        conf = float(data.get("confidence", 0) or 0)

        # Проверяем валидность пар от ИИ
        valid = []
        seen_left, seen_right = set(), set()
        for p in pairs:
            lid = str(p.get("left_id", "")).strip()
            rid = str(p.get("right_id", "")).strip()
            if lid in left_ids and rid in right_ids and lid not in seen_left and rid not in seen_right:
                valid.append((lid, rid))
                seen_left.add(lid)
                seen_right.add(rid)

        use_ai = len(valid) == len(left_ids) and conf >= 0.4
        if use_ai:
            final_pairs = valid
            self._log(f"   🔗 Сопоставление от ИИ: {len(final_pairs)} пар (conf={conf:.0%})")
        else:
            # Fallback «по порядку»: a_i → b_i
            n = min(len(left_ids), len(right_ids))
            final_pairs = [(left_ids[i], right_ids[i]) for i in range(n)]
            self._log(f"   🔗 Сопоставление по порядку (fallback): {len(final_pairs)} пар "
                      f"(ИИ дал {len(valid)}/{len(left_ids)}, conf={conf:.0%})")

        for lid, rid in final_pairs:
            ok_l = await self._click_node_by_id(lid)
            await async_random_delay(0.4, 0.9)
            ok_r = await self._click_node_by_id(rid)
            await async_random_delay(0.4, 0.9)
            self._log(f"      {lid} → {rid} {'✅' if (ok_l and ok_r) else '⚠️'}")

        # После соединения всех блоков появляется кнопка СОХРАНИТЬ
        self._is_matching = False
        await self._auto_save()

    async def _auto_save(self) -> bool:
        """
        Нажимает SaveButton физически (CDP mouse click).
        Используется после radio/checkbox кликов — без дополнительного AI-запроса.
        """
        # Короткая пауза чтобы сайт успел показать кнопку
        await asyncio.sleep(0.8)
        try:
            rect_raw = await self._tab.evaluate("""
            (() => {
                const btn = document.getElementById('SaveButton');
                if (!btn) return null;
                const r = btn.getBoundingClientRect();
                return {visible: btn.offsetParent!==null || r.width>0,
                        x: Math.round(r.left+r.width/2), y: Math.round(r.top+r.height/2),
                        w: Math.round(r.width)};
            })()
            """)
            rect = self._parse_js_result(rect_raw) if rect_raw else {}
            if rect and rect.get("visible") and rect.get("w", 0) > 0:
                await self._cdp_mouse_click(rect["x"], rect["y"])
                self._log("   💾 Авто-сохранение ✅")
                await self._wait_for_next_question()
                return True
            self._log("   💾 Кнопка сохранения не видна")
        except Exception as e:
            self._log(f"   ⚠️ Авто-сохранение: {e}")
        return False

    async def _action_click_save(self, data: Dict) -> None:
        self._log("💾 Нажимаем «СОХРАНИТЬ ОТВЕТ»")
        for text in ["СОХРАНИТЬ ОТВЕТ", "Сохранить ответ", "СОХРАНИТЬ", "Сохранить"]:
            el = await self._find_by_text(text)
            if el:
                await self._human_click(el)
                await async_random_delay(0.8, 1.5)
                return
        el = await self._safe_select("button[type='submit'], input[type='submit']")
        if el:
            await self._human_click(el)
        else:
            self._log("   ⚠️ Кнопка сохранения не найдена")

    def _should_skip_images(self) -> bool:
        """Читает настройку «пропускать вопросы с картинками» (по умолч. ВКЛ)."""
        try:
            from gui.theme import _settings
            return bool(_settings.get("skip_image_questions", True))
        except Exception:
            return True

    async def _skip_current_question(self) -> bool:
        """Нажимает «ПРОПУСТИТЬ» (#skip_btn / SkipQuest()) на странице теста."""
        try:
            res = await self._tab.evaluate("""
            (() => {
                const b = document.getElementById('skip_btn');
                if (b) { b.click(); return true; }
                if (typeof SkipQuest === 'function') { SkipQuest(); return true; }
                return false;
            })()
            """)
            ok = bool(res) if not isinstance(res, dict) else bool(res.get("value", res))
            if ok:
                await self._wait_for_next_question(max_wait=15.0)
            return ok
        except Exception as exc:
            logger.debug("_skip_current_question: %s", exc)
            return False

    async def _action_next_question(self, data: Dict) -> None:
        q_num = data.get("question_number")
        self._log(f"➡️  Переход к вопросу #{q_num}")
        if q_num:
            el = await self._find_by_text(str(q_num), tag="li") or await self._find_by_text(str(q_num), tag="a")
            if el:
                await self._human_click(el)
                await asyncio.sleep(1.0)
                return
        el = await self._safe_select(".unanswered, .question-nav li:not(.answered)")
        if el:
            await self._human_click(el)
            await asyncio.sleep(1.0)

    async def _is_test_in_progress(self) -> bool:
        """Проверяет, идёт ли уже тест (есть вопрос на странице)."""
        try:
            result = await self._tab.evaluate("""
            (() => {
                const qst = document.getElementById('qst');
                const variants = document.querySelectorAll('tr.varanswer');
                const fillInputs = document.querySelectorAll('input.inpas');
                return (qst && qst.textContent.trim().length > 0) || variants.length > 0 || fillInputs.length > 0;
            })()
            """)
            return bool(result)
        except Exception:
            return False

    async def _action_modal_confirm(self, data: Dict) -> None:
        btn_text = data.get("button_text", "ДА")
        self._log(f"🔔 Модал: «{btn_text}»")
        if "ПРИСТУПИТЬ" in btn_text.upper() and await self._is_test_in_progress():
            self._log("   ℹ️ Тест уже идёт, жду следующий вопрос...")
            await self._wait_for_next_question()
            return
        el = await self._find_by_text(btn_text) or await self._safe_select(".modal button, dialog button")
        if el:
            await self._human_click(el)
            await async_random_delay(0.5, 1.0)
        else:
            self._log(f"   ⚠️ Кнопка «{btn_text}» не найдена")

    async def _human_click(self, element) -> None:
        try:
            await element.scroll_into_view()
            await asyncio.sleep(0.15)
            await element.click()
        except Exception as exc:
            logger.warning("_human_click: %s", exc)

    async def _human_type(self, element, text: str) -> None:
        try:
            await element.scroll_into_view()
            await asyncio.sleep(0.1)
            await element.click(click_count=3)
            await asyncio.sleep(0.1)
            await element.send_keys(text)
        except Exception as exc:
            logger.warning("_human_type: %s, JS fallback", exc)
            try:
                await self._tab.evaluate(
                    "(el, v) => { el.focus(); el.value=v; el.dispatchEvent(new Event('input',{bubbles:true})); }",
                    element, text
                )
            except Exception as e2:
                logger.error("JS ввод провалился: %s", e2)

    async def _js_drag(self, source, target) -> None:
        try:
            script = """(function(src,tgt){const dt=new DataTransfer();
            ['dragstart','dragenter','dragover'].forEach(e=>src.dispatchEvent(new DragEvent(e,{bubbles:true,cancelable:true,dataTransfer:dt})));
            tgt.dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:dt}));
            src.dispatchEvent(new DragEvent('dragend',{bubbles:true,dataTransfer:dt}));})(arguments[0],arguments[1]);"""
            await self._tab.evaluate(script, source, target)
        except Exception as exc:
            logger.warning("_js_drag: %s", exc)

    async def _find_by_text(self, text: str, tag: str = "*"):
        if not text:
            return None
        try:
            el = await self._tab.find(text, best_match=True, timeout=3)
            if el:
                return el
        except Exception:
            pass
        try:
            text_esc = text.replace("'", "\\'").replace('"', '\\"')
            result = await self._tab.evaluate(
                f"[...document.querySelectorAll('{tag}')].find(el=>el.textContent.trim().includes('{text_esc}'))"
            )
            return result
        except Exception:
            return None

    async def _safe_select(self, selector: str):
        try:
            return await self._tab.select(selector)
        except Exception:
            return None

    def _log(self, msg: str):
        logger.info(msg)
        # Выводим в журнал ОДИН раз: либо через log_cb, либо через сигнал.
        # GUI передаёт log_cb, который сам испускает log_message — поэтому
        # повторный emit здесь приводил бы к дублированию строк.
        if self.log_cb:
            self.log_cb(msg)
        elif self._agent_signals:
            self._agent_signals.log_message.emit(msg)

    def _status(self, msg: str):
        if self.status_cb:
            self.status_cb(msg)
        elif self._agent_signals:
            self._agent_signals.status_update.emit(msg)

    def _play_sound(self, event_key: str):
        """Просит GUI проиграть звук уведомления (ai_error|test_done|error)."""
        if self._agent_signals is not None:
            try:
                self._agent_signals.play_sound.emit(str(event_key))
            except Exception:
                pass

    async def _emit_test_results(self):
        """Парсит страницу результатов и отправляет статистику в GUI (окно).

        Извлекает из блока «СТАТИСТИКА ОТВЕТОВ ПО ЗАДАНИЮ» цифры, оценку,
        и (если есть) разбивку по темам из массивов flot (d1/d2 + themestr).
        """
        js = r"""
        (() => {
            const out = { ok: false, title: '', discipline: '',
                          total: '', answered: '', correct: '', wrong: '',
                          grade: '', themes: [] };
            const bodyText = document.body ? document.body.innerText : '';
            // Заголовок теста и дисциплина
            const tMatch = bodyText.match(/Тест:\s*([^\n]+)/i);
            if (tMatch) out.title = tMatch[1].trim();
            const dMatch = bodyText.match(/Дисциплина:\s*([^\n]+)/i);
            if (dMatch) out.discipline = dMatch[1].trim();

            // Блок статистики — ищем по ключевым строкам
            const grab = (re) => { const m = bodyText.match(re); return m ? m[1].trim() : ''; };
            out.total    = grab(/Количество вопросов:\s*([0-9]+)/i);
            out.answered = grab(/Введено ответов:\s*([0-9]+\s*\(?[0-9]*%?\)?)/i);
            out.correct  = grab(/Верно отвечено:\s*([0-9]+\s*\(?[0-9]*%?\)?)/i);
            out.wrong    = grab(/Неверно отвечено:\s*([0-9]+\s*\(?[0-9]*%?\)?)/i);
            out.grade    = grab(/Заключение:\s*([^\n]+)/i);
            if (out.correct || out.grade) out.ok = true;

            // Разбивка по темам из flot-данных (если есть на странице)
            try {
                const scripts = [...document.querySelectorAll('script')].map(s => s.textContent).join('\n');
                const tm = scripts.match(/var\s+themestr\s*=\s*(\[[\s\S]*?\]);/);
                const d1m = scripts.match(/var\s+d1\s*=\s*(\[[\s\S]*?\]);/);
                const d2m = scripts.match(/var\s+d2\s*=\s*(\[[\s\S]*?\]);/);
                if (tm && d1m && d2m) {
                    const themes = JSON.parse(tm[1].replace(/'/g, '"'));
                    const d1 = JSON.parse(d1m[1]);
                    const d2 = JSON.parse(d2m[1]);
                    // d1/d2: [[themeIdx, count], ...]
                    for (let i = 0; i < d1.length; i++) {
                        const idx = d1[i][0];
                        const ok = d1[i][1];
                        const bad = (d2[i] && d2[i][1]) || 0;
                        const name = themes[idx-1] || ('Тема ' + idx);
                        out.themes.push({ name: name, correct: ok, wrong: bad });
                    }
                }
            } catch(e) {}

            return out;
        })()
        """
        try:
            data = await self._eval_json(js, timeout=8.0)
            if data and data.get("ok"):
                self._log("📊 Результаты теста извлечены — открою окно.")
                if self._agent_signals is not None:
                    self._agent_signals.results_ready.emit(dict(data))
            else:
                self._log("   ⚠️ Не удалось извлечь статистику результатов.")
        except Exception as exc:
            logger.debug("_emit_test_results: %s", exc)