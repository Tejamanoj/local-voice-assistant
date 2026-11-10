
"""Shared audio state between Spidey's separate processes."""

import json
import os
import tempfile
import threading
import time
from pathlib import Path

_LOCK = threading.RLock()
_STATE_FILE = (
    Path(__file__).resolve().parents[2]
    / "spidey_audio_state.json"
)

_LAST_MIC_WRITE = 0.0


def set_audio_state(source, level=0.0, spectrum=None):
    """Publish audio measurements to a local shared file."""
    global _LAST_MIC_WRITE

    now = time.monotonic()

    with _LOCK:
        # Avoid microphone updates overriding active speech playback.
        if source == "microphone":
            if now - _LAST_MIC_WRITE < 0.15:
                return
            _LAST_MIC_WRITE = now

            current = get_audio_state()

            if current["source"] == "spidey":
                return

        state = {
            "source": source,
            "level": max(0.0, min(1.0, float(level))),
            "spectrum": [
                max(0.0, min(1.0, float(value)))
                for value in (spectrum or [0.0] * 48)
            ],
            "updated": time.time(),
        }

        # Write a temporary file and replace the state file atomically.
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=_STATE_FILE.parent,
                suffix=".tmp",
                delete=False,
            ) as file:
                json.dump(state, file)
                temp_path = file.name

            os.replace(temp_path, _STATE_FILE)

        except OSError:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass


def get_audio_state():
    """Read the latest shared audio state."""
    try:
        with _LOCK:
            with _STATE_FILE.open(
                "r", encoding="utf-8"
            ) as file:
                state = json.load(file)

        # Recover if a process stops unexpectedly.
        if time.time() - state.get("updated", 0) > 2.0:
            return {
                "source": "idle",
                "level": 0.0,
                "spectrum": [0.0] * 48,
            }

        return {
            "source": state.get("source", "idle"),
            "level": float(state.get("level", 0.0)),
            "spectrum": state.get(
                "spectrum", [0.0] * 48
            ),
        }

    except (OSError, ValueError, TypeError):
        return {
            "source": "idle",
            "level": 0.0,
            "spectrum": [0.0] * 48,
        }

def set_orb_visibility(visible):
    """Tell the orb process whether it should be visible."""
    control_file = (
        Path(__file__).resolve().parents[2]
        / "spidey_orb_control.json"
    )

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=control_file.parent,
            suffix=".tmp",
            delete=False,
        ) as file:
            json.dump({"visible": bool(visible)}, file)
            temp_path = file.name

        os.replace(temp_path, control_file)

    except OSError:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def get_orb_visibility():
    """Read the requested visibility of the orb."""
    control_file = (
        Path(__file__).resolve().parents[2]
        / "spidey_orb_control.json"
    )

    try:
        with control_file.open("r", encoding="utf-8") as file:
            state = json.load(file)
        return bool(state.get("visible", False))
    except (OSError, ValueError, TypeError):
        return False

