
import sys
import json
import urllib.request
import urllib.error

from PySide6.QtCore import Qt, QThread, Signal
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
)

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "qwen2.5:3b"

SYSTEM_PROMPT = """
You are Spidey, a helpful local Windows AI assistant.

Rules:
- Remember relevant information from earlier messages in this chat.
- Be honest about what you can and cannot do.
- Never claim to have performed a computer action unless a connected
  tool actually performed and verified that action.
- For now, you can chat, explain, and answer questions. You do not
  yet have tools to control Windows.
- Keep answers clear and useful.
"""


class AIWorker(QThread):
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, messages):
        super().__init__()
        self.messages = messages.copy()

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

        except urllib.error.URLError as exc:
            self.failed.emit(
                "Could not connect to Ollama. Check that Ollama is running.\n"
                f"Details: {exc}"
            )
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            self.failed.emit(f"Could not process the AI response: {exc}")
        except Exception as exc:
            self.failed.emit(f"Unexpected error: {exc}")


class SpideyWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Spidey AI")
        self.resize(800, 600)

        self.messages = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

        self.worker = None

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("SPIDEY AI")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "font-size: 25px; font-weight: bold; padding: 8px;"
        )

        subtitle = QLabel("Local AI assistant · Powered by Ollama")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: gray;")

        self.chat = QTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setPlaceholderText("Your conversation appears here.")
        self.chat.append(
            "Spidey: Hello! I'm connected to your local AI model. "
            "I can chat with you and remember earlier messages "
            "while this window remains open."
        )

        self.input = QLineEdit()
        self.input.setPlaceholderText("Type a message...")
        self.input.returnPressed.connect(self.send_message)

        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send_message)

        self.clear_button = QPushButton("New Chat")
        self.clear_button.clicked.connect(self.new_chat)

        input_row = QHBoxLayout()
        input_row.addWidget(self.input, 1)
        input_row.addWidget(self.send_button)
        input_row.addWidget(self.clear_button)

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
                padding: 10px 16px;
                font-weight: bold;
            }
            QPushButton:disabled {
                background-color: #a0aec0;
            }
        """)

    def send_message(self):
        message = self.input.text().strip()

        if not message or (
            self.worker is not None and self.worker.isRunning()
        ):
            return

        self.input.clear()
        self.chat.append(f"\nYou: {message}")

        self.messages.append({
            "role": "user",
            "content": message,
        })

        self.send_button.setEnabled(False)
        self.clear_button.setEnabled(False)
        self.input.setEnabled(False)

        self.chat.append("Spidey: Thinking...")

        # Copy the complete conversation, including prior turns.
        self.worker = AIWorker(self.messages)
        self.worker.succeeded.connect(self.on_ai_success)
        self.worker.failed.connect(self.on_ai_error)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()

    def on_ai_success(self, reply):
        self.messages.append({
            "role": "assistant",
            "content": reply,
        })

        self.chat.append(f"\nSpidey: {reply}")

    def on_ai_error(self, error):
        # Remove the latest user message so a failed request doesn't
        # leave an unmatched turn in the conversation history.
        if (
            self.messages
            and self.messages[-1]["role"] == "user"
        ):
            self.messages.pop()

        self.chat.append(f"\nSpidey error: {error}")

    def on_worker_finished(self):
        self.send_button.setEnabled(True)
        self.clear_button.setEnabled(True)
        self.input.setEnabled(True)
        self.input.setFocus()
        self.worker = None

    def new_chat(self):
        if self.worker is not None and self.worker.isRunning():
            return

        self.messages = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

        self.chat.clear()
        self.chat.append(
            "Spidey: New conversation started. "
            "Previous chat history has been cleared from this session."
        )


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Spidey AI")

    window = SpideyWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
