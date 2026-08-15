# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — build on Windows:
#   pyinstaller --noconfirm packaging/windows/system-info.spec

from pathlib import Path

block_cipher = None
root = Path(SPECPATH).resolve().parents[1]
src = root / "src"

datas = []
binaries = []
hiddenimports = ["system_info"]
try:
    from PyInstaller.utils.hooks import collect_all

    for pkg in ("pystray", "PIL", "websocket"):
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
except Exception:
    pass

hiddenimports += [
    "pystray",
    "pystray._win32",
    "pystray._util",
    "pystray._util.win32",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL._imaging",
    "websocket",
]
hiddenimports = list(dict.fromkeys(hiddenimports))

a = Analysis(
    [str(src / "system_info" / "__main__.py")],
    pathex=[str(src)],
    binaries=binaries,
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
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
