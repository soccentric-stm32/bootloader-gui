"""Widgets of the flash GUI on top of the shared SoCcentric shell.

The shell (Card, NavItem, Switch, labels...) lives in ``soc_widgets.py``,
shared with the other SoCcentric apps; this module adds the flasher's own
StepTracker.  Every Qt name used inside a paintEvent is
imported at the top: an exception there aborts the process.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from . import soc_icons as icons
from . import soc_theme as theme
from .soc_widgets import (  # noqa: F401  - re-exported for pages.py and window.py
    ROW_LABEL_WIDTH,
    Card,
    ElidedLabel,
    FlowLayout,
    NavItem,
    Switch,
    field,
    hairline,
    label,
    repolish,
    set_tone,
)


class StepTracker(QWidget):
    """Horizontal pipeline: numbered circles joined by lines.

    States per step: pending, running, done, failed, skipped.  A running
    step spins and may show a percentage.
    """

    def __init__(self, steps) -> None:
        super().__init__()
        self.steps = steps
        self.states = {key: "pending" for key, _ in steps}
        self.notes = {key: "" for key, _ in steps}
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._spin)
        self.setMinimumHeight(68)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(120 * len(self.steps), 68)

    def set_state(self, key: str, state: str, note: str = "") -> None:
        if key not in self.states:
            return
        self.states[key] = state
        self.notes[key] = note
        running = any(value == "running" for value in self.states.values())
        if running and not self._timer.isActive():
            self._timer.start()
        elif not running:
            self._timer.stop()
        self.update()

    def set_note(self, key: str, note: str) -> None:
        if key in self.notes and self.notes[key] != note:
            self.notes[key] = note
            self.update()

    def reset(self, done: set[str] | None = None) -> None:
        for key in self.states:
            self.states[key] = "done" if done and key in done else "pending"
            self.notes[key] = ""
        self._timer.stop()
        self.update()

    def _spin(self) -> None:
        self._angle = (self._angle + 8) % 360
        self.update()

    def paintEvent(self, _event) -> None:
        t = theme.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        count = len(self.steps)
        if not count:
            return
        width = self.width()
        slot = width / count
        radius = 12.0
        cy = 16.0
        centres = [QPointF(slot * i + slot / 2, cy) for i in range(count)]

        for i in range(count - 1):
            left = self.states[self.steps[i][0]]
            colour = QColor(t.success if left in ("done", "skipped")
                            else t.hairline)
            painter.setPen(QPen(colour, 2))
            painter.drawLine(QPointF(centres[i].x() + radius + 6, cy),
                             QPointF(centres[i + 1].x() - radius - 6, cy))

        number_font = QFont(self.font())
        number_font.setPixelSize(theme.px(12))
        number_font.setWeight(QFont.DemiBold)
        label_font = QFont(self.font())
        label_font.setPixelSize(theme.px(12))
        note_font = QFont(self.font())
        note_font.setPixelSize(theme.px(11))

        for index, ((key, text), centre) in enumerate(zip(self.steps, centres)):
            state = self.states[key]
            circle = QRectF(centre.x() - radius, centre.y() - radius,
                            radius * 2, radius * 2)
            if state == "done":
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(t.success))
                painter.drawEllipse(circle)
                icons.paint(painter, "check", circle.adjusted(6, 6, -6, -6),
                            "#ffffff", 3)
            elif state == "failed":
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(t.danger))
                painter.drawEllipse(circle)
                icons.paint(painter, "x", circle.adjusted(7, 7, -7, -7),
                            "#ffffff", 3)
            elif state == "running":
                painter.setPen(QPen(QColor(t.accent_soft), 2.5))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(circle)
                pen = QPen(QColor(t.accent), 2.5)
                pen.setCapStyle(Qt.RoundCap)
                painter.setPen(pen)
                painter.drawArc(circle, -self._angle * 16, 100 * 16)
                painter.setPen(QColor(t.accent))
                painter.setFont(number_font)
                painter.drawText(circle, Qt.AlignCenter, str(index + 1))
            else:
                skipped = state == "skipped"
                painter.setPen(QPen(QColor(t.border), 1.5,
                                    Qt.DashLine if skipped else Qt.SolidLine))
                painter.setBrush(QColor(t.surface))
                painter.drawEllipse(circle)
                painter.setPen(QColor(t.text_tertiary))
                painter.setFont(number_font)
                painter.drawText(circle, Qt.AlignCenter,
                                 "–" if skipped else str(index + 1))

            painter.setFont(label_font)
            painter.setPen(QColor(
                t.accent if state == "running" else
                t.danger if state == "failed" else
                t.text if state == "done" else t.text_secondary))
            painter.drawText(QRectF(centre.x() - slot / 2, cy + radius + 4,
                                    slot, 18), Qt.AlignCenter, text)
            note = self.notes.get(key, "")
            if note:
                painter.setFont(note_font)
                painter.setPen(QColor(t.text_tertiary))
                metrics = QFontMetrics(note_font)
                painter.drawText(
                    QRectF(centre.x() - slot / 2, cy + radius + 21, slot, 16),
                    Qt.AlignCenter,
                    metrics.elidedText(note, Qt.ElideRight, int(slot - 8)))
