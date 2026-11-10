
import sounddevice as sd
import numpy as np
from faster_whisper import WhisperModel

SAMPLE_RATE = 16000
DURATION = 10
MICROPHONE_ID = 1

print("Loading Whisper base model on CPU...")
print("The first run may download the model and take a few minutes.")

model = WhisperModel("small", device="cpu", compute_type="int8")

print(f"\nSpeak clearly for {DURATION} seconds.")
audio = sd.rec(
    int(DURATION * SAMPLE_RATE),
    samplerate=SAMPLE_RATE,
    channels=1,
    dtype="int16",
    device=MICROPHONE_ID,
)
sd.wait()

audio_float = audio.reshape(-1).astype(np.float32) / 32768.0

print("\nTranscribing...")
segments, info = model.transcribe(
    audio_float,
    language="en",
    beam_size=5,
    vad_filter=True,
)

recognized_text = " ".join(
    segment.text.strip() for segment in segments
).strip()

print("\nRecognized:", recognized_text or "(no speech recognized)")
