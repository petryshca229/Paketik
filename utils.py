"""
utils.py — Вспомогательные утилиты Paketik
==============================================
Функции для скриншотов, кодирования изображений,
работы с путями браузеров, логирования и т.д.
"""

import os
import sys
import time
import random
import logging
import base64
import math
import asyncio
from pathlib import Path
from typing import Optional, List, Tuple
from io import BytesIO

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
#  Работа с браузерными путями
# ══════════════════════════════════════════════════════════════════════════════

def find_browser_executable(browser_name: str) -> Optional[str]:
    """
    Ищет исполняемый файл браузера по стандартным путям.

    Args:
        browser_name: 'Yandex' или 'Chrome'

    Returns:
        Путь к executable или None
    """
    from config import BROWSER_PATHS, USER_DATA_BASE

    candidates = BROWSER_PATHS.get(browser_name, [])
    user = os.environ.get("USERNAME") or os.environ.get("USER") or ""

    for path_template in candidates:
        path = path_template.replace("{user}", user)
        if os.path.exists(path):
            logger.debug("Найден браузер %s: %s", browser_name, path)
            return path

    logger.warning("Браузер %s не найден ни по одному из путей", browser_name)
    return None


def get_user_data_dir(browser_name: str) -> str:
    """
    Возвращает путь к папке профиля браузера для агента.
    Создаёт директорию при необходимости.

    Использование отдельного профиля критично:
    - Сохраняет cookies / сессию между запусками
    - Не мешает обычному браузеру пользователя
    """
    from config import USER_DATA_BASE
    profile_dir = Path(USER_DATA_BASE) / browser_name.lower()
    profile_dir.mkdir(parents=True, exist_ok=True)
    return str(profile_dir)


# ══════════════════════════════════════════════════════════════════════════════
#  Скриншоты и изображения
# ══════════════════════════════════════════════════════════════════════════════

def image_to_base64(image_bytes: bytes) -> str:
    """
    Конвертирует bytes изображения в base64-строку (data URI).

    Используется для передачи скриншота в API с поддержкой vision.
    """
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    return b64


def resize_screenshot(image_bytes: bytes, max_width: int = 1280) -> bytes:
    """
    Уменьшает скриншот до max_width пикселей по ширине (сохраняя пропорции).
    Нужно, чтобы не превышать лимит токенов vision-модели.
    """
    try:
        from PIL import Image
        img = Image.open(BytesIO(image_bytes))
        if img.width > max_width:
            ratio  = max_width / img.width
            new_h  = int(img.height * ratio)
            img    = img.resize((max_width, new_h), Image.LANCZOS)
        buf = BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
    except ImportError:
        logger.debug("Pillow не установлен, скриншот без ресайза")
        return image_bytes
    except Exception as exc:
        logger.warning("resize_screenshot ошибка: %s", exc)
        return image_bytes


# ══════════════════════════════════════════════════════════════════════════════
#  Антибот: реалистичные задержки и движение мыши
# ══════════════════════════════════════════════════════════════════════════════

def random_delay(min_s: float = None, max_s: float = None):
    """
    Синхронная пауза случайной длины.
    По умолчанию использует значения из config.
    """
    from config import DELAY_MIN, DELAY_MAX
    lo = min_s if min_s is not None else DELAY_MIN
    hi = max_s if max_s is not None else DELAY_MAX
    t = random.uniform(lo, hi)
    logger.debug("Задержка %.2f с", t)
    time.sleep(t)


async def async_random_delay(min_s: float = None, max_s: float = None):
    """Асинхронная версия random_delay (для async-кода Nodriver)."""
    from config import DELAY_MIN, DELAY_MAX
    lo = min_s if min_s is not None else DELAY_MIN
    hi = max_s if max_s is not None else DELAY_MAX
    t = random.uniform(lo, hi)
    logger.debug("Async задержка %.2f с", t)
    await asyncio.sleep(t)


def bezier_curve_points(
    start: Tuple[float, float],
    end: Tuple[float, float],
    num_points: int = 20,
) -> List[Tuple[float, float]]:
    """
    Генерирует точки кривой Безье между двумя координатами.

    Зачем: реальный пользователь двигает мышь по плавной кривой, а не по прямой.
    Даже если Nodriver сам умеет это делать, явная траектория
    делает поведение более человекоподобным.

    Args:
        start: (x1, y1) начало
        end:   (x2, y2) конец
        num_points: количество промежуточных точек

    Returns:
        Список (x, y) точек траектории включая start и end
    """
    x1, y1 = start
    x2, y2 = end

    # Контрольные точки — смещены случайным образом
    mid_x = (x1 + x2) / 2 + random.uniform(-60, 60)
    mid_y = (y1 + y2) / 2 + random.uniform(-60, 60)

    points = []
    for i in range(num_points + 1):
        t = i / num_points
        # Квадратичная кривая Безье: B(t) = (1-t)²P0 + 2(1-t)tP1 + t²P2
        bx = (1 - t) ** 2 * x1 + 2 * (1 - t) * t * mid_x + t ** 2 * x2
        by = (1 - t) ** 2 * y1 + 2 * (1 - t) * t * mid_y + t ** 2 * y2
        # Добавляем лёгкий "тремор"
        bx += random.uniform(-1.5, 1.5)
        by += random.uniform(-1.5, 1.5)
        points.append((bx, by))

    return points


# ══════════════════════════════════════════════════════════════════════════════
#  Парсинг JSON из ответа AI
# ══════════════════════════════════════════════════════════════════════════════

def extract_json_from_text(text: str) -> Optional[dict]:
    """
    Извлекает JSON из текстового ответа LLM.

    LLM часто оборачивают JSON в ```json ... ``` или пишут лишний текст.
    Эта функция аккуратно достаёт именно JSON-объект.

    Returns:
        dict или None, если JSON не найден
    """
    import json
    import re

    if not text or not text.strip():
        logger.warning("Пустой ответ AI")
        return None

    # Убираем markdown-блоки
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)

    # Чистим trailing punctuation (LLM часто ставят точку после })
    text = text.strip().rstrip(".,;:") + "\n"

    # Подход 1: ищем {...} с учётом вложенности
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                candidate = text[start:i+1]
                try:
                    result = json.loads(candidate)
                    if isinstance(result, dict):
                        logger.debug("JSON распарсен (depth, pos=%d): %s", i - start, str(result)[:80])
                        return result
                except json.JSONDecodeError:
                    pass
                start = None   # сбрасываем — пробуем следующий блок

    # Подход 2: ищем первый {...} блок (без depth-трекинга)
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, dict):
                logger.debug("JSON распарсен (simple): %s", str(result)[:80])
                return result
        except json.JSONDecodeError:
            pass

    # Подход 3: repair — чиним типичные ошибки LLM
    repaired = _repair_json(text)
    if repaired:
        try:
            result = json.loads(repaired)
            if isinstance(result, dict):
                logger.debug("JSON распарсен (repaired)")
                return result
        except json.JSONDecodeError:
            pass

    logger.warning("JSON не найден в ответе AI: %s", text[:200])
    return None


def _repair_json(text: str) -> Optional[str]:
    """
    Исправляет типичные ошибки JSON от LLM:
    - trailing commas
    - одинарные кавычки
    - комментарии
    - незакрытые строки
    - HTML-сущности
    """
    import re

    # Убираем всё до первого {
    first_brace = text.find("{")
    if first_brace == -1:
        return None
    text = text[first_brace:]

    # trailing commas перед } или ]
    text = re.sub(r",(\s*[}\]])", r"\1", text)

    # Одинарные кавычки → двойные (только вне JSON-строк)
    # Простой вариант: меняем ' на " внутри строк
    result = []
    i = 0
    in_string = False
    while i < len(text):
        ch = text[i]
        if ch == '"' and (i == 0 or text[i-1] != "\\"):
            in_string = not in_string
            result.append(ch)
        elif ch == "'" and not in_string:
            result.append('"')
        else:
            result.append(ch)
        i += 1
    text = "".join(result)

    # Убираем HTML-сущности
    text = text.replace("&quot;", '"').replace("&apos;", "'")
    text = text.replace("&#39;", "'").replace("&amp;", "&")

    # ── Восстановление ОБРЕЗАННОГО JSON ─────────────────────
    # Если ответ модели был обрезан по лимиту токенов, у нас открыта строка
    # и/или не закрыты {}[]. Достраиваем хвост, чтобы спасти то, что пришло.
    in_string = False
    escape = False
    stack = []  # стек открытых { и [
    for ch in text:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if not in_string:
            if ch in "{[":
                stack.append(ch)
            elif ch == "}" and stack and stack[-1] == "{":
                stack.pop()
            elif ch == "]" and stack and stack[-1] == "[":
                stack.pop()

    # Закрываем незавершённую строку
    if in_string:
        text = text.rstrip()
        text += '"'

    # Закрываем оставшиеся открытые скобки в обратном порядке
    if stack:
        text = text.rstrip().rstrip(",")
        for opener in reversed(stack):
            text += "}" if opener == "{" else "]"

    return text


# ══════════════════════════════════════════════════════════════════════════════
#  Логирование
# ══════════════════════════════════════════════════════════════════════════════

def setup_logging(log_file: str = "paketik.log", level: str = "DEBUG"):
    """
    Настраивает логирование: в файл + в консоль.
    Вызывается один раз из main.py при запуске.
    """
    numeric_level = getattr(logging, level.upper(), logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(numeric_level)

    # Файловый хэндлер с ротацией — чтобы лог не разрастался до гигабайтов.
    # (раньше был обычный FileHandler в режиме 'a' без ограничения размера)
    from logging.handlers import RotatingFileHandler
    fh = RotatingFileHandler(
        log_file, encoding="utf-8", mode="a",
        maxBytes=5 * 1024 * 1024, backupCount=2,
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # Консольный хэндлер
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    # ── Глушим шумные сторонние логгеры ──────────────────────────────────
    # Даже при LOG_LEVEL=DEBUG nodriver/websockets пишут КАЖДЫЙ CDP-кадр,
    # что забивает диск гигабайтами и подвешивает event loop. Держим их на
    # WARNING независимо от уровня приложения.
    for noisy in ("nodriver", "websockets", "websockets.client",
                  "websockets.server", "uc", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logger.info("Логирование инициализировано (уровень=%s, файл=%s)", level, log_file)


# ══════════════════════════════════════════════════════════════════════════════
#  Статистика
# ══════════════════════════════════════════════════════════════════════════════

class SessionStats:
    """
    Накапливает статистику текущей сессии агента.
    Используется GUI для отображения прогресса.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.questions_answered = 0
        self.actions_total      = 0
        self.tokens_spent       = 0
        self.errors             = 0
        self.started_at         = time.time()

    def add_ai_call(self, input_tokens: int, output_tokens: int,
                    model: str = ""):
        """Зафиксировать использование токенов и сразу списать из лицензии."""
        total = input_tokens + output_tokens
        self.tokens_spent += total

        # Немедленное списание — не ждём паузы/остановки
        try:
            from license_mgr import license_manager
            license_manager.consume_tokens(total)
        except Exception:
            pass

    def elapsed_str(self) -> str:
        secs = int(time.time() - self.started_at)
        m, s = divmod(secs, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def summary(self) -> str:
        return (
            f"Вопросов: {self.questions_answered} | "
            f"Действий: {self.actions_total} | "
            f"Токенов: {self.tokens_spent:,} | "

            f"Время: {self.elapsed_str()}"
        )


# Глобальный экземпляр статистики
session_stats = SessionStats()
