# Local Voice Assistant (Spidey AI)

A private, local-first voice assistant built for Windows 11 with wake-word detection, offline speech recognition, local AI inference, text-to-speech, and a floating animated orb.

---

## Features

- **Wake-Word Detection**: Always-listening wake word ("Hey Jarvis") powered locally by OpenWakeWord with minimal CPU footprint.
- **Offline Speech-to-Text**: Fast and accurate local transcription using Faster-Whisper.
- **Local AI Brain**: Powered by Ollama (`qwen2.5:3b`) for intelligent conversation and tool use without sending data to external clouds.
- **Local Text-to-Speech**: High-quality natural voice synthesis using Piper TTS (`en_US-lessac-medium`).
- **Interactive Floating Orb**: Animated PySide6 floating orb that appears when the wake word is detected and reacts to voice states.
- **Laptop & System Tools**: Built-in tools for system info, media controls, and browser actions (including YouTube integration).
- **Persistent Local Memory**: SQLite-based memory system storing preferences and context locally.

---

## Architecture & Workflow

```text
Idle ("Hey Jarvis" listening)
        │
        ▼ (Wake detected)
Floating Orb Appears  ──► Wake Listener Pauses
        │
        ▼
Voice Recording & Faster-Whisper Transcription
        │
        ▼
Ollama Reasoning (qwen2.5:3b) & Tool Execution
        │
        ▼
Piper TTS Voice Playback
        │
        ▼
Floating Orb Hides  ──► Wake Listener Rearms & Resumes
```

---

## Tech Stack & Hardware

- **OS**: Windows 11
- **Python**: 3.12+
- **Speech Stack**:
  - OpenWakeWord (0.6.0) with ONNX Runtime
  - Faster-Whisper
  - Piper TTS (1.8.0)
- **AI / LLM**: Ollama (`qwen2.5:3b`)
- **GUI**: PySide6 (Qt)
- **Storage**: SQLite

---

## Getting Started

### 1. Prerequisites

- [Ollama](https://ollama.com/) installed and running.
- Pull the local model:
  ```bash
  ollama pull qwen2.5:3b
  ```

### 2. Setup Virtual Environment

```powershell
cd "$HOME\SpideyAI"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Launch Spidey AI

```powershell
cd "$HOME\SpideyAI"
.\.venv\Scripts\Activate.ps1
python -m app.main
```

---

## How to Interact

1. Say **"Hey Jarvis"**.
2. Wait for the floating orb to appear on your screen.
3. Speak your command (e.g., *"What time is it?"*, *"Check battery level"*).
4. The assistant will speak the response and the orb will automatically hide.
5. Say **"Hey Jarvis"** again whenever you are ready for the next command.

---

## License

This project is licensed under the MIT License.
