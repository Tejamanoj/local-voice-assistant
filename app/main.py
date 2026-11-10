import time
import subprocess
from pathlib import Path
import sys
from datetime import datetime
import json
import urllib.request
import urllib.error
from pathlib import Path

import sounddevice as sd
import numpy as np
from faster_whisper import WhisperModel
from openwakeword.model import Model
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

from app.ui.audio_state import (
    set_audio_state,
    set_orb_visibility,
)
from app.memory.store import MemoryStore
from app.tools.registry import execute_tool


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "qwen2.5:3b"

PROJECT_DIR = Path(__file__).resolve().parent.parent

SAMPLE_RATE = 16000
RECORD_SECONDS = 5
MICROPHONE_ID = 1  # Use Windows default input device

WHISPER_MODEL = None
PIPER_VOICE = None

PIPER_MODEL_PATH = (
    PROJECT_DIR / "voice_models" / "en_US-lessac-medium.onnx"
)

WAKE_THRESHOLD = 0.50
WAKE_RESET_THRESHOLD = 0.10
WAKE_RESET_FRAMES_REQUIRED = 20
WAKE_COOLDOWN_SECONDS = 3.0


SYSTEM_PROMPT = """
You are Spidey, a capable personal AI assistant running locally on Windows.

YOUR PERSONALITY
- Be friendly, natural, helpful, and conversational.
- Communicate like an intelligent assistant, not a scripted chatbot.
- Give direct answers first, then explain when necessary.
- Adapt your response length to the user's request.

UNDERSTANDING
- Understand ordinary real-life language, including informal wording,
  spelling mistakes, and imperfect voice transcription.
- Identify the user's actual intent instead of matching isolated keywords.
- Use the conversation history to understand references and follow-up
  questions such as "what about tomorrow?" or "do that again".
- Ask a concise clarification question when essential information is missing.

ACCURACY
- Never invent dates, times, current events, personal memories, or facts.
- If you do not know something, say so clearly.
- Distinguish verified information from assumptions.
- For questions involving current information, recognize when external
  information is needed rather than presenting outdated knowledge as current.
- Use the actual output of connected tools when available.

TOOLS AND ACTIONS
- Use a connected tool when a request requires information or an action
  that cannot reliably be handled by language generation alone.
- Follow the tool's documented inputs and outputs.
- Never claim to have opened an application, changed a setting, searched
  the web, accessed a file, or completed a task unless a connected tool
  actually performed that action.
- Verify important actions before reporting success.
- Ask for confirmation before destructive, sensitive, or irreversible actions.

MEMORY
- Use relevant saved memories and conversation history when provided.
- Do not claim to remember information that is not available.
- Respect requests to update or forget saved information.

PROBLEM SOLVING
- Break complex requests into manageable steps.
- Explain limitations honestly.
- When performing a task, plan the steps, execute available actions,
  and verify the outcome.
- Do not expose private internal reasoning. Provide a concise explanation
  of conclusions and decisions when useful.

IMPORTANT LIMITATION
Your capabilities depend on the tools actually connected to you.
A system prompt does not grant access to Windows controls, files, the
internet, or other applications by itself.
"""


# --------------------------------------------------
# AI WORKER
# --------------------------------------------------


class AIWorker(QThread):
    succeeded = Signal(str)
    failed = Signal(str)

    MAX_TOOL_ROUNDS = 5

    TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "get_current_time",
                "description": "Get the computer's current local time.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_current_date",
                "description": "Get today's local date.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_tomorrow_date",
                "description": "Get tomorrow's date.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_yesterday_date",
                "description": "Get yesterday's date.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_system_info",
                "description": (
                    "Get actual information about the Windows computer "
                    "and its hardware."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_battery_status",
                "description": (
                    "Get the actual battery percentage and charging status "
                    "of the computer. Use this whenever the user asks "
                    "about battery level, battery percentage, or charging."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "open_notepad",
                "description": "Open Windows Notepad when requested.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "open_calculator",
                "description": "Open Windows Calculator when requested.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
                {
            "type": "function",
            "function": {
                "name": "open_youtube_in_brave",
                "description": (
                    "Immediately open YouTube in Brave when the user asks "
                    "to open YouTube in Brave. Execute the tool instead of "
                    "giving instructions."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "open_youtube",
                "description": (
                    "Immediately open YouTube in the default browser "
                    "when requested."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
    ]

    def __init__(self, messages):
        super().__init__()
        self.messages = [dict(message) for message in messages]

    def run(self):
        import time

        try:
            messages = [dict(message) for message in self.messages]
            total_start = time.perf_counter()

            for round_number in range(self.MAX_TOOL_ROUNDS):
                
                payload = {
                    "model": MODEL_NAME,
                    "messages": messages,
                    "tools": self.TOOLS,
                    "stream": False,
                    "options": {
                        "num_predict": 256,
                    },
                }

                request = urllib.request.Request(
                    OLLAMA_URL,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )

                request_start = time.perf_counter()

                with urllib.request.urlopen(
                    request, timeout=180
                ) as response:
                    result = json.loads(
                        response.read().decode("utf-8")
                    )

                request_seconds = time.perf_counter() - request_start
                print(
                    f"[Spidey Timing] Ollama request "
                    f"{round_number + 1}: {request_seconds:.2f}s"
                )

                assistant_message = result.get("message", {})
                tool_calls = assistant_message.get("tool_calls", [])

                if not tool_calls:
                    reply = assistant_message.get(
                        "content", ""
                    ).strip()

                    if not reply:
                        raise ValueError(
                            "Ollama returned an empty response."
                        )

                    print(
                        f"[Spidey Timing] Total AI time: "
                        f"{time.perf_counter() - total_start:.2f}s"
                    )

                    self.succeeded.emit(reply)
                    return

                messages.append(assistant_message)

                for tool_call in tool_calls:
                    function_info = tool_call.get("function", {})
                    tool_name = function_info.get("name", "")

                    if not tool_name:
                        tool_result = "Tool call rejected: missing name."
                    else:
                        try:
                            arguments = function_info.get(
                                "arguments", {}
                            )

                            if not isinstance(arguments, dict):
                                raise ValueError(
                                    "Tool arguments must be an object."
                                )

                            if arguments:
                                raise ValueError(
                                    "This tool does not accept arguments."
                                )

                            tool_start = time.perf_counter()
                            tool_result = execute_tool(tool_name)

                            print(
                                f"[Spidey Timing] Tool '{tool_name}': "
                                f"{time.perf_counter() - tool_start:.2f}s"
                            )

                        except Exception as exc:
                            tool_result = f"Tool execution failed: {exc}"

                    messages.append({
                        "role": "tool",
                        "name": tool_name or "unknown_tool",
                        "content": str(tool_result),
                    })

            raise RuntimeError(
                "Spidey reached the maximum number of tool calls "
                "without receiving a final answer."
            )

        except (urllib.error.URLError, TimeoutError) as exc:
            self.failed.emit(
                "Could not connect to Ollama or the request timed out.\n"
                f"Details: {exc}"
            )

        except Exception as exc:
            self.failed.emit(f"AI request failed: {exc}")


# --------------------------------------------------
# WAKE-WORD WORKER
# --------------------------------------------------


class WakeWordWorker(QThread):
    wake_detected = Signal()
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self._stop_requested = False

    def stop(self):
        self._stop_requested = True
        self.requestInterruption()

    def run(self):
        try:
            model = Model(
                wakeword_models=["hey_jarvis"],
                inference_framework="onnx",
            )

            block_size = 1280
            armed = True
            low_score_frames = 0
            last_detection_time = 0.0

            import time

            print("Spidey is listening for 'Hey Jarvis'.")

            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=block_size,
                device=MICROPHONE_ID,
            ) as stream:

                while (
                    not self._stop_requested
                    and not self.isInterruptionRequested()
                ):
                    audio, overflowed = stream.read(block_size)

                    if overflowed:
                        print("Wake listener: microphone buffer overflow.")

                    scores = model.predict(audio.reshape(-1))
                    score = float(scores.get("hey_jarvis", 0.0))
                    if not hasattr(self, "_last_debug_time"):
                        self._last_debug_time = 0.0

                    debug_now = time.monotonic()

                    if debug_now - self._last_debug_time >= 2.0:
                        print(
                            f"Wake score: {score:.3f} | "
                            f"Threshold: {WAKE_THRESHOLD:.2f}"
                        )
                        self._last_debug_time = debug_now
                    now = time.monotonic()

                    if armed:
                        if (
                            score >= WAKE_THRESHOLD
                            and now - last_detection_time
                            >= WAKE_COOLDOWN_SECONDS
                        ):
                            print(
                                f"Wake phrase detected: {score:.3f}"
                            )

                            last_detection_time = now
                            armed = False
                            low_score_frames = 0

                            self.wake_detected.emit()
                            return

                    else:
                        if score < WAKE_RESET_THRESHOLD:
                            low_score_frames += 1
                        else:
                            low_score_frames = 0

                        if (
                            low_score_frames
                            >= WAKE_RESET_FRAMES_REQUIRED
                        ):
                            armed = True
                            low_score_frames = 0
                            print("Wake listener rearmed.")

        except Exception as exc:
            if (
                not self._stop_requested
                and not self.isInterruptionRequested()
            ):
                self.failed.emit(f"Wake listener error: {exc}")
# --------------------------------------------------
# VOICE RECOGNITION WORKER
# --------------------------------------------------

class VoiceWorker(QThread):
    recognized = Signal(str)
    failed = Signal(str)

    def run(self):
        global WHISPER_MODEL

        try:
            if WHISPER_MODEL is None:
                print("Loading Faster-Whisper model...")

                WHISPER_MODEL = WhisperModel(
                    "base",
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=4,
                    num_workers=1,
                )

            audio = sd.rec(
                int(RECORD_SECONDS * SAMPLE_RATE),
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="int16",
                device=MICROPHONE_ID,
            )

            sd.wait()

            audio_float = (
                audio.reshape(-1).astype(np.float32) / 32768.0
            )

            segments, _info = WHISPER_MODEL.transcribe(
                audio_float,
                language="en",
                beam_size=1,
                best_of=1,
                temperature=0.0,
                vad_filter=True,
                condition_on_previous_text=False,
)

            text = " ".join(
                segment.text.strip() for segment in segments
            ).strip()

            if text:
                self.recognized.emit(text)
            else:
                self.failed.emit(
                    "No words recognized. Please speak clearly "
                    "and closer to the microphone."
                )

        except Exception as exc:
            self.failed.emit(f"Voice input failed: {exc}")


# --------------------------------------------------
# TEXT-TO-SPEECH WORKER
# --------------------------------------------------

class SpeechWorker(QThread):
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

            # Load the Piper model only once.
            if PIPER_VOICE is None:
                print("[TTS] Loading Piper voice model...")
                load_start = time.perf_counter()

                PIPER_VOICE = PiperVoice.load(
                    str(PIPER_MODEL_PATH)
                )

                print(
                    f"[TTS] Voice model loaded in "
                    f"{time.perf_counter() - load_start:.2f} seconds"
                )

            # Generate speech for every request.
            speech_start = time.perf_counter()
            print(f"[TTS] Starting synthesis: {self.text[:60]}")

            chunks = list(PIPER_VOICE.synthesize(self.text))

            print(
                f"[TTS] Synthesis completed in "
                f"{time.perf_counter() - speech_start:.2f} seconds"
            )

            if not chunks:
                print("[TTS] No audio was generated.")
                return

            audio_data = np.concatenate(
                [chunk.audio_int16_array for chunk in chunks]
            )

            sample_rate = PIPER_VOICE.config.sample_rate
            position = 0

            set_audio_state(
                source="spidey",
                level=0.0,
                spectrum=[0.0] * 48,
            )

            def playback_callback(outdata, frames, time_info, status):
                nonlocal position
                del time_info

                if status:
                    print(
                        f"Audio playback status: {status}",
                        file=sys.stderr,
                    )

                outdata.fill(0)

                remaining = len(audio_data) - position
                count = min(frames, remaining)

                if count <= 0:
                    raise sd.CallbackStop

                block = audio_data[position:position + count]
                outdata[:count, 0] = block
                position += count

                samples = block.astype(np.float32) / 32768.0

                if samples.size:
                    rms = float(np.sqrt(np.mean(samples * samples)))
                else:
                    rms = 0.0

                level = min(1.0, rms * 5.0)

                if samples.size > 1:
                    windowed = samples * np.hanning(samples.size)
                    magnitudes = np.abs(np.fft.rfft(windowed))

                    spectrum = np.interp(
                        np.linspace(0, len(magnitudes) - 1, 48),
                        np.arange(len(magnitudes)),
                        magnitudes,
                    )

                    spectrum = np.clip(
                        np.sqrt(spectrum) * 0.12,
                        0.0,
                        1.0,
                    )
                else:
                    spectrum = np.zeros(48, dtype=np.float32)

                set_audio_state(
                    source="spidey",
                    level=level,
                    spectrum=spectrum.tolist(),
                )

            try:
                playback_start = time.perf_counter()
                print("[TTS] Opening audio output stream...")

                with sd.OutputStream(
                    samplerate=sample_rate,
                    channels=1,
                    dtype="int16",
                    callback=playback_callback,
                ):
                    print(
                        f"[TTS] Output stream opened in "
                        f"{time.perf_counter() - playback_start:.2f} seconds"
                    )

                    while position < len(audio_data):
                        sd.sleep(20)

                print("[TTS] Playback finished.")

            finally:
                set_audio_state(
                    source="idle",
                    level=0.0,
                    spectrum=[0.0] * 48,
                )

        except Exception as exc:
            set_audio_state(
                source="idle",
                level=0.0,
                spectrum=[0.0] * 48,
            )
            print(f"[TTS] Error: {exc}")
            self.failed.emit(f"Speech error: {exc}")



# --------------------------------------------------
# MAIN WINDOW
# --------------------------------------------------

class SpideyWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Spidey AI")
        self.resize(850, 620)

        self.memory = MemoryStore()

        self.worker = None
        self.voice_worker = None
        self.speech_worker = None
        self.wake_worker = None

        self.pending_voice_send = False
        self.wake_pending = False
        self.wake_listener_paused = False
        self.allow_quit = False
        self.orb_process = None

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
            "Say 'Hey Jarvis' to start a voice command.\n"
            "You can also click Listen to dictate a message.\n"
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
        self.start_orb()
        self.start_wake_listener()
    # ----------------------------------------------
    # FLOATING ORB MANAGEMENT
    # ----------------------------------------------

    def start_orb(self):
        """Launch the floating orb as a separate process."""
        if (
            self.orb_process is not None
            and self.orb_process.poll() is None
        ):
            return

        project_root = Path(__file__).resolve().parent.parent

        try:
            self.orb_process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "app.ui.orb",
                ],
                cwd=str(project_root),
                creationflags=getattr(
                    subprocess,
                    "CREATE_NO_WINDOW",
                    0,
                ),
            )
        except Exception as exc:
            self.chat.append(
                f"\nSpidey Orb: Could not start the orb: {exc}"
            )

    def stop_orb(self):
        """Stop the separately launched orb when Spidey quits."""
        if (
            self.orb_process is not None
            and self.orb_process.poll() is None
        ):
            self.orb_process.terminate()

            try:
                self.orb_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.orb_process.kill()

        self.orb_process = None
    # ----------------------------------------------
    # SYSTEM TRAY
    # ----------------------------------------------

    def setup_tray(self):
        self.tray = QSystemTrayIcon(self)

        icon = self.style().standardIcon(
            QStyle.StandardPixmap.SP_ComputerIcon
        )

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
        self.wake_listener_paused = True

        self.stop_wake_listener()
        self.stop_orb()

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

    # ----------------------------------------------
    # WAKE-WORD MANAGEMENT
    # ----------------------------------------------

    def start_wake_listener(self):
        if self.allow_quit or self.wake_listener_paused:
            return

        if self.wake_worker is not None:
            return

        if self.voice_worker is not None:
            return

        if self.worker is not None and self.worker.isRunning():
            return

        if (
            self.speech_worker is not None
            and self.speech_worker.isRunning()
        ):
            return

        self.wake_worker = WakeWordWorker()
        self.wake_worker.wake_detected.connect(
            self.on_wake_detected
        )
        self.wake_worker.failed.connect(self.on_wake_error)
        self.wake_worker.finished.connect(
            self.on_wake_worker_finished
        )
        self.wake_worker.start()

    def stop_wake_listener(self):
        worker = self.wake_worker

        if worker is None:
            return

        if worker.isRunning():
            worker.stop()
            worker.wait()

        if self.wake_worker is worker:
            self.wake_worker = None

    def on_wake_detected(self):
        self.wake_pending = True
        set_orb_visibility(True)
        self.wake_listener_paused = True
        self.chat.append(
            "\nSpidey: Wake phrase detected. Listening for your command..."
        )

    def on_wake_worker_finished(self):
        worker = self.sender()

        if self.wake_worker is worker:
            self.wake_worker = None

        if self.wake_pending and not self.allow_quit:
            self.wake_pending = False
            self.listen_to_microphone(from_wake=True)
        else:
            self.start_wake_listener()

    def on_wake_error(self, error):
        print(error)
        self.chat.append(f"\nSpidey wake listener: {error}")

    # ----------------------------------------------
    # MICROPHONE / VOICE COMMANDS
    # ----------------------------------------------

    def listen_to_microphone(self, from_wake=False):
        if self.voice_worker is not None:
            return

        if self.worker is not None and self.worker.isRunning():
            self.chat.append(
                "Spidey: Wait for the current response before recording."
            )
            self.wake_listener_paused = False
            self.start_wake_listener()
            return

        self.stop_wake_listener()
        self.wake_listener_paused = True
        self.pending_voice_send = False

        self.listen_button.setEnabled(False)
        self.listen_button.setText("Listening...")

        self.chat.append(
            f"\nSpidey: Listening for {RECORD_SECONDS} seconds. "
            "Speak now..."
        )

        self.voice_worker = VoiceWorker()
        self.voice_worker.recognized.connect(
            self.on_voice_recognized
        )
        self.voice_worker.failed.connect(self.on_voice_error)
        self.voice_worker.finished.connect(
            self.on_voice_finished
        )

        # Wake-initiated commands are sent automatically.
        if from_wake:
            self.pending_voice_send = True

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

        if self.pending_voice_send:
            self.pending_voice_send = False

            if self.input.text().strip():
                self.send_message()
                return

        self.wake_listener_paused = False
        self.start_wake_listener()

    # ----------------------------------------------
    # SQLITE MEMORY COMMANDS
    # ----------------------------------------------

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

            if value is not None:
                return f"{key} = {value}"

            return f"No saved memory found for '{key}'."

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

    # ----------------------------------------------
    # CHAT
    # ----------------------------------------------

    @staticmethod
    def is_current_time_question(message):
        """Recognize common requests for the computer's current local time."""
        text = message.lower().strip()
        patterns = (
            "what time is it",
            "what's the time",
            "what is the time",
            "tell me the time",
            "current time",
            "time right now",
            "time now",
            "time is it",
            "what time",
            "tell me what time",
        )
        return any(pattern in text for pattern in patterns)

    def send_message(self):
        message = self.input.text().strip()

        if not message:
            return

        if self.worker is not None and self.worker.isRunning():
            return

        if self.voice_worker is not None:
            self.chat.append(
                "Spidey: Wait for voice recording to finish first."
            )
            return

        self.stop_wake_listener()
        self.wake_listener_paused = True

        self.input.clear()
        self.chat.append(f"\nYou: {message}")

        memory_reply = self.handle_memory_command(message)

        if memory_reply is not None:
            self.chat.append(f"\nSpidey: {memory_reply}")
            self.speak_reply(memory_reply)
            return

        # Handle current-time questions directly using Windows' system clock.
        # This must run before Ollama so the model cannot guess the time.
        if self.is_current_time_question(message):
            now = datetime.now().astimezone()
            time_reply = (
                f"The current time is {now.strftime('%I:%M %p').lstrip('0')} "
                f"on {now.strftime('%A, %d %B %Y')}."
            )
            self.chat.append(f"\nSpidey: {time_reply}")
            self.speak_reply(time_reply)
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
        request_messages.append(
            {"role": "user", "content": message}
        )

        self.messages.append(
            {"role": "user", "content": message}
        )

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
        self.messages.append(
            {"role": "assistant", "content": reply}
        )

        self.chat.append(f"\nSpidey: {reply}")
        self.speak_reply(reply)

    def speak_reply(self, text):
        if (
            self.speech_worker is not None
            and self.speech_worker.isRunning()
        ):
            self.chat.append(
                "Spidey voice: Previous speech is still playing."
            )
            return

        self.stop_wake_listener()
        self.wake_listener_paused = True

        self.speech_worker = SpeechWorker(text)
        self.speech_worker.failed.connect(
            lambda error: self.chat.append(
                f"Spidey voice: {error}"
            )
        )
        self.speech_worker.finished.connect(
            self.on_speech_finished
        )
        self.speech_worker.start()

    def on_speech_finished(self):
        self.speech_worker = None
        set_orb_visibility(False)
        self.wake_listener_paused = False
        self.start_wake_listener()

    def on_ai_error(self, error):
        if (
            self.messages
            and self.messages[-1]["role"] == "user"
        ):
            self.messages.pop()

        self.chat.append(f"\nSpidey error: {error}")

    def on_worker_finished(self):
        self.send_button.setEnabled(True)
        self.new_chat_button.setEnabled(True)
        self.listen_button.setEnabled(True)
        self.input.setEnabled(True)
        self.worker = None

        if (
            self.speech_worker is None
            or not self.speech_worker.isRunning()
        ):
            self.wake_listener_paused = False
            self.start_wake_listener()

    def new_chat(self):
        if self.worker is not None and self.worker.isRunning():
            return

        if self.voice_worker is not None:
            return

        self.messages = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

        self.chat.clear()
        self.chat.append(
            "Spidey: New chat started. Saved SQLite memories remain."
        )


# --------------------------------------------------
# APPLICATION ENTRY POINT
# --------------------------------------------------

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Spidey AI")

    # Keep the application running when its window is hidden.
    app.setQuitOnLastWindowClosed(False)

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