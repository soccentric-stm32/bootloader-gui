#!/usr/bin/env python3
"""Render the BOOT Flasher app icon.

Every SoCcentric app icon is its sidebar badge: the app's glyph from
soc_icons.py, white on a rounded accent plate, with the badge's corner
radius and inset.  This script writes

  packaging/boot-flasher.svg    SVG master, used by the Linux desktop entry
  packaging/boot-flasher.ico    Windows icon for the PyInstaller build
  packaging/boot-flasher.icns   macOS icon for the .app bundle

The containers embed ordinary PNG frames rendered by QImage/QSvgRenderer, so
the output is byte-identical on every OS and needs nothing beyond PySide6 -
no Pillow, ImageMagick or macOS-only iconutil.

Usage:
  python packaging/make_icons.py
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from gui import soc_icons as icons  # noqa: E402  - needs ROOT on sys.path
from gui.window import APP_GLYPH  # noqa: E402

NAME = "boot-flasher"
GLYPH = APP_GLYPH     # the sidebar badge's glyph
PLATE = "#007aff"     # soc_theme.py accent (light)
INK = "#ffffff"       # soc_theme.py on_accent
PLATE_RADIUS = round(256 * icons.BADGE_RADIUS)   # of 256
MARGIN = round(256 * icons.BADGE_INSET)          # of 256
STROKE = icons.BADGE_STROKE                      # of the 24-unit glyph grid

# Windows: 16 px is the taskbar, 256 px the Explorer/Large view.
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
# macOS names the same rasters by ICNS chunk type.
ICNS_CHUNKS = (
    ("icp4", 16),
    ("icp5", 32),
    ("ic07", 128),
    ("ic08", 256),
    ("ic09", 512),
    ("ic10", 1024),
)


def glyph_body() -> str:
    """The glyph's shapes, stripped of its own 24x24 <svg> wrapper."""
    document = icons.svg(GLYPH, INK, STROKE)
    return document[document.index(">") + 1:document.rindex("</svg>")]


def icon_svg() -> str:
    scale = (256 - 2 * MARGIN) / 24
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" '
        'width="256" height="256">\n'
        f'  <rect x="0" y="0" width="256" height="256" rx="{PLATE_RADIUS}" '
        f'fill="{PLATE}"/>\n'
        f'  <g transform="translate({MARGIN} {MARGIN}) scale({scale:.4f})" '
        f'stroke="{INK}" stroke-width="{STROKE}" fill="none" '
        'stroke-linecap="round" stroke-linejoin="round">\n'
        f'    {glyph_body()}\n'
        '  </g>\n'
        '</svg>\n'
    )


def render_png(svg_text: str, size: int) -> bytes:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(svg_text.encode())).render(
        painter, QRectF(0, 0, size, size))
    painter.end()
    buffer = QBuffer()
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def write_ico(path: Path, frames: list[tuple[int, bytes]]) -> None:
    """ICONDIR plus one PNG-framed entry per size (PNG entries are Vista+)."""
    header = struct.pack("<HHH", 0, 1, len(frames))
    entries = b""
    body = b""
    for size, png in frames:
        # 256 px is encoded as 0 in the one-byte width/height fields.
        entries += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1,
                               32, len(png),
                               len(header) + 16 * len(frames) + len(body))
        body += png
    path.write_bytes(header + entries + body)


def write_icns(path: Path, frames: list[tuple[str, bytes]]) -> None:
    """ICNS header plus PNG chunks (icp4/ic05/ic07..: all accept PNG data)."""
    chunks = b"".join(kind.encode("ascii") + struct.pack(">I", 8 + len(png))
                      + png for kind, png in frames)
    path.write_bytes(b"icns" + struct.pack(">I", 8 + len(chunks)) + chunks)


def main() -> int:
    # QImage/QPainter need the Qt GUI library loaded; a headless build host
    # has no display, so default to the offscreen platform plugin.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QGuiApplication([])  # noqa: F841  - must outlive the rendering

    svg_text = icon_svg()
    svg_path = HERE / f"{NAME}.svg"
    svg_path.write_text(svg_text, encoding="utf-8", newline="\n")
    write_ico(HERE / f"{NAME}.ico",
              [(size, render_png(svg_text, size)) for size in ICO_SIZES])
    write_icns(HERE / f"{NAME}.icns",
               [(kind, render_png(svg_text, size)) for kind, size in ICNS_CHUNKS])
    print(f"wrote {svg_path.name}, {NAME}.ico ({len(ICO_SIZES)} sizes) "
          f"and {NAME}.icns ({len(ICNS_CHUNKS)} sizes) in {HERE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
