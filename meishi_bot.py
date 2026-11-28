# -*- coding: utf-8 -*-
"""
刷关模拟器 2.1.1 (Flash) - FCBrowser《美食大战老鼠》后台自动闯关助手
特性：
1. 纯后台虚拟鼠标消息（WM_MOUSEMOVE + WM_LBUTTONDOWN/UP + 自动右键取消余卡），完全不抢占真实鼠标。
2. 零闪烁实时后台画面同步（约 7 FPS），可像小窗监视器一样实时观察后台浏览器反馈。
3. 完整的【多卡组管理 & 卡片库保存】（支持保存卡组内每张卡的名称、坐标与自动截取卡片缩略图）。
4. 自由直观的【选卡 -> 放卡位置】可视化布阵编排：
   - 选中卡组里的任意卡片，直接在实时画面上点击场地即可添加放卡点；
   - 实时画面叠加显示带编号与卡名的布阵落点标记；
   - 随时更换某一步点击哪张卡、调整放到哪个坐标、上移/下移顺序、修改间隔与单步开关。
5. 完整闭环：自动选定特定卡组并开战 -> 自动点卡放卡 & 后台扫火苗 -> 识别“继续战斗” -> 战斗结束翻牌收尾。
"""

import ast
import atexit
import base64
import copy
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import tkinter as tk

APP_VERSION = "2.1.1"
UPDATE_REPO = "liuhongbo20080713-bot/meishi---------bot"
UPDATE_BRANCH = "main"


def _parse_version_tuple(ver_str: str) -> tuple:
    nums = [int(x) for x in re.findall(r"\d+", str(ver_str or ""))]
    return tuple(nums) if nums else (0,)


def _build_update_urls(rel_path: str, ref: str = None, cache_bust: bool = False) -> list:
    """生成多条国内直连加速源 + GitHub 原链兜底地址（自动轮询，免梯子也能秒连）"""
    rf = (ref or UPDATE_BRANCH).strip()
    rp = rel_path.lstrip("/")
    qs = f"?t={int(time.time())}" if cache_bust else ""
    raw_url = f"https://raw.githubusercontent.com/{UPDATE_REPO}/{rf}/{rp}"
    return [
        ("ghfast加速源", f"https://ghfast.top/{raw_url}{qs}"),
        ("gh-proxy加速源", f"https://gh-proxy.com/{raw_url}{qs}"),
        ("Fastly-CDN", f"https://fastly.jsdelivr.net/gh/{UPDATE_REPO}@{rf}/{rp}"),
        ("Gcore-CDN", f"https://gcore.jsdelivr.net/gh/{UPDATE_REPO}@{rf}/{rp}"),
        ("jsDelivr-CDN", f"https://cdn.jsdelivr.net/gh/{UPDATE_REPO}@{rf}/{rp}"),
        ("GitHub原链", f"{raw_url}{qs}"),
    ]


def _fetch_from_mirrors(rel_path: str, ref: str = None, expected_sha256: str = "", cache_bust: bool = False, timeout: float = 8.0):
    """依次轮询所有镜像下载文件，若提供 expected_sha256 则自动做完整性校验，返回 (bytes, source_name, err_list)"""
    errs = []
    headers = {
        "User-Agent": f"MeishiBot/{APP_VERSION}",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    for src_name, url in _build_update_urls(rel_path, ref=ref, cache_bust=cache_bust):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if getattr(resp, "status", 200) != 200:
                    errs.append(f"{src_name}: HTTP {resp.status}")
                    continue
                data = resp.read()
            if not data:
                errs.append(f"{src_name}: 空响应")
                continue
            if expected_sha256:
                got = hashlib.sha256(data).hexdigest().lower()
                if got != expected_sha256.strip().lower():
                    errs.append(f"{src_name}: SHA256校验不匹配")
                    continue
            return data, src_name, errs
        except Exception as e:
            errs.append(f"{src_name}: {e}")
    return None, "", errs
from tkinter import ttk, messagebox, simpledialog, filedialog
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageTk
import psutil

# ==================== 1. 开启高分屏 DPI 感知 ====================
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CHAR = 0x0102
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
MK_LBUTTON = 0x0001
MK_RBUTTON = 0x0002
VK_BACK = 0x08
VK_RETURN = 0x0D
VK_END = 0x23
VK_RIGHT = 0x27
VK_DELETE = 0x2E
PW_RENDERFULLCONTENT = 0x00000002
GA_ROOT = 2
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
LWA_ALPHA = 0x00000002
HWND_TOP = 0
HWND_BOTTOM = 1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SW_MAXIMIZE = 3
SW_SHOWNOACTIVATE = 4
SW_SHOW = 5

user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = wintypes.LONG
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
user32.SetWindowLongW.restype = wintypes.LONG
user32.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.COLORREF, wintypes.BYTE, wintypes.DWORD]
user32.SetLayeredWindowAttributes.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.SetWindowPos.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 固定本机用户数据目录：以后无论更新/解压到哪个新版本文件夹，都会自动无缝继承所有卡组、模板、火苗字形与账号！
DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "MeishiBotData")
os.makedirs(DATA_DIR, exist_ok=True)


def _auto_migrate_local_data_to_appdata():
    """首次启用固定本机数据目录时，若 DATA_DIR 尚无配置而当前程序目录已有旧配置，自动无损迁移过去"""
    dst_cfg = os.path.join(DATA_DIR, "meishi_config.json")
    src_cfg = os.path.join(BASE_DIR, "meishi_config.json")
    if os.path.isfile(dst_cfg) or not os.path.isfile(src_cfg):
        return
    try:
        shutil.copy2(src_cfg, dst_cfg)
    except Exception:
        return
    ign = shutil.ignore_patterns("LOCK", "lockfile", "*.tmp", "SingletonLock", "SingletonCookie", "SingletonSocket")
    for sub in ("meishi_templates", "card_icons", "fire_digits", "backups", "ff_profiles"):
        s_sub = os.path.join(BASE_DIR, sub)
        d_sub = os.path.join(DATA_DIR, sub)
        if os.path.isdir(s_sub):
            try:
                shutil.copytree(s_sub, d_sub, dirs_exist_ok=True, ignore=ign)
            except Exception:
                pass


_auto_migrate_local_data_to_appdata()

CONFIG_FILE = os.path.join(DATA_DIR, "meishi_config.json")
TEMPLATE_DIR = os.path.join(DATA_DIR, "meishi_templates")
PROFILE_TPL_ROOT = os.path.join(TEMPLATE_DIR, "profiles")
CARD_ICON_DIR = os.path.join(DATA_DIR, "card_icons")
FIRE_DIGIT_DIR = os.path.join(DATA_DIR, "fire_digits")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
FF_PROFILE_ROOT = os.path.join(DATA_DIR, "ff_profiles")
LOG_FILE = os.path.join(DATA_DIR, "bot_debug.log")
DEFAULT_LOGIN_URL = "https://news.7k7k.com/msdzls/?lt"
os.makedirs(TEMPLATE_DIR, exist_ok=True)
os.makedirs(PROFILE_TPL_ROOT, exist_ok=True)
os.makedirs(CARD_ICON_DIR, exist_ok=True)
os.makedirs(FIRE_DIGIT_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)
os.makedirs(FF_PROFILE_ROOT, exist_ok=True)


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


_crypt32 = ctypes.windll.crypt32
_kernel32 = ctypes.windll.kernel32
_crypt32.CryptProtectData.argtypes = [
    ctypes.POINTER(_DATA_BLOB), wintypes.LPCWSTR, ctypes.POINTER(_DATA_BLOB),
    ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DATA_BLOB),
]
_crypt32.CryptProtectData.restype = wintypes.BOOL
_crypt32.CryptUnprotectData.argtypes = [
    ctypes.POINTER(_DATA_BLOB), ctypes.POINTER(wintypes.LPWSTR), ctypes.POINTER(_DATA_BLOB),
    ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DATA_BLOB),
]
_crypt32.CryptUnprotectData.restype = wintypes.BOOL


def encrypt_secret(plain: str) -> str:
    """使用 Windows 原生 DPAPI 仅对当前本机当前 Windows 用户加密密码（绝不明文落盘）"""
    if not plain:
        return ""
    try:
        raw = plain.encode("utf-8")
        buf = ctypes.create_string_buffer(raw, len(raw))
        in_b = _DATA_BLOB(len(raw), buf)
        out_b = _DATA_BLOB()
        if not _crypt32.CryptProtectData(ctypes.byref(in_b), "MeishiBotCred", None, None, None, 0, ctypes.byref(out_b)):
            return ""
        try:
            data = ctypes.string_at(out_b.pbData, out_b.cbData)
            return "dpapi:" + base64.b64encode(data).decode("ascii")
        finally:
            _kernel32.LocalFree(out_b.pbData)
    except Exception:
        return ""


def decrypt_secret(token: str) -> str:
    """解密由本机 Windows DPAPI 加密保存的密码"""
    if not token:
        return ""
    if not token.startswith("dpapi:"):
        return token
    try:
        raw = base64.b64decode(token[6:])
        buf = ctypes.create_string_buffer(raw, len(raw))
        in_b = _DATA_BLOB(len(raw), buf)
        out_b = _DATA_BLOB()
        if not _crypt32.CryptUnprotectData(ctypes.byref(in_b), None, None, None, None, 0, ctypes.byref(out_b)):
            return ""
        try:
            return ctypes.string_at(out_b.pbData, out_b.cbData).decode("utf-8")
        finally:
            _kernel32.LocalFree(out_b.pbData)
    except Exception:
        return ""


def detect_ffbrowser_exe(saved_path: str = "") -> str:
    """自动查找本机完整版 Flash 浏览器 (FFBrowser.exe) 路径"""
    if saved_path and os.path.isfile(saved_path):
        return saved_path
    try:
        for p in psutil.process_iter(["name", "exe"]):
            if (p.info.get("name") or "").lower() == "ffbrowser.exe":
                exe_p = p.info.get("exe") or ""
                if exe_p and os.path.isfile(exe_p):
                    return exe_p
    except Exception:
        pass
    candidates = [
        r"",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "FlashGameBrowser", "FFBrowser.exe"),
        r"C:\Program Files (x86)\FlashGameBrowser\FFBrowser.exe",
        r"C:\Program Files\FlashGameBrowser\FFBrowser.exe",
        r"D:\FlashGameBrowser\FFBrowser.exe",
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return ""


def _safe_profile_dirname(name: str) -> str:
    clean = re.sub(r'[\\/:*?"<>|]+', "_", (name or "default").strip())
    return clean or "default"

CARD_PALETTE = [
    "#ff7043", "#42a5f5", "#66bb6a", "#ab47bc", "#ffa726",
    "#26c6da", "#ec407a", "#8d6e63", "#26a69a", "#7e57c2",
    "#d4e157", "#ffca28", "#5c6bc0", "#ef5350",
]

# 卡片三层补阵分层（简洁明了，按顺序：基础层 → 辅助层 → 主力层；不补阵则跳过）
CARD_ROLES = [
    ("base",    "🧱基础层", "解决地图种卡限制（如盘子、软糖），补阵第 1 优先"),
    ("support", "⚡辅助层", "提供火苗/增幅/控场（如火盆、坩埚、冰沙），补阵第 2 优先"),
    ("main",    "⚔主力层", "核心输出与不占格主力（如法师蛇、炎凰马、烤串、蜜糖），补阵第 3 优先"),
    ("skip",    "🚫不补阵", "铲子等，第 2 轮起自动跳过绝不误铲"),
]
CARD_ROLE_LABEL = {k: lbl for k, lbl, _ in CARD_ROLES}


def _infer_card_role(card_name: str) -> str:
    n = (card_name or "").strip()
    if "铲" in n:
        return "skip"
    if any(k in n for k in ("盘", "软糖", "荷叶", "棉花糖")):
        return "base"
    if any(k in n for k in ("火盆", "火炉", "坩埚", "冰", "可乐", "布丁", "瓜", "葫芦", "小火")):
        return "support"
    return "main"


def _get_card_role(card: dict) -> str:
    if not card:
        return "main"
    r = card.get("role")
    if r in CARD_ROLE_LABEL:
        return r
    return _infer_card_role(card.get("name", ""))


def _is_card_overlay(card: dict) -> bool:
    if not card:
        return False
    if "overlay" in card:
        return bool(card["overlay"])
    return "蜜糖" in (card.get("name") or "")

# ==================== 1.5 内置护眼多套现代 UI 皮肤（零额外依赖） ====================
THEME_ORDER = ["dark", "warm", "mist"]
UI_THEMES = {
    "dark": {
        "label": "深蓝暗夜",
        "is_dark": True,
        "bg": "#161b26",
        "card": "#1e2636",
        "border": "#2e3b52",
        "fg": "#e2e8f0",
        "muted": "#94a3b8",
        "accent": "#3b82f6",
        "accent_hover": "#2563eb",
        "accent_fg": "#ffffff",
        "btn_bg": "#283347",
        "btn_hover": "#36455e",
        "btn_fg": "#e2e8f0",
        "input_bg": "#121822",
        "input_fg": "#f1f5f9",
        "input_border": "#3a4b68",
        "tab_bg": "#182030",
        "tab_sel_bg": "#2563eb",
        "tab_sel_fg": "#ffffff",
        "tab_fg": "#94a3b8",
        "th_bg": "#243046",
        "th_fg": "#cbd5e1",
        "row_odd": "#1a2232",
        "row_even": "#202a3d",
        "row_sel": "#1d4ed8",
        "row_sel_fg": "#ffffff",
        "canvas_bg": "#10151f",
        "log_bg": "#0f141e",
        "log_fg": "#cbd5e1",
        "log_ts": "#64748b",
        "log_ok": "#4ade80",
        "log_fire": "#fbbf24",
        "log_warn": "#fb923c",
        "log_trophy": "#38bdf8",
        "log_info": "#a5b4fc",
        "fps_fg": "#4ade80",
        "hwnd_fg": "#60a5fa",
        "fire_fg": "#fbbf24",
        "clear_fg": "#38bdf8",
        "prog_fg": "#fb923c",
        "tip_fg": "#4ade80",
        "hero_fg": "#fb923c",
        "start_bg": "#16a34a",
        "stop_bg": "#dc2626",
        "stealth_bg": "#4f46e5",
        "stealth_on_bg": "#ea580c",
        "qbtn_bg": "#283347",
        "qbtn_fg": "#e2e8f0",
        "caption_bgr": 0x00261B16,
        "caption_text_bgr": 0x00F0E8E2,
    },
    "warm": {
        "label": "暖米美食",
        "is_dark": False,
        "bg": "#f4ede3",
        "card": "#fdf8f1",
        "border": "#dfd0bc",
        "fg": "#3d2f24",
        "muted": "#7c6a58",
        "accent": "#d97706",
        "accent_hover": "#b45309",
        "accent_fg": "#ffffff",
        "btn_bg": "#efe4d4",
        "btn_hover": "#e4d4be",
        "btn_fg": "#3d2f24",
        "input_bg": "#ffffff",
        "input_fg": "#3d2f24",
        "input_border": "#cfbda5",
        "tab_bg": "#eadcc9",
        "tab_sel_bg": "#d97706",
        "tab_sel_fg": "#ffffff",
        "tab_fg": "#6d5b49",
        "th_bg": "#efe3d2",
        "th_fg": "#4a3828",
        "row_odd": "#fdf9f3",
        "row_even": "#f6ede1",
        "row_sel": "#d97706",
        "row_sel_fg": "#ffffff",
        "canvas_bg": "#241e18",
        "log_bg": "#241e18",
        "log_fg": "#e7dccb",
        "log_ts": "#a89984",
        "log_ok": "#8ec07c",
        "log_fire": "#fabd2f",
        "log_warn": "#fe8019",
        "log_trophy": "#83a598",
        "log_info": "#d3869b",
        "fps_fg": "#2f855a",
        "hwnd_fg": "#0369a1",
        "fire_fg": "#c2410c",
        "clear_fg": "#15803d",
        "prog_fg": "#c2410c",
        "tip_fg": "#2f855a",
        "hero_fg": "#c2410c",
        "start_bg": "#2f855a",
        "stop_bg": "#c53030",
        "stealth_bg": "#6d597a",
        "stealth_on_bg": "#ea580c",
        "qbtn_bg": "#efe4d4",
        "qbtn_fg": "#3d2f24",
        "caption_bgr": 0x00E3EDF4,
        "caption_text_bgr": 0x00242F3D,
    },
    "mist": {
        "label": "雾蓝极简",
        "is_dark": False,
        "bg": "#edf2f7",
        "card": "#ffffff",
        "border": "#d3deea",
        "fg": "#1e293b",
        "muted": "#64748b",
        "accent": "#0284c7",
        "accent_hover": "#0369a1",
        "accent_fg": "#ffffff",
        "btn_bg": "#e6eef6",
        "btn_hover": "#d6e4f2",
        "btn_fg": "#1e293b",
        "input_bg": "#f8fafc",
        "input_fg": "#1e293b",
        "input_border": "#cbd5e1",
        "tab_bg": "#e2ebf4",
        "tab_sel_bg": "#0284c7",
        "tab_sel_fg": "#ffffff",
        "tab_fg": "#475569",
        "th_bg": "#e9f0f7",
        "th_fg": "#334155",
        "row_odd": "#ffffff",
        "row_even": "#f5f8fc",
        "row_sel": "#0284c7",
        "row_sel_fg": "#ffffff",
        "canvas_bg": "#1c222d",
        "log_bg": "#1b212c",
        "log_fg": "#d8e1ec",
        "log_ts": "#94a3b8",
        "log_ok": "#4ade80",
        "log_fire": "#fbbf24",
        "log_warn": "#fb923c",
        "log_trophy": "#38bdf8",
        "log_info": "#93c5fd",
        "fps_fg": "#16a34a",
        "hwnd_fg": "#0284c7",
        "fire_fg": "#ea580c",
        "clear_fg": "#0369a1",
        "prog_fg": "#ea580c",
        "tip_fg": "#16a34a",
        "hero_fg": "#ea580c",
        "start_bg": "#16a34a",
        "stop_bg": "#dc2626",
        "stealth_bg": "#4f46e5",
        "stealth_on_bg": "#ea580c",
        "qbtn_bg": "#e6eef6",
        "qbtn_fg": "#1e293b",
        "caption_bgr": 0x00F7F2ED,
        "caption_text_bgr": 0x003B291E,
    },
}


def _make_modern_indicators(theme: dict, sz: int = 20):
    """用 4 倍超采样 PIL 绘制高清抗锯齿现代圆角勾选框(✓)与单选圆点(●)，彻底告别 clam 丑蓝叉！"""
    scale = 4
    S = sz * scale
    bg_card = theme["card"]
    in_bg = theme["input_bg"]
    in_bd = theme["input_border"]
    acc = theme["accent"]
    acc_fg = theme["accent_fg"]

    def _chk(checked: bool, hovered: bool):
        im = Image.new("RGBA", (S, S), bg_card)
        d = ImageDraw.Draw(im)
        pad = int(S * 0.08)
        rad = int(S * 0.24)
        bw = max(3, int(S * 0.085))
        if checked:
            d.rounded_rectangle([pad, pad, S - pad, S - pad], radius=rad, fill=acc, outline=acc, width=bw)
            # 画一个精致流畅的白色对勾 ✓
            p1 = (int(S * 0.26), int(S * 0.52))
            p2 = (int(S * 0.43), int(S * 0.70))
            p3 = (int(S * 0.75), int(S * 0.31))
            lw = max(5, int(S * 0.115))
            d.line([p1, p2, p3], fill=acc_fg, width=lw, joint="curve")
            # 端点圆帽润色
            r_cap = lw // 2
            for px, py in (p1, p2, p3):
                d.ellipse([px - r_cap, py - r_cap, px + r_cap, py + r_cap], fill=acc_fg)
        else:
            bd = acc if hovered else in_bd
            d.rounded_rectangle([pad, pad, S - pad, S - pad], radius=rad, fill=in_bg, outline=bd, width=bw)
        return im.resize((sz, sz), Image.Resampling.LANCZOS)

    def _rad(selected: bool, hovered: bool):
        im = Image.new("RGBA", (S, S), bg_card)
        d = ImageDraw.Draw(im)
        pad = int(S * 0.08)
        bw = max(3, int(S * 0.09))
        if selected:
            d.ellipse([pad, pad, S - pad, S - pad], fill=acc, outline=acc, width=bw)
            inner = int(S * 0.31)
            d.ellipse([inner, inner, S - inner, S - inner], fill=acc_fg)
        else:
            bd = acc if hovered else in_bd
            d.ellipse([pad, pad, S - pad, S - pad], fill=in_bg, outline=bd, width=bw)
        return im.resize((sz, sz), Image.Resampling.LANCZOS)

    return {
        "chk_off": _chk(False, False),
        "chk_on": _chk(True, False),
        "chk_hov": _chk(False, True),
        "rad_off": _rad(False, False),
        "rad_on": _rad(True, False),
        "rad_hov": _rad(False, True),
    }


def apply_win11_titlebar(tk_win, theme: dict):
    """同步 Windows 10/11 沉浸式暗色/彩色标题栏（不兼容的系统自动安全忽略）"""
    try:
        tk_win.update_idletasks()
        hwnd = user32.GetParent(tk_win.winfo_id()) or tk_win.winfo_id()
        dwmapi = ctypes.windll.dwmapi
        dark_val = ctypes.c_int(1 if theme.get("is_dark") else 0)
        dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark_val), ctypes.sizeof(dark_val))
        cap_val = ctypes.c_int(int(theme.get("caption_bgr", 0x00261B16)))
        dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(cap_val), ctypes.sizeof(cap_val))
        txt_val = ctypes.c_int(int(theme.get("caption_text_bgr", 0x00F0E8E2)))
        dwmapi.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(txt_val), ctypes.sizeof(txt_val))
    except Exception:
        pass


# ==================== 2. Win32 底层窗口与后台操作封装 ====================
class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


def make_lparam(x: int, y: int) -> int:
    return ((int(y) & 0xFFFF) << 16) | (int(x) & 0xFFFF)


def get_window_text(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def get_class_name(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def get_root_window(hwnd: int) -> int:
    if not hwnd or not user32.IsWindow(hwnd):
        return 0
    return user32.GetAncestor(hwnd, GA_ROOT) or hwnd


def set_window_stealth(root_hwnd: int, enable: bool, orig_state=None):
    """
    一键切换目标顶层窗口的【彻底隐身 + 鼠标穿透】（专攻最大化 Chromium/FFBrowser/FCBrowser GPU DirectComposition！）：
    - 开启时：
      1. 若窗口处于最小化先后台静默展开；
      2. 记录原始坐标 (x, y, w, h)、是否最大化 (WS_MAXIMIZE) 与样式；
      3. 关键修复：先剥离 WS_MAXIMIZE 标志解锁 Windows 最大化位置锁死（但不触发 SW_RESTORE 缩窗！），
         再用原尺寸 (rw, rh) 平滑移至屏幕右下角外侧仅留 2px 接触桌面（坐标 100% 不变，且防 Chromium 休眠！）；
      4. 叠加 WS_EX_LAYERED | WS_EX_TRANSPARENT + alpha=1 + HWND_BOTTOM，连角落 2px 也隐形穿透。
    - 关闭时：瞬间还原尺寸/坐标/最大化状态与不透明样式并前置显示。
    """
    GWL_STYLE = -16
    WS_MAXIMIZE = 0x01000000
    if not root_hwnd or not user32.IsWindow(root_hwnd):
        return False, orig_state
    if enable:
        if user32.IsIconic(root_hwnd):
            user32.ShowWindow(root_hwnd, SW_SHOWNOACTIVATE)
            time.sleep(0.12)
        rl, rt, rr, rb = get_window_rect(root_hwnd)
        rw, rh = max(100, rr - rl), max(100, rb - rt)
        cur_ex = user32.GetWindowLongW(root_hwnd, GWL_EXSTYLE)
        cur_style = user32.GetWindowLongW(root_hwnd, GWL_STYLE)
        was_zoomed = bool(user32.IsZoomed(root_hwnd) or (cur_style & WS_MAXIMIZE))
        saved = (
            {
                "ex": cur_ex,
                "style": cur_style,
                "x": rl,
                "y": rt,
                "w": rw,
                "h": rh,
                "zoomed": was_zoomed,
            }
            if not isinstance(orig_state, dict)
            else orig_state
        )

        # 计算虚拟桌面右下角（兼容单屏与多屏扩展，保留 2px 接触主屏底角防止 Chromium 触发遮挡休眠）
        vx = user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
        vy = user32.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
        vw = user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
        vh = user32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN
        pw = user32.GetSystemMetrics(0)   # SM_CXSCREEN
        ph = user32.GetSystemMetrics(1)   # SM_CYSCREEN
        hide_x = max(pw, vx + vw) - 2
        hide_y = min(ph, vy + vh) - 2

        # 关键：最大化窗口 (WS_MAXIMIZE) 会被 Windows DWM 锁死在屏幕内，SetWindowPos 移不动！
        # 直接剥离 WS_MAXIMIZE 位而不调用 SW_RESTORE，既能解锁移动又能 100% 保持原窗口像素尺寸不变！
        if cur_style & WS_MAXIMIZE:
            user32.SetWindowLongW(root_hwnd, GWL_STYLE, cur_style & (~WS_MAXIMIZE))

        new_ex = cur_ex | WS_EX_LAYERED | WS_EX_TRANSPARENT
        user32.SetWindowLongW(root_hwnd, GWL_EXSTYLE, new_ex)
        user32.SetLayeredWindowAttributes(root_hwnd, 0, 1, LWA_ALPHA)
        user32.SetWindowPos(
            root_hwnd,
            HWND_BOTTOM,
            int(hide_x),
            int(hide_y),
            int(rw),
            int(rh),
            SWP_NOACTIVATE | SWP_FRAMECHANGED,
        )
        # 二次确认：个别 Chromium 窗口首帧会抗拒非最大化移动，补发一次确保移出视野且尺寸不变
        nl, nt, _, _ = get_window_rect(root_hwnd)
        if nl < pw - 100 and nt < ph - 100:
            user32.SetWindowPos(
                root_hwnd,
                HWND_BOTTOM,
                int(hide_x),
                int(hide_y),
                int(rw),
                int(rh),
                SWP_NOACTIVATE | SWP_FRAMECHANGED,
            )
        return True, saved
    else:
        cur_ex = user32.GetWindowLongW(root_hwnd, GWL_EXSTYLE)
        if cur_ex & WS_EX_LAYERED:
            user32.SetLayeredWindowAttributes(root_hwnd, 0, 255, LWA_ALPHA)
        was_zoomed = False
        if isinstance(orig_state, dict):
            restore_ex = orig_state.get("ex", cur_ex) & (~WS_EX_TRANSPARENT)
            rx = int(orig_state.get("x", 0))
            ry = int(orig_state.get("y", 0))
            rw = int(orig_state.get("w", 0))
            rh = int(orig_state.get("h", 0))
            was_zoomed = bool(orig_state.get("zoomed", False))
            if "style" in orig_state:
                user32.SetWindowLongW(root_hwnd, GWL_STYLE, orig_state["style"] & (~WS_MAXIMIZE))
            flags = (SWP_FRAMECHANGED if (rw > 100 and rh > 100) else (SWP_NOSIZE | SWP_FRAMECHANGED))
        else:
            restore_ex = cur_ex & (~WS_EX_TRANSPARENT) & (~WS_EX_LAYERED)
            rx, ry, rw, rh = 0, 0, 0, 0
            flags = SWP_NOMOVE | SWP_NOSIZE | SWP_FRAMECHANGED
        user32.SetWindowLongW(root_hwnd, GWL_EXSTYLE, restore_ex)
        user32.SetWindowPos(root_hwnd, HWND_TOP, rx, ry, rw, rh, flags)
        user32.ShowWindow(root_hwnd, SW_MAXIMIZE if was_zoomed else SW_SHOW)
        return True, None


def get_window_rect(hwnd: int):
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def get_client_offset(hwnd: int):
    wl, wt, _, _ = get_window_rect(hwnd)
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    return pt.x - wl, pt.y - wt


def get_deepest_child_at_screen_point(root_hwnd: int, screen_x: int, screen_y: int) -> int:
    best_hwnd = root_hwnd
    best_area = 999999999
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HWND, wintypes.LPARAM)

    def cb(ch, _):
        nonlocal best_hwnd, best_area
        if user32.IsWindowVisible(ch):
            l, t, r, b = get_window_rect(ch)
            if l <= screen_x <= r and t <= screen_y <= b:
                area = (r - l) * (b - t)
                if area > 1000 and area <= best_area:
                    best_area = area
                    best_hwnd = ch
        return 1

    user32.EnumChildWindows(root_hwnd, WNDENUMPROC(cb), 0)
    return best_hwnd


_NON_GAME_PROCS = (
    "antigravity", "code", "cursor", "windsurf", "explorer", "cmd", "powershell", "pwsh",
    "windowsterminal", "wt", "notepad", "python", "pythonw", "wechat", "weixin",
    "qq", "tim", "dingtalk", "feishu", "clash", "verge", "devenv", "idea", "pycharm",
)


def _is_non_game_proc(pname: str) -> bool:
    pn = (pname or "").lower()
    if not pn:
        return False
    base = pn[:-4] if pn.endswith(".exe") else pn
    return any(base == k or k in base for k in _NON_GAME_PROCS)


def _get_proc_name_by_hwnd(hwnd: int) -> str:
    try:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value:
            return (psutil.Process(pid.value).name() or "").lower()
    except Exception:
        pass
    return ""


def find_fcbrowser_windows(profile_to_name: dict = None):
    """
    智能扫描 FCBrowser / FFBrowser 游戏窗口并按匹配度打分（绝不扫描脚本自身进程）：
    自动从进程 --user-data-dir 参数反查该窗口对应的账号备注名，方便多开一眼区分与一键切换！
    返回: [(hwnd, desc, score, prof_key), ...]
    """
    prof_map = profile_to_name or {}
    pid_names = {}
    pid_prof = {}
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            pid_i = p.info["pid"]
            pname = (p.info["name"] or "").lower()
            pid_names[pid_i] = pname
            if "ffbrowser" in pname or "fcbrowser" in pname:
                for arg in (p.info.get("cmdline") or []):
                    if arg.lower().startswith("--user-data-dir="):
                        udir = arg.split("=", 1)[1].strip().strip('"').rstrip("\\/")
                        pkey = os.path.basename(udir).lower()
                        if pkey:
                            pid_prof[pid_i] = (pkey, prof_map.get(pkey, pkey))
                        break
        except Exception:
            pass

    candidates = []
    my_pid = os.getpid()
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HWND, wintypes.LPARAM)

    def top_cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return 1
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        # 绝不扫描脚本自身进程窗口
        if pid.value == my_pid:
            return 1
        pname = pid_names.get(pid.value, "")
        # 严格过滤 IDE / 编辑器 / 终端 / 聊天软件等非游戏进程（防止标题带“美食/Flash”被误识别或误隐身！）
        if _is_non_game_proc(pname):
            return 1
        pkey, acc_label = pid_prof.get(pid.value, ("", ""))
        title = get_window_text(hwnd)
        cls = get_class_name(hwnd)
        l, t, r, b = get_window_rect(hwnd)
        w, h = r - l, b - t
        is_fcbrowser = ("fcbrowser" in pname) or ("ffbrowser" in pname) or ("fcbrowser" in cls.lower())
        is_flash = "flash" in pname or "flash" in title.lower()
        has_meishi = "美食" in title
        if (is_fcbrowser or is_flash or has_meishi) and w > 200 and h > 200:
            base_score = 0
            if is_fcbrowser:
                base_score += 1000
            elif is_flash:
                base_score += 150
            if has_meishi:
                base_score += 500
            top_score = base_score + min(150, int((w * h) / 25000))
            tag_top = f"[账号:{acc_label}]" if acc_label else "[顶层]"
            candidates.append((hwnd, f"{tag_top} HWND={hwnd} | {title or cls} ({w}x{h})", top_score, pkey))

            def child_cb(ch, __):
                if user32.IsWindowVisible(ch):
                    cl, ct, cr, cb_ = get_window_rect(ch)
                    cw, ch_h = cr - cl, cb_ - ct
                    if cw > 300 and ch_h > 200:
                        c_cls = get_class_name(ch)
                        c_title = get_window_text(ch)
                        c_score = base_score + min(200, int((cw * ch_h) / 20000))
                        if "Chrome_RenderWidgetHostHWND" in c_cls:
                            c_score += 450
                        elif "Flash" in c_cls or "NativeWindow" in c_cls:
                            c_score += 350
                        elif "Chrome_WidgetWin" in c_cls:
                            c_score += 150
                        tag_ch = f"[{acc_label}]" if acc_label else "[子渲染层]"
                        candidates.append(
                            (ch, f"  └─ {tag_ch} HWND={ch} | {c_cls} ({cw}x{ch_h})", c_score, pkey)
                        )
                return 1

            user32.EnumChildWindows(hwnd, WNDENUMPROC(child_cb), 0)
        return 1

    user32.EnumWindows(WNDENUMPROC(top_cb), 0)
    return candidates


def _to_client_xy(hwnd: int, x: int, y: int):
    ox, oy = get_client_offset(hwnd)
    return max(0, int(x) - ox), max(0, int(y) - oy)


def bg_move(hwnd: int, x: int, y: int):
    cx, cy = _to_client_xy(hwnd, x, y)
    user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, make_lparam(cx, cy))


def bg_right_click(hwnd: int, x: int, y: int):
    cx, cy = _to_client_xy(hwnd, x, y)
    lparam = make_lparam(cx, cy)
    user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, lparam)
    time.sleep(0.03)
    user32.PostMessageW(hwnd, WM_RBUTTONDOWN, MK_RBUTTON, lparam)
    time.sleep(0.05)
    user32.PostMessageW(hwnd, WM_RBUTTONUP, 0, lparam)


def bg_click_fast(hwnd: int, x: int, y: int):
    """稳健高速后台左键点击（移动后停留 36ms > 1个Flash渲染帧，确保网格高亮与点击 100% 生效）"""
    cx, cy = _to_client_xy(hwnd, x, y)
    lparam = make_lparam(cx, cy)
    user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, lparam)
    time.sleep(0.036)
    user32.PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
    time.sleep(0.036)
    user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lparam)


def bg_send_vk(hwnd: int, vk: int):
    """纯后台发送单次虚拟按键（带扫描码，兼容 Chromium 渲染层）"""
    scan = user32.MapVirtualKeyW(vk, 0) & 0xFF
    lp_down = 1 | (scan << 16)
    lp_up = 1 | (scan << 16) | (1 << 30) | (1 << 31)
    user32.PostMessageW(hwnd, WM_KEYDOWN, vk, lp_down)
    time.sleep(0.008)
    user32.PostMessageW(hwnd, WM_KEYUP, vk, lp_up)


def bg_clear_and_type(hwnd: int, x: int, y: int, text: str):
    """纯后台点击输入框 -> 清空残留字符(用方向右键替代END绝不滚屏) -> 逐字输入账号/密码"""
    bg_click_fast(hwnd, x, y)
    time.sleep(0.06)
    bg_click_fast(hwnd, x, y)
    time.sleep(0.08)
    for _ in range(18):
        bg_send_vk(hwnd, VK_RIGHT)
    for _ in range(28):
        bg_send_vk(hwnd, VK_BACK)
    for _ in range(12):
        bg_send_vk(hwnd, VK_DELETE)
    time.sleep(0.04)
    for ch in text:
        code = ord(ch)
        scan = user32.MapVirtualKeyW(code, 0) & 0xFF
        lp = 1 | (scan << 16)
        user32.PostMessageW(hwnd, WM_CHAR, code, lp)
        time.sleep(0.025)


def bg_click(hwnd: int, x: int, y: int, right_cancel: bool = False):
    cx, cy = _to_client_xy(hwnd, x, y)
    lparam = make_lparam(cx, cy)
    user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, lparam)
    time.sleep(0.03)
    user32.PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
    time.sleep(0.04)
    user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lparam)
    if right_cancel:
        time.sleep(0.06)
        user32.PostMessageW(hwnd, WM_RBUTTONDOWN, MK_RBUTTON, lparam)
        time.sleep(0.05)
        user32.PostMessageW(hwnd, WM_RBUTTONUP, 0, lparam)


SRCCOPY = 0x00CC0020
COLORONCOLOR = 3


class FastWindowCapturer:
    """
    高速 GDI 缓存截屏器（专为 2K/4K 窗口 30~60 FPS 实时预览优化）：
    1. 复用 GDI MemoryDC / Bitmap 与内存缓冲区，消除每帧 13MB 重复分配；
    2. 首次自动探测并缓存直接抓取 vs 根窗口裁剪模式，避免每帧重复 PrintWindow；
    3. 预览模式直接使用 Windows GDI 硬件加速 StretchBlt 缩放后再拷贝像素（内存拷贝量减少 92%），
       并使用 BGRX 零拷贝直出 RGB，轻松跑到 30~60 FPS！
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._mode_cache = {}  # hwnd -> ("direct" | "root")
        self._src_dc = None
        self._src_bmp = None
        self._src_old = None
        self._src_size = (0, 0)
        self._src_buf = None
        self._src_bmi = None

        self._dst_dc = None
        self._dst_bmp = None
        self._dst_old = None
        self._dst_size = (0, 0)
        self._dst_buf = None
        self._dst_bmi = None

    def _make_bmi(self, w: int, h: int):
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0
        return bmi

    def _ensure_src(self, ref_dc, w: int, h: int):
        if self._src_size != (w, h) or not self._src_dc:
            if self._src_dc:
                gdi32.SelectObject(self._src_dc, self._src_old)
                gdi32.DeleteObject(self._src_bmp)
                gdi32.DeleteDC(self._src_dc)
            self._src_dc = gdi32.CreateCompatibleDC(ref_dc)
            self._src_bmp = gdi32.CreateCompatibleBitmap(ref_dc, w, h)
            self._src_old = gdi32.SelectObject(self._src_dc, self._src_bmp)
            self._src_size = (w, h)
            self._src_buf = None
            self._src_bmi = self._make_bmi(w, h)

    def _ensure_dst(self, ref_dc, w: int, h: int):
        if self._dst_size != (w, h) or not self._dst_dc:
            if self._dst_dc:
                gdi32.SelectObject(self._dst_dc, self._dst_old)
                gdi32.DeleteObject(self._dst_bmp)
                gdi32.DeleteDC(self._dst_dc)
            self._dst_dc = gdi32.CreateCompatibleDC(ref_dc)
            self._dst_bmp = gdi32.CreateCompatibleBitmap(ref_dc, w, h)
            self._dst_old = gdi32.SelectObject(self._dst_dc, self._dst_bmp)
            gdi32.SetStretchBltMode(self._dst_dc, COLORONCOLOR)
            self._dst_size = (w, h)
            self._dst_buf = ctypes.create_string_buffer(w * h * 4)
            self._dst_bmi = self._make_bmi(w, h)

    def _probe_and_print(self, hwnd: int):
        """执行 PrintWindow 到 _src_dc，返回 (cap_hwnd, crop_l, crop_t, target_w, target_h) 或 None"""
        l, t, r, b = get_window_rect(hwnd)
        w, h = r - l, b - t
        if w <= 10 or h <= 10:
            return None

        mode = self._mode_cache.get(hwnd)
        if mode is None:
            # 首次探测 direct 模式是否有效（抽样检查防全黑）
            hdc = user32.GetWindowDC(hwnd)
            if not hdc:
                return None
            try:
                self._ensure_src(hdc, w, h)
                ok = user32.PrintWindow(hwnd, self._src_dc, PW_RENDERFULLCONTENT)
                if ok:
                    self._ensure_dst(hdc, 64, 64)
                    gdi32.StretchBlt(self._dst_dc, 0, 0, 64, 64, self._src_dc, 0, 0, w, h, SRCCOPY)
                    gdi32.GetDIBits(self._dst_dc, self._dst_bmp, 0, 64, self._dst_buf, ctypes.byref(self._dst_bmi), 0)
                    sample = np.frombuffer(self._dst_buf, dtype=np.uint8)
                    if float(sample.std()) > 3.0:
                        self._mode_cache[hwnd] = "direct"
                        return hwnd, 0, 0, w, h
            finally:
                user32.ReleaseDC(hwnd, hdc)

            root_hwnd = user32.GetAncestor(hwnd, GA_ROOT)
            if root_hwnd and root_hwnd != hwnd:
                self._mode_cache[hwnd] = "root"
                mode = "root"
            else:
                self._mode_cache[hwnd] = "direct"
                mode = "direct"

        if mode == "root":
            root_hwnd = user32.GetAncestor(hwnd, GA_ROOT)
            if not root_hwnd or not user32.IsWindow(root_hwnd):
                self._mode_cache.pop(hwnd, None)
                return None
            rl, rt, rr, rb = get_window_rect(root_hwnd)
            rw, rh = rr - rl, rb - rt
            if rw <= 10 or rh <= 10:
                return None
            hdc = user32.GetWindowDC(root_hwnd)
            if not hdc:
                return None
            try:
                self._ensure_src(hdc, rw, rh)
                ok = user32.PrintWindow(root_hwnd, self._src_dc, PW_RENDERFULLCONTENT)
            finally:
                user32.ReleaseDC(root_hwnd, hdc)
            if not ok:
                return None
            crop_l = max(0, l - rl)
            crop_t = max(0, t - rt)
            cw = min(w, rw - crop_l)
            ch = min(h, rh - crop_t)
            if cw <= 10 or ch <= 10:
                return None
            return root_hwnd, crop_l, crop_t, cw, ch
        else:
            hdc = user32.GetWindowDC(hwnd)
            if not hdc:
                return None
            try:
                self._ensure_src(hdc, w, h)
                ok = user32.PrintWindow(hwnd, self._src_dc, PW_RENDERFULLCONTENT)
            finally:
                user32.ReleaseDC(hwnd, hdc)
            if not ok:
                return None
            return hwnd, 0, 0, w, h

    def capture_preview(self, hwnd: int, max_w: int, max_h: int, view_crop=None):
        """极速预览截图：GDI 硬件裁剪+缩放直出目标画布尺寸 RGB 图像（支持零开销裁去左右网页白边）"""
        if not hwnd or not user32.IsWindow(hwnd):
            return None
        with self._lock:
            res = self._probe_and_print(hwnd)
            if not res:
                return None
            cap_hwnd, crop_l, crop_t, tw, th = res
            vox, voy, vw, vh = 0, 0, tw, th
            if view_crop and len(view_crop) == 4:
                cx0, cy0, cx1, cy1 = [int(v) for v in view_crop]
                cx0 = max(0, min(tw - 100, cx0))
                cy0 = max(0, min(th - 100, cy0))
                cx1 = max(cx0 + 100, min(tw, cx1))
                cy1 = max(cy0 + 100, min(th, cy1))
                if (cx1 - cx0) >= 100 and (cy1 - cy0) >= 100:
                    vox, voy, vw, vh = cx0, cy0, cx1 - cx0, cy1 - cy0

            scale = min(max_w / vw, max_h / vh)
            dw = max(2, int(vw * scale))
            dh = max(2, int(vh * scale))

            hdc = user32.GetWindowDC(cap_hwnd)
            if not hdc:
                return None
            try:
                self._ensure_dst(hdc, dw, dh)
                gdi32.StretchBlt(
                    self._dst_dc, 0, 0, dw, dh,
                    self._src_dc, crop_l + vox, crop_t + voy, vw, vh,
                    SRCCOPY,
                )
                gdi32.GetDIBits(self._dst_dc, self._dst_bmp, 0, dh, self._dst_buf, ctypes.byref(self._dst_bmi), 0)
            finally:
                user32.ReleaseDC(cap_hwnd, hdc)

            img = Image.frombuffer("RGB", (dw, dh), self._dst_buf, "raw", "BGRX", 0, 1).copy()
            return img, tw, th, scale, vox, voy

    def capture_roi(self, hwnd: int, x0: int, y0: int, x1: int, y1: int):
        """极速截取一个小区域（如火苗数字框），仅拷贝十几 KB，几乎零耗时"""
        if not hwnd or not user32.IsWindow(hwnd):
            return None
        rw = int(x1 - x0)
        rh = int(y1 - y0)
        if rw < 6 or rh < 6:
            return None
        with self._lock:
            res = self._probe_and_print(hwnd)
            if not res:
                return None
            cap_hwnd, crop_l, crop_t, tw, th = res
            sx = crop_l + max(0, int(x0))
            sy = crop_t + max(0, int(y0))
            rw = min(rw, tw - max(0, int(x0)))
            rh = min(rh, th - max(0, int(y0)))
            if rw < 6 or rh < 6:
                return None
            hdc = user32.GetWindowDC(cap_hwnd)
            if not hdc:
                return None
            try:
                tmp_dc = gdi32.CreateCompatibleDC(hdc)
                tmp_bmp = gdi32.CreateCompatibleBitmap(hdc, rw, rh)
                old_b = gdi32.SelectObject(tmp_dc, tmp_bmp)
                gdi32.BitBlt(tmp_dc, 0, 0, rw, rh, self._src_dc, sx, sy, SRCCOPY)
                bmi = self._make_bmi(rw, rh)
                buf = ctypes.create_string_buffer(rw * rh * 4)
                gdi32.GetDIBits(tmp_dc, tmp_bmp, 0, rh, buf, ctypes.byref(bmi), 0)
                gdi32.SelectObject(tmp_dc, old_b)
                gdi32.DeleteObject(tmp_bmp)
                gdi32.DeleteDC(tmp_dc)
            finally:
                user32.ReleaseDC(cap_hwnd, hdc)
            return Image.frombuffer("RGB", (rw, rh), buf, "raw", "BGRX", 0, 1).copy()

    def capture_full(self, hwnd: int):
        """原始全分辨率后台截图（用于模板识图、框选按钮、裁剪卡图和保存给 AI）"""
        if not hwnd or not user32.IsWindow(hwnd):
            return None
        with self._lock:
            res = self._probe_and_print(hwnd)
            if not res:
                return None
            _, crop_l, crop_t, tw, th = res
            sw, sh = self._src_size
            if self._src_buf is None or len(self._src_buf) != sw * sh * 4:
                self._src_buf = ctypes.create_string_buffer(sw * sh * 4)
            gdi32.GetDIBits(self._src_dc, self._src_bmp, 0, sh, self._src_buf, ctypes.byref(self._src_bmi), 0)
            full_img = Image.frombuffer("RGB", (sw, sh), self._src_buf, "raw", "BGRX", 0, 1).copy()
            if crop_l == 0 and crop_t == 0 and tw == sw and th == sh:
                return full_img
            return full_img.crop((crop_l, crop_t, crop_l + tw, crop_t + th))

    def reset_cache(self, hwnd: int = None):
        with self._lock:
            if hwnd is None:
                self._mode_cache.clear()
            else:
                self._mode_cache.pop(hwnd, None)

    def close(self):
        with self._lock:
            if self._src_dc:
                gdi32.SelectObject(self._src_dc, self._src_old)
                gdi32.DeleteObject(self._src_bmp)
                gdi32.DeleteDC(self._src_dc)
                self._src_dc = None
            if self._dst_dc:
                gdi32.SelectObject(self._dst_dc, self._dst_old)
                gdi32.DeleteObject(self._dst_bmp)
                gdi32.DeleteDC(self._dst_dc)
                self._dst_dc = None


CAPTURER = FastWindowCapturer()


def auto_detect_game_viewport(img: Image.Image):
    """
    自动识别 Flash 游戏主体画面边界，裁去左右/底部多余的纯色浏览器网页背景（自动忽略边缘桌宠/挂件）。
    仅用于美化预览画面显示，不改变任何已保存的游戏坐标！
    """
    if img is None:
        return None
    rgb = img.convert("RGB")
    w, h = rgb.size
    if w < 400 or h < 300:
        return None
    s = min(1.0, 640.0 / w)
    sw, sh = max(160, int(w * s)), max(120, int(h * s))
    arr = np.asarray(rgb.resize((sw, sh), Image.Resampling.BILINEAR), dtype=np.float32)

    samples = np.vstack([
        arr[int(sh * 0.15):int(sh * 0.85), 2, :],
        arr[int(sh * 0.15):int(sh * 0.85), sw - 3, :],
        arr[sh - 3, int(sw * 0.2):int(sw * 0.8), :],
    ])
    bg = np.median(samples, axis=0)
    diff = np.abs(arr - bg).mean(axis=2)

    def _longest_run(mask):
        best = (0, len(mask) - 1)
        best_len = 0
        cur_start = None
        for idx, val in enumerate(mask):
            if val and cur_start is None:
                cur_start = idx
            elif not val and cur_start is not None:
                if idx - cur_start > best_len:
                    best_len = idx - cur_start
                    best = (cur_start, idx - 1)
                cur_start = None
        if cur_start is not None and (len(mask) - cur_start) > best_len:
            best_len = len(mask) - cur_start
            best = (cur_start, len(mask) - 1)
        return best, best_len

    best_x, xlen = _longest_run((diff > 18.0).mean(axis=0) > 0.55)
    if xlen < sw * 0.45:
        return None

    sub_diff = diff[:, best_x[0]:best_x[1] + 1]
    best_y, ylen = _longest_run((sub_diff > 18.0).mean(axis=1) > 0.55)
    if ylen < sh * 0.45:
        return None

    vx0 = max(0, int(round(best_x[0] / s)))
    vx1 = min(w, int(round((best_x[1] + 1) / s)))
    vy0 = max(0, int(round(best_y[0] / s)))
    vy1 = min(h, int(round((best_y[1] + 1) / s)))
    if (vx1 - vx0) > w * 0.97 and (vy1 - vy0) > h * 0.97:
        return None
    return [vx0, vy0, vx1, vy1]


def capture_window_bg(hwnd: int):
    return CAPTURER.capture_full(hwnd)


# ==================== 3. 纯 NumPy FFT 高速零爆内存模板匹配 ====================
def match_template_numpy(screen_img: Image.Image, template_path: str, threshold: float = 0.85):
    """
    基于 2D FFT + 积分图的精确归一化互相关 (NCC) 模板匹配：
    - 无论模板多大、屏幕多高分辨率 (2K/4K)，内存占用恒定 < 20MB，绝不爆内存；
    - 2K 全屏匹配耗时仅约 20~35ms，数学结果与 OpenCV TM_CCOEFF_NORMED 完全等价！
    """
    if not os.path.exists(template_path) or screen_img is None:
        return False, 0, 0, 0.0
    try:
        tpl_img = Image.open(template_path).convert("RGB")
    except Exception:
        return False, 0, 0, 0.0

    sw, sh = screen_img.size
    tw, th = tpl_img.size
    if tw > sw or th > sh or tw < 4 or th < 4:
        return False, 0, 0, 0.0

    # 2倍下采样加速（2560x1342 -> 1280x671），既快又精准
    step = 2 if (tw >= 16 and th >= 16 and sw >= 800) else 1
    s_arr = np.asarray(screen_img.convert("L"), dtype=np.float32)[::step, ::step]
    t_arr = np.asarray(tpl_img.convert("L"), dtype=np.float32)[::step, ::step]
    sh_s, sw_s = s_arr.shape
    th_s, tw_s = t_arr.shape
    if th_s > sh_s or tw_s > sw_s or th_s < 2 or tw_s < 2:
        return False, 0, 0, 0.0

    t_zero = t_arr - float(t_arr.mean())
    t_norm = float(np.sqrt(np.sum(t_zero ** 2)))
    if t_norm < 1e-5:
        return False, 0, 0, 0.0
    t_hat = t_zero / t_norm

    # 1. 利用 2D FFT 计算互相关 (O(N log N)，极低内存)
    fh = 1 << (sh_s + th_s - 2).bit_length()
    fw = 1 << (sw_s + tw_s - 2).bit_length()
    corr_full = np.fft.irfft2(
        np.fft.rfft2(s_arr, s=(fh, fw)) * np.fft.rfft2(t_hat[::-1, ::-1], s=(fh, fw)),
        s=(fh, fw),
    )
    out_h = sh_s - th_s + 1
    out_w = sw_s - tw_s + 1
    corr = corr_full[th_s - 1 : th_s - 1 + out_h, tw_s - 1 : tw_s - 1 + out_w]

    # 2. 利用二维积分图 O(N) 计算每个滑动窗口的标准差范数
    s64 = s_arr.astype(np.float64)
    ii = np.pad(s64, ((1, 0), (1, 0)), mode="constant").cumsum(axis=0).cumsum(axis=1)
    ii2 = np.pad(s64 * s64, ((1, 0), (1, 0)), mode="constant").cumsum(axis=0).cumsum(axis=1)

    win_sum = ii[th_s:, tw_s:] - ii[:-th_s, tw_s:] - ii[th_s:, :-tw_s] + ii[:-th_s, :-tw_s]
    win_sq = ii2[th_s:, tw_s:] - ii2[:-th_s, tw_s:] - ii2[th_s:, :-tw_s] + ii2[:-th_s, :-tw_s]
    n_pix = float(th_s * tw_s)
    var = np.maximum(win_sq - (win_sum * win_sum) / n_pix, 0.0)
    w_norm = np.sqrt(var)

    # 过滤纯色平区域避免除零误匹配
    scores = np.where(w_norm > 1e-3, corr / (w_norm + 1e-6), 0.0)

    max_idx = np.unravel_index(np.argmax(scores), scores.shape)
    best_score = float(scores[max_idx])
    best_y = int(max_idx[0] * step + th // 2)
    best_x = int(max_idx[1] * step + tw // 2)
    return (best_score >= threshold), best_x, best_y, best_score


# ==================== 3.5 实时火苗数字识别引擎（零依赖 + 支持一键样本校准） ====================
class FireEnergyOCR:
    """
    专为 Flash 游戏火苗数值设计的超高速数字识别器（< 1ms / 次）：
    1. 自动适应深底浅字 / 浅底深字，提取干净数字掩膜；
    2. 内置 Windows 多种常见粗体/无衬线数字模板（开箱即用）；
    3. 支持用户一键输入当前火苗值校准（自动切分并保存游戏原生字体样本到 fire_digits/，校准后准确率 100%）。
    """

    GLYPH_W = 16
    GLYPH_H = 24

    def __init__(self, custom_dir: str):
        self.custom_dir = custom_dir
        self.builtin_templates = []  # [(digit_char, norm_vec)]
        self.custom_templates = []   # [(digit_char, norm_vec)]
        self._build_builtin_templates()
        self.reload_custom_templates()

    @staticmethod
    def _normalize_glyph(mask_2d: np.ndarray) -> np.ndarray:
        """将单个二值数字区域保持宽高比缩放到 16x24 并做零均值单位归一化"""
        h, w = mask_2d.shape
        if h <= 0 or w <= 0:
            return np.zeros((FireEnergyOCR.GLYPH_H, FireEnergyOCR.GLYPH_W), dtype=np.float32)
        pil = Image.fromarray((mask_2d.astype(np.uint8) * 255), mode="L")
        # 保留较细数字（如 '1'）的窄比例居中放入画布
        scale = min((FireEnergyOCR.GLYPH_W - 2) / w, (FireEnergyOCR.GLYPH_H - 2) / h)
        nw = max(2, int(round(w * scale)))
        nh = max(2, int(round(h * scale)))
        resized = pil.resize((nw, nh), Image.Resampling.BILINEAR)
        canvas = Image.new("L", (FireEnergyOCR.GLYPH_W, FireEnergyOCR.GLYPH_H), 0)
        canvas.paste(resized, ((FireEnergyOCR.GLYPH_W - nw) // 2, (FireEnergyOCR.GLYPH_H - nh) // 2))
        arr = np.asarray(canvas, dtype=np.float32) / 255.0
        return arr

    @staticmethod
    def _vec_norm(arr: np.ndarray) -> np.ndarray:
        v = arr.reshape(-1) - float(arr.mean())
        n = float(np.linalg.norm(v))
        return v / n if n > 1e-5 else v

    def _build_builtin_templates(self):
        fonts_dir = r"C:\Windows\Fonts"
        font_files = ["arial.ttf", "msyh.ttc", "tahoma.ttf", "arialbd.ttf", "tahomabd.ttf", "simhei.ttf", "msyhbd.ttc"]
        for fn in font_files:
            fpath = os.path.join(fonts_dir, fn)
            if not os.path.exists(fpath):
                continue
            try:
                font = ImageFont.truetype(fpath, 26)
            except Exception:
                continue
            for d in "0123456789":
                img = Image.new("L", (40, 44), 0)
                draw = ImageDraw.Draw(img)
                draw.text((8, 4), d, fill=255, font=font)
                arr = np.asarray(img, dtype=np.uint8) > 80
                ys, xs = np.where(arr)
                if len(xs) > 0:
                    crop = arr[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
                    g = self._normalize_glyph(crop)
                    self.builtin_templates.append((d, self._vec_norm(g)))

    def reload_custom_templates(self):
        self.custom_templates.clear()
        if not os.path.isdir(self.custom_dir):
            return
        for fname in os.listdir(self.custom_dir):
            if not fname.endswith(".png") or len(fname) < 5:
                continue
            d = fname[0]
            if d not in "0123456789":
                continue
            try:
                img = Image.open(os.path.join(self.custom_dir, fname)).convert("L")
                img = img.resize((self.GLYPH_W, self.GLYPH_H), Image.Resampling.BILINEAR)
                arr = np.asarray(img, dtype=np.float32) / 255.0
                self.custom_templates.append((d, self._vec_norm(arr)))
            except Exception:
                pass

    def segment_digits(self, roi_img: Image.Image):
        """
        从火苗区域图像中提取并切分所有独立数字的 16x24 标准化图块：
        1. 自动定位内部浅米色/白色数字框（自动剔除框选时带进来的蓝色背景、上方火苗边缘与棕色边框）；
        2. 提取内部清晰深色数字，避免把外框误判成数字！
        """
        if roi_img is None:
            return []
        rgb = np.asarray(roi_img.convert("RGB"), dtype=np.float32)
        gray = np.asarray(roi_img.convert("L"), dtype=np.float32)
        h, w = gray.shape
        if h < 6 or w < 6:
            return []

        # 优先自动检测《美食大战老鼠》火苗米白色内框（R>185, G>185, B>145），自动过滤掉蓝色背景与褐色外框
        cream = (rgb[:, :, 0] > 185) & (rgb[:, :, 1] > 185) & (rgb[:, :, 2] > 145)
        ys_box = np.where(cream.mean(axis=1) > 0.30)[0]
        xs_box = np.where(cream.mean(axis=0) > 0.25)[0]

        if len(ys_box) >= 6 and len(xs_box) >= 8:
            by0, by1 = int(ys_box[0]), int(ys_box[-1])
            bx0, bx1 = int(xs_box[0]), int(xs_box[-1])
            pad_y = max(1, int((by1 - by0) * 0.08))
            pad_x = max(1, int((bx1 - bx0) * 0.03))
            if (by1 - pad_y) > (by0 + pad_y + 4) and (bx1 - pad_x) > (bx0 + pad_x + 4):
                inner = gray[by0 + pad_y : by1 - pad_y, bx0 + pad_x : bx1 - pad_x]
                bg_hi = float(np.percentile(inner, 90))
                mask = inner < max(100.0, bg_hi * 0.52)
            else:
                inner = gray
                mask = inner < 115.0
        else:
            # 蓝底非战斗界面（如房间列表/翻宝箱蓝边）直接判定无火苗，防止误读出假火苗数字
            if float((rgb[:, :, 2] - rgb[:, :, 0]).mean()) > 22.0:
                return []
            # 通用回退模式：兼容其他深底浅字/浅底深字场景
            border = np.concatenate([gray[0, :], gray[-1, :], gray[:, 0], gray[:, -1]])
            bg_val = float(np.median(border))
            diff = np.abs(gray - bg_val)
            max_d = float(diff.max())
            if max_d < 25.0:
                return []
            mask = diff > max(26.0, max_d * 0.44)

        mh, mw = mask.shape
        # 按列投影切分字符
        col_sum = mask.sum(axis=0)
        in_seg = False
        raw_segs = []
        start_x = 0
        for x in range(mw):
            if col_sum[x] >= 1 and not in_seg:
                in_seg = True
                start_x = x
            elif col_sum[x] == 0 and in_seg:
                in_seg = False
                if x - start_x >= 2:
                    raw_segs.append((start_x, x))
        if in_seg and mw - start_x >= 2:
            raw_segs.append((start_x, mw))

        # 过滤微小噪点并拆分可能粘连的双数字
        glyphs = []
        for x0, x1 in raw_segs:
            sub = mask[:, x0:x1]
            ys = np.where(sub.sum(axis=1) > 0)[0]
            if len(ys) < 4:
                continue
            y0, y1 = int(ys[0]), int(ys[-1]) + 1
            gh, gw = y1 - y0, x1 - x0
            if gh < max(5, mh * 0.30):
                continue
            # 过滤贯穿整个截图顶到底的细竖线（例如房间卡片之间的深色边框缝隙，防止被误读成数字 1）
            if y0 == 0 and y1 >= mh and gw < gh * 0.45:
                continue
            if gw > gh * 1.15:
                mid_l = x0 + max(2, gw // 3)
                mid_r = x1 - max(2, gw // 3)
                if mid_r > mid_l:
                    split_x = mid_l + int(np.argmin(col_sum[mid_l:mid_r]))
                    parts = [(x0, split_x), (split_x, x1)]
                else:
                    parts = [(x0, x1)]
            else:
                parts = [(x0, x1)]

            for px0, px1 in parts:
                if px1 - px0 < 2:
                    continue
                p_sub = mask[:, px0:px1]
                pys = np.where(p_sub.sum(axis=1) > 0)[0]
                if len(pys) < 4:
                    continue
                crop = p_sub[int(pys[0]) : int(pys[-1]) + 1, :]
                glyphs.append(self._normalize_glyph(crop))
        return glyphs

    def read_number(self, roi_img: Image.Image):
        """识别火苗整数，返回 (value: int | None, avg_score: float, glyph_count: int)"""
        glyphs = self.segment_digits(roi_img)
        if not glyphs or len(glyphs) > 6:
            return None, 0.0, len(glyphs)

        digits = []
        scores = []
        for g in glyphs:
            v = self._vec_norm(g)
            best_d = None
            best_s = -1.0
            # 优先匹配用户校准过的游戏原生字体样本（加权 +0.08 优先）
            for d, tv in self.custom_templates:
                s = float(np.dot(v, tv)) + 0.08
                if s > best_s:
                    best_s = s
                    best_d = d
            for d, tv in self.builtin_templates:
                s = float(np.dot(v, tv))
                if s > best_s:
                    best_s = s
                    best_d = d
            if best_d is None or best_s < 0.35:
                return None, best_s, len(glyphs)
            digits.append(best_d)
            scores.append(min(1.0, best_s))

        try:
            val = int("".join(digits))
            return val, float(np.mean(scores)), len(glyphs)
        except ValueError:
            return None, 0.0, len(glyphs)

    def calibrate(self, roi_img: Image.Image, true_text: str):
        """将当前火苗截图切分出的每个字形对应保存为真实数字样本"""
        clean = "".join(ch for ch in true_text.strip() if ch in "0123456789")
        if not clean:
            return False, "请输入纯数字（例如 50、125、350）！"
        glyphs = self.segment_digits(roi_img)
        if len(glyphs) != len(clean):
            return False, f"画面中切分出 {len(glyphs)} 个数字字符，但你输入了 {len(clean)} 位数字。\n请重新更贴合数字边缘地框选一下【实时火苗数字监测区】！"
        ts = int(time.time() * 1000)
        for idx, (ch, g) in enumerate(zip(clean, glyphs)):
            img = Image.fromarray(np.clip(g * 255, 0, 255).astype(np.uint8), mode="L")
            img.save(os.path.join(self.custom_dir, f"{ch}_{ts}_{idx}.png"))
        self.reload_custom_templates()
        return True, f"成功校准并保存了数字样本【{clean}】（现有原生样本数：{len(self.custom_templates)}）"


FIRE_OCR = FireEnergyOCR(FIRE_DIGIT_DIR)


def auto_locate_fire_roi(img: Image.Image, deck_cards: list = None, viewport_box=None):
    """
    自动定位战斗画面左上角【火苗数字框】[l, t, r, b]（耗时 ~5-15ms，适配任意分辨率与任意带卡数量）：
    四重联合特征：
      1. 位于画面顶部左侧栏（优先在首张卡片左侧窄带内搜索，未命中时自动扩大到左上 60%×28%）；
      2. 米白色水平圆角矩形框（宽长比 1.65~5.5，填充度 >= 0.42）；
      3. 正上方紧贴亮橙金火苗徽章圆盘，周边紧邻蓝色顶栏边框；
      4. 框内数字必须通过 FIRE_OCR 清晰识别为合法整数（排除卡费与其他无关白块）。
    返回: (roi_box [l, t, r, b], fire_val, score) 或 (None, None, -1.0)
    """
    if img is None:
        return None, None, -1.0
    iw, ih = img.size
    if iw < 200 or ih < 120:
        return None, None, -1.0

    vp = viewport_box
    if not vp or len(vp) != 4:
        try:
            vp = auto_detect_game_viewport(img)
        except Exception:
            vp = None
    vx0, vy0, vx1, vy1 = vp if (vp and len(vp) == 4) else (0, 0, iw, ih)
    vw = max(200, vx1 - vx0)
    vh = max(120, vy1 - vy0)

    min_card_x = None
    if deck_cards:
        cxs = [int(c["x"]) for c in deck_cards if "x" in c and "铲" not in c.get("name", "")]
        if cxs:
            min_card_x = min(cxs)

    def _scan_region(sx0: int, sy0: int, sx1: int, sy1: int, enforce_left_of_card: bool):
        sx0, sy0 = max(0, sx0), max(0, sy0)
        sx1, sy1 = min(iw, sx1), min(ih, sy1)
        if sx1 - sx0 < 40 or sy1 - sy0 < 25:
            return None, None, -1.0

        crop_rgb = np.asarray(img.crop((sx0, sy0, sx1, sy1)).convert("RGB"), dtype=np.float32)
        r, g, b = crop_rgb[:, :, 0], crop_rgb[:, :, 1], crop_rgb[:, :, 2]
        cream = (
            (r > 175.0)
            & (g > 170.0)
            & (b > 130.0)
            & (np.abs(r - g) < 32.0)
            & ((r - b) > -20.0)
            & ((r - b) < 68.0)
        )
        sh, sw = cream.shape
        ds = max(2, sw // 180) if (sw >= 220 and sh >= 100) else 1
        c_ds = cream[::ds, ::ds]
        dh, dw = c_ds.shape
        vis = np.zeros((dh, dw), dtype=np.uint8)
        boxes = []
        ys_all, xs_all = np.where(c_ds)
        for idx in range(len(ys_all)):
            y0 = int(ys_all[idx])
            x0 = int(xs_all[idx])
            if vis[y0, x0]:
                continue
            stack = [(y0, x0)]
            vis[y0, x0] = 1
            min_y = max_y = y0
            min_x = max_x = x0
            area = 0
            while stack:
                cy, cx = stack.pop()
                area += 1
                if cy < min_y:
                    min_y = cy
                if cy > max_y:
                    max_y = cy
                if cx < min_x:
                    min_x = cx
                if cx > max_x:
                    max_x = cx
                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                    if 0 <= ny < dh and 0 <= nx < dw and not vis[ny, nx] and c_ds[ny, nx]:
                        vis[ny, nx] = 1
                        stack.append((ny, nx))
            bw = (max_x - min_x + 1) * ds
            bh = (max_y - min_y + 1) * ds
            if bw < max(28, int(vw * 0.025)) or bw > int(vw * 0.12):
                continue
            if bh < max(10, int(vh * 0.014)) or bh > int(vh * 0.065):
                continue
            aspect = bw / float(bh)
            if aspect < 1.65 or aspect > 5.5:
                continue
            fill = (area * ds * ds) / float(bw * bh)
            if fill < 0.42:
                continue
            boxes.append((min_x * ds, min_y * ds, min(sw, (max_x + 1) * ds), min(sh, (max_y + 1) * ds), aspect))

        best = (None, None, -1.0)
        for bx0, by0, bx1, by1, aspect in boxes:
            bw = bx1 - bx0
            bh = by1 - by0
            above_y0 = max(0, by0 - int(bh * 2.8))
            above_y1 = max(0, by0 - 2)
            if above_y1 - above_y0 < max(6, bh // 2):
                continue
            above = crop_rgb[above_y0:above_y1, bx0:bx1]
            ar, ag, ab = above[:, :, 0], above[:, :, 1], above[:, :, 2]
            flame_gold = float(((ar > 195.0) & (ag > 130.0) & ((ar - ab) > 45.0)).mean())
            medallion_bright = float(((ar > 180.0) & (ag > 165.0) & (ab > 120.0)).mean())
            if flame_gold < 0.04 or medallion_bright < 0.12:
                continue

            ring_x0 = max(0, bx0 - max(6, bw // 6))
            ring_x1 = min(sw, bx1 + max(6, bw // 6))
            ring_y0 = max(0, by0 - 4)
            ring_y1 = min(sh, by1 + max(6, bh // 2))
            ring = crop_rgb[ring_y0:ring_y1, ring_x0:ring_x1]
            rr, rb = ring[:, :, 0], ring[:, :, 2]
            blue_bar = float(((rb > 110.0) & ((rb - rr) > 28.0)).mean())
            if blue_bar < 0.04:
                continue

            pad_x = max(3, int(bw * 0.06))
            pad_y = max(3, int(bh * 0.14))
            gl = max(0, sx0 + bx0 - pad_x)
            gt = max(0, sy0 + by0 - pad_y)
            gr = min(iw, sx0 + bx1 + pad_x)
            gb = min(ih, sy0 + by1 + pad_y)
            val, ocr_sc, gcnt = FIRE_OCR.read_number(img.crop((gl, gt, gr, gb)))
            if val is None or ocr_sc < 0.48 or gcnt < 1 or gcnt > 5:
                continue

            score = ocr_sc * 2.0 + min(0.5, flame_gold * 2.0) + min(0.3, blue_bar * 1.5)
            if 2.2 <= aspect <= 4.2:
                score += 0.25
            if enforce_left_of_card and min_card_x is not None:
                if gr <= min_card_x + 15:
                    dist = min_card_x - gr
                    if 0 <= dist <= max(240, int(vw * 0.16)):
                        score += 0.5
                else:
                    score -= 0.85
            if score > best[2]:
                best = ([gl, gt, gr, gb], val, score)
        return best

    # Pass 1: 若有已录卡片，先在首张卡紧左侧窄带内极速搜索 (~3ms)
    if min_card_x is not None:
        nx0 = max(vx0, min_card_x - int(vw * 0.28))
        nx1 = min(vx1, min_card_x + 20)
        res1 = _scan_region(nx0, vy0, nx1, vy0 + int(vh * 0.28), enforce_left_of_card=True)
        if res1[0] is not None:
            return res1

    # Pass 2: 兜底扫描整个游戏画面左上区域（兼容未录卡组或换卡数大幅偏移场景）
    return _scan_region(vx0, vy0, vx0 + int(vw * 0.60), vy0 + int(vh * 0.28), enforce_left_of_card=False)


def _make_blank_deck() -> dict:
    return {
        "enter_clicks": [],
        "hero": {
            "enabled": True,
            "on_continue": False,
            "on_start": False,
            "x": 960,
            "y": 660,
            "wait_before": 3.0,
            "wait_after": 6.0,
            "clicks": 2,
        },
        "cards": [],
        "placements": [],
        "options": {
            "auto_collect_fire": False,
            "wait_for_fire": True,
            "verify_placed": True,
            "loop_placements": False,
            "continue_resets_battle": False,
        },
    }


# ==================== 4. 默认配置（已按 2560x1342 画面预填 6 套预设卡组与开始按钮） ====================
def build_default_config():
    preset_decks_xy = [
        ("159", 1170, 266),
        ("次元", 1352, 266),
        ("城堡", 1534, 266),
        ("别西卜", 1716, 266),
        ("双蛇", 1898, 266),
        ("三岛", 2080, 266),
    ]
    decks = {}
    for dname, dx, dy in preset_decks_xy:
        decks[dname] = {
            "enter_clicks": [
                {"name": f"选择卡组【{dname}】", "x": dx, "y": dy, "delay": 0.6},
                {"name": "点击【开始】进入战斗", "x": 2161, "y": 1085, "delay": 2.0},
            ],
            "hero": {
                "enabled": True,
                "on_continue": True,
                "on_start": False,
                "x": 960,
                "y": 660,
                "wait_before": 3.0,
                "wait_after": 4.0,
                "clicks": 2,
            },
            "cards": [],       # [{"name": "小火炉", "x": ..., "y": ..., "color": "#ff7043", "icon": "xxx.png"}]
            "placements": [],  # [{"card_name": "小火炉", "x": ..., "y": ..., "delay": 1.2, "enabled": True}]
        }
    return {
        "hwnd": 0,
        "active_deck": "三岛",
        "decks": decks,
        "auto_collect_fire": False,
        "wait_for_fire": True,
        "verify_placed": True,
        "loop_placements": False,
        "continue_resets_battle": False,
        "fire_ocr_roi": None,  # [x0, y0, x1, y1] 实时火苗数字框区域
        "fire_area": [420, 240, 2150, 1200],
        "template_threshold": 0.84,
        "ffbrowser_path": "",
        "login_url": DEFAULT_LOGIN_URL,
        "accounts": [],
        "active_account_id": "",
        "login_points": {
            "open_xy": None,
            "tab_xy": None,
            "user_xy": None,
            "pass_xy": None,
            "submit_xy": None,
            "after_clicks": [],
        },
        "auto_login_on_bot": False,
        "finish_extra_clicks": [
            {"name": "翻牌位置1", "x": 960, "y": 650, "delay": 0.8},
            {"name": "翻牌位置2", "x": 1280, "y": 650, "delay": 0.8},
            {"name": "结算确定/离开", "x": 1280, "y": 1020, "delay": 1.2},
        ],
    }


# ==================== 5. 主界面类 ====================
class MeishiBotGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"刷关模拟器 {APP_VERSION} (Flash) - 美食大战老鼠后台自动助手")
        # 按当前屏幕物理分辨率自适应初始窗口尺寸（适配 2K/4K 高分屏，小窗下所有按钮也完整可见）
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        init_w = min(1760, max(1200, int(sw * 0.76)))
        init_h = min(1060, max(780, int(sh * 0.78)))
        self.root.geometry(f"{init_w}x{init_h}")

        self.config = self.load_config()
        self.hwnd = int(self.config.get("hwnd", 0))
        self.running = False
        self.team_running = False
        self._run_token = 0
        self._runs_lock = threading.Lock()
        self._active_runs = {}
        self._active_tokens = set()
        self.worker_thread = None
        self.worker_threads = []
        self._team_lock = threading.Lock()
        self._team_member_ready = {}
        self._team_member_ids = []
        self._team_status = {}
        self.clear_count = 0
        self._last_clear_ts = 0.0
        self._account_clear_counts = {}
        self._account_clear_names = {}
        self._account_last_clear_ts = {}
        self._stealth_active = False
        self._stealth_root_hwnd = 0
        self._stealth_orig_exstyle = None
        self._stealth_entries = []  # [(root_hwnd, saved_state), ...] 支持多开同时隐身全部游戏窗口
        atexit.register(self._restore_stealth_on_exit)

        # 实时画面与画布状态
        self.current_pil_img = None
        self.orig_w = 0
        self.orig_h = 0
        self.canvas_w = 640
        self.canvas_h = 440
        self.preview_scale = 1.0
        self.view_ox = 0
        self.view_oy = 0
        self.canvas_ox = 0
        self.canvas_oy = 0
        self._auto_crop_tried = False
        self.canvas_img_id = None
        self.overlay_ids = []
        self.drag_start = None
        self.drag_rect_id = None
        self._preview_busy = False
        self._alive = True
        self._fps_count = 0
        self._fps_last_ts = time.perf_counter()
        self._last_fire_check_ts = 0.0
        self.latest_fire_val = None
        self._last_wait_fire_log_ts = 0.0
        self._last_autobind_ts = 0.0
        self._logging_in_accounts = set()

        # 交互模式与选中卡片
        self.click_pick_mode = tk.StringVar(value="test_click")
        self.var_live_preview = tk.BooleanVar(value=True)
        self.var_target_fps = tk.StringVar(value="30 FPS")
        self.var_show_markers = tk.BooleanVar(value=True)
        self.var_active_account = tk.StringVar(value="默认")
        self.var_active_deck = tk.StringVar(value=self.config.get("active_deck", "三岛"))
        self.var_selected_card = tk.StringVar(value="")
        self._switching_account = False
        self._icon_refs = {}  # 防止 PhotoImage 被垃圾回收
        self._card_icon_vec_cache = {}  # 缓存 32x32 卡牌图标归一化向量（0.4ms 判定是否在真实战斗画面）
        self._indicator_photos = None
        theme_k = self.config.get("ui_theme", "dark")
        self.ui_theme_key = theme_k if theme_k in UI_THEMES else "dark"
        self.style = ttk.Style(self.root)

        self._build_ui()
        self._apply_ui_theme(self.ui_theme_key, save=False)
        self._sync_account_combo_ui()
        self._update_checking = False
        self._refresh_window_list()
        self._refresh_deck_ui()
        self._sync_target_clears_ui()
        self._start_hotkey_listener()
        self._start_live_preview_loop()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        # 启动 2.8 秒后在后台静默检查一次是否有新版本（断网无弹窗打扰）
        self.root.after(2800, lambda: self.check_for_updates(manual=False))

    def _cur_theme(self) -> dict:
        return UI_THEMES.get(self.ui_theme_key, UI_THEMES["dark"])

    def _cycle_ui_theme(self):
        idx = (THEME_ORDER.index(self.ui_theme_key) + 1) % len(THEME_ORDER)
        next_key = THEME_ORDER[idx]
        self._apply_ui_theme(next_key, save=True)
        self.log(f"🎨 已切换界面皮肤为【{UI_THEMES[next_key]['label']}】")

    def _apply_ui_theme(self, theme_key: str, save: bool = True):
        if theme_key not in UI_THEMES:
            theme_key = "dark"
        self.ui_theme_key = theme_key
        t = UI_THEMES[theme_key]
        self.config["ui_theme"] = theme_key

        try:
            self.style.theme_use("clam")
        except Exception:
            pass

        self.root.configure(bg=t["bg"])
        self.root.option_add("*TCombobox*Listbox.background", t["input_bg"])
        self.root.option_add("*TCombobox*Listbox.foreground", t["input_fg"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", t["accent"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", t["accent_fg"])

        s = self.style
        s.configure(
            ".",
            background=t["card"],
            foreground=t["fg"],
            bordercolor=t["border"],
            troughcolor=t["input_bg"],
            focuscolor=t["accent"],
            font=("Microsoft YaHei", 9),
        )
        s.configure("TFrame", background=t["card"])
        s.configure("Root.TFrame", background=t["bg"])
        s.configure("TPanedwindow", background=t["bg"])
        s.configure("Sash", sashthickness=5, gripcount=0, background=t["bg"])
        s.configure(
            "TLabelframe",
            background=t["card"],
            bordercolor=t["border"],
            lightcolor=t["border"],
            darkcolor=t["border"],
            relief="solid",
            borderwidth=1,
        )
        s.configure(
            "TLabelframe.Label",
            background=t["card"],
            foreground=t["accent"],
            font=("Microsoft YaHei", 9, "bold"),
        )
        s.configure("TLabel", background=t["card"], foreground=t["fg"])
        s.configure(
            "TButton",
            background=t["btn_bg"],
            foreground=t["btn_fg"],
            bordercolor=t["border"],
            lightcolor=t["btn_bg"],
            darkcolor=t["btn_bg"],
            padding=(6, 3),
            relief="flat",
        )
        s.map(
            "TButton",
            background=[("active", t["btn_hover"]), ("pressed", t["accent"])],
            foreground=[("pressed", t["accent_fg"])],
            bordercolor=[("active", t["accent"])],
        )
        try:
            dpi_scale = max(1.0, float(self.root.winfo_fpixels("1i")) / 96.0)
        except Exception:
            dpi_scale = 1.25
        ind_sz = max(15, min(24, int(round(14.5 * dpi_scale))))
        ind_imgs = _make_modern_indicators(t, sz=ind_sz)
        if self._indicator_photos is None:
            self._indicator_photos = {k: ImageTk.PhotoImage(v) for k, v in ind_imgs.items()}
            try:
                s.element_create(
                    "Modern.Check.indicator",
                    "image",
                    self._indicator_photos["chk_off"],
                    ("selected", self._indicator_photos["chk_on"]),
                    ("active", self._indicator_photos["chk_hov"]),
                    width=ind_sz + 5,
                    sticky="w",
                )
                s.layout(
                    "TCheckbutton",
                    [
                        (
                            "Checkbutton.padding",
                            {
                                "sticky": "nswe",
                                "children": [
                                    ("Modern.Check.indicator", {"side": "left", "sticky": ""}),
                                    ("Checkbutton.label", {"sticky": "nswe"}),
                                ],
                            },
                        )
                    ],
                )
                s.element_create(
                    "Modern.Radio.indicator",
                    "image",
                    self._indicator_photos["rad_off"],
                    ("selected", self._indicator_photos["rad_on"]),
                    ("active", self._indicator_photos["rad_hov"]),
                    width=ind_sz + 5,
                    sticky="w",
                )
                s.layout(
                    "TRadiobutton",
                    [
                        (
                            "Radiobutton.padding",
                            {
                                "sticky": "nswe",
                                "children": [
                                    ("Modern.Radio.indicator", {"side": "left", "sticky": ""}),
                                    ("Radiobutton.label", {"sticky": "nswe"}),
                                ],
                            },
                        )
                    ],
                )
            except Exception:
                pass
        else:
            for k, pil_im in ind_imgs.items():
                self._indicator_photos[k].paste(pil_im)

        s.configure(
            "TCheckbutton",
            background=t["card"],
            foreground=t["fg"],
            padding=(2, 2),
        )
        s.map(
            "TCheckbutton",
            background=[("active", t["card"])],
            foreground=[("active", t["accent"])],
        )
        s.configure(
            "TRadiobutton",
            background=t["card"],
            foreground=t["fg"],
            padding=(2, 2),
        )
        s.map(
            "TRadiobutton",
            background=[("active", t["card"])],
            foreground=[("active", t["accent"])],
        )
        s.configure(
            "TEntry",
            fieldbackground=t["input_bg"],
            foreground=t["input_fg"],
            insertcolor=t["fg"],
            bordercolor=t["input_border"],
            lightcolor=t["input_border"],
            darkcolor=t["input_border"],
            padding=(4, 2),
        )
        s.configure(
            "TCombobox",
            fieldbackground=t["input_bg"],
            foreground=t["input_fg"],
            background=t["btn_bg"],
            arrowcolor=t["fg"],
            bordercolor=t["input_border"],
            lightcolor=t["input_border"],
            darkcolor=t["input_border"],
            padding=(4, 2),
        )
        s.map(
            "TCombobox",
            fieldbackground=[("readonly", t["input_bg"]), ("disabled", t["card"])],
            foreground=[("readonly", t["input_fg"])],
            selectbackground=[("readonly", t["input_bg"])],
            selectforeground=[("readonly", t["input_fg"])],
            background=[("active", t["btn_hover"])],
        )
        s.configure("TNotebook", background=t["bg"], bordercolor=t["border"], tabmargins=(2, 2, 2, 0))
        s.configure(
            "TNotebook.Tab",
            background=t["tab_bg"],
            foreground=t["tab_fg"],
            padding=(10, 5),
            borderwidth=0,
            font=("Microsoft YaHei", 9, "bold"),
        )
        s.map(
            "TNotebook.Tab",
            background=[("selected", t["tab_sel_bg"]), ("active", t["btn_hover"])],
            foreground=[("selected", t["tab_sel_fg"]), ("active", t["fg"])],
        )
        try:
            dpi_scale = max(1.0, float(self.root.winfo_fpixels("1i")) / 96.0)
        except Exception:
            dpi_scale = 1.25
        std_rh = max(28, int(round(25 * dpi_scale)))
        card_rh = max(38, int(round(32 * dpi_scale)))
        for tv_style, rh in [("Treeview", std_rh), ("Cards.Treeview", card_rh)]:
            s.configure(
                tv_style,
                background=t["row_odd"],
                fieldbackground=t["row_odd"],
                foreground=t["fg"],
                bordercolor=t["border"],
                lightcolor=t["border"],
                darkcolor=t["border"],
                rowheight=rh,
                font=("Microsoft YaHei", 9),
            )
            s.map(
                tv_style,
                background=[("selected", t["row_sel"])],
                foreground=[("selected", t["row_sel_fg"])],
            )
            s.configure(
                f"{tv_style}.Heading",
                background=t["th_bg"],
                foreground=t["th_fg"],
                bordercolor=t["border"],
                relief="flat",
                font=("Microsoft YaHei", 9, "bold"),
                padding=(4, 4),
            )
            s.map(f"{tv_style}.Heading", background=[("active", t["btn_hover"])])

        s.configure(
            "Vertical.TScrollbar",
            background=t["btn_bg"],
            troughcolor=t["input_bg"],
            bordercolor=t["border"],
            arrowcolor=t["muted"],
        )

        # 更新经典 tk 控件、语义文字与彩色日志标签
        if hasattr(self, "canvas"):
            self.canvas.configure(
                bg=t["canvas_bg"], highlightbackground=t["border"], highlightcolor=t["accent"], highlightthickness=1
            )
        if hasattr(self, "txt_log"):
            self.txt_log.configure(
                bg=t["log_bg"],
                fg=t["log_fg"],
                insertbackground=t["fg"],
                selectbackground=t["accent"],
                selectforeground=t["accent_fg"],
                highlightbackground=t["border"],
                highlightcolor=t["accent"],
                highlightthickness=1,
                relief="flat",
                bd=0,
                padx=6,
                pady=4,
            )
            self.txt_log.tag_configure("ts", foreground=t["log_ts"])
            self.txt_log.tag_configure("ok", foreground=t["log_ok"])
            self.txt_log.tag_configure("fire", foreground=t["log_fire"])
            self.txt_log.tag_configure("warn", foreground=t["log_warn"])
            self.txt_log.tag_configure("trophy", foreground=t["log_trophy"], font=("Consolas", 9, "bold"))
            self.txt_log.tag_configure("info", foreground=t["log_info"])
            self.txt_log.tag_configure("normal", foreground=t["log_fg"])

        if hasattr(self, "btn_start") or hasattr(self, "btn_team_start"):
            self._refresh_run_buttons(refresh_tree=False)
        if hasattr(self, "btn_stealth"):
            bg_st = t["stealth_on_bg"] if self._stealth_active else t["stealth_bg"]
            self.btn_stealth.configure(bg=bg_st, fg="#ffffff", activebackground=bg_st, activeforeground="#ffffff", relief="flat", bd=0, cursor="hand2")
        if hasattr(self, "btn_theme"):
            self.btn_theme.configure(text=f"🎨{t['label']}")
        if hasattr(self, "btn_crop_view"):
            self._update_crop_btn_label()
        if hasattr(self, "lbl_fps"):
            self.lbl_fps.configure(foreground=t["fps_fg"])
        if hasattr(self, "lbl_hwnd"):
            self.lbl_hwnd.configure(foreground=t["hwnd_fg"])
        if hasattr(self, "lbl_fire_live"):
            self.lbl_fire_live.configure(foreground=t["fire_fg"])
        if hasattr(self, "lbl_cur_card_hint"):
            self.lbl_cur_card_hint.configure(foreground=t["muted"])
        if hasattr(self, "lbl_clear_count"):
            self.lbl_clear_count.configure(foreground=t["clear_fg"])
        if hasattr(self, "lbl_bot_progress"):
            self.lbl_bot_progress.configure(foreground=t["prog_fg"])
        if hasattr(self, "lbl_hero_xy"):
            self.lbl_hero_xy.configure(foreground=t["hero_fg"])
        if hasattr(self, "lbl_templates"):
            self.lbl_templates.configure(foreground=t["hwnd_fg"])
        if hasattr(self, "lbl_cards_tip"):
            self.lbl_cards_tip.configure(foreground=t["tip_fg"])
        if hasattr(self, "lbl_finish_tip"):
            self.lbl_finish_tip.configure(foreground=t["muted"])
        if hasattr(self, "place_menu"):
            self.place_menu.configure(
                bg=t["card"], fg=t["fg"], activebackground=t["accent"], activeforeground=t["accent_fg"]
            )

        for tv_name in ("tree_cards", "tree_place", "tree_enter", "tree_finish", "tree_accounts"):
            tv = getattr(self, tv_name, None)
            if tv is not None:
                tv.tag_configure("odd", background=t["row_odd"], foreground=t["fg"])
                tv.tag_configure("even", background=t["row_even"], foreground=t["fg"])

        if hasattr(self, "quick_cards_box"):
            self._reload_quick_card_buttons()

        apply_win11_titlebar(self.root, t)
        if save:
            self.save_config(silent=True)

    def _restore_stealth_on_exit(self):
        if self._stealth_active:
            entries = list(self._stealth_entries)
            if not entries and self._stealth_root_hwnd:
                entries = [(self._stealth_root_hwnd, self._stealth_orig_exstyle)]
            for rh, st in entries:
                try:
                    set_window_stealth(rh, False, st)
                except Exception:
                    pass
            self._stealth_active = False
            self._stealth_root_hwnd = 0
            self._stealth_orig_exstyle = None
            self._stealth_entries = []

    def _on_close(self):
        self._alive = False
        self._stop_all_bots(silent=True)
        self._restore_stealth_on_exit()
        self.save_config(silent=True)
        CAPTURER.close()
        self.root.destroy()

    def load_config(self):
        default_cfg = build_default_config()
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # 兼容旧版配置结构自动升级
                if "decks" not in data:
                    default_cfg["hwnd"] = data.get("hwnd", 0)
                    default_cfg["auto_collect_fire"] = data.get("auto_collect_fire", True)
                    default_cfg["finish_extra_clicks"] = data.get("finish_extra_clicks", default_cfg["finish_extra_clicks"])
                    return default_cfg
                for k, v in default_cfg.items():
                    data.setdefault(k, v)
                self._migrate_decks_to_accounts(data)
                return data
            except Exception:
                pass
        self._migrate_decks_to_accounts(default_cfg)
        return default_cfg

    def _migrate_decks_to_accounts(self, data: dict):
        """
        平滑无损迁移：若已有账号列表且尚未按账号拆分布阵，则自动把旧全局 decks 原封不动归属到第 1 个账号，
        其余账号分配各自独立的新卡组库，彻底实现每个账号独立卡组与布阵！
        """
        accs = data.get("accounts") or []
        if not accs:
            return
        any_has_decks = any(isinstance(a.get("decks"), dict) and a.get("decks") for a in accs)
        if not any_has_decks:
            old_decks = copy.deepcopy(data.get("decks") or {"默认关卡": _make_blank_deck()})
            old_active = data.get("active_deck") or next(iter(old_decks.keys()))
            accs[0]["decks"] = old_decks
            accs[0]["active_deck"] = old_active if old_active in old_decks else next(iter(old_decks.keys()))
        for a in accs:
            if not isinstance(a.get("decks"), dict) or not a.get("decks"):
                a["decks"] = {"默认关卡": _make_blank_deck()}
            if a.get("active_deck") not in a["decks"]:
                a["active_deck"] = next(iter(a["decks"].keys()))
        active_id = data.get("active_account_id", "")
        if not any(a.get("id") == active_id for a in accs):
            data["active_account_id"] = accs[0].get("id", "")

    def _get_active_decks_store(self):
        """返回 (当前生效的 decks 字典, 归属对象 dict, 账号显示名)"""
        accs = self.config.get("accounts") or []
        if accs:
            aid = self.config.get("active_account_id", "")
            target = None
            for a in accs:
                if a.get("id") == aid:
                    target = a
                    break
            if target is None:
                target = accs[0]
                self.config["active_account_id"] = target.get("id", "")
            decks = target.setdefault("decks", {})
            if not decks:
                decks["默认关卡"] = _make_blank_deck()
            return decks, target, target.get("name", "")
        decks = self.config.setdefault("decks", {})
        if not decks:
            decks["默认关卡"] = _make_blank_deck()
        return decks, self.config, ""

    def save_config(self, silent: bool = False):
        self.config["hwnd"] = self.hwnd
        _, owner, _ = self._get_active_decks_store()
        owner["active_deck"] = self.var_active_deck.get()
        if owner is self.config:
            self.config["active_deck"] = self.var_active_deck.get()
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            if not silent:
                self.log("配置与卡组数据已保存到 meishi_config.json")
        except Exception as e:
            if not silent:
                self.log(f"保存配置失败: {e}")

    def get_cur_deck(self) -> dict:
        decks, owner, _ = self._get_active_decks_store()
        name = self.var_active_deck.get()
        if name not in decks:
            saved_name = owner.get("active_deck", "")
            if saved_name in decks:
                name = saved_name
            elif decks:
                name = next(iter(decks.keys()))
            else:
                decks["默认关卡"] = _make_blank_deck()
                name = "默认关卡"
            self.var_active_deck.set(name)
        owner["active_deck"] = name
        deck = decks[name]
        deck.setdefault("enter_clicks", [])
        deck.setdefault("cards", [])
        deck.setdefault("placements", [])
        deck.setdefault(
            "hero",
            {
                "enabled": True,
                "on_continue": False,
                "on_start": False,
                "x": 960,
                "y": 660,
                "wait_before": 3.0,
                "wait_after": 4.0,
                "clicks": 2,
            },
        )
        deck["hero"].setdefault("wait_after", 4.0)
        # 每个关卡方案独立保存自己的收尾步骤与战斗开关（首次自动从旧全局配置平滑继承）
        if "finish_clicks" not in deck:
            deck["finish_clicks"] = copy.deepcopy(self.config.get("finish_extra_clicks", []))
        opts = deck.setdefault("options", {})
        opts.setdefault("auto_collect_fire", bool(self.config.get("auto_collect_fire", False)))
        opts.setdefault("wait_for_fire", bool(self.config.get("wait_for_fire", True)))
        opts.setdefault("verify_placed", bool(self.config.get("verify_placed", True)))
        opts.setdefault("loop_placements", bool(self.config.get("loop_placements", False)))
        opts.setdefault("continue_resets_battle", bool(self.config.get("continue_resets_battle", False)))
        return deck

    def get_cur_options(self) -> dict:
        return self.get_cur_deck()["options"]

    def _get_profile_tpl_dir(self, profile_name: str = None) -> str:
        pname = profile_name if profile_name is not None else self.var_active_deck.get()
        d = os.path.join(PROFILE_TPL_ROOT, _safe_profile_dirname(pname))
        os.makedirs(d, exist_ok=True)
        return d

    def _resolve_template(self, fname: str, profile_name: str = None) -> str:
        """优先使用当前(或指定)关卡方案的专属模板，若未单独截取则回退到公共模板"""
        p_path = os.path.join(self._get_profile_tpl_dir(profile_name), fname)
        if os.path.exists(p_path):
            return p_path
        return os.path.join(TEMPLATE_DIR, fname)

    def get_card_by_name(self, card_name: str):
        for c in self.get_cur_deck().get("cards", []):
            if c["name"] == card_name:
                return c
        return None

    # ==================== UI 构建 ====================
    def _build_ui(self):
        # 1. 顶部：窗口绑定与卡组切换栏
        top_frame = ttk.LabelFrame(self.root, text="第一步：绑定 FCBrowser 窗口 & 选择当前卡组方案", padding=6)
        top_frame.pack(fill="x", padx=8, pady=4)

        row1 = ttk.Frame(top_frame)
        row1.pack(fill="x", pady=2)
        self.win_combo = ttk.Combobox(row1, width=20, state="readonly")
        self.win_combo.pack(side="left", padx=2)
        self.win_combo.bind("<<ComboboxSelected>>", self._on_combo_select)

        ttk.Button(row1, text="刷新", width=5, command=self._refresh_window_list).pack(side="left", padx=2)
        ttk.Checkbutton(row1, text="实时", variable=self.var_live_preview).pack(side="left", padx=2)
        self.fps_combo = ttk.Combobox(
            row1, textvariable=self.var_target_fps, values=["15 FPS", "30 FPS", "60 FPS"], width=7, state="readonly"
        )
        self.fps_combo.pack(side="left", padx=2)
        self.lbl_fps = ttk.Label(row1, text="[0 FPS]", foreground="#2e7d32", width=8)
        self.lbl_fps.pack(side="left", padx=2)
        ttk.Checkbutton(
            row1, text="标记", variable=self.var_show_markers, command=self._redraw_canvas_overlays
        ).pack(side="left", padx=2)
        self.btn_crop_view = ttk.Button(row1, text="✂去白边", width=7, command=self._toggle_preview_crop)
        self.btn_crop_view.pack(side="left", padx=2)
        ttk.Button(row1, text="截图", width=5, command=self.save_snapshot_for_ai).pack(side="left", padx=2)
        self.btn_stealth = tk.Button(
            row1,
            text="👻隐身穿透(F10)",
            bg="#4f46e5",
            fg="white",
            font=("Microsoft YaHei", 9, "bold"),
            relief="flat",
            bd=0,
            padx=7,
            pady=2,
            cursor="hand2",
            command=self.toggle_stealth,
        )
        self.btn_stealth.pack(side="left", padx=3)
        self.btn_theme = ttk.Button(row1, text="🎨深蓝暗夜", width=9, command=self._cycle_ui_theme)
        self.btn_theme.pack(side="left", padx=2)
        self.btn_update = ttk.Button(row1, text="🔄更新", width=6, command=lambda: self.check_for_updates(manual=True))
        self.btn_update.pack(side="left", padx=2)

        self.lbl_hwnd = ttk.Label(row1, text="未绑定(按F8锁定)", foreground="blue")
        self.lbl_hwnd.pack(side="left", padx=4)

        # 账号 & 独立关卡方案栏
        row2 = ttk.Frame(top_frame)
        row2.pack(fill="x", pady=2)
        ttk.Label(row2, text="👤:", font=("Microsoft YaHei", 9, "bold")).pack(side="left", padx=(2, 0))
        self.account_combo = ttk.Combobox(row2, textvariable=self.var_active_account, width=9, state="readonly")
        self.account_combo.pack(side="left", padx=2)
        self.account_combo.bind("<<ComboboxSelected>>", self._on_account_combo_select)

        ttk.Label(row2, text="方案:", font=("Microsoft YaHei", 9, "bold")).pack(side="left", padx=(4, 1))
        self.deck_combo = ttk.Combobox(row2, textvariable=self.var_active_deck, width=9, state="readonly")
        self.deck_combo.pack(side="left", padx=2)
        self.deck_combo.bind("<<ComboboxSelected>>", lambda _: self._refresh_deck_ui())

        ttk.Button(row2, text="➕新建", width=6, command=self._create_deck).pack(side="left", padx=1)
        ttk.Button(row2, text="📑复制", width=6, command=self._clone_deck).pack(side="left", padx=1)
        ttk.Button(row2, text="✏改名", width=6, command=self._rename_deck).pack(side="left", padx=1)
        ttk.Button(row2, text="🗑删", width=4, command=self._delete_deck).pack(side="left", padx=1)
        ttk.Button(row2, text="💾导出", width=6, command=self._export_deck).pack(side="left", padx=1)
        ttk.Button(row2, text="📂导入", width=6, command=self._import_deck).pack(side="left", padx=1)
        ttk.Button(row2, text="🚀测开战", width=7, command=self._test_run_enter).pack(side="left", padx=3)
        self.lbl_fire_live = ttk.Label(
            row2, text="🔥火苗:进战自动锁", foreground="#e65100", font=("Microsoft YaHei", 9, "bold")
        )
        self.lbl_fire_live.pack(side="left", padx=4)
        ttk.Button(row2, text="🔍寻火", width=6, command=self._manual_auto_locate_fire_roi).pack(side="left", padx=1)
        ttk.Button(row2, text="🎯校准", width=6, command=self._open_fire_calibrate_dialog).pack(side="left", padx=1)

        # 2. 优先固定底部控制与日志区（防止高分屏窗口缩放时启动按钮被挤出屏幕底部）
        bot_frame = ttk.LabelFrame(
            self.root,
            text="控制与运行日志 (全局快捷键：F8 = 锁定窗口 | F10 = 隐身穿透/恢复 | F11 = 启动/暂停挂机)",
            padding=5,
        )
        bot_frame.pack(side="bottom", fill="x", padx=8, pady=4)

        ctrl_bar = ttk.Frame(bot_frame)
        ctrl_bar.pack(fill="x")
        self.btn_start = tk.Button(
            ctrl_bar,
            text="▶ 启动后台自动闯关 (F11)",
            bg="#28a745",
            fg="white",
            font=("Microsoft YaHei", 11, "bold"),
            padx=14,
            pady=3,
            command=self.toggle_bot,
        )
        self.btn_start.pack(side="left", padx=4)
        self.btn_team_start = tk.Button(
            ctrl_bar,
            text="🤝 组队联刷",
            bg="#2563eb",
            fg="white",
            font=("Microsoft YaHei", 10, "bold"),
            relief="flat",
            bd=0,
            padx=10,
            pady=3,
            cursor="hand2",
            command=self.toggle_team_bot,
        )
        self.btn_team_start.pack(side="left", padx=4)
        ttk.Button(ctrl_bar, text="💾 保存配置", command=self.save_config).pack(side="left", padx=4)

        self.lbl_cur_card_hint = ttk.Label(
            ctrl_bar, text="画笔:未选", foreground="#555555", font=("Microsoft YaHei", 9)
        )
        self.lbl_cur_card_hint.pack(side="left", padx=6)
        self.lbl_clear_count = ttk.Label(
            ctrl_bar, text="🏆 已刷: 0 次", foreground="#1565c0", font=("Microsoft YaHei", 10, "bold")
        )
        self.lbl_clear_count.pack(side="left", padx=6)
        ttk.Button(ctrl_bar, text="清零", width=4, command=self._reset_clear_count).pack(side="left", padx=2)
        ttk.Label(ctrl_bar, text="目标:", font=("Microsoft YaHei", 9)).pack(side="left", padx=(4, 1))
        self.var_target_clears = tk.StringVar(value="0")
        self.spn_target_clears = ttk.Spinbox(
            ctrl_bar, from_=0, to=9999, width=4, textvariable=self.var_target_clears,
            command=self._on_target_clears_change,
        )
        self.spn_target_clears.pack(side="left", padx=1)
        self.spn_target_clears.bind("<Return>", lambda _: self._on_target_clears_change())
        self.spn_target_clears.bind("<FocusOut>", lambda _: self._on_target_clears_change())
        self.spn_target_clears.bind("<KeyRelease>", lambda _: self._on_target_clears_change(silent_invalid=True))
        ttk.Label(ctrl_bar, text="(0无限)", foreground="#777777", font=("Microsoft YaHei", 8)).pack(side="left", padx=(1, 4))
        self.lbl_bot_progress = ttk.Label(
            ctrl_bar, text="执行进度：未运行", foreground="#d84315", font=("Microsoft YaHei", 9, "bold")
        )
        self.lbl_bot_progress.pack(side="left", padx=8)

        self.txt_log = tk.Text(bot_frame, height=4, font=("Consolas", 9))
        self.txt_log.pack(fill="x", pady=3)
        self.log(f"欢迎使用刷关模拟器 {APP_VERSION}！支持自动检测游戏画面、多账号独立卡组、双号组队联刷与三层智能补阵，按 F11 即可开始后台自动闯关。")

        # 3. 中部：左右分栏（自动填满剩余高度）
        mid_pane = ttk.PanedWindow(self.root, orient="horizontal")
        mid_pane.pack(fill="both", expand=True, padx=8, pady=2)

        # --- 左侧：实时画面与交互画布 ---
        left_frame = ttk.LabelFrame(mid_pane, text="实时游戏画面预览（左键按下方模式操作 | 右键拖拽框选识别按钮）", padding=6)
        mid_pane.add(left_frame, weight=3)

        mode_bar1 = ttk.Frame(left_frame)
        mode_bar1.pack(fill="x", pady=1)
        ttk.Label(mode_bar1, text="左键模式:").pack(side="left", padx=2)
        modes_row1 = [
            ("🖱测试点击", "test_click"),
            ("🧑设角色位", "set_hero"),
            ("🃏录入新卡", "add_card"),
            ("🔄改卡坐标", "update_card_xy"),
        ]
        for txt, val in modes_row1:
            ttk.Radiobutton(mode_bar1, text=txt, value=val, variable=self.click_pick_mode).pack(side="left", padx=3)

        mode_bar2 = ttk.Frame(left_frame)
        mode_bar2.pack(fill="x", pady=1)
        modes_row2 = [
            ("🟢加放卡点", "add_place"),
            ("🔵改选中落点", "update_place_xy"),
            ("📌加进图步", "add_enter"),
            ("🏁加收尾步", "add_finish"),
        ]
        for txt, val in modes_row2:
            ttk.Radiobutton(mode_bar2, text=txt, value=val, variable=self.click_pick_mode).pack(side="left", padx=3)

        self.canvas = tk.Canvas(left_frame, bg="#1e1e1e", width=620, height=440, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True, pady=2)
        self.canvas.bind("<Button-1>", self._on_canvas_left_click)
        self.canvas.bind("<ButtonPress-3>", self._on_canvas_right_down)
        self.canvas.bind("<B3-Motion>", self._on_canvas_right_drag)
        self.canvas.bind("<ButtonRelease-3>", self._on_canvas_right_up)
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        # --- 右侧：4 个核心功能页签 ---
        right_frame = ttk.Frame(mid_pane)
        mid_pane.add(right_frame, weight=2)

        self.notebook = ttk.Notebook(right_frame)
        self.notebook.pack(fill="both", expand=True)

        self._build_tab_cards()
        self._build_tab_placements()
        self._build_tab_enter()
        self._build_tab_finish()
        self._build_tab_accounts()

    # ---- Tab 1: 卡组卡片库 ----
    def _build_tab_cards(self):
        tab = ttk.Frame(self.notebook, padding=5)
        self.notebook.add(tab, text="1.卡片库")

        self.lbl_cards_tip = ttk.Label(
            tab,
            text="📌 进战斗选【🃏录入新卡】，点左侧顶部卡槽即可保存（自动截小图标）",
            foreground="#006600",
        )
        self.lbl_cards_tip.pack(anchor="w", pady=1)

        # 底部操作按钮优先 side="bottom" 固定，小窗模式下绝不会被挤出界面！
        bar2 = ttk.Frame(tab)
        bar2.pack(side="bottom", fill="x", pady=2)
        ttk.Button(bar2, text="🏷切分层", command=self._edit_card_role).pack(side="left", padx=2)
        ttk.Button(bar2, text="⚡测点卡槽", command=self._test_click_card).pack(side="left", padx=2)
        ttk.Button(bar2, text="➡用选中卡去布阵", command=self._go_place_with_selected_card).pack(side="left", padx=2)

        bar1 = ttk.Frame(tab)
        bar1.pack(side="bottom", fill="x", pady=2)
        ttk.Button(bar1, text="➕录新卡", command=lambda: self._switch_pick_mode("add_card")).pack(side="left", padx=2)
        ttk.Button(bar1, text="✏改名/火苗", command=self._rename_card).pack(side="left", padx=2)
        ttk.Button(bar1, text="🔄改坐标", command=lambda: self._switch_pick_mode("update_card_xy")).pack(side="left", padx=2)
        ttk.Button(bar1, text="🗑删卡", command=self._delete_card).pack(side="left", padx=2)

        self.tree_cards = ttk.Treeview(tab, columns=("name", "role", "cost", "xy"), show="tree headings", height=6)
        self.tree_cards.heading("#0", text="图标")
        self.tree_cards.column("#0", width=46, anchor="center")
        self.tree_cards.heading("name", text="卡片名")
        self.tree_cards.column("name", width=78, anchor="center")
        self.tree_cards.heading("role", text="补阵定位")
        self.tree_cards.column("role", width=96, anchor="center")
        self.tree_cards.heading("cost", text="火苗")
        self.tree_cards.column("cost", width=52, anchor="center")
        self.tree_cards.heading("xy", text="卡槽坐标")
        self.tree_cards.column("xy", width=82, anchor="center")
        self.tree_cards.bind("<Double-1>", lambda _e: self._edit_card_role())
        style = ttk.Style()
        style.configure("Cards.Treeview", rowheight=34)
        self.tree_cards.configure(style="Cards.Treeview")
        self.tree_cards.pack(fill="both", expand=True, pady=3)
        self.tree_cards.bind("<<TreeviewSelect>>", self._on_card_tree_select)

    # ---- Tab 2: 自由放卡布阵 ----
    def _build_tab_placements(self):
        tab = ttk.Frame(self.notebook, padding=5)
        self.notebook.add(tab, text="2.放卡布阵")

        # 开局先放置角色配置区
        hero_frame = ttk.LabelFrame(tab, text="开局先放置角色（进战斗后先放人物到指定格子，再开始下卡）", padding=4)
        hero_frame.pack(fill="x", pady=2)

        hrow1 = ttk.Frame(hero_frame)
        hrow1.pack(fill="x", pady=1)
        self.var_hero_en = tk.BooleanVar(value=True)
        self.var_hero_cont = tk.BooleanVar(value=True)
        self.var_hero_start = tk.BooleanVar(value=False)
        ttk.Checkbutton(hrow1, text="开局先放角色", variable=self.var_hero_en, command=self._save_hero_ui).pack(side="left", padx=3)
        ttk.Checkbutton(hrow1, text="继续战斗后也放", variable=self.var_hero_cont, command=self._save_hero_ui).pack(side="left", padx=3)
        ttk.Checkbutton(hrow1, text="按F11启动立即先放", variable=self.var_hero_start, command=self._save_hero_ui).pack(side="left", padx=3)

        hrow2 = ttk.Frame(hero_frame)
        hrow2.pack(fill="x", pady=2)
        self.lbl_hero_xy = ttk.Label(hrow2, text="落点:(960,660)", foreground="#e65100", font=("Microsoft YaHei", 9, "bold"))
        self.lbl_hero_xy.pack(side="left", padx=2)
        ttk.Label(hrow2, text="加载等(s):").pack(side="left")
        self.ent_hero_wait = ttk.Entry(hrow2, width=4)
        self.ent_hero_wait.pack(side="left", padx=1)
        ttk.Label(hrow2, text="放后等(s):").pack(side="left")
        self.ent_hero_wait_after = ttk.Entry(hrow2, width=4)
        self.ent_hero_wait_after.pack(side="left", padx=1)
        ttk.Label(hrow2, text="补点:").pack(side="left")
        self.ent_hero_clicks = ttk.Entry(hrow2, width=2)
        self.ent_hero_clicks.pack(side="left", padx=1)
        ttk.Button(hrow2, text="保存", width=4, command=self._save_hero_ui).pack(side="left", padx=2)
        ttk.Button(hrow2, text="🧑 设角色位", command=lambda: self._switch_pick_mode("set_hero")).pack(side="left", padx=2)
        ttk.Button(hrow2, text="⚡ 测放", width=6, command=self._test_place_hero).pack(side="left", padx=1)

        # 快捷选卡按钮区
        quick_frame = ttk.LabelFrame(tab, text="选好卡片后点左侧场地添加放卡点", padding=3)
        quick_frame.pack(fill="x", pady=2)
        self.quick_cards_box = ttk.Frame(quick_frame)
        self.quick_cards_box.pack(fill="x")

        # 底部选项与单步编辑区优先 side="bottom" 固定，小窗模式下绝不被挤出！
        self.var_auto_fire = tk.BooleanVar(value=self.config.get("auto_collect_fire", False))
        self.var_wait_fire = tk.BooleanVar(value=self.config.get("wait_for_fire", True))
        self.var_verify_placed = tk.BooleanVar(value=self.config.get("verify_placed", True))
        self.var_loop_place = tk.BooleanVar(value=self.config.get("loop_placements", False))

        smart_opts_bar = ttk.Frame(tab)
        smart_opts_bar.pack(side="bottom", fill="x", pady=1)
        ttk.Checkbutton(
            smart_opts_bar,
            text="🧠 回点验亮确认放卡",
            variable=self.var_verify_placed,
            command=self._update_fire_cfg,
        ).pack(side="left", padx=2)
        ttk.Checkbutton(
            smart_opts_bar,
            text="🔁 三层智能补阵",
            variable=self.var_loop_place,
            command=self._update_fire_cfg,
        ).pack(side="left", padx=4)

        fire_opts_bar = ttk.Frame(tab)
        fire_opts_bar.pack(side="bottom", fill="x", pady=1)
        ttk.Checkbutton(
            fire_opts_bar,
            text="后台扫火苗",
            variable=self.var_auto_fire,
            command=self._update_fire_cfg,
        ).pack(side="left", padx=2)
        ttk.Checkbutton(
            fire_opts_bar,
            text="🔥 按火苗消耗等火",
            variable=self.var_wait_fire,
            command=self._update_fire_cfg,
        ).pack(side="left", padx=6)

        # 单步编辑调整区（自由改点击哪张卡、放哪里、等待时间）
        edit_frame = ttk.LabelFrame(tab, text="调整选中放卡步骤", padding=4)
        edit_frame.pack(side="bottom", fill="x", pady=2)

        erow1 = ttk.Frame(edit_frame)
        erow1.pack(fill="x", pady=1)
        ttk.Label(erow1, text="卡:").pack(side="left")
        self.edit_card_combo = ttk.Combobox(erow1, width=10, state="readonly")
        self.edit_card_combo.pack(side="left", padx=2)
        ttk.Label(erow1, text="X:").pack(side="left")
        self.ent_px = ttk.Entry(erow1, width=5)
        self.ent_px.pack(side="left", padx=1)
        ttk.Label(erow1, text="Y:").pack(side="left")
        self.ent_py = ttk.Entry(erow1, width=5)
        self.ent_py.pack(side="left", padx=1)
        ttk.Label(erow1, text="等:").pack(side="left")
        self.ent_delay = ttk.Entry(erow1, width=4)
        self.ent_delay.pack(side="left", padx=1)
        ttk.Button(erow1, text="✔应用", width=6, command=self._apply_place_edit).pack(side="left", padx=2)

        erow2 = ttk.Frame(edit_frame)
        erow2.pack(fill="x", pady=1)
        ttk.Button(erow2, text="🔵改点", width=6, command=lambda: self._switch_pick_mode("update_place_xy")).pack(side="left", padx=1)
        ttk.Button(erow2, text="⬆", width=3, command=lambda: self._move_place_step(-1)).pack(side="left", padx=1)
        ttk.Button(erow2, text="⬇", width=3, command=lambda: self._move_place_step(1)).pack(side="left", padx=1)
        ttk.Button(erow2, text="🎯移至", width=6, command=self._move_place_to_index).pack(side="left", padx=1)
        ttk.Button(erow2, text="⏯开关", width=6, command=self._toggle_place_enabled).pack(side="left", padx=1)
        ttk.Button(erow2, text="🗑删", width=4, command=self._del_place_step).pack(side="left", padx=1)
        ttk.Button(erow2, text="⏱全改", width=6, command=self._batch_set_delay).pack(side="left", padx=1)
        ttk.Button(erow2, text="⚡测", width=4, command=self._test_single_place).pack(side="left", padx=1)

        erow3 = ttk.Frame(edit_frame)
        erow3.pack(fill="x", pady=1)
        self.var_insert_after = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            erow3,
            text="📌 添加新步时直接插入到【当前选中行之后】",
            variable=self.var_insert_after,
        ).pack(side="left", padx=2)
        ttk.Button(erow3, text="📐对齐新浏览器坐标", command=self._open_rescale_coords_dialog).pack(side="right", padx=2)
        ttk.Button(erow3, text="🔄批量换卡", command=self._batch_replace_place_card).pack(side="right", padx=2)

        # 放卡步骤列表（自动填充中间剩余高度）
        self.tree_place = ttk.Treeview(
            tab, columns=("idx", "enabled", "card", "pos", "delay"), show="headings", height=5
        )
        for col, title, w in [
            ("idx", "序", 32),
            ("enabled", "启", 32),
            ("card", "点击哪张卡", 132),
            ("pos", "放到哪里", 90),
            ("delay", "等(s)", 46),
        ]:
            self.tree_place.heading(col, text=title)
            self.tree_place.column(col, width=w, anchor="center")
        self.tree_place.pack(fill="both", expand=True, pady=2)
        self.tree_place.bind("<<TreeviewSelect>>", self._on_place_tree_select)
        self.tree_place.bind("<Button-3>", self._show_place_context_menu)

        # 右键快捷菜单（方便在中间快速插入、复制、瞬移序号）
        self.place_menu = tk.Menu(self.root, tearoff=0)
        self.place_menu.add_command(label="🎯 移动到指定序号...", command=self._move_place_to_index)
        self.place_menu.add_command(label="📋 在下方复制这一步", command=self._duplicate_place_step)
        self.place_menu.add_command(label="🔁 设补阵替换卡（复制卡改补本体）...", command=self._set_place_repair_card)
        self.place_menu.add_command(label="🔄 将本卡所有落点批量换为...", command=self._batch_replace_place_card)
        self.place_menu.add_command(label="⏯ 启用 / 禁用", command=self._toggle_place_enabled)
        self.place_menu.add_separator()
        self.place_menu.add_command(label="🗑 删除这一步", command=self._del_place_step)

    # ---- Tab 3: 自动选卡组进图 ----
    def _build_tab_enter(self):
        tab = ttk.Frame(self.notebook, padding=5)
        self.notebook.add(tab, text="3.选卡开战")

        ttk.Label(tab, text="识别到房间界面时依次点击（可按关卡自定义）：").pack(anchor="w")

        bar = ttk.Frame(tab)
        bar.pack(side="bottom", fill="x", pady=2)
        ttk.Button(bar, text="➕添加点击点", command=lambda: self._switch_pick_mode("add_enter")).pack(side="left", padx=2)
        ttk.Button(bar, text="🗑删选中", command=self._del_enter_step).pack(side="left", padx=2)
        ttk.Button(bar, text="🚀测试开战", command=self._test_run_enter).pack(side="left", padx=4)

        self.tree_enter = ttk.Treeview(tab, columns=("name", "x", "y", "delay"), show="headings", height=6)
        for col, title, w in [("name", "步骤说明", 150), ("x", "X", 55), ("y", "Y", 55), ("delay", "等(s)", 50)]:
            self.tree_enter.heading(col, text=title)
            self.tree_enter.column(col, width=w, anchor="center")
        self.tree_enter.pack(fill="both", expand=True, pady=3)

    # ---- Tab 4: 继续战斗与结束收尾 ----
    def _build_tab_finish(self):
        tab = ttk.Frame(self.notebook, padding=5)
        self.notebook.add(tab, text="4.继续与收尾")

        self.lbl_finish_tip = ttk.Label(
            tab,
            text="右键框选保存识别模板（4张模板与收尾步骤默认全关卡通用）：",
            foreground="#333333",
        )
        self.lbl_finish_tip.pack(anchor="w")

        tpl_bar = ttk.Frame(tab)
        tpl_bar.pack(fill="x", pady=2)
        self.lbl_templates = ttk.Label(tpl_bar, text="", foreground="blue")
        self.lbl_templates.pack(side="left")
        ttk.Button(tpl_bar, text="清专属", width=7, command=self._clear_profile_templates).pack(side="right", padx=2)
        self._refresh_template_status()

        self.var_continue_resets = tk.BooleanVar(value=self.config.get("continue_resets_battle", False))
        ttk.Checkbutton(
            tab,
            text="点【继续战斗】后视为新一局重摆(深渊岛等连战图别勾！)",
            variable=self.var_continue_resets,
            command=self._update_fire_cfg,
        ).pack(anchor="w", pady=2)

        ttk.Label(tab, text="检测到【战斗结束/翻牌】后执行的收尾点击：").pack(anchor="w")

        bar = ttk.Frame(tab)
        bar.pack(side="bottom", fill="x", pady=2)
        ttk.Button(bar, text="➕加收尾点", command=lambda: self._switch_pick_mode("add_finish")).pack(side="left", padx=2)
        ttk.Button(bar, text="⏱改等待", command=self._edit_finish_delay).pack(side="left", padx=2)
        ttk.Button(bar, text="🗑删选中", command=self._del_finish_step).pack(side="left", padx=2)
        ttk.Button(bar, text="⚡测收尾", command=self._test_run_finish).pack(side="left", padx=3)

        self.tree_finish = ttk.Treeview(tab, columns=("name", "x", "y", "delay"), show="headings", height=5)
        for col, title, w in [("name", "收尾步骤", 130), ("x", "X", 55), ("y", "Y", 55), ("delay", "等(s)", 50)]:
            self.tree_finish.heading(col, text=title)
            self.tree_finish.column(col, width=w, anchor="center")
        self.tree_finish.pack(fill="both", expand=True, pady=3)
        self._reload_finish_tree()

    # ---- Tab 5: 多账号独立浏览器启动 & 加密账密自动登录 ----
    def _build_tab_accounts(self):
        tab = ttk.Frame(self.notebook, padding=5)
        self.notebook.add(tab, text="5.账号登录")

        # 浏览器路径与登录网址栏
        brow = ttk.Frame(tab)
        brow.pack(fill="x", pady=2)
        detected = detect_ffbrowser_exe(self.config.get("ffbrowser_path", ""))
        if detected and not self.config.get("ffbrowser_path"):
            self.config["ffbrowser_path"] = detected
        self.lbl_ff_path = ttk.Label(
            brow,
            text=f"浏览器: {os.path.basename(detected) if detected else '未找到FFBrowser'}",
            font=("Microsoft YaHei", 9, "bold"),
        )
        self.lbl_ff_path.pack(side="left", padx=2)
        ttk.Button(brow, text="📂数据", width=6, command=lambda: os.startfile(DATA_DIR)).pack(side="right", padx=1)
        ttk.Button(brow, text="📥继承旧版", width=9, command=self._import_legacy_version_data).pack(side="right", padx=2)
        ttk.Button(brow, text="📂选浏览器", width=9, command=self._choose_ffbrowser_path).pack(side="right", padx=2)

        urow = ttk.Frame(tab)
        urow.pack(fill="x", pady=2)
        ttk.Label(urow, text="网址:").pack(side="left", padx=2)
        self.ent_login_url = ttk.Entry(urow)
        self.ent_login_url.insert(0, self.config.get("login_url") or DEFAULT_LOGIN_URL)
        self.ent_login_url.pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(urow, text="保存", width=5, command=self._save_login_url).pack(side="left", padx=2)

        # 底部：登录页点位配置（优先 side="bottom" 固定）
        pt_frame = ttk.LabelFrame(tab, text="登录页点位（登录页录一次，全账号共用；密码本机加密存盘）", padding=4)
        pt_frame.pack(side="bottom", fill="x", pady=2)

        self.lbl_login_pts = ttk.Label(pt_frame, text="", font=("Microsoft YaHei", 8))
        self.lbl_login_pts.pack(anchor="w", pady=1)

        prow1 = ttk.Frame(pt_frame)
        prow1.pack(fill="x", pady=1)
        ttk.Button(prow1, text="📍弹登录", width=7, command=lambda: self._switch_pick_mode("pick_login_open")).pack(side="left", padx=1)
        ttk.Button(prow1, text="📍切登录", width=7, command=lambda: self._switch_pick_mode("pick_login_tab")).pack(side="left", padx=1)
        ttk.Button(prow1, text="📍账号框", width=7, command=lambda: self._switch_pick_mode("pick_login_user")).pack(side="left", padx=1)
        ttk.Button(prow1, text="📍密码框", width=7, command=lambda: self._switch_pick_mode("pick_login_pass")).pack(side="left", padx=1)
        ttk.Button(prow1, text="📍登录钮", width=7, command=lambda: self._switch_pick_mode("pick_login_submit")).pack(side="left", padx=1)
        ttk.Button(prow1, text="➕进服", width=6, command=lambda: self._switch_pick_mode("add_login_after")).pack(side="left", padx=1)
        ttk.Button(prow1, text="🗑清", width=3, command=self._clear_login_after_clicks).pack(side="left", padx=1)

        prow2 = ttk.Frame(pt_frame)
        prow2.pack(fill="x", pady=1)
        self.var_auto_login_bot = tk.BooleanVar(value=bool(self.config.get("auto_login_on_bot", False)))
        ttk.Checkbutton(
            prow2,
            text="挂机识别到【登录页】模板(stage_login.png)自动填选中账号重登",
            variable=self.var_auto_login_bot,
            command=self._save_auto_login_flag,
        ).pack(side="left", padx=2)

        # 账号操作按钮栏（优先 side="bottom" 固定）
        abar2 = ttk.Frame(tab)
        abar2.pack(side="bottom", fill="x", pady=2)
        ttk.Button(abar2, text="🚀启动独立FFBrowser", command=self._launch_selected_account_browser).pack(side="left", padx=2)
        ttk.Button(abar2, text="👁看此账号", width=9, command=self._view_selected_account_window).pack(side="left", padx=2)
        ttk.Button(abar2, text="🔑后台自动登录", command=self._run_selected_account_login).pack(side="left", padx=2)

        abar1 = ttk.Frame(tab)
        abar1.pack(side="bottom", fill="x", pady=2)
        ttk.Button(abar1, text="➕加号", width=6, command=self._add_account).pack(side="left", padx=1)
        ttk.Button(abar1, text="✏改", width=4, command=self._edit_account).pack(side="left", padx=1)
        ttk.Button(abar1, text="🗑删", width=4, command=self._delete_account).pack(side="left", padx=1)
        ttk.Button(abar1, text="👑切角色", width=8, command=self._cycle_account_role).pack(side="left", padx=2)
        ttk.Button(abar1, text="☑选联刷", width=8, command=self._toggle_account_team_enabled).pack(side="left", padx=1)
        ttk.Button(abar1, text="📋跨号复制", width=9, command=self._copy_deck_from_other_account).pack(side="right", padx=1)

        # 中部：账号列表（含组队角色与参与联刷开关）
        self.tree_accounts = ttk.Treeview(tab, columns=("name", "user", "role", "team", "pwd"), show="headings", height=5)
        for col, title, w in [
            ("name", "账号备注", 74),
            ("user", "7k7k账号", 95),
            ("role", "组队角色", 62),
            ("team", "联刷", 42),
            ("pwd", "密码", 58),
        ]:
            self.tree_accounts.heading(col, text=title)
            self.tree_accounts.column(col, width=w, anchor="center")
        self.tree_accounts.pack(fill="both", expand=True, pady=2)
        self.tree_accounts.bind("<<TreeviewSelect>>", self._on_account_select)
        self.tree_accounts.bind("<Double-1>", lambda _: self._view_selected_account_window())
        self._reload_accounts_tree()
        self._refresh_login_pts_label()

    def log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass
        if "🏆" in msg:
            tag = "trophy"
        elif "✅" in msg or "🎉" in msg:
            tag = "ok"
        elif "🔥" in msg:
            tag = "fire"
        elif "⚠" in msg or "失败" in msg or "异常" in msg:
            tag = "warn"
        elif any(k in msg for k in ("🚀", "⏹", "👻", "👁", "🎨")):
            tag = "info"
        else:
            tag = "normal"

        def _append():
            self.txt_log.insert("end", f"[{ts}] ", "ts")
            self.txt_log.insert("end", f"{msg}\n", tag)
            self.txt_log.see("end")

        self.root.after(0, _append)

    def _switch_pick_mode(self, mode: str):
        self.click_pick_mode.set(mode)
        hints = {
            "set_hero": "已切换为【设定开局角色放置点】模式：请直接左键点击左侧实时游戏画面中要放人物的格子！",
            "add_card": "已切换为【录入新卡片】模式：请直接左键点击左侧实时画面顶部的一张卡片槽！",
            "update_card_xy": "已切换为【更新卡片坐标】模式：请左键点击左侧画面中该卡的新卡槽位置！",
            "add_place": f"已切换为【放置卡片】模式：当前选中【{self.var_selected_card.get()}】，请左键点击左侧游戏场地添加落点！",
            "update_place_xy": "已切换为【修改放卡新位置】模式：请左键点击左侧游戏场地的新格子位置！",
            "add_enter": "已切换为【添加选卡/进图步骤】模式：请左键点击左侧画面按钮！",
            "add_finish": "已切换为【添加结束收尾步骤】模式：请左键点击左侧画面翻牌/确定位置！",
            "pick_login_open": "已切换为【设定弹出登录框按钮(可选)】：请左键点击网页左上角【登录】或中间【PLAY】按钮！",
            "pick_login_tab": "已切换为【设定切回账号登录标签(防误进注册页)】：请左键点击弹窗里的【登录/账号登录】切换标签！",
            "pick_login_user": "已切换为【设定7k7k账号输入框】：请直接左键点击左侧登录画面中的【账号输入框】！",
            "pick_login_pass": "已切换为【设定7k7k密码输入框】：请直接左键点击左侧登录画面中的【密码输入框】！",
            "pick_login_submit": "已切换为【设定7k7k登录按钮】：请直接左键点击左侧登录画面中的【登录按钮】！",
            "add_login_after": "已切换为【添加登录后进服点】：请左键点击登录成功后需要点击的【进入游戏/区服】位置！",
        }
        if mode in hints:
            self.log(hints[mode])

    # ==================== 独立关卡方案增删改 / 复制 / 导出 / 导入（按当前账号隔离） ====================
    def _refresh_deck_ui(self):
        decks, owner, _ = self._get_active_decks_store()
        names = list(decks.keys())
        self.deck_combo["values"] = names
        cur = self.var_active_deck.get()
        if cur not in decks and names:
            saved = owner.get("active_deck", "")
            self.var_active_deck.set(saved if saved in decks else names[0])
        owner["active_deck"] = self.var_active_deck.get()
        self._reload_hero_ui()
        self._reload_options_ui()
        self._reload_cards_tree()
        self._reload_quick_card_buttons()
        self._reload_place_tree()
        self._reload_enter_tree()
        self._reload_finish_tree()
        self._refresh_template_status()
        self._redraw_canvas_overlays()

    def _reload_options_ui(self):
        opts = self.get_cur_options()
        self.var_auto_fire.set(bool(opts.get("auto_collect_fire", False)))
        self.var_wait_fire.set(bool(opts.get("wait_for_fire", True)))
        self.var_verify_placed.set(bool(opts.get("verify_placed", True)))
        self.var_loop_place.set(bool(opts.get("loop_placements", False)))
        self.var_continue_resets.set(bool(opts.get("continue_resets_battle", False)))

    def _reload_hero_ui(self):
        h = self.get_cur_deck()["hero"]
        self.var_hero_en.set(bool(h.get("enabled", True)))
        self.var_hero_cont.set(bool(h.get("on_continue", True)))
        self.var_hero_start.set(bool(h.get("on_start", False)))
        self.lbl_hero_xy.config(text=f"落点:({h.get('x', 960)},{h.get('y', 660)})")
        self.ent_hero_wait.delete(0, "end")
        self.ent_hero_wait.insert(0, str(h.get("wait_before", 3.0)))
        self.ent_hero_wait_after.delete(0, "end")
        self.ent_hero_wait_after.insert(0, str(h.get("wait_after", 4.0)))
        self.ent_hero_clicks.delete(0, "end")
        self.ent_hero_clicks.insert(0, str(h.get("clicks", 2)))

    def _save_hero_ui(self):
        h = self.get_cur_deck()["hero"]
        h["enabled"] = bool(self.var_hero_en.get())
        h["on_continue"] = bool(self.var_hero_cont.get())
        h["on_start"] = bool(self.var_hero_start.get())
        try:
            h["wait_before"] = max(0.0, float(self.ent_hero_wait.get().strip()))
        except Exception:
            pass
        try:
            h["wait_after"] = max(0.0, float(self.ent_hero_wait_after.get().strip()))
        except Exception:
            pass
        try:
            h["clicks"] = max(1, int(self.ent_hero_clicks.get().strip()))
        except Exception:
            pass
        self._redraw_canvas_overlays()
        self.save_config(silent=True)

    def _test_place_hero(self):
        threading.Thread(target=self._exec_place_hero, kwargs={"wait": False, "wait_after": False}, daemon=True).start()

    def _create_deck(self):
        decks, _, acc_lbl = self._get_active_decks_store()
        scope = f"（归属账号：{acc_lbl}）" if acc_lbl else ""
        name = simpledialog.askstring("新建独立关卡方案", f"请输入新关卡方案名称{scope}（如：城堡、海盗船、魔塔）：")
        if not name:
            return
        name = name.strip()
        if name in decks:
            messagebox.showwarning("提示", "该账号下已存在同名方案！")
            return
        decks[name] = _make_blank_deck()
        self.var_active_deck.set(name)
        self._refresh_deck_ui()
        self.save_config()

        self.log(f"✅ 已新建独立关卡方案【{name}】{scope}")

    def _clone_deck(self):
        decks, _, acc_lbl = self._get_active_decks_store()
        src_name = self.var_active_deck.get()
        new_name = simpledialog.askstring(
            "复制当前关卡方案",
            f"将【{src_name}】的卡组、布阵、开关与专属模板完整复制为新方案：",
            initialvalue=f"{src_name}_副本",
        )
        if not new_name:
            return
        new_name = new_name.strip()
        if new_name in decks:
            messagebox.showwarning("提示", "目标名称已存在！")
            return
        decks[new_name] = copy.deepcopy(self.get_cur_deck())
        # 同步复制专属模板目录
        src_tpl = os.path.join(PROFILE_TPL_ROOT, _safe_profile_dirname(src_name))
        dst_tpl = os.path.join(PROFILE_TPL_ROOT, _safe_profile_dirname(new_name))
        if os.path.isdir(src_tpl):
            os.makedirs(dst_tpl, exist_ok=True)
            for fn in os.listdir(src_tpl):
                sp = os.path.join(src_tpl, fn)
                if os.path.isfile(sp):
                    shutil.copy2(sp, os.path.join(dst_tpl, fn))
        self.var_active_deck.set(new_name)
        self._refresh_deck_ui()
        self.save_config()

        self.log(f"📑 已完整复制方案【{src_name}】->【{new_name}】")

    def _rename_deck(self):
        decks, _, _ = self._get_active_decks_store()
        old_name = self.var_active_deck.get()
        new_name = simpledialog.askstring("重命名关卡方案", "请输入新的方案名称：", initialvalue=old_name)
        if not new_name or new_name.strip() == old_name:
            return
        new_name = new_name.strip()
        if new_name in decks:
            messagebox.showwarning("提示", "目标名称已存在！")
            return
        decks[new_name] = decks.pop(old_name)
        old_tpl = os.path.join(PROFILE_TPL_ROOT, _safe_profile_dirname(old_name))
        new_tpl = os.path.join(PROFILE_TPL_ROOT, _safe_profile_dirname(new_name))
        if os.path.isdir(old_tpl) and not os.path.exists(new_tpl):
            try:
                os.rename(old_tpl, new_tpl)
            except Exception:
                pass
        self.var_active_deck.set(new_name)
        self._refresh_deck_ui()
        self.save_config()


    def _delete_deck(self):
        decks, _, _ = self._get_active_decks_store()
        if len(decks) <= 1:
            messagebox.showwarning("提示", "当前账号至少保留一套关卡方案！")
            return
        name = self.var_active_deck.get()
        if messagebox.askyesno("确认删除", f"确定删除关卡方案【{name}】及其专属配置吗？"):
            del decks[name]
            self.var_active_deck.set(next(iter(decks.keys())))
            self._refresh_deck_ui()
            self.save_config()

    def _export_deck(self):
        name = self.var_active_deck.get()
        ts = time.strftime("%Y%m%d_%H%M%S")
        default_file = f"关卡方案_{_safe_profile_dirname(name)}_{ts}.json"
        save_path = filedialog.asksaveasfilename(
            title="导出备份当前关卡方案",
            initialdir=BACKUP_DIR,
            initialfile=default_file,
            defaultextension=".json",
            filetypes=[("关卡方案配置 (*.json)", "*.json")],
        )
        if not save_path:
            return
        payload = {
            "profile_name": name,
            "deck": copy.deepcopy(self.get_cur_deck()),
            "fire_ocr_roi": self.config.get("fire_ocr_roi"),
        }
        try:
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            self.log(f"💾 已导出关卡方案【{name}】到 {save_path}")
            messagebox.showinfo("导出成功", f"已成功备份方案【{name}】到：\n{save_path}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def _import_deck(self):
        open_path = filedialog.askopenfilename(
            title="导入关卡方案 (.json)",
            initialdir=BACKUP_DIR,
            filetypes=[("关卡方案配置 (*.json)", "*.json")],
        )
        if not open_path:
            return
        try:
            with open(open_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if "deck" not in payload:
                messagebox.showwarning("格式提示", "所选文件不是有效的单关卡方案导出文件！")
                return
            init_name = payload.get("profile_name", "导入方案")
            name = simpledialog.askstring("导入关卡方案", "请为导入的关卡方案命名：", initialvalue=init_name)
            if not name:
                return
            name = name.strip()
            decks, _, acc_lbl = self._get_active_decks_store()
            if name in decks and not messagebox.askyesno("覆盖确认", f"方案【{name}】已存在，是否覆盖？"):
                return
            decks[name] = payload["deck"]
            if payload.get("fire_ocr_roi") and not self.config.get("fire_ocr_roi"):
                self.config["fire_ocr_roi"] = payload["fire_ocr_roi"]
            self.var_active_deck.set(name)
            self._refresh_deck_ui()
            self.save_config()
            scope = f"到账号【{acc_lbl}】" if acc_lbl else ""
            self.log(f"📂 已成功导入关卡方案【{name}】{scope}")
        except Exception as e:
            messagebox.showerror("导入失败", str(e))

    def _get_profile_to_name_map(self) -> dict:
        mp = {}
        for a in self.config.get("accounts", []):
            pk = _safe_profile_dirname(a.get("profile_dir") or a.get("id") or "").lower()
            if pk:
                mp[pk] = a.get("name") or pk
        return mp

    # ==================== 窗口绑定与热键 ====================
    def _refresh_window_list(self, silent: bool = False):
        self.win_candidates = find_fcbrowser_windows(self._get_profile_to_name_map())
        items = [desc for _, desc, _, _ in self.win_candidates]
        self.win_combo["values"] = items
        if self.win_candidates:
            # 按智能评分选出最优游戏渲染层（优先 FCBrowser/FFBrowser + 美食大战老鼠 + 最大可见子渲染层）
            best_idx = max(range(len(self.win_candidates)), key=lambda i: self.win_candidates[i][2])
            best_hwnd, best_desc, best_score, best_prof = self.win_candidates[best_idx]
            prev_hwnd = self.hwnd
            self.win_combo.current(best_idx)
            self.hwnd = best_hwnd
            cls = get_class_name(best_hwnd)
            acc_lbl = self._get_profile_to_name_map().get(best_prof, "")
            tag = f"【{acc_lbl}】" if acc_lbl else ""
            self.lbl_hwnd.config(text=f"已自动绑定{tag} HWND: {self.hwnd} ({cls})")
            if best_hwnd != prev_hwnd:
                self._auto_crop_tried = False
                CAPTURER.reset_cache(best_hwnd)
                if not silent:
                    self.log(f"🎯 已自动检测到游戏画面并锁定{tag} HWND={best_hwnd} ({cls})")
        else:
            self.hwnd = 0
            self.lbl_hwnd.config(text="等待检测游戏画面（打开浏览器自动锁定，或按 F8）")

    def _on_combo_select(self, _):
        idx = self.win_combo.current()
        if 0 <= idx < len(self.win_candidates):
            self.hwnd = self.win_candidates[idx][0]
            prof_k = self.win_candidates[idx][3]
            acc_lbl = self._get_profile_to_name_map().get(prof_k, "")
            tag = f"【{acc_lbl}】" if acc_lbl else ""
            self._auto_crop_tried = False
            self.lbl_hwnd.config(text=f"当前绑定{tag} HWND: {self.hwnd} ({get_class_name(self.hwnd)})")
            self.refresh_preview()

    def toggle_stealth(self):
        """一键开启/关闭全部已打开游戏浏览器窗口的【隐身透明 + 鼠标穿透 + 沉底】（兼容单开与双号/多号多开！）"""
        if self._stealth_active:
            entries = list(self._stealth_entries)
            if not entries and self._stealth_root_hwnd:
                entries = [(self._stealth_root_hwnd, self._stealth_orig_exstyle)]
            restored = 0
            for rh, st in entries:
                ok, _ = set_window_stealth(rh, False, st)
                if ok:
                    restored += 1
            self._stealth_active = False
            self._stealth_root_hwnd = 0
            self._stealth_orig_exstyle = None
            self._stealth_entries = []
            self.btn_stealth.config(
                text="👻隐身穿透(F10)",
                bg=self._cur_theme()["stealth_bg"],
                activebackground=self._cur_theme()["stealth_bg"],
            )
            self.log(f"👁 已恢复 {restored} 个游戏浏览器窗口的正常显示与鼠标操作。")
        else:
            if not self.hwnd or not user32.IsWindow(self.hwnd):
                self._refresh_window_list()
            my_root = 0
            try:
                my_root = get_root_window(self.root.winfo_id())
            except Exception:
                pass

            # 仅收集真正的游戏浏览器顶层窗口（FFBrowser / FCBrowser / FlashPlayer），绝不误隐藏 Antigravity/IDE/桌面软件！
            root_set = []
            cands = find_fcbrowser_windows(self._get_profile_to_name_map())
            for h, _, _, _ in cands:
                rh = get_root_window(h)
                if rh and rh != my_root and rh not in root_set and user32.IsWindow(rh):
                    pn = _get_proc_name_by_hwnd(rh)
                    if ("ffbrowser" in pn or "fcbrowser" in pn or "flashplayer" in pn) and not _is_non_game_proc(pn):
                        root_set.append(rh)
            if self.hwnd and user32.IsWindow(self.hwnd):
                cur_r = get_root_window(self.hwnd)
                if cur_r and cur_r != my_root and cur_r not in root_set:
                    pn_cur = _get_proc_name_by_hwnd(cur_r)
                    if not _is_non_game_proc(pn_cur):
                        root_set.append(cur_r)

            if not root_set:
                messagebox.showwarning("提示", "尚未检测到游戏浏览器窗口，请先打开游戏或按 F8 锁定！")
                return

            entries = []
            for rh in root_set:
                ok, saved = set_window_stealth(rh, True, None)
                if ok:
                    entries.append((rh, saved))

            if entries:
                self._stealth_active = True
                self._stealth_entries = entries
                self._stealth_root_hwnd = entries[0][0]
                self._stealth_orig_exstyle = entries[0][1]
                self.btn_stealth.config(
                    text="👁恢复显示(F10)",
                    bg=self._cur_theme()["stealth_on_bg"],
                    activebackground=self._cur_theme()["stealth_on_bg"],
                )
                self.log(f"👻 已将全部 {len(entries)} 个游戏浏览器窗口设为【彻底隐身 + 鼠标穿透】！随时按 F10 或关闭本程序自动恢复。")
            else:
                self.log("⚠ 隐身穿透开启失败，请先重新按 F8 绑定游戏窗口。")

    def _start_hotkey_listener(self):
        VK_F8, VK_F10, VK_F11 = 0x77, 0x79, 0x7A

        def loop():
            f8_down = False
            f10_down = False
            f11_down = False
            while self._alive:
                if user32.GetAsyncKeyState(VK_F8) & 0x8000:
                    if not f8_down:
                        f8_down = True
                        pt = wintypes.POINT()
                        user32.GetCursorPos(ctypes.byref(pt))
                        raw_hwnd = user32.WindowFromPoint(pt)
                        if raw_hwnd:
                            pid_f8 = wintypes.DWORD()
                            user32.GetWindowThreadProcessId(raw_hwnd, ctypes.byref(pid_f8))
                            if pid_f8.value == os.getpid():
                                self.log("⚠ 请把鼠标移到【FCBrowser 游戏画面】上再按 F8，不能绑定脚本自身窗口！")
                            else:
                                root_h = user32.GetAncestor(raw_hwnd, GA_ROOT) or raw_hwnd
                                target_h = get_deepest_child_at_screen_point(root_h, pt.x, pt.y)
                                self.hwnd = target_h
                                self._auto_crop_tried = False
                                cls = get_class_name(target_h)
                                self.root.after(
                                    0,
                                    lambda h=target_h, c=cls: (
                                        self.lbl_hwnd.config(text=f"已 F8 锁定 HWND: {h} ({c})"),
                                        self.refresh_preview(),
                                    ),
                                )
                                self.log(f"已锁定游戏渲染窗口 HWND={target_h} (类名={cls})")
                else:
                    f8_down = False

                if user32.GetAsyncKeyState(VK_F10) & 0x8000:
                    if not f10_down:
                        f10_down = True
                        self.root.after(0, self.toggle_stealth)
                else:
                    f10_down = False

                if user32.GetAsyncKeyState(VK_F11) & 0x8000:
                    if not f11_down:
                        f11_down = True
                        self.root.after(0, self.toggle_bot)
                else:
                    f11_down = False
                time.sleep(0.05)

        threading.Thread(target=loop, daemon=True).start()

    # ==================== 实时画面同步 (30~60 FPS GDI 加速) & 布阵落点可视化叠加 ====================
    def _update_crop_btn_label(self):
        if not hasattr(self, "btn_crop_view"):
            return
        if self.config.get("preview_crop"):
            self.btn_crop_view.configure(text="↩显示全图")
        else:
            self.btn_crop_view.configure(text="✂去白边")

    def _toggle_preview_crop(self):
        """一键切换【自动裁去左右/底部多余网页白边】与【显示完整浏览器画面】（纯视觉优化，绝不改任何坐标）"""
        if self.config.get("preview_crop"):
            self.config["preview_crop"] = None
            self.config["auto_crop_preview"] = False
            self._update_crop_btn_label()
            self.save_config(silent=True)
            self.log("↩ 已还原完整窗口预览画面。")
            return

        full_img = CAPTURER.capture_full(self.hwnd) if (self.hwnd and user32.IsWindow(self.hwnd)) else self.current_pil_img
        if full_img is None:
            messagebox.showinfo("提示", "请先按 F8 绑定 FCBrowser 游戏画面！")
            return
        crop = auto_detect_game_viewport(full_img)
        if not crop:
            messagebox.showinfo("提示", "未检测到明显白边，你也可以在左侧画面上【按住鼠标右键】框选游戏区域，选择设为预览裁剪区！")
            return
        self.config["preview_crop"] = crop
        self.config["auto_crop_preview"] = True
        self._update_crop_btn_label()
        self.save_config(silent=True)
        self.log(f"✂ 已自动裁去多余网页背景，仅展示游戏主体区域 {crop}（所有已保存坐标不受影响）！")

    def _on_canvas_resize(self, event):
        if event.width > 100 and event.height > 100:
            self.canvas_w = event.width
            self.canvas_h = event.height
        self._redraw_canvas_overlays()

    def _get_target_frame_interval(self) -> float:
        txt = self.var_target_fps.get()
        if "60" in txt:
            return 1.0 / 60.0
        if "30" in txt:
            return 1.0 / 30.0
        return 1.0 / 15.0

    def _auto_detect_and_bind_if_needed(self):
        """后台静默检测：当尚未绑定、浏览器刚打开、重启或切换标签页导致旧渲染层失效时，自动重新锁定游戏画面！"""
        cur_ok = bool(self.hwnd and user32.IsWindow(self.hwnd))
        if cur_ok and (not self._stealth_active):
            # 若用户切了标签页导致旧的 Chrome_RenderWidgetHostHWND 变成不可见，也自动跟进到当前可见标签页！
            if not user32.IsWindowVisible(self.hwnd):
                cur_ok = False
        if cur_ok:
            return
        pmap = self._get_profile_to_name_map()
        cands = find_fcbrowser_windows(pmap)
        if not cands:
            return
        # 优先重连当前选中账号自己的新标签页窗口，绝不随意串跳到别的账号画面！
        cur_acc, _ = self._get_selected_account()
        cur_prof = _safe_profile_dirname(cur_acc.get("profile_dir") or cur_acc.get("id") or "").lower() if cur_acc else ""
        same_acc = [i for i, c in enumerate(cands) if cur_prof and c[3] == cur_prof]
        if same_acc:
            best_idx = max(same_acc, key=lambda i: cands[i][2])
        else:
            best_idx = max(range(len(cands)), key=lambda i: cands[i][2])
        best_hwnd, _, best_score, best_prof = cands[best_idx]
        # 只自动绑定明确属于 FCBrowser / FFBrowser / 美食大战老鼠 的高置信度窗口
        if best_score < 600:
            return
        self.hwnd = best_hwnd
        self._auto_crop_tried = False
        CAPTURER.reset_cache(best_hwnd)
        cls = get_class_name(best_hwnd)
        acc_lbl = pmap.get(best_prof, "")
        tag = f"【{acc_lbl}】" if acc_lbl else ""

        def _sync_ui():
            self.win_candidates = cands
            self.win_combo["values"] = [desc for _, desc, _, _ in cands]
            self.win_combo.current(best_idx)
            self.lbl_hwnd.config(text=f"已自动绑定{tag} HWND: {best_hwnd} ({cls})")

        self.root.after(0, _sync_ui)
        self.log(f"🎯 自动检测到《美食大战老鼠》游戏画面，已自动锁定{tag} HWND={best_hwnd} ({cls})")

    def _start_live_preview_loop(self):
        def loop():
            while self._alive:
                t0 = time.perf_counter()
                interval = self._get_target_frame_interval()
                # 每 1.5 秒检查一次：若未绑定或浏览器重启/切标签页，全自动重新锁定游戏画面（无需按 F8）
                if t0 - self._last_autobind_ts >= 1.5:
                    self._last_autobind_ts = t0
                    try:
                        self._auto_detect_and_bind_if_needed()
                    except Exception:
                        pass
                if (
                    self.var_live_preview.get()
                    and self.hwnd
                    and user32.IsWindow(self.hwnd)
                    and self.drag_start is None
                    and not self._preview_busy
                ):
                    try:
                        # 首次绑定时自动检测并裁去左右多余网页背景（随时可点顶部【↩显示全图】关闭）
                        if self.config.get("auto_crop_preview", True) and not self.config.get("preview_crop") and not self._auto_crop_tried:
                            self._auto_crop_tried = True
                            full0 = CAPTURER.capture_full(self.hwnd)
                            if full0 is not None:
                                det = auto_detect_game_viewport(full0)
                                if det:
                                    self.config["preview_crop"] = det
                                    self.root.after(0, self._update_crop_btn_label)

                        res = CAPTURER.capture_preview(
                            self.hwnd,
                            max(320, self.canvas_w),
                            max(240, self.canvas_h),
                            view_crop=self.config.get("preview_crop"),
                        )
                        if res is not None:
                            resized, ow, oh, scale, vox, voy = res
                            self._preview_busy = True
                            self.root.after(
                                0,
                                lambda r=resized, w=ow, h=oh, s=scale, x0=vox, y0=voy: self._apply_preview_frame(r, w, h, s, x0, y0),
                            )

                        # 每 0.25 秒同步一次实时火苗数值（只抓小框，不影响帧率）
                        roi = self._ctx_fire_roi()
                        now_t = time.perf_counter()
                        if roi and len(roi) == 4 and (now_t - self._last_fire_check_ts >= 0.25):
                            self._last_fire_check_ts = now_t
                            roi_img = CAPTURER.capture_roi(self.hwnd, roi[0], roi[1], roi[2], roi[3])
                            if roi_img is not None:
                                val, score, _ = FIRE_OCR.read_number(roi_img)
                                self.latest_fire_val = val
                                txt = f"🔥 实时火苗: {val}" if val is not None else "🔥 实时火苗: 识别中..."
                                self.root.after(0, lambda t=txt: self.lbl_fire_live.config(text=t))
                    except Exception:
                        pass
                elapsed = time.perf_counter() - t0
                sleep_s = interval - elapsed
                if sleep_s > 0.002:
                    time.sleep(sleep_s)
                else:
                    time.sleep(0.002)

        threading.Thread(target=loop, daemon=True).start()

    def _game_to_canvas_xy(self, gx: float, gy: float):
        cx = int(round(self.canvas_ox + (gx - self.view_ox) * self.preview_scale))
        cy = int(round(self.canvas_oy + (gy - self.view_oy) * self.preview_scale))
        return cx, cy

    def _apply_preview_frame(self, resized_img: Image.Image, ow: int, oh: int, scale: float, vox: int = 0, voy: int = 0):
        try:
            dw, dh = resized_img.size
            cox = max(0, (self.canvas_w - dw) // 2)
            coy = max(0, (self.canvas_h - dh) // 2)
            geom_changed = (
                abs(scale - self.preview_scale) > 1e-4
                or vox != self.view_ox
                or voy != self.view_oy
                or cox != self.canvas_ox
                or coy != self.canvas_oy
                or self.canvas_img_id is None
            )
            self.orig_w = ow
            self.orig_h = oh
            self.preview_scale = scale
            self.view_ox = vox
            self.view_oy = voy
            self.canvas_ox = cox
            self.canvas_oy = coy
            self.tk_img = ImageTk.PhotoImage(resized_img)
            if self.canvas_img_id is None:
                self.canvas_img_id = self.canvas.create_image(cox, coy, anchor="nw", image=self.tk_img)
                self.canvas.tag_lower(self.canvas_img_id)
            else:
                self.canvas.itemconfig(self.canvas_img_id, image=self.tk_img)
                if geom_changed:
                    self.canvas.coords(self.canvas_img_id, cox, coy)
            if geom_changed:
                self._redraw_canvas_overlays()

            # 统计真实渲染帧率
            self._fps_count += 1
            now = time.perf_counter()
            if now - self._fps_last_ts >= 0.8:
                fps = int(round(self._fps_count / (now - self._fps_last_ts)))
                self.lbl_fps.config(text=f"[{fps} FPS]")
                self._fps_count = 0
                self._fps_last_ts = now
        finally:
            self._preview_busy = False

    def _redraw_canvas_overlays(self):
        """在实时画面上叠加显示已保存的卡片槽位置 & 编号放卡落点"""
        for oid in self.overlay_ids:
            self.canvas.delete(oid)
        self.overlay_ids.clear()

        if not self.var_show_markers.get() or self.preview_scale <= 0 or self.orig_w <= 0:
            return

        deck = self.get_cur_deck()

        # -1. 绘制实时火苗监测框（橙色虚线，按当前账号独立显示）
        roi = self._ctx_fire_roi()
        if roi and len(roi) == 4:
            fx0, fy0 = self._game_to_canvas_xy(roi[0], roi[1])
            fx1, fy1 = self._game_to_canvas_xy(roi[2], roi[3])
            oid_f1 = self.canvas.create_rectangle(fx0, fy0, fx1, fy1, outline="#ff9100", width=2, dash=(4, 2))
            oid_f2 = self.canvas.create_text(
                (fx0 + fx1) // 2, max(8, fy0 - 8), text="🔥火苗区", fill="#ffab40", font=("Microsoft YaHei", 8, "bold")
            )
            self.overlay_ids.extend([oid_f1, oid_f2])

        # 0. 绘制开局角色放置点（醒目金色 ★角色）
        hero = deck.get("hero", {})
        if hero.get("enabled", False):
            hx, hy = self._game_to_canvas_xy(hero.get("x", 0), hero.get("y", 0))
            oid_h1 = self.canvas.create_oval(
                hx - 14, hy - 14, hx + 14, hy + 14, outline="#ffd600", fill="#ff6f00", stipple="gray50", width=3
            )
            oid_h2 = self.canvas.create_text(hx + 1, hy + 1, text="★角色", fill="black", font=("Microsoft YaHei", 9, "bold"))
            oid_h3 = self.canvas.create_text(hx, hy, text="★角色", fill="#ffff00", font=("Microsoft YaHei", 9, "bold"))
            self.overlay_ids.extend([oid_h1, oid_h2, oid_h3])

        # 1. 绘制已保存卡片槽的淡青色方框标签
        for card in deck.get("cards", []):
            cx, cy = self._game_to_canvas_xy(card["x"], card["y"])
            col = card.get("color", "#42a5f5")
            oid1 = self.canvas.create_rectangle(cx - 10, cy - 12, cx + 10, cy + 12, outline=col, width=2)
            oid2 = self.canvas.create_text(
                cx, cy - 18, text=card["name"], fill="white", font=("Microsoft YaHei", 8, "bold")
            )
            self.overlay_ids.extend([oid1, oid2])

        # 2. 绘制所有放卡落点（带序号 + 卡片名称）
        for i, p in enumerate(deck.get("placements", []), start=1):
            px, py = self._game_to_canvas_xy(p["x"], p["y"])
            card = self.get_card_by_name(p.get("card_name", ""))
            col = card.get("color", "#ffeb3b") if card else "#ffeb3b"
            enabled = p.get("enabled", True)
            outline_col = col if enabled else "#888888"
            dash = () if enabled else (3, 3)

            oid1 = self.canvas.create_oval(
                px - 10, py - 10, px + 10, py + 10, outline=outline_col, fill=col if enabled else "", stipple="gray50", width=2, dash=dash
            )
            label = f"{i}.{p.get('card_name', '?')}"
            oid2 = self.canvas.create_text(px + 1, py + 1, text=label, fill="black", font=("Microsoft YaHei", 8, "bold"))
            oid3 = self.canvas.create_text(px, py, text=label, fill="white", font=("Microsoft YaHei", 8, "bold"))
            self.overlay_ids.extend([oid1, oid2, oid3])

    def refresh_preview(self):
        if not self.hwnd or not user32.IsWindow(self.hwnd):
            messagebox.showwarning("提示", "请先绑定有效的 FCBrowser 窗口（鼠标指着游戏画面按 F8）")
            return
        CAPTURER.reset_cache(self.hwnd)
        img = CAPTURER.capture_full(self.hwnd)
        if img is None:
            self.log("后台截图失败，请确认 FCBrowser 没有被最小化到任务栏。")
            return
        self.current_pil_img = img
        iw, ih = img.size
        if self.config.get("auto_crop_preview", True) and not self.config.get("preview_crop"):
            det = auto_detect_game_viewport(img)
            if det:
                self.config["preview_crop"] = det
                self._update_crop_btn_label()
        vc = self.config.get("preview_crop")
        vox, voy = 0, 0
        view_img = img
        if vc and len(vc) == 4:
            cx0, cy0, cx1, cy1 = [int(v) for v in vc]
            cx0 = max(0, min(iw - 100, cx0))
            cy0 = max(0, min(ih - 100, cy0))
            cx1 = max(cx0 + 100, min(iw, cx1))
            cy1 = max(cy0 + 100, min(ih, cy1))
            vox, voy = cx0, cy0
            view_img = img.crop((cx0, cy0, cx1, cy1))
        vw, vh = view_img.size
        scale = min(max(320, self.canvas_w) / vw, max(240, self.canvas_h) / vh)
        resized = view_img.resize((max(1, int(vw * scale)), max(1, int(vh * scale))), Image.Resampling.BILINEAR)
        self._apply_preview_frame(resized, iw, ih, scale, vox, voy)
        self._redraw_canvas_overlays()
        self.save_snapshot_for_ai(silent=True)
        self.log(f"已刷新并开启高帧率同步！窗口分辨率: {iw}x{ih}" + (f" (已自动裁去白边展示 {vw}x{vh})" if vc else ""))

    def save_snapshot_for_ai(self, silent: bool = False):
        img = CAPTURER.capture_full(self.hwnd) if self.hwnd else self.current_pil_img
        if img is None:
            if not silent:
                self.log("请先绑定 FCBrowser 窗口后再截图。")
            return
        self.current_pil_img = img
        path = os.path.join(DATA_DIR, "current_game_screen.png")
        try:
            img.save(path)
            if not silent:
                self.log(f"已保存全分辨率当前画面到 {path}")
        except Exception as e:
            if not silent:
                self.log(f"保存截图失败: {e}")

    def _canvas_to_game_xy(self, cx: int, cy: int):
        if self.orig_w <= 0 or self.orig_h <= 0 or self.preview_scale <= 0:
            return None, None
        gx = int(round(self.view_ox + (cx - self.canvas_ox) / self.preview_scale))
        gy = int(round(self.view_oy + (cy - self.canvas_oy) / self.preview_scale))
        if 0 <= gx < self.orig_w and 0 <= gy < self.orig_h:
            return gx, gy
        return None, None

    def _crop_card_icon(self, gx: int, gy: int, card_name: str) -> str:
        """自动以点击的卡槽坐标为中心，从原始分辨率截图裁剪一张卡片缩略图并保存到 card_icons/"""
        full_img = CAPTURER.capture_full(self.hwnd) or self.current_pil_img
        if full_img is None:
            return ""
        self.current_pil_img = full_img
        iw, ih = full_img.size
        rx = max(24, int(iw * 0.022))
        ry = max(28, int(ih * 0.036))
        box = (max(0, gx - rx), max(0, gy - ry), min(iw, gx + rx), min(ih, gy + ry))
        crop = full_img.crop(box).resize((32, 32), Image.Resampling.LANCZOS)
        safe_name = f"card_{int(time.time()*1000)}.png"
        path = os.path.join(CARD_ICON_DIR, safe_name)
        try:
            crop.save(path)
            return safe_name
        except Exception:
            return ""

    # ==================== 画布鼠标点击/拖拽事件 ====================
    def _on_canvas_left_click(self, event):
        gx, gy = self._canvas_to_game_xy(event.x, event.y)
        if gx is None:
            return

        # 0.5 秒闪现点击反馈圈
        r = 7
        dot_id = self.canvas.create_oval(event.x - r, event.y - r, event.x + r, event.y + r, outline="#ff3333", width=2)
        self.root.after(500, lambda d=dot_id: self.canvas.delete(d))

        mode = self.click_pick_mode.get()
        deck = self.get_cur_deck()

        if mode == "test_click":
            threading.Thread(target=bg_click, args=(self.hwnd, gx, gy), daemon=True).start()
            self.log(f"[测试后台点击] 坐标 ({gx}, {gy})（物理鼠标未移动）")

        elif mode == "set_hero":
            hero = deck["hero"]
            hero["x"], hero["y"] = gx, gy
            hero["enabled"] = True
            self._reload_hero_ui()
            self._redraw_canvas_overlays()
            self.save_config()
            self.log(f"✅ 已设定当前卡组的【开局角色放置点】为 ({gx}, {gy})（画面已用金色 ★角色 标出）")

        elif mode == "add_card":
            idx = len(deck["cards"]) + 1
            res_info = self._ask_card_name_and_cost(
                title="录入卡组卡片",
                prompt_hint=f"已锁定卡槽坐标 ({gx}, {gy})",
                init_name=f"卡片{idx}",
                init_cost=0,
            )
            if not res_info:
                return
            name, cost = res_info
            if self.get_card_by_name(name):
                messagebox.showwarning("提示", f"卡组里已经有叫【{name}】的卡片了，请换个名字！")
                return
            color = CARD_PALETTE[(idx - 1) % len(CARD_PALETTE)]
            icon_file = self._crop_card_icon(gx, gy, name)
            deck["cards"].append({"name": name, "cost": cost, "x": gx, "y": gy, "color": color, "icon": icon_file})
            self.var_selected_card.set(name)
            self._reload_cards_tree()
            self._reload_quick_card_buttons()
            self._redraw_canvas_overlays()
            self.save_config()
            self.log(f"✅ 已保存卡片【{name}】(消耗:{cost}火)，卡槽坐标 ({gx}, {gy})")

        elif mode == "update_card_xy":
            sel = self.tree_cards.selection()
            if not sel:
                messagebox.showinfo("提示", "请先在右侧【1.卡组卡片库】里选中一张要更新坐标的卡片！")
                return
            idx = self.tree_cards.index(sel[0])
            card = deck["cards"][idx]
            card["x"], card["y"] = gx, gy
            icon_file = self._crop_card_icon(gx, gy, card["name"])
            if icon_file:
                card["icon"] = icon_file
            self._reload_cards_tree()
            self._reload_quick_card_buttons()
            self._redraw_canvas_overlays()
            self.save_config()
            self.log(f"✅ 已更新卡片【{card['name']}】的卡槽坐标为 ({gx}, {gy})")

        elif mode == "add_place":
            card_name = self.var_selected_card.get()
            if not card_name or not self.get_card_by_name(card_name):
                messagebox.showinfo("提示", "请先在【1.卡组卡片库】录入卡片，并在【2.自由放卡布阵】顶部选中一张卡片！")
                return
            plist = deck["placements"]
            sel = self.tree_place.selection()
            default_delay = 0.3 if plist else 1.2
            if sel and self.var_insert_after.get():
                cur_idx = self.tree_place.index(sel[0])
                default_delay = float(plist[cur_idx].get("delay", 0.3))
                insert_idx = cur_idx + 1
                plist.insert(insert_idx, {"card_name": card_name, "x": gx, "y": gy, "delay": default_delay, "enabled": True})
            else:
                if plist:
                    default_delay = float(plist[-1].get("delay", 0.3))
                insert_idx = len(plist)
                plist.append({"card_name": card_name, "x": gx, "y": gy, "delay": default_delay, "enabled": True})
            self._reload_place_tree()
            # 自动选中刚插入的新行，方便连续在中间插入多步！
            items = self.tree_place.get_children()
            if 0 <= insert_idx < len(items):
                self.tree_place.selection_set(items[insert_idx])
                self.tree_place.see(items[insert_idx])
            self._redraw_canvas_overlays()
            self.save_config()
            self.log(f"✅ 已在第 {insert_idx+1} 步插入：【{card_name}】 -> ({gx}, {gy})")

        elif mode == "update_place_xy":
            sel = self.tree_place.selection()
            if not sel:
                messagebox.showinfo("提示", "请先在右侧【2.自由放卡布阵】列表中选中要调整位置的那一行！")
                return
            idx = self.tree_place.index(sel[0])
            deck["placements"][idx]["x"] = gx
            deck["placements"][idx]["y"] = gy
            self._reload_place_tree()
            self._redraw_canvas_overlays()
            self.save_config()
            self.log(f"✅ 已将第 {idx+1} 步【{deck['placements'][idx]['card_name']}】的新落点改为 ({gx}, {gy})")

        elif mode == "add_enter":
            name = simpledialog.askstring("添加选卡/进图点击", f"坐标 ({gx}, {gy}) 的说明：", initialvalue="点击预设卡组/开始")
            if name:
                deck["enter_clicks"].append({"name": name, "x": gx, "y": gy, "delay": 0.8})
                self._reload_enter_tree()
                self.save_config()

        elif mode == "add_finish":
            name = simpledialog.askstring("添加收尾点击(全关卡通用)", f"坐标 ({gx}, {gy}) 的说明：", initialvalue="翻牌/点击确定")
            if name:
                self.config.setdefault("finish_extra_clicks", []).append({"name": name, "x": gx, "y": gy, "delay": 2.0})
                self._reload_finish_tree()
                self.save_config()

        elif mode in ("pick_login_open", "pick_login_tab", "pick_login_user", "pick_login_pass", "pick_login_submit"):
            pts = self._get_login_points()
            key_map = {
                "pick_login_open": ("open_xy", "弹出登录框按钮"),
                "pick_login_tab": ("tab_xy", "切回登录页标签"),
                "pick_login_user": ("user_xy", "账号输入框"),
                "pick_login_pass": ("pass_xy", "密码输入框"),
                "pick_login_submit": ("submit_xy", "登录按钮"),
            }
            k, label = key_map[mode]
            pts[k] = [gx, gy]
            self.click_pick_mode.set("test_click")
            self._refresh_login_pts_label()
            self.save_config()
            self.log(f"✅ 已设定登录页【{label}】坐标为 ({gx}, {gy})")

        elif mode == "add_login_after":
            pts = self._get_login_points()
            name = simpledialog.askstring("添加登录后进服点击", f"坐标 ({gx}, {gy}) 的说明：", initialvalue="进入游戏/选区")
            if name:
                delay_s = simpledialog.askfloat("点击前等待", "点击前等待秒数（等待登录跳转加载）：", initialvalue=2.5, minvalue=0.2, maxvalue=30.0)
                pts.setdefault("after_clicks", []).append({"name": name, "x": gx, "y": gy, "delay": round(float(delay_s or 2.5), 2)})
                self.click_pick_mode.set("test_click")
                self._refresh_login_pts_label()
                self.save_config()
                self.log(f"✅ 已添加登录后进服点：【{name}】({gx}, {gy})")

    def _on_canvas_right_down(self, event):
        self.drag_start = (event.x, event.y)
        if self.drag_rect_id:
            self.canvas.delete(self.drag_rect_id)
            self.drag_rect_id = None

    def _on_canvas_right_drag(self, event):
        if not self.drag_start:
            return
        if self.drag_rect_id:
            self.canvas.delete(self.drag_rect_id)
        x0, y0 = self.drag_start
        self.drag_rect_id = self.canvas.create_rectangle(x0, y0, event.x, event.y, outline="#00ff00", width=2)

    def _on_canvas_right_up(self, event):
        if not self.drag_start or self.orig_w <= 0:
            self.drag_start = None
            return
        x0, y0 = self.drag_start
        x1, y1 = event.x, event.y
        self.drag_start = None
        if self.drag_rect_id:
            self.canvas.delete(self.drag_rect_id)
            self.drag_rect_id = None

        gx0, gy0 = self._canvas_to_game_xy(min(x0, x1), min(y0, y1))
        gx1, gy1 = self._canvas_to_game_xy(max(x0, x1), max(y0, y1))
        if gx0 is None or gx1 is None or (gx1 - gx0) < 10 or (gy1 - gy0) < 10:
            return

        full_img = CAPTURER.capture_full(self.hwnd) or self.current_pil_img
        if full_img is None:
            return
        self.current_pil_img = full_img
        crop_img = full_img.crop((gx0, gy0, gx1, gy1))
        win = tk.Toplevel(self.root)
        win.title("保存框选区域 / 识别模板")
        win.resizable(True, True)
        win.configure(bg=self._cur_theme()["card"])
        apply_win11_titlebar(win, self._cur_theme())
        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=f"已框选区域 ({gx0},{gy0}) -> ({gx1},{gy1})\n请选择将该框选区域用作什么功能：").pack(pady=6)

        choice = tk.StringVar(value="__fire_roi__")
        opts = [
            ("🔥 设定为【实时火苗数字监测区】(包含外框也能自动识别)", "__fire_roi__"),
            ("✂ 设定为【预览裁剪区】(只隐藏画面两侧白边，不影响坐标)", "__preview_crop__"),
            ("🧑 开局【请放置角色】提示标志 (stage_place_hero.png)", "stage_place_hero.png"),
            ("▶ 闯关途中【继续战斗】按钮 (btn_continue.png)", "btn_continue.png"),
            ("📋 房间/房主【开始】标志 (stage_select.png)", "stage_select.png"),
            ("🙋 组队队员【准备】按钮 (stage_ready.png，小号专用)", "stage_ready.png"),
            ("🏁 【战斗结束/翻牌结算】标志 (stage_finish.png)", "stage_finish.png"),
            ("💀 【战斗失败/退出重开】按钮 (stage_fail.png，翻车自动回房)", "stage_fail.png"),
            ("🔑 【7k7k 登录界面】标志 (stage_login.png，用于自动重登)", "stage_login.png"),
        ]
        for txt, val in opts:
            ttk.Radiobutton(body, text=txt, value=val, variable=choice).pack(anchor="w", padx=8, pady=3)

        cur_pname = self.var_active_deck.get()
        var_only_cur = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            body,
            text=f"🔒 仅保存为当前方案【{cur_pname}】专属模板（不勾则所有关卡通用，推荐不勾）",
            variable=var_only_cur,
        ).pack(anchor="w", padx=8, pady=6)

        def save_tpl():
            val = choice.get()
            if val == "__preview_crop__":
                if (gx1 - gx0) < 120 or (gy1 - gy0) < 120:
                    messagebox.showwarning("提示", "预览裁剪区太小，请框选完整的游戏画面区域！", parent=win)
                    return
                self.config["preview_crop"] = [gx0, gy0, gx1, gy1]
                self.config["auto_crop_preview"] = True
                self._update_crop_btn_label()
                self.save_config()
                self.log(f"✂ 已手动设置预览裁剪区 ({gx0},{gy0})-({gx1},{gy1})，原有坐标保持不变！")
                win.destroy()
                return
            if val == "__fire_roi__":
                new_roi = [gx0, gy0, gx1, gy1]
                cur_deck = self.get_cur_deck()
                cur_deck["fire_ocr_roi"] = new_roi
                _, owner, acc_name = self._get_active_decks_store()
                if not owner.get("fire_ocr_roi"):
                    owner["fire_ocr_roi"] = new_roi
                if not self.config.get("fire_ocr_roi") or owner is self.config:
                    self.config["fire_ocr_roi"] = new_roi
                self.save_config()
                self._redraw_canvas_overlays()
                num, sc, cnt = FIRE_OCR.read_number(crop_img)
                self.latest_fire_val = num
                dname = self.var_active_deck.get()
                who = f"【{acc_name} · {dname}】专属" if acc_name else f"方案【{dname}】专属"
                if num is not None:
                    self.lbl_fire_live.config(text=f"🔥 实时火苗: {num}")
                    self.log(f"🔥 已设定{who}实时火苗监测区 ({gx0},{gy0})-({gx1},{gy1})，当前立即识别到火苗: {num} (置信度={sc:.2f})")
                else:
                    self.lbl_fire_live.config(text="🔥 实时火苗: 请校准")
                    self.log(f"🔥 已设定{who}实时火苗监测区 ({gx0},{gy0})-({gx1},{gy1})，切分出 {cnt} 位字符，请点击顶部【🎯 校准火苗数字】！")
                win.destroy()
                return
            save_dir = self._get_profile_tpl_dir() if var_only_cur.get() else TEMPLATE_DIR
            crop_img.save(os.path.join(save_dir, val))
            self._refresh_template_status()
            self._refresh_login_pts_label()
            scope = f"方案【{cur_pname}】专属模板" if var_only_cur.get() else "公共模板"
            self.log(f"✅ 已保存{scope}: {val}")
            win.destroy()

        ttk.Button(body, text="确定保存", command=save_tpl).pack(pady=10)

    def _ask_card_name_and_cost(self, title: str, prompt_hint: str, init_name: str, init_cost: int):
        """弹出简洁对话框同时输入卡片名称与火苗消耗（自适应高分屏尺寸）"""
        res = []
        win = tk.Toplevel(self.root)
        win.title(title)
        win.resizable(True, True)
        win.configure(bg=self._cur_theme()["card"])
        apply_win11_titlebar(win, self._cur_theme())
        win.transient(self.root)
        win.grab_set()

        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=prompt_hint, foreground=self._cur_theme()["tip_fg"]).pack(pady=4)
        f1 = ttk.Frame(body)
        f1.pack(fill="x", pady=4)
        ttk.Label(f1, text="卡片名称:", width=10).pack(side="left")
        e_name = ttk.Entry(f1, width=22)
        e_name.insert(0, init_name)
        e_name.pack(side="left", fill="x", expand=True)

        f2 = ttk.Frame(body)
        f2.pack(fill="x", pady=4)
        ttk.Label(f2, text="火苗消耗:", width=10).pack(side="left")
        e_cost = ttk.Entry(f2, width=22)
        e_cost.insert(0, str(init_cost))
        e_cost.pack(side="left", fill="x", expand=True)

        def ok(_=None):
            nm = e_name.get().strip()
            if not nm:
                return
            try:
                ct = max(0, int(e_cost.get().strip() or "0"))
            except ValueError:
                messagebox.showwarning("提示", "火苗消耗请填写整数（如 0、50、150、350）", parent=win)
                return
            res.append((nm, ct))
            win.destroy()

        f3 = ttk.Frame(body)
        f3.pack(pady=10)
        ttk.Button(f3, text="确定", command=ok).pack(side="left", padx=8)
        ttk.Button(f3, text="取消", command=win.destroy).pack(side="left", padx=8)
        e_name.focus_set()
        e_name.select_range(0, "end")
        win.bind("<Return>", ok)
        self.root.wait_window(win)
        return res[0] if res else None

    def _open_fire_calibrate_dialog(self):
        """一键采集当前火苗数字画面并让用户输入真实数值（高分屏自适应大小，不遮挡按钮）"""
        roi = self._ctx_fire_roi()
        if not roi or len(roi) != 4:
            messagebox.showinfo(
                "尚未框选火苗监测区",
                "请先进入战斗画面，在左侧实时画面上【按住鼠标右键】框选出火苗数字区域，\n"
                "然后选择【🔥 设定为实时火苗数字监测区】！",
            )
            return
        roi_img = CAPTURER.capture_roi(self.hwnd, roi[0], roi[1], roi[2], roi[3])
        if roi_img is None:
            messagebox.showwarning("提示", "截取火苗区域失败，请确认已绑定 FCBrowser 且未最小化！")
            return

        cur_val, sc, cnt = FIRE_OCR.read_number(roi_img)
        win = tk.Toplevel(self.root)
        win.title("🎯 校准游戏火苗数字字体")
        win.resizable(True, True)
        win.configure(bg=self._cur_theme()["card"])
        apply_win11_titlebar(win, self._cur_theme())
        win.transient(self.root)
        win.grab_set()

        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)

        ttk.Label(body, text="当前实时抓取到的火苗数字框画面：", font=("Microsoft YaHei", 9, "bold")).pack(pady=4)
        # 限制预览图最大宽度，防止 2K 屏下把下方输入框顶出窗口
        scale_p = min(2.0, 260 / max(1, roi_img.width), 90 / max(1, roi_img.height))
        preview = roi_img.resize(
            (max(80, int(roi_img.width * scale_p)), max(32, int(roi_img.height * scale_p))),
            Image.Resampling.NEAREST,
        )
        tk_roi = ImageTk.PhotoImage(preview)
        lbl_img = ttk.Label(body, image=tk_roi)
        lbl_img.image = tk_roi
        lbl_img.pack(pady=6)

        ttk.Label(
            body,
            text=f"当前程序识别为：{cur_val}（切分出 {cnt} 位数字，匹配度 {sc:.2f}）\n若读错，请输入上方实际显示的火苗数字（如 685）：",
        ).pack(pady=4)

        ent = ttk.Entry(body, width=18, font=("Consolas", 12, "bold"), justify="center")
        if cur_val is not None:
            ent.insert(0, str(cur_val))
        ent.pack(pady=6)
        ent.focus_set()

        def do_cal(_=None):
            ok, msg = FIRE_OCR.calibrate(roi_img, ent.get())
            if ok:
                self.log(f"🎯 {msg}")
                val2, _, _ = FIRE_OCR.read_number(roi_img)
                if val2 is not None:
                    self.lbl_fire_live.config(text=f"🔥 实时火苗: {val2}")
                messagebox.showinfo("校准成功", msg, parent=win)
                win.destroy()
            else:
                messagebox.showwarning("校准提示", msg, parent=win)

        bbar = ttk.Frame(body)
        bbar.pack(pady=8)
        ttk.Button(bbar, text="✔ 保存样本完成校准", command=do_cal).pack(side="left", padx=8)
        ttk.Button(bbar, text="取消", command=win.destroy).pack(side="left", padx=8)
        win.bind("<Return>", do_cal)

    # ==================== 卡片库管理逻辑 ====================
    def _load_card_tk_icon(self, icon_name: str):
        if not icon_name:
            return None
        path = os.path.join(CARD_ICON_DIR, icon_name)
        if not os.path.exists(path):
            return None
        if icon_name not in self._icon_refs:
            try:
                img = Image.open(path).resize((30, 30), Image.Resampling.LANCZOS)
                self._icon_refs[icon_name] = ImageTk.PhotoImage(img)
            except Exception:
                return None
        return self._icon_refs[icon_name]

    def _reload_cards_tree(self):
        self.tree_cards.delete(*self.tree_cards.get_children())
        cards = self.get_cur_deck().get("cards", [])
        card_names = []
        for idx_c, c in enumerate(cards):
            card_names.append(c["name"])
            tk_icon = self._load_card_tk_icon(c.get("icon", ""))
            kwargs = {"image": tk_icon} if tk_icon else {}
            cost = int(c.get("cost", 0))
            cost_txt = f"{cost} 🔥"
            role_key = _get_card_role(c)
            role_txt = CARD_ROLE_LABEL.get(role_key, "⚔主力层")
            ztag = "even" if (idx_c % 2 == 1) else "odd"
            self.tree_cards.insert(
                "", "end", values=(c["name"], role_txt, cost_txt, f"({c['x']}, {c['y']})"), tags=(ztag,), **kwargs
            )

        self.edit_card_combo["values"] = card_names
        if card_names and self.var_selected_card.get() not in card_names:
            self.var_selected_card.set(card_names[0])
        elif not card_names:
            self.var_selected_card.set("")
        self._update_selected_card_hint()

    def _reload_quick_card_buttons(self):
        for w in self.quick_cards_box.winfo_children():
            w.destroy()
        cards = self.get_cur_deck().get("cards", [])
        if not cards:
            ttk.Label(
                self.quick_cards_box, text="尚未录入卡片，请先在【1.卡组卡片库】点击卡槽录入你卡组里的卡片！", foreground="gray"
            ).pack(anchor="w", padx=4, pady=4)
            return

        t = self._cur_theme()
        cur_sel = self.var_selected_card.get()
        row_frame = None
        for i, c in enumerate(cards):
            if i % 4 == 0:
                row_frame = ttk.Frame(self.quick_cards_box)
                row_frame.pack(fill="x", pady=2)
            cname = c["name"]
            is_sel = (cname == cur_sel)
            tk_icon = self._load_card_tk_icon(c.get("icon", ""))
            btn_bg = c.get("color", t["accent"]) if is_sel else t["qbtn_bg"]
            btn_fg = "#ffffff" if is_sel else t["qbtn_fg"]
            btn = tk.Button(
                row_frame,
                text=f" {cname}",
                image=tk_icon if tk_icon else "",
                compound="left",
                bg=btn_bg,
                fg=btn_fg,
                activebackground=btn_bg,
                activeforeground=btn_fg,
                relief="flat",
                bd=1 if not is_sel else 0,
                highlightthickness=1,
                highlightbackground=t["accent"] if is_sel else t["border"],
                cursor="hand2",
                font=("Microsoft YaHei", 9, "bold" if is_sel else "normal"),
                padx=6,
                pady=2,
                command=lambda n=cname: self._select_card_for_placing(n),
            )
            btn.pack(side="left", padx=3)

    def _select_card_for_placing(self, card_name: str):
        self.var_selected_card.set(card_name)
        self.click_pick_mode.set("add_place")
        self._reload_quick_card_buttons()
        self._update_selected_card_hint()
        self.log(f"已选中卡片【{card_name}】，现在直接左键点击左侧实时游戏场地，即可把【{card_name}】放到那个位置！")

    def _update_selected_card_hint(self):
        c = self.var_selected_card.get()
        self.lbl_cur_card_hint.config(text=f"画笔:{c if c else '未选'}")

    def _on_card_tree_select(self, _):
        sel = self.tree_cards.selection()
        if not sel:
            return
        idx = self.tree_cards.index(sel[0])
        cards = self.get_cur_deck().get("cards", [])
        if 0 <= idx < len(cards):
            self.var_selected_card.set(cards[idx]["name"])
            self._reload_quick_card_buttons()
            self._update_selected_card_hint()

    def _rename_card(self):
        sel = self.tree_cards.selection()
        if not sel:
            messagebox.showinfo("提示", "请先在卡片列表中选中一张卡片！")
            return
        idx = self.tree_cards.index(sel[0])
        deck = self.get_cur_deck()
        card = deck["cards"][idx]
        old_name = card["name"]
        old_cost = int(card.get("cost", 0))
        res_info = self._ask_card_name_and_cost(
            title="修改卡片名称与火苗消耗",
            prompt_hint=f"修改卡片【{old_name}】的名称或火苗消耗：",
            init_name=old_name,
            init_cost=old_cost,
        )
        if not res_info:
            return
        new_name, new_cost = res_info
        if new_name != old_name and self.get_card_by_name(new_name):
            messagebox.showwarning("提示", "该卡片名已存在！")
            return
        card["name"] = new_name
        card["cost"] = new_cost
        if new_name != old_name:
            for p in deck["placements"]:
                if p.get("card_name") == old_name:
                    p["card_name"] = new_name
            if self.var_selected_card.get() == old_name:
                self.var_selected_card.set(new_name)
        self._refresh_deck_ui()
        self.save_config()

        self.log(f"✅ 已更新卡片【{new_name}】(火苗消耗: {new_cost})")

    def _edit_card_role(self):
        """一键循环切换选中卡片的三层补阵分层：🧱基础层 → ⚡辅助层 → ⚔主力层 → 🚫不补阵"""
        sel = self.tree_cards.selection()
        if not sel:
            messagebox.showinfo("提示", "请先在【1.卡片库】中选中一张卡片！")
            return
        idx = self.tree_cards.index(sel[0])
        deck = self.get_cur_deck()
        card = deck["cards"][idx]
        cname = card["name"]
        order = ["base", "support", "main", "skip"]
        cur = _get_card_role(card)
        nxt = order[(order.index(cur) + 1) % len(order)] if cur in order else "main"
        card["role"] = nxt
        self._reload_cards_tree()
        children = self.tree_cards.get_children()
        if 0 <= idx < len(children):
            self.tree_cards.selection_set(children[idx])
        self.save_config()
        self.log(f"🏷 已将卡片【{cname}】补阵分层切为：{CARD_ROLE_LABEL.get(nxt, nxt)}")

    def _delete_card(self):
        sel = self.tree_cards.selection()
        if not sel:
            return
        idx = self.tree_cards.index(sel[0])
        deck = self.get_cur_deck()
        cname = deck["cards"][idx]["name"]
        if messagebox.askyesno("确认删除", f"确定从当前卡组删除卡片【{cname}】吗？"):
            del deck["cards"][idx]
            self._refresh_deck_ui()
            self.save_config()

    def _test_click_card(self):
        sel = self.tree_cards.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选中一张卡片！")
            return
        idx = self.tree_cards.index(sel[0])
        c = self.get_cur_deck()["cards"][idx]
        threading.Thread(target=bg_click, args=(self.hwnd, c["x"], c["y"]), daemon=True).start()
        self.log(f"[测试点击卡片] 后台点击【{c['name']}】({c['x']}, {c['y']})")

    def _go_place_with_selected_card(self):
        sel = self.tree_cards.selection()
        if sel:
            idx = self.tree_cards.index(sel[0])
            cname = self.get_cur_deck()["cards"][idx]["name"]
            self.notebook.select(1)
            self._select_card_for_placing(cname)
        else:
            messagebox.showinfo("提示", "请先在列表中选中一张卡片！")

    # ==================== 自由放卡布阵管理逻辑 ====================
    def _resolve_step_repair_card(self, placements: list, idx_zero: int, cur_deck: dict = None) -> str:
        """
        解析某一步在【三层智能补阵】阶段实际应该补种哪张卡：
        - 显式设置了 repair_card == "__skip__" -> 返回 ""（跳过）
        - 显式设置了 repair_card -> 直接返回该指定本体卡名
        - 未手动指定时：若为【百变/幻鸡】等复制卡，自动取相邻本体卡；否则返回原卡名
        """
        if idx_zero < 0 or idx_zero >= len(placements):
            return ""
        p = placements[idx_zero]
        rc = (p.get("repair_card") or "").strip()
        if rc == "__skip__":
            return ""
        if rc:
            return rc
        cname = p.get("card_name", "")
        deck = cur_deck if cur_deck is not None else self.get_cur_deck()
        cards_by_name = {c["name"]: c for c in deck.get("cards", [])}

        def _role_of(name: str) -> str:
            c = cards_by_name.get(name)
            return _get_card_role(c) if c else _infer_card_role(name)

        if _role_of(cname) == "skip":
            return ""
        if "百变" in cname:
            for j in range(idx_zero + 1, len(placements)):
                cand = placements[j].get("card_name", "")
                if _role_of(cand) != "skip" and ("百变" not in cand) and ("幻鸡" not in cand):
                    return cand
            return ""
        if "幻鸡" in cname:
            for j in range(idx_zero - 1, -1, -1):
                cand = placements[j].get("card_name", "")
                if _role_of(cand) != "skip" and ("百变" not in cand) and ("幻鸡" not in cand):
                    return cand
            return ""
        return cname

    def _reload_place_tree(self):
        self.tree_place.delete(*self.tree_place.get_children())
        deck = self.get_cur_deck()
        placements = deck.get("placements", [])
        for idx0, p in enumerate(placements):
            i = idx0 + 1
            en = "✅" if p.get("enabled", True) else "⏸"
            cname = p.get("card_name", "?")
            card = self.get_card_by_name(cname)
            cost = int(card.get("cost", 0)) if card else 0
            rc = (p.get("repair_card") or "").strip()
            if rc == "__skip__":
                c_disp = f"{cname}→补:跳过"
            elif rc:
                c_disp = f"{cname}→补:{rc}"
            elif ("百变" in cname) or ("幻鸡" in cname):
                auto_t = self._resolve_step_repair_card(placements, idx0, deck)
                c_disp = f"{cname}→补:{auto_t}" if auto_t else f"{cname}({cost}🔥)"
            else:
                c_disp = f"{cname}({cost}🔥)"
            ztag = "even" if (i % 2 == 0) else "odd"
            self.tree_place.insert("", "end", values=(i, en, c_disp, f"({p['x']}, {p['y']})", p.get("delay", 1.2)), tags=(ztag,))

    def _set_place_repair_card(self):
        """为选中放卡步骤指定【三层补阵】时实际要补种的本体卡（专门用于百变/幻鸡等复制卡！）"""
        sel = self.tree_place.selection()
        if not sel:
            messagebox.showinfo("提示", "请先在放卡步骤列表中选中一步（可右键点击对应行）！")
            return
        idx = self.tree_place.index(sel[0])
        deck = self.get_cur_deck()
        p = deck["placements"][idx]
        orig_name = p.get("card_name", "")
        cur_rc = (p.get("repair_card") or "").strip()
        card_names = [c["name"] for c in deck.get("cards", [])]

        win = tk.Toplevel(self.root)
        win.title(f"🔁 设置第 {idx+1} 步补阵替换卡")
        win.resizable(False, False)
        win.configure(bg=self._cur_theme()["card"])
        apply_win11_titlebar(win, self._cur_theme())
        win.transient(self.root)
        win.grab_set()

        body = ttk.Frame(win, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text=f"第 {idx+1} 步开局放【{orig_name}】({p['x']},{p['y']})\n补阵阶段这一格应该改种哪张本体卡？",
            font=("Microsoft YaHei", 9, "bold"),
        ).pack(anchor="w", pady=(0, 8))

        OPT_AUTO = "✨ 默认（普通卡同原卡 / 百变幻鸡自动推断）"
        OPT_SKIP = "🚫 补阵跳过这一格"
        choices = [OPT_AUTO, OPT_SKIP] + card_names
        cmb = ttk.Combobox(body, values=choices, width=32, state="readonly")
        if cur_rc == "__skip__":
            cmb.set(OPT_SKIP)
        elif cur_rc in card_names:
            cmb.set(cur_rc)
        else:
            cmb.set(OPT_AUTO)
        cmb.pack(fill="x", pady=4)

        def do_ok():
            val = cmb.get()
            if val == OPT_AUTO:
                p.pop("repair_card", None)
                desc = "默认自动"
            elif val == OPT_SKIP:
                p["repair_card"] = "__skip__"
                desc = "补阵跳过"
            else:
                p["repair_card"] = val
                desc = f"补阵改种【{val}】"
            self._reload_place_tree()
            children = self.tree_place.get_children()
            if 0 <= idx < len(children):
                self.tree_place.selection_set(children[idx])
            self.save_config()
            self.log(f"🔁 第 {idx+1} 步【{orig_name}】已设为：{desc}")
            win.destroy()

        bbar = ttk.Frame(body)
        bbar.pack(fill="x", pady=(8, 0))
        ttk.Button(bbar, text="✔ 保存", command=do_ok).pack(side="left", padx=4)
        ttk.Button(bbar, text="取消", command=win.destroy).pack(side="left", padx=4)
        win.bind("<Return>", lambda _e: do_ok())
        win.bind("<Escape>", lambda _e: win.destroy())
        win.update_idletasks()
        px = self.root.winfo_x() + max(20, (self.root.winfo_width() - win.winfo_width()) // 2)
        py = self.root.winfo_y() + max(20, (self.root.winfo_height() - win.winfo_height()) // 2)
        win.geometry(f"+{px}+{py}")

    def _on_place_tree_select(self, _):
        sel = self.tree_place.selection()
        if not sel:
            return
        idx = self.tree_place.index(sel[0])
        p = self.get_cur_deck()["placements"][idx]
        self.edit_card_combo.set(p.get("card_name", ""))
        self.ent_px.delete(0, "end")
        self.ent_px.insert(0, str(p["x"]))
        self.ent_py.delete(0, "end")
        self.ent_py.insert(0, str(p["y"]))
        self.ent_delay.delete(0, "end")
        self.ent_delay.insert(0, str(p.get("delay", 1.2)))

    def _apply_place_edit(self):
        sel = self.tree_place.selection()
        if not sel:
            messagebox.showinfo("提示", "请先在放卡列表选中要修改的一行！")
            return
        idx = self.tree_place.index(sel[0])
        try:
            nx = int(self.ent_px.get().strip())
            ny = int(self.ent_py.get().strip())
            nd = float(self.ent_delay.get().strip())
        except ValueError:
            messagebox.showwarning("提示", "X、Y 坐标必须是整数，间隔必须是数字！")
            return
        new_card = self.edit_card_combo.get().strip()
        p = self.get_cur_deck()["placements"][idx]
        if new_card:
            p["card_name"] = new_card
        p["x"], p["y"], p["delay"] = nx, ny, nd
        self._reload_place_tree()
        self._redraw_canvas_overlays()
        self.save_config()
        self.log(f"✅ 已修改第 {idx+1} 步：改为点击【{p['card_name']}】放到 ({nx}, {ny})，间隔 {nd}s")

    def _batch_replace_place_card(self):
        """一键将当前方案布阵中某张旧卡的全部落点（及可选的补阵替换指向）批量替换为另一张卡"""
        deck = self.get_cur_deck()
        placements = deck.get("placements") or []
        if not placements:
            messagebox.showinfo("提示", "当前方案还没有任何放卡步骤！")
            return
        lib_names = [c["name"] for c in deck.get("cards", []) if c.get("name")]
        if not lib_names:
            messagebox.showinfo("提示", "请先在【1.卡片库】录入你要替换成的目标新卡！")
            return

        # 统计布阵与补阵替换中出现过的所有卡名（即使旧卡已从卡片库删掉也能选中替换！）
        used_counts = {}
        for p in placements:
            cn = p.get("card_name", "")
            if cn:
                used_counts[cn] = used_counts.get(cn, 0) + 1
            rc = p.get("repair_card", "")
            if rc and rc != "__skip__" and rc not in used_counts:
                used_counts[rc] = 0
        old_choices = [f"{nm}（布阵 {cnt} 步）" for nm, cnt in used_counts.items()]
        old_raw_list = list(used_counts.keys())

        # 若当前选中了某一行，自动预选该行的卡名作为“原卡片”
        default_old_idx = 0
        sel = self.tree_place.selection()
        if sel:
            s_idx = self.tree_place.index(sel[0])
            if 0 <= s_idx < len(placements):
                s_cn = placements[s_idx].get("card_name", "")
                if s_cn in old_raw_list:
                    default_old_idx = old_raw_list.index(s_cn)

        win = tk.Toplevel(self.root)
        win.title("🔄 批量换卡（一键替换某张卡的全部落点）")
        win.resizable(False, False)
        th = self._cur_theme()
        win.configure(bg=th["card"])
        apply_win11_titlebar(win, th)
        win.transient(self.root)
        win.grab_set()

        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text="改卡组后无需重录坐标！将当前方案中旧卡的所有放卡点一次性换为新卡：",
            foreground=th["tip_fg"],
        ).pack(anchor="w", pady=(0, 8))

        r1 = ttk.Frame(body)
        r1.pack(fill="x", pady=4)
        ttk.Label(r1, text="要被替换的旧卡：", width=16).pack(side="left")
        var_old = tk.StringVar(value=old_choices[default_old_idx])
        cb_old = ttk.Combobox(r1, textvariable=var_old, values=old_choices, width=24, state="readonly")
        cb_old.pack(side="left", fill="x", expand=True)

        r2 = ttk.Frame(body)
        r2.pack(fill="x", pady=4)
        ttk.Label(r2, text="全部替换为新卡：", width=16).pack(side="left")
        default_new = next((n for n in lib_names if n != old_raw_list[default_old_idx]), lib_names[0])
        var_new = tk.StringVar(value=default_new)
        cb_new = ttk.Combobox(r2, textvariable=var_new, values=lib_names, width=24, state="readonly")
        cb_new.pack(side="left", fill="x", expand=True)

        var_sync_repair = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            body,
            text="同时把复制卡（百变/幻鸡）指向该旧卡的【补阵替换卡】也一并改为新卡",
            variable=var_sync_repair,
        ).pack(anchor="w", pady=(6, 4))

        def do_replace():
            oi = cb_old.current()
            if oi < 0 or oi >= len(old_raw_list):
                return
            old_nm = old_raw_list[oi]
            new_nm = var_new.get().strip()
            if not new_nm:
                return
            if old_nm == new_nm:
                messagebox.showinfo("提示", "旧卡与新卡名称相同，无需替换！", parent=win)
                return
            changed_steps = 0
            changed_repairs = 0
            sync_rep = bool(var_sync_repair.get())
            for p in placements:
                if p.get("card_name") == old_nm:
                    p["card_name"] = new_nm
                    changed_steps += 1
                if sync_rep and p.get("repair_card") == old_nm:
                    p["repair_card"] = new_nm
                    changed_repairs += 1
            self._reload_place_tree()
            self._redraw_canvas_overlays()
            self.save_config()
            extra = f"（另同步更新 {changed_repairs} 个补阵替换指向）" if changed_repairs else ""
            self.log(f"🔄 批量换卡完成：已将全部 {changed_steps} 步【{old_nm}】替换为【{new_nm}】{extra}！")
            win.destroy()

        bf = ttk.Frame(body)
        bf.pack(fill="x", pady=(10, 0))
        ttk.Button(bf, text="✔ 确认全部替换", command=do_replace).pack(side="left", padx=4)
        ttk.Button(bf, text="取消", command=win.destroy).pack(side="left", padx=4)
        win.bind("<Return>", lambda _e: do_replace())
        win.bind("<Escape>", lambda _e: win.destroy())
        win.update_idletasks()
        px = self.root.winfo_x() + max(20, (self.root.winfo_width() - win.winfo_width()) // 2)
        py = self.root.winfo_y() + max(20, (self.root.winfo_height() - win.winfo_height()) // 2)
        win.geometry(f"+{px}+{py}")

    def _move_place_step(self, delta: int):
        sel = self.tree_place.selection()
        if not sel:
            return
        idx = self.tree_place.index(sel[0])
        plist = self.get_cur_deck()["placements"]
        new_idx = idx + delta
        if 0 <= new_idx < len(plist):
            plist[idx], plist[new_idx] = plist[new_idx], plist[idx]
            self._reload_place_tree()
            items = self.tree_place.get_children()
            self.tree_place.selection_set(items[new_idx])
            self.tree_place.see(items[new_idx])
            self._redraw_canvas_overlays()
            self.save_config(silent=True)

    def _show_place_context_menu(self, event):
        row = self.tree_place.identify_row(event.y)
        if row:
            self.tree_place.selection_set(row)
            self.place_menu.tk_popup(event.x_root, event.y_root)

    def _move_place_to_index(self):
        sel = self.tree_place.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选中要移动的那一步！")
            return
        idx = self.tree_place.index(sel[0])
        plist = self.get_cur_deck()["placements"]
        n = len(plist)
        target_num = simpledialog.askinteger(
            "一键移动到指定序号",
            f"当前为第 {idx+1} 步【{plist[idx]['card_name']}】\n请输入要移动到的目标序号（1 ~ {n}）：",
            initialvalue=idx + 1,
            minvalue=1,
            maxvalue=n,
        )
        if target_num is None:
            return
        new_idx = target_num - 1
        if new_idx == idx:
            return
        item = plist.pop(idx)
        plist.insert(new_idx, item)
        self._reload_place_tree()
        items = self.tree_place.get_children()
        self.tree_place.selection_set(items[new_idx])
        self.tree_place.see(items[new_idx])
        self._redraw_canvas_overlays()
        self.save_config()
        self.log(f"✅ 已将【{item['card_name']}】从第 {idx+1} 步一键移至第 {new_idx+1} 步")

    def _duplicate_place_step(self):
        sel = self.tree_place.selection()
        if not sel:
            return
        idx = self.tree_place.index(sel[0])
        plist = self.get_cur_deck()["placements"]
        dup = dict(plist[idx])
        plist.insert(idx + 1, dup)
        self._reload_place_tree()
        items = self.tree_place.get_children()
        self.tree_place.selection_set(items[idx + 1])
        self.tree_place.see(items[idx + 1])
        self._redraw_canvas_overlays()
        self.save_config()
        self.log(f"✅ 已在第 {idx+2} 步复制【{dup['card_name']}】")

    def _toggle_place_enabled(self):
        sel = self.tree_place.selection()
        if not sel:
            return
        idx = self.tree_place.index(sel[0])
        p = self.get_cur_deck()["placements"][idx]
        p["enabled"] = not p.get("enabled", True)
        self._reload_place_tree()
        self._redraw_canvas_overlays()
        self.save_config(silent=True)

    def _del_place_step(self):
        sel = self.tree_place.selection()
        if not sel:
            return
        idx = self.tree_place.index(sel[0])
        del self.get_cur_deck()["placements"][idx]
        self._reload_place_tree()
        self._redraw_canvas_overlays()
        self.save_config()

    def _test_single_place(self):
        sel = self.tree_place.selection()
        if not sel:
            messagebox.showinfo("提示", "请先在列表中选中一步放卡动作！")
            return
        idx = self.tree_place.index(sel[0])
        step = self.get_cur_deck()["placements"][idx]
        threading.Thread(target=self._exec_single_placement, args=(step,), daemon=True).start()

    def _batch_set_delay(self):
        val = simpledialog.askfloat("批量修改间隔", "请输入要统一设置给当前卡组所有放卡步骤的间隔(秒)：", initialvalue=0.6, minvalue=0.1, maxvalue=60.0)
        if val is None:
            return
        for p in self.get_cur_deck().get("placements", []):
            p["delay"] = round(float(val), 2)
        self._reload_place_tree()
        self.save_config()
        self.log(f"✅ 已将当前卡组所有放卡步骤的间隔统一设为 {val:.2f}s")

    def _open_rescale_coords_dialog(self):
        """
        一键按比例无损对齐坐标（专治换浏览器 FCBrowser -> FFBrowser 或换分辨率导致的整体等比偏移）：
        自动检测当前浏览器中的 Flash 游戏主体画框，按旧画框 -> 新画框做线性坐标映射并自动备份！
        """
        full_img = CAPTURER.capture_full(self.hwnd) if (self.hwnd and user32.IsWindow(self.hwnd)) else self.current_pil_img
        if full_img is None:
            messagebox.showinfo("提示", "请先绑定正在显示游戏画面的浏览器窗口（不要最小化）！")
            return
        new_box = auto_detect_game_viewport(full_img) or [0, 0, full_img.width, full_img.height]
        deck = self.get_cur_deck()
        old_box = deck.get("ref_viewport") or [232, 0, 2328, 1312]

        win = tk.Toplevel(self.root)
        win.title("📐 一键对齐新浏览器 / 新分辨率坐标")
        win.resizable(True, True)
        win.configure(bg=self._cur_theme()["card"])
        apply_win11_titlebar(win, self._cur_theme())
        win.transient(self.root)
        win.grab_set()

        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)

        ow, oh = old_box[2] - old_box[0], old_box[3] - old_box[1]
        nw, nh = new_box[2] - new_box[0], new_box[3] - new_box[1]
        ttk.Label(
            body,
            text=(
                f"原录入画框 (默认旧 FCBrowser)：{old_box}  ({ow}×{oh})\n"
                f"当前检测画框 (实时游戏主体)  ：{new_box}  ({nw}×{nh})\n"
                f"缩放比例：X = {nw/max(1,ow):.4f}，Y = {nh/max(1,oh):.4f}"
            ),
            foreground=self._cur_theme()["tip_fg"],
            font=("Microsoft YaHei", 9, "bold"),
        ).pack(anchor="w", pady=(0, 8))

        f_old = ttk.Frame(body)
        f_old.pack(fill="x", pady=2)
        ttk.Label(f_old, text="旧画框(x0,y0,x1,y1):", width=18).pack(side="left")
        e_old = ttk.Entry(f_old, width=26)
        e_old.insert(0, ",".join(str(v) for v in old_box))
        e_old.pack(side="left", fill="x", expand=True)

        f_new = ttk.Frame(body)
        f_new.pack(fill="x", pady=2)
        ttk.Label(f_new, text="新画框(x0,y0,x1,y1):", width=18).pack(side="left")
        e_new = ttk.Entry(f_new, width=26)
        e_new.insert(0, ",".join(str(v) for v in new_box))
        e_new.pack(side="left", fill="x", expand=True)

        var_do_board = tk.BooleanVar(value=True)
        var_do_cards = tk.BooleanVar(value=True)
        var_do_global = tk.BooleanVar(value=False)
        ttk.Checkbutton(body, text="对齐当前方案的【放卡落点 + 开局角色点 + 进图点】", variable=var_do_board).pack(anchor="w", pady=2)
        ttk.Checkbutton(body, text="同时对齐当前方案的【顶部卡槽坐标】（若该号卡槽总数不同，可对齐后再微调卡槽）", variable=var_do_cards).pack(anchor="w", pady=2)
        ttk.Checkbutton(body, text="同时对齐全局【火苗监测区 + 通用收尾步骤】（切去新浏览器首次勾选一次即可！）", variable=var_do_global).pack(anchor="w", pady=2)

        def do_apply():
            try:
                ob = [int(x.strip()) for x in e_old.get().split(",")]
                nb = [int(x.strip()) for x in e_new.get().split(",")]
                if len(ob) != 4 or len(nb) != 4 or ob[2] <= ob[0] or ob[3] <= ob[1] or nb[2] <= nb[0] or nb[3] <= nb[1]:
                    raise ValueError("画框格式需为 x0,y0,x1,y1 且宽高 > 0")
            except Exception as ex:
                messagebox.showwarning("格式错误", str(ex), parent=win)
                return

            # 转换前自动备份一份配置
            try:
                if os.path.isfile(CONFIG_FILE):
                    ts = time.strftime("%Y%m%d_%H%M%S")
                    shutil.copy2(CONFIG_FILE, os.path.join(BACKUP_DIR, f"before_rescale_{ts}.json"))
            except Exception:
                pass

            def _map_xy(x, y):
                nx = int(round(nb[0] + (x - ob[0]) * (nb[2] - nb[0]) / (ob[2] - ob[0])))
                ny = int(round(nb[1] + (y - ob[1]) * (nb[3] - nb[1]) / (ob[3] - ob[1])))
                return nx, ny

            if var_do_board.get():
                for p in deck.get("placements", []):
                    p["x"], p["y"] = _map_xy(p["x"], p["y"])
                hero = deck.get("hero")
                if hero and "x" in hero and "y" in hero:
                    hero["x"], hero["y"] = _map_xy(hero["x"], hero["y"])
                for e in deck.get("enter_clicks", []):
                    e["x"], e["y"] = _map_xy(e["x"], e["y"])
            if var_do_cards.get():
                for c in deck.get("cards", []):
                    c["x"], c["y"] = _map_xy(c["x"], c["y"])
                d_roi = deck.get("fire_ocr_roi")
                if d_roi and len(d_roi) == 4:
                    x0, y0 = _map_xy(d_roi[0], d_roi[1])
                    x1, y1 = _map_xy(d_roi[2], d_roi[3])
                    deck["fire_ocr_roi"] = [x0, y0, x1, y1]
            if var_do_global.get():
                roi = self.config.get("fire_ocr_roi")
                if roi and len(roi) == 4:
                    x0, y0 = _map_xy(roi[0], roi[1])
                    x1, y1 = _map_xy(roi[2], roi[3])
                    self.config["fire_ocr_roi"] = [x0, y0, x1, y1]
                for fstep in self.config.get("finish_extra_clicks", []):
                    fstep["x"], fstep["y"] = _map_xy(fstep["x"], fstep["y"])
                self.config["ref_viewport"] = nb

            deck["ref_viewport"] = nb
            self.config["preview_crop"] = nb
            self._update_crop_btn_label()
            self._refresh_deck_ui()
            self._reload_finish_tree()
            self._redraw_canvas_overlays()
            self.save_config()
            self.log(f"📐 已按画框 {ob} -> {nb} 一键完成坐标比例对齐（原配置已自动备份至 backups/）！")
            win.destroy()

        bf = ttk.Frame(body)
        bf.pack(pady=10)
        ttk.Button(bf, text="✔ 立即一键对齐", command=do_apply).pack(side="left", padx=8)
        ttk.Button(bf, text="取消", command=win.destroy).pack(side="left", padx=8)

    def _update_fire_cfg(self):
        opts = self.get_cur_options()
        opts["auto_collect_fire"] = bool(self.var_auto_fire.get())
        opts["wait_for_fire"] = bool(self.var_wait_fire.get())
        opts["verify_placed"] = bool(self.var_verify_placed.get())
        opts["loop_placements"] = bool(self.var_loop_place.get())
        opts["continue_resets_battle"] = bool(self.var_continue_resets.get())
        self.save_config(silent=True)

    # ==================== 进图 & 收尾列表逻辑（均已按关卡方案彻底独立） ====================
    def _reload_enter_tree(self):
        self.tree_enter.delete(*self.tree_enter.get_children())
        for idx_e, item in enumerate(self.get_cur_deck().get("enter_clicks", [])):
            ztag = "even" if (idx_e % 2 == 1) else "odd"
            self.tree_enter.insert("", "end", values=(item["name"], item["x"], item["y"], item["delay"]), tags=(ztag,))

    def _del_enter_step(self):
        sel = self.tree_enter.selection()
        if sel:
            idx = self.tree_enter.index(sel[0])
            del self.get_cur_deck()["enter_clicks"][idx]
            self._reload_enter_tree()
            self.save_config()

    def _test_run_enter(self):
        threading.Thread(target=self._exec_enter_sequence, daemon=True).start()

    def _reload_finish_tree(self):
        self.tree_finish.delete(*self.tree_finish.get_children())
        for idx_f, item in enumerate(self.config.get("finish_extra_clicks", [])):
            ztag = "even" if (idx_f % 2 == 1) else "odd"
            self.tree_finish.insert("", "end", values=(item["name"], item["x"], item["y"], item["delay"]), tags=(ztag,))

    def _edit_finish_delay(self):
        sel = self.tree_finish.selection()
        if not sel:
            messagebox.showinfo("提示", "请先在收尾列表选中一行！")
            return
        idx = self.tree_finish.index(sel[0])
        item = self.config["finish_extra_clicks"][idx]
        val = simpledialog.askfloat(
            "修改等待时间",
            f"步骤【{item['name']}】点击后的等待秒数：\n（例如“开始洗牌”后建议等 4.5 秒，“翻牌”后建议等 2.0 秒）",
            initialvalue=float(item.get("delay", 1.5)),
            minvalue=0.1,
            maxvalue=30.0,
        )
        if val is not None:
            item["delay"] = round(float(val), 2)
            self._reload_finish_tree()
            self.save_config()

    def _del_finish_step(self):
        sel = self.tree_finish.selection()
        if sel:
            idx = self.tree_finish.index(sel[0])
            del self.config["finish_extra_clicks"][idx]
            self._reload_finish_tree()
            self.save_config()

    def _test_run_finish(self):
        threading.Thread(target=self._exec_finish_sequence, daemon=True).start()

    # ==================== 账号管理、独立 FFBrowser 启动 & 后台自动登录 ====================
    def _get_login_points(self) -> dict:
        pts = self.config.setdefault("login_points", {})
        pts.setdefault("open_xy", None)
        pts.setdefault("tab_xy", None)
        pts.setdefault("user_xy", None)
        pts.setdefault("pass_xy", None)
        pts.setdefault("submit_xy", None)
        pts.setdefault("after_clicks", [])
        return pts

    def _choose_ffbrowser_path(self):
        path = filedialog.askopenfilename(
            title="选择完整版 Flash 浏览器 (FFBrowser.exe)",
            filetypes=[("浏览器程序 (*.exe)", "*.exe"), ("所有文件", "*.*")],
        )
        if not path:
            return
        self.config["ffbrowser_path"] = path
        self.lbl_ff_path.config(text=f"浏览器: {os.path.basename(path)}")
        self.save_config()
        self.log(f"✅ 已设置浏览器路径: {path}")

    def _save_login_url(self):
        url = self.ent_login_url.get().strip() or DEFAULT_LOGIN_URL
        self.config["login_url"] = url
        self.save_config()
        self.log(f"✅ 已保存登录网址: {url}")

    def _save_auto_login_flag(self):
        self.config["auto_login_on_bot"] = bool(self.var_auto_login_bot.get())
        self.save_config(silent=True)

    def _refresh_login_pts_label(self):
        if not hasattr(self, "lbl_login_pts"):
            return
        pts = self._get_login_points()
        o = f"({pts['open_xy'][0]},{pts['open_xy'][1]})" if pts.get("open_xy") else "可选"
        tb = f"({pts['tab_xy'][0]},{pts['tab_xy'][1]})" if pts.get("tab_xy") else "可选"
        u = f"({pts['user_xy'][0]},{pts['user_xy'][1]})" if pts.get("user_xy") else "未设"
        p = f"({pts['pass_xy'][0]},{pts['pass_xy'][1]})" if pts.get("pass_xy") else "未设"
        s = f"({pts['submit_xy'][0]},{pts['submit_xy'][1]})" if pts.get("submit_xy") else "未设"
        ac = len(pts.get("after_clicks") or [])
        tpl_ok = "已录" if os.path.exists(os.path.join(TEMPLATE_DIR, "stage_login.png")) else "未录"
        self.lbl_login_pts.config(text=f"弹:{o}|切:{tb}|账:{u}|密:{p}|登:{s}|服:{ac}|模:{tpl_ok}")

    def _clear_login_after_clicks(self):
        pts = self._get_login_points()
        pts["after_clicks"] = []
        self._refresh_login_pts_label()
        self.save_config()
        self.log("已清空登录后进服点击步骤。")

    def _reload_accounts_tree(self):
        if not hasattr(self, "tree_accounts"):
            return
        prev_sw = self._switching_account
        self._switching_account = True
        try:
            self.tree_accounts.delete(*self.tree_accounts.get_children())
            accs = self.config.setdefault("accounts", [])
            active_id = self.config.get("active_account_id", "")
            with self._runs_lock:
                running_ids = set(self._active_runs.keys())
            sel_iid = None
            role_disp = {"host": "👑房主", "member": "🙋队员", "solo": "单刷"}
            for i, a in enumerate(accs):
                if "role" not in a:
                    a["role"] = "host" if i == 0 else "member"
                if "team_enabled" not in a:
                    a["team_enabled"] = (i < 2)
                pwd_status = "🔒已存" if a.get("password_enc") else "未填"
                r_txt = role_disp.get(a.get("role", "member"), "🙋队员")
                t_txt = "✅" if a.get("team_enabled", False) else "—"
                disp_name = a.get("name", "")
                if a.get("id", "") in running_ids:
                    disp_name = f"🟢 {disp_name}"
                ztag = "even" if (i % 2 == 1) else "odd"
                iid = self.tree_accounts.insert(
                    "", "end",
                    values=(disp_name, a.get("username", ""), r_txt, t_txt, pwd_status),
                    tags=(ztag,),
                )
                if a.get("id") == active_id:
                    sel_iid = iid
            children = self.tree_accounts.get_children()
            if sel_iid:
                self.tree_accounts.selection_set(sel_iid)
            elif children:
                self.tree_accounts.selection_set(children[0])
                self.config["active_account_id"] = accs[0].get("id", "")
        finally:
            self._switching_account = prev_sw

    def _cycle_account_role(self):
        acc, idx = self._get_selected_account()
        if not acc:
            messagebox.showinfo("提示", "请先在账号列表中选中一个账号！")
            return
        order = ["host", "member", "solo"]
        cur = acc.get("role", "member")
        nxt = order[(order.index(cur) + 1) % len(order)] if cur in order else "host"
        acc["role"] = nxt
        labels = {"host": "👑房主（等队员准备后再点开始）", "member": "🙋队员（回房先点准备通知房主）", "solo": "单刷（独立开战）"}
        self._reload_accounts_tree()
        children = self.tree_accounts.get_children()
        if 0 <= idx < len(children):
            self.tree_accounts.selection_set(children[idx])
        self.save_config()
        self.log(f"👑 已将账号【{acc.get('name', '')}】组队角色设为：{labels[nxt]}")

    def _toggle_account_team_enabled(self):
        acc, idx = self._get_selected_account()
        if not acc:
            messagebox.showinfo("提示", "请先在账号列表中选中一个账号！")
            return
        acc["team_enabled"] = not bool(acc.get("team_enabled", False))
        self._reload_accounts_tree()
        children = self.tree_accounts.get_children()
        if 0 <= idx < len(children):
            self.tree_accounts.selection_set(children[idx])
        self.save_config()
        state = "已加入组队联刷" if acc["team_enabled"] else "已移出组队联刷"
        self.log(f"☑ 账号【{acc.get('name', '')}】{state}。")

    def _get_selected_account(self):
        accs = self.config.setdefault("accounts", [])
        if not accs:
            return None, -1
        if hasattr(self, "tree_accounts"):
            sel = self.tree_accounts.selection()
            if sel:
                idx = self.tree_accounts.index(sel[0])
                if 0 <= idx < len(accs):
                    return accs[idx], idx
        active_id = self.config.get("active_account_id", "")
        for i, a in enumerate(accs):
            if a.get("id") == active_id:
                return a, i
        return accs[0], 0

    def _switch_to_account_window(self, acc: dict, warn_if_missing: bool = False) -> bool:
        """按账号的独立目录名精准定位并切换左侧实时预览到该账号的 FFBrowser 窗口"""
        if not acc:
            return False
        target_prof = _safe_profile_dirname(acc.get("profile_dir") or acc.get("id") or "").lower()
        pmap = self._get_profile_to_name_map()
        cands = find_fcbrowser_windows(pmap)
        matched = [i for i, c in enumerate(cands) if c[3] == target_prof]
        if not matched:
            if warn_if_missing:
                self.log(f"⏳ 账号【{acc.get('name', '')}】的独立浏览器尚未打开，请先点【🚀启动独立FFBrowser】！")
            return False
        best_idx = max(matched, key=lambda i: cands[i][2])
        best_hwnd = cands[best_idx][0]
        self.win_candidates = cands
        self.win_combo["values"] = [desc for _, desc, _, _ in cands]
        self.win_combo.current(best_idx)
        changed = (best_hwnd != self.hwnd)
        self.hwnd = best_hwnd
        self._auto_crop_tried = False
        CAPTURER.reset_cache(best_hwnd)
        cls = get_class_name(best_hwnd)
        self.lbl_hwnd.config(text=f"当前账号【{acc.get('name', '')}】HWND: {best_hwnd} ({cls})")
        if changed or warn_if_missing:
            self.refresh_preview()
            self.log(f"👁 已将实时画面切换到账号【{acc.get('name', '')}】(HWND={best_hwnd})")
        return True

    def _view_selected_account_window(self):
        acc, _ = self._get_selected_account()
        if not acc:
            messagebox.showinfo("提示", "请先在账号列表中选中一个账号！")
            return
        self._switch_to_account_window(acc, warn_if_missing=True)

    def _sync_account_combo_ui(self):
        if not hasattr(self, "account_combo"):
            return
        accs = self.config.get("accounts") or []
        if not accs:
            self.account_combo["values"] = ["默认"]
            self.var_active_account.set("默认")
            return
        labels = [a.get("name") or a.get("username") or a.get("id", "") for a in accs]
        self.account_combo["values"] = labels
        aid = self.config.get("active_account_id", "")
        sel_idx = 0
        for i, a in enumerate(accs):
            if a.get("id") == aid:
                sel_idx = i
                break
        self.config["active_account_id"] = accs[sel_idx].get("id", "")
        self.var_active_account.set(labels[sel_idx])

    def _on_account_combo_select(self, _):
        accs = self.config.get("accounts") or []
        if not accs:
            return
        idx = self.account_combo.current()
        if 0 <= idx < len(accs):
            self._switch_active_account(accs[idx].get("id", ""), switch_window=True)

    def _switch_active_account(self, acc_id: str, switch_window: bool = True):
        """切换当前活动账号：联动切换该账号专属卡组库 + 同步下拉框/列表选中 + 切换左侧实时画面"""
        if self._switching_account:
            return
        accs = self.config.get("accounts") or []
        target_idx = -1
        for i, a in enumerate(accs):
            if a.get("id") == acc_id:
                target_idx = i
                break
        if target_idx < 0:
            return
        self._switching_account = True
        try:
            # 切走前先记住旧账号的当前方案
            _, old_owner, _ = self._get_active_decks_store()
            old_owner["active_deck"] = self.var_active_deck.get()

            acc = accs[target_idx]
            self.config["active_account_id"] = acc.get("id", "")
            self._sync_account_combo_ui()
            if hasattr(self, "tree_accounts"):
                children = self.tree_accounts.get_children()
                if 0 <= target_idx < len(children):
                    self.tree_accounts.selection_set(children[target_idx])
                    self.tree_accounts.see(children[target_idx])

            decks = acc.setdefault("decks", {"默认关卡": _make_blank_deck()})
            if not decks:
                decks["默认关卡"] = _make_blank_deck()
            nxt_deck = acc.get("active_deck", "")
            if nxt_deck not in decks:
                nxt_deck = next(iter(decks.keys()))
            self.var_active_deck.set(nxt_deck)
            self._refresh_deck_ui()
            self.save_config(silent=True)
            if switch_window:
                self._switch_to_account_window(acc, warn_if_missing=False)
            self._sync_target_clears_ui()
            self._refresh_run_buttons(refresh_tree=False)
            self.log(f"👤 已切换到账号【{acc.get('name', '')}】专属卡组库（当前方案：{nxt_deck}，共 {len(decks)} 套方案）")
        finally:
            self._switching_account = False

    def _on_account_select(self, _):
        if self._switching_account:
            return
        acc, _ = self._get_selected_account()
        if acc and acc.get("id") != self.config.get("active_account_id"):
            self._switch_active_account(acc.get("id", ""), switch_window=True)
        elif acc:
            self._switch_to_account_window(acc, warn_if_missing=False)

    def _copy_deck_from_other_account(self):
        """跨账号复制卡组方案：把任意账号的某套关卡卡组与布阵完整复制到当前选中账号"""
        accs = self.config.get("accounts") or []
        if len(accs) < 2:
            messagebox.showinfo("提示", "请先添加至少 2 个账号，才能跨账号复制卡组！")
            return
        cur_decks, cur_owner, cur_name = self._get_active_decks_store()
        cur_id = cur_owner.get("id", "")

        choices = []
        for a in accs:
            if a.get("id") == cur_id:
                continue
            aname = a.get("name", "")
            for dname, ddata in (a.get("decks") or {}).items():
                choices.append((f"【{aname}】-> {dname} ({len(ddata.get('cards', []))}卡/{len(ddata.get('placements', []))}步)", a, dname, ddata))
        if not choices:
            messagebox.showinfo("提示", "其他账号下暂时没有可复制的卡组方案！")
            return

        win = tk.Toplevel(self.root)
        win.title(f"跨账号复制卡组到【{cur_name}】")
        win.resizable(True, True)
        win.configure(bg=self._cur_theme()["card"])
        apply_win11_titlebar(win, self._cur_theme())
        win.transient(self.root)
        win.grab_set()

        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=f"选择要复制到账号【{cur_name}】的源方案：", foreground=self._cur_theme()["tip_fg"]).pack(anchor="w", pady=4)
        var_src = tk.StringVar(value=choices[0][0])
        cb = ttk.Combobox(body, textvariable=var_src, values=[c[0] for c in choices], width=42, state="readonly")
        cb.pack(fill="x", pady=4)

        f2 = ttk.Frame(body)
        f2.pack(fill="x", pady=6)
        ttk.Label(f2, text="新方案名称:").pack(side="left")
        e_new = ttk.Entry(f2, width=22)
        e_new.insert(0, choices[0][2])
        e_new.pack(side="left", fill="x", expand=True, padx=4)

        def _on_src(_):
            idx = cb.current()
            if 0 <= idx < len(choices):
                e_new.delete(0, "end")
                e_new.insert(0, choices[idx][2])

        cb.bind("<<ComboboxSelected>>", _on_src)

        def do_copy():
            idx = cb.current()
            if idx < 0:
                return
            _, src_acc, src_dname, src_data = choices[idx]
            new_nm = e_new.get().strip() or src_dname
            if new_nm in cur_decks and not messagebox.askyesno("覆盖确认", f"当前账号【{cur_name}】已有方案【{new_nm}】，是否覆盖？", parent=win):
                return
            cur_decks[new_nm] = copy.deepcopy(src_data)
            self.var_active_deck.set(new_nm)
            self._refresh_deck_ui()
            self.save_config()
            self.log(f"📋 已从账号【{src_acc.get('name', '')}】复制方案【{src_dname}】到当前账号【{cur_name}】->【{new_nm}】！")
            win.destroy()

        bf = ttk.Frame(body)
        bf.pack(pady=8)
        ttk.Button(bf, text="✔ 确认复制", command=do_copy).pack(side="left", padx=8)
        ttk.Button(bf, text="取消", command=win.destroy).pack(side="left", padx=8)

    def _import_legacy_version_data(self):
        """一键继承旧版本文件夹的全部个人数据（配置、模板、卡片图标、火苗字形、可选独立浏览器目录），更新版本零重录！"""
        src_dir = filedialog.askdirectory(title="请选择旧版刷关模拟器文件夹（包含 meishi_config.json）")
        if not src_dir:
            return
        if os.path.abspath(src_dir) == os.path.abspath(DATA_DIR):
            messagebox.showinfo("提示", "你选择的就是当前正在使用的本机数据目录，无需导入。")
            return
        src_cfg = os.path.join(src_dir, "meishi_config.json")
        if not os.path.isfile(src_cfg):
            messagebox.showwarning("提示", "所选文件夹里没有找到 meishi_config.json，请确认选对了旧版目录！")
            return
        if not messagebox.askyesno(
            "确认一键继承旧版数据",
            f"将从以下目录无损导入配置、识别模板、卡片图标与火苗字形库到本机固定数据目录：\n{src_dir}\n  -> {DATA_DIR}\n\n"
            "导入前会自动把当前配置备份到 backups/ 目录，确认继续？",
        ):
            return
        try:
            # 1. 自动备份当前配置
            if os.path.isfile(CONFIG_FILE):
                ts = time.strftime("%Y%m%d_%H%M%S")
                shutil.copy2(CONFIG_FILE, os.path.join(BACKUP_DIR, f"before_migrate_{ts}.json"))

            # 2. 复制配置文件与资源文件夹（跳过浏览器锁文件防报错）
            ign = shutil.ignore_patterns("LOCK", "lockfile", "*.tmp", "SingletonLock", "SingletonCookie", "SingletonSocket")
            shutil.copy2(src_cfg, CONFIG_FILE)
            copied_items = ["meishi_config.json"]
            for sub in ("meishi_templates", "card_icons", "fire_digits"):
                s_sub = os.path.join(src_dir, sub)
                d_sub = os.path.join(DATA_DIR, sub)
                if os.path.isdir(s_sub):
                    shutil.copytree(s_sub, d_sub, dirs_exist_ok=True, ignore=ign)
                    copied_items.append(sub + "/")

            s_ff = os.path.join(src_dir, "ff_profiles")
            if os.path.isdir(s_ff) and os.listdir(s_ff):
                if messagebox.askyesno("浏览器登录态", "旧版文件夹中检测到 ff_profiles（多账号登录态目录），是否一并复制过来？"):
                    shutil.copytree(s_ff, FF_PROFILE_ROOT, dirs_exist_ok=True, ignore=ign)
                    copied_items.append("ff_profiles/")

            # 3. 实时重载内存配置与界面
            self.config = self.load_config()
            self._icon_refs.clear()
            FIRE_OCR.reload_custom_templates()
            self._reload_accounts_tree()
            self._sync_account_combo_ui()
            self._refresh_deck_ui()
            self._reload_finish_tree()
            self._refresh_template_status()
            self._refresh_login_pts_label()
            self._apply_ui_theme(self.config.get("ui_theme", self.ui_theme_key), save=False)
            self.save_config(silent=True)
            self.log(f"✅ 已成功继承旧版全部数据（{', '.join(copied_items)}），无需重新录入任何内容！")
            messagebox.showinfo("继承成功", f"已成功导入：{', '.join(copied_items)}\n全部卡组、模板、图标与设置已立刻生效！")
        except Exception as e:
            messagebox.showerror("继承失败", f"导入旧版数据时出错：\n{e}")

    def _ask_account_dialog(self, title: str, init_name="", init_user="", init_pass="", init_profile=""):
        res = []
        win = tk.Toplevel(self.root)
        win.title(title)
        win.resizable(True, True)
        win.configure(bg=self._cur_theme()["card"])
        apply_win11_titlebar(win, self._cur_theme())
        win.transient(self.root)
        win.grab_set()

        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text="密码使用本机 Windows DPAPI 加密保存（仅当前电脑当前系统账户可解密）",
            foreground=self._cur_theme()["tip_fg"],
        ).pack(pady=(0, 8))

        def _row(label_txt, init_val, show_char=""):
            f = ttk.Frame(body)
            f.pack(fill="x", pady=4)
            ttk.Label(f, text=label_txt, width=10).pack(side="left")
            ent = ttk.Entry(f, width=26, show=show_char)
            ent.insert(0, init_val)
            ent.pack(side="left", fill="x", expand=True)
            return ent

        e_name = _row("账号备注:", init_name)
        e_user = _row("7k7k账号:", init_user)
        e_pass = _row("登录密码:", init_pass, show_char="*")
        e_prof = _row("独立目录:", init_profile)

        def ok(_=None):
            nm = e_name.get().strip() or e_user.get().strip()
            us = e_user.get().strip()
            pw = e_pass.get()
            pf = _safe_profile_dirname(e_prof.get().strip() or nm or f"acc_{int(time.time())}")
            if not us:
                messagebox.showwarning("提示", "请填写 7k7k 登录账号！", parent=win)
                return
            res.append((nm, us, pw, pf))
            win.destroy()

        bf = ttk.Frame(body)
        bf.pack(pady=10)
        ttk.Button(bf, text="✔ 保存", command=ok).pack(side="left", padx=8)
        ttk.Button(bf, text="取消", command=win.destroy).pack(side="left", padx=8)
        e_name.focus_set()
        win.bind("<Return>", ok)
        self.root.wait_window(win)
        return res[0] if res else None

    def _add_account(self):
        accs = self.config.setdefault("accounts", [])
        n = len(accs) + 1
        info = self._ask_account_dialog("新增 7k7k 账号", init_name=f"账号{n}", init_profile=f"acc_{n}")
        if not info:
            return
        nm, us, pw, pf = info
        acc_id = f"acc_{int(time.time() * 1000)}"
        # 若这是新增的第一个账号，自动平滑继承此前录好的全部全局卡组；后续新账号获得各自独立的干净卡组库
        if len(accs) == 0 and self.config.get("decks"):
            init_decks = copy.deepcopy(self.config["decks"])
            init_active = self.var_active_deck.get() if self.var_active_deck.get() in init_decks else next(iter(init_decks.keys()))
        else:
            init_decks = {"默认关卡": _make_blank_deck()}
            init_active = "默认关卡"
        accs.append({
            "id": acc_id,
            "name": nm,
            "username": us,
            "password_enc": encrypt_secret(pw) if pw else "",
            "profile_dir": pf,
            "decks": init_decks,
            "active_deck": init_active,
        })
        self._reload_accounts_tree()
        self._switch_active_account(acc_id, switch_window=False)
        self.save_config()
        self.log(f"✅ 已新增账号【{nm}】({us})，已分配独立卡组库与目录 ff_profiles/{pf}")

    def _edit_account(self):
        acc, idx = self._get_selected_account()
        if not acc:
            messagebox.showinfo("提示", "请先在账号列表中选中一个账号！")
            return
        cur_pwd = decrypt_secret(acc.get("password_enc", ""))
        info = self._ask_account_dialog(
            f"编辑账号【{acc.get('name', '')}】",
            init_name=acc.get("name", ""),
            init_user=acc.get("username", ""),
            init_pass=cur_pwd,
            init_profile=acc.get("profile_dir", ""),
        )
        if not info:
            return
        nm, us, pw, pf = info
        acc["name"] = nm
        acc["username"] = us
        acc["password_enc"] = encrypt_secret(pw) if pw else ""
        acc["profile_dir"] = pf
        self._reload_accounts_tree()
        self._sync_account_combo_ui()
        self.save_config()
        self.log(f"✅ 已更新账号【{nm}】({us}) 加密配置。")

    def _delete_account(self):
        acc, idx = self._get_selected_account()
        if not acc:
            return
        if messagebox.askyesno("确认删除", f"确定删除账号【{acc.get('name', '')}】及其名下卡组吗？（不会删掉其浏览器缓存目录）"):
            del self.config["accounts"][idx]
            self._reload_accounts_tree()
            self._sync_account_combo_ui()
            if self.config["accounts"]:
                self._switch_active_account(self.config["accounts"][0].get("id", ""), switch_window=False)
            else:
                self._refresh_deck_ui()
            self.save_config()

    def _launch_selected_account_browser(self):
        acc, _ = self._get_selected_account()
        if not acc:
            messagebox.showinfo("提示", "请先点【➕加账号】添加一个 7k7k 账号！")
            return
        exe = detect_ffbrowser_exe(self.config.get("ffbrowser_path", ""))
        if not exe:
            messagebox.showwarning("提示", "未找到 FFBrowser.exe，请先点【📂选浏览器】选择完整版 Flash 浏览器程序！")
            return
        self.config["ffbrowser_path"] = exe
        self.lbl_ff_path.config(text=f"浏览器: {os.path.basename(exe)}")
        url = (self.ent_login_url.get().strip() if hasattr(self, "ent_login_url") else "") or self.config.get("login_url") or DEFAULT_LOGIN_URL
        self.config["login_url"] = url
        prof_dir = os.path.join(FF_PROFILE_ROOT, _safe_profile_dirname(acc.get("profile_dir") or acc.get("id") or "acc_1"))
        os.makedirs(prof_dir, exist_ok=True)
        # 提前关闭“设为默认浏览器”检查，防止顶部弹出白条把登录框与游戏坐标整体顶歪！
        try:
            def_dir = os.path.join(prof_dir, "Default")
            os.makedirs(def_dir, exist_ok=True)
            pref_path = os.path.join(def_dir, "Preferences")
            prefs = {}
            if os.path.isfile(pref_path):
                with open(pref_path, "r", encoding="utf-8") as f:
                    prefs = json.load(f)
            prefs.setdefault("browser", {})["check_default_browser"] = False
            prefs["browser"]["show_home_button"] = False
            with open(pref_path, "w", encoding="utf-8") as f:
                json.dump(prefs, f, ensure_ascii=False)
        except Exception:
            pass

        cmd = [
            exe,
            f"--user-data-dir={prof_dir}",
            "--no-proxy-server",
            "--start-maximized",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-infobars",
            "--disable-session-crashed-bubble",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-features=CalculateNativeWinOcclusion,IntensiveWakeUpThrottling,UseEcoQoSForBackgroundProcess",
            "--new-window",
            url,
        ]
        try:
            proc = subprocess.Popen(cmd)
            self.log(f"🚀 已启动账号【{acc['name']}】的独立 FFBrowser（目录: ff_profiles/{os.path.basename(prof_dir)}，已屏蔽默认浏览器提示条 + 自动最大化）！")

            # 若 FFBrowser 忽略 --start-maximized，2秒后用 Win32 强制最大化确保窗口尺寸 100% 统一
            def _ensure_max(pid_target=proc.pid):
                for _ in range(12):
                    time.sleep(0.4)
                    found_h = []
                    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HWND, wintypes.LPARAM)

                    def _cb(h, __):
                        if user32.IsWindowVisible(h):
                            p = wintypes.DWORD()
                            user32.GetWindowThreadProcessId(h, ctypes.byref(p))
                            if p.value == pid_target and "Chrome_WidgetWin" in get_class_name(h):
                                found_h.append(h)
                        return 1

                    user32.EnumWindows(WNDENUMPROC(_cb), 0)
                    if found_h:
                        user32.ShowWindow(found_h[0], SW_MAXIMIZE)
                        time.sleep(0.5)
                        self.root.after(0, lambda a=acc: self._switch_to_account_window(a, warn_if_missing=False))
                        return

            threading.Thread(target=_ensure_max, daemon=True).start()
        except Exception as e:
            messagebox.showerror("启动失败", f"无法启动浏览器:\n{e}")

    def _find_hwnd_for_account(self, acc: dict) -> int:
        """精准查找指定账号(按独立目录名)当前可见的最优渲染层 HWND，不修改全局 self.hwnd"""
        if not acc:
            return 0
        target_prof = _safe_profile_dirname(acc.get("profile_dir") or acc.get("id") or "").lower()
        cands = find_fcbrowser_windows(self._get_profile_to_name_map())
        matched = [c for c in cands if c[3] == target_prof]
        if not matched:
            return 0
        best = max(matched, key=lambda c: c[2])
        return best[0]

    def _exec_auto_login(self, acc: dict = None, token=None, target_hwnd: int = 0) -> bool:
        if acc is None:
            acc, _ = self._get_selected_account()
        if not acc:
            self.log("⚠ 未选中任何账号，请先在【5.账号登录】添加并选中账号！")
            return False
        acc_id = acc.get("id") or acc.get("name", "")
        acc_name = acc.get("name", "")
        if acc_id in self._logging_in_accounts:
            self.log(f"⏳ 账号【{acc_name}】正在登录中，跳过重复点击。")
            return False

        # 锁定本线程专属的目标窗口 HWND（绝不共用会随界面切换变化的 self.hwnd，支持多账号同时并行登录！）
        hwnd = int(target_hwnd or self._find_hwnd_for_account(acc) or self.hwnd)
        if not hwnd or not user32.IsWindow(hwnd):
            self.log(f"⚠ 账号【{acc_name}】尚未找到有效浏览器窗口，无法执行后台自动登录！")
            return False
        pts = copy.deepcopy(self._get_login_points())
        u_xy = pts.get("user_xy")
        p_xy = pts.get("pass_xy")
        s_xy = pts.get("submit_xy")
        if not (u_xy and p_xy and s_xy):
            self.log("⚠ 请先在登录画面依次点【📍账号框】【📍密码框】【📍登录钮】完成坐标录入！")
            return False
        username = acc.get("username", "").strip()
        password = decrypt_secret(acc.get("password_enc", ""))
        if not username or not password:
            self.log(f"⚠ 账号【{acc_name}】缺少用户名或密码，请先点【✏改账密】补全！")
            return False

        self._logging_in_accounts.add(acc_id)
        try:
            self.log(f"🔑 [{acc_name}] 开始在专属窗口 HWND={hwnd} 执行后台自动填账密登录...")
            o_xy = pts.get("open_xy")
            if o_xy:
                bg_click_fast(hwnd, int(o_xy[0]), int(o_xy[1]))
                self.log(f"  [{acc_name}][弹出登录框] 后台点击 ({o_xy[0]}, {o_xy[1]})，等待弹窗加载...")
                if token is not None:
                    self._sleep_interruptible(1.2, token)
                    if not self._is_active(token):
                        return False
                else:
                    time.sleep(1.2)
            t_xy = pts.get("tab_xy")
            if t_xy:
                bg_click_fast(hwnd, int(t_xy[0]), int(t_xy[1]))
                self.log(f"  [{acc_name}][切回登录页] 后台点击 ({t_xy[0]}, {t_xy[1]})")
                if token is not None:
                    self._sleep_interruptible(0.45, token)
                    if not self._is_active(token):
                        return False
                else:
                    time.sleep(0.45)
            bg_clear_and_type(hwnd, int(u_xy[0]), int(u_xy[1]), username)
            if token is not None and not self._is_active(token):
                return False
            time.sleep(0.18)
            bg_clear_and_type(hwnd, int(p_xy[0]), int(p_xy[1]), password)
            if token is not None and not self._is_active(token):
                return False
            time.sleep(0.2)
            bg_click_fast(hwnd, int(s_xy[0]), int(s_xy[1]))
            self.log(f"  ✅ [{acc_name}] 已后台填入账密并点击【登录】({s_xy[0]}, {s_xy[1]})")

            for step in pts.get("after_clicks") or []:
                wait_s = float(step.get("delay", 2.5))
                if token is not None:
                    self._sleep_interruptible(wait_s, token)
                    if not self._is_active(token):
                        return False
                else:
                    time.sleep(wait_s)
                # 若点登录后该账号打开了新标签页，自动追踪同一账号的新可见渲染层，绝不点到别的账号！
                if not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd):
                    new_h = self._find_hwnd_for_account(acc)
                    if new_h:
                        hwnd = new_h
                bg_click(hwnd, int(step["x"]), int(step["y"]))
                self.log(f"  [{acc_name}][进服] 后台点击 {step.get('name', '进服点')} ({step['x']}, {step['y']})")
            return True
        finally:
            self._logging_in_accounts.discard(acc_id)

    def _run_selected_account_login(self):
        acc, _ = self._get_selected_account()
        if not acc:
            messagebox.showinfo("提示", "请先在【5.账号登录】添加并选中一个账号！")
            return
        # 精准定位该账号自己的专属窗口 HWND（锁定后传给独立线程，切走看别的号也互不干扰！）
        acc_hwnd = self._find_hwnd_for_account(acc)
        if acc_hwnd:
            self._switch_to_account_window(acc, warn_if_missing=False)
        else:
            if not self.hwnd or not user32.IsWindow(self.hwnd):
                self._refresh_window_list()
            acc_hwnd = self.hwnd
        if not acc_hwnd or not user32.IsWindow(acc_hwnd):
            messagebox.showwarning("提示", f"尚未检测到账号【{acc.get('name', '')}】的浏览器窗口，请先点【🚀启动独立FFBrowser】！")
            return
        pts = self._get_login_points()
        if not (pts.get("user_xy") and pts.get("pass_xy") and pts.get("submit_xy")):
            messagebox.showinfo(
                "尚未录制登录页点位",
                "请先把浏览器打开到 7k7k 登录页面，然后在下方依次点击：\n"
                "【📍账号框】-> 点左侧画面账号输入框\n"
                "【📍密码框】-> 点左侧画面密码输入框\n"
                "【📍登录钮】-> 点左侧画面登录按钮\n"
                "录好一次后，所有账号即可一键后台自动登录！",
            )
            return
        threading.Thread(target=self._exec_auto_login, args=(copy.deepcopy(acc), None, acc_hwnd), daemon=True).start()

    def _clear_profile_templates(self):
        pname = self.var_active_deck.get()
        pdir = self._get_profile_tpl_dir(pname)
        if messagebox.askyesno("清除专属模板", f"确定清除方案【{pname}】的专属模板（清除后将自动回退使用公共模板）吗？"):
            for fn in os.listdir(pdir):
                fp = os.path.join(pdir, fn)
                if os.path.isfile(fp):
                    try:
                        os.remove(fp)
                    except Exception:
                        pass
            self._refresh_template_status()
            self.log(f"🗑 已清除方案【{pname}】的专属模板")

    def _refresh_template_status(self):
        pdir = self._get_profile_tpl_dir()
        status = []
        for title, fname in [
            ("选卡", "stage_select.png"),
            ("准备", "stage_ready.png"),
            ("放角色", "stage_place_hero.png"),
            ("继续", "btn_continue.png"),
            ("结束", "stage_finish.png"),
            ("失败", "stage_fail.png"),
        ]:
            if os.path.exists(os.path.join(pdir, fname)):
                tag = "🔒专属"
            elif os.path.exists(os.path.join(TEMPLATE_DIR, fname)):
                tag = "✅公共"
            else:
                tag = "❌"
            status.append(f"{title}:{tag}")
        self.lbl_templates.config(text=" | ".join(status))

    # ==================== 后台自动执行动作 ====================
    def _is_active(self, token=None) -> bool:
        if token is None:
            return True
        return self.running and (token in self._active_tokens)

    def _ctx_hwnd(self, ctx=None) -> int:
        return int(ctx["hwnd"]) if (ctx and ctx.get("hwnd")) else self.hwnd

    def _ctx_cap(self, ctx=None):
        return ctx["capturer"] if (ctx and ctx.get("capturer") is not None) else CAPTURER

    def _ctx_deck(self, ctx=None) -> dict:
        if ctx and ctx.get("acc") is not None:
            acc = ctx["acc"]
            decks = acc.get("decks") or {}
            dname = ctx.get("deck_name") or acc.get("active_deck") or ""
            if dname in decks:
                d = decks[dname]
                d.setdefault("enter_clicks", [])
                d.setdefault("cards", [])
                d.setdefault("placements", [])
                d.setdefault("hero", {"enabled": True, "on_continue": False, "on_start": False, "x": 960, "y": 660, "wait_before": 3.0, "wait_after": 4.0, "clicks": 2})
                opts = d.setdefault("options", {})
                opts.setdefault("auto_collect_fire", False)
                opts.setdefault("wait_for_fire", True)
                opts.setdefault("verify_placed", True)
                opts.setdefault("loop_placements", False)
                opts.setdefault("continue_resets_battle", False)
                return d
        return self.get_cur_deck()

    def _ctx_fire_roi(self, ctx=None):
        """
        火苗监测区四级优先级（每局进战斗自动锁定最准，适配不同卡数与分辨率）：
        1. 本局进战斗自动锁定的 ctx["auto_fire_roi"]
        2. 当前卡组方案专属 deck["fire_ocr_roi"]
        3. 当前账号默认 acc["fire_ocr_roi"]
        4. 全局兜底 config["fire_ocr_roi"]
        """
        if ctx:
            auto_r = ctx.get("auto_fire_roi")
            if auto_r and len(auto_r) == 4:
                return auto_r
        deck = self._ctx_deck(ctx)
        d_roi = deck.get("fire_ocr_roi")
        if d_roi and len(d_roi) == 4:
            return d_roi
        if ctx and ctx.get("acc") is not None:
            a_roi = ctx["acc"].get("fire_ocr_roi")
            if a_roi and len(a_roi) == 4:
                return a_roi
        else:
            _, owner, _ = self._get_active_decks_store()
            a_roi = owner.get("fire_ocr_roi")
            if a_roi and len(a_roi) == 4:
                return a_roi
        return self.config.get("fire_ocr_roi")

    def _auto_lock_fire_roi_for_battle(self, ctx=None, screen: Image.Image = None, save_to_deck: bool = True):
        """进入战斗后自动定位并锁定本局火苗数字框 [l, t, r, b]，返回 (roi, fire_val) 或 (None, None)"""
        hwnd = self._ctx_hwnd(ctx)
        cap = self._ctx_cap(ctx)
        img = screen if screen is not None else (cap.capture_full(hwnd) if (hwnd and user32.IsWindow(hwnd)) else None)
        if img is None:
            return None, None
        cur_deck = self._ctx_deck(ctx)
        roi, val, _ = auto_locate_fire_roi(img, deck_cards=cur_deck.get("cards"))
        if roi is None:
            return None, None
        if ctx is not None:
            ctx["auto_fire_roi"] = list(roi)
        if save_to_deck:
            old_r = cur_deck.get("fire_ocr_roi")
            if old_r != list(roi):
                cur_deck["fire_ocr_roi"] = list(roi)
                try:
                    self.root.after(0, lambda: self.save_config(silent=True))
                except Exception:
                    pass
        ctx_aid = ctx.get("acc_id", "") if ctx else ""
        if (not ctx_aid) or (ctx_aid == self.config.get("active_account_id")):
            self.latest_fire_val = val
            try:
                self.root.after(0, lambda v=val: (self.lbl_fire_live.config(text=f"🔥 实时火苗: {v}"), self._redraw_canvas_overlays()))
            except Exception:
                pass
        pfx = self._ctx_prefix(ctx)
        self.log(f"{pfx}🎯 [自动锁火苗] 本局已自动锁定火苗位置 {roi}（当前火苗: {val}）")
        return roi, val

    def _manual_auto_locate_fire_roi(self):
        """手动点击【🔍寻火】立即自动扫描当前战斗画面并锁定火苗区"""
        img = CAPTURER.capture_full(self.hwnd) or self.current_pil_img
        if img is None:
            messagebox.showinfo("提示", "尚未获取到游戏画面，请先打开游戏并进入战斗！")
            return
        roi, val = self._auto_lock_fire_roi_for_battle(ctx=None, screen=img, save_to_deck=True)
        if roi is None:
            messagebox.showinfo("未检测到战斗火苗框", "当前画面未识别到战斗左上角的火苗数字框。\n请在【已进入战斗且顶栏可见】时再试，或右键手动框选。")
        else:
            self._redraw_canvas_overlays()
            messagebox.showinfo("自动锁定成功", f"已自动定位并锁定火苗区：{roi}\n当前识别火苗数值：{val}\n\n（挂机时每次进入战斗也会自动重新锁定！）")

    def _ctx_card(self, card_name: str, ctx=None):
        for c in self._ctx_deck(ctx).get("cards", []):
            if c["name"] == card_name:
                return c
        return None

    def _ctx_prefix(self, ctx=None) -> str:
        if ctx and ctx.get("acc_name") and (ctx.get("is_team") or len(self._active_runs) > 1):
            r_tag = {"host": "房主", "member": "队员", "solo": "单刷"}.get(ctx.get("role", ""), "")
            return f"[{r_tag}:{ctx.get('acc_name', '')}] "
        return ""

    def _update_team_progress_ui(self, acc_name: str, short_status: str):
        with self._team_lock:
            self._team_status[acc_name] = short_status
            summary = " | ".join(f"{k}:{v}" for k, v in self._team_status.items())
        hdr = "🤝 联刷中" if self.team_running else "⚡ 多号运行中"
        self.root.after(0, lambda t=f"{hdr} · {summary}": self.lbl_bot_progress.config(text=t))

    def _exec_enter_sequence(self, token=None, ctx=None):
        hwnd = self._ctx_hwnd(ctx)
        deck = self._ctx_deck(ctx)
        deck_name = ctx.get("deck_name", "") if ctx else self.var_active_deck.get()
        pfx = self._ctx_prefix(ctx)
        self.log(f"{pfx}>>> 执行【选卡组({deck_name}) & 开战/准备】...")
        for step in deck.get("enter_clicks", []):
            if not self._is_active(token):
                return
            bg_click(hwnd, step["x"], step["y"])
            self.log(f"  {pfx}[进图] 后台点击 {step['name']} ({step['x']}, {step['y']})")
            self._sleep_interruptible(float(step.get("delay", 0.8)), token)

    def _sleep_interruptible(self, seconds: float, token=None):
        end_t = time.time() + max(0.0, seconds)
        while time.time() < end_t:
            if token is not None:
                if not self._is_active(token):
                    return
            elif not self.running:
                return
            time.sleep(0.08)

    def _bg_glide_and_click(self, x: int, y: int, hwnd: int = 0):
        """带虚拟鼠标平滑移入与较长按住时间的点击（专门适配 Flash 角色放置与灵敏度高的控件）"""
        h = int(hwnd or self.hwnd)
        bg_move(h, max(10, x - 60), y)
        time.sleep(0.05)
        bg_move(h, max(10, x - 20), y)
        time.sleep(0.05)
        cx, cy = _to_client_xy(h, x, y)
        lparam = make_lparam(cx, cy)
        user32.PostMessageW(h, WM_MOUSEMOVE, 0, lparam)
        time.sleep(0.08)
        user32.PostMessageW(h, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
        time.sleep(0.08)
        user32.PostMessageW(h, WM_LBUTTONUP, 0, lparam)

    def _exec_place_hero(self, wait: bool = True, wait_after: bool = True, token=None, ctx=None):
        hwnd = self._ctx_hwnd(ctx)
        pfx = self._ctx_prefix(ctx)
        hero = self._ctx_deck(ctx).get("hero", {})
        if not hero.get("enabled", False):
            return
        hx, hy = int(hero.get("x", 960)), int(hero.get("y", 660))
        wait_s = float(hero.get("wait_before", 3.0)) if wait else 0.0
        after_s = float(hero.get("wait_after", 4.0)) if wait_after else 0.0
        clicks = max(1, int(hero.get("clicks", 2)))
        if wait_s > 0:
            self.log(f"{pfx}>>> 等待地图加载 {wait_s:.1f}s 后放置角色到 ({hx}, {hy})...")
            self._sleep_interruptible(wait_s, token)
            if not self._is_active(token):
                return
        for i in range(clicks):
            if not self._is_active(token):
                return
            self._bg_glide_and_click(hx, hy, hwnd=hwnd)
            self.log(f"  {pfx}[放角色] 第 {i+1}/{clicks} 次平滑移入并点击角色落点 ({hx}, {hy})")
            if i < clicks - 1:
                self._sleep_interruptible(0.45, token)
        if after_s > 0 and self._is_active(token):
            self.log(f"{pfx}>>> 角色已放置，等待开局倒计时/动画 {after_s:.1f}s 后开始放卡...")
            self._sleep_interruptible(after_s, token)

    def _wait_battle_and_place_hero(self, tpl_hero: str, max_wait: float = 45.0, token=None, ctx=None):
        """
        点完【开始】或【继续战斗】后，耐心等待战斗加载与【请放置您的角色】真正出现：
        - 已截取 stage_place_hero.png 时：严格死等【请放置您的角色】真正弹出(兼容初次加载慢，最长等 45s)，
          绝不因为顶部先出现“火苗=50”或加载画面而抢跑漏放！
        - 放完后还会确认提示是否消失，若仍在则补点，确保 100% 稳放人物！
        """
        hwnd = self._ctx_hwnd(ctx)
        cap = self._ctx_cap(ctx)
        pfx = self._ctx_prefix(ctx)
        has_tpl = os.path.exists(tpl_hero)
        if not has_tpl:
            self._exec_place_hero(wait=True, wait_after=True, token=token, ctx=ctx)
            return

        self.log(f"{pfx}>>> 正在等待地图加载并监测【请放置您的角色】弹出（初次加载较慢也会耐心等待，最长 {int(max_wait)}s）...")
        deadline = time.time() + max_wait
        best_h_seen = 0.0
        last_wait_log = time.time()

        # 先等 0.8s 让房间界面切走
        self._sleep_interruptible(0.8, token)
        while self._is_active(token) and time.time() < deadline:
            sc_now = cap.capture_full(hwnd)
            if sc_now is not None:
                ok_h, _, _, sc_h = match_template_numpy(sc_now, tpl_hero, 0.58)
                if sc_h > best_h_seen:
                    best_h_seen = sc_h
                if ok_h:
                    if not self._is_active(token):
                        return
                    self.log(f"{pfx}🎯 捕捉到【请放置您的角色】(匹配度={sc_h:.2f})，立刻放置角色！")
                    self._sleep_interruptible(0.25, token)
                    self._exec_place_hero(wait=False, wait_after=False, token=token, ctx=ctx)
                    # 二次确认：若 0.35s 后【请放置您的角色】提示仍在，补点一次确保 100% 落位！
                    self._sleep_interruptible(0.35, token)
                    if not self._is_active(token):
                        return
                    sc_chk = cap.capture_full(hwnd)
                    if sc_chk is not None:
                        still_there, _, _, _ = match_template_numpy(sc_chk, tpl_hero, 0.58)
                        if still_there and self._is_active(token):
                            hero = self._ctx_deck(ctx).get("hero", {})
                            hx, hy = int(hero.get("x", 960)), int(hero.get("y", 660))
                            self.log(f"  {pfx}[放角色] 提示仍在，自动补点确认落位...")
                            self._bg_glide_and_click(hx, hy, hwnd=hwnd)
                    # 角色确认落位后再执行放后等待
                    after_s = float(self._ctx_deck(ctx).get("hero", {}).get("wait_after", 4.0))
                    if after_s > 0 and self._is_active(token):
                        self.log(f"{pfx}>>> 角色已稳妥放置，等待开局倒计时/动画 {after_s:.1f}s 后开始放卡...")
                        self._sleep_interruptible(after_s, token)
                    return

            if time.time() - last_wait_log >= 5.0:
                last_wait_log = time.time()
                self.log(f"{pfx}⏳ 仍在等待进图/【请放置您的角色】出现...（当前最高匹配={best_h_seen:.2f}）")
            self._sleep_interruptible(0.20, token)

        if self._is_active(token):
            self.log(f"{pfx}⚠ 等待【请放置您的角色】超时(最高匹配={best_h_seen:.2f})，执行兜底放置角色。")
            self._exec_place_hero(wait=False, wait_after=True, token=token, ctx=ctx)

    def _sample_slot_brightness(self, img: Image.Image, cx: int, cy: int) -> float:
        """采样卡槽上半部卡面区域的平均亮度（冷却遮罩总从顶部开始覆盖，检测最灵敏准确）"""
        if img is None:
            return -1.0
        iw, ih = img.size
        box = (max(0, cx - 22), max(0, cy - 28), min(iw, cx + 22), min(ih, cy + 16))
        if box[2] <= box[0] or box[3] <= box[1]:
            return -1.0
        arr = np.asarray(img.crop(box).convert("L"), dtype=np.float32)
        return float(arr.mean())

    def _read_fire_from_img(self, img: Image.Image, ctx=None):
        roi = self._ctx_fire_roi(ctx)
        if not roi or len(roi) != 4 or img is None:
            return None
        val, _, _ = FIRE_OCR.read_number(img.crop((roi[0], roi[1], roi[2], roi[3])))
        return val

    def _sample_slot_brightness_roi(self, cx: int, cy: int, ctx=None) -> float:
        """
        极速局部 ROI 采样卡槽亮度（专防飞向左上角的巨型黄色/白金火苗光球遮挡误判！）：
        1. 同时剔除亮黄光晕 (R>200, G>145, R-B>28) 与白金过曝球心 (R>235, G>215, B>140)；
        2. 使用中位数 (median) 抗局部光斑干扰；若光球遮挡面积 > 35%，自动稍等 0.16s 待火球飞过后再重采！
        """
        hwnd = self._ctx_hwnd(ctx)
        cap = self._ctx_cap(ctx)
        for attempt in range(2):
            roi_img = cap.capture_roi(hwnd, max(0, cx - 22), max(0, cy - 28), cx + 22, cy + 16)
            if roi_img is None:
                return -1.0
            rgb = np.asarray(roi_img.convert("RGB"), dtype=np.float32)
            r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
            gray = 0.299 * r + 0.587 * g + 0.114 * b
            # 仅剔除真正的高饱和金黄色火苗光球（避免把白色/米白色卡如【软糖】或高光卡面误当成火球剔除！）
            is_fire_orb = (r > 215.0) & (g > 155.0) & ((r - b) > 45.0)
            orb_ratio = float(is_fire_orb.mean())
            if attempt == 0 and orb_ratio > 0.35:
                time.sleep(0.16)
                continue
            valid = gray[~is_fire_orb]
            if valid.size >= gray.size * 0.25:
                return float(np.median(valid))
        return float(np.percentile(gray, 20))

    def _read_fire_fast(self, ctx=None):
        """极速局部 ROI 识别实时火苗（耗时 ~1ms，按账号独立火苗区）"""
        roi = self._ctx_fire_roi(ctx)
        if not roi or len(roi) != 4:
            return None
        hwnd = self._ctx_hwnd(ctx)
        cap = self._ctx_cap(ctx)
        roi_img = cap.capture_roi(hwnd, roi[0], roi[1], roi[2], roi[3])
        if roi_img is None:
            return None
        val, _, _ = FIRE_OCR.read_number(roi_img)
        return val

    def _get_card_icon_vec(self, icon_name: str):
        """加载并缓存卡槽 32x32 图标的零均值单位向量（用于 0.4ms 判定顶栏卡片是否仍在战斗画面中）"""
        if not icon_name:
            return None
        key = os.path.basename(icon_name)
        if key in self._card_icon_vec_cache:
            return self._card_icon_vec_cache[key]
        path = os.path.join(CARD_ICON_DIR, key)
        if not os.path.exists(path):
            self._card_icon_vec_cache[key] = None
            return None
        try:
            with Image.open(path) as im:
                arr = np.asarray(im.convert("RGB").resize((32, 32), Image.Resampling.BILINEAR), dtype=np.float32).ravel()
            arr = arr - float(arr.mean())
            norm = float(np.linalg.norm(arr))
            vec = (arr / norm) if norm > 1e-6 else None
        except Exception:
            vec = None
        self._card_icon_vec_cache[key] = vec
        return vec

    def _card_slot_icon_score(self, card: dict, hwnd: int, cap):
        """计算当前画面卡槽位置与已保存卡片图标的 RGB 归一化相关度 (-1~1)；无图标时返回 None"""
        vec = self._get_card_icon_vec(card.get("icon", ""))
        if vec is None:
            return None
        l, t, r, b = get_window_rect(hwnd)
        iw, ih = r - l, b - t
        if iw < 100 or ih < 100:
            return None
        rx = max(24, int(iw * 0.022))
        ry = max(28, int(ih * 0.036))
        cx, cy = int(card["x"]), int(card["y"])
        crop = cap.capture_roi(hwnd, max(0, cx - rx), max(0, cy - ry), min(iw, cx + rx), min(ih, cy + ry))
        if crop is None:
            return None
        arr = np.asarray(crop.convert("RGB").resize((32, 32), Image.Resampling.BILINEAR), dtype=np.float32).ravel()
        arr = arr - float(arr.mean())
        norm = float(np.linalg.norm(arr))
        if norm <= 1e-6:
            return 0.0
        return float(np.dot(arr / norm, vec))

    def _is_battle_card_bar_visible(self, card: dict, ctx=None) -> bool:
        """
        卡槽视觉指纹锁（专防翻宝箱/结算/房间列表等亮色非战斗界面误点！）：
        - 真实战斗画面（含卡片冷却变灰）时，卡槽与原卡片图标 RGB 相关度通常在 0.70~0.98；
        - 一旦切到【翻宝箱】或【选卡房间】，顶栏被蓝色边框/其他界面覆盖，相关度骤降到 < 0.35！
        - 若当前卡因飞过金黄火球短暂低于 0.45，再抽查 1 张距离最远的参考卡；两张都不匹配则 100% 确认已离场，零误点立刻交回阶段识别！
        """
        hwnd = self._ctx_hwnd(ctx)
        cap = self._ctx_cap(ctx)
        sc1 = self._card_slot_icon_score(card, hwnd, cap)
        if sc1 is None:
            return True
        if sc1 >= 0.45:
            return True
        # 防止飞向左上角的巨型火苗光球刚好盖住单张卡：抽查距离最远的另一张带图标卡片
        deck = self._ctx_deck(ctx)
        best_other = None
        best_dist = -1
        cx = int(card["x"])
        for other in deck.get("cards", []):
            if other is card or other.get("name") == card.get("name"):
                continue
            if not other.get("icon"):
                continue
            dist = abs(int(other.get("x", 0)) - cx)
            if dist > best_dist:
                best_dist = dist
                best_other = other
        if best_other is not None:
            sc2 = self._card_slot_icon_score(best_other, hwnd, cap)
            if sc2 is not None and sc2 >= 0.45:
                return True
        return False

    def _exec_single_placement(self, step: dict, verify: bool = False, screen_before: Image.Image = None, ctx=None, fast: bool = False):
        """
        【抗火球干扰 + 安全回点卡槽验亮法】：
        返回状态码:
          - "ok"        : 确认放卡成功
          - "cd"        : 卡片仍在冷却 CD 中（未拿起，未做第3下回点）
          - "bounced"   : 卡片明明就绪拿起来了，但该格子放不下去（已干净退回卡槽）
        """
        hwnd = self._ctx_hwnd(ctx)
        pfx = self._ctx_prefix(ctx)
        cname = step.get("card_name", "")
        card = self._ctx_card(cname, ctx)
        if not card:
            self.log(f"{pfx}⚠ 找不到卡片【{cname}】的卡槽坐标，跳过该步！")
            return "ok"
        cx, cy = card["x"], card["y"]
        gx, gy = step["x"], step["y"]
        card_cost = int(card.get("cost", 0))

        # 铲子专属逻辑：无火苗消耗、无CD，点铲子 -> 点目标格 -> 补一次右键防空地粘铲子
        if "铲" in cname:
            bg_click_fast(hwnd, cx, cy)
            time.sleep(0.08)
            bg_click_fast(hwnd, gx, gy)
            time.sleep(0.08)
            bg_right_click(hwnd, gx, gy)
            self.log(f"  {pfx}✅ [铲除卡片] 【{cname}】({cx},{cy}) -> ({gx},{gy})")
            return "ok"

        # 1) 卡槽视觉指纹锁（0.4ms 零开销）：一旦切到【翻宝箱/房间/结算】等亮色非战斗界面，卡槽图标消失，立刻中止点击绝不误点宝箱！
        if verify and not self._is_battle_card_bar_visible(card, ctx=ctx):
            return "modal"

        b_init = self._sample_slot_brightness_roi(cx, cy, ctx=ctx) if verify else -1.0
        # 2) 弹窗黑幕双重守卫（1ms 零开销）：
        #    a) 结算/继续战斗黑幕会瞬间压暗顶栏卡槽 (b_init < 72)；
        #    b) 也会瞬间压暗左上角白底火苗框（正常白底 p90 > 180，弹窗黑幕下会骤降到 < 135）！
        #    一旦检测到黑幕，立刻中止点击，绝不误点【领取奖励】或【提前翻牌】！
        cur_froi = self._ctx_fire_roi(ctx)
        has_fire_roi = bool(cur_froi and len(cur_froi) == 4)
        if verify:
            if fast and 0.0 <= b_init < 72.0:
                return "modal"
            if has_fire_roi:
                f_roi_img = self._ctx_cap(ctx).capture_roi(
                    hwnd, cur_froi[0], cur_froi[1], cur_froi[2], cur_froi[3]
                )
                if f_roi_img is not None:
                    f_p90 = float(np.percentile(np.asarray(f_roi_img.convert("L"), dtype=np.float32), 90))
                    if f_p90 < 135.0:
                        return "modal"
        fire_init = self._read_fire_fast(ctx=ctx) if (verify and has_fire_roi) else None

        # 1. 点击卡槽拿卡 -> 点击场地放卡
        bg_click_fast(hwnd, cx, cy)
        time.sleep(0.048 if fast else 0.065)
        bg_click_fast(hwnd, gx, gy)

        if not verify:
            self.log(f"  {pfx}[放卡] 选【{cname}】({cx},{cy}) -> 放 ({gx},{gy})")
            return "ok"

        # 2. 等待 2~3 个 Flash 渲染帧再验亮与验扣火，防止高特效掉帧时抢在变灰前截屏！
        time.sleep(0.090 if fast else 0.105)
        b_mid = self._sample_slot_brightness_roi(cx, cy, ctx=ctx)
        # 若顶栏在 90ms 内骤降超过 75 且跌破 72（例如 195->36 / 181->67），说明刚好弹出结算/继续黑幕，立刻停止补阵！
        if fast and 0.0 <= b_mid < 72.0 and (b_init - b_mid) >= 75.0:
            return "modal"
        fire_mid = self._read_fire_fast(ctx=ctx) if has_fire_roi else None

        became_grey = (
            b_init > 35.0
            and b_mid >= 0.0
            and b_mid < b_init * 0.91
            and (b_init - b_mid) >= 8.0
        )
        # 合理扣火区间：若卡片填了真实消耗 (card_cost > 0)，严格按 card_cost 校验防单帧 OCR 抖动误判；
        # 若卡片未填消耗 (card_cost == 0)，则要求第2/3步扣火一致且 >= 50，防止 0 火卡(如软糖/盘子)被偶发 OCR 抖动误判已放下！
        min_drop = max(25, card_cost - 125) if card_cost > 0 else 50
        max_drop = (card_cost + 60) if card_cost > 0 else 650
        fire_mid_dropped = (
            fire_init is not None
            and fire_mid is not None
            and min_drop <= (fire_init - fire_mid) <= max_drop
        )
        if not (became_grey or fire_mid_dropped):
            return "cd"

        # 3. 确认拿起/扣火了 -> 左键回点卡槽取消未放下的卡（Flash 中右键不能取消拿起的卡！），并立刻移开鼠标防止悬浮动画遮挡卡槽！
        bg_click_fast(hwnd, cx, cy)
        time.sleep(0.018 if fast else 0.02)
        bg_move(hwnd, gx, gy)
        time.sleep(0.075 if fast else 0.09)
        b_final = self._sample_slot_brightness_roi(cx, cy, ctx=ctx)
        fire_final = self._read_fire_fast(ctx=ctx) if has_fire_roi else None
        if fire_final is not None:
            ctx_aid = ctx.get("acc_id", "") if ctx else ""
            if (not ctx_aid) or (ctx_aid == self.config.get("active_account_id")):
                self.latest_fire_val = fire_final
                self.root.after(0, lambda v=fire_final: self.lbl_fire_live.config(text=f"🔥 实时火苗: {v}"))

        stayed_grey_in_cd = (
            b_init > 35.0
            and b_final >= 0.0
            and b_final < b_init * 0.90
            and (b_init - b_final) >= 9.0
        )
        # 回点退卡后，如果火苗依然净减少合理区间 (未退回)，说明卡片已真正种下；
        # 当 card_cost == 0 时额外要求 fire_mid 也稳定扣火（避免 0 火卡因单帧 OCR 错读假成功！）
        fire_still_spent = (
            fire_init is not None
            and fire_final is not None
            and min_drop <= (fire_init - fire_final) <= max_drop
            and (card_cost > 0 or fire_mid_dropped)
        )
        if stayed_grey_in_cd or fire_still_spent:
            reason = (
                f"验灰入CD({b_init:.0f}->{b_final:.0f})"
                if stayed_grey_in_cd
                else f"回点后净扣火({fire_init}->{fire_final})"
            )
            tag = "🔧补阵成功" if fast else "✅ [放卡成功"
            end_b = "]" if not fast else ""
            if fast:
                self.log(f"  {pfx}🔧 [补阵成功/{reason}] 【{cname}】 -> ({gx},{gy})")
            else:
                self.log(f"  {pfx}✅ [放卡成功/{reason}] 【{cname}】 -> ({gx},{gy})")
            return "ok"

        return "bounced"

    # ==================== 三层简洁补阵引擎（🧱基础层 → ⚡辅助层 → ⚔主力层） ====================
    def _build_repair_plan(self, cur_deck: dict, active_steps: list) -> list:
        """
        将第 1 轮布阵整理为严格三层顺序的极速补阵队列（跳过【🚫不补阵】如铲子）：
          1. 🧱基础层（盘子、软糖等解决地图限制的卡）
          2. ⚡辅助层（火盆、坩埚、冰沙等增幅辅助卡）
          3. ⚔主力层（法师蛇、炎凰马、烤串、蜜糖等核心卡）
        对于开局用来骗 CD 的【百变 / 幻鸡】格子，补阵时自动替换为对应相邻本体卡，绝不会变错成废卡！
        """
        cards_by_name = {c["name"]: c for c in cur_deck.get("cards", [])}

        def _role_of(name: str) -> str:
            c = cards_by_name.get(name)
            return _get_card_role(c) if c else _infer_card_role(name)

        tiers = {"base": [], "support": [], "main": []}
        seen = set()

        for i, st in enumerate(active_steps):
            xy = (int(st["x"]), int(st["y"]))
            target = self._resolve_step_repair_card(active_steps, i, cur_deck)
            if not target:
                continue

            tr = _role_of(target)
            if tr not in tiers:
                continue
            key = (tr, target, xy[0], xy[1])
            if key in seen:
                continue
            seen.add(key)
            tiers[tr].append((tr, CARD_ROLE_LABEL.get(tr, tr), target, xy[0], xy[1]))

        return tiers["base"] + tiers["support"] + tiers["main"]

    def _exec_smart_repair_burst(
        self,
        my_token: int,
        ctx: dict,
        cur_deck: dict,
        active_steps: list,
        repair_state: dict,
        set_prog,
        max_slice_s: float = 1.6,
    ):
        """
        三层极速非阻塞补阵（每次最多跑 1.6s 就交回主循环检测继续/结算/战败，绝不漏判结算！）：
        - 严格按【🧱基础层 → ⚡辅助层 → ⚔主力层】巡检空位；
        - 自动跳过冷却中或火苗暂不够的卡（绝不卡在单一步），空位立刻补种、已有卡干净退回不粘手。
        """
        cd_until = repair_state.setdefault("cd_until", {})
        opts = cur_deck["options"]
        wait_fire = bool(opts.get("wait_for_fire", True))
        fire_roi = self._ctx_fire_roi(ctx)
        use_fire = bool(wait_fire and fire_roi and len(fire_roi) == 4)
        slice_deadline = time.perf_counter() + max_slice_s

        tasks = repair_state.get("tasks")
        cursor = int(repair_state.get("cursor", 0))
        if not tasks or cursor >= len(tasks):
            tasks = self._build_repair_plan(cur_deck, active_steps)
            repair_state["tasks"] = tasks
            cursor = 0
            repair_state["cursor"] = 0

        if not tasks:
            return

        while cursor < len(tasks) and self._is_active(my_token) and time.perf_counter() < slice_deadline:
            _, tlabel, cname, tx, ty = tasks[cursor]
            cursor += 1
            repair_state["cursor"] = cursor

            now_m = time.perf_counter()
            if now_m < cd_until.get(cname, 0.0):
                continue
            card = self._ctx_card(cname, ctx)
            if not card:
                continue
            cost = int(card.get("cost", 0))
            if use_fire:
                cf = self._read_fire_fast(ctx=ctx)
                if cf is None:
                    return "modal"  # 不在战斗画面，立刻交回主循环检测结算/继续战斗
                if cost > 0 and cf < cost:
                    continue

            set_prog(f"补阵:{tlabel}[{cname}]", f"🔁 三层补阵：{tlabel}【{cname}】({tx},{ty})")
            res = self._exec_single_placement(
                {"card_name": cname, "x": tx, "y": ty}, verify=True, ctx=ctx, fast=True
            )
            if res == "modal":
                return "modal"
            if res == "cd":
                cd_until[cname] = time.perf_counter() + 2.2
            elif res == "ok":
                cd_until[cname] = time.perf_counter() + 3.0
        return "ok"

    def _exec_collect_fire(self, ctx=None):
        # 扫火苗前先右键取消一次，确保绝对不会拖着未放下的卡片满屏绕圈！
        hwnd = self._ctx_hwnd(ctx)
        l, t, r, b = self.config.get("fire_area", [420, 240, 2150, 1200])
        bg_right_click(hwnd, (l + r) // 2, (t + b) // 2)
        time.sleep(0.03)
        for y in range(t, b, 150):
            for x in range(l, r, 180):
                bg_move(hwnd, x, y)
                time.sleep(0.006)

    def _park_cursor_left(self, ctx=None):
        """将后台虚拟鼠标移至窗口最左侧边缘（不动真实鼠标），防止一局结束回房后悬停触发老鼠详情介绍挡住【开始】按钮"""
        hwnd = self._ctx_hwnd(ctx)
        if not hwnd or not user32.IsWindow(hwnd):
            return
        try:
            l, t, r, b = get_window_rect(hwnd)
            ih = max(200, b - t)
            bg_move(hwnd, 8, ih // 3)
        except Exception:
            bg_move(hwnd, 8, 300)

    def _exec_finish_sequence(self, token=None, ctx=None):
        hwnd = self._ctx_hwnd(ctx)
        pfx = self._ctx_prefix(ctx)
        self.log(f"{pfx}>>> 执行【全关卡通用 · 战斗结束翻牌与收尾】...")
        steps = self.config.get("finish_extra_clicks", [])
        for idx, step in enumerate(steps):
            if not self._is_active(token):
                return
            bg_click(hwnd, step["x"], step["y"])
            self.log(f"  {pfx}[收尾] 后台点击 {step['name']} ({step['x']}, {step['y']})")
            # 最后一步（通常是【完成】）点完立刻把虚拟鼠标移到最左侧，避免回房时悬停到老鼠详情页遮挡【开始】
            if idx == len(steps) - 1:
                time.sleep(0.05)
                self._park_cursor_left(ctx=ctx)
            self._sleep_interruptible(float(step.get("delay", 1.5)), token)
        if self._is_active(token):
            self._park_cursor_left(ctx=ctx)

    # ==================== 主状态机 ====================
    def _get_target_clears_for_key(self, key: str = "", acc: dict = None) -> int:
        """读取指定账号预设的目标刷关次数（0 = 无限刷）"""
        if isinstance(acc, dict):
            try:
                return max(0, int(acc.get("target_clears", 0) or 0))
            except Exception:
                return 0
        if key and key != "default":
            for a in self.config.get("accounts") or []:
                if a.get("id") == key:
                    try:
                        return max(0, int(a.get("target_clears", 0) or 0))
                    except Exception:
                        return 0
        _, owner, _ = self._get_active_decks_store()
        try:
            return max(0, int(owner.get("target_clears", self.config.get("target_clears", 0)) or 0))
        except Exception:
            return 0

    def _sync_target_clears_ui(self):
        """切换账号或启动时同步底部【目标】刷关次数输入框与显示"""
        if not hasattr(self, "var_target_clears"):
            return
        _, owner, _ = self._get_active_decks_store()
        try:
            val = max(0, int(owner.get("target_clears", self.config.get("target_clears", 0)) or 0))
        except Exception:
            val = 0
        self.var_target_clears.set(str(val))
        self._refresh_clear_count_ui()

    def _on_target_clears_change(self, silent_invalid: bool = False):
        """实时保存当前账号的预设刷关次数（支持挂机中途动态修改，0=无限）"""
        raw = (self.var_target_clears.get() if hasattr(self, "var_target_clears") else "").strip()
        if raw == "":
            if silent_invalid:
                return
            val = 0
        else:
            try:
                val = max(0, min(9999, int(raw)))
            except ValueError:
                if silent_invalid:
                    return
                val = 0
        _, owner, _ = self._get_active_decks_store()
        old_val = int(owner.get("target_clears", 0) or 0)
        owner["target_clears"] = val
        if owner is self.config:
            self.config["target_clears"] = val
        if not silent_invalid:
            self.var_target_clears.set(str(val))
        if val != old_val:
            self.save_config(silent=True)
        self._refresh_clear_count_ui()

    def _refresh_clear_count_ui(self):
        """按账号分别展示刷关次数与目标进度：单号显示【账号名: 3/10 次】，多号并排显示【号A:3/10 | 号B:2】"""
        if not hasattr(self, "lbl_clear_count"):
            return
        with self._team_lock:
            items = [
                (k, self._account_clear_names.get(k, k), cnt)
                for k, cnt in self._account_clear_counts.items()
                if cnt > 0
            ]
        if not items:
            cur_k, cur_acc, _ = self._get_current_run_key()
            tgt = self._get_target_clears_for_key(cur_k, acc=cur_acc)
            txt = f"🏆 已刷: 0/{tgt} 次" if tgt > 0 else "🏆 已刷: 0 次"
        elif len(items) == 1:
            k, nm, cnt = items[0]
            tgt = self._get_target_clears_for_key(k)
            frac = f"{cnt}/{tgt}" if tgt > 0 else f"{cnt}"
            txt = f"🏆 {nm}: {frac} 次" if (nm and nm != "default") else f"🏆 已刷: {frac} 次"
        else:
            parts = []
            for k, nm, cnt in items:
                tgt = self._get_target_clears_for_key(k)
                frac = f"{cnt}/{tgt}" if tgt > 0 else f"{cnt}"
                parts.append(f"{nm}:{frac}")
            txt = "🏆 " + " | ".join(parts)
        self.lbl_clear_count.config(text=txt)

    def _reset_clear_count(self):
        cur_key, _, cur_name = self._get_current_run_key()
        with self._team_lock:
            nonzero_keys = [k for k, c in self._account_clear_counts.items() if c > 0]
            if len(nonzero_keys) >= 2 and self._account_clear_counts.get(cur_key, 0) > 0:
                self._account_clear_counts.pop(cur_key, None)
                self._account_last_clear_ts.pop(cur_key, None)
                self.clear_count = sum(self._account_clear_counts.values())
                msg = f"已清零账号【{cur_name or cur_key}】的刷关次数（其他账号统计保留，再点一次可全部清零）。"
            else:
                self._account_clear_counts.clear()
                self._account_clear_names.clear()
                self._account_last_clear_ts.clear()
                self.clear_count = 0
                self._last_clear_ts = 0.0
                msg = "已将全部账号的刷关次数统计清零。"
        self._refresh_clear_count_ui()
        self.log(msg)

    def _on_target_clears_reached(self, run_key: str, acc_name: str, cnt: int, tgt: int):
        """某个账号达到预设目标次数后在主线程优雅收尾 UI 状态（绝不影响其他未达标账号！）"""
        self._stop_single_bot(run_key, custom_log=(
            f"🎯 账号【{acc_name or '当前窗口'}】已完成预设目标 {cnt}/{tgt} 次，已自动停止该账号挂机！"
        ))
        self._refresh_clear_count_ui()

    def _increment_clear_count(self, ctx=None) -> bool:
        """为当前账号 +1 刷关计数；若达到该账号预设目标次数，立即停掉该账号并返回 True"""
        key = "default"
        acc_name = ""
        acc_obj = None
        run_key = ""
        if ctx:
            key = ctx.get("acc_id") or ctx.get("run_key") or "default"
            run_key = ctx.get("run_key") or key
            acc_name = ctx.get("acc_name") or ""
            acc_obj = ctx.get("acc")
        else:
            cur_k, cur_acc, cur_n = self._get_current_run_key()
            key = cur_k or "default"
            run_key = key
            acc_name = cur_n or ""
            acc_obj = cur_acc
        pfx = self._ctx_prefix(ctx)
        with self._team_lock:
            now = time.time()
            # 按账号独立 15 秒防抖：防止同一号结算动画重复计次，同时不同号同时结算互不影响！
            if now - self._account_last_clear_ts.get(key, 0.0) < 15.0:
                return False
            self._account_last_clear_ts[key] = now
            self._last_clear_ts = now
            cnt = self._account_clear_counts.get(key, 0) + 1
            self._account_clear_counts[key] = cnt
            self._account_clear_names[key] = acc_name or key
            self.clear_count = sum(self._account_clear_counts.values())
        tgt = self._get_target_clears_for_key(key, acc=acc_obj)
        self.root.after(0, self._refresh_clear_count_ui)
        if acc_name:
            t_str = f"/{tgt}" if tgt > 0 else ""
            self.log(f"{pfx}🏆 账号【{acc_name}】累计已刷完第 {cnt}{t_str} 次！")
        else:
            t_str = f"/{tgt}" if tgt > 0 else ""
            self.log(f"{pfx}🏆 本次累计已刷完第 {cnt}{t_str} 次！")

        if tgt > 0 and cnt >= tgt:
            # 立刻作废当前账号 token，防止主线程回调执行前开启下一局
            with self._runs_lock:
                rinfo = self._active_runs.get(run_key)
                if rinfo:
                    self._active_tokens.discard(rinfo["token"])
            self.root.after(0, lambda rk=run_key, nm=acc_name, c=cnt, t=tgt: self._on_target_clears_reached(rk, nm, c, t))
            return True
        return False

    def _get_current_run_key(self):
        """返回当前界面选中账号的唯一运行键、账号对象、账号显示名"""
        _, owner, acc_name = self._get_active_decks_store()
        pinned_acc = owner if (owner is not self.config) else None
        if pinned_acc and pinned_acc.get("id"):
            return pinned_acc["id"], pinned_acc, (acc_name or pinned_acc.get("name", ""))
        return f"hwnd:{int(self.hwnd or 0)}", None, (acc_name or "")

    def _refresh_run_buttons(self, refresh_tree: bool = True):
        """按当前选中账号的运行状态实时刷新顶部启停按钮与账号列表运行标记"""
        th = self._cur_theme()
        with self._runs_lock:
            active_keys = set(self._active_runs.keys())
            total = len(self._active_runs)
        cur_key, _, cur_name = self._get_current_run_key()
        cur_running = cur_key in active_keys
        if hasattr(self, "btn_start"):
            if cur_running:
                s_txt = f"⏹ 停止【{cur_name}】 (F11)" if cur_name else "⏹ 停止后台挂机 (F11)"
                s_bg = th["stop_bg"]
            else:
                if total > 0:
                    s_txt = f"▶ 追加启动【{cur_name}】 (F11)" if cur_name else "▶ 追加启动当前号 (F11)"
                else:
                    s_txt = "▶ 启动后台自动闯关 (F11)"
                s_bg = th["start_bg"]
            self.btn_start.configure(
                text=s_txt, bg=s_bg, fg="#ffffff", activebackground=s_bg,
                activeforeground="#ffffff", relief="flat", bd=0, cursor="hand2",
            )
        if hasattr(self, "btn_team_start"):
            if total > 0:
                tm_txt = f"⏹ 停止全部 ({total}号)" if total >= 2 else "⏹ 停止全部挂机"
                tm_bg = th["stop_bg"]
            else:
                tm_txt = "🤝 组队联刷"
                tm_bg = th["accent"]
            self.btn_team_start.configure(
                text=tm_txt, bg=tm_bg, fg="#ffffff", activebackground=tm_bg,
                activeforeground="#ffffff", relief="flat", bd=0, cursor="hand2",
            )
        if refresh_tree:
            self._reload_accounts_tree()

    def _stop_single_bot(self, run_key: str, custom_log: str = ""):
        """单独停止某一个正在运行的账号，不影响其他并行运行中的账号"""
        with self._runs_lock:
            info = self._active_runs.pop(run_key, None)
            if info:
                self._active_tokens.discard(info["token"])
            rem = len(self._active_runs)
            self.running = rem > 0
            if rem == 0:
                self.team_running = False
                self.worker_threads = []
        if not info:
            self._refresh_run_buttons()
            if custom_log:
                self.log(custom_log)
            return
        with self._team_lock:
            self._team_status.pop(info.get("acc_name", ""), None)
            aid = info.get("acc_id", "")
            if aid:
                self._team_member_ready.pop(aid, None)
                if aid in self._team_member_ids:
                    self._team_member_ids = [x for x in self._team_member_ids if x != aid]
            summary = " | ".join(f"{k}:{v}" for k, v in self._team_status.items())
        self._refresh_run_buttons()
        if rem == 0:
            self.lbl_bot_progress.config(text="执行进度：已达目标自动停止" if custom_log else "执行进度：已暂停")
            self.log(custom_log or f"⏹ 已暂停账号【{info.get('acc_name') or '当前窗口'}】的后台自动闯关。")
        else:
            hdr = "🤝 联刷中" if self.team_running else "⚡ 运行中"
            self.lbl_bot_progress.config(text=f"{hdr} · {summary}" if summary else f"{hdr} ({rem}号)")
            self.log(custom_log or f"⏹ 已单独停止账号【{info.get('acc_name') or '当前窗口'}】，其余 {rem} 个账号继续运行中！")

    def _stop_all_bots(self, silent: bool = False):
        """统一彻底停止所有正在运行的单刷/联刷后台线程并恢复按钮状态"""
        with self._runs_lock:
            prev_cnt = len(self._active_runs)
            was_team = self.team_running
            self._run_token += 1
            self._active_tokens.clear()
            self._active_runs.clear()
            self.running = False
            self.team_running = False
            self.worker_threads = []
        with self._team_lock:
            self._team_member_ready.clear()
            self._team_member_ids = []
            self._team_status.clear()
        if not silent:
            self._refresh_run_buttons()
            self.lbl_bot_progress.config(text="执行进度：已暂停")
            if prev_cnt >= 2 or was_team:
                self.log(f"⏹ 已停止全部运行中的账号（共 {max(prev_cnt, 1)} 个），所有线程已安全退出。")
            else:
                self.log("⏹ 已暂停后台自动闯关。")

    def toggle_bot(self):
        """按当前选中账号独立启停：当前号在跑就只停当前号；没在跑就直接追加启动，不影响已开的其他号！"""
        cur_key, pinned_acc, acc_name = self._get_current_run_key()
        with self._runs_lock:
            is_cur_running = cur_key in self._active_runs
        if is_cur_running:
            self._stop_single_bot(cur_key)
            return

        # 优先取该账号绑定的独立浏览器窗口，避免切换账号后还没切窗口误拿旧 HWND
        pinned_hwnd = 0
        if pinned_acc is not None:
            found_h = self._find_hwnd_for_account(pinned_acc)
            if found_h and user32.IsWindow(found_h):
                pinned_hwnd = found_h
        if not pinned_hwnd:
            if not self.hwnd or not user32.IsWindow(self.hwnd):
                self._refresh_window_list()
            pinned_hwnd = int(self.hwnd or 0)
        if not pinned_hwnd or not user32.IsWindow(pinned_hwnd):
            messagebox.showwarning("提示", "尚未检测到该账号的游戏窗口，请先打开独立浏览器或按 F8 锁定窗口！")
            return

        # 严防两个账号线程抢占同一个游戏窗口 HWND
        with self._runs_lock:
            for _, rinfo in self._active_runs.items():
                if rinfo.get("hwnd") == pinned_hwnd:
                    messagebox.showwarning(
                        "窗口已被占用",
                        f"当前窗口 (HWND:{pinned_hwnd}) 正由账号【{rinfo.get('acc_name') or '另一个账号'}】自动刷关中！\n\n"
                        f"请先到【5.账号登录】选中【{acc_name or '本账号'}】并点击【🌐启动独立FFBrowser】打开它自己的独立窗口，再启动即可并行单刷。",
                    )
                    return

        pinned_deck = self.var_active_deck.get()
        if cur_key.startswith("hwnd:"):
            cur_key = f"hwnd:{pinned_hwnd}"
        disp_name = acc_name or f"窗口{pinned_hwnd}"
        # 若该账号上次已达预设刷关目标，重新启动时自动归零本账号计数方便开新一轮
        self._on_target_clears_change()
        tgt_clears = self._get_target_clears_for_key(cur_key, acc=pinned_acc)
        if tgt_clears > 0:
            with self._team_lock:
                prev_cnt = self._account_clear_counts.get(cur_key, 0)
                if prev_cnt >= tgt_clears:
                    self._account_clear_counts[cur_key] = 0
                    self._account_last_clear_ts.pop(cur_key, None)
                    self.clear_count = sum(self._account_clear_counts.values())
                    self.log(f"🔄 账号【{disp_name}】上次已达预设目标 {tgt_clears}/{tgt_clears}，本次启动已自动重新计次！")
            self._refresh_clear_count_ui()
        with self._runs_lock:
            self._run_token += 1
            my_token = self._run_token
            self._active_tokens.add(my_token)
            self.running = True
            solo_ctx = {
                "is_team": False,
                "run_key": cur_key,
                "acc": pinned_acc,
                "acc_id": pinned_acc.get("id", "") if pinned_acc else "",
                "acc_name": disp_name,
                "role": "solo",
                "hwnd": pinned_hwnd,
                "deck_name": pinned_deck,
                "capturer": FastWindowCapturer(),
            }
            th = threading.Thread(target=self._bot_main_loop, args=(my_token, solo_ctx), daemon=True)
            self._active_runs[cur_key] = {
                "token": my_token,
                "acc_id": solo_ctx["acc_id"],
                "acc_name": disp_name,
                "hwnd": pinned_hwnd,
                "role": "solo",
                "is_team": False,
                "thread": th,
            }
            self.worker_thread = th
            self.worker_threads.append(th)
            total_now = len(self._active_runs)
        with self._team_lock:
            self._team_status[disp_name] = "启动中"
        self._refresh_run_buttons()
        who = f"账号【{acc_name}】" if acc_name else f"窗口(HWND:{pinned_hwnd})"
        if total_now >= 2:
            self.log(f"🚀 已追加启动 {who}（方案：{pinned_deck} / HWND:{pinned_hwnd}），当前共 {total_now} 个账号并行独立运行中！")
        else:
            self.log(f"🚀 已启动单号后台自动闯关（已锁定 {who} / 方案：{pinned_deck} / HWND:{pinned_hwnd}），切去别的号按 F11 可随时追加并行单刷！")
        th.start()

    def toggle_team_bot(self):
        """启动多账号联刷 / 一键停止全部运行中的账号"""
        if self.running:
            self._stop_all_bots()
            return

        accounts = self.config.get("accounts", [])
        team_accs = [a for a in accounts if a.get("team_enabled", False)]
        if len(team_accs) < 2:
            messagebox.showwarning(
                "尚未勾选多开账号",
                "请先到右侧【5.账号登录】标签页中：\n"
                "1. 分别选中要同时刷关的账号，点【☑选联刷】打勾（至少 2 个账号）；\n"
                "2. 点【👑切角色】设置角色：\n"
                "   • 组队刷同一房：开房号设【👑房主】，小号设【🙋队员】；\n"
                "   • 各自独立单刷：把参与的号都设为【单刷】，或者直接切号逐个按 F11 随时追加启动！\n"
                "3. 确认每个号都已用【🌐启动独立FFBrowser】打开各自浏览器窗口。",
            )
            return

        # 校验每个参与账号是否都有自己独立的存活浏览器窗口
        team_specs = []
        missing_wins = []
        for acc in team_accs:
            hwnd = self._find_hwnd_for_account(acc)
            if not hwnd or not user32.IsWindow(hwnd):
                missing_wins.append(acc.get("name", acc.get("id", "未知")))
                continue
            decks = acc.get("decks") or {}
            dname = acc.get("active_deck") or ""
            if dname not in decks and decks:
                dname = next(iter(decks.keys()))
            role = acc.get("role", "solo")
            if role not in ("host", "member", "solo"):
                role = "solo"
            team_specs.append([acc, role, hwnd, dname])

        if missing_wins:
            messagebox.showwarning(
                "部分账号窗口未打开",
                f"以下已勾选的账号尚未检测到独立浏览器窗口：\n  • "
                + "\n  • ".join(missing_wins)
                + "\n\n请先在【5.账号登录】中选中对应账号并点击【🌐启动独立FFBrowser】打开各自窗口！",
            )
            return

        # 尊重用户设为【单刷(solo)】的账号，绝不强行改成房主/队员！
        # 仅当存在【队员(member)】但忘了设任何【房主(host)】时，才自动把第一个队员升为房主
        has_host = any(sp[1] == "host" for sp in team_specs)
        has_member = any(sp[1] == "member" for sp in team_specs)
        if has_member and not has_host:
            for sp in team_specs:
                if sp[1] == "member":
                    sp[1] = "host"
                    self.log(f"💡 检测到有队员但未指定房主，已自动将【{sp[0]['name']}】设为👑房主。")
                    break

        # 防止多个窗口误绑定成同一个 HWND
        seen_hwnds = {}
        for acc, role, hwnd, _ in team_specs:
            if hwnd in seen_hwnds:
                messagebox.showwarning(
                    "窗口冲突",
                    f"账号【{acc['name']}】与【{seen_hwnds[hwnd]}】匹配到了同一个浏览器窗口！\n"
                    "请确保每个账号都是通过【🌐启动独立FFBrowser】分别启动的独立窗口。",
                )
                return
            seen_hwnds[hwnd] = acc["name"]

        self._on_target_clears_change()
        member_ids = [sp[0]["id"] for sp in team_specs if sp[1] == "member"]
        with self._team_lock:
            self._team_member_ids = list(member_ids)
            self._team_member_ready = {mid: False for mid in member_ids}
            self._team_status = {sp[0]["name"]: "启动中" for sp in team_specs}
            for acc, _, _, _ in team_specs:
                aid = acc["id"]
                t_c = self._get_target_clears_for_key(aid, acc=acc)
                if t_c > 0 and self._account_clear_counts.get(aid, 0) >= t_c:
                    self._account_clear_counts[aid] = 0
                    self._account_last_clear_ts.pop(aid, None)
                    self.log(f"🔄 账号【{acc['name']}】上次已达预设目标 {t_c}/{t_c}，本次启动已自动重新计次！")
            self.clear_count = sum(self._account_clear_counts.values())
        self._refresh_clear_count_ui()

        threads_to_start = []
        with self._runs_lock:
            self.running = True
            self.team_running = True
            self.worker_threads = []
            for acc, role, hwnd, dname in team_specs:
                self._run_token += 1
                my_token = self._run_token
                self._active_tokens.add(my_token)
                rkey = acc["id"]
                ctx = {
                    "is_team": True,
                    "run_key": rkey,
                    "acc": acc,
                    "acc_id": acc["id"],
                    "acc_name": acc["name"],
                    "role": role,
                    "hwnd": hwnd,
                    "deck_name": dname,
                    "capturer": FastWindowCapturer(),
                }
                th = threading.Thread(target=self._bot_main_loop, args=(my_token, ctx), daemon=True)
                self._active_runs[rkey] = {
                    "token": my_token,
                    "acc_id": acc["id"],
                    "acc_name": acc["name"],
                    "hwnd": hwnd,
                    "role": role,
                    "is_team": True,
                    "thread": th,
                }
                self.worker_threads.append(th)
                threads_to_start.append(th)

        self._refresh_run_buttons()

        r_label_map = {"host": "👑房主", "member": "🙋队员", "solo": "⚡独立单刷"}
        desc_parts = []
        for acc, role, hwnd, dname in team_specs:
            desc_parts.append(f"{r_label_map.get(role, role)}:{acc['name']}(方案:{dname}, HWND:{hwnd})")
        all_solo = all(sp[1] == "solo" for sp in team_specs)
        if all_solo:
            self.log("⚡ 已启动【多账号并行独立单刷】！参与账号：" + " | ".join(desc_parts))
            self.log("💡 各账号完全隔离窗口、卡组与进图节奏，互不干扰、互不等待！")
        else:
            self.log("🤝 已启动【多账号联刷】！参与成员：" + " | ".join(desc_parts))
            if member_ids:
                self.log("💡 联刷机制：队员回房先点【准备】→ 通知房主点【开始】；单刷角色各自独立开战互不干扰！")

        for th in threads_to_start:
            th.start()

    def _bot_main_loop(self, my_token: int, ctx: dict = None):
        is_team = bool(ctx and ctx.get("is_team"))
        role = ctx.get("role", "solo") if ctx else "solo"
        acc_id = ctx.get("acc_id", "") if ctx else ""
        acc_name = ctx.get("acc_name", "") if ctx else ""
        pfx = self._ctx_prefix(ctx)

        place_idx = 0
        first_pass_done = False
        repair_state = {}
        bounce_count = 0
        last_retry_log_ts = 0.0
        last_wait_fire_log_ts = 0.0
        last_stage_scan_ts = 0.0
        last_auto_login_ts = 0.0
        local_latest_fire = None
        has_entered_battle = False
        battle_fire_locked = False
        last_auto_fire_try_ts = 0.0
        loop_start_mono = time.perf_counter()
        thresh = float(self.config.get("template_threshold", 0.84))

        def _reset_battle_fire_lock():
            nonlocal battle_fire_locked, last_auto_fire_try_ts
            battle_fire_locked = False
            last_auto_fire_try_ts = 0.0
            if ctx is not None:
                ctx["auto_fire_roi"] = None

        def _try_lock_battle_fire(screen_img=None):
            nonlocal battle_fire_locked, last_auto_fire_try_ts
            last_auto_fire_try_ts = time.perf_counter()
            roi, _ = self._auto_lock_fire_roi_for_battle(ctx=ctx, screen=screen_img, save_to_deck=True)
            if roi is not None:
                battle_fire_locked = True
                return True
            return False

        def _set_prog(short_txt: str, full_txt: str = None):
            if is_team or len(self._active_runs) > 1:
                self._update_team_progress_ui(acc_name or "当前号", short_txt)
            else:
                if acc_name:
                    with self._team_lock:
                        self._team_status[acc_name] = short_txt
                self.root.after(0, lambda t=(full_txt or short_txt): self.lbl_bot_progress.config(text=t))

        try:
            # 如果勾选了“启动立即先放角色”，开跑前先放人物并等待开局倒计时
            hero_cfg = self._ctx_deck(ctx).get("hero", {})
            if hero_cfg.get("enabled", False) and hero_cfg.get("on_start", False):
                self._exec_place_hero(wait=False, wait_after=True, token=my_token, ctx=ctx)
                if self._is_active(my_token):
                    _try_lock_battle_fire()

            while self._is_active(my_token):
                try:
                    hwnd = self._ctx_hwnd(ctx)
                    cap = self._ctx_cap(ctx)
                    if not hwnd or not user32.IsWindow(hwnd):
                        if ctx and ctx.get("acc"):
                            new_h = self._find_hwnd_for_account(ctx["acc"])
                            if new_h and user32.IsWindow(new_h):
                                ctx["hwnd"] = new_h
                                with self._runs_lock:
                                    rinfo = self._active_runs.get(ctx.get("run_key", ""))
                                    if rinfo and rinfo.get("token") == my_token:
                                        rinfo["hwnd"] = new_h
                                hwnd = new_h
                                self.log(f"{pfx}🔗 已自动重新绑定浏览器窗口 (HWND:{hwnd})")
                            else:
                                _set_prog("窗口离线")
                                self._sleep_interruptible(1.5, my_token)
                                continue
                        else:
                            self._sleep_interruptible(1.0, my_token)
                            continue

                    cur_deck = self._ctx_deck(ctx)
                    cur_deck_name = ctx.get("deck_name") if (ctx and ctx.get("deck_name")) else self.var_active_deck.get()
                    opts = cur_deck["options"]
                    tpl_select = self._resolve_template("stage_select.png", cur_deck_name)
                    tpl_ready = self._resolve_template("stage_ready.png", cur_deck_name)
                    tpl_hero = self._resolve_template("stage_place_hero.png", cur_deck_name)
                    tpl_continue = self._resolve_template("btn_continue.png", cur_deck_name)
                    tpl_finish = self._resolve_template("stage_finish.png", cur_deck_name)
                    tpl_fail = self._resolve_template("stage_fail.png", cur_deck_name)

                    active_steps = [p for p in cur_deck.get("placements", []) if p.get("enabled", True)]
                    loop_mode = bool(opts.get("loop_placements", False))
                    actively_placing = bool(active_steps and (not first_pass_done or loop_mode))

                    # 极速优化：第 1 轮连放期间每 1.8s 扫描一次全屏阶段模板；第 2 轮补阵期间缩短到 0.55s，防止补阵误点刚弹出的结算/继续窗口！
                    now_mono = time.perf_counter()
                    in_repair_mode = bool(active_steps and first_pass_done and loop_mode)
                    scan_gap = 0.55 if in_repair_mode else 1.8
                    need_stage_scan = (not actively_placing) or (now_mono - last_stage_scan_ts >= scan_gap)
                    if need_stage_scan:
                        last_stage_scan_ts = now_mono
                        screen = cap.capture_full(hwnd)
                        if not self._is_active(my_token):
                            break
                        if screen is not None:
                            # -1. 若勾选掉线自动重登且录入了登录页模板 (stage_login.png)，自动填账密重登（20s 冷却防刷屏）
                            if self.config.get("auto_login_on_bot", False) and (now_mono - last_auto_login_ts >= 20.0):
                                tpl_login = os.path.join(TEMPLATE_DIR, "stage_login.png")
                                if os.path.exists(tpl_login):
                                    found_login, _, _, l_score = match_template_numpy(screen, tpl_login, thresh)
                                    if found_login and self._is_active(my_token):
                                        last_auto_login_ts = now_mono
                                        self.log(f"{pfx}🔑 检测到【7k7k 登录界面】(匹配度={l_score:.2f})，自动填入账号密码重登！")
                                        _set_prog("自动重登")
                                        self._exec_auto_login(
                                            acc=(ctx.get("acc") if ctx else None),
                                            token=my_token,
                                            target_hwnd=hwnd,
                                        )
                                        last_stage_scan_ts = 0.0
                                        self._sleep_interruptible(4.0, my_token)
                                        continue

                            # 0. 精准识图检测【请放置您的角色】提示
                            if cur_deck.get("hero", {}).get("enabled", False):
                                found_hero, _, _, score = match_template_numpy(screen, tpl_hero, 0.58)
                                if found_hero and self._is_active(my_token):
                                    has_entered_battle = True
                                    if is_team and role == "member":
                                        with self._team_lock:
                                            self._team_member_ready[acc_id] = False
                                    self.log(f"{pfx}检测到【请放置您的角色】(匹配度={score:.2f})，立刻放置角色！")
                                    _set_prog("放角色")
                                    self._exec_place_hero(wait=False, wait_after=True, token=my_token, ctx=ctx)
                                    _reset_battle_fire_lock()
                                    if self._is_active(my_token):
                                        _try_lock_battle_fire()
                                    place_idx = 0
                                    first_pass_done = False
                                    repair_state.clear()
                                    last_stage_scan_ts = 0.0
                                    continue

                            # 1. 继续战斗（组队时仅随机一人出现此按钮，双号各自独立监测，谁看到谁点！）
                            found_cont, cx, cy, score = match_template_numpy(screen, tpl_continue, thresh)
                            if found_cont and self._is_active(my_token):
                                resets = bool(opts.get("continue_resets_battle", False))
                                if resets:
                                    self.log(f"{pfx}检测到【继续战斗】(匹配度={score:.2f})，后台点击 ({cx}, {cy})（已开启重摆：准备进入下一局）")
                                    bg_click(hwnd, cx, cy)
                                    if self._increment_clear_count(ctx=ctx):
                                        break
                                    place_idx = 0
                                    first_pass_done = False
                                    _reset_battle_fire_lock()
                                    _set_prog("继续→重摆")
                                    h_cfg = cur_deck.get("hero", {})
                                    if h_cfg.get("enabled", False) and h_cfg.get("on_continue", True):
                                        self._wait_battle_and_place_hero(tpl_hero, max_wait=45.0, token=my_token, ctx=ctx)
                                        if self._is_active(my_token):
                                            _try_lock_battle_fire()
                                    else:
                                        self._sleep_interruptible(2.0, my_token)
                                else:
                                    self.log(f"{pfx}检测到【继续战斗】(匹配度={score:.2f})，后台点击 ({cx}, {cy})（连战保留当前阵型，继续下一波）")
                                    bg_click(hwnd, cx, cy)
                                    _set_prog("已点继续", "▶ 已点继续战斗，继续连战中...")
                                    self._sleep_interruptible(2.5, my_token)
                                last_stage_scan_ts = 0.0
                                continue

                            # 2. 战斗结束收尾（组队结算点完后双方自动回到同一房间）
                            found_fin, _, _, score = match_template_numpy(screen, tpl_finish, thresh)
                            if found_fin and self._is_active(my_token):
                                if is_team and role == "member":
                                    with self._team_lock:
                                        self._team_member_ready[acc_id] = False
                                self.log(f"{pfx}检测到【战斗结束】(匹配度={score:.2f})，执行翻牌与收尾！")
                                _set_prog("结算收尾")
                                self._exec_finish_sequence(token=my_token, ctx=ctx)
                                if self._is_active(my_token):
                                    if self._increment_clear_count(ctx=ctx):
                                        break
                                place_idx = 0
                                first_pass_done = False
                                repair_state.clear()
                                _reset_battle_fire_lock()
                                last_stage_scan_ts = 0.0
                                self._sleep_interruptible(2.0, my_token)
                                if self._is_active(my_token):
                                    self._park_cursor_left(ctx=ctx)
                                continue

                            # 2.5 战斗失败兜底（翻车时自动点回房/重开，不计入刷关次数）
                            if os.path.exists(tpl_fail):
                                found_fail, fx, fy, f_score = match_template_numpy(screen, tpl_fail, thresh)
                                if found_fail and self._is_active(my_token):
                                    if is_team and role == "member":
                                        with self._team_lock:
                                            self._team_member_ready[acc_id] = False
                                    self.log(f"{pfx}💀 检测到【战斗失败】(匹配度={f_score:.2f})，自动点击 ({fx}, {fy}) 返回重开！")
                                    _set_prog("失败重开")
                                    bg_click(hwnd, fx, fy)
                                    time.sleep(0.05)
                                    self._park_cursor_left(ctx=ctx)
                                    place_idx = 0
                                    first_pass_done = False
                                    repair_state.clear()
                                    _reset_battle_fire_lock()
                                    last_stage_scan_ts = 0.0
                                    self._sleep_interruptible(2.5, my_token)
                                    if self._is_active(my_token):
                                        self._park_cursor_left(ctx=ctx)
                                    continue

                            # 3. 选卡 / 组队房间同步界面
                            if is_team and role == "member":
                                # 队员优先匹配专属【准备】按钮 (stage_ready.png)，未截时回退到 stage_select.png
                                clicked_ready = False
                                if os.path.exists(tpl_ready):
                                    found_r, rx, ry, r_score = match_template_numpy(screen, tpl_ready, thresh)
                                    if found_r and self._is_active(my_token):
                                        self.log(f"{pfx}🙋 检测到房间【准备】按钮(匹配度={r_score:.2f})，执行准备！")
                                        if cur_deck.get("enter_clicks"):
                                            self._exec_enter_sequence(token=my_token, ctx=ctx)
                                        else:
                                            bg_click(hwnd, rx, ry)
                                            self.log(f"  {pfx}[队员准备] 直接后台点击准备按钮 ({rx}, {ry})")
                                        clicked_ready = True
                                else:
                                    found_sel, _, _, score = match_template_numpy(screen, tpl_select, thresh)
                                    if found_sel and self._is_active(my_token):
                                        self.log(f"{pfx}🙋 检测到【选卡/房间界面】(匹配度={score:.2f})，执行队员进图/准备步骤！")
                                        self._exec_enter_sequence(token=my_token, ctx=ctx)
                                        clicked_ready = True

                                if clicked_ready and self._is_active(my_token):
                                    with self._team_lock:
                                        self._team_member_ready[acc_id] = True
                                    self.log(f"{pfx}✅ 队员已准备就绪，已通知房主点击【开始】！")
                                    _set_prog("已准备✓")
                                    place_idx = 0
                                    first_pass_done = False
                                    repair_state.clear()
                                    _reset_battle_fire_lock()
                                    last_stage_scan_ts = 0.0
                                    self._sleep_interruptible(2.5, my_token)
                                    continue

                                # 首局防死锁兜底：若开跑前玩家已手动点过“准备”（按钮已变成“取消准备”），4s 后自动通知房主放行！
                                if (not has_entered_battle) and (now_mono - loop_start_mono >= 4.0):
                                    with self._team_lock:
                                        already_r = self._team_member_ready.get(acc_id, False)
                                    if not already_r:
                                        fire_peek = self._read_fire_fast(ctx=ctx)
                                        if fire_peek is None:
                                            with self._team_lock:
                                                self._team_member_ready[acc_id] = True
                                            self.log(f"{pfx}💡 开局前可能已处于准备状态，自动放行通知房主开战！")
                                            _set_prog("已准备✓")
                            else:
                                found_sel, _, _, score = match_template_numpy(screen, tpl_select, thresh)
                                if found_sel and self._is_active(my_token):
                                    # 组队房主：在点击【开始】前，先等所有队员完成【准备】！
                                    if is_team and role == "host" and self._team_member_ids:
                                        _set_prog("等队员准备")
                                        wait_deadline = time.time() + 25.0
                                        last_wlog = 0.0
                                        while self._is_active(my_token):
                                            with self._team_lock:
                                                all_ready = all(
                                                    self._team_member_ready.get(mid, False)
                                                    for mid in self._team_member_ids
                                                )
                                            if all_ready:
                                                self.log(f"{pfx}🤝 所有队员均已准备就绪，房主立刻点击开战！")
                                                break
                                            if time.time() >= wait_deadline:
                                                self.log(f"{pfx}⚠ 等待队员准备超时(25s)，执行兜底开战！")
                                                break
                                            if time.time() - last_wlog >= 3.5:
                                                last_wlog = time.time()
                                                self.log(f"{pfx}⏳ 房主已在房间就位，正在等待队员点击【准备】...")
                                            self._sleep_interruptible(0.35, my_token)
                                        if not self._is_active(my_token):
                                            break
                                        with self._team_lock:
                                            for mid in self._team_member_ids:
                                                self._team_member_ready[mid] = False

                                    self.log(f"{pfx}检测到【选卡/房间界面】(匹配度={score:.2f})，自动选择当前卡组并开战！")
                                    _set_prog("开战进图")
                                    self._exec_enter_sequence(token=my_token, ctx=ctx)
                                    place_idx = 0
                                    first_pass_done = False
                                    repair_state.clear()
                                    _reset_battle_fire_lock()
                                    last_stage_scan_ts = 0.0
                                    h_cfg = cur_deck.get("hero", {})
                                    if h_cfg.get("enabled", False) and self._is_active(my_token):
                                        self._wait_battle_and_place_hero(tpl_hero, max_wait=45.0, token=my_token, ctx=ctx)
                                        if self._is_active(my_token):
                                            _try_lock_battle_fire()
                                    else:
                                        self._sleep_interruptible(1.5, my_token)
                                    continue

                    if not self._is_active(my_token):
                        break

                    # 4. 战斗内极速按序放卡（每局进战斗先自动锁定火苗位置；第 1 轮按序放卡，第 2 轮起三层智能补阵！）
                    if actively_placing:
                        if not battle_fire_locked and (time.perf_counter() - last_auto_fire_try_ts >= 0.65):
                            _try_lock_battle_fire()
                        if first_pass_done and loop_mode:
                            r_ret = self._exec_smart_repair_burst(
                                my_token, ctx, cur_deck, active_steps, repair_state, _set_prog, max_slice_s=0.45
                            )
                            if r_ret == "modal":
                                # 检测到顶栏变暗/弹窗切屏/离场回房，先将虚拟鼠标移到最左侧防悬停弹窗，立刻切回阶段检测！
                                self._park_cursor_left(ctx=ctx)
                                last_stage_scan_ts = 0.0
                                self._sleep_interruptible(0.12, my_token)
                                continue
                            if opts.get("auto_collect_fire", False) and self._is_active(my_token):
                                self._exec_collect_fire(ctx=ctx)
                            self._sleep_interruptible(0.12, my_token)
                            continue

                        step = active_steps[place_idx % len(active_steps)]
                        cname = step.get("card_name", "")
                        card = self._ctx_card(cname, ctx)
                        card_cost = 0 if ("铲" in cname) else (int(card.get("cost", 0)) if card else 0)
                        fire_roi = self._ctx_fire_roi(ctx)
                        step_no = (place_idx % len(active_steps)) + 1
                        _set_prog(
                            f"{step_no}/{len(active_steps)}[{cname}]",
                            f"▶ 正在执行：第 {step_no}/{len(active_steps)} 步【{cname}】",
                        )

                        # (a) 1ms 局部 ROI 读取火苗（不在战斗界面或火苗不足时原地等待）
                        need_wait_fire = False
                        if opts.get("wait_for_fire", True) and fire_roi and len(fire_roi) == 4:
                            cur_fire = self._read_fire_fast(ctx=ctx)
                            if cur_fire is None:
                                need_wait_fire = True
                                now_ts = time.time()
                                if now_ts - last_wait_fire_log_ts >= 3.0:
                                    last_wait_fire_log_ts = now_ts
                                    self.log(f"{pfx}⏳ 尚未检测到战斗火苗数值(可能正在加载/等待开战)，原地等待不跳步...")
                            else:
                                has_entered_battle = True
                                if is_team and role == "member":
                                    with self._team_lock:
                                        if self._team_member_ready.get(acc_id, False):
                                            self._team_member_ready[acc_id] = False
                                local_latest_fire = cur_fire
                                if (not acc_id) or (acc_id == self.config.get("active_account_id")):
                                    self.latest_fire_val = cur_fire
                                    self.root.after(0, lambda v=cur_fire: self.lbl_fire_live.config(text=f"🔥 实时火苗: {v}"))
                                if card_cost > 0 and cur_fire < card_cost:
                                    need_wait_fire = True
                                    now_ts = time.time()
                                    if now_ts - last_wait_fire_log_ts >= 3.0:
                                        last_wait_fire_log_ts = now_ts
                                        self.log(f"{pfx}🔥 第 {place_idx+1} 步【{cname}】需要 {card_cost} 火，当前 {cur_fire} 火，等待攒火...")

                        if need_wait_fire:
                            if opts.get("auto_collect_fire", False) and local_latest_fire is not None:
                                self._exec_collect_fire(ctx=ctx)
                            self._sleep_interruptible(0.22, my_token)
                            continue

                        if not self._is_active(my_token):
                            break

                        # (b) 第一轮布阵开启“抗火球干扰 + 回点卡槽验亮法”
                        should_verify = bool(opts.get("verify_placed", True)) and (not first_pass_done)
                        res_status = self._exec_single_placement(step, verify=should_verify, ctx=ctx)
                        if res_status == "modal":
                            self._park_cursor_left(ctx=ctx)
                            last_stage_scan_ts = 0.0
                            self._sleep_interruptible(0.12, my_token)
                            continue
                        if res_status != "ok":
                            if res_status == "bounced":
                                bounce_count += 1
                                # 若卡片明明就绪(非CD、火也够)却连续 5 次落不下去退回卡槽，说明该格已被占用/已种过，自动跳过防卡死！
                                if bounce_count >= 5:
                                    self.log(f"{pfx}⚠ 第 {place_idx+1} 步【{cname}】连续 5 次就绪退卡(该格可能已被占用)，自动进入下一步防卡死！")
                                    bounce_count = 0
                                    place_idx += 1
                                    if place_idx >= len(active_steps) and not first_pass_done:
                                        first_pass_done = True
                                    self._sleep_interruptible(0.25, my_token)
                                    continue
                            else:
                                bounce_count = 0
                            now_ts = time.time()
                            if now_ts - last_retry_log_ts >= 3.0:
                                last_retry_log_ts = now_ts
                                why = "卡槽仍在冷却CD中" if res_status == "cd" else f"卡片退回卡槽({bounce_count}/5)"
                                self.log(f"{pfx}⏳ 第 {place_idx+1} 步【{cname}】暂未放下({why})，等待重试...")
                            self._sleep_interruptible(0.22, my_token)
                            continue

                        bounce_count = 0
                        place_idx += 1
                        if place_idx >= len(active_steps) and not first_pass_done:
                            first_pass_done = True
                            if not loop_mode:
                                _set_prog("布阵完成✓", "🎉 本轮布阵已完成，监测继续/结算中...")
                                self.log(f"{pfx}🎉 本轮全部 {len(active_steps)} 步布阵已完成！正在后台监测【继续战斗】与【战斗结束】...")
                        wait_s = float(step.get("delay", 0.3))
                    else:
                        wait_s = 0.7

                    if opts.get("auto_collect_fire", False) and self._is_active(my_token):
                        self._exec_collect_fire(ctx=ctx)

                    self._sleep_interruptible(wait_s, my_token)

                except Exception as e:
                    self.log(f"{pfx}循环异常: {e}")
                    time.sleep(1.0)
        finally:
            if ctx and ctx.get("capturer") is not None:
                try:
                    ctx["capturer"].close()
                except Exception:
                    pass
            rkey = ctx.get("run_key", "") if ctx else ""
            if rkey:
                removed = False
                with self._runs_lock:
                    info = self._active_runs.get(rkey)
                    if info and info.get("token") == my_token:
                        self._active_runs.pop(rkey, None)
                        self._active_tokens.discard(my_token)
                        self.running = bool(self._active_tokens)
                        if not self.running:
                            self.team_running = False
                        removed = True
                if removed and self._alive:
                    with self._team_lock:
                        self._team_status.pop(acc_name, None)
                    try:
                        self.root.after(0, self._refresh_run_buttons)
                    except Exception:
                        pass


    # ==================== 在线自动更新（GitHub + 多国内加速源自动轮询） ====================
    def check_for_updates(self, manual: bool = False):
        """检查远程仓库是否有新版本（启动时静默检查，点顶部【🔄更新】时弹窗反馈）"""
        if self._update_checking:
            if manual:
                self.log("⏳ 正在检查更新中，请稍候...")
            return
        self._update_checking = True
        if manual:
            self.log(f"🔄 正在联网检查更新（当前版本 v{APP_VERSION}）...")

        def _worker():
            try:
                raw, src_name, errs = _fetch_from_mirrors(
                    "version.json", ref=UPDATE_BRANCH, cache_bust=True, timeout=6.5
                )
                if not raw:
                    if manual:
                        err_brief = "\n".join(f"• {e}" for e in errs[:4])
                        self.root.after(
                            0,
                            lambda eb=err_brief: (
                                self.log("⚠ 检查更新失败：所有加速源暂时均无法连接。"),
                                messagebox.showwarning(
                                    "检查更新失败",
                                    f"当前未能连接到更新服务器（请检查网络后重试）：\n\n{eb}",
                                ),
                            ),
                        )
                    return

                manifest = json.loads(raw.decode("utf-8"))
                remote_ver = str(manifest.get("version", "")).strip()
                if not remote_ver:
                    if manual:
                        self.root.after(0, lambda: messagebox.showwarning("提示", "远端版本清单格式异常，请稍后再试。"))
                    return

                if _parse_version_tuple(remote_ver) > _parse_version_tuple(APP_VERSION):
                    self.root.after(0, lambda m=manifest, sn=src_name: self._on_new_version_found(m, sn))
                else:
                    if manual:
                        self.root.after(
                            0,
                            lambda rv=remote_ver, sn=src_name: (
                                self.log(f"✅ 当前已是最新版本 v{APP_VERSION}（来源：{sn}）"),
                                messagebox.showinfo(
                                    "已是最新版本",
                                    f"当前版本：v{APP_VERSION}\n远端最新：v{rv}\n检测线路：{sn}\n\n无需更新！",
                                ),
                            ),
                        )
            except Exception as e:
                if manual:
                    self.root.after(0, lambda err=str(e): messagebox.showwarning("检查更新异常", f"解析更新信息失败：\n{err}"))
            finally:
                self._update_checking = False

        threading.Thread(target=_worker, daemon=True).start()

    def _on_new_version_found(self, manifest: dict, src_name: str):
        remote_ver = str(manifest.get("version", "")).strip()
        if hasattr(self, "btn_update"):
            self.btn_update.config(text=f"🆕v{remote_ver}", width=max(7, len(remote_ver) + 3))
        self.log(f"🆕 发现新版本 v{remote_ver}（当前 v{APP_VERSION}，检测线路：{src_name}）！")
        self._show_update_dialog(manifest, src_name)

    def _show_update_dialog(self, manifest: dict, src_name: str):
        remote_ver = str(manifest.get("version", "")).strip()
        released_at = str(manifest.get("released_at", "")).strip()
        notes = str(manifest.get("notes", "本次更新包含稳定性与功能优化。")).strip()

        win = tk.Toplevel(self.root)
        win.title(f"发现新版本 v{remote_ver}")
        win.geometry("540x390")
        win.resizable(True, True)
        th = self._cur_theme()
        win.configure(bg=th["card"])
        apply_win11_titlebar(win, th)
        win.transient(self.root)
        win.grab_set()

        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)

        hdr = f"🎉 发现新版本：v{APP_VERSION}  →  v{remote_ver}"
        if released_at:
            hdr += f"   ({released_at})"
        ttk.Label(body, text=hdr, font=("Microsoft YaHei", 11, "bold"), foreground=th["accent"]).pack(anchor="w", pady=(0, 6))
        ttk.Label(
            body,
            text=f"检测线路：{src_name}（个人账号、卡组、模板保存在独立数据目录，更新完全不丢配置！）",
            foreground=th["muted"],
            font=("Microsoft YaHei", 8),
        ).pack(anchor="w", pady=(0, 6))

        txt = tk.Text(
            body, height=11, wrap="word", font=("Microsoft YaHei", 9),
            bg=th["input_bg"], fg=th["input_fg"], relief="solid", bd=1,
        )
        txt.insert("1.0", notes)
        txt.config(state="disabled")
        txt.pack(fill="both", expand=True, pady=4)

        lbl_prog = ttk.Label(body, text="点击下方按钮后将自动下载、SHA256 校验并重启软件。", foreground=th["tip_fg"])
        lbl_prog.pack(anchor="w", pady=(4, 6))

        bf = ttk.Frame(body)
        bf.pack(fill="x", pady=(2, 0))
        btn_go = tk.Button(
            bf,
            text=f"⬇ 立即一键更新到 v{remote_ver} 并重启",
            bg=th["start_bg"],
            fg="#ffffff",
            activebackground=th["start_bg"],
            activeforeground="#ffffff",
            font=("Microsoft YaHei", 10, "bold"),
            relief="flat",
            bd=0,
            padx=14,
            pady=5,
            cursor="hand2",
        )
        btn_go.pack(side="left", padx=(0, 8))
        btn_later = ttk.Button(bf, text="稍后再说", command=win.destroy)
        btn_later.pack(side="left")

        def _start_dl():
            btn_go.config(state="disabled", text="⏳ 正在下载并校验更新...")
            btn_later.config(state="disabled")
            lbl_prog.config(text="正在通过高速加速源下载 meishi_bot.py，请稍候...")

            def _dl_worker():
                ok, msg = self._apply_remote_update(manifest)
                if ok:
                    self.root.after(
                        0,
                        lambda m=msg: (
                            lbl_prog.config(text=f"✅ {m}，正在自动重启..."),
                            win.destroy(),
                            self._restart_app_after_update(),
                        ),
                    )
                else:
                    self.root.after(
                        0,
                        lambda m=msg: (
                            btn_go.config(state="normal", text=f"⬇ 重新尝试更新到 v{remote_ver}"),
                            btn_later.config(state="normal"),
                            lbl_prog.config(text="更新失败，原程序未受任何影响。"),
                            messagebox.showerror("更新失败", m, parent=win),
                        ),
                    )

            threading.Thread(target=_dl_worker, daemon=True).start()

        btn_go.config(command=_start_dl)

    def _apply_remote_update(self, manifest: dict):
        """安全下载、SHA256 校验、语法检查、自动备份旧版并原子覆盖 meishi_bot.py"""
        remote_ver = str(manifest.get("version", "")).strip()
        tag_ref = str(manifest.get("tag", "")).strip() or UPDATE_BRANCH
        files_meta = manifest.get("files") or {}
        py_meta = files_meta.get("meishi_bot.py") or {}
        py_sha = str(py_meta.get("sha256", "")).strip()

        # 优先按精确版本 tag 下载（CDN 零缓存延迟），失败再回退到 main 分支
        raw_py, src_used, errs = _fetch_from_mirrors(
            "meishi_bot.py", ref=tag_ref, expected_sha256=py_sha, cache_bust=(tag_ref == UPDATE_BRANCH), timeout=12.0
        )
        if not raw_py and tag_ref != UPDATE_BRANCH:
            raw_py, src_used, errs2 = _fetch_from_mirrors(
                "meishi_bot.py", ref=UPDATE_BRANCH, expected_sha256=py_sha, cache_bust=True, timeout=12.0
            )
            errs.extend(errs2)
        if not raw_py:
            return False, "下载新版主程序失败（所有线路均不可用或校验未通过）：\n" + "\n".join(errs[:5])

        # 替换前先验证 UTF-8 解码与静态 AST 语法解析，防止写坏主程序且不触发杀软动态编译误报
        try:
            code_str = raw_py.decode("utf-8")
            ast.parse(code_str)
        except Exception as e:
            return False, f"下载的新版脚本完整性或语法校验未通过，已中止更新：\n{e}"

        script_path = os.path.abspath(__file__)
        app_dir = os.path.dirname(script_path)
        ts = time.strftime("%Y%m%d_%H%M%S")
        try:
            os.makedirs(BACKUP_DIR, exist_ok=True)
            if os.path.isfile(script_path):
                shutil.copy2(script_path, os.path.join(BACKUP_DIR, f"meishi_bot_before_v{remote_ver}_{ts}.py"))
        except Exception:
            pass

        tmp_py = script_path + ".new"
        try:
            with open(tmp_py, "wb") as f:
                f.write(raw_py)
            os.replace(tmp_py, script_path)
        except Exception as e:
            try:
                if os.path.exists(tmp_py):
                    os.remove(tmp_py)
            except Exception:
                pass
            return False, f"写入新版主程序失败（请确认程序目录有写权限）：\n{e}"

        # 若本目录为标准分享版（存在使用说明.txt），顺带同步更新说明文档（不覆盖作者本地手写文档）
        has_guide = os.path.isfile(os.path.join(app_dir, "使用说明.txt"))
        if has_guide:
            for doc_name in ("使用说明.txt", "更新说明.txt"):
                dmeta = files_meta.get(doc_name)
                if not isinstance(dmeta, dict):
                    continue
                d_sha = str(dmeta.get("sha256", "")).strip()
                d_raw, _, _ = _fetch_from_mirrors(doc_name, ref=tag_ref, expected_sha256=d_sha, timeout=8.0)
                if d_raw:
                    try:
                        d_dst = os.path.join(app_dir, doc_name)
                        d_tmp = d_dst + ".new"
                        with open(d_tmp, "wb") as f:
                            f.write(d_raw)
                        os.replace(d_tmp, d_dst)
                    except Exception:
                        pass

        self.log(f"✅ 已通过【{src_used}】完成 v{remote_ver} 下载、校验与自动备份！")
        return True, f"已成功更新至 v{remote_ver}（来源：{src_used}）"

    def _restart_app_after_update(self):
        """释放单实例互斥锁、清理窗口并拉起刚更新的新版脚本"""
        script_path = os.path.abspath(__file__)
        app_dir = os.path.dirname(script_path)
        self._alive = False
        self._stop_all_bots(silent=True)
        self._restore_stealth_on_exit()
        self.save_config(silent=True)
        CAPTURER.close()
        _release_single_instance_mutex()
        try:
            subprocess.Popen([sys.executable, script_path], cwd=app_dir)
        except Exception as e:
            try:
                messagebox.showinfo("更新完成", f"已更新完成，但自动重启失败：{e}\n请手动重新双击启动脚本即可！")
            except Exception:
                pass
        try:
            self.root.destroy()
        except Exception:
            pass


_SINGLE_INSTANCE_MUTEX = None
_SINGLE_INSTANCE_K32 = None


def _release_single_instance_mutex():
    """显式释放单实例互斥锁（供在线更新自动重启前调用，避免新进程被旧锁拦截）"""
    global _SINGLE_INSTANCE_MUTEX, _SINGLE_INSTANCE_K32
    if _SINGLE_INSTANCE_MUTEX:
        try:
            k32 = _SINGLE_INSTANCE_K32 or ctypes.WinDLL("kernel32", use_last_error=True)
            k32.CloseHandle(_SINGLE_INSTANCE_MUTEX)
        except Exception:
            pass
        _SINGLE_INSTANCE_MUTEX = None


def _activate_existing_meishi_window() -> bool:
    """找到已在运行的刷关模拟器主窗口并恢复置前"""
    my_pid = os.getpid()
    found_hwnd = [0]
    enum_proc_t = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @enum_proc_t
    def _cb(hwnd, _lp):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == my_pid:
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        if "刷关模拟器" in title and "美食大战老鼠" in title:
            found_hwnd[0] = hwnd
            return False
        return True

    try:
        user32.EnumWindows(_cb, 0)
    except Exception:
        pass

    target = found_hwnd[0]
    if target and user32.IsWindow(target):
        try:
            SW_RESTORE = 9
            SW_SHOW = 5
            if user32.IsIconic(target):
                user32.ShowWindow(target, SW_RESTORE)
            else:
                user32.ShowWindow(target, SW_SHOW)
            user32.BringWindowToTop(target)
            user32.SetForegroundWindow(target)
        except Exception:
            pass
        return True
    return False


def _acquire_single_instance_or_activate(show_popup: bool = True) -> bool:
    """
    使用 Windows 内核命名互斥锁（Mutex）防止重复多开：
    - 进程异常崩溃/被强杀时系统会自动释放锁，不会残留死锁文件；
    - 检测到已有实例在运行时，自动激活并切回原窗口，防止双脚本抢控冲突。
    """
    global _SINGLE_INSTANCE_MUTEX, _SINGLE_INSTANCE_K32
    ERROR_ALREADY_EXISTS = 183
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    k32.CreateMutexW.restype = wintypes.HANDLE
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.CloseHandle.restype = wintypes.BOOL

    handle = k32.CreateMutexW(None, False, "Local\\MeishiBot_SingleInstance_Mutex_v2")
    last_err = ctypes.get_last_error()
    if not handle:
        return True

    if last_err == ERROR_ALREADY_EXISTS:
        k32.CloseHandle(handle)
        activated = _activate_existing_meishi_window()
        if show_popup:
            msg = (
                "刷关模拟器已经在运行中，已自动为您切回原窗口！\n\n"
                "（本程序内置多账号独立多开与组队联刷功能，无需重复启动多个脚本）"
                if activated
                else "刷关模拟器已经在后台运行中，请勿重复启动！"
            )
            try:
                user32.MessageBoxW(0, msg, "刷关模拟器 - 防止重复启动", 0x40 | 0x40000)
            except Exception:
                pass
        return False

    _SINGLE_INSTANCE_MUTEX = handle
    _SINGLE_INSTANCE_K32 = k32
    atexit.register(_release_single_instance_mutex)
    return True


if __name__ == "__main__":
    if not _acquire_single_instance_or_activate(show_popup=True):
        sys.exit(0)
    root = tk.Tk()
    app = MeishiBotGUI(root)
    root.mainloop()
