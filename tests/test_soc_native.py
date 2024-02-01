#!/usr/bin/env python3
"""Tests for the Windows 11 look layer (gui/soc_native.py)."""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

pytest.importorskip("PySide6")

from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from gui import soc_theme, soc_native  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_off_windows_is_a_no_op(monkeypatch):
    monkeypatch.setattr(soc_native, "ENABLED", False)
    marker = type("NavItem", (), {})
    assert soc_native.fluent_nav(marker) is marker
    assert not soc_native.mica_available()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows look")
def test_tokens_are_valid_colours_and_keep_the_app_accent(app):
    light, dark = soc_theme.LIGHT, soc_theme.DARK
    try:
        soc_native._tokens()
        assert soc_theme.LIGHT.accent == light.accent
        assert soc_theme.DARK.accent == dark.accent
        for tokens in (soc_theme.LIGHT, soc_theme.DARK):
            for name in ("window", "surface", "text", "accent", "accent_hover",
                         "accent_pressed", "accent_soft", "on_accent", "danger"):
                assert QColor(getattr(tokens, name)).isValid(), name
    finally:
        soc_theme.LIGHT, soc_theme.DARK = light, dark


@pytest.mark.skipif(sys.platform != "win32", reason="Windows look")
def test_stylesheet_variants():
    for dark in (False, True):
        for mica in (False, True):
            qss = soc_native._stylesheet(
                soc_theme.DARK if dark else soc_theme.LIGHT, mica)
            assert "QPushButton#Primary" in qss
            # Only the Mica sheet lets the backdrop through the panels.
            assert ("QWidget#Root" in qss) == mica
