"""
gui.py — Paketik  (fix: dropdown closes on minimize, colored star ratings)
"""

import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox
import customtkinter as ctk
from pathlib import Path
import logging
import subprocess
import math
import json
from typing import Optional, List, Dict
from PIL import Image, ImageTk

import config
from license_mgr import license_manager
from accounts import account_manager
from utils import find_browser_executable, get_user_data_dir, session_stats

logger = logging.getLogger(__name__)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

C_BG      = "#0b0b14"
C_PANEL   = "#10101c"
C_CARD    = "#16162a"
C_BORDER  = "#252540"
C_ACCENT  = "#7c6cf2"
C_ACCENT2 = "#5c9cf5"
C_GREEN   = "#3ddc97"
C_YELLOW  = "#f7c948"
C_RED     = "#e05c5c"
C_TEXT    = "#e8e8f2"
C_MUTED   = "#5a5a7a"
C_LOG_BG  = "#08080f"
GRAD_TOP  = "#1e1248"
GRAD_BOT  = "#0b0b18"

PANEL_W    = 400
LOG_W      = 540
SETTINGS_W = 300

SETTINGS_FILE = Path.home() / ".paketik" / "settings.json"
DEFAULT_SETTINGS = {
    "font_family":    "Segoe UI Semibold",
    "font_size_base": 14,
    "scale":          1.0,
}
FONT_FAMILIES = [
    "Segoe UI Semibold", "Segoe UI", "Calibri",
    "Arial Rounded MT Bold", "Trebuchet MS", "Verdana",
]

# Системные emoji-шрифты — используются для рендеринга смайликов без контурных артефактов
# Segoe UI Emoji — системный шрифт Windows 10/11, правильно рендерит все emoji
# Fallback: Noto Color Emoji (кроссплатформенный) и Apple Color Emoji
_EMOJI_FONTS = [
    "Segoe UI Emoji",
    "Noto Color Emoji",
    "Apple Color Emoji",
    "EmojiOne Color",
]


def _emoji_font(size: int = 12) -> str:
    """Возвращает первый доступный emoji-шрифт с указанным размером."""
    for fam in _EMOJI_FONTS:
        try:
            tkfont.Font(family=fam, size=size)
            return fam
        except Exception:
            pass
    return "Segoe UI Emoji"  # fallback — система сама подставит


def _load_settings() -> dict:
    try:
        if SETTINGS_FILE.exists():
            return {**DEFAULT_SETTINGS, **json.loads(SETTINGS_FILE.read_text())}
    except Exception:
        pass
    return dict(DEFAULT_SETTINGS)


def _save_settings(s: dict):
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2))
    except Exception:
        pass


_settings = _load_settings()


def _font(rel: int = 0, weight="normal") -> ctk.CTkFont:
    """Обычный шрифт для текста БЕЗ emoji."""
    base = max(8, int(_settings["font_size_base"] * _settings["scale"]) + rel)
    for fam in (_settings["font_family"], "Segoe UI", "Arial"):
        try:
            return ctk.CTkFont(family=fam, size=base, weight=weight)
        except Exception:
            pass
    return ctk.CTkFont(size=base, weight=weight)


def _font_emoji(rel: int = 0, weight: str = "normal") -> ctk.CTkFont:
    """
    Шрифт для текста СО СМАЙЛИКАМИ.
    Использует Segoe UI Emoji — правильно рендерит emoji без контурных артефактов.
    На Windows 10/11 это системный шрифт, он есть почти всегда.
    """
    base = max(8, int(_settings["font_size_base"] * _settings["scale"]) + rel)
    # Каскадный поиск первого доступного emoji-шрифта
    for fam in _EMOJI_FONTS:
        try:
            return ctk.CTkFont(family=fam, size=base, weight=weight)
        except Exception:
            pass
    # Fallback: Segoe UI Emoji если ничего не нашли
    try:
        return ctk.CTkFont(family="Segoe UI Emoji", size=base, weight=weight)
    except Exception:
        return ctk.CTkFont(size=base, weight=weight)


def _s(px: int) -> int:
    return max(1, int(px * _settings["scale"]))


def _load_icon(name: str, size=(18, 18)) -> Optional[ctk.CTkImage]:
    try:
        p = Path(__file__).parent / "assets" / name
        if p.exists():
            img = Image.open(p).convert("RGBA").resize(size, Image.LANCZOS)
            return ctk.CTkImage(light_image=img, dark_image=img, size=size)
    except Exception:
        pass
    return None


class GradientFrame(tk.Canvas):
    def __init__(self, master, top: str, bot: str, **kw):
        super().__init__(master, highlightthickness=0, bd=0, **kw)
        self._top, self._bot = top, bot
        self.bind("<Configure>", self._draw)

    def _draw(self, _=None):
        self.delete("g")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 2 or h < 2:
            return
        def h2r(hx):
            hx = hx.lstrip("#")
            return tuple(int(hx[i:i+2], 16) for i in (0, 2, 4))
        r1,g1,b1 = h2r(self._top); r2,g2,b2 = h2r(self._bot)
        steps = min(h, 64)
        for i in range(steps):
            t  = i / max(steps-1, 1)
            y0 = int(i*h/steps); y1 = int((i+1)*h/steps)
            c  = f"#{int(r1+(r2-r1)*t):02x}{int(g1+(g2-g1)*t):02x}{int(b1+(b2-b1)*t):02x}"
            self.create_rectangle(0, y0, w, y1, fill=c, outline=c, tags="g")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Paketik")
        self._log_visible      = False
        self._settings_visible = False
        self._pulse_running    = False
        self._pulse_angle      = 0.0
        self._dot_state        = True
        self._paused           = False
        self._browser_ready    = False
        self._ws_url: Optional[str] = None
        self._agent_thread: Optional[threading.Thread] = None
        self._agent_instance   = None
        self._browser_process: Optional[subprocess.Popen] = None

        self.lbl_stat_q = self.lbl_stat_a = self.lbl_stat_t = None
        self.lbl_stat_bal = self.lbl_stat_e = self.lbl_stat_er = None

        self.var_browser     = ctk.StringVar(value="Chrome")
        self.var_license_key = ctk.StringVar()
        self.var_use_ollama  = ctk.BooleanVar(value=False)
        self.var_status      = ctk.StringVar(value="Готов к работе")
        self.var_font_size   = ctk.IntVar(value=int(_settings["font_size_base"]))
        self.var_font_family = ctk.StringVar(value=_settings["font_family"])

        isz = (_s(18), _s(18))
        self._ico_logo      = _load_icon("logo.png",       (_s(40), _s(40)))
        self._ico_browser   = _load_icon("browser.png",    isz)
        self._ico_play      = _load_icon("play.png",       isz)
        self._ico_pause     = _load_icon("pause.png",      isz)
        self._ico_stop      = _load_icon("stop.png",       isz)
        self._ico_log       = _load_icon("log.png",        (_s(15),_s(15)))
        self._ico_task      = _load_icon("task.png",       (_s(15),_s(15)))
        self._ico_key_green = _load_icon("green_key.png",  (_s(20),_s(20)))
        self._ico_key_red   = _load_icon("red_key.png",    (_s(20),_s(20)))
        self._ico_clock     = _load_icon("sand_clock.png", (_s(15),_s(15)))
        self._ico_stat      = _load_icon("statistic.png",  (_s(15),_s(15)))
        self._ico_gear      = _load_icon("gear.png",       (_s(15),_s(15)))
        # Звёзды 32x32 — автоматически ресайзятся до нужного размера
        _ssz = (_s(15), _s(15))
        self._ico_star_full  = _load_icon("star.png",       _ssz)
        self._ico_star_half  = _load_icon("half_star.png",  _ssz)
        self._ico_star_empty = _load_icon("star_empty.png", _ssz)

        # dropdown state
        self._model_dropdown_win: Optional[ctk.CTkToplevel] = None
        self._model_dropdown_open = False
        self._item_click_pending  = False
        self._outside_click_bind_id = None
        self._star_labels: list = []

        self.after(200, self._set_window_icon)
        self.configure(fg_color=C_BG)
        self.resizable(True, True)
        self.minsize(PANEL_W, 580)
        self.geometry(f"{PANEL_W}x{_s(720)}")

        self._build_ui()
        self._refresh_license_ui()
        self._schedule_stats_update()
        self._animate_dot()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # ── FIX: закрываем dropdown при сворачивании окна ─────────────────
        self.bind("<FocusOut>", self._on_focus_out)
        self.bind("<Unmap>",    self._on_minimize)   # окно свёрнуто


    # ─────────────────────────────────────────────────────────────────────────
    def _set_window_icon(self):
        try:
            p = Path(__file__).parent / "assets" / "logo.png"
            if not p.exists():
                return
            pil_img = Image.open(p).resize((32, 32), Image.LANCZOS).convert("RGBA")
            self._tk_icon_img = ImageTk.PhotoImage(pil_img)
            self.tk.call("wm", "iconphoto", self._w, self._tk_icon_img)
        except Exception as e:
            logger.debug("window icon: %s", e)

    def _recalc_width(self):
        w = PANEL_W
        if self._settings_visible:
            w += SETTINGS_W
        if self._log_visible:
            w += LOG_W
        h = self.winfo_height() or _s(720)
        self.geometry(f"{w}x{h}")
        self.minsize(w, 580)

    # ─────────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1, minsize=PANEL_W)
        self.grid_columnconfigure(1, weight=0)
        self.grid_columnconfigure(2, weight=2)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self._build_left()
        self._build_settings_panel()
        self._build_log_panel()
        self._build_statusbar()

    # ─────────────────────────────────────────────────────────────────────────
    def _build_left(self):
        self._left = ctk.CTkScrollableFrame(
            self, fg_color=C_PANEL, corner_radius=0,
            scrollbar_button_color=C_BORDER,
            scrollbar_button_hover_color=C_ACCENT)
        self._left.grid(row=0, column=0, sticky="nsew")
        self._left.grid_columnconfigure(0, weight=1)
        # add="+" — добавляем обработчик, НЕ заменяя скролл CTkScrollableFrame
        self._left.bind("<MouseWheel>", lambda e: self._on_scroll_close(), add="+")
        self._left.bind("<Button-4>",   lambda e: self._on_scroll_close(), add="+")
        self._left.bind("<Button-5>",   lambda e: self._on_scroll_close(), add="+")
        left = self._left

        # Header
        hdr_wrap = ctk.CTkFrame(left, fg_color="transparent", height=_s(100))
        hdr_wrap.grid(row=0, column=0, sticky="ew")
        hdr_wrap.grid_propagate(False)
        hdr_wrap.grid_columnconfigure(0, weight=1)

        grad = GradientFrame(hdr_wrap, GRAD_TOP, GRAD_BOT, bg=GRAD_BOT)
        grad.place(relx=0, rely=0, relwidth=1, relheight=1)

        hdr = ctk.CTkFrame(hdr_wrap, fg_color="transparent")
        hdr.place(relx=0, rely=0, relwidth=1, relheight=1)
        hdr.grid_columnconfigure(1, weight=1)

        if self._ico_logo:
            ctk.CTkLabel(hdr, image=self._ico_logo, text="", fg_color="transparent",
                         ).grid(row=0, column=0, rowspan=2,
                                padx=(_s(16),_s(10)), pady=_s(18))

        ctk.CTkLabel(hdr, text="Paketik", font=_font(+14,"bold"),
                     text_color=C_ACCENT, fg_color="transparent",
                     ).grid(row=0, column=1, sticky="sw", pady=(_s(20),0))
        self.lbl_subtitle = ctk.CTkLabel(hdr, text="DEMO EDITION",
                     font=_font(-2), text_color="#808090", fg_color="transparent")
        self.lbl_subtitle.grid(row=1, column=1, sticky="nw", pady=(0,_s(16)))

        btn_f = ctk.CTkFrame(hdr, fg_color="transparent")
        btn_f.grid(row=0, column=2, rowspan=2, padx=_s(12), pady=_s(18))

        self.btn_log_toggle = ctk.CTkButton(
            btn_f, text="Лог", image=self._ico_log, command=self._toggle_log,
            width=_s(72), height=_s(28), font=_font(-2),
            fg_color="#1e1e36", hover_color=C_BORDER,
            border_width=1, border_color=C_BORDER, corner_radius=_s(7))
        self.btn_log_toggle.grid(row=0, column=0, pady=(0,_s(4)))

        self.btn_settings_toggle = ctk.CTkButton(
            btn_f, text="⚙ Вид", image=self._ico_gear, command=self._toggle_settings,
            width=_s(72), height=_s(28), font=_font_emoji(-2),
            fg_color="#1e1e36", hover_color=C_BORDER,
            border_width=1, border_color=C_BORDER, corner_radius=_s(7))
        self.btn_settings_toggle.grid(row=1, column=0)

        # Task card
        self._sect(left, 1, "ЗАДАЧА", self._ico_task)
        c1 = self._card(left, 2)
        self.txt_task = ctk.CTkTextbox(
            c1, height=_s(60), corner_radius=_s(8),
            fg_color="#0e0e1c", text_color=C_TEXT,
            font=_font(0), border_width=1, border_color=C_BORDER)
        self.txt_task.grid(row=0, column=0, columnspan=2,
                           sticky="ew", padx=_s(12), pady=_s(12))
        self.txt_task.insert("0.0", "Пройди тест, выбирая правильные ответы.")

        # ── Authorization card ────────────────────────────────────────────────
        self._sect(left, 3, "АВТОРИЗАЦИЯ", self._ico_browser)
        c2a = self._card(left, 4)
        c2a.grid_columnconfigure(0, weight=1)

        def _auth_row(entry: ctk.CTkEntry, row: int, label_text: str, is_password: bool = False):
            ctk.CTkLabel(c2a, text=label_text, font=_font(-1),
                         text_color=C_MUTED, anchor="w").grid(
                row=row, column=0, sticky="w",
                padx=_s(14), pady=(_s(8), _s(2)))
            entry.grid(row=row + 1, column=0, sticky="ew",
                       padx=_s(12), pady=(0, _s(6)))

        self._auth_login = ctk.CTkEntry(
            c2a, placeholder_text="Логин", height=_s(32),
            fg_color="#0e0e1c", border_color=C_BORDER, font=_font(0))
        self._auth_login.bind("<Control-v>", self._paste_to_auth, add=True)
        self._auth_login.bind("<Control-V>", self._paste_to_auth, add=True)
        _auth_row(self._auth_login, 0, "Логин:")

        self._auth_password = ctk.CTkEntry(
            c2a, placeholder_text="Пароль", height=_s(32), show="*",
            fg_color="#0e0e1c", border_color=C_BORDER, font=_font(0))
        self._auth_password.bind("<Control-v>", self._paste_to_auth, add=True)
        self._auth_password.bind("<Control-V>", self._paste_to_auth, add=True)
        _auth_row(self._auth_password, 2, "Пароль:", is_password=True)

        # Profile selector + save/delete buttons row
        self._auth_profile_var = ctk.StringVar(value="Новый профиль")
        self._auth_profiles_combo = ctk.CTkComboBox(
            c2a, variable=self._auth_profile_var,
            values=["Новый профиль"],
            command=self._on_profile_selected,
            height=_s(32), dropdown_font=_font(0),
            fg_color="#0e0e1c", border_color=C_BORDER,
            button_color=C_BORDER, dropdown_fg_color=C_CARD,
            font=_font(0))
        self._auth_profiles_combo.grid(row=6, column=0, sticky="ew",
                                        padx=_s(12), pady=(0, _s(6)))
        self._refresh_profile_combo()

        btn_row = ctk.CTkFrame(c2a, fg_color="transparent")
        btn_row.grid(row=7, column=0, sticky="ew", padx=_s(12), pady=(0, _s(8)))
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)

        self._btn_save_profile = ctk.CTkButton(
            btn_row, text="💾 Сохранить", command=self._save_profile,
            height=_s(32), font=_font_emoji(0),
            fg_color="#1a2e1a", hover_color="#203820",
            border_color="#2d4d2d", border_width=1, corner_radius=_s(8))
        self._btn_save_profile.grid(row=0, column=0, sticky="ew", padx=(0, _s(5)))

        self._btn_del_profile = ctk.CTkButton(
            btn_row, text="🗑 Удалить", command=self._delete_profile,
            height=_s(32), font=_font_emoji(0),
            fg_color="#2e1a1a", hover_color="#382020",
            border_color="#4d2d2d", border_width=1, corner_radius=_s(8),
            state="disabled")
        self._btn_del_profile.grid(row=0, column=1, sticky="ew", padx=(_s(5), 0))

        # License card
        self._sect(left, 5, "ЛИЦЕНЗИЯ", self._ico_clock)
        c3 = self._card(left, 6)
        c3.grid_columnconfigure(0, weight=0)
        c3.grid_columnconfigure(1, weight=1)

        self.lbl_key_icon = ctk.CTkLabel(c3, text="", image=self._ico_key_red, width=_s(26))
        self.lbl_key_icon.grid(row=0, column=0, padx=(_s(14),_s(6)), pady=(_s(14),_s(2)))

        self.lbl_license_status = ctk.CTkLabel(c3, text="Standard Edition",
            font=_font(+2,"bold"), text_color=C_RED, anchor="w")
        self.lbl_license_status.grid(row=0, column=1, sticky="w",
                                     pady=(_s(14),_s(2)), padx=(0,_s(12)))

        self.lbl_expiry = ctk.CTkLabel(c3, text="", font=_font(-2),
                                       text_color=C_MUTED, anchor="w")
        self.lbl_expiry.grid(row=1, column=0, columnspan=2,
                             sticky="w", padx=_s(14), pady=(0,_s(4)))

        self.lbl_token_balance = ctk.CTkLabel(c3, text="—", font=_font(-1),
                                              text_color=C_MUTED, anchor="w")
        self.lbl_token_balance.grid(row=2, column=0, columnspan=2,
                                    sticky="w", padx=_s(14), pady=(0,_s(6)))

        pb_bg = tk.Frame(c3, bg=C_BORDER, height=_s(7))
        pb_bg.grid(row=3, column=0, columnspan=2, sticky="ew",
                   padx=_s(12), pady=(0,_s(10)))
        pb_bg.grid_propagate(False)
        self._pb_fill = tk.Frame(pb_bg, bg=C_ACCENT, height=_s(7))
        self._pb_fill.place(relx=0, rely=0, relheight=1, relwidth=0)

        self.entry_license = ctk.CTkEntry(
            c3, textvariable=self.var_license_key,
            placeholder_text="XXXX-XXXX-XXXX-XXXX", height=_s(36),
            fg_color="#0e0e1c", border_color=C_BORDER, font=_font(0))
        self.entry_license.grid(row=4, column=0, columnspan=2,
                                sticky="ew", padx=_s(12), pady=(0,_s(6)))
        self.entry_license.bind("<Control-v>", self._paste_key, add=True)
        self.entry_license.bind("<Control-V>", self._paste_key, add=True)
        self.entry_license.bind("<Control-KeyPress>", self._paste_key_any, add=True)

        self.btn_activate = ctk.CTkButton(
            c3, text="Активировать", command=self._activate_license,
            height=_s(36), font=_font(0,"bold"),
            fg_color=C_ACCENT, hover_color="#6355d4", corner_radius=_s(8))
        self.btn_activate.grid(row=5, column=0, columnspan=2,
                               sticky="ew", padx=_s(12), pady=(0,_s(6)))

        # Model selector label
        ctk.CTkLabel(c3, text="🤖  Модель AI:", font=_font_emoji(-2),
                     text_color=C_MUTED, anchor="w").grid(
            row=6, column=0, columnspan=2, sticky="w",
            padx=_s(14), pady=(_s(2),0))

        # Model card (clickable)
        model_card = ctk.CTkFrame(c3, fg_color="#0e0e1c",
                                  corner_radius=_s(10),
                                  border_width=1, border_color=C_BORDER)
        model_card.grid(row=7, column=0, columnspan=2,
                        sticky="ew", padx=_s(12), pady=(0,_s(12)))
        model_card.grid_columnconfigure(0, weight=1)
        model_card.grid_columnconfigure(1, weight=0)
        model_card.grid_columnconfigure(2, weight=0)

        self._lbl_model_name = ctk.CTkLabel(
            model_card, text="DeepSeek V3.2", font=_font(0),
            text_color=C_TEXT, anchor="w")
        self._lbl_model_name.grid(row=0, column=0, sticky="ew",
                                   padx=(_s(12), _s(8)), pady=_s(8))

        # ── Звёзды: 5 виджетов — CTkLabel с иконкой или tk.Label с текстом ──
        stars_bg = "#0e0e1c"
        self._star_labels = []
        stars_frame = tk.Frame(model_card, bg=stars_bg, bd=0, highlightthickness=0)
        stars_frame.grid(row=0, column=1, sticky="ns", padx=(0, _s(6)), pady=_s(8))
        _ico_empty = self._ico_star_empty or self._ico_star_full
        for _ in range(5):
            if self._ico_star_full:
                lbl = ctk.CTkLabel(stars_frame,
                                   image=_ico_empty,
                                   text="", fg_color="transparent",
                                   width=_s(15), height=_s(15))
            else:
                lbl = tk.Label(stars_frame, text="★",
                               font=("Segoe UI", _s(12)),
                               bg=stars_bg, fg="#2a2a45", bd=0, padx=0)
            lbl.pack(side="left", padx=_s(1))
            self._star_labels.append(lbl)

        self._lbl_model_arrow = ctk.CTkLabel(
            model_card, text="▼", font=("Segoe UI", _s(10)),
            text_color=C_MUTED, fg_color="transparent")
        self._lbl_model_arrow.grid(row=0, column=2, sticky="ns",
                                    padx=(0, _s(12)), pady=_s(8))

        def _mc_click(e): self._toggle_model_dropdown()
        def _mc_enter(e): model_card.configure(fg_color="#14142a")
        def _mc_leave(e): model_card.configure(fg_color="#0e0e1c")

        for w in [model_card, self._lbl_model_name,
                  self._lbl_model_arrow, stars_frame]:
            w.bind("<Button-1>", _mc_click)
            w.bind("<Enter>",    _mc_enter)
            w.bind("<Leave>",    _mc_leave)
        for lbl in self._star_labels:
            lbl.bind("<Button-1>", _mc_click)

        self._model_card = model_card
        self._refresh_model_selector()

        # Control card
        self._sect(left, 9, "УПРАВЛЕНИЕ", None)
        c4 = self._card(left, 10)
        c4.grid_columnconfigure(0, weight=1)
        c4.grid_columnconfigure(1, weight=1)

        self.btn_start = ctk.CTkButton(
            c4, text="  Запустить браузер", image=self._ico_browser, compound="left",
            command=self._start_step, height=_s(52), font=_font(+2,"bold"),
            fg_color=C_ACCENT2, hover_color="#4a82e0", corner_radius=_s(10))
        self.btn_start.grid(row=0, column=0, columnspan=2,
                            sticky="ew", padx=_s(12), pady=(_s(12),_s(8)))

        self.btn_pause = ctk.CTkButton(
            c4, text="  Пауза", image=self._ico_pause, compound="left",
            command=self._toggle_pause, height=_s(40), font=_font(0),
            fg_color="#1e1808", hover_color="#2e2410",
            border_width=1, border_color="#6a5800",
            state="disabled", corner_radius=_s(8))
        self.btn_pause.grid(row=1, column=0, sticky="ew",
                            padx=(_s(12),_s(5)), pady=(0,_s(12)))

        self.btn_stop = ctk.CTkButton(
            c4, text="  Стоп", image=self._ico_stop, compound="left",
            command=self._stop_agent, height=_s(40), font=_font(0),
            fg_color="#1e0808", hover_color="#2e1010",
            border_width=1, border_color="#6a1800",
            state="disabled", corner_radius=_s(8))
        self.btn_stop.grid(row=1, column=1, sticky="ew",
                           padx=(_s(5),_s(12)), pady=(0,_s(12)))

        # Stats card
        self._sect(left, 11, "СЕССИЯ", self._ico_stat)
        c5 = self._card(left, 12)
        c5.grid_columnconfigure(0, weight=1)
        c5.grid_columnconfigure(1, weight=1)

        stat_defs = [
            ("Вопросов",  "lbl_stat_q",   C_ACCENT),
            ("Действий",  "lbl_stat_a",   C_ACCENT2),
            ("Токенов",   "lbl_stat_t",   C_MUTED),
            ("Остаток",   "lbl_stat_bal", C_GREEN),
            ("Время",     "lbl_stat_e",   C_GREEN),
            ("Ошибок",    "lbl_stat_er",  C_RED),
        ]
        for i, (label, attr, color) in enumerate(stat_defs):
            col, ri = i % 2, i // 2
            cell = ctk.CTkFrame(c5, fg_color="#111124", corner_radius=_s(10),
                                border_width=1, border_color=C_BORDER)
            cell.grid(row=ri, column=col, sticky="nsew",
                      padx=(_s(12) if col==0 else _s(4),
                            _s(4)  if col==0 else _s(12)),
                      pady=_s(4))
            cell.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(cell, text=label, font=_font(-3),
                         text_color=C_MUTED).grid(row=0, column=0, pady=(_s(8),0))
            lbl = ctk.CTkLabel(cell, text="—", font=_font(+5,"bold"), text_color=color)
            lbl.grid(row=1, column=0, pady=(0,_s(8)))
            setattr(self, attr, lbl)

        ctk.CTkLabel(c5, text="", height=_s(8),
                     fg_color="transparent").grid(row=3, column=0, columnspan=2)

    # ─────────────────────────────────────────────────────────────────────────
    def _build_settings_panel(self):
        self._settings_panel = ctk.CTkFrame(
            self, fg_color="#0e0e20", corner_radius=0,
            border_width=1, border_color=C_BORDER)

        hdr = ctk.CTkFrame(self._settings_panel, fg_color="#13132a",
                           height=_s(42), corner_radius=0)
        hdr.pack(fill="x")
        hdr.grid_propagate(False)
        ctk.CTkLabel(hdr, text="⚙  Настройки вида",
                     font=_font_emoji(0,"bold"), text_color=C_ACCENT,
                     ).pack(side="left", padx=_s(14), pady=_s(10))

        body = ctk.CTkFrame(self._settings_panel, fg_color="transparent")
        body.pack(fill="both", padx=_s(14), pady=_s(10))
        body.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(body, text="Размер шрифта", font=_font(-1),
                     text_color=C_MUTED).grid(row=0, column=0, sticky="w",
                                              pady=(_s(8),_s(2)))
        ff = ctk.CTkFrame(body, fg_color="transparent")
        ff.grid(row=1, column=0, sticky="ew")
        ff.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(ff, text="−", width=_s(34), height=_s(34),
                      font=_font(+6,"bold"), fg_color=C_BORDER, hover_color=C_ACCENT,
                      command=lambda: self._adjust_font(-1), corner_radius=_s(8),
                      ).grid(row=0, column=0, padx=(0,_s(6)))

        self.lbl_font_size_val = ctk.CTkLabel(ff, textvariable=self.var_font_size,
                                              font=_font(+4,"bold"), text_color=C_TEXT,
                                              width=_s(36))
        self.lbl_font_size_val.grid(row=0, column=1)

        ctk.CTkButton(ff, text="+", width=_s(34), height=_s(34),
                      font=_font(+6,"bold"), fg_color=C_BORDER, hover_color=C_ACCENT,
                      command=lambda: self._adjust_font(+1), corner_radius=_s(8),
                      ).grid(row=0, column=2, padx=(_s(6),0))

        self.lbl_font_preview = tk.Label(body, text="Aa Бб 0123",
                                         bg=C_CARD, fg=C_TEXT, relief="flat",
                                         bd=0, padx=_s(8), pady=_s(6))
        self.lbl_font_preview.grid(row=2, column=0, sticky="ew",
                                   pady=(_s(6),_s(4)))
        self._update_font_preview()

        ctk.CTkLabel(body, text="Шрифт", font=_font(-1),
                     text_color=C_MUTED).grid(row=3, column=0, sticky="w",
                                              pady=(_s(12),_s(4)))

        list_frame = tk.Frame(body, bg=C_CARD, bd=1, relief="flat",
                              highlightbackground=C_BORDER, highlightthickness=1)
        list_frame.grid(row=4, column=0, sticky="ew", pady=(0,_s(6)))

        self._font_listbox = tk.Listbox(
            list_frame, bg=C_CARD, fg=C_TEXT,
            selectbackground=C_ACCENT, selectforeground="#ffffff",
            activestyle="none", bd=0, highlightthickness=0,
            height=len(FONT_FAMILIES),
            font=("Segoe UI", int(_settings["font_size_base"]*_settings["scale"])-2))
        self._font_listbox.pack(fill="both")

        for i, fam in enumerate(FONT_FAMILIES):
            self._font_listbox.insert(tk.END, f"  {fam}")
            sz = max(9, int(_settings["font_size_base"]*_settings["scale"])-1)
            try:
                self._font_listbox.itemconfigure(i, font=tkfont.Font(family=fam, size=sz))
            except Exception:
                pass
            if fam == _settings["font_family"]:
                self._font_listbox.selection_set(i)
                self._font_listbox.see(i)
        self._font_listbox.bind("<<ListboxSelect>>", self._on_font_select)

        ctk.CTkLabel(body, text="Масштаб", font=_font(-1),
                     text_color=C_MUTED).grid(row=5, column=0, sticky="w",
                                              pady=(_s(12),_s(4)))
        scale_vals = [("80%", 0.8), ("90%", 0.9), ("100%", 1.0),
                      ("110%", 1.1), ("120%", 1.2), ("140%", 1.4)]
        self._scale_btns = []
        sf = ctk.CTkFrame(body, fg_color="transparent")
        sf.grid(row=6, column=0, sticky="ew")

        for idx, (label, val) in enumerate(scale_vals):
            active = abs(val - _settings["scale"]) < 0.05
            btn = ctk.CTkButton(
                sf, text=label, width=_s(52), height=_s(28), font=_font(-2),
                fg_color=C_ACCENT if active else C_BORDER,
                hover_color="#6355d4", corner_radius=_s(6),
                command=lambda v=val: self._set_scale(v))
            btn.grid(row=idx//3, column=idx%3, padx=_s(2), pady=_s(2))
            self._scale_btns.append((btn, val))

        ctk.CTkButton(body, text="Применить (нужен перезапуск)",
                      command=self._apply_settings, height=_s(36),
                      font=_font(0,"bold"), fg_color=C_ACCENT,
                      hover_color="#6355d4", corner_radius=_s(8),
                      ).grid(row=7, column=0, sticky="ew", pady=(_s(14),_s(4)))

        ctk.CTkButton(body, text="Сброс", command=self._reset_settings,
                      height=_s(28), font=_font(-2), fg_color=C_BORDER,
                      hover_color="#3a3a56", corner_radius=_s(8),
                      ).grid(row=8, column=0, sticky="ew", pady=(0,_s(10)))

    # ─────────────────────────────────────────────────────────────────────────
    def _build_log_panel(self):
        self.log_panel = ctk.CTkFrame(self, fg_color=C_LOG_BG, corner_radius=0)
        self.log_panel.grid_columnconfigure(0, weight=1)
        self.log_panel.grid_rowconfigure(1, weight=1)

        hdr = ctk.CTkFrame(self.log_panel, fg_color="#0d0d1e",
                           height=_s(38), corner_radius=0)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hdr, text="[Журнал]  Работа агента",
                     font=_font(0,"bold"), text_color="#7070a0",
                     ).grid(row=0, column=0, sticky="w", padx=_s(14), pady=_s(8))
        ctk.CTkButton(hdr, text="Очистить", command=self._clear_log,
                      width=_s(80), height=_s(24), fg_color=C_CARD,
                      hover_color=C_BORDER, font=_font(-2), corner_radius=_s(6),
                      ).grid(row=0, column=1, padx=_s(10))

        # tk.Text + Scrollbar — для правильного рендеринга emoji
        # CTkTextbox не поддерживает Segoe UI Emoji, tk.Text — поддерживает
        log_scroll = tk.Scrollbar(self.log_panel, bg=C_LOG_BG,
                                  troughcolor=C_BORDER,
                                  activebackground=C_ACCENT)
        log_font_size = max(10, int(12 * _settings["scale"]))
        self.log_box = tk.Text(
            self.log_panel,
            font=tkfont.Font(family="Consolas", size=log_font_size),
            bg=C_LOG_BG, fg="#9090b8",
            wrap="word", bd=0, relief="flat",
            highlightthickness=0, state="disabled",
            padx=_s(8), pady=_s(4),
            yscrollcommand=log_scroll.set,
        )
        log_scroll.config(command=self.log_box.yview)
        self.log_box.grid(row=1, column=0, sticky="nsew")
        log_scroll.grid(row=1, column=1, sticky="ns")

        # Segoe UI рендерит и Cyrillic, и emoji (без контурных артефактов)
        log_font_size = max(11, int(12 * _settings["scale"]))
        self.log_box.configure(font=tkfont.Font(family="Segoe UI", size=log_font_size))

        for line in ["[OK] Paketik готов к работе",
                     f"   Версия: {config.APP_VERSION}",
                     f"   Сайт: {config.TARGET_URL}", "─"*56]:
            self._log_ui(line)

    # ─────────────────────────────────────────────────────────────────────────
    def _build_statusbar(self):
        bar = ctk.CTkFrame(self, height=_s(28), fg_color="#08080f", corner_radius=0)
        bar.grid(row=1, column=0, columnspan=3, sticky="ew")
        bar.grid_columnconfigure(1, weight=1)

        self._dot_canvas = tk.Canvas(bar, width=_s(10), height=_s(10),
                                     bg="#08080f", highlightthickness=0)
        self._dot_canvas.grid(row=0, column=0, padx=(_s(12),_s(4)), pady=_s(9))
        self._dot_id = self._dot_canvas.create_oval(
            1, 1, _s(9), _s(9), fill=C_MUTED, outline="")

        ctk.CTkLabel(bar, textvariable=self.var_status,
                     font=_font(-2), text_color=C_MUTED, anchor="w",
                     ).grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(bar, text="By Kaban4ik",
                     font=_font(-3), text_color="#1e1e30",
                     ).grid(row=0, column=2, sticky="e", padx=_s(12))

    # ─────────────────────────────────────────────────────────────────────────
    def _card(self, parent, row: int) -> ctk.CTkFrame:
        outer = ctk.CTkFrame(parent, fg_color=C_BORDER, corner_radius=_s(14))
        outer.grid(row=row, column=0, sticky="ew",
                   padx=_s(12), pady=(_s(2),_s(6)))
        outer.grid_columnconfigure(0, weight=1)
        inner = ctk.CTkFrame(outer, fg_color=C_CARD, corner_radius=_s(13))
        inner.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
        inner.grid_columnconfigure(0, weight=1)
        inner.grid_columnconfigure(1, weight=1)
        return inner

    def _sect(self, parent, row: int, text: str, icon=None):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid(row=row, column=0, sticky="w", padx=_s(18), pady=(_s(14),_s(2)))
        col = 0
        if icon:
            ctk.CTkLabel(f, image=icon, text="", fg_color="transparent",
                         ).grid(row=0, column=0, padx=(0,_s(6)))
            col = 1
        ctk.CTkLabel(f, text=text, font=_font(-2,"bold"),
                     text_color=C_ACCENT, fg_color="transparent",
                     ).grid(row=0, column=col)

    def _make_rounded_rect(self, canvas):
        def _create(x0, y0, x1, y1, radius, **kw):
            fill = kw.pop("fill", "")
            outline = kw.pop("outline", "")
            width = kw.pop("width", 1)
            pts = [x0+radius,y0, x1-radius,y0, x1,y0, x1,y0+radius,
                   x1,y1-radius, x1,y1, x1-radius,y1, x0+radius,y1,
                   x0,y1, x0,y1-radius, x0,y0+radius, x0,y0]
            return canvas.create_polygon(pts, smooth=True, fill=fill,
                                         outline=outline, width=width, **kw)
        return _create

    # ── Panels toggle ─────────────────────────────────────────────────────────
    def _toggle_log(self):
        self._log_visible = not self._log_visible
        if self._log_visible:
            self.log_panel.grid(row=0, column=2, sticky="nsew")
            self.grid_columnconfigure(2, weight=2, minsize=LOG_W)
            self.btn_log_toggle.configure(text="X Скрыть",
                                          fg_color=C_ACCENT, hover_color="#6355d4")
        else:
            self.log_panel.grid_remove()
            self.grid_columnconfigure(2, weight=0, minsize=0)
            self.btn_log_toggle.configure(text="[Журнал]",
                                          fg_color="#1e1e36", hover_color=C_BORDER)
        self._recalc_width()

    def _toggle_settings(self):
        self._settings_visible = not self._settings_visible
        if self._settings_visible:
            self._settings_panel.grid(row=0, column=1, sticky="nsew")
            self.grid_columnconfigure(1, weight=0, minsize=SETTINGS_W)
            self.update_idletasks()
            self.btn_settings_toggle.configure(fg_color=C_ACCENT,
                                               hover_color="#6355d4")
        else:
            self._settings_panel.grid_remove()
            self.grid_columnconfigure(1, weight=0, minsize=0)
            self.update_idletasks()
            self.btn_settings_toggle.configure(fg_color="#1e1e36",
                                               hover_color=C_BORDER)
        self._recalc_width()

    # ── Font settings ─────────────────────────────────────────────────────────
    def _update_font_preview(self):
        fam  = self.var_font_family.get()
        size = max(9, int(self.var_font_size.get() * _settings["scale"]))
        try:
            self.lbl_font_preview.configure(
                font=tkfont.Font(family=fam, size=size),
                text=f"Aa Бб — {fam} {size}pt\nПривет, Paketik! 123 ABC")
        except Exception:
            self.lbl_font_preview.configure(text=f"{fam} {size}pt\nПривет, Paketik!")

    def _adjust_font(self, delta: int):
        new = max(9, min(26, self.var_font_size.get() + delta))
        self.var_font_size.set(new)
        _settings["font_size_base"] = new
        self._update_font_preview()

    def _on_font_select(self, _=None):
        sel = self._font_listbox.curselection()
        if sel:
            fam = FONT_FAMILIES[sel[0]]
            self.var_font_family.set(fam)
            _settings["font_family"] = fam
            self._update_font_preview()

    def _set_scale(self, val: float):
        _settings["scale"] = val
        for btn, v in self._scale_btns:
            btn.configure(fg_color=C_ACCENT if abs(v-val)<0.05 else C_BORDER)

    def _apply_settings(self):
        _settings["font_size_base"] = self.var_font_size.get()
        _settings["font_family"]    = self.var_font_family.get()
        _save_settings(_settings)
        messagebox.showinfo("Настройки сохранены",
                            "Перезапустите Paketik — изменения вступят в силу.")

    def _reset_settings(self):
        global _settings
        _settings = dict(DEFAULT_SETTINGS)
        _save_settings(_settings)
        self.var_font_size.set(DEFAULT_SETTINGS["font_size_base"])
        self.var_font_family.set(DEFAULT_SETTINGS["font_family"])
        for btn, v in self._scale_btns:
            btn.configure(fg_color=C_ACCENT
                          if abs(v-DEFAULT_SETTINGS["scale"])<0.05 else C_BORDER)
        self._update_font_preview()

    # ── Animations ────────────────────────────────────────────────────────────
    def _animate_dot(self):
        try:
            c = (C_GREEN if self._dot_state else "#1a3a2a") \
                if self._pulse_running else C_MUTED
            self._dot_canvas.itemconfigure(self._dot_id, fill=c)
            self._dot_state = not self._dot_state
        except Exception:
            pass
        self.after(600, self._animate_dot)

    def _pulse_step(self):
        if not self._pulse_running:
            return
        self._pulse_angle = (self._pulse_angle + 0.1) % (2*math.pi)
        t = 0.5 + 0.5*math.sin(self._pulse_angle)
        r = int(0x1a + (0x5c-0x1a)*t)
        g = int(0x6a + (0x9c-0x6a)*t)
        b = int(0x3a + (0xf5-0x3a)*t)
        try:
            self.btn_start.configure(fg_color=f"#{r:02x}{g:02x}{b:02x}")
        except Exception:
            return
        self.after(40, self._pulse_step)

    def _animate_progress(self, pct: float):
        try:
            self._pb_fill.place(relwidth=min(max(pct,0),1))
            if pct < 0.6:
                t = pct/0.6
                r=int(0x3d+(0xf7-0x3d)*t); g=int(0xdc+(0xc9-0xdc)*t); b=int(0x97+(0x48-0x97)*t)
            else:
                t=(pct-0.6)/0.4
                r=int(0xf7+(0xe0-0xf7)*t); g=int(0xc9+(0x5c-0xc9)*t); b=int(0x48+(0x5c-0x48)*t)
            self._pb_fill.configure(bg=f"#{r:02x}{g:02x}{b:02x}")
        except Exception:
            pass

    # ── License ───────────────────────────────────────────────────────────────
    def _paste_key(self, event=None):
        try:
            t = self.clipboard_get()
            if t:
                self.var_license_key.set(t.strip())
        except Exception:
            pass
        return "break"

    def _paste_key_any(self, event):
        if getattr(event, "keycode", 0) == 86:
            return self._paste_key()

    def _activate_license(self):
        if not self.var_license_key.get().strip():
            messagebox.showwarning("Нет ключа", "Введите лицензионный ключ.")
            return
        self.btn_activate.configure(text="Проверка...", state="disabled")
        self.after(100, self._do_activate)

    def _do_activate(self):
        key = self.var_license_key.get().strip()
        try:
            new_tier = license_manager.peek_key_tier(key)
            cur_tier = license_manager.tier if license_manager.is_active else -1
            # new_tier == -1 → ключ не найден (не показываем диалог)
            # new_tier < cur_tier → понижение (показываем, в т.ч. для demo tier=0)
            if new_tier >= 0 and new_tier < cur_tier and license_manager.is_active:
                from config import TIER_NAMES
                if not messagebox.askyesno(
                    "Понижение тира",
                    f"Текущий тир: {TIER_NAMES.get(cur_tier, cur_tier)}\n"
                    f"Новый тир:   {TIER_NAMES.get(new_tier, 'Demo')}\n\n"
                    "Понизить уровень подписки?"):
                    self.btn_activate.configure(text="Активировать", state="normal")
                    return
        except Exception:
            pass
        ok, msg = license_manager.activate(key)
        self._log_ui(f"🔒 {msg}")
        self._refresh_license_ui()
        self.btn_activate.configure(text="Активировать", state="normal")
        (messagebox.showinfo if ok else messagebox.showerror)("Лицензия", msg)

    def _refresh_license_ui(self):
        info = license_manager.get_summary()
        if info["active"]:
            plan  = info.get("plan", "Pro")
            color = info.get("plan_color", C_GREEN)
            self.lbl_license_status.configure(text=f"{plan} Edition", text_color=color)
            self.lbl_key_icon.configure(image=self._ico_key_green)
            self.lbl_expiry.configure(text=f"Действует до: {info['expiry']}",
                                      text_color=C_MUTED)
            bal = f"{info['balance']:,}".replace(",", " ")
            lim = f"{info['limit']:,}".replace(",", " ")
            self.lbl_token_balance.configure(text=f"{bal} / {lim} токенов",
                                             text_color=C_ACCENT2)
            self._animate_progress(info["pct_used"] / 100)
            try:
                self.lbl_subtitle.configure(text=f"{plan} Edition", text_color=color)
            except Exception:
                pass
            self._refresh_model_selector()

    # ── Account management ────────────────────────────────────────────────────

    def _paste_to_auth(self, event=None):
        """Вставляет текст из буфера обмена в поле ввода (login/password)."""
        try:
            clipboard_text = self.clipboard_get()
            if clipboard_text:
                # Вставляем в виджет, который сейчас имеет фокус
                focused = self.focus_get()
                if focused and hasattr(focused, 'insert'):
                    focused.delete(0, "end")
                    focused.insert(0, clipboard_text.strip())
        except Exception:
            pass
        return "break"

    def _refresh_profile_combo(self):
        """Обновляет выпадающий список профилей."""
        labels = ["Новый профиль"] + account_manager.labels
        self._auth_profiles_combo.configure(values=labels)
        current = self._auth_profile_var.get()
        if current not in labels:
            self._auth_profile_var.set("Новый профиль")
            self._on_profile_selected("Новый профиль")

    def _on_profile_selected(self, value: str):
        """При выборе профиля — заполняет поля ввода."""
        if value == "Новый профиль":
            self._auth_login.delete(0, "end")
            self._auth_password.delete(0, "end")
            self._btn_del_profile.configure(state="disabled")
        else:
            profile = account_manager.get_profile(value)
            if profile:
                self._auth_login.delete(0, "end")
                self._auth_login.insert(0, profile["login"])
                self._auth_password.delete(0, "end")
                self._auth_password.insert(0, profile["password"])
                self._btn_del_profile.configure(state="normal")
            else:
                self._btn_del_profile.configure(state="disabled")

    def _save_profile(self):
        label = self._auth_profile_var.get()
        login = self._auth_login.get().strip()
        password = self._auth_password.get()

        if label == "Новый профиль":
            if not login:
                messagebox.showwarning("Ошибка", "Введите логин для сохранения.")
                return
            # Своё окно вместо CTkInputDialog — с логотипом и шрифтом Paketik
            dialog = ctk.CTkInputDialog(
                text="Введите название профиля:", title="Новый профиль")
            dialog.configure(fg_color=C_PANEL)
            try:
                # Подменяем заголовок (CTkInputDialog не имеет set_title, но можно
                # найти и изменить label через children)
                for child in dialog.winfo_children():
                    for sub in child.winfo_children():
                        if isinstance(sub, ctk.CTkLabel):
                            sub.configure(text="Новый профиль", font=_font(0, "bold"),
                                          text_color=C_ACCENT)
            except Exception:
                pass
            new_label = dialog.get_input()
            if not new_label or not new_label.strip():
                return
            label = new_label.strip()
            self._auth_profile_var.set(label)

        if not login:
            messagebox.showwarning("Ошибка", "Введите логин.")
            return

        ok = account_manager.save_profile(label, login, password)
        if ok:
            self._log_ui(f"💾 Профиль «{label}» сохранён")
            self._refresh_profile_combo()
            # Переключаем combo на только что сохранённый профиль
            self._auth_profile_var.set(label)
        else:
            messagebox.showerror("Ошибка", "Не удалось сохранить профиль.")

    def _delete_profile(self):
        label = self._auth_profile_var.get()
        if label == "Новый профиль":
            return
        if not messagebox.askyesno("Удалить профиль",
                                   f"Удалить профиль «{label}»?"):
            return
        account_manager.delete_profile(label)
        self._log_ui(f"🗑 Профиль «{label}» удалён")
        self._auth_profile_var.set("Новый профиль")
        self._on_profile_selected("Новый профиль")
        self._refresh_profile_combo()

    # ── Model selector ────────────────────────────────────────────────────────

    def _refresh_model_selector(self):
        """Обновляет имя и звёзды на плашке текущей модели."""
        try:
            models  = license_manager.allowed_models   # [(id, name, rating), ...]
            cur_id  = license_manager.current_model
            rating  = next((m[2] for m in models if m[0] == cur_id), 3.0)
            name    = next((m[1] for m in models if m[0] == cur_id),
                           models[0][1] if models else "")
            self._lbl_model_name.configure(text=name)
            self._update_star_labels(rating)
        except Exception:
            pass

    def _update_star_labels(self, rating: float):
        """Обновляет 5 звёзд на плашке (PNG-иконки или Unicode-fallback)."""
        full     = int(rating)
        half     = (rating - full) >= 0.4
        use_ico  = bool(self._ico_star_full)
        for i, lbl in enumerate(self._star_labels):
            if i < full:
                ico  = self._ico_star_full
                txt, fg = "★", "#f7c948"
            elif half and i == full:
                ico  = self._ico_star_half or self._ico_star_full
                txt, fg = "✦", "#c48a20"
            else:
                ico  = self._ico_star_empty or self._ico_star_full
                txt, fg = "★", "#2a2a45"
            try:
                if use_ico and ico:
                    lbl.configure(image=ico, text="")
                else:
                    lbl.configure(text=txt, fg=fg)
            except Exception:
                pass

    def _pointer_inside_widget(self, widget) -> bool:
        """Проверяет, находится ли курсор внутри виджета."""
        try:
            if not widget or not widget.winfo_exists():
                return False
            x, y = self.winfo_pointerxy()
            wx, wy = widget.winfo_rootx(), widget.winfo_rooty()
            ww, wh = widget.winfo_width(), widget.winfo_height()
            return wx <= x <= wx + ww and wy <= y <= wy + wh
        except Exception:
            return False

    def _event_from_widget_tree(self, event, root_widget) -> bool:
        """Проверяет, пришёл ли event от root_widget или его потомка."""
        try:
            if not event or not root_widget:
                return False
            w = event.widget
            root_name = str(root_widget)
            while w is not None:
                if str(w) == root_name:
                    return True
                w = getattr(w, "master", None)
        except Exception:
            pass
        return False

    def _bind_model_item_click_recursive(self, widget, callback):
        """Вешает click-handler на сам item и всех его детей."""
        try:
            widget.bind("<ButtonPress-1>", callback)
            widget.bind("<ButtonRelease-1>", lambda e: "break")
        except Exception:
            pass
        try:
            for child in widget.winfo_children():
                self._bind_model_item_click_recursive(child, callback)
        except Exception:
            pass

    def _toggle_model_dropdown(self):
        if self._model_dropdown_open:
            self._close_model_dropdown()
            return

        models = license_manager.allowed_models
        cur_id = license_manager.current_model

        self.update_idletasks()
        cx = self._model_card.winfo_rootx()
        cy = self._model_card.winfo_rooty()
        cw = self._model_card.winfo_width()
        ch = self._model_card.winfo_height()

        ITEM_H     = _s(44)
        PAD_V      = _s(8)
        popup_w    = max(cw, _s(250))
        popup_h    = len(models) * ITEM_H + PAD_V * 2
        BG         = "#131330"
        R          = _s(12)

        popup = ctk.CTkToplevel(self)
        popup.wm_overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.configure(fg_color=BG)
        popup.wm_geometry(f"{popup_w}x{popup_h}+{cx}+{cy + ch}")

        # Canvas background with rounded corners
        cv = tk.Canvas(popup, width=popup_w, height=popup_h,
                       bg=BG, highlightthickness=0, bd=0)
        cv.place(x=0, y=0, relwidth=1, relheight=1)
        cv.create_rounded_rectangle = self._make_rounded_rect(cv)
        cv.create_rounded_rectangle(1, 1, popup_w-1, popup_h-1, R,
                                    fill=BG, outline=C_BORDER, width=1)

        self._model_dropdown_win  = popup
        self._model_dropdown_open = True
        self._lbl_model_arrow.configure(text="▲")

        # ── Строим элементы ─────────────────────────────────────────────────
        for idx, (model_id, name, rating) in enumerate(models):
            is_sel   = (model_id == cur_id)
            item_bg  = "#252550" if is_sel else "#1a1a32"
            hover_bg = "#1e1e44"

            y_pos = PAD_V + idx * ITEM_H
            item  = tk.Frame(popup, bg=item_bg, bd=0, highlightthickness=0)
            item.place(x=2, y=y_pos, width=popup_w-4, height=ITEM_H)

            inner = tk.Frame(item, bg=item_bg, bd=0, highlightthickness=0)
            inner.pack(fill="x", padx=_s(10), expand=True)

            # Галочка у выбранной
            if is_sel:
                tk.Label(inner, text="✓", font=("Segoe UI", _s(11), "bold"),
                         bg=item_bg, fg=C_ACCENT, bd=0).pack(
                    side="left", padx=(0, _s(4)), pady=_s(10))

            # Название
            name_lbl = tk.Label(inner, text=name,
                                font=("Segoe UI", _s(12)),
                                bg=item_bg, fg=C_TEXT, anchor="w", bd=0)
            name_lbl.pack(side="left", fill="x", expand=True, pady=_s(10))

            # ── 5 звёзд: PNG 32x32 или Unicode ──────────────────────────────
            stars_fr = tk.Frame(inner, bg=item_bg, bd=0, highlightthickness=0)
            stars_fr.pack(side="right", padx=(_s(4), _s(2)), pady=_s(10))

            full_s  = int(rating)
            half_s  = (rating - full_s) >= 0.4
            use_ico = bool(self._ico_star_full)
            _psz    = (_s(13), _s(13))

            for si in range(5):
                if si < full_s:
                    ico_src       = self._ico_star_full
                    ch_, col_     = "★", "#f7c948"
                elif half_s and si == full_s:
                    ico_src       = self._ico_star_half or self._ico_star_full
                    ch_, col_     = "✦", "#c48a20"
                else:
                    ico_src       = self._ico_star_empty or self._ico_star_full
                    ch_, col_     = "★", "#2a2a45"

                if use_ico and ico_src:
                    try:
                        resized = ctk.CTkImage(
                            light_image=ico_src._light_image,
                            dark_image=ico_src._dark_image,
                            size=_psz)
                        star_w = ctk.CTkLabel(stars_fr, image=resized, text="",
                                              fg_color="transparent",
                                              width=_psz[0], height=_psz[1])
                        star_w._img_ref = resized
                    except Exception:
                        star_w = tk.Label(stars_fr, text=ch_,
                                          font=("Segoe UI", _s(10)),
                                          bg=item_bg, fg=col_, bd=0)
                else:
                    star_w = tk.Label(stars_fr, text=ch_,
                                      font=("Segoe UI", _s(10)),
                                      bg=item_bg, fg=col_, bd=0)
                star_w.pack(side="left", padx=_s(1))

            # Hover / click
            all_w = [item, inner, name_lbl, stars_fr] + stars_fr.winfo_children()

            def _enter(e, fr=item, inn=inner, sf=stars_fr):
                if fr.cget("bg") != "#252550":
                    for w in [fr, inn, sf] + list(sf.winfo_children()):
                        try: w.configure(bg=hover_bg)
                        except: pass
                    for w in fr.winfo_children():
                        try: w.configure(bg=hover_bg)
                        except: pass

            def _leave(e, fr=item, inn=inner, sf=stars_fr, bg0=item_bg):
                for w in [fr, inn, sf] + list(sf.winfo_children()):
                    try: w.configure(bg=bg0)
                    except: pass
                for w in fr.winfo_children():
                    try: w.configure(bg=bg0)
                    except: pass

            def _click(e, m=model_id, n=name, r=rating):
                self._select_model(m, n, r)
                return "break"

            # Hover оставляем как было
            for w in [item, inner, name_lbl, stars_fr]:
                w.bind("<Enter>", _enter)
                w.bind("<Leave>", _leave)

            for child in list(stars_fr.winfo_children()):
                child.bind("<Enter>", _enter)
                child.bind("<Leave>", _leave)

            # А вот click вешаем рекурсивно на весь пункт и всех детей
            self._bind_model_item_click_recursive(item, _click)
            

        # Закрытие при клике вне.
        # Сохраняем bind id, чтобы потом снять только этот обработчик.
        try:
            if self._outside_click_bind_id:
                self.unbind("<Button-1>", self._outside_click_bind_id)
        except Exception:
            pass

        self._outside_click_bind_id = self.bind(
            "<Button-1>",
            self._on_click_outside_model,
            add="+"
        )

        # FocusOut не закрывает сразу, иначе выбор модели не успевает сработать
        popup.bind("<FocusOut>", self._on_focus_out, add="+")

    # ── FIX: закрытие dropdown при сворачивании / потере фокуса ─────────────

    def _on_minimize(self, event=None):
        """Вызывается при сворачивании главного окна — закрываем dropdown."""
        self._close_model_dropdown()

    def _on_scroll_close(self, event=None):
        """Закрываем dropdown при прокрутке в любом месте приложения."""
        if self._model_dropdown_open:
            self._close_model_dropdown()

    def _on_focus_out(self, event=None):
        """
        Не закрываем dropdown мгновенно.
        При клике по пункту модели главное окно тоже получает FocusOut,
        поэтому даём обработчику выбора модели шанс сработать.
        """
        if not self._model_dropdown_open:
            return
        self.after(120, self._close_model_dropdown_if_outside)

    def _close_model_dropdown_if_outside(self):
        """Закрывает меню только если курсор реально вне dropdown и карточки модели."""
        if not self._model_dropdown_open:
            return
        if self._model_dropdown_win and self._pointer_inside_widget(self._model_dropdown_win):
            return
        if hasattr(self, "_model_card") and self._pointer_inside_widget(self._model_card):
            return
        self._close_model_dropdown()

    def _on_click_outside_model(self, event):
        try:
            if not self._model_dropdown_open:
                return

            if getattr(self, "_item_click_pending", False):
                self._item_click_pending = False
                return

            if self._model_dropdown_win:
                if self._event_from_widget_tree(event, self._model_dropdown_win):
                    return
                if self._pointer_inside_widget(self._model_dropdown_win):
                    return

            if hasattr(self, "_model_card"):
                if self._event_from_widget_tree(event, self._model_card):
                    return
                if self._pointer_inside_widget(self._model_card):
                    return

            self._close_model_dropdown()

        except Exception:
            pass

    def _close_model_dropdown(self):
        self._model_dropdown_open = False

        try:
            self._lbl_model_arrow.configure(text="▼")
        except Exception:
            pass

        try:
            if self._outside_click_bind_id:
                self.unbind("<Button-1>", self._outside_click_bind_id)
                self._outside_click_bind_id = None
        except Exception:
            self._outside_click_bind_id = None

        if self._model_dropdown_win:
            try:
                if self._model_dropdown_win.winfo_exists():
                    self._model_dropdown_win.destroy()
            except Exception:
                pass
            self._model_dropdown_win = None

    def _select_model(self, model_id: str, name: str, rating: float = 3.0):
        self._item_click_pending = True

        try:
            license_manager.set_model(model_id)
        except Exception as e:
            logger.warning("Не удалось сохранить выбранную модель: %s", e)

        try:
            self._lbl_model_name.configure(text=name)
            self._update_star_labels(rating)
        except Exception:
            pass

        self._log_ui(f"🤖 Выбрана модель: {name}")
        self._close_model_dropdown()

    # ── Test selector ─────────────────────────────────────────────────────────
    _selected_test: Optional[Dict] = None
    _test_selector_open = False

    def _show_test_selector(self, tests: List[Dict]):
        """Показывает модальное окно с карточками доступных тестов."""
        if self._test_selector_open:
            return
        self._test_selector_open = True
        self._selected_test = None

        root = ctk.CTkToplevel(self)
        root.title("Выберите тест")
        root.geometry(f"{_s(500)}x{_s(550)}")
        root.configure(fg_color=C_BG)
        root.transient(self)
        root.grab_set()
        root.protocol("WM_DELETE_WINDOW", lambda: self._close_test_selector(root))

        # Заголовок
        hdr = ctk.CTkFrame(root, fg_color=C_PANEL, height=_s(50))
        hdr.pack(fill="x", padx=0, pady=0)
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="Доступные тесты", font=_font(+2, "bold"),
                     text_color=C_ACCENT).pack(pady=_s(12))

        scroll = ctk.CTkScrollableFrame(root, fg_color=C_BG,
                                      scrollbar_button_color=C_BORDER,
                                      scrollbar_button_hover_color=C_ACCENT)
        scroll.pack(fill="both", expand=True, padx=_s(12), pady=_s(8))
        scroll.grid_columnconfigure(0, weight=1)

        for idx, test in enumerate(tests):
            card = ctk.CTkFrame(scroll, fg_color=C_CARD, corner_radius=_s(10),
                               border_width=1, border_color=C_BORDER)
            card.grid(row=idx, column=0, sticky="ew", pady=(_s(4), 0))
            card.grid_columnconfigure(0, weight=1)

            # Название теста
            ctk.CTkLabel(card, text=test.get("name", "—"),
                         font=_font(+1, "bold"), text_color=C_TEXT,
                         anchor="w").grid(row=0, column=0, sticky="ew",
                                         padx=_s(12), pady=(_s(10), _s(2)))

            # Дисциплина
            subj = test.get("subject", "")
            if subj:
                ctk.CTkLabel(card, text=f"Предмет: {subj}", font=_font(-1),
                             text_color=C_MUTED, anchor="w").grid(
                    row=1, column=0, sticky="w",
                    padx=_s(12), pady=(0, _s(2)))

            # Мета-информация
            meta_parts = []
            if test.get("time_limit"):
                meta_parts.append(f"{test['time_limit']}")
            if test.get("questions"):
                meta_parts.append(f"{test['questions']} вопросов")
            if test.get("author"):
                meta_parts.append(f"{test['author']}")
            if test.get("date"):
                meta_parts.append(f"{test['date']}")
            if test.get("status"):
                meta_parts.append(f"{test['status']}")

            if meta_parts:
                meta_text = "   ".join(meta_parts)
                ctk.CTkLabel(card, text=meta_text, font=_font(-2),
                             text_color=C_MUTED, anchor="w").grid(
                    row=2, column=0, sticky="w",
                    padx=_s(12), pady=(0, _s(8)))

            # Кнопка выбора
            btn = ctk.CTkButton(card, text="Выбрать",
                               command=lambda t=test, r=root: self._confirm_test(t, r),
                               height=_s(34), font=_font(0, "bold"),
                               fg_color=C_ACCENT2, hover_color="#4a82e0",
                               corner_radius=_s(8))
            btn.grid(row=3, column=0, sticky="ew",
                     padx=_s(12), pady=(0, _s(10)))

        # Кнопка отмены
        ctk.CTkButton(root, text="Отмена",
                      command=lambda r=root: self._close_test_selector(r),
                      height=_s(36), font=_font(0),
                      fg_color=C_RED, hover_color="#a04040",
                      corner_radius=_s(8)).pack(
            fill="x", padx=_s(12), pady=(_s(6), _s(12)))

        root.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - root.winfo_width()) // 2
        y = self.winfo_y() + (self.winfo_height() - root.winfo_height()) // 2
        root.geometry(f"+{max(0,x)}+{max(0,y)}")
        root.focus()

    def _confirm_test(self, test: Dict, window):
        self._selected_test = test
        self._test_selector_open = False
        window.grab_release()
        window.destroy()
        self._log_ui(f"🎯 Выбран тест: {test.get('name', '?')}")

    def _close_test_selector(self, window):
        self._test_selector_open = False
        window.grab_release()
        window.destroy()

    def _get_selected_test(self) -> Optional[Dict]:
        return self._selected_test

    # ── Browser / Agent ───────────────────────────────────────────────────────
    def _open_browser(self):
        exe = find_browser_executable(self.var_browser.get())
        if not exe:
            messagebox.showerror("Браузер не найден",
                                 f"Не удалось найти {self.var_browser.get()}.")
            return
        try:
            port = 9222
            self._browser_process = subprocess.Popen([
                exe, f"--remote-debugging-port={port}",
                f"--user-data-dir={get_user_data_dir(self.var_browser.get())}",
                "--no-first-run", "--no-default-browser-check", config.TARGET_URL,
            ])
            self._ws_url = f"ws://127.0.0.1:{port}"
            self._log_ui(f"🌐 Браузер запущен ({self.var_browser.get()})")
            self.var_status.set("Браузер открыт — авторизуйтесь, затем нажмите кнопку")
        except Exception as exc:
            messagebox.showerror("Ошибка", f"Не удалось запустить браузер:\n{exc}")

    def _start_step(self):
        if not self._browser_ready:
            self._open_browser()
            if self._ws_url:
                self._browser_ready = True
                self.btn_start.configure(text="  Запустить агента",
                                         image=self._ico_play, hover_color="#2dba7a")
                self._pulse_running = True
                self._pulse_step()
                self.var_status.set("Браузер готов — нажмите «Запустить агента»")
        else:
            self._start_agent()

    def _start_agent(self):
        if not license_manager.is_active:
            messagebox.showwarning("Нет лицензии", "Активируйте лицензию перед запуском.")
            return
        info = license_manager.get_summary()
        if info["balance"] <= 0:
            messagebox.showwarning("Токены исчерпаны",
                                   "Активируйте новый ключ.")
            return
        if info["balance"] < 500:
            if not messagebox.askyesno("Мало токенов",
                                       f"Осталось {info['balance']:,} токенов. Продолжить?"):
                return
        if self._agent_thread and self._agent_thread.is_alive():
            messagebox.showinfo("Уже запущен", "Агент уже работает.")
            return

        self._pulse_running = False
        from agent import TestAgent

        login    = self._auth_login.get().strip()
        password = self._auth_password.get()
        tests_cb = lambda tests: self.after(0, lambda: self._show_test_selector(tests))

        self._agent_instance = TestAgent(
            browser_ws_url     = self._ws_url,
            user_data_dir      = get_user_data_dir(self.var_browser.get())
                                 if not self._ws_url else None,
            browser_executable = find_browser_executable(self.var_browser.get())
                                 if not self._ws_url else None,
            use_ollama         = self.var_use_ollama.get(),
            log_cb             = self._log_ui,
            status_cb          = lambda s: self.after(0, lambda: self.var_status.set(s)),
            task_description   = self.txt_task.get("0.0", "end").strip(),
            login              = login,
            password           = password,
            tests_cb           = tests_cb,
            get_selected_test  = self._get_selected_test,
        )
        self._agent_thread = threading.Thread(
            target=self._agent_instance.start, daemon=True, name="AgentThread")
        self._agent_thread.start()

        self.btn_start.configure(state="disabled", fg_color="#1a1a2e")
        self.btn_pause.configure(state="normal")
        self.btn_stop.configure(state="normal")
        self._pulse_running = True
        self._log_ui("\n[*] Paketik запущен!")
        self.var_status.set("Агент работает...")

    def _toggle_pause(self):
        if not self._agent_instance:
            return
        if not self._paused:
            self._paused = True
            self._agent_instance.pause()
            self.btn_pause.configure(text="  Продолжить", image=self._ico_play,
                                     fg_color="#0a1e10", hover_color="#0e2e18",
                                     border_color=C_GREEN)
            self.var_status.set("Пауза")
        else:
            self._paused = False
            self._agent_instance.resume()
            self.btn_pause.configure(text="  Пауза", image=self._ico_pause,
                                     fg_color="#1e1808", hover_color="#2e2410",
                                     border_color="#6a5800")
            self.var_status.set("Агент работает...")

    def _stop_agent(self):
        if self._agent_instance:
            self._agent_instance.stop()
        self._reset_controls()

    def _reset_controls(self):
        self._pulse_running = False
        self._browser_ready = False
        self._paused = False
        self.btn_start.configure(state="normal", text="  Запустить браузер",
                                 image=self._ico_browser,
                                 fg_color=C_ACCENT2, hover_color="#4a82e0")
        self.btn_pause.configure(state="disabled", text="  Пауза",
                                 image=self._ico_pause,
                                 fg_color="#1e1808", border_color="#6a5800")
        self.btn_stop.configure(state="disabled")
        self.var_status.set("Агент остановлен")

    def _on_close(self):
        self._close_model_dropdown()
        if self._agent_instance:
            self._agent_instance.stop()
        if self._browser_process:
            try: self._browser_process.terminate()
            except Exception: pass
        self.destroy()

    def _clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("0.0", "end")
        self.log_box.configure(state="disabled")

    def _schedule_stats_update(self):
        s    = session_stats
        info = license_manager.get_summary()

        # Проверяем не истёк ли срок лицензии
        if not info["active"] and not info.get("demo"):
            # Лицензия истекла — обновляем UI
            try:
                self._refresh_license_ui()
            except Exception:
                pass
            # Останавливаем агента если работал
            if self._agent_thread and self._agent_thread.is_alive():
                self._log_ui("⚠️ Срок лицензии истёк — агент остановлен.")
                if self._agent_instance:
                    self._agent_instance.stop()
                self._reset_controls()

        if self.lbl_stat_q:
            self.lbl_stat_q.configure(text=str(s.questions_answered))
            self.lbl_stat_a.configure(text=str(s.actions_total))
            self.lbl_stat_t.configure(text=f"{s.tokens_spent:,}")
            self.lbl_stat_bal.configure(text=f"{info['balance']:,}")
            self.lbl_stat_e.configure(text=s.elapsed_str())
            self.lbl_stat_er.configure(text=str(s.errors))
            self._animate_progress(info["pct_used"] / 100)
            self.lbl_token_balance.configure(
                text=f"{info['balance']:,} / {info['limit']:,} токенов"
                if info["active"] else "—")

        if self._agent_thread and not self._agent_thread.is_alive():
            if self.btn_stop.cget("state") == "normal":
                self._reset_controls()

        self.after(2000, self._schedule_stats_update)

    def _log_ui(self, message: str):
        def _do():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", message + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        try:
            self.after(0, _do)
        except RuntimeError:
            pass
