import sys
import json
import urllib.request
import urllib.error
from pathlib import Path

import sounddevice as sd
import numpy as np
from faster_whisper import WhisperModel
from piper import PiperVoice

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QLineEdit,
    QPushButton,
    QCheckBox,
    QLabel,
    QSystemTrayIcon,
    QMenu,
    QMessageBox,
    QStyle,
)

from app.memory.store import MemoryStore


OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "qwen2.5:3b"

PROJECT_DIR = Path(__file__).resolve().parent.parent
VOSK_MODEL_PATH = (
    PROJECT_DIR / "vosk-model-small-en-us-0.15" / "vosk-model-small-en-us-0.15"
)

SAMPLE_RATE = 16000
RECORD_SECONDS = 5
MICROPHONE_ID = 1

WHISPER_MODEL = None
PIPER_MODEL_PATH = PROJECT_DIR / "voice_models" / "en_US-lessac-medium.onnx"
PIPER_VOICE = None


SYSTEM_PROMPT = """
You are Spidey, a helpful local Windows AI assistant.
You can chat and answer questions using your local AI model.
You do not yet have tools to control Windows.
Never claim to have performed an action unless a connected tool
actually performed and verified that action.
"""


class AIWorker(QThread):
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, messages):
        super().__init__()
        self.messages = [dict(message) for message in messages]

    def run(self):
        try:
            payload = {
                "model": MODEL_NAME,
                "messages": self.messages,
                "stream": False,
            }

            request = urllib.request.Request(
                OLLAMA_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(request, timeout=180) as response:
                result = json.loads(response.read().decode("utf-8"))

            reply = result.get("message", {}).get("content", "").strip()
            if not reply:
                raise ValueError("Ollama returned an empty response.")

            self.succeeded.emit(reply)

        except (urllib.error.URLError, TimeoutError) as exc:
            self.failed.emit(
                "Could not connect to Ollama or the request timed out.\n"
                f"Details: {exc}"
            )
        except Exception as exc:
            self.failed.emit(f"AI request failed: {exc}")


class VoiceWorker(QThread):
    recognized = Signal(str)
    failed = Signal(str)

    def run(self):
        global WHISPER_MODEL

        try:
            if WHISPER_MODEL is None:
                print("Loading Faster-Whisper model...")
                WHISPER_MODEL = WhisperModel(
                    "small",
                    device="cpu",
                    compute_type="int8",
                )

            audio = sd.rec(
                int(RECORD_SECONDS * SAMPLE_RATE),
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="int16",
                device=MICROPHONE_ID,
            )
            sd.wait()

            audio_float = audio.reshape(-1).astype(np.float32) / 32768.0
            segments, _info = WHISPER_MODEL.transcribe(
                audio_float,
                language="en",
                beam_size=5,
                vad_filter=True,
            )

            text = " ".join(segment.text.strip() for segment in segments).strip()
            if text:
                self.recognized.emit(text)
            else:
                self.failed.emit(
                    "No words recognized. Please speak clearly "
                    "and closer to the microphone."
                )

        except Exception as exc:
            self.failed.emit(f"Voice input failed: {exc}")


class SpeechWorker(QThread):
    """Generate and play speech without freezing the chat window."""

    failed = Signal(str)

    def __init__(self, text):
        super().__init__()
        self.text = text

    def run(self):
        global PIPER_VOICE

        try:
            if not PIPER_MODEL_PATH.is_file():
                raise FileNotFoundError(
                    f"Piper voice model not found: {PIPER_MODEL_PATH}"
                )

            if PIPER_VOICE is None:
                PIPER_VOICE = PiperVoice.load(str(PIPER_MODEL_PATH))

            chunks = list(PIPER_VOICE.synthesize(self.text))
            if not chunks:
                return

            audio_data = np.concatenate(
                [chunk.audio_int16_array for chunk in chunks]
            )
            sd.play(audio_data, samplerate=PIPER_VOICE.config.sample_rate)
            sd.wait()

        except Exception as exc:
            self.failed.emit(f"Speech error: {exc}")


class SpideyWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Spidey AI")
        self.resize(850, 620)

        self.memory = MemoryStore()
        self.worker = None
        self.voice_worker = None
        self.speech_worker = None
        self.pending_voice_send = False
        self.allow_quit = False

        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        central = QWidget()
        layout = QVBoxLayout(central)

        title = QLabel("SPIDEY AI")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 26px; font-weight: bold; padding: 8px;")

        subtitle = QLabel(
            "Local AI assistant · Ollama · SQLite memory · Offline voice"
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.chat = QTextEdit()
        self.chat.setReadOnly(True)
        self.chat.append(
            "Spidey: Hello! I'm running locally.\n\n"
            "Memory commands:\n"
            "remember: project_name = Spidey AI\n"
            "recall: project_name\n"
            "memories\n"
            "forget: project_name\n\n"
            "Click Listen to dictate a message. "
            "Review the recognized text before sending.\n"
            "AI replies will be spoken aloud.\n"
            "Closing this window hides Spidey in the system tray."
        )

        self.input = QLineEdit()
        self.input.setPlaceholderText("Message Spidey...")
        self.input.returnPressed.connect(self.send_message)

        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send_message)

        self.listen_button = QPushButton("Listen")
        self.listen_button.clicked.connect(self.listen_to_microphone)

        self.voice_command_checkbox = QCheckBox("Voice Command")
        self.voice_command_checkbox.setChecked(False)

        self.new_chat_button = QPushButton("New Chat")
        self.new_chat_button.clicked.connect(self.new_chat)

        input_row = QHBoxLayout()
        input_row.addWidget(self.input, 1)
        input_row.addWidget(self.send_button)
        input_row.addWidget(self.listen_button)
        input_row.addWidget(self.voice_command_checkbox)
        input_row.addWidget(self.new_chat_button)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.chat, 1)
        layout.addLayout(input_row)
        self.setCentralWidget(central)

        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f7fb;
            }
            QTextEdit, QLineEdit {
                background-color: white;
                border: 1px solid #d5dbe5;
                border-radius: 8px;
                padding: 10px;
                font-size: 14px;
            }
            QPushButton {
                background-color: #2457d6;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 14px;
                font-weight: bold;
            }
            QPushButton:disabled {
                background-color: #a0aec0;
            }
        """)

        self.setup_tray()

    def setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.setWindowIcon(icon)
        self.tray.setIcon(icon)
        self.tray.setToolTip("Spidey AI")

        menu = QMenu(self)
        show_action = QAction("Show Spidey", self)
        show_action.triggered.connect(self.show_window)
        hide_action = QAction("Hide Spidey", self)
        hide_action.triggered.connect(self.hide)
        quit_action = QAction("Quit Spidey", self)
        quit_action.triggered.connect(self.quit_application)

        menu.addAction(show_action)
        menu.addAction(hide_action)
        menu.addSeparator()
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_window()

    def show_window(self):
        self.show()
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_application(self):
        self.allow_quit = True
        self.tray.hide()
        QApplication.quit()

    def closeEvent(self, event):
        if self.allow_quit:
            event.accept()
        else:
            event.ignore()
            self.hide()
            self.tray.showMessage(
                "Spidey AI",
                "Spidey is still running in the system tray.",
                QSystemTrayIcon.MessageIcon.Information,
                2500,
            )

    def listen_to_microphone(self):
        if self.voice_worker is not None:
            return

        if self.worker is not None and self.worker.isRunning():
            self.chat.append("Spidey: Wait for the current response before recording.")
            return

        self.pending_voice_send = False
        self.listen_button.setEnabled(False)
        self.listen_button.setText("Listening...")
        self.chat.append(
            f"\nSpidey: Listening for {RECORD_SECONDS} seconds. Speak now..."
        )

        self.voice_worker = VoiceWorker()
        self.voice_worker.recognized.connect(self.on_voice_recognized)
        self.voice_worker.failed.connect(self.on_voice_error)
        self.voice_worker.finished.connect(self.on_voice_finished)
        self.voice_worker.start()

    def on_voice_recognized(self, text):
        self.input.setText(text)
        self.input.setFocus()
        self.chat.append(f"Spidey: Recognized: {text}")

        if self.voice_command_checkbox.isChecked():
            self.pending_voice_send = True

    def on_voice_error(self, error):
        self.chat.append(f"Spidey voice: {error}")

    def on_voice_finished(self):
        self.listen_button.setText("Listen")
        self.listen_button.setEnabled(True)
        self.voice_worker = None

        # Send only after the recording thread has fully finished.
        if self.pending_voice_send:
            self.pending_voice_send = False
            self.send_message()

    def handle_memory_command(self, message):
        text = message.strip()

        if text.lower().startswith("remember:"):
            content = text[len("remember:"):].strip()
            if "=" not in content:
                return "Use: remember: project_name = Spidey AI"

            key, value = content.split("=", 1)
            key = key.strip()
            value = value.strip()

            try:
                self.memory.save(key, value)
                return f"Saved memory: {key} = {value}"
            except (ValueError, OSError) as exc:
                return f"Could not save memory: {exc}"

        if text.lower().startswith("recall:"):
            key = text[len("recall:"):].strip()
            if not key:
                return "Please provide a memory key."

            value = self.memory.get(key)
            return (
                f"{key} = {value}"
                if value is not None
                else f"No saved memory found for '{key}'."
            )

        if text.lower() == "memories":
            saved = self.memory.list_all()
            if not saved:
                return "No saved memories yet."

            return "\n".join(
                f"{item['memory_key']} = {item['memory_value']}"
                for item in saved
            )

        if text.lower().startswith("forget:"):
            key = text[len("forget:"):].strip()
            if not key:
                return "Please provide a memory key."

            if self.memory.delete(key):
                return f"Deleted saved memory: {key}"

            return f"No saved memory found for '{key}'."

        return None

    def send_message(self):
        message = self.input.text().strip()
        if not message:
            return

        if self.worker is not None and self.worker.isRunning():
            return

        if self.voice_worker is not None:
            self.chat.append("Spidey: Wait for voice recording to finish first.")
            return

        self.input.clear()
        self.chat.append(f"\nYou: {message}")

        memory_reply = self.handle_memory_command(message)
        if memory_reply is not None:
            self.chat.append(f"\nSpidey: {memory_reply}")
            self.speak_reply(memory_reply)
            return

        saved = self.memory.list_all()
        memory_context = ""
        if saved:
            memory_context = "\nSaved facts:\n" + "\n".join(
                f"- {item['memory_key']}: {item['memory_value']}"
                for item in saved
            )

        request_messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT + memory_context,
            }
        ]
        request_messages.extend(self.messages[1:])
        request_messages.append({"role": "user", "content": message})

        self.messages.append({"role": "user", "content": message})

        self.send_button.setEnabled(False)
        self.new_chat_button.setEnabled(False)
        self.listen_button.setEnabled(False)
        self.input.setEnabled(False)
        self.chat.append("Spidey: Thinking...")

        self.worker = AIWorker(request_messages)
        self.worker.succeeded.connect(self.on_ai_success)
        self.worker.failed.connect(self.on_ai_error)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()

    def on_ai_success(self, reply):
        self.messages.append({"role": "assistant", "content": reply})
        self.chat.append(f"\nSpidey: {reply}")
        self.speak_reply(reply)

    def speak_reply(self, text):
        if self.speech_worker is not None and self.speech_worker.isRunning():
            self.chat.append("Spidey voice: Previous speech is still playing.")
            return

        self.speech_worker = SpeechWorker(text)
        self.speech_worker.failed.connect(
            lambda error: self.chat.append(f"Spidey voice: {error}")
        )
        self.speech_worker.finished.connect(self.on_speech_finished)
        self.speech_worker.start()

    def on_speech_finished(self):
        self.speech_worker = None

    def on_ai_error(self, error):
        if self.messages and self.messages[-1]["role"] == "user":
            self.messages.pop()
        self.chat.append(f"\nSpidey error: {error}")

    def on_worker_finished(self):
        self.send_button.setEnabled(True)
        self.new_chat_button.setEnabled(True)
        self.listen_button.setEnabled(True)
        self.input.setEnabled(True)
        self.input.setFocus()
        self.worker = None

    def new_chat(self):
        if self.worker is not None and self.worker.isRunning():
            return

        if self.voice_worker is not None:
            return

        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.chat.clear()
        self.chat.append("Spidey: New chat started. Saved SQLite memories remain.")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Spidey AI")

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.warning(
            None,
            "System tray unavailable",
            "Windows reports that the system tray is unavailable. "
            "Spidey will still open, but tray behavior may not work.",
        )

    window = SpideyWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
