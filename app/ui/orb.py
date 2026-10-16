"""Spidey AI floating orb — visual prototype.

Run from the project root with:
    python -m app.ui.orb

This file is intentionally standalone for the first UI test. It does not replace
app/main.py or change your existing AI, voice, or memory behavior.
"""

import math
import sys

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QLinearGradient, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QApplication, QMenu, QWidget


class SpideyOrb(QWidget):
    """Small draggable, always-on-top blue/cyan orb window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Spidey AI Orb")
        self.setFixedSize(190, 190)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._phase = 0.0
        self._drag_offset = None

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(40)

        screen = QApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            self.move(area.right() - self.width() - 35, area.bottom() - self.height() - 65)

    def _animate(self):
        self._phase = (self._phase + 0.045) % (2 * math.pi)
        self.update()

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        cx = self.width() / 2
        cy = self.height() / 2
        pulse = 1.0 + 0.025 * math.sin(self._phase)
        radius = 56 * pulse

        # Soft outer cyan glow.
        glow = QRadialGradient(cx, cy, 88)
        glow.setColorAt(0.0, QColor(0, 150, 255, 75))
        glow.setColorAt(0.55, QColor(0, 100, 255, 35))
        glow.setColorAt(1.0, QColor(0, 60, 180, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(QPoint(int(cx), int(cy)), 88, 88)

        # Rotating orbital rings.
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(math.degrees(self._phase))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(40, 205, 255, 145), 1.5))
        painter.drawEllipse(-69, -62, 138, 124)
        painter.setPen(QPen(QColor(20, 120, 255, 180), 1.2))
        painter.drawEllipse(-76, -48, 152, 96)
        painter.restore()

        # Main glass-like sphere.
        sphere = QRadialGradient(cx - 20, cy - 24, radius * 1.55)
        sphere.setColorAt(0.0, QColor(80, 225, 255, 245))
        sphere.setColorAt(0.28, QColor(15, 125, 255, 250))
        sphere.setColorAt(0.68, QColor(3, 48, 145, 250))
        sphere.setColorAt(1.0, QColor(0, 14, 55, 250))
        painter.setBrush(sphere)
        painter.setPen(QPen(QColor(80, 230, 255, 235), 2))
        painter.drawEllipse(QPoint(int(cx), int(cy)), int(radius), int(radius))

        # Inner highlight.
        highlight = QLinearGradient(cx - 28, cy - 48, cx + 30, cy + 45)
        highlight.setColorAt(0.0, QColor(170, 250, 255, 125))
        highlight.setColorAt(0.35, QColor(35, 160, 255, 45))
        highlight.setColorAt(1.0, QColor(0, 20, 100, 5))
        painter.setBrush(highlight)
        painter.setPen(QPen(QColor(90, 220, 255, 100), 1))
        painter.drawEllipse(QPoint(int(cx), int(cy)), int(radius - 5), int(radius - 5))

        # Small luminous core.
        core = QRadialGradient(cx, cy, 19)
        core.setColorAt(0.0, QColor(220, 255, 255, 250))
        core.setColorAt(0.3, QColor(45, 230, 255, 240))
        core.setColorAt(1.0, QColor(0, 145, 255, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(core)
        painter.drawEllipse(QPoint(int(cx), int(cy)), 19, 19)

        # Minimal orbit spark.
        spark_angle = self._phase * 1.7
        sx = cx + math.cos(spark_angle) * 72
        sy = cy + math.sin(spark_angle) * 56
        painter.setBrush(QColor(155, 250, 255, 235))
        painter.drawEllipse(QPoint(int(sx), int(sy)), 3, 3)

        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_menu(event.globalPosition().toPoint())
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = None
            event.accept()

    def _show_menu(self, global_position):
        menu = QMenu(self)
        menu.setStyleSheet(
            """
            QMenu {
                background-color: #071426;
                color: #e8f7ff;
                border: 1px solid #168bd1;
                padding: 6px;
            }
            QMenu::item { padding: 7px 24px; }
            QMenu::item:selected { background-color: #0b4770; }
            """
        )

        status_action = QAction("Spidey AI — Visual Preview", self)
        status_action.setEnabled(False)
        menu.addAction(status_action)
        menu.addSeparator()

        hide_action = QAction("Hide orb", self)
        hide_action.triggered.connect(self.hide)
        menu.addAction(hide_action)

        quit_action = QAction("Exit preview", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(quit_action)

        menu.exec(global_position)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Spidey AI Orb")
    orb = SpideyOrb()
    orb.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
