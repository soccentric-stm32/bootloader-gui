#!/usr/bin/env bash
#
# build-linux.sh - PyInstaller one-folder package for Linux
#
#   PYTHON=/path/to/python packaging/build-linux.sh
#
# Writes dist/BOOT Flasher/ and dist/BOOT-Flasher-linux.tar.gz.  The tarball
# holds the payload plus the desktop entry and the SVG icon; unpack it
# anywhere (for example /opt) and point the desktop entry's Exec and Icon at
# what you unpacked.  AppImage/.deb wrapping is left to the release owner.
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

APP="$ROOT/dist/BOOT Flasher"
if [ ! -x "$APP/BOOT Flasher" ]; then
  echo "PyInstaller did not produce $APP/BOOT Flasher" >&2
  exit 1
fi

STAGE="$ROOT/build/linux-stage"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -a "$APP" "$STAGE/"
cp packaging/boot-flasher.desktop packaging/boot-flasher.svg "$STAGE/"

tar -czf "$ROOT/dist/BOOT-Flasher-linux.tar.gz" -C "$STAGE" .
echo "Linux package: $ROOT/dist/BOOT-Flasher-linux.tar.gz"
