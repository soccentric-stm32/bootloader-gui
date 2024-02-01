"""bootctl --json reports failures on stdout; the board panel must read them."""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
pytest.importorskip("PySide6")

from gui.window import MainWindow  # noqa: E402


def test_running_application_error_is_found_in_stdout():
    out = (
        '{"event":"error","command":"info","status":"error",'
        '"error":"device is running the application; use \'bootctl enter\'"}\n'
    )
    assert "running the application" in MainWindow._json_error(out)


def test_other_output_gives_no_message():
    assert MainWindow._json_error("") == ""
    assert MainWindow._json_error("not json\n") == ""
    assert MainWindow._json_error('{"event":"info"}\n') == ""


def test_host_build_sdk_is_found_via_the_environment(tmp_path, monkeypatch):
    from gui.pages import BootloaderPage

    header = (tmp_path / "Drivers" / "STM32F7xx_HAL_Driver" / "Inc" /
              "stm32f7xx_hal.h")
    header.parent.mkdir(parents=True)
    header.write_text("", encoding="utf-8")
    monkeypatch.setenv("STM32CUBE_F7", str(tmp_path))
    assert BootloaderPage.host_sdk_root() == tmp_path


def test_missing_host_build_sdk_is_reported(tmp_path, monkeypatch):
    from gui.pages import BootloaderPage

    monkeypatch.setenv("STM32CUBE_F7", str(tmp_path))
    assert BootloaderPage.host_sdk_root() is None
