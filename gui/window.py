"""Main window of the flash GUI.

Sidebar: the bootloader and the seven firmware projects, then the board
panel (serial port and what BOOT reports).  Content: the selected page above
a shared output console.  One job runner serves every page, because there is
one board.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
import time
from dataclasses import dataclass

from PySide6.QtCore import QProcess, QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QDesktopServices,
    QGuiApplication,
    QKeySequence,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import __version__, projects
from . import soc_theme as theme
from . import soc_native, soc_widgets
from .device import parse_boot_info, stlink_ports
from .pages import (
    BOOTCTL,
    DEV_SCRIPT,
    ROOT,
    BootloaderPage,
    FirmwarePage,
    Page,
)
from .runner import Job, Runner
from .soc_terminal import TerminalPanel
from .widgets import ElidedLabel, NavItem, label, set_tone

APP_GLYPH = "zap"
FluentNavItem = soc_native.fluent_nav(NavItem)

APP_NAME = "BOOT Flasher"
VERSION = __version__
# The pages need this much width; the debug terminal takes the rest.
CONTENT_MIN_WIDTH = 592
WINDOW_MIN_WIDTH = 1040
WINDOW_MIN_WIDTH_TERMINAL = 1180
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
SIGNING_GUIDE = ROOT / "docs" / "IMAGE_SIGNING.md"


@dataclass
class BoardState:
    connected: bool = False
    app_running: bool = False     # the application answered, not BOOT
    error: str = ""
    boot_version: str = ""
    active_slot: str | None = None
    target_slot: str | None = None
    flash_mode: str = ""
    key_id: str = ""
    security_floor: int | None = None
    active_pending: bool = False  # active slot on trial, not confirmed yet
    active_name: str = ""


class MainWindow(QMainWindow):
    def __init__(self, boot_firmware: str | None = None) -> None:
        super().__init__()
        soc_native.prepare_window(self)
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1040, 720)
        self.settings = QSettings("soccentric", "boot-flasher")
        self.board = BoardState()
        self.run_page: Page | None = None
        self._terminal_visible = True
        self._terminal_sizes: list[int] | None = None
        self._quiet_until = 0.0
        self._step_started: dict[str, float] = {}
        self._run_failed = False

        self.runner = Runner(self)
        self.runner.output.connect(self._on_output)
        self.runner.started.connect(self._on_step_started)
        self.runner.finished.connect(self._on_step_finished)
        self.runner.allFinished.connect(self._on_run_finished)

        self.info_process = QProcess(self)
        self.info_process.finished.connect(self._on_info_finished)
        self.info_process.errorOccurred.connect(self._on_info_error)
        self.info_timer = QTimer(self)
        self.info_timer.setSingleShot(True)
        self.info_timer.setInterval(400)
        self.info_timer.timeout.connect(self.refresh_board)

        self.pages: list[Page] = [BootloaderPage(self)]
        self.pages += [FirmwarePage(self, project)
                       for project in projects.PROJECTS]

        self._build_ui()
        self._build_menus()
        self._load_settings(boot_firmware)
        self.apply_theme()
        self._fit_sidebar()
        for page in self.pages:
            page.refresh()
        self._populate_ports()
        self.switch_page(self._initial_page)
        theme.on_change(lambda _tokens: self.apply_theme())

    # ---- layout ---------------------------------------------------------

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        row = QHBoxLayout(root)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self._side = self._sidebar()
        row.addWidget(self._side)

        content = QWidget()
        content.setObjectName("Content")
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, 0, 16)
        column.setSpacing(0)

        self.stack = QStackedWidget()
        for page in self.pages:
            scroll = QScrollArea()
            scroll.setObjectName("PageScroll")
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll.setWidget(page)
            self.stack.addWidget(scroll)

        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(8)
        self.splitter.addWidget(self.stack)
        self.splitter.addWidget(self._console())
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        column.addWidget(self.splitter, 1)
        content.setMinimumWidth(CONTENT_MIN_WIDTH)

        self.terminal = TerminalPanel()
        self.terminal.closed.connect(lambda: self.set_terminal_visible(False))
        self.terminal.baudChanged.connect(self._sync_terminal)
        holder = QWidget()
        holder.setObjectName("Content")
        holder_column = QVBoxLayout(holder)
        holder_column.setContentsMargins(0, 24, 32, 16)
        holder_column.setSpacing(0)
        holder_column.addWidget(self.terminal)
        self.terminal_holder = holder

        # Content and debug terminal side by side; the terminal can be
        # closed and is reopened from the View menu or the console header.
        self.body = QSplitter(Qt.Horizontal)
        self.body.setChildrenCollapsible(False)
        self.body.setHandleWidth(8)
        self.body.addWidget(content)
        self.body.addWidget(holder)
        self.body.setStretchFactor(0, 1)
        self.body.setStretchFactor(1, 0)
        row.addWidget(self.body, 1)
        self.setCentralWidget(root)

    def _sidebar(self) -> QWidget:
        side = QWidget()
        side.setObjectName("Sidebar")
        side.setFixedWidth(soc_widgets.SIDEBAR_WIDTH)
        column = QVBoxLayout(side)
        column.setContentsMargins(12, 16, 12, 12)
        column.setSpacing(2)

        self.sidebar_header = soc_widgets.SidebarHeader(APP_NAME, "NUCLEO-F767ZI", APP_GLYPH)
        column.addWidget(self.sidebar_header)
        column.addSpacing(24)

        def section(text: str) -> None:
            column.addWidget(soc_widgets.section(text))

        section("BOOTLOADER")
        for index, page in enumerate(self.pages):
            if index == 1:
                column.addSpacing(16)
                section("APPLICATIONS")
            page.nav = FluentNavItem(
                page.icon_name, page.title, page.nav_subtitle)
            page.nav.clicked.connect(
                lambda _checked=False, i=index: self.switch_page(i))
            column.addWidget(page.nav)
        column.addStretch(1)
        column.addWidget(self._board_box())
        column.addSpacing(8)
        column.addWidget(soc_widgets.version_label(VERSION))
        return side

    def _board_box(self) -> QFrame:
        box = QFrame()
        box.setObjectName("DeviceBox")
        column = QVBoxLayout(box)
        column.setContentsMargins(12, 10, 8, 12)
        column.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(4)
        head.addWidget(label("Board", "CardTitle"))
        head.addStretch(1)
        self.board_pill = label("", "Pill")
        head.addWidget(self.board_pill)
        self.board_refresh = soc_widgets.icon_button(
            "refresh", "Refresh ports and board info (F5)")
        self.board_refresh.clicked.connect(self.refresh_all_board)
        head.addWidget(self.board_refresh)
        column.addLayout(head)

        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.lineEdit().setPlaceholderText("No ST-LINK found")
        self.port_combo.setToolTip("ST-LINK virtual COM port")
        self.port_combo.currentTextChanged.connect(self._on_port_changed)
        column.addWidget(self.port_combo)
        self.board_line1 = ElidedLabel(name="Hint", mode=Qt.ElideRight)
        self.board_line2 = ElidedLabel(name="Hint", mode=Qt.ElideRight)
        column.addWidget(self.board_line1)
        column.addWidget(self.board_line2)
        return box

    def _console(self) -> QWidget:
        self.output = soc_widgets.OutputPanel(
            "Output", "Command output appears here. Choose a page on the left "
            "and press its blue button.", copy=False, clear=False)
        card = self.output
        self.console_title = self.output.title
        self.console_status = self.output.status
        self.progress = self.output.progress
        self.cancel_button = self.output.cancel_button
        self.cancel_button.setToolTip("Stop the running command (Esc)")
        self.output.cancelled.connect(self.cancel)
        self.terminal_button = soc_widgets.icon_button(
            "terminal", "Show or hide the debug terminal (Ctrl+J)")
        self.terminal_button.clicked.connect(self.toggle_terminal)
        self.copy_button = soc_widgets.icon_button("copy", "Copy the output")
        self.copy_button.clicked.connect(self.copy_output)
        self.clear_button = soc_widgets.icon_button("trash", "Clear the output (Ctrl+K)")
        self.clear_button.clicked.connect(self.clear_output)
        for widget in (self.terminal_button, self.copy_button, self.clear_button):
            self.output.add_tool(widget, before_copy=False)
        self.console = self.output.console
        self.console.setMinimumHeight(120)

        wrapper = QWidget()
        wrapper.setObjectName("Content")
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(32, 0, 32, 0)
        layout.addWidget(card)
        return wrapper

    def _build_menus(self) -> None:
        bar = self.menuBar()

        file_menu = bar.addMenu("&File")
        open_action = QAction("Open Bootloader Firmware…", self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self._open_boot_firmware)
        file_menu.addAction(open_action)
        file_menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.setShortcut(QKeySequence.Quit)
        quit_action.setMenuRole(QAction.QuitRole)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        edit_menu = bar.addMenu("&Edit")
        for text, key, method in (("Undo", QKeySequence.Undo, "undo"),
                                  ("Redo", QKeySequence.Redo, "redo"),
                                  (None, None, None),
                                  ("Cut", QKeySequence.Cut, "cut"),
                                  ("Copy", QKeySequence.Copy, "copy"),
                                  ("Paste", QKeySequence.Paste, "paste"),
                                  ("Select All", QKeySequence.SelectAll,
                                   "selectAll")):
            if text is None:
                edit_menu.addSeparator()
                continue
            action = QAction(text, self)
            action.setShortcut(key)
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            action.triggered.connect(
                lambda _checked=False, m=method: self._route_edit(m))
            edit_menu.addAction(action)

        view_menu = bar.addMenu("&View")
        self.page_actions: list[QAction] = []
        group = QActionGroup(self)
        for index, page in enumerate(self.pages):
            action = QAction(page.title, self)
            action.setCheckable(True)
            action.setShortcut(QKeySequence(f"Ctrl+{index + 1}"))
            action.triggered.connect(
                lambda _checked=False, i=index: self.switch_page(i))
            group.addAction(action)
            view_menu.addAction(action)
            self.page_actions.append(action)
            if index == 0:
                view_menu.addSeparator()
        view_menu.addSeparator()
        self.terminal_action = QAction("Debug Terminal", self)
        self.terminal_action.setCheckable(True)
        self.terminal_action.setShortcut(QKeySequence("Ctrl+J"))
        self.terminal_action.setToolTip("Show the ST-LINK debug UART output")
        self.terminal_action.toggled.connect(self.set_terminal_visible)
        view_menu.addAction(self.terminal_action)
        view_menu.addSeparator()
        soc_widgets.add_zoom_actions(view_menu, self, self.settings)
        view_menu.addSeparator()
        clear_action = QAction("Clear Output", self)
        clear_action.setShortcut(QKeySequence("Ctrl+K"))
        clear_action.triggered.connect(self.clear_output)
        view_menu.addAction(clear_action)

        run_menu = bar.addMenu("&Run")
        self.run_all_action = QAction("Build and Flash", self)
        self.run_all_action.setShortcut(QKeySequence("Ctrl+Return"))
        self.run_all_action.triggered.connect(
            lambda: self.current_page().run_all())
        build_action = QAction("Build", self)
        build_action.setShortcut(QKeySequence("Ctrl+B"))
        build_action.triggered.connect(
            lambda: self.current_page().run_steps(["build"]))
        flash_action = QAction("Flash Only", self)
        flash_action.setShortcut(QKeySequence("Ctrl+Shift+Return"))
        flash_action.triggered.connect(
            lambda: self.current_page().run_steps(["flash"]))
        self.cancel_action = QAction("Cancel", self)
        self.cancel_action.setShortcut(QKeySequence(Qt.Key_Escape))
        self.cancel_action.triggered.connect(self.cancel)
        self.cancel_action.setEnabled(False)
        for action in (self.run_all_action, build_action, flash_action):
            run_menu.addAction(action)
        run_menu.addSeparator()
        run_menu.addAction(self.cancel_action)
        self.run_actions = [self.run_all_action, build_action, flash_action]

        board_menu = bar.addMenu("&Board")
        refresh_action = QAction("Refresh Board", self)
        refresh_action.setShortcut(QKeySequence.Refresh)
        refresh_action.triggered.connect(self.refresh_all_board)
        board_menu.addAction(refresh_action)
        speed = board_menu.addMenu("Upload Speed")
        self.baud_group = QActionGroup(self)
        for baud in ("115200", "921600"):
            action = QAction(f"{baud} baud", self)
            action.setCheckable(True)
            action.setData(baud)
            self.baud_group.addAction(action)
            speed.addAction(action)
        board_menu.addSeparator()
        enter_action = QAction("Enter Bootloader", self)
        enter_action.triggered.connect(self.enter_boot)
        board_menu.addAction(enter_action)
        recover_action = QAction("Recover Board into BOOT", self)
        recover_action.setToolTip("Reset over SWD and catch BOOT's listen "
                                  "window; for an application that does "
                                  "not answer HWLINK")
        recover_action.triggered.connect(self.recover_board)
        board_menu.addAction(recover_action)
        provision_action = QAction("Provision Board…", self)
        provision_action.setToolTip("Set dual-bank flash, mass-erase and "
                                    "write BOOT; needed once for a new "
                                    "board or after WRONG_FLASH_MODE")
        provision_action.triggered.connect(self.provision_board)
        board_menu.addAction(provision_action)
        reset_action = QAction("Reset Board", self)
        reset_action.setShortcut(QKeySequence("Ctrl+R"))
        reset_action.triggered.connect(
            lambda: self.current_page().reset_board())
        board_menu.addAction(reset_action)
        self.board_actions = [enter_action, recover_action, provision_action,
                              reset_action]

        help_menu = bar.addMenu("&Help")
        guide_action = QAction("Image Signing Guide", self)
        guide_action.triggered.connect(
            lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(SIGNING_GUIDE))))
        help_menu.addAction(guide_action)
        about_action = QAction(f"About {APP_NAME}", self)
        about_action.setMenuRole(QAction.AboutRole)
        about_action.triggered.connect(self._about)
        help_menu.addAction(about_action)

    # ---- theme ----------------------------------------------------------

    def apply_theme(self) -> None:
        """Called after every theme or zoom change (soc_theme.on_change)."""
        for page in self.pages:
            page.apply_theme()

    def _fit_sidebar(self) -> None:
        """Never let the window get shorter than its sidebar needs.

        Below that the board box is squeezed and its text overlaps the port
        selector.  The menu bar and title bar take about 58 px."""
        need = self._side.minimumSizeHint().height() + 58
        self.setMinimumHeight(max(self.minimumHeight(), need))

    # ---- pages ----------------------------------------------------------

    def current_page(self) -> Page:
        return self.pages[self.stack.currentIndex()]

    def switch_page(self, index: int) -> None:
        """The one place that changes page: nav, menu and title follow."""
        index = max(0, min(index, len(self.pages) - 1))
        self.stack.setCurrentIndex(index)
        page = self.pages[index]
        for i, other in enumerate(self.pages):
            other.nav.setChecked(i == index)
            self.page_actions[i].setChecked(i == index)
        self.setWindowTitle(f"{page.title} — {APP_NAME}")
        self.run_all_action.setText(page.primary_button.text()
                                    .replace("&&", "and"))
        if page.uses_serial and not self.board.connected and \
                not self.board.app_running and \
                self.port() and not self.busy():
            self.info_timer.start()
            self._sync_terminal()

    def _open_boot_firmware(self) -> None:
        self.switch_page(0)
        self.pages[0].browse()

    # ---- runner ---------------------------------------------------------

    def busy(self) -> bool:
        return self.runner.busy() or self.run_page is not None

    def run(self, page: Page, jobs: list[Job], steps: list[str]) -> None:
        if self.busy() or not jobs:
            return
        self.info_timer.stop()
        if self.info_process.state() != QProcess.NotRunning:
            self.info_process.kill()
            self.info_process.waitForFinished(500)
        self.run_page = page
        self._run_failed = False
        self._step_started.clear()
        for step in steps:
            page.stepper.set_state(step, "pending")
        self.console.appendPlainText("")
        self._set_busy(True)
        self.runner.start(jobs)

    def _set_busy(self, busy: bool) -> None:
        for page in self.pages:
            page.set_busy(busy)
        for action in (*self.run_actions, *self.board_actions):
            action.setEnabled(not busy)
        self.port_combo.setEnabled(not busy)
        self.board_refresh.setEnabled(not busy)
        self.cancel_action.setEnabled(busy)
        self.cancel_button.setVisible(busy)
        if busy:
            self.progress.setRange(0, 0)
            self.progress.show()
        else:
            self.progress.hide()

    def _on_step_started(self, step: str, text: str) -> None:
        job = self.runner.current
        if job is not None and job.serial:
            # Released before QProcess starts the command.
            self.terminal.stop("Paused while the board port is in use")
        self._step_started.setdefault(step, time.monotonic())
        if self.run_page is not None:
            self.run_page.stepper.set_state(step, "running")
        self.progress.setRange(0, 0)
        self.console_status.setText(text)
        set_tone(self.console_status, "")

    def _on_step_finished(self, step: str, success: bool, code: int) -> None:
        page = self.run_page
        elapsed = time.monotonic() - self._step_started.get(step,
                                                             time.monotonic())
        note = f"{elapsed:.0f} s" if elapsed >= 1 else ""
        if page is not None:
            page.stepper.set_state(step, "done" if success else "failed",
                                   note if success else f"exit {code}")
        self._sync_terminal()

    def _on_run_finished(self, failed: bool) -> None:
        page = self.run_page
        self.run_page = None
        self._set_busy(False)
        if failed:
            self.console_status.setText("Failed · see the output above")
            set_tone(self.console_status, "danger")
        else:
            self.console_status.setText("Done")
            set_tone(self.console_status, "success")
        if page is not None:
            page.run_finished(failed)
            if page.uses_serial or failed is False:
                self.info_timer.start()
        self._sync_terminal()

    def _on_output(self, line: str) -> None:
        text = ANSI_RE.sub("", line).rstrip("\r\n")
        if not text:
            return
        if text.startswith("{"):
            try:
                event = json.loads(text)
            except json.JSONDecodeError:
                event = None
            if isinstance(event, dict):
                self._on_event(event)
                if event.get("event") == "progress":
                    return       # the progress bar shows it
        self._append(text)

    def _on_event(self, event: dict) -> None:
        kind = event.get("event")
        if kind == "progress":
            percent = event.get("percent")
            if isinstance(percent, (int, float)):
                self.progress.setRange(0, 100)
                self.progress.setValue(max(0, min(100, int(percent))))
                if self.run_page is not None:
                    self.run_page.stepper.set_note(
                        self.runner.current.step if self.runner.current
                        else "flash", f"{int(percent)}%")
            operation = event.get("operation", "update")
            self.console_status.setText(
                f"{operation} {event.get('done', 0)} / {event.get('total', 0)}")
        elif kind == "error":
            message = str(event.get("error", "error"))
            self.console_status.setText(message)
            set_tone(self.console_status, "danger")
            if "timeout waiting for reply" in message:
                self._append("hint: nothing answers HWLINK.  If the "
                             "application does not speak HWLINK (or is "
                             "busy), use Board > Recover Board into BOOT.")
            if "on trial" in message:
                self.board.active_pending = True
                self._append("hint: the active slot has not confirmed its "
                             "trial.  Flash again and choose Reset Board to "
                             "let BOOT finish the trial first.")
        elif kind in ("stage", "result", "confirm"):
            self.console_status.setText(str(event.get("status",
                                                      event.get("state", ""))))

    def _append(self, text: str) -> None:
        bar = self.console.verticalScrollBar()
        at_end = bar.value() >= bar.maximum() - 4
        self.console.appendPlainText(text)
        if at_end:
            self.console.moveCursor(QTextCursor.End)
            bar.setValue(bar.maximum())
            # Moving the cursor to the end scrolls long lines sideways;
            # keep the start of every line in view.
            self.console.horizontalScrollBar().setValue(0)

    def console_line(self, text: str) -> None:
        self._append(text)

    def cancel(self) -> None:
        if not self.busy():
            return
        self.console_status.setText("Cancelling…")
        self.runner.cancel()

    def clear_output(self) -> None:
        self.console.clear()
        if not self.busy():
            self.console_status.setText("")

    def copy_output(self) -> None:
        QGuiApplication.clipboard().setText(self.console.toPlainText())
        self.console_status.setText("Output copied")
        set_tone(self.console_status, "")

    # ---- debug terminal -------------------------------------------------

    def set_terminal_visible(self, visible: bool) -> None:
        self._terminal_visible = visible
        self.setMinimumWidth(WINDOW_MIN_WIDTH_TERMINAL if visible
                             else WINDOW_MIN_WIDTH)
        if self.terminal_action.isChecked() != visible:
            self.terminal_action.blockSignals(True)
            self.terminal_action.setChecked(visible)
            self.terminal_action.blockSignals(False)
        if visible:
            self.terminal_holder.show()
            self.terminal.show()
            # The window may not be laid out yet; sizes need a real width.
            QTimer.singleShot(0, self._apply_terminal_sizes)
        else:
            sizes = self.body.sizes()
            if len(sizes) == 2 and sum(sizes) > 0:
                self._terminal_sizes = list(sizes)
            self.terminal_holder.hide()
        self.terminal_button.setToolTip(
            "Hide the debug terminal (Ctrl+J)" if visible else
            "Show the debug terminal (Ctrl+J)")
        self._sync_terminal()

    def _apply_terminal_sizes(self) -> None:
        """Restore the saved terminal width, leaving room for the page."""
        if not self._terminal_visible:
            return
        sizes = self._terminal_sizes
        terminal = sizes[1] if sizes and len(sizes) == 2 else 368
        terminal = max(300, terminal)
        usable = self.body.width() - self.body.handleWidth()
        if usable > 0:
            terminal = min(terminal, max(300, usable - CONTENT_MIN_WIDTH))
            self.body.setSizes([usable - terminal, terminal])
        else:
            self.body.setSizes([max(CONTENT_MIN_WIDTH, 900 - terminal),
                                terminal])

    def toggle_terminal(self) -> None:
        self.set_terminal_visible(not self._terminal_visible)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not getattr(self, "_terminal_visible", False) or \
                not hasattr(self, "body"):
            return
        usable = self.body.width() - self.body.handleWidth()
        sizes = self.body.sizes()
        if usable <= 0 or len(sizes) != 2:
            return
        # Keep the page usable; the terminal gives way on narrow windows.
        limit = max(300, usable - CONTENT_MIN_WIDTH)
        if sizes[1] > limit:
            self.body.setSizes([usable - limit, limit])

    def _sync_terminal(self) -> None:
        """Pause the monitor only when it shares the bootctl port."""
        if not self._terminal_visible:
            self.terminal.shutdown()
            return
        self.terminal.set_board_port(self.port())
        if self.port_in_use():
            self.terminal.stop("Paused while the board port is in use")
            return
        if self.info_timer.isActive() and not self.waiting_for_trial():
            self.terminal.stop("Paused while reading the board")
            return
        self.terminal.resume()

    # ---- board ----------------------------------------------------------

    def port(self) -> str:
        return self.port_combo.currentText().strip()

    def port_in_use(self) -> bool:
        """True while bootctl (a job or a board read) owns the serial port."""
        return self.runner.busy() or \
            self.info_process.state() != QProcess.NotRunning

    def baud(self) -> str:
        action = self.baud_group.checkedAction()
        return action.data() if action else "115200"

    def openocd_cfg(self) -> str:
        return os.environ.get("OPENOCD_CFG", "board/st_nucleo_f7.cfg")

    def _populate_ports(self) -> None:
        current = self.port() or self.settings.value("port", "", type=str)
        ports = stlink_ports()
        self.port_combo.blockSignals(True)
        self.port_combo.clear()
        self.port_combo.addItems(ports)
        if current and (current in ports or not ports):
            self.port_combo.setCurrentText(current)
        elif ports:
            self.port_combo.setCurrentIndex(0)
        else:
            self.port_combo.setCurrentText("")
        self.port_combo.blockSignals(False)
        self.terminal.refresh_ports(self.port())
        self._on_port_changed(self.port())

    def refresh_all_board(self) -> None:
        if self.busy():
            return
        self._populate_ports()

    def _on_port_changed(self, _text: str) -> None:
        self.board = BoardState()
        self._show_board()
        if self.port():
            self.info_timer.start()
        self._sync_terminal()

    def refresh_board_later(self, ms: int) -> None:
        """Read the board once after `ms`, and not before.

        A Hello inside BOOT's 500 ms listen window (ENT-001) keeps BOOT in
        update mode, which would stop a trial from being counted.
        """
        self._quiet_until = time.monotonic() + ms / 1000
        self.board_line1.setText("Waiting for the trial to end…")
        set_tone(self.board_line1, "")
        self.board_line2.setText("leave the board alone for "
                                 f"{ms // 1000} s")
        QTimer.singleShot(ms + 100, self.refresh_board)

    def waiting_for_trial(self) -> bool:
        return time.monotonic() < self._quiet_until

    def refresh_board(self) -> None:
        port = self.port()
        if not port or self.busy() or \
                self.info_process.state() != QProcess.NotRunning or \
                time.monotonic() < self._quiet_until:
            return
        self.board_line1.setText("Reading board…")
        set_tone(self.board_line1, "")
        self.board_line2.setText(port)
        # bootctl needs the port; the debug monitor reopens it afterwards.
        self.terminal.stop("Paused while reading the board")
        # --no-enter: reading the panel must never stop a running
        # application.  Flashing switches to BOOT on its own.
        self.info_process.start(sys.executable, [
            str(BOOTCTL), "--port", port, "--timeout", "2", "--no-enter",
            "info", "--json"])

    def _on_info_finished(self, code: int, status: QProcess.ExitStatus) -> None:
        self._sync_terminal()
        out = bytes(self.info_process.readAllStandardOutput()).decode(
            "utf-8", "replace")
        err = bytes(self.info_process.readAllStandardError()).decode(
            "utf-8", "replace").strip()
        ok = status == QProcess.NormalExit and code == 0
        if ok and self.absorb_board_json(out):
            return
        message = (err.splitlines()[-1] if err else
                   self._json_error(out) or "no answer"
                   ).removeprefix("bootctl: ")
        if "running the application" in message:
            # Keep what BOOT told us last; the slots are unchanged.
            self.board.app_running = True
            self.board.connected = False
            self.board.error = ""
        else:
            self.board = BoardState(error=message)
        self._show_board()

    @staticmethod
    def _json_error(text: str) -> str:
        """The "error" of a bootctl --json error event, or an empty string.

        With --json bootctl reports failures on stdout, not stderr.
        """
        for line in reversed(text.splitlines()):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict) and event.get("event") == "error":
                return str(event.get("error") or "")
        return ""

    def absorb_board_json(self, text: str) -> bool:
        """Take `bootctl info --json` output; False if it is not that."""
        start, end = text.find("{"), text.rfind("}")
        try:
            data = json.loads(text[start:end + 1]) if start >= 0 else None
        except json.JSONDecodeError:
            data = None
        view = parse_boot_info(data) if isinstance(data, dict) else None
        if view is None:
            return False
        active = next((slot for slot in view.slots
                       if slot.slot == view.active_slot), None)
        names = {item.get("slot"): item.get("name", "")
                 for item in data.get("slots", []) if isinstance(item, dict)}
        self.board = BoardState(
            connected=True, boot_version=view.boot_version,
            active_slot=view.active_slot, target_slot=view.target_slot,
            flash_mode=view.flash_mode, key_id=view.key_id,
            security_floor=view.security_floor,
            active_pending=bool(active and active.pending and
                                not active.confirmed),
            active_name=str(names.get(view.active_slot, "") or ""))
        self._show_board()
        return True

    def _on_info_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.FailedToStart:
            self.board = BoardState(error="could not start bootctl.py")
            self._show_board()
        self._sync_terminal()

    def _show_board(self) -> None:
        board = self.board
        if not self.port():
            self.board_pill.setText("No port")
            set_tone(self.board_pill, "")
            self.board_line1.setText("Connect the ST-LINK USB port")
            self.board_line2.setText("")
        elif board.connected:
            single = board.flash_mode and board.flash_mode != "DUAL_BANK"
            self.board_pill.setText("Single bank" if single else
                                    "On trial" if board.active_pending
                                    else "Connected")
            set_tone(self.board_pill, "warning" if single or
                     board.active_pending else "success")
            parts = [f"BOOT {board.boot_version}" if board.boot_version
                     else "BOOT"]
            if board.active_slot:
                parts.append(f"slot {board.active_slot} " +
                             ("on trial" if board.active_pending
                              else "active"))
            if board.target_slot:
                parts.append(f"next {board.target_slot}")
            self.board_line1.setText(" · ".join(parts))
            set_tone(self.board_line1, "")
            signing = []
            if board.key_id:
                signing.append(f"key {board.key_id}")
            if board.security_floor is not None:
                signing.append(f"floor {board.security_floor}")
            self.board_line2.setText(" · ".join(signing) or
                                     "unsigned images accepted")
        elif board.app_running:
            self.board_pill.setText("App running")
            set_tone(self.board_pill, "accent")
            known = [f"BOOT {board.boot_version}"] if board.boot_version else []
            if board.active_slot:
                known.append(f"slot {board.active_slot}")
            self.board_line1.setText("Application running" +
                                     (f" · {' · '.join(known)}" if known
                                      else ""))
            set_tone(self.board_line1, "")
            if board.key_id or board.security_floor is not None:
                signing = []
                if board.key_id:
                    signing.append(f"key {board.key_id}")
                if board.security_floor is not None:
                    signing.append(f"floor {board.security_floor}")
                self.board_line2.setText(" · ".join(signing))
            else:
                self.board_line2.setText("Flashing reads BOOT's key and floor")
        elif board.error:
            self.board_pill.setText("No answer")
            set_tone(self.board_pill, "warning")
            self.board_line1.setText(board.error)
            set_tone(self.board_line1, "warning")
            self.board_line2.setText("Is BOOT flashed? Try Refresh.")
        else:
            self.board_pill.setText("")
            self.board_line1.setText("")
            self.board_line2.setText("")
        self.board_pill.setVisible(bool(self.board_pill.text()))
        for page in self.pages:
            page.board_info_changed()

    def serial_command(self, command: str, text: str) -> None:
        port = self.port()
        if not port:
            self.error("Board", "Choose the board's serial port in the "
                       "sidebar first.")
            return
        args = [str(BOOTCTL), "--port", port, "--baud", self.baud(), command]
        self.run(self.current_page(),
                 [Job(command, sys.executable, args, text, ROOT,
                      "bootctl.py " + " ".join(args[1:]), serial=True)], [])

    def enter_boot(self) -> None:
        self.serial_command("enter", "Switching the board to BOOT…")

    def provision_board(self) -> None:
        """Provision from any page: show the Bootloader page, then run it."""
        if self.busy():
            return
        self.switch_page(0)
        self.pages[0].provision()

    def recover_board(self) -> None:
        """Reach BOOT when the running application does not answer HWLINK.

        bootctl keeps resending Hello while the board is reset over SWD, so
        one lands in BOOT's 500 ms listen window (ENT-001) and BOOT stays
        in update mode.
        """
        port = self.port()
        if not port:
            self.error("Board", "Choose the board's serial port in the "
                       "sidebar first.")
            return
        if self.busy():
            return
        boot_page = self.pages[0]
        if boot_page.container_switch.isChecked():
            reset = f"{shlex.quote(str(DEV_SCRIPT))} reset"
        else:
            reset = (f"openocd -f {shlex.quote(self.openocd_cfg())} "
                     "-c 'init; reset run; exit'")
        script = (
            f"{shlex.quote(sys.executable)} {shlex.quote(str(BOOTCTL))} "
            f"--port {shlex.quote(port)} --no-enter catch --for 20 --json"
            " > \"$out\" 2>&1 & pid=$!; sleep 0.5; "
            f"{reset} >/dev/null 2>&1; wait $pid; rc=$?; cat \"$out\"; "
            "exit $rc")
        job = Job("recover", "bash",
                  ["-c", 'out=$(mktemp); trap \'rm -f "$out"\' EXIT; ' + script],
                  "Resetting over SWD and catching BOOT…", ROOT,
                  "bootctl catch --for 20 + SWD reset",
                  capture=True, serial=True, done=self._recovered)
        self.run(self.current_page(), [job], [])

    def _recovered(self, text: str) -> None:
        if not self.absorb_board_json(text):
            raise RuntimeError("BOOT did not answer during the reset")
        self._append("BOOT caught in update mode; it boots the active slot "
                     "after 120 s without traffic, or on Reset Board.")

    # ---- dialogs --------------------------------------------------------

    def error(self, title: str, text: str) -> None:
        soc_widgets.error(self, title, text)

    def confirm(self, title: str, text: str, ok_text: str,
                destructive: bool = False) -> bool:
        return soc_widgets.confirm(self, title, text, ok_text, destructive)

    def _about(self) -> None:
        soc_widgets.about(
            self, APP_NAME, VERSION, APP_GLYPH,
            "Flash the A/B bootloader and the firmware projects of the "
            "soccentric-stm32 workspace onto a NUCLEO-F767ZI.",
            "Applications are signed with ECDSA P-256 before upload; BOOT "
            "only starts signed images.")

    @staticmethod
    def _route_edit(method: str) -> None:
        widget = QApplication.focusWidget()
        target = getattr(widget, method, None)
        if callable(target):
            target()

    # ---- settings -------------------------------------------------------

    def _load_settings(self, boot_firmware: str | None) -> None:
        geometry = self.settings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            self.resize(1200, 880)
        state = self.settings.value("window/splitter")
        if state is not None:
            self.splitter.restoreState(state)
        else:
            self.splitter.setSizes([560, 240])
        sizes = self.settings.value("terminal/sizes")
        if isinstance(sizes, list) and len(sizes) == 2:
            try:
                self._terminal_sizes = [int(value) for value in sizes]
            except (TypeError, ValueError):
                self._terminal_sizes = None
        self.terminal.set_baud(self.settings.value("terminal/baud", "115200",
                                                   type=str))
        self.terminal.set_preferred_port(self.settings.value("terminal/port",
                                                             "", type=str))
        self.set_terminal_visible(self.settings.value("terminal/visible", True,
                                                      type=bool))
        for page in self.pages:
            page.load(self.settings)
        if boot_firmware:
            self.pages[0].firmware_edit.setText(boot_firmware)
        baud = self.settings.value("baud", "115200", type=str)
        for action in self.baud_group.actions():
            action.setChecked(action.data() == baud)
        if self.baud_group.checkedAction() is None:
            self.baud_group.actions()[0].setChecked(True)
        saved = self.settings.value("page", "boot", type=str)
        self._initial_page = next(
            (i for i, page in enumerate(self.pages) if page.key == saved), 0)
        if boot_firmware:
            self._initial_page = 0

    def _save_settings(self) -> None:
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("window/splitter", self.splitter.saveState())
        self.settings.setValue("terminal/visible", self._terminal_visible)
        self.settings.setValue("terminal/baud", self.terminal.baud())
        self.settings.setValue("terminal/port", self.terminal.port())
        if self._terminal_visible:
            self.settings.setValue("terminal/sizes", self.body.sizes())
        elif self._terminal_sizes:
            self.settings.setValue("terminal/sizes", self._terminal_sizes)
        self.settings.setValue("page", self.current_page().key)
        self.settings.setValue("port", self.port())
        self.settings.setValue("baud", self.baud())
        for page in self.pages:
            page.save(self.settings)

    def closeEvent(self, event) -> None:
        if self.busy() and not self.confirm(
                "Stop the running command?",
                "A build or flash is still running. Quitting stops it; an "
                "interrupted flash leaves the target slot unusable until "
                "it is flashed again.", "Quit", destructive=True):
            event.ignore()
            return
        self.runner.cancel()
        self.terminal.shutdown()
        if self.info_process.state() != QProcess.NotRunning:
            self.info_process.kill()
            self.info_process.waitForFinished(1000)
        self._save_settings()
        super().closeEvent(event)
