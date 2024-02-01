#
# Makefile - Run, check, test and package the BOOT Flasher GUI
#
# Author:  Sandesh Ghimire <sandesh@soccentric.com>
#
#   make gui      launch the GUI (flash_gui.py)
#   make deps     install the dependencies (PySide6, pyserial, cryptography)
#   make check    byte-compile the GUI
#   make test     run the Python tests
#   make package  build the package for this OS (see packaging/README.md)
#
# Python: PYTHON overrides the interpreter (make PYTHON=/opt/py/bin/python gui).
# Without it the project virtualenv wins when it exists (VENV, default .venv),
# then the interpreter on PATH: python on Windows, python3 elsewhere.  Windows
# puts the virtualenv interpreter in Scripts/ and ships "python" only - the
# python3 name is usually the Microsoft Store stub, which refuses to run.
#
# On a machine without a display (a Linux build host) run the tests headless:
#   QT_QPA_PLATFORM=offscreen make test
#
# The GUI drives the bootloader repository, found next to this one
# (../bootloader) or in the workspace's bootloader/ group folder;
# BOOTLOADER_DIR points at another checkout.
#

# Windows: run every recipe under Git's POSIX sh, also from cmd.exe or
# PowerShell with only Git\cmd on PATH. Otherwise native make falls back to
# cmd.exe, which cannot run the recipes (quotes, pipes, find, rm -rf), and
# `sh scripts/...` is not found. Git's usr\bin goes first on PATH so find,
# sort and friends are the POSIX tools, not the Windows ones of the same name.
ifeq ($(OS),Windows_NT)
ifneq ($(origin SHELL),command line)
GIT_USR_BIN := $(firstword \
  $(if $(wildcard C:/Program?Files/Git/usr/bin/sh.exe),C:/Program?Files/Git/usr/bin) \
  $(if $(wildcard $(subst \,/,$(LOCALAPPDATA))/Programs/Git/usr/bin/sh.exe),$(subst \,/,$(LOCALAPPDATA))/Programs/Git/usr/bin) \
  $(if $(wildcard C:/msys64/usr/bin/sh.exe),C:/msys64/usr/bin))
ifneq ($(GIT_USR_BIN),)
SHELL := $(subst ?, ,$(GIT_USR_BIN))/sh.exe
export PATH := $(subst /,\,$(subst ?, ,$(GIT_USR_BIN)));$(PATH)
endif
endif
endif

VENV ?= .venv

ifeq ($(OS),Windows_NT)
  VENV_PYTHON := $(VENV)/Scripts/python.exe
  DEFAULT_PYTHON := python
  PACKAGER := powershell -NoProfile -ExecutionPolicy Bypass -File packaging/build-windows.ps1
else
  VENV_PYTHON := $(VENV)/bin/python
  DEFAULT_PYTHON := python3
  ifeq ($(shell uname -s),Darwin)
    PACKAGER := bash packaging/build-macos.sh
  else
    PACKAGER := bash packaging/build-linux.sh
  endif
endif

# An explicit PYTHON, from the command line or the environment, always wins.
ifeq ($(origin PYTHON),undefined)
  ifneq ($(wildcard $(VENV_PYTHON)),)
    PYTHON := $(VENV_PYTHON)
  else
    PYTHON := $(DEFAULT_PYTHON)
  endif
endif

.PHONY: gui deps check test package help

gui: check
	$(PYTHON) flash_gui.py

deps:
	$(PYTHON) -m pip install -r requirements.txt

check:
	$(PYTHON) -m py_compile flash_gui.py $(wildcard gui/*.py)

test: check
	$(PYTHON) -m pytest -q tests

package: check
	$(PACKAGER)

.DEFAULT_GOAL := help

help:
	@sed -n "/^#   make/p" Makefile | sed "s/^#//"
