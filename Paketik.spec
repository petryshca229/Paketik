# -*- mode: python ; coding: utf-8 -*-

import os, sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Путь к папке проекта — нужен чтобы PyInstaller нашёл все .py рядом с main.py
PROJECT_DIR = os.path.dirname(os.path.abspath(SPEC))

datas = [
    ("assets", "assets"),
]

# PyQt6/WebEngine data
datas += collect_data_files("PyQt6")
datas += collect_data_files("PyQt6.QtWebEngineCore")
datas += collect_data_files("PyQt6.QtWebEngineWidgets")

# GUI package — все .py файлы
hiddenimports += collect_submodules("gui")

hiddenimports = [
    # Локальные модули проекта
    "license_mgr",
    "accounts",
    "config",
    "agent",
    "utils",
    # PyQt6
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "PyQt6.QtWebEngineCore",
    "PyQt6.QtWebEngineWidgets",
    "PyQt6.QtNetwork",
]
hiddenimports += collect_submodules("nodriver")
hiddenimports += collect_submodules("httpx")
hiddenimports += collect_submodules("PIL")
hiddenimports += collect_submodules("gui")

a = Analysis(
    ["main.py"],
    pathex=[PROJECT_DIR],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Paketik",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/logo.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Paketik",
)