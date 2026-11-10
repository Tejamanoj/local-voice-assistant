
import json
import sounddevice as sd
from vosk import Model, KaldiRecognizer

MODEL_PATH = (
    r"vosk-model-small-en-us-0.15"
    r"\vosk-model-small-en-us-0.15"
)

SAMPLE_RATE = 16000
DURATION = 5
MICROPHONE_ID = 1

print("Loading offline speech model...")
model = Model(MODEL_PATH)
recognizer = KaldiRecognizer(model, SAMPLE_RATE)

print(f"Speak clearly for {DURATION} seconds...")
audio = sd.rec(
    int(DURATION * SAMPLE_RATE),
    samplerate=SAMPLE_RATE,
    channels=1,
    dtype="int16",
    device=MICROPHONE_ID,
)
sd.wait()

print("Processing audio locally...")
audio_bytes = audio.tobytes()
recognizer.AcceptWaveform(audio_bytes)
result = json.loads(recognizer.FinalResult())

text = result.get("text", "").strip()

if text:
    print("Recognized words:", text)
else:
    print("No words recognized. Try speaking louder or closer to the microphone.")
