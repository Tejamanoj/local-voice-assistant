import time

import sounddevice as sd
from openwakeword.model import Model


SAMPLE_RATE = 16000
CHUNK_SIZE = 1280

WAKE_THRESHOLD = 0.60
RESET_THRESHOLD = 0.10

# Require several consecutive low scores before rearming.
RESET_FRAMES_REQUIRED = 20
COOLDOWN_SECONDS = 3.0


def main():
    print("Loading wake-word model...")

    model = Model(
        wakeword_models=["hey_jarvis"],
        inference_framework="onnx",
    )

    print("Spidey wake listener is running.")
    print("Say 'Hey Jarvis' to test detection.")
    print("Press Ctrl+C to stop.")

    last_detection_time = 0.0
    armed = True
    low_score_frames = 0

    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            blocksize=CHUNK_SIZE,
            channels=1,
            dtype="int16",
        ) as stream:

            while True:
                audio, overflowed = stream.read(CHUNK_SIZE)

                if overflowed:
                    print("\nWarning: microphone input overflowed.")

                prediction = model.predict(audio.reshape(-1))
                score = float(prediction.get("hey_jarvis", 0.0))
                now = time.monotonic()

                if armed:
                    if (
                        score >= WAKE_THRESHOLD
                        and now - last_detection_time >= COOLDOWN_SECONDS
                    ):
                        print(
                            f"\nWake phrase detected! Score: {score:.3f}"
                        )

                        last_detection_time = now
                        armed = False
                        low_score_frames = 0

                    else:
                        print(
                            f"Listening... score: {score:.3f}",
                            end="\r",
                            flush=True,
                        )

                else:
                    if score < RESET_THRESHOLD:
                        low_score_frames += 1
                    else:
                        low_score_frames = 0

                    if low_score_frames >= RESET_FRAMES_REQUIRED:
                        armed = True
                        low_score_frames = 0
                        print(
                            "\nWake listener rearmed.",
                            flush=True,
                        )

    except KeyboardInterrupt:
        print("\nWake listener stopped.")

    except Exception as error:
        print(f"\nWake listener error: {error}")


if __name__ == "__main__":
    main()
