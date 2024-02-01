# Packaging BOOT Flasher

The app is built with PyInstaller in **one-folder** mode on each operating
system; `packaging/boot-flasher.spec` is the only build description. On macOS
the same spec also wraps the folder in an `.app` (bundle identifier
`com.soccentric.bootflasher`).

The bundle contains the GUI only. The bootloader checkout it drives
(`tools/bootctl.py`, `tools/mkimage.py`, `keys/`, the firmware projects) is
found at run time through `BOOTLOADER_DIR` or the workspace layout, so a
packaged BOOT Flasher still needs that checkout next to it - see the
Environment table in the repository README.

```bash
python -m pip install pyinstaller        # packaging-only dependency
python packaging/make_icons.py           # packaging/boot-flasher.svg/.ico/.icns
python -m PyInstaller packaging/boot-flasher.spec --noconfirm --clean
```

`make package` runs the right script for the current OS
(Windows: `packaging\build-windows.ps1`, macOS: `packaging/build-macos.sh`,
Linux: `packaging/build-linux.sh`); `PYTHON=/path/to/python` picks the
interpreter, otherwise `VENV` (`.venv`) and then `python`/`python3` on PATH.

Artifacts land in `dist/`.

## Prerequisites per OS

| | Needs |
|---|---|
| All | Python 3.10+ with the app dependencies (`make deps`) and PyInstaller |
| Linux | A C toolchain only if PyInstaller has no wheel for your Python. At run time the bundled Qt needs the usual xcb/GL libraries of a desktop install (libxcb, libGL), which a normal desktop already has. For real flashing: OpenOCD or the `stm32-dev` container, and membership of the `dialout` (Debian/Ubuntu) or `uucp` group for `/dev/ttyACM*` |
| macOS | Xcode command line tools (for the bootloader's own builds), `hdiutil` (ships with macOS). Unsigned `.app`/`.dmg` are fine locally; signing + notarisation is a release-owner step |
| Windows | Nothing beyond Python and PyInstaller; `Compress-Archive` ships with PowerShell 5. Also install the ST-LINK USB driver, which OpenOCD needs |

## Icons

`gui/icons.py` owns the glyphs, so the app icon is the `chip` glyph on the
theme's accent plate. `packaging/make_icons.py` imports it, writes the SVG
master `packaging/boot-flasher.svg` (used by the Linux desktop entry) and
renders the rasters into `packaging/boot-flasher.ico` (7 sizes) and
`packaging/boot-flasher.icns` (6 sizes). Both containers embed PNG frames
written by QImage, so no Pillow, ImageMagick or macOS `iconutil` is needed
and the files are identical on every OS. The `.ico`/`.icns` are generated,
not committed.

## Per OS

### Linux

```bash
packaging/build-linux.sh    # dist/BOOT Flasher/ + dist/BOOT-Flasher-linux.tar.gz
```

The tarball holds the payload, `boot-flasher.desktop` and
`boot-flasher.svg`; unpack it (for example in `/opt`), then point the
desktop entry's `Exec` at the unpacked `BOOT Flasher` binary and install the
SVG under `~/.local/share/icons/hicolor/scalable/apps/`.

### macOS

```bash
packaging/build-macos.sh    # dist/BOOT Flasher.app + dist/BOOT-Flasher-macos.dmg
```

### Windows

```powershell
packaging\build-windows.ps1  # dist\BOOT Flasher\ + dist\BOOT-Flasher-windows.zip
```

No installer is produced; the zip is a portable folder with
`BOOT Flasher.exe` (windowed) next to `_internal\`.

## Direct source run

```bash
make deps
make gui
```
