#!/usr/bin/env bash
#
# build-macos.sh - PyInstaller .app and .dmg for macOS
#
#   PYTHON=/path/to/python packaging/build-macos.sh
#
# Writes dist/BOOT Flasher.app (one-folder build wrapped by the spec's
# BUNDLE, identifier com.soccentric.bootflasher) and dist/BOOT-Flasher-macos.dmg
# with a drag-to-Applications layout.  Signing and notarisation are left to
# the release owner: set CODESIGN_IDENTITY and codesign the .app before
# uploading the .dmg.
#
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT"

# Prefer the project virtualenv; callers can override PYTHON.
PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
  if [ -x "$ROOT/.venv/bin/python" ]; then
    PYTHON="$ROOT/.venv/bin/python"
  else
    PYTHON=python3
  fi
fi

"$PYTHON" packaging/make_icons.py
"$PYTHON" -m PyInstaller packaging/boot-flasher.spec --noconfirm --clean

APP="$ROOT/dist/BOOT Flasher.app"
if [ ! -d "$APP" ]; then
  echo "PyInstaller did not produce $APP; the spec builds a .app on darwin" >&2
  exit 1
fi

DMG="$ROOT/dist/BOOT-Flasher-macos.dmg"
STAGE="$ROOT/build/dmg"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -a "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "BOOT Flasher" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
echo "macOS packages: $APP and $DMG"
