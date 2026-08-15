# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — build on Windows:
#   pyinstaller --noconfirm packaging/windows/system-info.spec

import sys
from pathlib import Path

block_cipher = None
root = Path(SPECPATH).resolve().parents[1]
src = root / "src"

hiddenimports = ["system_info", "pystray", "pystray._win32", "PIL", "PIL.Image", "PIL.ImageDraw"]
try:
    from PyInstaller.utils.hooks import collect_submodules

    hiddenimports = ["system_info"] + collect_submodules("pystray") + [
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
    ]
except Exception:
    pass

a = Analysis(
    [str(src / "system_info" / "__main__.py")],
    pathex=[str(src)],
    binaries=[],
    datas=[],
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
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="system-info",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
