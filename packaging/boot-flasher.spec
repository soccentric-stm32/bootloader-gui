# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller one-folder spec for BOOT Flasher (see packaging/README.md).
#
#   python -m PyInstaller packaging/boot-flasher.spec --noconfirm --clean
#
# Relative paths in a spec are resolved against the spec file, not against
# the directory the build was started from, so the repository root comes from
# SPECPATH and the build works from any working directory.
#
# The GUI ships one data folder, the bundled fonts (gui/soc_fonts).  The bootloader checkout it drives
# (tools/bootctl.py, tools/mkimage.py, keys/) is found at run time from
# BOOTLOADER_DIR or the workspace layout, and is not part of this bundle.

import os
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))
sys.path.insert(0, ROOT)

from gui import __version__  # noqa: E402  - gui/__init__.py imports no Qt

PACKAGING = os.path.join(ROOT, "packaging")
ICON = os.path.join(PACKAGING,
                    "boot-flasher.icns" if sys.platform == "darwin"
                    else "boot-flasher.ico")

# serial and its port enumerator are imported inside functions, so
# PyInstaller's static analysis cannot see them.
hiddenimports = ["serial", "serial.tools.list_ports", "PySide6.QtSvg"]

a = Analysis(
    [os.path.join(ROOT, "flash_gui.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[(os.path.join(ROOT, "gui", "soc_fonts"), os.path.join("gui", "soc_fonts"))],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BOOT Flasher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON if os.path.exists(ICON) else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="BOOT Flasher",
)

if sys.platform == "darwin":
    # One-folder build wrapped in an .app: dist/BOOT Flasher.app.
    app = BUNDLE(
        coll,
        name="BOOT Flasher.app",
        icon=ICON if os.path.exists(ICON) else None,
        bundle_identifier="com.soccentric.bootflasher",
        info_plist={
            "CFBundleName": "BOOT Flasher",
            "CFBundleDisplayName": "BOOT Flasher",
            "CFBundleShortVersionString": __version__,
            "CFBundleVersion": __version__,
            "NSHighResolutionCapable": True,
        },
    )
