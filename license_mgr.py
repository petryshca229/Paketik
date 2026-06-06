"""
license.py — Система лицензирования Paketik
===============================================
Supabase-активация + локальный cache в ~/.paketik/license.json
"""

import os
import json
import hashlib
import base64
import socket
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)

# ── Пути ────────────────────────────────────────────────────────────────────
LICENSE_FILE = Path(os.path.expanduser("~")) / ".paketik" / "license.json"
_SALT = b"PaketikNodriverSalt2025"

# ── Статический ключ шифрования API-ключа RouterAI ───────────────────────────
# API-ключ RouterAI приходит с Supabase зашифрованным XOR с этим ключом.
# (Тот же ключ, что и в рабочей 4.5 — сервер шифрует именно им.)
_API_ENC_KEY = b"PaketikRouterAI2025SecretKey!"


def _xor_encrypt(data: str, key: bytes) -> str:
    """XOR-шифрование строки. Результат — base64."""
    if not data:
        return ""
    k = (key * (len(data) // len(key) + 1))[:len(data)]
    encrypted = bytes(a ^ b for a, b in zip(data.encode("utf-8"), k))
    return base64.b64encode(encrypted).decode()


def _xor_decrypt(data: str, key: bytes) -> str:
    """Дешифрует XOR-base64 строку."""
    if not data:
        return ""
    try:
        encrypted = base64.b64decode(data.encode())
        k = (key * (len(encrypted) // len(key) + 1))[:len(encrypted)]
        return bytes(a ^ b for a, b in zip(encrypted, k)).decode("utf-8")
    except Exception:
        return ""

DEMO_TOKENS   = 20_000
DEMO_MODEL_ID = "deepseek/deepseek-v4-flash"   # самый дешёвый DeepSeek

# ── Supabase ─────────────────────────────────────────────────────────────────
_SB_URL = "https://ddxdkdpdkfkyhqyebgfp.supabase.co"
_SB_KEY = "sb_publishable_kMAOQ6lm14xQWGbs0J3_ww_ukk1sL2N"

_HDR_R = {
    "apikey":        _SB_KEY,
    "Authorization": f"Bearer {_SB_KEY}",
    "Content-Type":  "application/json",
}
_HDR_W = {
    "apikey":        _SB_KEY,
    "Authorization": f"Bearer {_SB_KEY}",
    "Content-Type":  "application/json",
    "Prefer":        "return=minimal",   # не требуем тело ответа при PATCH
}


def _sb_get(table: str, params: dict) -> list:
    """GET запрос к Supabase REST API."""
    import urllib.request
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(
        f"{_SB_URL}/rest/v1/{table}?{qs}", headers=_HDR_R)
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read().decode())


def _sb_insert(table: str, data: dict) -> bool:
    """INSERT в Supabase REST API."""
    import urllib.request
    payload = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{_SB_URL}/rest/v1/{table}",
        data=payload, headers=_HDR_W, method="POST")
    with urllib.request.urlopen(req, timeout=8) as r:
        return r.status in (200, 201)


def _sb_patch(table: str, params: dict, data: dict) -> bool:
    """PATCH запрос к Supabase REST API. Возвращает True при успехе."""
    import urllib.request
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    payload = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{_SB_URL}/rest/v1/{table}?{qs}",
        data=payload, headers=_HDR_W, method="PATCH")
    with urllib.request.urlopen(req, timeout=8) as r:
        return r.status in (200, 204)


# ── Вспомогательные функции ──────────────────────────────────────────────────

def _obfuscate(key: str) -> str:
    raw = key.encode() + _SALT
    return base64.b64encode(
        hashlib.sha256(raw).digest()[:16] + key.encode()
    ).decode()


def _deobfuscate(data: str) -> str:
    try:
        return base64.b64decode(data.encode())[16:].decode()
    except Exception:
        return ""


def _get_machine_id() -> str:
    """Стабильный HWID: Windows Machine GUID + hostname, SHA-256."""
    parts = []
    try:
        import winreg
        k = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography")
        guid, _ = winreg.QueryValueEx(k, "MachineGuid")
        parts.append(str(guid))
        winreg.CloseKey(k)
    except Exception:
        pass
    try:
        parts.append(socket.gethostname())
    except Exception:
        pass
    raw = "|".join(parts) or "unknown"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


# ── LicenseManager ────────────────────────────────────────────────────────────

class LicenseManager:
    """
    Управляет лицензией: активация (Supabase + offline),
    баланс токенов, тир, выбор модели AI.
    Данные хранятся локально в ~/.paketik/license.json.
    """

    def __init__(self):
        self._data: Dict[str, Any] = {}
        self._api_key: Optional[str] = None   # дешифрованный API-ключ
        LICENSE_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._load()
        # Инициализируем демо при первом запуске (если нет реальной лицензии)
        if not self._data.get("activated") or self._data.get("demo"):
            self._init_demo()

    # ── Свойства активности ──────────────────────────────────────────────────

    @property
    def is_active(self) -> bool:
        if not self._data.get("activated"):
            return False
        expiry = self._data.get("expiry")
        if expiry:                          # None = бессрочная
            try:
                from datetime import timezone as _tz
                exp_dt = datetime.fromisoformat(str(expiry))
                # Снимаем таймзону для честного сравнения даты И времени
                if exp_dt.tzinfo is not None:
                    exp_dt = exp_dt.astimezone(_tz.utc).replace(tzinfo=None)
                if exp_dt < datetime.utcnow():
                    # Срок истёк — если была реальная лицензия, сбрасываем
                    if not self._data.get("demo"):
                        logger.info("Лицензия истекла — переходим в demo")
                        # Сохраняем факт истечения, _init_demo вызовется снаружи
                        self._data["activated"] = False
                        self._save()
                    return False
            except Exception:
                pass
        return True

    @property
    def token_balance(self) -> int:
        return max(0, self._data.get("token_limit", 0)
                      - self._data.get("tokens_used", 0))

    @property
    def tokens_used(self) -> int:
        return self._data.get("tokens_used", 0)

    @property
    def token_limit(self) -> int:
        return self._data.get("token_limit", 0)

    @property
    def expiry_str(self) -> str:
        expiry = self._data.get("expiry")
        if not expiry:
            return "∞"
        try:
            return datetime.fromisoformat(expiry).strftime("%d.%m.%Y")
        except Exception:
            return "∞"

    # ── Тир и модели ─────────────────────────────────────────────────────────

    @property
    def tier(self) -> int:
        """0=Demo, 1=Pro, 2=Ultra, 3=Ultimate."""
        if self._data.get("demo"):
            return 0
        return int(self._data.get("tier", 1))

    @property
    def plan_name(self) -> str:
        if self._data.get("demo"):
            return "Demo"
        from config import TIER_NAMES
        return TIER_NAMES.get(self.tier, "Pro")

    @property
    def plan_color(self) -> str:
        if self._data.get("demo"):
            return "#808090"
        from config import TIER_COLORS
        return TIER_COLORS.get(self.tier, "#5c9cf5")

    @property
    def allowed_models(self) -> list:
        """[(model_id, display_name, rating), ...] для тира/демо."""
        if self._data.get("demo"):
            return [(DEMO_MODEL_ID, "DeepSeek V4 Flash", 3.0)]
        from config import TIER_MODELS
        return TIER_MODELS.get(self.tier, TIER_MODELS[1])

    @property
    def current_model(self) -> str:
        """Последняя выбранная модель AI (persisted)."""
        allowed_ids = [m[0] for m in self.allowed_models]
        sel = self._data.get("selected_model", "")
        return sel if sel in allowed_ids else (allowed_ids[0] if allowed_ids else "")

    def set_model(self, model_id: str):
        if model_id in [m[0] for m in self.allowed_models]:
            self._data["selected_model"] = model_id
            self._save()

    @property
    def license_key(self) -> str:
        raw = self._data.get("_key_enc", "")
        return _deobfuscate(raw) if raw else ""

    @property
    def api_key(self) -> str:
        """
        Возвращает дешифрованный API-ключ RouterAI.
        Ключ приходит с Supabase при наличии активированной лицензии (tier >= 1).
        Хранится зашифрованным в Supabase, расшифровывается локально.
        """
        if self._api_key:
            return self._api_key

        if not self._data.get("activated") or self._data.get("demo"):
            return ""

        enc_api_key = self._data.get("_api_key_enc", "")
        if not enc_api_key:
            # Пробуем получить с Supabase
            self._fetch_api_key_from_server()
            enc_api_key = self._data.get("_api_key_enc", "")

        if enc_api_key:
            # Сервер (Supabase) шифрует API-ключ XOR'ом со статическим ключом —
            # как в рабочей 4.5. Это основной путь.
            decoded = _xor_decrypt(enc_api_key, _API_ENC_KEY)
            if decoded and decoded.startswith("sk-"):
                self._api_key = decoded
            else:
                # Запасной путь: HWID-производный ключ (для возможной новой схемы).
                try:
                    _machine_salt = _get_machine_id().encode() + _SALT
                    _enc_key = hashlib.sha256(_machine_salt).digest()
                    encrypted = base64.b64decode(enc_api_key.encode())
                    k = (_enc_key * (len(encrypted) // len(_enc_key) + 1))[: len(encrypted)]
                    cand = bytes(a ^ b for a, b in zip(encrypted, k)).decode("utf-8")
                    if cand.startswith("sk-"):
                        self._api_key = cand
                    elif decoded:
                        self._api_key = decoded
                except Exception:
                    self._api_key = decoded or ""

        return self._api_key or ""

    def _fetch_api_key_from_server(self):
        """Получает зашифрованный API-ключ с Supabase и сохраняет локально."""
        hwid = _get_machine_id()
        try:
            rows = _sb_get("licenses", {
                "used_by_hwid": f"eq.{hwid}",
                "is_active":    "eq.false",
                "select":        "api_key_enc"
            })
            if rows and rows[0].get("api_key_enc"):
                self._data["_api_key_enc"] = rows[0]["api_key_enc"]
                self._save()
                logger.info("API-ключ загружен с сервера лицензий")
        except Exception as exc:
            logger.debug("Не удалось получить API-ключ с сервера: %s", exc)


    def _init_demo(self):
        """
        Выдаёт 20к демо-токенов при первом запуске.
        Проверяет Supabase — после переутановки повторно НЕ выдаёт.
        """
        hwid = _get_machine_id()
        balance, used = 0, 0
        try:
            rows = _sb_get("devices", {
                "hwid": f"eq.{hwid}",
                "select": "tokens_balance,plan_name,free_given,tokens_used"
            })
            if rows:
                row     = rows[0]
                balance = int(row.get("tokens_balance", 0))
                used    = int(row.get("tokens_used", 0))
                _sb_patch("devices", {"hwid": f"eq.{hwid}"},
                          {"last_seen_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")})
            else:
                _sb_insert("devices", {
                    "hwid":            hwid,
                    "tokens_balance":  DEMO_TOKENS,
                    "tokens_used":     0,
                    "free_given":      True,
                    "plan_name":       "Demo",
                })
                balance, used = DEMO_TOKENS, 0
                logger.info("Demo: новое устройство, выдано %d токенов", DEMO_TOKENS)
        except Exception as exc:
            logger.warning("Demo init offline: %s", exc)
            if self._data.get("demo_given"):
                balance = max(0, DEMO_TOKENS - self._data.get("tokens_used", 0))
                used    = self._data.get("tokens_used", 0)
            else:
                balance, used = DEMO_TOKENS, 0
                self._data["demo_given"] = True

        self._data.update({
            "activated":   True,
            "demo":        True,
            "tier":        0,
            "plan":        "Demo",
            "expiry":      None,
            "token_limit": DEMO_TOKENS,
            "tokens_used": used,
            "hwid":        hwid,
        })
        self._save()


    def peek_key_tier(self, key: str) -> int:
        """Проверить тир ключа без активации. -1 = не найден, 0 = Demo."""
        try:
            rows = _sb_get("licenses", {
                "key": f"eq.{key.strip().upper()}",
                "select": "tier,is_active"
            })
            if rows:
                return int(rows[0].get("tier", 1))
        except Exception:
            pass
        return -1   # не найден — отличаем от tier=0 (Demo)

    def activate(self, key: str) -> Tuple[bool, str]:
        """
        Активировать лицензию по ключу.
        Приоритет: Supabase → offline fallback.
        """
        key = key.strip().upper()
        if not key:
            return False, "Введите лицензионный ключ"

        hwid = _get_machine_id()

        # ── Supabase онлайн ───────────────────────────────────────────
        try:
            rows = _sb_get("licenses", {"key": f"eq.{key}", "select": "*"})

            if not rows:
                return False, "❌ Ключ не найден"

            lic       = rows[0]
            used_hwid = lic.get("used_by_hwid") or ""
            is_active = bool(lic.get("is_active", False))

            # Проверка одноразовости
            if not is_active:
                if used_hwid and used_hwid != hwid:
                    return False, "❌ Ключ уже активирован на другом устройстве"
                elif not used_hwid:
                    return False, "❌ Ключ недействителен"
                # used_hwid == hwid → та же машина, переактивация ОК

            tokens     = int(lic.get("tokens_granted", 100_000))
            tier       = int(lic.get("tier", 1))
            expiry_raw = lic.get("expiry_date")   # NULL в БД → None в Python

            # ⚠ ВАЖНО: used_at передаём как ISO-строку, НЕ "now()" (это не SQL)
            _sb_patch(
                "licenses",
                {"key": f"eq.{key}"},
                {
                    "used_by_hwid": hwid,
                    "used_at":      datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "is_active":    False,
                }
            )

            # tier=0 = demo ключ
            is_demo_key = (tier == 0)
            if is_demo_key:
                plan = "Demo"
            else:
                from config import TIER_NAMES
                plan = TIER_NAMES.get(tier, "Pro")
            tokens_fmt = f"{tokens:,}".replace(",", " ")

            self._data.update({
                "_key_enc":     _obfuscate(key),
                "activated":    True,
                "demo":         is_demo_key,
                "expiry":       expiry_raw,   # None = ∞
                "token_limit":  tokens,
                "tokens_used":  0,
                "tier":         tier,
                "plan":         plan,
                "hwid":         hwid,
                "activated_at": datetime.now().isoformat(),
            })
            self._save()
            logger.info("✅ Активирован tier=%d plan=%s tokens=%d hwid=%s",
                        tier, plan, tokens, hwid)

            # Получаем зашифрованный API-ключ с Supabase
            self._fetch_api_key_from_server()

            return True, f"✅ {plan} Edition активирован! {tokens_fmt} токенов"

        except Exception as exc:
            logger.warning("Supabase недоступен (%s), пробую offline...", exc)

        # ── Offline fallback ──────────────────────────────────────────
        if self._offline_validate(key):
            self._data.update({
                "_key_enc":     _obfuscate(key),
                "activated":    True,
                "expiry":       None,
                "token_limit":  100_000,
                "tokens_used":  0,
                "tier":         1,
                "plan":         "Pro",
                "activated_at": datetime.now().isoformat(),
            })
            self._save()
            return True, "✅ Pro Edition (offline). Токены: 100 000"

        return False, "❌ Неверный ключ"

    def deactivate(self):
        self._data = {}
        self._save()
        logger.info("Лицензия деактивирована")

    # ── Токены ───────────────────────────────────────────────────────────────

    def consume_tokens(self, count: int):
        """Зафиксировать использование токенов (+ синхронизация Supabase в демо)."""
        if count <= 0:
            return
        self._data["tokens_used"] = self._data.get("tokens_used", 0) + count
        self._save()
        # В демо-режиме синхронизируем баланс в Supabase
        if self._data.get("demo"):
            try:
                hwid = self._data.get("hwid") or _get_machine_id()
                _sb_patch("devices", {"hwid": f"eq.{hwid}"}, {
                    "tokens_balance": max(0, self.token_balance),
                    "tokens_used":    self._data.get("tokens_used", 0),
                })
            except Exception:
                pass

    def get_summary(self) -> Dict[str, Any]:
        """Словарь для GUI."""
        return {
            "active":     self.is_active,
            "plan":       self.plan_name,
            "plan_color": self.plan_color,
            "tier":       self.tier,
            "demo":       bool(self._data.get("demo")),
            "expiry":     self.expiry_str,
            "balance":    self.token_balance,
            "used":       self.tokens_used,
            "limit":      self.token_limit,
            "pct_used":   round(
                self.tokens_used / max(self.token_limit, 1) * 100, 1),
        }

    # ── I/O ──────────────────────────────────────────────────────────────────

    def _load(self):
        try:
            if LICENSE_FILE.exists():
                with open(LICENSE_FILE, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                logger.debug("Лицензия загружена из %s", LICENSE_FILE)
        except Exception as exc:
            logger.error("Ошибка загрузки лицензии: %s", exc)
            self._data = {}

    def _save(self):
        try:
            with open(LICENSE_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.error("Ошибка сохранения: %s", exc)

    @staticmethod
    def _offline_validate(key: str) -> bool:
        """
        Валидация оффлайн-ключа: формат XXXX-XXXX-XXXX-XXXX + checksum.
        Не проверяет уникальность — только формат и контрольную сумму.
        """
        key_clean = key.strip().replace("-", "")
        # Формат: ровно 16 hex-символов
        if len(key_clean) != 16:
            return False
        if not all(c in "0123456789ABCDEF" for c in key_clean):
            return False
        # Контрольная сумма: сумма hex-цифр должна быть чётной
        digit_sum = sum(int(c, 16) for c in key_clean)
        return digit_sum % 2 == 0


# Глобальный экземпляр
license_manager = LicenseManager()
