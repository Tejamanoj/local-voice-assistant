
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

from app.memory.store import MemoryStore


OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "qwen2.5:3b"

SYSTEM_PROMPT = """
You are Spidey, a helpful local Windows AI assistant.

Be clear and honest about your capabilities.
You can chat and answer questions using your local AI model.
You do not yet have tools to control Windows or execute computer actions.

Conversation history is provided during the current chat session.
Some explicitly saved facts may be provided as additional context.

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
        self.resize(850, 620)

        self.memory = MemoryStore()
        self.worker = None

        self.messages = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("SPIDEY AI")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "font-size: 26px; font-weight: bold; padding: 8px;"
        )

        subtitle = QLabel(
            "Local AI assistant · Ollama · Persistent local memory"
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: gray;")

        self.chat = QTextEdit()
        self.chat.setReadOnly(True)
        self.chat.append(
            "Spidey: Hello! I'm running locally.\n\n"
            "You can chat with me or use these memory commands:\n"
            "• remember: project_name = Spidey AI\n"
            "• recall: project_name\n"
            "• memories\n"
            "• forget: project_name"
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

    def handle_memory_command(self, message):
        text = message.strip()

        if text.lower().startswith("remember:"):
            content = text[len("remember:"):].strip()

            if "=" not in content:
                return (
                    "Use this format: "
                    "remember: project_name = Spidey AI"
                )

            key, value = content.split("=", 1)

            try:
                self.memory.save(key, value)
                return f"Saved memory: {key.strip()} = {value.strip()}"
            except (ValueError, OSError) as exc:
                return f"Could not save memory: {exc}"

        if text.lower().startswith("recall:"):
            key = text[len("recall:"):].strip()

            if not key:
                return "Please provide a key after 'recall:'."

            value = self.memory.get(key)

            if value is None:
                return f"No saved memory found for '{key}'."

            return f"{key} = {value}"

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
                return "Please provide a key after 'forget:'."

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

        self.input.clear()
        self.chat.append(f"\nYou: {message}")

        # Handle explicit memory operations locally.
        memory_reply = self.handle_memory_command(message)

        if memory_reply is not None:
            self.chat.append(f"\nSpidey: {memory_reply}")
            return

        # Include saved facts as context for normal AI questions.
        saved_memories = self.memory.list_all()

        memory_context = ""
        if saved_memories:
            memory_context = (
                "\n\nSaved user facts for context:\n"
                + "\n".join(
                    f"- {item['memory_key']}: {item['memory_value']}"
                    for item in saved_memories
                )
                + "\nUse these facts when relevant, but do not claim "
                  "they came from the current chat."
            )

        request_messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT + memory_context,
            }
        ]

        # Keep conversation history separate from memory context.
        request_messages.extend(self.messages[1:])
        request_messages.append({
            "role": "user",
            "content": message,
        })

        self.send_button.setEnabled(False)
        self.new_chat_button.setEnabled(False)
        self.input.setEnabled(False)
        self.chat.append("Spidey: Thinking...")

        self.worker = AIWorker(request_messages)
        self.worker.succeeded.connect(self.on_ai_success)
        self.worker.failed.connect(self.on_ai_error)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()

        # Add the user message to session history after launching.
        self.messages.append({
            "role": "user",
            "content": message,
        })

    def on_ai_success(self, reply):
        self.messages.append({
            "role": "assistant",
            "content": reply,
        })
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

        self.messages = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

        self.chat.clear()
        self.chat.append(
            "Spidey: New conversation started. "
            "Saved SQLite memories remain available."
        )


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Spidey AI")

    window = SpideyWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
