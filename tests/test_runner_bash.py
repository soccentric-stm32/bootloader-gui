#!/usr/bin/env python3
"""
Tests for how the GUI's runner picks the bash that build and flash jobs use.

On Windows a bare `bash` is normally C:\\Windows\\System32\\bash.exe, the WSL
launcher, which cannot run the host build.  The runner must pick Git for
Windows' bash (as make.cmd does) instead.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from gui import runner


def test_posix_bash_is_none_off_windows(monkeypatch):
    monkeypatch.setattr(runner.sys, "platform", "linux")
    assert runner.posix_bash() is None


def test_bash_exe_override_wins(monkeypatch, tmp_path):
    fake = tmp_path / "bash.exe"
    fake.write_text("")
    monkeypatch.setattr(runner.sys, "platform", "win32")
    monkeypatch.setenv("BASH_EXE", str(fake))
    assert runner.posix_bash() == str(fake)


def test_wsl_launcher_on_path_is_rejected(monkeypatch):
    monkeypatch.setattr(runner.sys, "platform", "win32")
    monkeypatch.delenv("BASH_EXE", raising=False)
    monkeypatch.setattr(runner, "_windows_bash_candidates", lambda: [])
    monkeypatch.setattr(runner.shutil, "which",
                        lambda _name: r"C:\WINDOWS\system32\bash.exe")
    assert runner.posix_bash() is None


def test_other_bash_on_path_is_used_as_last_resort(monkeypatch):
    monkeypatch.setattr(runner.sys, "platform", "win32")
    monkeypatch.delenv("BASH_EXE", raising=False)
    monkeypatch.setattr(runner, "_windows_bash_candidates", lambda: [])
    monkeypatch.setattr(runner.shutil, "which",
                        lambda _name: r"D:\tools\bin\bash.exe")
    assert runner.posix_bash() == r"D:\tools\bin\bash.exe"


def test_git_bash_gets_usr_bin_on_path(tmp_path):
    (tmp_path / "bin").mkdir()
    (tmp_path / "usr" / "bin").mkdir(parents=True)
    dirs = runner._posix_path_dirs(str(tmp_path / "bin" / "bash.exe"))
    assert dirs == [str(tmp_path / "bin"), str(tmp_path / "usr" / "bin")]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only detection")
def test_detects_git_bash_on_this_machine():
    found = runner.posix_bash()
    assert found is None or "system32" not in found.lower()
