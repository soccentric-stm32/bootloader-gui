"""The debug UART monitor shows BOOT's log lines, not its ANSI escapes."""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
pytest.importorskip("PySide6")

from gui.soc_terminal import ANSI_RE  # noqa: E402


def test_ansi_colours_are_removed_from_uart_lines():
    line = "\x1b[32mBOOT\x1b[0m 1.4.0 ready\r\n"
    assert ANSI_RE.sub("", line).rstrip("\r\n") == "BOOT 1.4.0 ready"


def test_plain_uart_lines_are_unchanged():
    assert ANSI_RE.sub("", "[app ] hello") == "[app ] hello"


def test_panel_shows_fed_lines_and_reports_no_port():
    from PySide6.QtWidgets import QApplication

    from gui.soc_terminal import TerminalPanel

    app = QApplication.instance() or QApplication([])
    if not isinstance(app, QApplication):
        pytest.skip("a QCoreApplication from another test owns the process")
    panel = TerminalPanel(title="Debug UART")
    panel.feed("task 1 LED: blinks")
    panel.feed("task 2 Button: debounce")
    assert panel.text().splitlines() == ["task 1 LED: blinks",
                                         "task 2 Button: debounce"]
    assert panel.pill.text() == "No port"
    panel.clear()
    assert panel.text() == ""


@pytest.mark.skipif(sys.platform == "win32", reason="termios is POSIX only")
def test_raw_link_reads_lines_from_a_pty():
    import os
    import pty

    from gui.soc_terminal import _RawLink

    master, slave = pty.openpty()
    link = _RawLink(os.ttyname(slave), 115200)
    try:
        os.write(master, b"BOOT 1.4.0 ready\r\npartial")
        assert link.readline() == b"BOOT 1.4.0 ready\r\n"
        assert link.readline() == b"partial"   # timeout returns the rest
        assert link.readline() == b""
    finally:
        link.close()
        os.close(master)
        os.close(slave)
