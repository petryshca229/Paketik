"""
accounts.py — Хранилище учётных записей Paketik
================================================
Сохраняет профили авторизации в ~/.paketik/accounts.json.
Пароли обфусцируются через XOR+base64 (аналогично лицензионному ключу).
"""

import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional
from license_mgr import _xor_encrypt, _xor_decrypt

logger = logging.getLogger(__name__)

ACCOUNTS_FILE = Path.home() / ".paketik" / "accounts.json"
_SALT_KEY    = b"PaketikAccountsSalt2025"


def _obfuscate(plain: str) -> str:
    """Обфусцирует строку через XOR+base64."""
    return _xor_encrypt(plain, _SALT_KEY)


def _deobfuscate(obf: str) -> str:
    """Деобфусцирует строку."""
    return _xor_decrypt(obf, _SALT_KEY)


class AccountManager:
    """Менеджер профилей авторизации."""

    def __init__(self, path: Optional[str] = None):
        self._path = Path(path) if path else ACCOUNTS_FILE
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._accounts: List[Dict] = []
        self._load()

    # ── Загрузка / сохранение ───────────────────────────────────────────────

    def _load(self):
        try:
            if self._path.exists():
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    self._accounts = raw
                    logger.debug("Загружено %d профилей", len(self._accounts))
        except Exception as exc:
            logger.warning("Не удалось загрузить accounts.json: %s", exc)
            self._accounts = []

    def _save(self):
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._accounts, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            logger.debug("Сохранено %d профилей", len(self._accounts))
        except Exception as exc:
            logger.warning("Не удалось сохранить accounts.json: %s", exc)

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def list_profiles(self) -> List[Dict]:
        """Возвращает список профилей (без паролей)."""
        return [
            {"label": a["label"], "login": a["login"]}
            for a in self._accounts
        ]

    def get_profile(self, label: str) -> Optional[Dict]:
        """Возвращает профиль по label (с расшифрованным паролем)."""
        for a in self._accounts:
            if a.get("label", "").lower() == label.lower():
                return {
                    "label":   a["label"],
                    "login":   a["login"],
                    "password": _deobfuscate(a.get("password_enc", "")),
                }
        return None

    def save_profile(self, label: str, login: str, password: str) -> bool:
        """Сохраняет или обновляет профиль."""
        if not label.strip() or not login.strip():
            return False
        password_enc = _obfuscate(password) if password else ""
        entry = {
            "label":        label.strip(),
            "login":        login.strip(),
            "password_enc": password_enc,
        }
        for i, a in enumerate(self._accounts):
            if a["label"].lower() == label.lower():
                self._accounts[i] = entry
                self._save()
                logger.info("Обновлён профиль: %s", label)
                return True
        self._accounts.append(entry)
        self._save()
        logger.info("Создан профиль: %s", label)
        return True

    def delete_profile(self, label: str) -> bool:
        """Удаляет профиль по label."""
        for i, a in enumerate(self._accounts):
            if a["label"].lower() == label.lower():
                del self._accounts[i]
                self._save()
                logger.info("Удалён профиль: %s", label)
                return True
        return False

    @property
    def labels(self) -> List[str]:
        return [a["label"] for a in self._accounts]


account_manager = AccountManager()