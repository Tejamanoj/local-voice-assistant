
import sys
import json
import urllib.request
import urllib.error

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
    QLabel,
    QSystemTrayIcon,
    QMenu,
    QMessageBox,
    QStyle,
)

from app.memory.store import MemoryStore


OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "qwen2.5:3b"

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


class SpideyWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Spidey AI")
        self.resize(850, 620)

        self.memory = MemoryStore()
        self.worker = None
        self.allow_quit = False

        self.messages = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

        central = QWidget()
        layout = QVBoxLayout(central)

        title = QLabel("SPIDEY AI")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "font-size: 26px; font-weight: bold; padding: 8px;"
        )

        subtitle = QLabel("Local AI assistant · Ollama · SQLite memory")
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
            "Closing this window hides Spidey in the system tray."
        )

        self.input = QLineEdit()
        self.input.setPlaceholderText("Message Spidey...")
        self.input.returnPressed.connect(self.send_message)

        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send_message)

        self.new_chat_button = QPushButton("New Chat")
        self.new_chat_button.clicked.connect(self.new_chat)

        input_row = QHBoxLayout()
        input_row.addWidget(self.input, 1)
        input_row.addWidget(self.send_button)
        input_row.addWidget(self.new_chat_button)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.chat, 1)
        layout.addLayout(input_row)

        self.setCentralWidget(central)

        self.setStyleSheet("""
            QMainWindow { background-color: #f5f7fb; }
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
            QPushButton:disabled { background-color: #a0aec0; }
        """)

        self.setup_tray()

    def setup_tray(self):
        self.tray = QSystemTrayIcon(self)

        icon = self.style().standardIcon(
            QStyle.StandardPixmap.SP_ComputerIcon
        )
        self.setWindowIcon(icon)
        self.tray.setIcon(icon)
        self.tray.setToolTip("Spidey AI")

        menu = QMenu()

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

    def handle_memory_command(self, message):
        text = message.strip()

        if text.lower().startswith("remember:"):
            content = text[len("remember:"):].strip()

            if "=" not in content:
                return "Use: remember: project_name = Spidey AI"

            key, value = content.split("=", 1)

            try:
                self.memory.save(key, value)
                return f"Saved memory: {key.strip()} = {value.strip()}"
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

        if not message or (
            self.worker is not None and self.worker.isRunning()
        ):
            return

        self.input.clear()
        self.chat.append(f"\nYou: {message}")

        memory_reply = self.handle_memory_command(message)

        if memory_reply is not None:
            self.chat.append(f"\nSpidey: {memory_reply}")
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
        request_messages.append({
            "role": "user",
            "content": message,
        })

        self.messages.append({"role": "user", "content": message})

        self.send_button.setEnabled(False)
        self.new_chat_button.setEnabled(False)
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

    def on_ai_error(self, error):
        if self.messages and self.messages[-1]["role"] == "user":
            self.messages.pop()
        self.chat.append(f"\nSpidey error: {error}")

    def on_worker_finished(self):
        self.send_button.setEnabled(True)
        self.new_chat_button.setEnabled(True)
        self.input.setEnabled(True)
        self.input.setFocus()
        self.worker = None

    def new_chat(self):
        if self.worker is not None and self.worker.isRunning():
            return

        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.chat.clear()
        self.chat.append(
            "Spidey: New chat started. Saved SQLite memories remain."
        )


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
