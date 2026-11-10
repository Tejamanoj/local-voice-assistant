

import math
import sys
import threading

import numpy as np
import sounddevice as sd

from app.ui.audio_state import (
    get_audio_state,
    set_audio_state,
    get_orb_visibility,
)

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QColor,
    QLinearGradient,
    QPainter,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QWidget,
    QSystemTrayIcon,
    QStyle,
)


# Audio configuration
MICROPHONE_ID = 1
SAMPLE_RATE = 16000
BLOCK_SIZE = 1024
BAR_COUNT = 48


class SpideyOrb(QWidget):
    """Draggable, always-on-top blue/cyan orb."""

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Spidey AI Orb")
        self.setFixedSize(240, 240)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )

        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground, True
        )

        self._phase = 0.0
        self._drag_offset = None

        self._spectrum = [0.02] * BAR_COUNT
        self._target_spectrum = [0.02] * BAR_COUNT

        self._audio_level = 0.0
        self._display_level = 0.0

        self._state = "STARTING MIC"
        self._audio_lock = threading.Lock()

        self._stream = None
        self._audio_error = None

        # UI animation timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(30)

        # Position orb near the bottom-right corner
        screen = QApplication.primaryScreen()

        if screen:
            area = screen.availableGeometry()
            self.move(
                area.right() - self.width() - 35,
                area.bottom() - self.height() - 65,
            )

        self._start_microphone()

        # System tray controller
        self.tray = QSystemTrayIcon(self)

        tray_icon = self.style().standardIcon(
            QStyle.StandardPixmap.SP_ComputerIcon
        )
        self.tray.setIcon(tray_icon)
        self.tray.setToolTip("Spidey AI")

        tray_menu = QMenu(self)

        show_action = QAction("Show Orb", self)
        show_action.triggered.connect(self.show_orb)
        tray_menu.addAction(show_action)

        hide_action = QAction("Hide Orb", self)
        hide_action.triggered.connect(self.hide)
        tray_menu.addAction(hide_action)

        tray_menu.addSeparator()

        exit_action = QAction("Exit Spidey Orb", self)
        exit_action.triggered.connect(
            QApplication.instance().quit
        )
        tray_menu.addAction(exit_action)

        self.tray.setContextMenu(tray_menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _start_microphone(self):
        """Start continuous microphone capture."""
        try:
            self._stream = sd.InputStream(
                device=MICROPHONE_ID,
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=BLOCK_SIZE,
                callback=self._audio_callback,
            )

            self._stream.start()
            self._state = "LISTENING"

            print("Spidey orb: microphone connected.")

        except Exception as exc:
            self._audio_error = str(exc)
            self._state = "MIC ERROR"

            print(
                f"Could not start microphone: {exc}",
                file=sys.stderr,
            )

    def _audio_callback(self, indata, frames, time_info, status):
        """Calculate microphone volume and frequency bands."""
        del frames, time_info, status

        samples = indata[:, 0].copy()

        if samples.size == 0:
            return

        # Overall microphone volume
        rms = float(np.sqrt(np.mean(samples * samples)))
        activity = min(1.0, rms * 12.0)

        # Frequency analysis
        windowed = samples * np.hanning(samples.size)
        magnitudes = np.abs(np.fft.rfft(windowed))

        frequencies = np.fft.rfftfreq(
            samples.size,
            d=1.0 / SAMPLE_RATE,
        )

        # 48 frequency bands, from 80 Hz to 7.5 kHz
        edges = np.geomspace(
            80.0, 7500.0, BAR_COUNT + 1
        )

        bands = []

        for i in range(BAR_COUNT):
            mask = (
                (frequencies >= edges[i])
                & (frequencies < edges[i + 1])
            )

            if np.any(mask):
                value = float(
                    np.sqrt(np.mean(magnitudes[mask] ** 2))
                )
            else:
                value = 0.0

            # Compress values for smoother animation
            bar_level = math.sqrt(value) * 0.16
            bar_level *= 0.18 + activity

            bands.append(min(1.0, bar_level))

        # Keep the microphone's local measurements
        with self._audio_lock:
            self._audio_level = activity
            self._target_spectrum = bands[:]

        # Publish microphone measurements to shared state
        set_audio_state(
            source="microphone",
            level=activity,
            spectrum=bands,
        )

    def _animate(self):
        """Animate using microphone or Spidey's playback audio."""
        should_be_visible = get_orb_visibility()

        if should_be_visible and not self.isVisible():
            screen = QApplication.primaryScreen()
            if screen:
                area = screen.availableGeometry()
                self.move(
                    area.center().x() - self.width() // 2,
                    area.center().y() - self.height() // 2,
                )
            self.show_orb()

        elif not should_be_visible and self.isVisible():
            self.hide()
        self._phase = (
            self._phase + 0.045
        ) % (2 * math.pi)

        shared_audio = get_audio_state()

        if shared_audio["source"] == "spidey":
            # Use spectrum calculated from actual Piper output
            level = shared_audio["level"]
            targets = shared_audio["spectrum"]
            self._state = "SPEAKING"
        else:
            # Use the microphone when Spidey is not speaking
            with self._audio_lock:
                level = self._audio_level
                targets = self._target_spectrum[:]

            if self._audio_error:
                self._state = "MIC ERROR"
            elif level > 0.055:
                self._state = "LISTENING"
            else:
                self._state = "IDLE"

        self._display_level = level

        # Smooth the spectrum bars
        for i, value in enumerate(self._spectrum):
            target = 0.02 + targets[i] * 0.95
            self._spectrum[i] = (
                value * 0.52 + target * 0.48
            )

        self.update()

    def paintEvent(self, event):
        del event

        painter = QPainter(self)

        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing, True
        )

        cx = self.width() / 2
        cy = self.height() / 2

        level = self._display_level

        # Sphere pulses with the selected audio source
        radius = 57 * (
            1.0
            + 0.035 * level
            + 0.012 * math.sin(self._phase)
        )

        # Outer cyan glow
        glow = QRadialGradient(cx, cy, 108)
        glow.setColorAt(0.0, QColor(0, 150, 255, 72))
        glow.setColorAt(0.55, QColor(0, 100, 255, 32))
        glow.setColorAt(1.0, QColor(0, 60, 180, 0))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)

        painter.drawEllipse(
            QPoint(int(cx), int(cy)), 108, 108
        )

        # Circular audio spectrum
        for i, value in enumerate(self._spectrum):
            angle = (
                2 * math.pi * i / BAR_COUNT
            ) - math.pi / 2

            inner_r = 76
            outer_r = inner_r + 3 + value * 30

            x1 = cx + math.cos(angle) * inner_r
            y1 = cy + math.sin(angle) * inner_r
            x2 = cx + math.cos(angle) * outer_r
            y2 = cy + math.sin(angle) * outer_r

            mix = i / max(1, BAR_COUNT - 1)

            if mix < 0.5:
                color = QColor(
                    25, 190 + int(mix * 100), 255, 225
                )
            else:
                color = QColor(
                    0, 155 + int((1 - mix) * 80), 255, 225
                )

            painter.setPen(
                QPen(
                    color,
                    2.2,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                )
            )

            painter.drawLine(
                int(x1), int(y1), int(x2), int(y2)
            )

        # Rotating orbital rings
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(math.degrees(self._phase))
        painter.setBrush(Qt.BrushStyle.NoBrush)

        painter.setPen(
            QPen(QColor(40, 205, 255, 125), 1.3)
        )
        painter.drawEllipse(-68, -61, 136, 122)

        painter.setPen(
            QPen(QColor(20, 120, 255, 165), 1.1)
        )
        painter.drawEllipse(-73, -47, 146, 94)

        painter.restore()

        # Main glass-like sphere
        sphere = QRadialGradient(
            cx - 20, cy - 24, radius * 1.55
        )

        sphere.setColorAt(
            0.0, QColor(80, 225, 255, 245)
        )
        sphere.setColorAt(
            0.28, QColor(15, 125, 255, 250)
        )
        sphere.setColorAt(
            0.68, QColor(3, 48, 145, 250)
        )
        sphere.setColorAt(
            1.0, QColor(0, 14, 55, 250)
        )

        painter.setBrush(sphere)
        painter.setPen(
            QPen(QColor(80, 230, 255, 235), 2)
        )

        painter.drawEllipse(
            QPoint(int(cx), int(cy)),
            int(radius),
            int(radius),
        )

        # Inner highlight
        highlight = QLinearGradient(
            cx - 28, cy - 48, cx + 30, cy + 45
        )

        highlight.setColorAt(
            0.0, QColor(170, 250, 255, 125)
        )
        highlight.setColorAt(
            0.35, QColor(35, 160, 255, 45)
        )
        highlight.setColorAt(
            1.0, QColor(0, 20, 100, 5)
        )

        painter.setBrush(highlight)
        painter.setPen(
            QPen(QColor(90, 220, 255, 100), 1)
        )

        painter.drawEllipse(
            QPoint(int(cx), int(cy)),
            int(radius - 5),
            int(radius - 5),
        )

        # Luminous core
        core = QRadialGradient(cx, cy, 19)

        core.setColorAt(
            0.0, QColor(220, 255, 255, 250)
        )
        core.setColorAt(
            0.3, QColor(45, 230, 255, 240)
        )
        core.setColorAt(
            1.0, QColor(0, 145, 255, 0)
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(core)

        painter.drawEllipse(
            QPoint(int(cx), int(cy)), 19, 19
        )

        # Moving spark
        spark_angle = self._phase * 1.7

        sx = cx + math.cos(spark_angle) * 72
        sy = cy + math.sin(spark_angle) * 56

        painter.setBrush(
            QColor(155, 250, 255, 235)
        )

        painter.drawEllipse(
            QPoint(int(sx), int(sy)), 3, 3
        )

        # Status label
        painter.setPen(
            QPen(QColor(140, 225, 255, 210), 1)
        )

        painter.drawText(
            0,
            self.height() - 8,
            self.width(),
            18,
            Qt.AlignmentFlag.AlignHCenter,
            self._state,
        )

        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint()
                - self.frameGeometry().topLeft()
            )
            event.accept()

        elif event.button() == Qt.MouseButton.RightButton:
            self._show_menu(
                event.globalPosition().toPoint()
            )
            event.accept()

    def mouseMoveEvent(self, event):
        if (
            self._drag_offset is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            self.move(
                event.globalPosition().toPoint()
                - self._drag_offset
            )
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = None
            event.accept()

    def show_orb(self):
        """Show the orb and bring it to the front."""
        self.show()
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _tray_activated(self, reason):
        """Show the orb when the tray icon is double-clicked."""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_orb()

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
            QMenu::item {
                padding: 7px 24px;
            }
            QMenu::item:selected {
                background-color: #0b4770;
            }
            """
        )

        title = QAction(
            "Spidey AI - Audio Spectrum", self
        )
        title.setEnabled(False)

        menu.addAction(title)
        menu.addSeparator()

        hide_action = QAction("Hide orb", self)
        hide_action.triggered.connect(self.hide)
        menu.addAction(hide_action)

        quit_action = QAction("Exit preview", self)
        quit_action.triggered.connect(
            QApplication.instance().quit
        )
        menu.addAction(quit_action)

        menu.exec(global_position)

    def closeEvent(self, event):
        """Release the microphone when the orb exits."""
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass

        self.tray.hide()
        event.accept()
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Spidey AI Orb")

    # Keep the app running when the orb is hidden.
    app.setQuitOnLastWindowClosed(False)

    orb = SpideyOrb()
    # Start hidden; Spidey will show the orb when activated.

    sys.exit(app.exec())
    
if __name__ == "__main__":
    main()

