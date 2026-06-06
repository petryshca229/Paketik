"""
gui/sound_manager.py — Звуковые уведомления Paketik 4.7.1

Проигрывает короткие звуки для трёх ситуаций:
  • "ai_error"   — два таймаута/ошибки ИИ подряд
  • "test_done"  — тест завершён
  • "error"      — любая другая ошибка (не связана с ИИ)

Громкость каждого звука настраивается в «Настройках вида» (0..100, 0 = выкл).
Громкости берутся из theme._settings (vol_ai_error / vol_test_done / vol_error).

Доп. звуки (без ползунков громкости, играют на полной):
  • 67.wav         — пасхалка: с шансом 1/67 при завершении теста
  • пасхалки лого  — случайный звук при клике по логотипу

Файлы звуков лежат в  res/sounds/.
Если файла нет — соответствующий звук просто молча пропускается.
"""

import random
from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtMultimedia import QSoundEffect

from .theme import _settings


# event_key → (имя файла, ключ громкости в настройках)
_SOUND_MAP = {
    "ai_error":  ("ai_error.wav",  "vol_ai_error"),
    "test_done": ("test_done.wav", "vol_test_done"),
    "error":     ("error.wav",     "vol_error"),
}

# Редкая пасхалка при завершении теста (1 шанс из ZALUPA_CHANCE).
LUCKY_FILE   = "67.wav"
LUCKY_CHANCE = 67

# Пасхалки, играющие в случайном порядке при клике по логотипу.
EASTER_EGG_FILES = [
    "do-you-want-a-bite.wav",
    "here-our-powers-are-all.wav",
    "i-just-slap.wav",
    "lucky-lucky.wav",
    "minute-five-ten-five.wav",
    "let39s-start.wav",
]


class SoundManager:
    """Управляет проигрыванием звуковых уведомлений (QSoundEffect)."""

    def __init__(self):
        self._sounds_dir = Path(__file__).parent.parent / "res" / "sounds"
        self._effects: dict[str, QSoundEffect] = {}
        self._extra: dict[str, QSoundEffect] = {}   # пасхалки по имени файла
        self._egg_order: list[str] = []             # перемешанная очередь пасхалок
        self._load()

    def _make_effect(self, filename: str) -> QSoundEffect | None:
        path = self._sounds_dir / filename
        if not path.exists():
            return None
        try:
            eff = QSoundEffect()
            eff.setSource(QUrl.fromLocalFile(str(path)))
            return eff
        except Exception:
            return None

    def _load(self):
        """Создаёт QSoundEffect для каждого существующего файла звука."""
        for key, (filename, _vol_key) in _SOUND_MAP.items():
            eff = self._make_effect(filename)
            if eff is not None:
                self._effects[key] = eff

        # Доп. звуки (пасхалки + 67) — по имени файла, без ползунков.
        for filename in [LUCKY_FILE, *EASTER_EGG_FILES]:
            eff = self._make_effect(filename)
            if eff is not None:
                self._extra[filename] = eff

    def play(self, event_key: str):
        """Проигрывает звук для события с учётом настроенной громкости.

        Для "test_done" с шансом 1/67 вместо обычного звука играет 67.wav.
        Безопасно вызывать из GUI-потока (через сигнал play_sound).
        """
        # Пасхалка: при завершении теста изредка играем 67.wav
        if event_key == "test_done":
            if random.randint(1, LUCKY_CHANCE) == 1 and LUCKY_FILE in self._extra:
                self._play_extra(LUCKY_FILE, event_key="test_done")
                return

        eff = self._effects.get(event_key)
        if eff is None:
            return
        vol_key = _SOUND_MAP[event_key][1]
        try:
            volume = int(_settings.get(vol_key, 70))
        except Exception:
            volume = 70
        if volume <= 0:
            return  # звук выключен
        eff.setVolume(max(0.0, min(1.0, volume / 100.0)))
        eff.play()

    def _play_extra(self, filename: str, event_key: str | None = None):
        """Проигрывает доп. звук (пасхалку) по имени файла.

        Если задан event_key — берёт громкость из его ползунка, иначе полная.
        """
        eff = self._extra.get(filename)
        if eff is None:
            return
        volume = 100
        if event_key and event_key in _SOUND_MAP:
            try:
                volume = int(_settings.get(_SOUND_MAP[event_key][1], 70))
            except Exception:
                volume = 70
        if volume <= 0:
            return
        eff.setVolume(max(0.0, min(1.0, volume / 100.0)))
        eff.play()

    def play_easter_egg(self):
        """Случайная пасхалка при клике по логотипу.

        Перемешанная очередь без повторов подряд — звуки идут «в случайном
        порядке», но не дублируются, пока не сыграют все.
        """
        available = [f for f in EASTER_EGG_FILES if f in self._extra]
        if not available:
            return
        if not self._egg_order:
            self._egg_order = available[:]
            random.shuffle(self._egg_order)
        filename = self._egg_order.pop()
        self._play_extra(filename)

    def reload(self):
        """Перечитывает файлы звуков (например, после их добавления)."""
        self._effects.clear()
        self._extra.clear()
        self._egg_order.clear()
        self._load()

